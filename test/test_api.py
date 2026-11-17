"""API-Tests gegen die Stub-CLI (kein echtes CreaBIM nötig)."""

from __future__ import annotations

import io
import json

import pytest
from conftest import new_project, start_job, wait_for_job


# ── Grundlagen ─────────────────────────────────────────────────────────────
def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["cli"].endswith("stub_creabim_cli.py")
    assert body["errors"] == []


def test_info(client):
    body = client.get("/api/info").json()
    assert body["upstream"] == "chopinregis/CreaBIM"
    keys = {a["key"] for a in body["actions"]}
    assert {"plan", "view", "sheet", "pdf", "ifc", "schedule", "check"} <= keys
    plan = next(a for a in body["actions"] if a["key"] == "plan")
    assert plan["params"][0]["kind"] == "level"
    assert {s["key"] for s in body["samples"]} == {
        "starter", "simple", "layered", "typed", "furnished", "garden"}


def test_spa_is_served_or_explains_itself(client):
    # Mit gebautem Frontend (static/index.html) kommt die SPA, ohne Build eine
    # verständliche 503 – ein 500er ist in beiden Fällen falsch.
    response = client.get("/")
    assert response.status_code in (200, 503)
    if response.status_code == 503:
        assert "static/index.html" in response.json()["error"]


# ── Projekte ───────────────────────────────────────────────────────────────
def test_create_list_and_structure(client):
    pid = new_project(client, "Mein Haus")
    listed = client.get("/api/projects").json()["projects"]
    assert [p["id"] for p in listed] == [pid]

    detail = client.get(f"/api/projects/{pid}").json()
    assert detail["project"]["name"] == "Mein Haus"
    structure = detail["structure"]
    assert structure["levels"] == ["Foundation", "Ground Floor", "First Floor"]
    assert structure["views"][0]["name"] == "Ground Floor plan"
    assert structure["sheets"][0]["number"] == "A101"
    assert structure["stats"]["IfcWall"] == 24


def test_structure_is_cached(client):
    pid = new_project(client)
    first = client.get(f"/api/projects/{pid}/structure").json()["structure"]
    second = client.get(f"/api/projects/{pid}/structure").json()["structure"]
    assert first["model_sig"] == second["model_sig"]
    assert first["generated"] == second["generated"]


def test_rename_and_delete(client):
    pid = new_project(client)
    renamed = client.patch(f"/api/projects/{pid}", json={"name": "Neuer Name"})
    assert renamed.status_code == 200
    assert renamed.json()["project"]["name"] == "Neuer Name"

    assert client.delete(f"/api/projects/{pid}").status_code == 200
    assert client.get(f"/api/projects/{pid}").status_code == 404


def test_rename_rejects_empty(client):
    pid = new_project(client)
    assert client.patch(f"/api/projects/{pid}", json={"name": "  "}).status_code == 400


def test_unknown_sample(client):
    response = client.post("/api/projects", json={"sample": "gibt-es-nicht"})
    assert response.status_code == 400
    assert "Unbekanntes Beispiel" in response.json()["detail"]


def test_path_traversal_is_blocked(client):
    assert client.get("/api/projects/..%2F..%2Fetc").status_code in (400, 404)
    assert client.get("/api/projects/%2e%2e%2f%2e%2e%2fetc").status_code in (400, 404)
    assert client.get("/api/projects/nixda").status_code == 404


def test_model_download(client):
    pid = new_project(client)
    response = client.get(f"/api/projects/{pid}/model")
    assert response.status_code == 200
    assert json.loads(response.text)["version"] == "1.1.2"


# ── Import ─────────────────────────────────────────────────────────────────
def test_import_ifc(client):
    payload = b"ISO-10303-21;\nHEADER;\nENDSEC;\nEND-ISO-10303-21;\n"
    response = client.post("/api/projects/import",
                           files={"file": ("haus.ifc", io.BytesIO(payload), "application/step")},
                           data={"name": "Importiert"})
    assert response.status_code == 201, response.text
    project = response.json()["project"]
    assert project["kind"] == "ifc"
    assert project["name"] == "Importiert"
    assert client.get(f"/api/projects/{project['id']}").status_code == 200


