#!/usr/bin/env python3
"""Konverter: Sweet Home 3D (.sh3d) → CreaBIM-Modell-JSON.

Ein .sh3d-File ist ein ZIP mit ``Home.xml`` darin. Der Konverter liest dieses
XML und bildet es auf das CreaBIM-JSON-Format (docs/json-format.md im
CreaBIM-Repo) ab:

  levels           → levels   (Höhen in Metern)
  wall             → walls    (Mittellinie; Kurven werden übersprungen)
  doorOrWindow     → openings (nur wenn ein tragende Wand gefunden wird)
  room             → slabs    (Bodenflächen; SH3D-Räume sind hier Flächen-Polygone)
  pieceOfFurniture → objects  (per Katalog-Schlüssel, s. CATALOGUE_MAP)
  light            → objects  (ceiling-light)
  dimensionLine    → übersprungen (Bemaßung ist nicht im JSON-Format)

Koordinaten: SH3D arbeitet in cm und hat y nach unten (Plan-Blick), CreaBIM in
Metern mit y nach Norden → x/100, y/100 und y gespiegelt. Die Drehrichtung der
Möbel ist zwischen beiden Programmen nicht eindeutig dokumentiert; steht in
ROTATION_OFFSET_DEG / ANGLE_SIGN und lässt sich dort umstellen.

Standalone:
    python3 sh3d.py eingabe.sh3d [ausgabe.json]     # druckt den Umwandlungs-Report
Im Server (library.import_model) wird die Spec an ``creabim-cli build`` gegeben.
"""

from __future__ import annotations

import io
import json
import math
import sys
import unicodedata
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

# ── Einstellungen ──────────────────────────────────────────────────────────
#: SH3D-Winkel (Bogenmaß) → CreaBIM-Drehung (Grad): (ANGLE_SIGN·deg + OFFSET) % 360
ANGLE_SIGN = -1
ROTATION_OFFSET_DEG = 180.0
#: Toleranz (cm), in der eine Tür als Öffnung in die nächstgelegene Wand kommt
WALL_SNAP_CM = 12.0
#: Standard-Brüstungshöhe für Fenster ohne Höhenangabe
WINDOW_SILL_M = 0.9

# SH3D-catalogId (oder Namens-Keywords) → CreaBIM-Katalog-Schlüssel
# (``creabim-cli catalogue`` listet sie; ``starter/`` darf entfallen)
CATALOGUE_MAP: dict[str, str] = {
    "eteks#sofa2": "sofa-3",
    "eteks#sofa": "sofa-3",
    "eteks#chair": "chair",
    "eteks#coffeetable": "coffee-table",
    "eteks#roundtable": "dining-table",
    "eteks#diningtable": "dining-table",
    "eteks#bed": "double-bed",
    "eteks#bedsimple": "single-bed",
    "eteks#kitchencabinet": "base-cabinet-600",
    "eteks#kitchenisland": "base-cabinet-600",
    "eteks#toiletunit": "wc",
    "eteks#shower": "shower",
    "eteks#bathtub": "bathtub",
    "eteks#washbasin": "washbasin",
    "eteks#sink": "sink-unit-1000",
    "eteks#cooktop": "cooker-600",
    "eteks#oven": "cooker-600",
    "eteks#fridge": "fridge-freezer",
    "eteks#refrigerator": "fridge-freezer",
    "eteks#wardrobe": "wardrobe",
    "eteks#desk": "desk",
    "eteks#table": "dining-table",
    "eteks#computerdesk": "desk",
    "eteks#bookshelf": "wardrobe",
    "sleipnir1#rectangulartable": "dining-table",
    "scopia#desk_table": "desk",
    "kator legaz#office-chair": "chair",
    "artist373#armchair": "armchair",
}
#: Namens-Stichwörter für Stücke ohne catalogId (kleingeschrieben, Teilstring)
KEYWORD_MAP: dict[str, str] = {
    "sofa": "sofa-3", "couch": "sofa-3", "sessel": "armchair",
    "stuhl": "chair", "chair": "chair", "tisch": "dining-table", "table": "dining-table",
    "bett": "double-bed", "bed": "double-bed", "schrank": "wardrobe",
    "wc": "wc", "toilette": "wc", "toilet": "wc",
    "dusche": "shower", "shower": "shower", "badewanne": "bathtub",
    "waschbecken": "washbasin", "washbasin": "washbasin", "spüle": "sink-unit-1000",
    "kühlschrank": "fridge-freezer", "fridge": "fridge-freezer",
    "lamp": "ceiling-light", "leuchte": "ceiling-light", "lampe": "ceiling-light",
}


