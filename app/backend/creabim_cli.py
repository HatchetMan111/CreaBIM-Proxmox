#!/usr/bin/env python3
"""Headless-Wrapper um die ``creabim-cli`` von CreaBIM.

Hintergrund: CreaBIM selbst ist ein nativer Rust-GUI-Client (eframe/egui,
GTK, WebKitGTK). Sein Release-Tarball enthält aber zusätzlich ``creabim-cli`` –
ein statisches Binary ohne jede GUI-Abhängigkeit, das dieselbe Modell-Engine
nutzt. Dieses Modul kapselt genau diese CLI: Befehle bauen, ausführen, Ausgaben
parsen und Fehlerketten verständlich machen.

Die CLI schreibt bei Fehlern gern die komplette Usage nach stderr. Deshalb
validieren wir Namen (Level/View/Sheet) vorab gegen die Modell-Struktur und
schneiden bei echten Fehlern den Usage-Block weg.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence


# ── Aktionen (vom Frontend gerendert) ──────────────────────────────────────
@dataclass(frozen=True)
class Param:
    """Ein Parameter einer Aktion – das Frontend baut daraus das Formular."""

    name: str
    label: str
    kind: str = "text"          # text | choice | level | view | sheet
    choices: tuple[str, ...] = ()
    default: str = ""


@dataclass(frozen=True)
class Action:
    key: str
    label: str
    group: str
    description: str
    output: str                 # svg | pdf | csv | xlsx | ifc | ifcx | glb | fcstd | json | model | text
    params: tuple[Param, ...] = ()
    suffix: str = ""            # Dateiendung des Artefakts
    mime: str = "application/octet-stream"


SVG = "image/svg+xml"
JSON_MIME = "application/json"
TEXT = "text/plain"

ACTIONS: tuple[Action, ...] = (
    Action("views", "Ansichten", "Modell",
           "Listet alle gespeicherten Ansichten (Grundrisse, Schnitte, Ansichten, 3D).",
           "text"),
    Action("sheets", "Pläne (Sheets)", "Modell",
           "Listet alle Pläne mit Nummer, Format und Titel.",
           "text"),
    Action("plan", "Grundriss zeichnen", "Zeichnung",
           "Zeichnet den Grundriss eines Geschosses als Vektor-SVG (1:100).",
           "svg", (Param("level", "Geschoss", "level"),), ".svg", SVG),
    Action("view", "Ansicht zeichnen", "Zeichnung",
           "Zeichnet eine beliebige Ansicht (Grundriss, Schnitt, Ansicht, 3D).",
           "svg", (Param("name", "Ansicht", "view"),), ".svg", SVG),
    Action("sheet", "Einzelnen Plan zeichnen", "Zeichnung",
           "Zeichnet einen einzelnen Plan (Sheet) als SVG – inkl. Titelblock.",
           "svg", (Param("number", "Plan-Nummer", "sheet"),), ".svg", SVG),
    Action("pdf", "Alle Pläne als PDF", "Export",
           "Exportiert jeden Plan als Vektor-Seite in ein einziges PDF.",
           "pdf", suffix=".pdf", mime="application/pdf"),
    Action("xlsx", "Schedules als Excel", "Export",
           "Exportiert Tür-, Fenster-, Wand-, Raum- und Materiallisten nach Excel.",
           "xlsx", suffix=".xlsx",
           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    Action("schedule", "Schedule als CSV", "Export",
           "Exportiert eine einzelne Liste als CSV.",
           "csv",
           (Param("kind", "Liste", "choice", ("doors", "windows", "walls", "slabs", "rooms"),
                   "doors"),),
           ".csv", "text/csv"),
    Action("ifc", "IFC4 exportieren", "Export",
           "Exportiert das Modell als IFC4 (STEP) – für BIM-Programme.",
           "ifc", suffix=".ifc", mime="application/step"),
    Action("ifcx", "IFC5 (IFCX) exportieren", "Export",
           "Experimenteller Export als IFC5-IFCX-JSON.",
           "ifcx", suffix=".ifcx", mime=JSON_MIME),
    Action("glb", "glTF (GLB) exportieren", "Export",
           "Exportiert das Modell als binäres glTF – öffnbar in Blender.",
           "glb", suffix=".glb", mime="model/gltf-binary"),
    Action("fcstd", "FreeCAD-Dokument", "Export",
           "Exportiert ein FreeCAD-Dokument (.FCStd).",
           "fcstd", suffix=".FCStd",
           mime="application/vnd.freecad"),
    Action("stats", "Element-Statistik", "Auswertung",
           "Zählt alle Elemente nach IFC-Klasse.",
           "json"),
    Action("check", "Modell prüfen", "Auswertung",
           "Prüft Türen/Türanschläge und Wandanschlüsse auf Fehler.",
           "text"),
    Action("label-clashes", "Beschriftungs-Konflikte", "Auswertung",
           "Listet Labels, Marken und Notizen, die sich in Grundrissen überlappen.",
           "text"),
    Action("export-json", "Modell als JSON", "Auswertung",
           "Beschreibt das Modell im CreaBIM-JSON-Format.",
           "json"),
    Action("rooms-from-notes", "Räume aus Notizen", "Auswertung",
           "Wandelt Raumnamen (Name über Fläche) in echte Räume um – Ergebnis als neues Modell.",
           "model", suffix=".creabim.json", mime=JSON_MIME),
)

ACTION_BY_KEY: dict[str, Action] = {a.key: a for a in ACTIONS}


# ── Fehler ─────────────────────────────────────────────────────────────────
class CliError(RuntimeError):
    """Ein CLI-Aufruf ist fehlgeschlagen – mit vollständiger Fehlerkette."""

    def __init__(self, message: str, *, exit_code: int = 1,
                 stdout: str = "", stderr: str = "", argv: Sequence[str] = ()):
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.argv = list(argv)

    def report(self) -> str:
        """Die komplette Fehlerkette als Text (für UI und Logs)."""
        lines = [f"creabim-cli: {self.message}"]
        if self.argv:
            lines.append("Befehl: " + " ".join(self.argv))
        lines.append(f"Exit-Code: {self.exit_code}")
        if self.stdout.strip():
            lines.append("--- stdout ---")
            lines += self.stdout.rstrip().splitlines()
        if self.stderr.strip():
            lines.append("--- stderr ---")
            lines += self.stderr.rstrip().splitlines()
        return "\n".join(lines)


@dataclass
class Result:
    returncode: int
    stdout: str
    stderr: str
    argv: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def _strip_usage(text: str) -> str:
    """Entfernt den Usage-Block, den die CLI bei Fehlern mit ausgibt."""
    keep: list[str] = []
    for line in text.splitlines():
        if line.startswith("usage:"):
            break
        keep.append(line)
    cleaned = "\n".join(keep).strip()
    if cleaned:
        return cleaned
    # Wenn die Usage zuerst kommt, ist die eigentliche Meldung nicht verwertbar.
    return ""


def error_message(res: Result, fallback: str) -> str:
    """Die eigentliche Fehlermeldung aus stdout/stderr fischen."""
    for candidate in (_strip_usage(res.stderr), _strip_usage(res.stdout)):
        if candidate:
            return candidate
    return f"{fallback} (Exit-Code {res.returncode})"


# ── Ausgaben parsen ────────────────────────────────────────────────────────
def parse_views(text: str) -> list[dict[str, Any]]:
    """``plan       1:50    Ground Floor plan`` → Liste von Dicts."""
    out: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        kind, scale, name = parts
        out.append({"kind": kind, "scale": scale, "name": name.strip()})
    return out


def parse_sheets(text: str) -> list[dict[str, Any]]:
    """``A000     A3     Cover`` → Liste von Dicts."""
    out: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        number, size, name = parts
        out.append({"number": number, "size": size, "name": name.strip()})
    return out


def parse_stats(text: str) -> dict[str, int]:
    """``IfcWall                      24`` → Dict."""
    out: dict[str, int] = {}
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        parts = line.rsplit(None, 1)
        if len(parts) != 2:
            continue
        name, count = parts
        try:
            out[name.strip()] = int(count)
        except ValueError:
            continue
    return out


# ── Runner ─────────────────────────────────────────────────────────────────
class CliRunner:
    """Führt ``creabim-cli`` aus – mit Timeout und vollständiger Fehlerkette."""

    def __init__(self, binary: str | os.PathLike[str], timeout: int = 300):
        self.binary = str(binary)
        self.timeout = timeout

    def available(self) -> bool:
        return Path(self.binary).exists() and os.access(self.binary, os.X_OK)

    def version(self) -> str:
        """Die CLI kennt kein --version – wir nutzen die Usage-Zeile als Beleg."""
        res = self.run(["--help"])
        first = (res.stderr or res.stdout).strip().splitlines()
        return first[0] if first else "unbekannt"

    def run(self, args: Iterable[str], cwd: str | os.PathLike[str] | None = None) -> Result:
        argv = [self.binary, *args]
        try:
            proc = subprocess.run(
                argv, cwd=str(cwd) if cwd else None,
                capture_output=True, text=True, timeout=self.timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise CliError(f"creabim-cli nicht gefunden: {self.binary}", argv=argv) from exc
        except subprocess.TimeoutExpired as exc:
            raise CliError(
                f"Zeitüberschreitung nach {self.timeout}s – die CLI hängt.",
                exit_code=124,
                stdout=exc.stdout or "", stderr=exc.stderr or "", argv=argv,
            ) from exc
        return Result(proc.returncode, proc.stdout or "", proc.stderr or "", argv)


# ── Aktionen ausführen ─────────────────────────────────────────────────────
def slugify(value: str, fallback: str = "export") -> str:
    """Dateinamen aus Bezeichnungen bauen (ASCII, keine Pfad-Tricks)."""
    for src, dst in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"),
                     ("Ä", "Ae"), ("Ö", "Oe"), ("Ü", "Ue"), ("ß", "ss")):
        value = value.replace(src, dst)
    keep = []
    for ch in value.strip().lower():
        if ch.isalnum():
            keep.append(ch)
        elif ch in " -_.":
            keep.append("-")
    slug = "".join(keep).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or fallback


def build_argv(action: Action, model: Path, params: dict[str, Any],
               out_dir: Path) -> tuple[list[str], Path]:
    """CLI-Argumente für eine Aktion bauen; gibt (argv, Artefaktpfad) zurück."""
    if action.output == "text" or action.output == "json" or action.output == "model":
        # stdout/Datei-Aktionen ohne Artefakt im out_dir
        if action.key == "export-json":
            target = out_dir / "model.json"
            return (["export-json", str(model), str(target)], target)
        if action.key == "stats":
            return (["stats", str(model)], out_dir / "stats.json")
        if action.key == "rooms-from-notes":
            target = out_dir / "raeume.creabim.json"
            return (["rooms-from-notes", str(model), str(target)], target)
        return ([action.key, str(model)], out_dir / f"{action.key}.txt")

    suffix = action.suffix or ".out"
    name = slugify(str(params.get("name") or params.get("level")
                        or params.get("number") or params.get("kind")
                        or action.key))
    target = out_dir / f"{name}{suffix}"

    if action.key == "plan":
        return (["plan", str(model), str(params["level"]), str(target)], target)
    if action.key == "view":
        return (["view", str(model), str(params["name"]), str(target)], target)
    if action.key == "sheet":
        return (["sheet", str(model), str(params["number"]), str(target)], target)
    if action.key == "schedule":
        return (["schedule", str(model), str(params["kind"]), str(target)], target)
    return ([action.key, str(model), str(target)], target)


def parse_artifact_text(action: Action, path: Path, res: Result) -> Any:
    """stdout/Datei-Ergebnis in eine JSON-Antwort umwandeln."""
    if action.output == "model":
        # Ein neues Modell – nur Metadaten, nicht der Inhalt (mehrere MB).
        if path.exists():
            return {"filename": path.name, "size": path.stat().st_size}
        return {"filename": path.name, "size": 0}
    if action.key == "views":
        return parse_views(res.stdout)
    if action.key == "sheets":
        return parse_sheets(res.stdout)
    if action.key == "stats":
        return parse_stats(res.stdout)
    if action.key == "check":
        return {"ok": res.ok, "text": res.stdout.strip()}
    if action.key == "label-clashes":
        return {"text": res.stdout.strip()}
    if action.key == "export-json":
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"text": path.read_text(encoding="utf-8", errors="replace")[:2000]}
    if path.exists():
        return {"text": path.read_text(encoding="utf-8", errors="replace")[:5000]}
    return {"text": res.stdout.strip()[:5000]}


def find_cli(explicit: str | None = None) -> str:
    """CLI-Pfad bestimmen: Env/Config → Standardpfad → PATH."""
    if explicit and Path(explicit).exists():
        return explicit
    env = os.environ.get("CREABIM_CLI")
    if env and Path(env).exists():
        return env
    for candidate in ("/opt/creabim/bin/creabim-cli", "/usr/local/bin/creabim-cli"):
        if Path(candidate).exists():
            return candidate
    found = shutil.which("creabim-cli")
    if found:
        return found
    raise CliError(
        "creabim-cli wurde nicht gefunden. Erwartet unter /opt/creabim/bin/creabim-cli "
        "oder im PATH (Variable CREABIM_CLI setzt den Pfad)."
    )