def test_import_rejects_unknown_type(client):
    response = client.post("/api/projects/import",
                           files={"file": ("haus.xyz", io.BytesIO(b"nix"), "application/octet-stream")})
    assert response.status_code == 400
    assert "Dateityp nicht unterstützt" in response.json()["detail"]


def test_import_rejects_empty(client):
    response = client.post("/api/projects/import",
                           files={"file": ("haus.ifc", io.BytesIO(b""), "application/step")})
    assert response.status_code == 400


# ── Jobs ───────────────────────────────────────────────────────────────────
def test_plan_job_produces_svg(client):
    pid = new_project(client)
    job = start_job(client, pid, "plan", {"level": "Ground Floor"})
    assert job["status"] == "done"
    assert job["artifact"].endswith(".svg")
    assert job["exit_code"] == 0
    assert job["duration_ms"] is not None

    art = client.get(f"/api/jobs/{job['id']}/artifact?inline=1")
    assert art.status_code == 200
    assert art.headers["content-type"].startswith("image/svg+xml")
    assert 'sandbox' in art.headers["content-security-policy"]
    assert art.headers["content-disposition"].startswith("inline")
    assert b"<svg" in art.content


def test_view_job_and_unknown_view(client):
    pid = new_project(client)
    job = start_job(client, pid, "view", {"name": "Section A-A"})
    assert job["status"] == "done"

    response = client.post(f"/api/projects/{pid}/jobs",
                           json={"action": "view", "params": {"name": "Quatsch"}})
    assert response.status_code == 400
    assert "Ansicht 'Quatsch'" in response.json()["detail"]


def test_sheet_job(client):
    pid = new_project(client)
    job = start_job(client, pid, "sheet", {"number": "A101"})
    assert job["status"] == "done"
    assert job["result"]["size"] > 0


def test_stats_and_views_are_parsed(client):
    pid = new_project(client)
    stats = start_job(client, pid, "stats")
    assert stats["result"]["IfcWall"] == 24

    views = start_job(client, pid, "views")
    assert views["result"][0] == {"kind": "plan", "scale": "1:50",
                                  "name": "Ground Floor plan"}


def test_check_ok_and_findings(client, monkeypatch):
    pid = new_project(client)
    ok_job = start_job(client, pid, "check")
    assert ok_job["status"] == "done"
    assert ok_job["result"]["ok"] is True

    monkeypatch.setenv("STUB_CHECK_FINDINGS", "1")
    findings = start_job(client, pid, "check")
    assert findings["status"] == "done"
    assert findings["result"]["ok"] is False
    assert "door swing" in findings["result"]["text"]


def test_schedule_job(client):
    pid = new_project(client)
    job = start_job(client, pid, "schedule", {"kind": "doors"})
    assert job["status"] == "done"
    assert job["artifact"].endswith(".csv")
    assert b"Mark,Type" in client.get(f"/api/jobs/{job['id']}/artifact").content


def test_schedule_rejects_unknown_kind(client):
    pid = new_project(client)
    response = client.post(f"/api/projects/{pid}/jobs",
                           json={"action": "schedule", "params": {"kind": "Tueren"}})
    assert response.status_code == 400


def test_pdf_job_and_download(client):
    pid = new_project(client)
    job = start_job(client, pid, "pdf")
    assert job["status"] == "done"
    art = client.get(f"/api/jobs/{job['id']}/artifact")
    assert art.status_code == 200
    assert art.headers["content-disposition"].startswith("attachment")
    assert art.content.startswith(b"%PDF")


def test_unknown_action(client):
    pid = new_project(client)
    response = client.post(f"/api/projects/{pid}/jobs", json={"action": "zauber"})
    assert response.status_code == 400


def test_job_on_missing_project(client):
    response = client.post("/api/projects/gibt-es-nicht/jobs", json={"action": "stats"})
    assert response.status_code == 404


