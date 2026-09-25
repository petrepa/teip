"""Entry points for the page when it runs without a server (GitHub Pages), under Pyodide.

The page passes JSON strings and bytes in and gets bytes and JSON back; everything in
between is labels.py, the same code the server runs. The page itself talks to the printer
(WebUSB or Web Serial) and fetches each icon into ICON_DIR before asking for a render.
"""

import json
from pathlib import Path

from .config import Config
from .labels import Pipeline, PrintRequest, parse_batch
from .printers import PRINTERS
from .raster import INITIALIZE, INVALIDATE, STATUS_REQUEST, parse_status
from .render import BUNDLED_FONT

ICON_DIR = Path("/icons")
CFG = Config(font=BUNDLED_FONT)  # config.py defaults: margins, Gridfinity lengths


def _pipe(model: str) -> Pipeline:
    return Pipeline(PRINTERS[model], CFG, ICON_DIR)


def models() -> str:
    """Every supported printer, for the model picker and for matching a WebUSB device id."""
    return json.dumps([
        {"model": p.model, "usb_pid": p.usb_pid, "dpi": p.dpi, "half_cut": p.half_cut, "tapes": sorted(p.tapes),
         "min_feed_mm": p.min_feed_mm}
        for p in PRINTERS.values()
    ])


def defaults() -> str:
    return json.dumps({"tape_mm": CFG.tape_mm, "margin_mm": CFG.margin_mm,
                       "gridfinity_base_mm": CFG.gridfinity_base_mm, "gridfinity_unit_mm": CFG.gridfinity_unit_mm})


def preview(model: str, request: str, tape_mm: int) -> list:
    """[png bytes, X-Dots, X-Dpi] for the label or strip."""
    png, headers = _pipe(model).preview(PrintRequest.model_validate_json(request), tape_mm)
    return [png, headers["X-Dots"], headers["X-Dpi"]]


def jobs(model: str, request: str, tape_mm: int) -> list:
    """[[job bytes, ...], [label length in mm, ...]] for the tape the printer reports."""
    pipe = _pipe(model)
    req = pipe.for_loaded_tape(PrintRequest.model_validate_json(request), tape_mm)
    job_list, mm = pipe.jobs(req, tape_mm)
    return [job_list, mm]


def handshake() -> bytes:
    """Clear the printer's buffer, reset it and ask for status: the start of every exchange."""
    return INVALIDATE + INITIALIZE + STATUS_REQUEST


def status_request() -> bytes:
    return STATUS_REQUEST


def status(raw) -> str:
    """raw: the 32-byte packet; a JS Uint8Array arrives as a JsProxy with to_bytes()."""
    st = parse_status(raw.to_bytes() if hasattr(raw, "to_bytes") else bytes(raw))
    return json.dumps({"tape_mm": st.width_mm, "media": st.media, "errors": st.errors,
                       "status_type": st.status_type, "phase_type": st.phase_type})


def parse(text: str) -> str:
    return json.dumps([s.model_dump(exclude_none=True) for s in parse_batch(text)])
