import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from teip import config as cfgmod
from teip.app import ROOT, create_app
from teip.labels import LabelSpec, parse_batch


@pytest.fixture
def client(tmp_path):
    cfg = cfgmod.Config(backend="mock", tape_mm=9, data_dir=str(tmp_path))
    return TestClient(create_app(cfg))


def test_index_and_status(client):
    assert "<title>teip</title>" in client.get("/").text
    assert client.get("/api/boot").json()["printer"] == "PT-E560BT"
    r = client.get("/v2", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "./"
    s = client.get("/api/status").json()
    assert s["connected"] and s["tape_mm"] == 9 and s["backend"] == "mock"


def test_preview_dims(client):
    r = client.post("/api/preview", json={"labels": [{"lines": ["M3x8", "SHCS"], "units": 1, "icon": "drive/hex-socket"}]})
    assert r.status_code == 200 and r.headers["X-Dots"] == "262x50"
    assert Image.open(io.BytesIO(r.content)).size == (262, 50)


def test_print_mock_and_recent(client, tmp_path):
    r = client.post("/api/print", json={"labels": [{"lines": ["A"]}, {"lines": ["B"], "units": 2}], "options": {"copies": 2}})
    assert r.status_code == 200 and r.json()["labels"] == 4
    assert len(list((tmp_path / "mock").glob("*.bin"))) == 1
    assert len(client.get("/api/recent").json()) == 1


def test_tape_mismatch_refused(client):
    r = client.post("/api/print", json={"labels": [{"lines": ["A"], "tape_mm": 12}]})
    assert r.status_code == 409
    r = client.post("/api/print", json={"labels": [{"lines": ["A"], "tape_mm": 12}], "options": {"force": True}})
    assert r.status_code == 200


def test_print_png(client):
    buf = io.BytesIO()
    Image.new("1", (100, 50), 1).save(buf, "PNG")
    r = client.post("/api/print/png", files={"image": ("x.png", buf.getvalue(), "image/png")})
    assert r.status_code == 200
    buf = io.BytesIO()
    Image.new("1", (100, 70), 1).save(buf, "PNG")
    assert client.post("/api/print/png", files={"image": ("x.png", buf.getvalue(), "image/png")}).status_code == 400


def test_icon_traversal_and_missing(client):
    assert client.post("/api/preview", json={"labels": [{"lines": ["A"], "icon": "../pyproject"}]}).status_code == 400
    assert client.post("/api/preview", json={"labels": [{"lines": ["A"], "icon": "nope/nope"}]}).status_code == 404


def test_templates_roundtrip(client):
    assert client.post("/api/templates", json={"name": "m3", "label": {"lines": ["M3"], "units": 1}}).json()[0]["name"] == "m3"
    assert client.get("/api/templates").json()[0]["label"]["units"] == 1
    assert client.delete("/api/templates/m3").json() == []


def test_parse_batch_yaml_and_csv():
    y = parse_batch("- {icon: drive/torx, line1: T20, units: 1}\n- {lines: [M4, nyloc], units: 2}")
    assert [s.lines for s in y] == [["T20"], ["M4", "nyloc"]] and y[1].units == 2
    c = parse_batch("icon,line1,line2,units\ndrive/torx,T20,,1\n,M4,nyloc,2\n")
    assert [s.lines for s in c] == [["T20"], ["M4", "nyloc"]] and c[1].icon is None and c[1].units == 2
    assert parse_batch("") == []


def test_labelspec_merges_lines():
    assert LabelSpec(line1="a", line2="").lines == ["a"]
    assert LabelSpec(lines=["x", " "]).lines == ["x"]


def test_half_units_and_rotated_icon(client):
    r = client.post("/api/preview", json={"labels": [{"lines": ["M3"], "units": 1.5, "icons": ["head/hex@90", "drive/torx"]}]})
    assert r.status_code == 200 and r.headers["X-Dots"].startswith("411x")  # 37 + 21 mm = 58 mm


def test_rivet_icons_render(client):
    for n in ("dome", "countersunk", "large-flange", "nut"):
        assert (ROOT / "icons" / "rivets" / f"{n}.png").exists()
    r = client.post("/api/preview", json={"labels": [{"lines": ["Ø4.8×13", "Alu · grip ≈6.5–8.5"], "units": 1, "icons": ["rivets/dome"]}]})
    assert r.status_code == 200