# ── Fehlerpfade ────────────────────────────────────────────────────────────
def test_cli_failure_is_reported(client, monkeypatch):
    pid = new_project(client)          # Projekt vor dem Fehler anlegen
    client.get(f"/api/projects/{pid}")  # Struktur cachen (sonst scheitert schon das Validieren)
    monkeypatch.setenv("STUB_FAIL", "1")
    job = start_job(client, pid, "view", {"name": "Section A-A"})
    assert job["status"] == "error"
    # Die Fehlermeldung muss lesbar sein – ohne den kompletten Usage-Block.
    assert "no view named" in job["error"]
    assert "usage:" not in job["error"]
    assert "Exit-Code" in job["report"]

    report = client.get(f"/api/jobs/{job['id']}/report")
    assert report.status_code == 200
    assert "--- stderr ---" in report.text


def test_missing_artifact_is_an_error(client, monkeypatch):
    monkeypatch.setenv("STUB_NO_ARTIFACT", "1")
    pid = new_project(client)
    job = start_job(client, pid, "pdf")
    assert job["status"] == "error"
    assert "keine Datei erzeugt" in job["error"]


def test_job_list_and_limit(client):
    pid = new_project(client)
    start_job(client, pid, "stats")
    start_job(client, pid, "stats")
    jobs = client.get("/api/jobs?limit=1").json()["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["status"] in ("done", "error")


def test_artifact_of_text_job_is_gone(client):
    pid = new_project(client)
    job = start_job(client, pid, "stats")
    assert not job["artifact"]       # stats hat kein Artefakt (nur stdout)
    # Ein Download auf einen Job ohne Datei muss 404 liefern, nicht 500.
    response = client.get(f"/api/jobs/{job['id']}/artifact")
    assert response.status_code == 404


def test_rooms_from_notes_produces_model(client):
    pid = new_project(client)
    job = start_job(client, pid, "rooms-from-notes")
    assert job["status"] == "done"
    assert job["result"]["filename"].endswith(".creabim.json")
    art = client.get(f"/api/jobs/{job['id']}/artifact")
    assert art.status_code == 200


def test_unknown_job(client):
    assert client.get("/api/jobs/does-not-exist").status_code == 404

# ── Gespeicherte Projekte mit reinem .json-Namen ───────────────────────────
SAVED_PROJECT_JSON = {
    "version": 1,
    "levels": [{"id": "Ground Floor"}],
    "views": [{"id": "Plan", "kind": "plan",
               "viewports": [{"view": "Plan", "at": [10, 10]}]}],
}


def test_saved_project_with_plain_json_name_imports_natively(client):
    """CreaBIM-Speicherstände enden manchmal nur auf .json (Browser-Umbenennung,
    Doppel-Download). Der Server muss sie nativ übernehmen, nicht als Spec bauen."""
    response = client.post(
        "/api/projects/import",
        files={"file": ("dratboden-konzept.creabim (1).json",
                        io.BytesIO(json.dumps(SAVED_PROJECT_JSON).encode()),
                        "application/json")})
    assert response.status_code == 201, response.text
    project = response.json()["project"]
    assert project["kind"] == "creabim-json"
    assert any("gespeichertes CreaBIM-Projekt" in line
               for line in project.get("import_report", []))
    assert client.get(f"/api/projects/{project['id']}").status_code == 200


def test_real_spec_json_still_builds(client):
    """Eine echte Build-Spec ohne Viewports geht weiterhin durch `build`."""
    spec = {"version": 1, "levels": [{"id": "Ground Floor", "elevation": 0}],
            "walls": [{"id": "W", "level": "Ground Floor",
                       "start": [0, 0], "end": [5, 0], "thickness": 0.2}]}
    response = client.post(
        "/api/projects/import",
        files={"file": ("spec.json", io.BytesIO(json.dumps(spec).encode()),
                        "application/json")})
    assert response.status_code == 201, response.text
    assert response.json()["project"]["kind"] == "spec"
