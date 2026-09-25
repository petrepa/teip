import json

import pytest

from teip import browser
from teip.app import ROOT
from teip.raster import STATUS_REQUEST


@pytest.fixture(autouse=True)
def icons(monkeypatch):
    monkeypatch.setattr(browser, "ICON_DIR", ROOT / "icons")


REQ = json.dumps({"labels": [{"lines": ["M3×8", "DIN 912"], "icons": ["drive/hex-socket"], "units": 1}]})


def test_models_include_every_printer():
    names = {m["model"] for m in json.loads(browser.models())}
    assert {"PT-E560BT", "PT-P700", "PT-P910BT"} <= names


def test_preview_matches_tape():
    png, dots, dpi = browser.preview("PT-E560BT", REQ, 9)
    assert png[:4] == b"\x89PNG" and dots == "262x50" and dpi == "180x180"


def test_jobs_bytes_and_lengths():
    jobs, mm = browser.jobs("PT-E560BT", REQ, 9)
    assert len(jobs) == 1 and jobs[0].startswith(b"\x00" * 100 + b"\x1b@")
    assert mm == [pytest.approx(37 + 2 * 2.0, abs=0.2)]


def test_jobs_refuse_other_tape():
    req = json.dumps({"labels": [{"lines": ["x"], "tape_mm": 12}]})
    with pytest.raises(ValueError, match="12"):
        browser.jobs("PT-E560BT", req, 9)


def test_status_and_handshake():
    raw = bytearray(32)
    raw[0], raw[1], raw[10], raw[11], raw[9] = 0x80, 0x20, 12, 0x01, 0x10
    st = json.loads(browser.status(bytes(raw)))
    assert st["tape_mm"] == 12 and st["errors"] == ["cover open"]
    assert browser.handshake().endswith(STATUS_REQUEST)


def test_parse_csv():
    labels = json.loads(browser.parse("line1,units\nM4,1\nM5,2"))
    assert [x["lines"] for x in labels] == [["M4"], ["M5"]]
