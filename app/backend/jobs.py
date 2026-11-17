#!/usr/bin/env python3
"""Job-Warteschlange: führt CLI-Aktionen in Hintergrund-Threads aus.

Ein Job ist ein einzelner CLI-Aufruf mit Status, Logs, Exit-Code und
(optional) einem Artefakt zum Herunterladen. Das Frontend pollt die
Job-Liste, statt lange HTTP-Requests offen zu halten – PDF-Exporte
brauchen auf grossen Modellen mehrere Sekunden.
"""

from __future__ import annotations

import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from creabim_cli import (
    ACTION_BY_KEY, Action, CliError, Result, build_argv,
    error_message, parse_artifact_text,
)
from library import Library

MAX_JOBS = 200          # behalten: die letzten N Jobs (Artefakte inklusive)
JOB_TTL_DAYS = 7        # ältere Job-Artefakte beim Start aufräumen


@dataclass
class Job:
    id: str
    project_id: str
    project_name: str
    action: str
    label: str
    params: dict[str, Any] = field(default_factory=dict)
    status: str = "queued"          # queued | running | done | error
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    error: str = ""
    report: str = ""                # vollständige Fehlerkette bei Fehlern
    artifact: str = ""              # Dateiname im Job-Ordner
    result: Any = None              # geparste Ausgabe (JSON-fähig)
    created: float = field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None

    @property
    def duration_ms(self) -> int | None:
        if self.started is None or self.finished is None:
            return None
        return int((self.finished - self.started) * 1000)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "project_name": self.project_name,
            "action": self.action,
            "label": self.label,
            "params": self.params,
            "status": self.status,
            "exit_code": self.exit_code,
            "error": self.error,
            "report": self.report,
            "artifact": self.artifact,
            "result": self.result,
            "created": self.created,
            "started": self.started,
            "finished": self.finished,
            "duration_ms": self.duration_ms,
        }


class JobManager:
    """Annähernd FIFO, zwei parallele CLI-Läufe."""

    def __init__(self, library: Library, workers: int = 2):
        self.library = library
        self.jobs_dir = library.jobs_dir
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=max(1, workers),
                                        thread_name_prefix="creabim-job")
        self._cleanup_old()

    # ── öffentliche API ────────────────────────────────────────────────────
    def submit(self, project_id: str, action_key: str,
               params: dict[str, Any] | None = None) -> Job:
        action: Action | None = ACTION_BY_KEY.get(action_key)
        if action is None:
            raise ValueError(f"Unbekannte Aktion: {action_key}")
        meta = self.library.get(project_id)
        params = self.library.validate_params(project_id, action_key, params or {})

        job = Job(
            id=uuid.uuid4().hex[:12],
            project_id=project_id,
            project_name=meta.get("name", project_id),
            action=action_key,
            label=action.label,
            params=params,
        )
        (self.jobs_dir / job.id).mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)
            self._trim()
        self._pool.submit(self._run, job, action)
        return job

    def get(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            ids = list(reversed(self._order))
        return [self._jobs[j].to_dict() for j in ids[:limit] if j in self._jobs]

    def artifact_path(self, job_id: str) -> Path:
        job = self.get(job_id)
        if not job.artifact:
            raise KeyError("Dieser Job hat kein Artefakt.")
        path = (self.jobs_dir / job_id / job.artifact).resolve()
        if path.parent != (self.jobs_dir / job_id).resolve():
            raise KeyError("Artefaktpfad ist ungültig.")
        if not path.exists():
            raise KeyError("Artefakt wurde aufgeräumt.")
        return path

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    # ── intern ─────────────────────────────────────────────────────────────
    def _run(self, job: Job, action: Action) -> None:
        out_dir = self.jobs_dir / job.id
        job.status = "running"
        job.started = time.time()
        try:
            model = self.library.model_path(self.library.get(job.project_id))
            argv, target = build_argv(action, model, job.params, out_dir)
            res: Result = self.library.runner.run(argv, cwd=str(out_dir))
            job.exit_code = res.returncode
            job.stdout = res.stdout[:20000]
            job.stderr = res.stderr[:20000]

            if res.ok:
                if action.output in ("text", "json", "model"):
                    job.result = parse_artifact_text(action, target, res)
                    # Nur echte Dateien als Artefakt anbieten (stats/views haben keine).
                    if target.exists():
                        job.artifact = target.name
                else:
                    if not target.exists() or target.stat().st_size == 0:
                        raise CliError(
                            f"Die CLI meldete Erfolg, hat aber keine Datei erzeugt: "
                            f"{target.name}",
                            exit_code=res.returncode, stdout=res.stdout,
                            stderr=res.stderr, argv=res.argv)
                    job.artifact = target.name
                    job.result = {"size": target.stat().st_size}
                job.status = "done"
            else:
                # `check` liefert die Liste der Funde mit Exit 1 – das ist ein
                # Ergebnis, kein Abbruch.
                if action.key == "check":
                    job.result = {"ok": False, "text": job.stdout.strip()}
                    job.status = "done"
                else:
                    job.status = "error"
                    job.error = error_message(res, f"{action.label} fehlgeschlagen")
                    job.report = CliError(
                        job.error, exit_code=res.returncode, stdout=res.stdout,
                        stderr=res.stderr, argv=res.argv).report()
        except Exception as exc:                      # noqa: BLE001 – Fehler in den Job schreiben
            job.status = "error"
            job.error = str(exc)
            if isinstance(exc, CliError):
                job.report = exc.report()
            else:
                job.report = f"{type(exc).__name__}: {exc}"
        finally:
            job.finished = time.time()

    def _trim(self) -> None:
        """Nur die letzten MAX_JOBS behalten – inklusive ihrer Artefakte."""
        while len(self._order) > MAX_JOBS:
            old = self._order.pop(0)
            self._jobs.pop(old, None)
            shutil.rmtree(self.jobs_dir / old, ignore_errors=True)

    def _cleanup_old(self) -> None:
        cutoff = time.time() - JOB_TTL_DAYS * 86400
        for entry in self.jobs_dir.iterdir():
            if entry.is_dir() and entry.stat().st_mtime < cutoff:
                shutil.rmtree(entry, ignore_errors=True)