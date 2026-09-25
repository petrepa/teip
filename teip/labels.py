"""Label requests -> images -> printer jobs. Shared by the server (app.py) and the browser (browser.py,
run under Pyodide), so both render and encode with exactly the same code."""

import csv
import io
from pathlib import Path

import yaml
from PIL import Image
from pydantic import BaseModel, Field, model_validator

from .config import Config
from .printers import Printer, dots
from .raster import JobOptions, build_jobs
from .render import Design, gridfinity_length_mm, render, strip_preview

ICON_EXT = (".png", ".jpg", ".jpeg", ".bmp", ".gif")


class LabelSpec(BaseModel):
    lines: list[str] = []
    line1: str | None = None  # batch-friendly aliases, merged into `lines`
    line2: str | None = None
    icon: str | None = None  # single icon, "drive/hex-socket" relative to the icon dir, extension optional
    icons: list[str] = []  # several, left to right, e.g. ["head/screw-hex", "drive/hex-socket"]
    tape_mm: int | None = None  # None = whatever the printer reports
    length_mm: float | None = None
    units: float | None = Field(None, ge=0.5, le=12)  # Gridfinity grid units (halves allowed); overrides length_mm
    font_size: int | None = Field(None, ge=4)
    align: str = "left"
    layout: str = "side"
    margin_mm: float = 0.6
    gap_mm: float = 0.8

    @model_validator(mode="after")
    def _merge(self):
        if not self.lines:
            self.lines = [t for t in (self.line1, self.line2) if t]
        self.lines = [t for t in self.lines if t and t.strip()]
        if self.icon and self.icon not in self.icons:
            self.icons = [self.icon, *self.icons]
        self.icon = None
        return self


class PrintOptions(BaseModel):
    margin_mm: float | None = None  # feed before/after each label; None = config
    half_cut: bool = True
    hires: bool = False
    copies: int = Field(1, ge=1, le=50)
    chain: bool = False  # no feed/cut after the last label; next job or the printer's Feed/Cut key releases it
    force: bool = False  # re-lay out the design for the loaded tape instead of refusing on mismatch


class PrintRequest(BaseModel):
    labels: list[LabelSpec] = Field(min_length=1)
    options: PrintOptions = PrintOptions()


class Template(BaseModel):
    name: str
    label: LabelSpec


class IconNotFound(LookupError):
    pass


def list_icons(icon_dir: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for p in sorted(icon_dir.rglob("*")):
        if p.suffix.lower() in ICON_EXT:
            out.setdefault(str(p.parent.relative_to(icon_dir)).replace("\\", "/"), []).append(p.stem)
    return out


def resolve_icon(icon_dir: Path, name: str) -> str:
    """"drive/torx" -> file path; a "@90" suffix (rotation, CCW degrees) is passed through to the renderer."""
    name, _, rot = name.partition("@")
    base = (icon_dir / name).resolve()
    if not base.is_relative_to(icon_dir.resolve()):
        raise ValueError("icon path escapes the icon directory")
    for cand in [base, *(base.with_suffix(e) for e in ICON_EXT)]:
        if cand.is_file():
            return f"{cand}@{rot}" if rot else str(cand)
    raise IconNotFound(f"icon not found: {name}")


class Pipeline:
    """Everything between a PrintRequest and the printer, for one printer model and config."""

    def __init__(self, printer: Printer, cfg: Config, icon_dir: Path):
        self.printer, self.cfg, self.icon_dir = printer, cfg, icon_dir

    def design(self, spec: LabelSpec, tape_mm: int, hires: bool) -> Design:
        length = spec.length_mm
        if spec.units:
            length = gridfinity_length_mm(spec.units, self.cfg.gridfinity_base_mm, self.cfg.gridfinity_unit_mm)
        return Design(
            tape_mm=spec.tape_mm or tape_mm,
            lines=tuple(spec.lines),
            icons=tuple(resolve_icon(self.icon_dir, i) for i in spec.icons if i),
            length_mm=length,
            font_size=spec.font_size,
            font=self.cfg.font or None,
            align=spec.align,
            layout=spec.layout,
            margin_mm=spec.margin_mm,
            gap_mm=spec.gap_mm,
            hires=hires,
        )

    def job_options(self, o: PrintOptions) -> JobOptions:
        p = self.printer
        dpi = p.hires_dpi if o.hires else p.dpi
        margin = dots(o.margin_mm if o.margin_mm is not None else self.cfg.margin_mm, dpi)
        return JobOptions(margin_dots=margin, half_cut=o.half_cut and p.half_cut, hires=o.hires, chain=o.chain)

    def images(self, req: PrintRequest, tape_mm: int) -> list[Image.Image]:
        return [render(self.design(s, tape_mm, req.options.hires), self.printer) for s in req.labels] * req.options.copies

    def preview(self, req: PrintRequest, tape_mm: int) -> tuple[bytes, dict[str, str]]:
        """PNG of the label, or of the whole strip for several, plus the X-Dots / X-Dpi headers."""
        ims = self.images(req, tape_mm)
        im = strip_preview(ims, self.job_options(req.options).margin_dots) if len(ims) > 1 else ims[0]
        buf = io.BytesIO()
        im.save(buf, "PNG")
        dpi_x = self.printer.hires_dpi if req.options.hires else self.printer.dpi
        return buf.getvalue(), {"X-Dots": f"{im.width}x{im.height}", "X-Dpi": f"{dpi_x}x{self.printer.dpi}"}

    def for_loaded_tape(self, req: PrintRequest, tape_mm: int) -> PrintRequest:
        """Refuse a design made for another tape, unless options.force: then re-lay it out for the loaded one."""
        wanted = {s.tape_mm for s in req.labels if s.tape_mm} - {tape_mm}
        if not wanted:
            return req
        if not req.options.force:
            raise ValueError(f"design is for {sorted(wanted)} mm tape but printer has {tape_mm} mm")
        return req.model_copy(update={"labels": [s.model_copy(update={"tape_mm": None}) for s in req.labels]})

    def jobs(self, req: PrintRequest, tape_mm: int) -> tuple[list[bytes], list[float]]:
        """Printer jobs for the loaded tape, and each label's length in mm with its margins (for wait estimates)."""
        ims = self.images(req, tape_mm)
        o = self.job_options(req.options)
        dpi_x = self.printer.hires_dpi if o.hires else self.printer.dpi
        mm = [(im.width + 2 * o.margin_dots) * 25.4 / dpi_x for im in ims]
        return build_jobs(self.printer, tape_mm, ims, o, self.printer.max_job_bytes), mm


def parse_batch(text: str) -> list[LabelSpec]:
    """YAML list of label dicts (or {labels: [...]}), else CSV with a header row."""
    text = text.strip()
    if not text:
        return []
    try:
        data = yaml.safe_load(text)
        if isinstance(data, dict):
            data = data.get("labels")
        if isinstance(data, list) and all(isinstance(x, dict) for x in data):
            return [LabelSpec(**x) for x in data]
    except yaml.YAMLError:
        pass
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise ValueError("batch text is neither a YAML list nor CSV with a header")
    return [LabelSpec(**{k.strip(): v for k, v in r.items() if k and v not in (None, "")}) for r in rows]