class Sh3dError(RuntimeError):
    """Die .sh3d-Datei konnte nicht gelesen oder nicht zugeordnet werden."""


def slugify(value: str, fallback: str = "element") -> str:
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


def _m(cm: float | str | None, default: float = 0.0) -> float:
    """SH3D-Zentimeter → Meter."""
    if cm is None or cm == "":
        return default
    return round(float(cm) / 100.0, 4)


def _pt(x: float | str, y: float | str) -> list[float]:
    """SH3D-Punkt (cm, y nach unten) → CreaBIM-Punkt (m, y nach Norden)."""
    return [_m(x), round(-_m(y), 4)]


def _deg(radians: float | str | None) -> float:
    try:
        rad = float(radians or 0.0)
    except ValueError:
        rad = 0.0
    return round((ANGLE_SIGN * math.degrees(rad) + ROTATION_OFFSET_DEG) % 360.0, 2)


def read_home_xml(source: str | Path | bytes) -> ElementTree.Element:
    """Home.xml aus einem .sh3d-Archiv lesen (Dateipfad oder Bytes)."""
    if isinstance(source, bytes):
        archive = io.BytesIO(source)
    else:
        archive = Path(source)          # type: ignore[arg-type]
    try:
        with zipfile.ZipFile(archive) as zf:
            names = zf.namelist()
            if "Home.xml" in names:
                data = zf.read("Home.xml")
            elif "Home" in names:
                data = zf.read("Home")
            else:
                raise Sh3dError(
                    "Kein Home.xml im Archiv – ist das wirklich eine "
                    "Sweet-Home-3D-Datei? Inhalt: " + ", ".join(names[:12]))
    except zipfile.BadZipFile as exc:
        raise Sh3dError(f"Datei ist kein ZIP-Archiv: {exc}") from exc

    text = data.decode("utf-8", errors="replace")
    head = text[:512].lstrip()
    if head.startswith("<?xml") and "<!DOCTYPE" in head[:256]:
        raise Sh3dError("Home.xml enthält eine DOCTYPE-Deklaration – nicht importierbar.")
    try:
        return ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        raise Sh3dError(f"Home.xml ist kein gültiges XML: {exc}") from exc


def _catalogue_key(piece: ElementTree.Element) -> str | None:
    cat = (piece.get("catalogId") or "").strip().lower()
    if cat:
        if cat in CATALOGUE_MAP:
            return CATALOGUE_MAP[cat]
        base = cat.split("#")[-1]
        for known, key in CATALOGUE_MAP.items():
            if known.endswith(base):
                return key
    name = (piece.get("name") or "").strip().lower()
    for needle, key in KEYWORD_MAP.items():
        if needle in name:
            return key
    return None


def _unique_id(base: str, used: set[str]) -> str:
    slug = slugify(base)
    candidate = slug
    n = 2
    while candidate in used:
        candidate = f"{slug}-{n}"
        n += 1
    used.add(candidate)
    return candidate


