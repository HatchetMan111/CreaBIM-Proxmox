#!/usr/bin/env python3
"""Projekt-Bibliothek: Projekte anlegen, importieren, umbenennen, löschen.

Jedes Projekt ist ein Ordner unter ``<data>/library/<id>/`` mit

* ``model.creabim`` bzw. ``model.creabim.json`` – das eigentliche Modell,
* ``meta.json`` – Name, Zeitstempel und (gecachte) Modell-Struktur.

Die Struktur (Geschosse, Ansichten, Pläne, Statistik) wird einmal pro
Modell-Version aus der CLI gelesen und in ``meta.json`` zwischengespeichert.
Ein Import oder eine Namensänderung invalidiert den Cache.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sh3d
from creabim_cli import (
    ACTION_BY_KEY, CliError, CliRunner, Result, error_message,
    parse_stats, slugify,
)

PID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
MODEL_KINDS = {".creabim": "creabim", ".creabim.json": "creabim-json"}


class ProjectNotFound(LookupError):
    """Projekt-ID existiert nicht (oder der Pfad zeigt aus der Bibliothek."""


class ProjectExists(ValueError):
    """Beim Anlegen ist die ID schon vergeben."""


# Bezeichnungen der mitgelieferten Beispielmodelle
SAMPLES: dict[str, dict[str, str]] = {
    "starter": {"key": "sample", "name": "Maple Lane House",
                "description": "Das vollständige Beispielhaus (13 Pläne, 640 Elemente)"},
    "simple": {"key": "sample-simple", "name": "Simple House",
               "description": "Das kleine Haus aus den Tests"},
    "layered": {"key": "sample-layered", "name": "Layered House",
                "description": "Beispielhaus aus geschichteten Bauteilen"},
    "typed": {"key": "sample-typed", "name": "Typed House",
              "description": "Haus mit Elementtypen, Vorhangfassade und Schacht"},
    "furnished": {"key": "sample-furnished", "name": "Furnished House",
                  "description": "Das Beispielhaus mit Katalog-Möblierung"},
    "garden": {"key": "sample-garden", "name": "House in a Garden",
               "description": "Beispielhaus mit Garten, Cheminée und Carport"},
}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class Library:
    """Verwaltet alle Projekte unterhalb eines Datenverzeichnisses."""

    def __init__(self, root: str | os.PathLike[str], runner: CliRunner):
        self.root = Path(root)
        self.library_dir = self.root / "library"
        self.jobs_dir = self.root / "jobs"
        self.runner = runner
        self.library_dir.mkdir(parents=True, exist_ok=True)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

    # ── interne Helfer ─────────────────────────────────────────────────────
    def _dir(self, pid: str) -> Path:
        if not PID_RE.match(pid or ""):
            raise ProjectNotFound(f"Ungültige Projekt-ID: {pid!r}")
        path = (self.library_dir / pid).resolve()
        # Der aufgelöste Pfad MUSS innerhalb der Bibliothek liegen.
        if path.parent != self.library_dir.resolve():
            raise ProjectNotFound(f"Projekt-ID zeigt aus der Bibliothek: {pid!r}")
        return path

    def _meta_path(self, pid: str) -> Path:
        return self._dir(pid) / "meta.json"

    def _read_meta(self, pid: str) -> dict[str, Any]:
        path = self._meta_path(pid)
        if not path.exists():
            raise ProjectNotFound(f"Projekt {pid} hat keine meta.json")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CliError(f"meta.json von {pid} ist kaputt: {exc}") from exc

    def _write_meta(self, meta: dict[str, Any]) -> None:
        _atomic_write(self.library_dir / meta["id"] / "meta.json",
                      json.dumps(meta, indent=2, ensure_ascii=False))

    def model_path(self, meta: dict[str, Any]) -> Path:
        path = (self.library_dir / meta["id"] / meta["model"]).resolve()
        if path.parent != self._dir(meta["id"]):
            raise CliError(f"Modellpfad zeigt aus dem Projektordner: {meta['model']}")
        return path

    def _new_pid(self, name: str) -> str:
        base = slugify(name, "projekt")[:40] or "projekt"
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        pid = f"{base}-{stamp}"
        n = 2
        while (self.library_dir / pid).exists():
            pid = f"{base}-{stamp}-{n}"
            n += 1
        return pid

    # ── öffentliche API ────────────────────────────────────────────────────
    def list_projects(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for entry in sorted(self.library_dir.iterdir(), key=lambda p: p.name):
            if not entry.is_dir():
                continue
            try:
                meta = self._read_meta(entry.name)
            except (ProjectNotFound, CliError):
                continue
            out.append({
                "id": meta["id"],
                "name": meta.get("name", entry.name),
                "model": meta.get("model", ""),
                "kind": meta.get("kind", ""),
                "created": meta.get("created"),
                "modified": meta.get("modified"),
                "size": meta.get("size", 0),
                "levels": (meta.get("structure") or {}).get("levels", []),
                "views": len((meta.get("structure") or {}).get("views", [])),
                "sheets": len((meta.get("structure") or {}).get("sheets", [])),
            })
        out.sort(key=lambda p: p.get("modified") or "", reverse=True)
        return out

    def get(self, pid: str) -> dict[str, Any]:
        meta = self._read_meta(pid)
        if not self.model_path(meta).exists():
            raise ProjectNotFound(f"Modelldatei von {pid} fehlt")
        return meta

    def create_sample(self, sample: str, name: str | None = None) -> dict[str, Any]:
        if sample not in SAMPLES:
            raise ValueError(
                "Unbekanntes Beispiel. Verfügbar: " + ", ".join(sorted(SAMPLES)))
        info = SAMPLES[sample]
        pid = self._new_pid(name or info["name"])
        target = self.library_dir / pid
        target.mkdir(parents=True)
        model = target / "model.creabim.json"
        res = self.runner.run([info["key"], str(model)])
        if not res.ok or not model.exists():
            shutil.rmtree(target, ignore_errors=True)
            raise CliError(error_message(res, f"Beispiel '{sample}' konnte nicht "
                                              f"erzeugt werden"), exit_code=res.returncode,
                           stdout=res.stdout, stderr=res.stderr, argv=res.argv)
        meta = {
            "id": pid,
            "name": name or info["name"],
            "model": model.name,
            "kind": "creabim-json",
            "created": now_iso(),
            "modified": now_iso(),
            "size": model.stat().st_size,
            "structure": None,
        }
        self._write_meta(meta)
        self._warm_structure(pid)
        return self.get(pid)

    def import_model(self, filename: str, data: bytes,
                     name: str | None = None) -> dict[str, Any]:
        """Eine hochgeladene Datei importieren.

        Erlaubt: .creabim, .creabim.json, .ifc, .ifcx, .json (Build-Spec) und
        .sh3d (Sweet Home 3D – wird vor dem Build umgewandelt).
        """
        safe = Path(filename or "modell").name
        lower = safe.lower()
        if lower.endswith(".ifc") or lower.endswith(".ifcx"):
            kind, suffix = "ifc", ".creabim.json"
        elif lower.endswith(".creabim.json"):
            kind, suffix = "creabim-json", ".creabim.json"
        elif lower.endswith(".creabim"):
            kind, suffix = "creabim", ".creabim"
        elif lower.endswith(".sh3d"):
            kind, suffix = "sh3d", ".creabim.json"
        elif lower.endswith(".json"):
            # Eine JSON-Spezifikation wird über `creabim build` zum Modell.
            kind, suffix = "spec", ".creabim.json"
        else:
            raise ValueError(
                "Dateityp nicht unterstützt. Erlaubt: .creabim, .creabim.json, "
                ".ifc, .ifcx, .json, .sh3d")

        pid = self._new_pid(name or Path(safe).stem)
        target = self.library_dir / pid
        target.mkdir(parents=True)
        import_report: list[str] = []
        try:
            source = target / ("import" + Path(safe).suffix)
            source.write_bytes(data)
            model = target / ("model" + suffix)
            spec_path = target / "import-spec.json"

            if kind == "ifc":
                res = self.runner.run(["import-ifc", str(source), str(model)])
            elif kind == "sh3d":
                # Sweet Home 3D: erst in eine CreaBIM-Spec umwandeln, dann bauen.
                try:
                    converted = sh3d.convert_sh3d(data, name=name)
                except sh3d.Sh3dError as exc:
                    raise CliError(f"SH3D-Import fehlgeschlagen: {exc}") from exc
                spec_path.write_text(
                    json.dumps(converted["spec"], indent=2, ensure_ascii=False),
                    encoding="utf-8")
                res = self.runner.run(["build", str(spec_path), str(model)])
                import_report = sh3d.report_lines(converted["report"])
            elif kind == "spec":
                res = self.runner.run(["build", str(source), str(model)])
            else:
                # .creabim / .creabim.json sind schon das native Format.
                shutil.move(str(source), str(model))
                res = Result(0, "", "", [])
            source.unlink(missing_ok=True)

            if not res.ok or not model.exists():
                raise CliError(
                    error_message(res, "Import fehlgeschlagen"),
                    exit_code=res.returncode, stdout=res.stdout,
                    stderr=res.stderr, argv=res.argv)
        except Exception:
            shutil.rmtree(target, ignore_errors=True)
            raise

        meta = {
            "id": pid,
            "name": name or Path(safe).stem,
            "model": model.name,
            "kind": kind,
            "created": now_iso(),
            "modified": now_iso(),
            "size": model.stat().st_size,
            "structure": None,
        }
        if import_report:
            meta["import_report"] = import_report
        self._write_meta(meta)
        self._warm_structure(pid)
        return self.get(pid)

    def _warm_structure(self, pid: str) -> None:
        """Struktur einmal vorab lesen – so zeigt die Liste sofort Zahlen.

        Ein Fehler hier darf das Anlegen nicht kippen: ausländische IFC-Dateien
        oder Reparaturmodelle können export-json verweigern; dann bleibt der
        Cache leer und wird beim ersten Öffnen nachgeholt.
        """
        try:
            self.structure(pid)
        except Exception:                              # noqa: BLE001 – Best effort
            pass

    def rename(self, pid: str, name: str) -> dict[str, Any]:
        meta = self._read_meta(pid)
        meta["name"] = name.strip()[:120] or meta["name"]
        meta["modified"] = now_iso()
        self._write_meta(meta)
        return meta

    def delete(self, pid: str) -> None:
        path = self._dir(pid)
        if not path.exists():
            raise ProjectNotFound(f"Projekt {pid} existiert nicht")
        shutil.rmtree(path)

    # ── Struktur (gecacht) ─────────────────────────────────────────────────
    def structure(self, pid: str, refresh: bool = False) -> dict[str, Any]:
        meta = self._read_meta(pid)
        model = self.model_path(meta)
        sig = f"{int(model.stat().st_mtime)}:{model.stat().st_size}"
        cached = meta.get("structure")
        if cached and cached.get("model_sig") == sig and not refresh:
            return cached

        out_dir = self.library_dir / pid / ".cache"
        out_dir.mkdir(parents=True, exist_ok=True)
        tmp_json = out_dir / "structure-export.json"

        res = self.runner.run(["export-json", str(model), str(tmp_json)])
        if not res.ok or not tmp_json.exists():
            raise CliError(
                "Modell-Struktur konnte nicht gelesen werden: "
                + error_message(res, "export-json fehlgeschlagen"),
                exit_code=res.returncode, stdout=res.stdout,
                stderr=res.stderr, argv=res.argv)

        try:
            data = json.loads(tmp_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CliError(f"export-json lieferte kein gültiges JSON: {exc}") from exc

        levels = [l.get("id") for l in data.get("levels", []) if l.get("id")]
        views = [{
            "name": v.get("id", ""),
            "kind": v.get("kind", ""),
            "scale": v.get("scale"),
            "level": v.get("level"),
        } for v in data.get("views", []) if v.get("id")]
        sheets = [{
            "number": s.get("id", ""),
            "name": s.get("name", ""),
            "size": s.get("size", ""),
        } for s in data.get("sheets", []) if s.get("id")]

        stats: dict[str, int] = {}
        res = self.runner.run(["stats", str(model)])
        if res.ok:
            stats = parse_stats(res.stdout)

        structure = {
            "levels": levels,
            "views": views,
            "sheets": sheets,
            "stats": stats,
            "model_sig": sig,
            "generated": now_iso(),
        }
        meta["structure"] = structure
        self._write_meta(meta)
        tmp_json.unlink(missing_ok=True)
        return structure

    # ── Validierung von Parametern ─────────────────────────────────────────
    def validate_params(self, pid: str, action_key: str,
                        params: dict[str, Any]) -> dict[str, Any]:
        """Namen gegen die Struktur prüfen, damit die CLI keine Usage-Dumps liefert."""
        action = ACTION_BY_KEY.get(action_key)
        if action is None:
            raise ValueError(f"Unbekannte Aktion: {action_key}")
        structure = self.structure(pid)
        cleaned = dict(params or {})

        for param in action.params:
            if param.kind == "level":
                value = str(cleaned.get(param.name, param.default)).strip()
                if value not in structure["levels"]:
                    raise ValueError(
                        f"Geschoss '{value}' gibt es nicht. Vorhanden: "
                        + ", ".join(structure["levels"]))
                cleaned[param.name] = value
            elif param.kind == "view":
                value = str(cleaned.get(param.name, param.default)).strip()
                names = [v["name"] for v in structure["views"]]
                if value not in names:
                    raise ValueError(
                        f"Ansicht '{value}' gibt es nicht. Vorhanden: " + ", ".join(names))
                cleaned[param.name] = value
            elif param.kind == "sheet":
                value = str(cleaned.get(param.name, param.default)).strip()
                numbers = [s["number"] for s in structure["sheets"]]
                if value not in numbers:
                    raise ValueError(
                        f"Plan '{value}' gibt es nicht. Vorhanden: " + ", ".join(numbers))
                cleaned[param.name] = value
            elif param.kind == "choice":
                value = str(cleaned.get(param.name, param.default)).strip()
                if param.choices and value not in param.choices:
                    raise ValueError(
                        f"{param.label}: '{value}' ist ungültig. Erlaubt: "
                        + ", ".join(param.choices))
                cleaned[param.name] = value
        return cleaned