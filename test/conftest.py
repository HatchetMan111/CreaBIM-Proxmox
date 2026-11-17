"""Test-Gemeincode: Stub-CLI, TestClient, Job-Polling."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "app" / "backend"
STUB = ROOT / "test" / "stub_creabim_cli.py"

# main.py liest CREABIM_* erst beim App-Start → Env vor dem Import setzen.
os.environ.setdefault("CREABIM_CLI", str(STUB))
os.environ.setdefault("CREABIM_TIMEOUT", "60")
os.environ.pop("CREABIM_DATA_DIR", None)
sys.path.insert(0, str(BACKEND))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Ein frischer App-Zustand pro Test (eigener Datenordner)."""
    from fastapi.testclient import TestClient

    monkeypatch.setenv("CREABIM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CREABIM_CLI", str(STUB))
    monkeypatch.delenv("STUB_FAIL", raising=False)
    monkeypatch.delenv("STUB_NO_ARTIFACT", raising=False)
    monkeypatch.delenv("STUB_CHECK_FINDINGS", raising=False)

    import main  # noqa: PLC0415 – Import erst nach den Env-Variablen

    with TestClient(main.app) as test_client:
        yield test_client


def wait_for_job(client, job_id: str, timeout: float = 15.0) -> dict:
    """Job bis zum Endzustand pollen (queued/running → done/error)."""
    deadline = time.time() + timeout
    job: dict = {}
    while time.time() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200, response.text
        job = response.json()["job"]
        if job["status"] in ("done", "error"):
            return job
        time.sleep(0.05)
    raise AssertionError(f"Job {job_id} blieb im Status {job.get('status')!r}")


def start_job(client, pid: str, action: str, params: dict | None = None) -> dict:
    """Job anlegen und bis zum Ergebnis pollen."""
    response = client.post(f"/api/projects/{pid}/jobs",
                           json={"action": action, "params": params or {}})
    assert response.status_code in (200, 202), response.text
    job_id = response.json()["job"]["id"]
    return wait_for_job(client, job_id)


def new_project(client, name: str = "Testhaus") -> str:
    response = client.post("/api/projects", json={"sample": "starter", "name": name})
    assert response.status_code == 201, response.text
    return response.json()["project"]["id"]