def convert_sh3d(source: str | Path | bytes, name: str | None = None) -> dict[str, Any]:
    """Konvertiert eine .sh3d-Datei → (spec, report). Wirft Sh3dError bei Problemen.

    ``name`` fließt nur in den Report (Projektname) ein, nicht in die Spec.
    """
    root = read_home_xml(source)
    used: set[str] = set()
    report: dict[str, Any] = {"levels": 0, "walls": 0, "openings": 0, "slabs": 0,
                              "objects": 0, "skipped_walls_curved": 0,
                              "skipped_openings": [], "skipped_furniture": []}

    # ── Levels ─────────────────────────────────────────────────────────────
    levels_out: list[dict[str, Any]] = []
    level_ids: dict[str, str] = {}
    for lv in root.findall("level"):
        lid = lv.get("id") or lv.get("name") or f"level-{len(levels_out)}"
        cid = slugify(lv.get("name") or f"Niveau {len(levels_out)}")
        cid = _unique_id(cid, used)
        levels_out.append({
            "id": cid,
            "elevation": _m(lv.get("elevation")),
            "height": _m(lv.get("height"), 2.5) or 2.5,
        })
        level_ids[lid] = cid
    report["levels"] = len(levels_out)

    # ── Wände ──────────────────────────────────────────────────────────────
    walls_out: list[dict[str, Any]] = []
    wall_index: list[tuple[float, float, float, float, float, float, str]] = []
    for w in root.findall("wall"):
        curve = float(w.get("curve") or 0.0)
        if abs(curve) > 1e-6:
            report["skipped_walls_curved"] += 1
            continue
        cid = _unique_id(w.get("name") or f"Wand-{len(walls_out) + 1}", used)
        thickness = _m(w.get("thickness"), 0.2) or 0.2
        height = _m(w.get("height"), 0.0) or None
        wall = {
            "id": cid,
            "level": level_ids.get(w.get("level") or "", levels_out[0]["id"] if levels_out else None),
            "start": _pt(w.get("x1"), w.get("y1")),
            "end": _pt(w.get("x2"), w.get("y2")),
            "thickness": thickness,
        }
        if wall["level"] is None:
            report["skipped_walls_curved"] += 1        # kein Level → weglassen
            continue
        if height:
            wall["height"] = height
        walls_out.append(wall)
        x1, y1 = wall["start"]
        x2, y2 = wall["end"]
        wall_index.append((x1, y1, x2, y2, thickness * 100, _m(w.get("height")), cid))

    def _nearest_wall(x_m: float, y_m: float) -> tuple[float, str, float] | None:
        """Nächste Wand: (Abstand in cm, Wand-id, Projektion ab Wandstart in m)."""
        best: tuple[float, str, float] | None = None
        for x1, y1, x2, y2, thick, _h, cid in wall_index:
            dx, dy = x2 - x1, y2 - y1
            length2 = dx * dx + dy * dy
            if length2 == 0:
                continue
            t = max(0.0, min(1.0, ((x_m - x1) * dx + (y_m - y1) * dy) / length2))
            px, py = x1 + t * dx, y1 + t * dy
            dist = math.hypot(x_m - px, y_m - py) * 100
            if dist <= thick + WALL_SNAP_CM:
                centre = math.hypot(px - x1, py - y1)
                if best is None or dist < best[0]:
                    best = (dist, cid, round(centre, 4))
        return best

    # ── Türen / Fenster → Öffnungen (nur mit tragender Wand) ───────────────
    openings_out: list[dict[str, Any]] = []
    for d in root.findall("doorOrWindow"):
        x, y = _m(d.get("x")), _m(d.get("y"))
        if not wall_index:
            report["skipped_openings"].append(
                f"{d.get('name') or 'Tür/Fenster'} ({d.get('catalogId') or 'ohne Katalog'})")
            continue
        near = _nearest_wall(x, y)
        if near is None:
            report["skipped_openings"].append(
                f"{d.get('name') or 'Tür/Fenster'} – keine Wand in Snapping-Nähe")
            continue
        _dist, wall_cid, centre = near
        width = _m(d.get("width"), 0.9) or 0.9
        height = _m(d.get("height"), 2.0) or 2.0
        kind = "window" if "window" in (d.get("catalogId") or "").lower() \
            or (d.get("name") or "").lower().startswith("fenster") else "door"
        opening: dict[str, Any] = {
            "id": _unique_id(d.get("name") or kind, used),
            "kind": kind,
            "wall": wall_cid,
            "centre": centre,
            "width": width,
            "height": height,
        }
        if kind == "window":
            opening["sill"] = WINDOW_SILL_M
        openings_out.append(opening)
    report["openings"] = len(openings_out)

    # ── Räume → Bodenflächen (Slabs) ───────────────────────────────────────
    slabs_out: list[dict[str, Any]] = []
    floor_by_level: dict[str, float] = {
        lv.get("id") or "": _m(lv.get("floorThickness"), 0.12) or 0.12
        for lv in root.findall("level")
    }
    for i, r in enumerate(root.findall("room"), start=1):
        pts = [_pt(p.get("x"), p.get("y")) for p in r.findall("point")]
        if len(pts) < 3:
            report["skipped_furniture"].append(f"Fläche {i} – weniger als 3 Punkte")
            continue
        level_key = r.get("level") or ""
        thickness = floor_by_level.get(level_key, 0.12)
        label = r.get("name") or f"Fläche {i:02d}"
        cid = _unique_id(label, used)
        slab = {
            "id": cid,
            "name": label,
            "level": level_ids.get(level_key, levels_out[0]["id"] if levels_out else None),
            "outline": pts,
            "thickness": thickness,
        }
        if slab["level"] is None:
            report["skipped_furniture"].append(f"{label} – kein Level")
            continue
        slabs_out.append(slab)
    report["slabs"] = len(slabs_out)

    # ── Möbel + Lichter → Objekte ─────────────────────────────────────────
    objects_out: list[dict[str, Any]] = []
    pieces = list(root.findall("pieceOfFurniture")) + list(root.findall("light"))
    for p in pieces:
        key = _catalogue_key(p)
        if key is None:
            report["skipped_furniture"].append(
                f"{p.get('name') or 'Objekt'} ({p.get('catalogId') or 'ohne Katalog'})")
            continue
        cid = _unique_id(p.get("name") or key, used)
        obj: dict[str, Any] = {
            "id": cid,
            "name": p.get("name") or key,
            "level": level_ids.get(p.get("level") or "",
                                   levels_out[0]["id"] if levels_out else None),
            "catalogue": key,
            "at": _pt(p.get("x"), p.get("y")),
            "anchor": "centre",
        }
        if obj["level"] is None:
            report["skipped_furniture"].append(f"{obj['name']} – kein Level")
            continue
        rotation = _deg(p.get("angle"))
        if rotation:
            obj["rotation"] = rotation
        elevation = _m(p.get("elevation"))
        if elevation:
            obj["offset"] = elevation
        objects_out.append(obj)
    report["objects"] = len(objects_out)

    # ── Ansichten ─────────────────────────────────────────────────────────
    views_out: list[dict[str, Any]] = []
    for i, lv in enumerate(levels_out, start=1):
        views_out.append({
            "id": _unique_id(f"Plan {lv['id']}", used),
            "name": f"Grundriss {lv['id']}",
            "kind": "plan",
            "level": lv["id"],
            "scale": 100,
        })
    views_out.append({"id": _unique_id("3D", used), "name": "3D-Ansicht",
                      "kind": "3d", "azimuth": 35, "altitude": 30})

    spec: dict[str, Any] = {"version": 1}
    if levels_out:
        spec["levels"] = levels_out
    if walls_out:
        spec["walls"] = walls_out
    if openings_out:
        spec["openings"] = openings_out
    if slabs_out:
        spec["slabs"] = slabs_out
    if objects_out:
        spec["objects"] = objects_out
    if views_out:
        spec["views"] = views_out

    # Deriveable-Wand-Hinweis: keine Wände im Quellmodell?
    if not walls_out and slabs_out:
        report["note"] = ("Das SH3D-Modell enthält keine Wände – die Flächen wurden als "
                          "Bodenplatten übernommen, Türen/Fenster konnten ohne tragende "
                          "Wand nicht platziert werden.")
    return {"spec": spec, "report": report}


