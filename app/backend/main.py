#!/usr/bin/env python3
"""CreaBIM-Server – FastAPI-Frontend um die headless CreaBIM-CLI.

Startet die React/Vite-SPA aus ``static/`` und stellt darunter eine kleine
JSON-API bereit, die Projekte verwaltet und Modell-Aktionen als Jobs ausführt.

Umgebungsvariablen:
  CREABIM_DATA_DIR   Datenverzeichnis (Projekte, Job-Artefakte) – Default /opt/creabim/data
  CREABIM_CLI        Pfad zur creabim-cli – Default /opt/creabim/bin/creabim-cli
  CREABIM_VERSION    Version der App (nur Anzeige)
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from creabim_cli import ACTION_BY_KEY, ACTIONS, CliError, CliRunner, find_cli
from jobs import JobManager
from library import SAMPLES, Library, ProjectNotFound

APP_VERSION = os.environ.get("CREABIM_VERSION", "1.0.0")
DEFAULT_DATA_DIR = "/opt/creabim/data"
STATIC_DIR = Path(__file__).resolve().parent / "static"

library: Library
jobs: JobManager


def _make_library() -> Library:
    """CLI suchen und Library aufbauen – Fehler gehören in den Start-Log."""
    binary = find_cli()
    runner = CliRunner(binary, timeout=int(os.environ.get("CREABIM_TIMEOUT", "300")))
    data_dir = os.environ.get("CREABIM_DATA_DIR") or DEFAULT_DATA_DIR
    return Library(data_dir, runner)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global library, jobs
    app.state.startup_errors = []
    try:
        library = _make_library()
    except CliError as exc:
        # Der Container soll starten, damit journalctl die Ursache zeigt.
        app.state.startup_errors.append(str(exc))
        library = None  # type: ignore[assignment]
    jobs = JobManager(library, workers=int(os.environ.get("CREABIM_WORKERS", "2"))) \
        if library else None  # type: ignore[assignment]
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    yield
    if jobs is not None:
        jobs.shutdown()


app = FastAPI(
    title="CreaBIM Server",
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)


# ── Hilfsfunktionen ────────────────────────────────────────────────────────
def _require_library() -> Library:
    if library is None:
        raise HTTPException(
            503,
            "creabim-cli wurde nicht gefunden – Installation prüfen "
            "(journalctl -u creabim-server -e).",
        )
    return library


def _project(pid: str) -> dict[str, Any]:
    try:
        return _require_library().get(pid)
    except ProjectNotFound as exc:
        raise HTTPException(404, str(exc)) from exc


def _job(jid: str):
    if jobs is None:
        raise HTTPException(503, "Job-Manager nicht verfügbar.")
    try:
        return jobs.get(jid)
    except KeyError as exc:
        raise HTTPException(404, f"Job {jid} unbekannt") from exc


# ── API: Info ──────────────────────────────────────────────────────────────
@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok" if library is not None else "degraded",
        "version": APP_VERSION,
        "cli": library.runner.binary if library else None,
        "data_dir": str(library.root) if library else DEFAULT_DATA_DIR,
        "errors": getattr(app.state, "startup_errors", []),
    }


@app.get("/api/info")
def info() -> dict[str, Any]:
    """Alles, was das Frontend zum Rendern der Oberfläche braucht."""
    lib = _require_library()
    return {
        "app": "CreaBIM Server",
        "version": APP_VERSION,
        "upstream": "chopinregis/CreaBIM",
        "cli": lib.runner.binary,
        "data_dir": str(lib.root),
        "actions": [
            {
                "key": a.key,
                "label": a.label,
                "group": a.group,
                "description": a.description,
                "output": a.output,
                "params": [
                    {"name": p.name, "label": p.label, "kind": p.kind,
                     "choices": list(p.choices), "default": p.default}
                    for p in a.params
                ],
            }
            for a in ACTIONS
        ],
        "samples": [
            {"key": k, "name": v["name"], "description": v["description"]}
            for k, v in SAMPLES.items()
        ],
    }


# ── API: Projekte ──────────────────────────────────────────────────────────
@app.get("/api/projects")
def list_projects() -> dict[str, Any]:
    return {"projects": _require_library().list_projects()}


@app.post("/api/projects", status_code=201)
def create_project(payload: dict[str, Any]) -> dict[str, Any]:
    lib = _require_library()
    sample = str(payload.get("sample") or "starter")
    name = (payload.get("name") or "").strip() or None
    try:
        project = lib.create_sample(sample, name)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except CliError as exc:
        raise HTTPException(500, exc.report()) from exc
    return {"project": project}


@app.post("/api/projects/import", status_code=201)
async def import_project(file: UploadFile = File(...),
                         name: str | None = Form(default=None)) -> dict[str, Any]:
    lib = _require_library()
    data = await file.read()
    if not data:
        raise HTTPException(400, "Die hochgeladene Datei ist leer.")
    try:
        project = lib.import_model(file.filename or "modell", data, name)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except CliError as exc:
        raise HTTPException(400, exc.report()) from exc
    return {"project": project}


@app.get("/api/projects/{pid}")
def get_project(pid: str) -> dict[str, Any]:
    meta = _project(pid)
    structure = _require_library().structure(pid)
    return {"project": meta, "structure": structure}


@app.patch("/api/projects/{pid}")
def rename_project(pid: str, payload: dict[str, Any]) -> dict[str, Any]:
    _project(pid)
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Ein Name ist erforderlich.")
    return {"project": _require_library().rename(pid, name)}


@app.delete("/api/projects/{pid}")
def delete_project(pid: str) -> dict[str, Any]:
    lib = _require_library()
    try:
        lib.delete(pid)
    except ProjectNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"deleted": pid}


@app.get("/api/projects/{pid}/structure")
def project_structure(pid: str, refresh: bool = Query(default=False)) -> dict[str, Any]:
    lib = _require_library()
    try:
        return {"structure": lib.structure(pid, refresh=refresh)}
    except ProjectNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except CliError as exc:
        raise HTTPException(500, exc.report()) from exc


@app.get("/api/projects/{pid}/model")
def download_model(pid: str) -> FileResponse:
    lib = _require_library()
    meta = _project(pid)
    path = lib.model_path(meta)
    if not path.exists():
        raise HTTPException(404, "Modelldatei fehlt.")
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")


# ── API: Jobs ──────────────────────────────────────────────────────────────
@app.post("/api/projects/{pid}/jobs", status_code=202)
def create_job(pid: str, payload: dict[str, Any]) -> dict[str, Any]:
    _project(pid)
    if jobs is None:
        raise HTTPException(503, "Job-Manager nicht verfügbar.")
    action = str(payload.get("action") or "")
    if action not in ACTION_BY_KEY:
        raise HTTPException(400, f"Unbekannte Aktion: {action}")
    params = payload.get("params") or {}
    if not isinstance(params, dict):
        raise HTTPException(400, "params muss ein Objekt sein.")
    try:
        job = jobs.submit(pid, action, params)
    except ProjectNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"job": job.to_dict()}


@app.get("/api/jobs")
def list_jobs(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
    if jobs is None:
        raise HTTPException(503, "Job-Manager nicht verfügbar.")
    return {"jobs": jobs.list(limit=limit)}


@app.get("/api/jobs/{jid}")
def get_job(jid: str) -> dict[str, Any]:
    return {"job": _job(jid).to_dict()}


@app.get("/api/jobs/{jid}/report", response_class=PlainTextResponse)
def job_report(jid: str) -> str:
    job = _job(jid)
    if job.report:
        return job.report
    out = [f"Job {job.id} · {job.label} · Status: {job.status}",
           f"Projekt: {job.project_name}",
           f"Exit-Code: {job.exit_code}"]
    if job.stdout:
        out += ["", "--- stdout ---", job.stdout.rstrip()]
    if job.stderr:
        out += ["", "--- stderr ---", job.stderr.rstrip()]
    return "\n".join(out)


@app.get("/api/jobs/{jid}/artifact")
def job_artifact(jid: str, inline: bool = Query(default=False)) -> FileResponse:
    if jobs is None:
        raise HTTPException(503, "Job-Manager nicht verfügbar.")
    try:
        path = jobs.artifact_path(jid)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc

    action = ACTION_BY_KEY.get(_job(jid).action)
    mime = action.mime if action else "application/octet-stream"
    disposition = "inline" if inline else "attachment"
    response = FileResponse(path, media_type=mime, filename=path.name)
    response.headers["Content-Disposition"] = f'{disposition}; filename="{path.name}"'
    if mime == "image/svg+xml":
        # SVG kann Scripte tragen – nur als Bild rendern, niemals ausführen.
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; style-src 'unsafe-inline'; sandbox")
        response.headers["X-Content-Type-Options"] = "nosniff"
    return response


# ── SPA ────────────────────────────────────────────────────────────────────
if (STATIC_DIR / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="spa")
else:
    @app.get("/")
    def spa_missing() -> JSONResponse:
        return JSONResponse(
            {"error": "Frontend wurde nicht gebaut (static/index.html fehlt).",
             "hint": "Im Container: cd /opt/creabim/src/frontend && npm ci && npm run build"},
            status_code=503)