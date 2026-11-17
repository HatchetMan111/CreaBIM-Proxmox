#!/usr/bin/env python3
"""Stub für die creabim-cli – ersetzt das echte Binary in den Tests.

Der Stub verhält sich wie die CLI-Auswahl, die der Server benutzt: gleiche
Argumentformen, gleiche stdout-Formate, gleiche Fehlerzeilen. Über zwei
Umgebungsvariablen lassen sich Fehlerpfade testen:

  STUB_FAIL=1          jeder Aufruf endet mit Exit 1 und einer stderr-Meldung
  STUB_NO_ARTIFACT=1   Erfolg (Exit 0), aber ohne Ausgabedatei

Das echte Binary wird in ``test_real_cli.py`` gegen die Testumgebung geprüft.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

USAGE = """usage: (<model> is a .creabim project or a legacy .creabim.json file)
  creabim sample <out.creabim|out.creabim.json>
                                       write the starter house, with its sheets
  creabim stats <model>                count elements by IFC class
"""

MODEL = {
    "version": "1.1.2",
    "levels": [{"id": "Foundation"}, {"id": "Ground Floor"}, {"id": "First Floor"}],
    "views": [
        {"id": "Ground Floor plan", "kind": "plan", "scale": 50.0, "level": "Ground Floor"},
        {"id": "Section A-A", "kind": "section", "scale": 50.0},
    ],
    "sheets": [{"id": "A101", "name": "Ground Floor Plan", "size": "A2"}],
    "walls": [],
    "materials": [],
}

STATS = [
    ("IfcWall", 24),
    ("IfcDoor", 16),
    ("IfcWindow", 20),
    ("IfcSlab", 5),
]

VIEWS = [
    ("plan", "1:50", "Ground Floor plan"),
    ("section", "1:50", "Section A-A"),
]

SHEETS = [("A101", "A2", "Ground Floor Plan")]


def fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def write_model(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(MODEL, indent=2), encoding="utf-8")


def write_svg(path: Path, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm" '
        f'viewBox="0 0 100 100"><title>{title}</title>'
        '<rect width="100%" height="100%" fill="white"/></svg>\n',
        encoding="utf-8",
    )


def main(argv: list[str]) -> int:
    if os.environ.get("STUB_FAIL") == "1":
        # Die echte CLI druckt bei Fehlern die komplette Usage – das muss der
        # Server korrekt abschneiden.
        print("no view named \"Gibt es nicht\"", file=sys.stderr)
        print(USAGE, file=sys.stderr)
        return 1

    if not argv or argv[0] in ("--help", "-h"):
        print(USAGE, file=sys.stderr)
        return 1 if not argv else 0

    cmd, args = argv[0], argv[1:]

    if cmd.startswith("sample"):
        if not args:
            return fail("no output file given")
        write_model(Path(args[0]))
        return 0

    if cmd == "stats":
        if not args:
            return fail("no model given")
        for name, count in STATS:
            print(f"{name:<30} {count}")
        return 0

    if cmd == "views":
        for kind, scale, name in VIEWS:
            print(f"{kind:<10} {scale:<8} {name}")
        return 0

    if cmd == "sheets":
        for number, size, name in SHEETS:
            print(f"{number:<8} {size:<6} {name}")
        return 0

    if cmd == "export-json":
        if len(args) < 2:
            return fail("usage: export-json <model> <out.json>")
        write_model(Path(args[1]))
        return 0

    if cmd in ("plan", "view", "sheet"):
        if len(args) < 3:
            return fail(f"usage: {cmd} <model> <name> <out.svg>")
        if cmd == "view" and args[1] not in [v[2] for v in VIEWS]:
            print(f"no view named \"{args[1]}\"", file=sys.stderr)
            print(USAGE, file=sys.stderr)
            return 1
        if cmd == "sheet" and args[1] not in [s[0] for s in SHEETS]:
            return fail(f"no sheet numbered \"{args[1]}\"")
        if cmd == "plan" and args[1] not in [l["id"] for l in MODEL["levels"]]:
            return fail(f"no level named \"{args[1]}\"")
        write_svg(Path(args[2]), args[1])
        return 0

    if cmd in ("pdf", "xlsx", "ifc", "ifcx", "glb", "fcstd"):
        if len(args) < 2:
            return fail(f"usage: {cmd} <model> <out>")
        if os.environ.get("STUB_NO_ARTIFACT") != "1":
            Path(args[1]).write_bytes(b"%PDF-1.4 stub\n")
        return 0

    if cmd == "schedule":
        if len(args) < 3:
            return fail("usage: schedule <model> <kind> [out.csv]")
        if args[1] not in ("doors", "windows", "walls", "slabs", "rooms"):
            return fail(f"unknown schedule '{args[1]}'")
        Path(args[2]).write_text("Mark,Type\nD01,Door\n", encoding="utf-8")
        return 0

    if cmd == "check":
        if os.environ.get("STUB_CHECK_FINDINGS") == "1":
            print("2 objects standing in a door swing")
            return 1
        print("no objects in doorways or door swings, no layer gaps or overlaps at joins")
        return 0

    if cmd == "label-clashes":
        print("Ground Floor plan: 0 overlapping")
        return 0

    if cmd == "import-ifc":
        if len(args) < 2:
            return fail("usage: import-ifc <in.ifc> <out>")
        write_model(Path(args[1]))
        return 0

    if cmd == "build":
        if len(args) < 2:
            return fail("usage: build <spec.json> <out>")
        write_model(Path(args[1]))
        return 0

    if cmd == "rooms-from-notes":
        if len(args) < 2:
            return fail("usage: rooms-from-notes <model> <out>")
        shutil.copyfile(args[0], args[1])
        return 0

    return fail(f"unknown command '{cmd}'\n{USAGE}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))