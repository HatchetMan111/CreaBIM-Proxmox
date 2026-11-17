"""Tests für den Sweet-Home-3D-Konverter (sh3d.py) und den .sh3d-Import."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from conftest import new_project, start_job

HOME_XML = """<?xml version='1.0'?>
<home version='7400' name='Testhaus.sh3d' wallHeight='250.0'>
  <level id='level-aaa' name='Niveau 0' elevation='0.0' floorThickness='12.0'
         height='250.0' elevationIndex='0'/>
  <level id='level-bbb' name='Niveau 1' elevation='262.0' floorThickness='12.0'
         height='250.0' elevationIndex='1'/>
  <wall id='wall-1' level='level-aaa' x1='0' y1='0' x2='1000' y2='0'
        thickness='20.0' height='250.0'/>
  <wall id='wall-2' level='level-aaa' x1='1000' y1='0' x2='1000' y2='800'
        thickness='20.0' height='250.0'/>
  <wall id='wall-3' level='level-aaa' x1='1000' y1='800' x2='0' y2='800'
        thickness='20.0' height='250.0' curve='0.5'/>
  <room id='room-1' name='Wohnen' level='level-aaa'>
    <point x='0' y='0'/><point x='1000' y='0'/><point x='1000' y='800'/>
    <point x='0' y='800'/>
  </room>
  <room id='room-2' level='level-aaa'>
    <point x='100' y='100'/><point x='500' y='100'/><point x='500' y='400'/>
    <point x='100' y='400'/><point x='100' y='500'/>
  </room>
  <doorOrWindow id='door-1' level='level-aaa' catalogId='eTeks#door' name='Tür'
    x='500' y='0' angle='0' width='91.5' depth='14.5' height='208.5'
    modelSize='1' movable='false' wallThickness='0.5' wallDistance='0.1'/>
  <pieceOfFurniture id='furn-1' level='level-aaa' catalogId='eTeks#sofa2'
    name='Sofa' x='300' y='600' angle='1.5707963' width='259' depth='106'
    height='88' modelSize='1' elevation='0'/>
  <pieceOfFurniture id='furn-2' level='level-aaa' catalogId='eteks#curved' 
    name='Wundergerät' x='700' y='300' angle='0' width='50' depth='50'
    height='50' modelSize='1'/>
  <pieceOfFurniture id='furn-3' level='level-bbb' catalogId='eTeks#bed'
    name='Bett' x='200' y='200' angle='0' width='144' depth='193'
    height='52' modelSize='1'/>
  <dimensionLine id='dim-1' level='level-aaa' xStart='0' yStart='-50'
    xEnd='1000' yEnd='-50' offset='10'/>