def report_lines(report: dict[str, Any]) -> list[str]:
    """Der Umwandlungs-Report als lesbare Zeilenliste für die UI."""
    lines = [f"Levels: {report['levels']} · Wände: {report['walls']} · "
             f"Öffnungen: {report['openings']} · Flächen: {report['slabs']} · "
             f"Objekte: {report['objects']}"]
    if report.get("note"):
        lines.append(report["note"])
    if report.get("skipped_walls_curved"):
        lines.append(f"{report['skipped_walls_curved']} gekrümmte Wände übergangen")
    for key, label in (("skipped_openings", "Türen/Fenster"),
                       ("skipped_furniture", "Möbel/Objekte")):
        items = report.get(key) or []
        if items:
            preview = "; ".join(items[:10])
            mehr = f" … und {len(items) - 10} weitere" if len(items) > 10 else ""
            lines.append(f"{len(items)} {label} übergangen: {preview}{mehr}")
    return lines


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip(), file=sys.stderr)
        return 1
    source = Path(argv[0])
    out = Path(argv[1]) if len(argv) > 1 else source.with_suffix(".creabim.json")
    try:
        result = convert_sh3d(source, name=source.stem)
    except Sh3dError as exc:
        print(f"✘ {exc}", file=sys.stderr)
        return 1
    out.write_text(json.dumps(result["spec"], indent=2, ensure_ascii=False), encoding="utf-8")

    rep = result["report"]
    print(f"✔ {out} geschrieben")
    print(f"  Levels: {rep['levels']} · Wände: {rep['walls']} · Öffnungen: {rep['openings']}"
          f" · Flächen: {rep['slabs']} · Objekte: {rep['objects']}")
    if rep.get("note"):
        print(f"  Hinweis: {rep['note']}")
    if rep["skipped_openings"]:
        print(f"  Übergangen ({len(rep['skipped_openings'])}) Türen/Fenster:")
        for line in rep["skipped_openings"][:8]:
            print(f"    - {line}")
        if len(rep["skipped_openings"]) > 8:
            print(f"    … und {len(rep['skipped_openings']) - 8} weitere")
    if rep["skipped_furniture"]:
        print(f"  Übergangen ({len(rep['skipped_furniture'])}) Objekte:")
        for line in rep["skipped_furniture"][:8]:
            print(f"    - {line}")
        if len(rep["skipped_furniture"]) > 8:
            print(f"    … und {len(rep['skipped_furniture']) - 8} weitere")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))