"""Integrationstests gegen das ECHTE creabim-cli (optional).

Voraussetzung: das Release-Binary liegt vor und CREABIM_TEST_CLI zeigt darauf,
z. B.

    CREABIM_TEST_CLI=/opt/creabim/bin/creabim-cli pytest test/ -q

Ohne diese Variable werden die Tests übersprungen – die schnelle Suite
(``test_api.py``) arbeitet mit der Stub-CLI.
"""

from __future__ import annotations

import os

import pytest
from conftest import new_project, start_job

REAL_CLI = os.environ.get("CREABIM_TEST_CLI", "").strip()

pytestmark = pytest.mark.skipif(
    not REAL_CLI or not os.path.exists(REAL_CLI),
    reason="CREABIM_TEST_CLI nicht gesetzt oder Binary fehlt")


@pytest.fixture()
def real_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("CREABIM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CREABIM_CLI", REAL_CLI)
    monkeypatch.delenv("STUB_FAIL", raising=False)
    monkeypatch.delenv("STUB_NO_ARTIFACT", raising=False)

    import main

    with TestClient(main.app) as test_client:
        yield test_client


def test_real_structure(real_client):
    pid = new_project(real_client)
    structure = real_client.get(f"/api/projects/{pid}/structure").json()["structure"]
    assert structure["levels"] == ["Foundation", "Ground Floor", "First Floor"]
    assert len(structure["views"]) == 23
    assert len(structure["sheets"]) == 13
    assert structure["stats"]["IfcWall"] == 24
    assert structure["stats"]["IfcFurniture"] == 119


def test_real_plan_svg(real_client):
    pid = new_project(real_client)
    job = start_job(real_client, pid, "plan", {"level": "Ground Floor"})
    assert job["status"] == "done", job.get("report")
    art = real_client.get(f"/api/jobs/{job['id']}/artifact")
    assert art.status_code == 200
    assert art.content.startswith(b"<svg")


def test_real_sheet_svg(real_client):
    pid = new_project(real_client)
    job = start_job(real_client, pid, "sheet", {"number": "A101"})
    assert job["status"] == "done", job.get("report")
    assert real_client.get(f"/api/jobs/{job['id']}/artifact").content.startswith(b"<svg")


def test_real_pdf(real_client):
    pid = new_project(real_client)
    job = start_job(real_client, pid, "pdf")
    assert job["status"] == "done", job.get("report")
    content = real_client.get(f"/api/jobs/{job['id']}/artifact").content
    assert content.startswith(b"%PDF")
    assert len(content) > 100_000


def test_real_ifc_export(real_client):
    pid = new_project(real_client)
    job = start_job(real_client, pid, "ifc")
    assert job["status"] == "done", job.get("report")
    content = real_client.get(f"/api/jobs/{job['id']}/artifact").content
    assert b"ISO-10303-21" in content[:200]


def test_real_schedule_csv(real_client):
    pid = new_project(real_client)
    job = start_job(real_client, pid, "schedule", {"kind": "doors"})
    assert job["status"] == "done", job.get("report")
    text = real_client.get(f"/api/jobs/{job['id']}/artifact").text
    assert text.startswith("Mark,Type")
    assert "D01" in text


def test_real_check_reports_clean(real_client):
    pid = new_project(real_client)
    job = start_job(real_client, pid, "check")
    assert job["status"] == "done"
    assert job["result"]["ok"] is True


def test_real_stats(real_client):
    pid = new_project(real_client)
    job = start_job(real_client, pid, "stats")
    assert job["status"] == "done"
    assert job["result"]["IfcWall"] == 24


def test_real_error_chain(real_client):
    """Ein unbekannter Ansichtsname muss zu einem Job-Fehler mit Kette führen."""
    pid = new_project(real_client)
    real_client.get(f"/api/projects/{pid}")
    response = real_client.post(f"/api/projects/{pid}/jobs",
                                json={"action": "view", "params": {"name": "Quatsch"}})
    # Die Strukturprüfung fängt das vor dem CLI-Aufruf ab.
    assert response.status_code == 400
    assert "Quatsch" in response.json()["detail"]