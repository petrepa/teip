"""FastAPI server: the web app, preview, print, status, templates, recent, batch parsing.

Server mode of teip. The same page also runs without this server (GitHub Pages, printer on
WebUSB or Web Serial); see browser.py. Rendering and encoding live in labels.py for both."""

import io
import json
import threading
import time
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image

from . import config as cfgmod
from .backend import MockBackend, UsbBackend
from .labels import ICON_EXT, IconNotFound, Pipeline, PrintOptions, PrintRequest, Template, list_icons, parse_batch
from .printers import PRINTERS

ROOT = Path(__file__).resolve().parent.parent


def create_app(cfg: cfgmod.Config | None = None) -> FastAPI:
    cfg = cfg or cfgmod.load()
    printer = PRINTERS[cfg.printer]
    data_dir = (ROOT / cfg.data_dir) if not Path(cfg.data_dir).is_absolute() else Path(cfg.data_dir)
    icon_dir = (ROOT / cfg.icon_dir) if not Path(cfg.icon_dir).is_absolute() else Path(cfg.icon_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    backend = MockBackend(printer, data_dir / "mock", cfg.tape_mm) if cfg.backend == "mock" else UsbBackend(printer)
    lock = threading.Lock()

    app = FastAPI(title="teip", root_path=cfg.root_path)
    app.state.cfg, app.state.backend, app.state.printer = cfg, backend, printer
    app.mount("/static", StaticFiles(directory=ROOT / "teip" / "static"), name="static")
    app.mount("/icons", StaticFiles(directory=icon_dir), name="icons")

    # --- small JSON stores -------------------------------------------------------------
    def read_json(name, default):
        p = data_dir / name
        return json.loads(p.read_text("utf-8")) if p.exists() else default

    def write_json(name, obj):
        (data_dir / name).write_text(json.dumps(obj, indent=1, ensure_ascii=False), "utf-8")

    # --- helpers -----------------------------------------------------------------------
    pipe = Pipeline(printer, cfg, icon_dir)

    def icons() -> dict[str, list[str]]:
        return list_icons(icon_dir)

    def http_errors(fn, *args):
        try:
            return fn(*args)
        except IconNotFound as e:
            raise HTTPException(404, str(e))
        except ValueError as e:
            raise HTTPException(400, str(e))

    def render_all(req: PrintRequest, tape_mm: int) -> list[Image.Image]:
        return http_errors(pipe.images, req, tape_mm)

    def status_dict():
        st = backend.status()
        return {
            "backend": cfg.backend,
            "printer": printer.model,
            "dpi": printer.dpi,
            "connected": st is not None,
            "tape_mm": st.width_mm if st else None,
            "media": st.media if st else None,
            "errors": st.errors if st else [],
            "half_cut": printer.half_cut,
            "busy": getattr(backend, "busy", False),
        }

    # --- routes ------------------------------------------------------------------------
    def boot():
        return {
            "icons": icons(),
            "tapes": sorted(printer.tapes),
            "printable_dots": {mm: p.print for mm, p in printer.tapes.items()},
            "dpi": printer.dpi,
            "printer": printer.model,
            "defaults": {
                "tape_mm": cfg.tape_mm,
                "margin_mm": cfg.margin_mm,
                "gridfinity_base_mm": cfg.gridfinity_base_mm,
                "gridfinity_unit_mm": cfg.gridfinity_unit_mm,
            },
            "templates": read_json("templates.json", []),
            "recent": read_json("recent.json", []),
        }

    @app.get("/")
    def index():
        return FileResponse(ROOT / "teip" / "static" / "index.html")

    @app.get("/api/boot")
    def api_boot():
        """What the page needs to start in server mode. On GitHub Pages this 404s and the page runs on its own."""
        return boot()

    @app.get("/v2")
    def index_v2():
        """The v2 UI is the only UI now; keep old /v2 links (and their #category) working."""
        return RedirectResponse("./", 301)

    @app.get("/api/status")
    def api_status():
        return status_dict()

    @app.post("/api/preview")
    def api_preview(req: PrintRequest):
        st = backend.status()
        tape = st.width_mm if st and st.width_mm else cfg.tape_mm
        png, headers = http_errors(pipe.preview, req, tape)
        return Response(png, media_type="image/png", headers=headers)

    def push_recent(req: PrintRequest, result: str):
        recent = read_json("recent.json", [])
        recent.insert(0, {"ts": int(time.time()), "result": result, "request": req.model_dump(exclude_none=True)})
        write_json("recent.json", recent[:30])

    @app.post("/api/print")
    def api_print(req: PrintRequest):
        st = backend.status()
        if st is None:
            raise HTTPException(503, f"{printer.model} not connected")
        if st.errors:
            raise HTTPException(409, "printer error: " + ", ".join(st.errors))
        if not st.width_mm:
            raise HTTPException(409, "no tape loaded")
        try:
            req = pipe.for_loaded_tape(req, st.width_mm)
        except ValueError as e:
            raise HTTPException(409, str(e))
        ims = render_all(req, st.width_mm)
        try:
            with lock:
                result = backend.print(ims, pipe.job_options(req.options))
        except (RuntimeError, TimeoutError, ValueError) as e:
            raise HTTPException(500, str(e))
        push_recent(req, result)
        return {"ok": True, "labels": len(ims), "result": result}

    @app.post("/api/print/png")
    async def api_print_png(image: UploadFile = File(...), margin_mm: float | None = None, half_cut: bool = True):
        """Raw 1-bit PNG, height must equal the printable dots of the loaded tape. Length is free."""
        st = backend.status()
        if st is None or not st.width_mm:
            raise HTTPException(503, "printer not connected or no tape")
        im = Image.open(io.BytesIO(await image.read())).convert("1")
        want = printer.tape(st.width_mm).print
        if im.height != want:
            raise HTTPException(400, f"image height {im.height} px, need {want} px for {st.width_mm} mm tape at {printer.dpi} dpi")
        opts = pipe.job_options(PrintOptions(margin_mm=margin_mm, half_cut=half_cut))
        try:
            with lock:
                result = backend.print([im], opts)
        except (RuntimeError, TimeoutError, ValueError) as e:
            raise HTTPException(500, str(e))
        return {"ok": True, "labels": 1, "result": result}

    @app.post("/api/batch/parse")
    def api_batch_parse(body: dict):
        try:
            labels = parse_batch(body.get("text", ""))
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"labels": [s.model_dump(exclude_none=True) for s in labels]}

    @app.get("/api/templates")
    def api_templates():
        return read_json("templates.json", [])

    @app.post("/api/templates")
    def api_templates_save(t: Template):
        items = [x for x in read_json("templates.json", []) if x["name"] != t.name]
        items.append(t.model_dump(exclude_none=True))
        write_json("templates.json", sorted(items, key=lambda x: x["name"].lower()))
        return items

    @app.delete("/api/templates/{name}")
    def api_templates_delete(name: str):
        items = [x for x in read_json("templates.json", []) if x["name"] != name]
        write_json("templates.json", items)
        return items

    @app.get("/api/recent")
    def api_recent():
        return read_json("recent.json", [])

    @app.get("/api/icons")
    def api_icons():
        return icons()

    @app.post("/api/icons")
    async def api_icon_upload(file: UploadFile = File(...), folder: str = "custom"):
        if Path(file.filename or "").suffix.lower() not in ICON_EXT:
            raise HTTPException(400, f"PNG/JPG/BMP/GIF only, got {file.filename}")
        dest = (icon_dir / folder / Path(file.filename).name).resolve()
        if not dest.is_relative_to(icon_dir.resolve()):
            raise HTTPException(400, "bad folder")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(await file.read())
        return {"icon": f"{folder}/{dest.stem}", "icons": icons()}

    return app



app = create_app()