</home>
"""


@pytest.fixture()
def sh3d_file(tmp_path) -> Path:
    path = tmp_path / "testhaus.sh3d"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("Home.xml", HOME_XML)
    return path


@pytest.fixture()
def sh3d_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Home.xml", HOME_XML)
    return buf.getvalue()


def spec_of(source) -> dict:
    import sh3d

    return sh3d.convert_sh3d(source)["spec"]


def report_of(source) -> dict:
    import sh3d

    return sh3d.convert_sh3d(source)["report"]


# ── Konverter ──────────────────────────────────────────────────────────────
def test_levels_are_converted(sh3d_file):
    levels = spec_of(sh3d_file)["levels"]
    assert [l["id"] for l in levels] == ["niveau-0", "niveau-1"]
    assert levels[0]["elevation"] == 0
    assert levels[0]["height"] == 2.5
    assert levels[1]["elevation"] == 2.62


def test_walls_straight_only_and_y_flip(sh3d_file):
    walls = spec_of(sh3d_file)["walls"]
    assert len(walls) == 2                 # die Kurve wird übersprungen
    south = next(w for w in walls if w["id"].startswith("wand-1"))
    assert south["start"] == [0.0, 0.0]
    assert south["end"] == [10.0, 0.0]     # 1000 cm → 10 m
    assert south["thickness"] == 0.2


def test_rooms_become_slabs(sh3d_file):
    spec = spec_of(sh3d_file)
    slabs = spec["slabs"]
    assert [s["name"] for s in slabs] == ["Wohnen", "Fläche 02"]
    wohnen = slabs[0]
    assert wohnen["thickness"] == 0.12     # floorThickness aus dem Level
    assert [0.0, 0.0] in wohnen["outline"]
    assert [0.0, -8.0] in wohnen["outline"]      # y gespiegelt (800 cm → -8 m)
    assert len(spec_of(sh3d_file)["slabs"][1]["outline"]) == 5


def test_doors_snap_to_walls(sh3d_file):
    openings = spec_of(sh3d_file)["openings"]
    assert len(openings) == 1
    door = openings[0]
    assert door["kind"] == "door"
    assert door["wall"].startswith("wand-")
    assert door["width"] == pytest.approx(0.915)
    assert door["height"] == pytest.approx(2.085)


def test_furniture_maps_by_catalog_id(sh3d_file):
    objects = spec_of(sh3d_file)["objects"]
    sofa = next(o for o in objects if o["name"] == "Sofa")
    assert sofa["catalogue"] == "sofa-3"
    assert sofa["anchor"] == "centre"
    assert sofa["at"] == [3.0, -6.0]
    # 1.5708 rad → (−90 + 180) % 360 = 90
    assert sofa["rotation"] == 90.0
    bett = next(o for o in objects if o["name"] == "Bett")
    assert bett["catalogue"] == "double-bed"
    assert bett["level"] == "niveau-1"


def test_unknown_furniture_is_reported(sh3d_file):
    report = report_of(sh3d_file)
    assert any("Wundergerät" in line for line in report["skipped_furniture"])
    assert any("gekrümmte Wände" in line
               for line in __import__("sh3d").report_lines(report))


def test_views_are_generated(sh3d_file):
    views = spec_of(sh3d_file)["views"]
    kinds = {(v["kind"], v.get("level")) for v in views}
    assert ("plan", "niveau-0") in kinds
    assert ("plan", "niveau-1") in kinds
    assert any(v["kind"] == "3d" for v in views)


def test_rejects_non_zip(tmp_path):
    import sh3d

    bogus = tmp_path / "fake.sh3d"
    bogus.write_bytes(b"das ist kein zip")
    with pytest.raises(sh3d.Sh3dError):
        sh3d.convert_sh3d(bogus)


def test_rejects_doctype(tmp_path):
    import sh3d

    path = tmp_path / "evil.sh3d"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("Home.xml",
                    "<?xml version='1.0'?><!DOCTYPE home [<!ENTITY a 'x'>]>")
    with pytest.raises(sh3d.Sh3dError):
        sh3d.convert_sh3d(path)


def test_standalone_cli(tmp_path, capsys, sh3d_file):
    import subprocess
    import sys

    backend = Path(__file__).resolve().parents[1] / "app" / "backend"
    out = tmp_path / "modell.creabim.json"
    result = subprocess.run(
        [sys.executable, str(backend / "sh3d.py"), str(sh3d_file),
         str(out)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    spec = json.loads(out.read_text(encoding="utf-8"))
    assert spec["version"] == 1
    assert len(spec["slabs"]) == 2
    assert "Flächen: 2" in result.stdout


# ── Import über die API ────────────────────────────────────────────────────
def test_import_sh3d_via_api(client, sh3d_bytes):
    """Plumbing-Test mit der Stub-CLI (die echte Geometrie prüft test_real_cli)."""
    response = client.post("/api/projects/import",
                           files={"file": ("konzept.sh3d", io.BytesIO(sh3d_bytes),
                                           "application/octet-stream")},
                           data={"name": "SH3D Konzept"})
    assert response.status_code == 201, response.text
    project = response.json()["project"]
    assert project["kind"] == "sh3d"
    # Der Konvertierungs-Report kommt aus sh3d.convert_sh3d, nicht aus dem Stub.
    report = project.get("import_report")
    assert report and any("Flächen: 2" in line for line in report)
    assert any("Wundergerät" in line for line in report)
    assert client.get(f"/api/projects/{project['id']}").status_code == 200


def test_import_broken_sh3d_is_rejected(client):
    response = client.post("/api/projects/import",
                           files={"file": ("kaputt.sh3d", io.BytesIO(b"kein zip"),
                                           "application/octet-stream")})
    assert response.status_code == 400
    assert "SH3D" in response.json()["detail"]


def test_sample_still_works(client):
    pid = new_project(client)
    assert client.get(f"/api/projects/{pid}").status_code == 200