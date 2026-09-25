"""Design -> 1-bit image whose height is exactly the printable dots of the tape. Pure functions.

Everything is laid out at the printer's native dpi on both axes. High-resolution mode
(along-tape dpi doubled) is a final nearest-neighbour stretch, so geometry stays exact.
"""

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .printers import Printer, dots


@dataclass(frozen=True)
class Design:
    tape_mm: int = 9
    lines: tuple[str, ...] = ()  # line 1 large, line 2 a smaller subtitle (LINE_WEIGHTS)
    icons: tuple[str, ...] = ()  # PNG/JPG/BMP paths, left to right (e.g. head profile, drive)
    length_mm: float | None = None  # None = fit to content
    font_size: int | None = None  # px across the tape; None = largest that fits
    font: str | None = None  # TTF path; None = Pillow's bundled default
    align: str = "left"  # text block inside its area: left | center | right
    layout: str = "side"  # side = icon left of text; stacked = icon above text
    margin_mm: float = 0.6  # padding inside the label, all sides
    gap_mm: float = 0.8  # between icon and text
    hires: bool = False


LINE_WEIGHTS = {1: (1.0,), 2: (0.62, 0.38)}  # share of the text height per line


def gridfinity_length_mm(units: int, base_mm: float = 37.0, unit_mm: float = 42.0) -> float:
    return base_mm + unit_mm * (units - 1)


# Pillow's bundled fallback (Aileron) lacks "×" and friends. Arial Bold where Windows has it (what the
# first install printed with), else the bundled Liberation Sans Bold: metric-compatible with Arial, SIL OFL,
# and the font the browser build uses, so a label looks the same wherever it is rendered.
BUNDLED_FONT = str(Path(__file__).resolve().parent / "fonts" / "LiberationSans-Bold.ttf")
FONT_CANDIDATES = ("C:/Windows/Fonts/arialbd.ttf", BUNDLED_FONT)


def load_font(path: str | None, size: int) -> ImageFont.FreeTypeFont:
    for p in ([path] if path else FONT_CANDIDATES):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            if path:
                raise
    return ImageFont.load_default(size=size)


def load_icon(path: str | Path) -> Image.Image:
    """Image file -> mode "1", alpha flattened on white, cropped to the black content.
    "file.png@90" rotates 90 degrees counter-clockwise (head-up profile -> head-left)."""
    path, _, rot = str(path).partition("@")
    p = Path(path)
    if p.suffix.lower() == ".svg":
        # ponytail: no SVG rasteriser; pre-render icons to PNG. Add resvg-py if the icon set is SVG-only.
        raise ValueError("SVG icons must be rasterised to PNG first")
    im = Image.open(p).convert("RGBA")
    bg = Image.new("RGBA", im.size, "white")
    bg.alpha_composite(im)
    gray = bg.convert("L")
    if rot:
        gray = gray.rotate(int(rot), expand=True, fillcolor=255)
    bbox = ImageOps.invert(gray).getbbox()
    return _to_1bit(gray.crop(bbox) if bbox else gray)


def _to_1bit(gray: Image.Image) -> Image.Image:
    return gray.point(lambda v: 255 if v > 127 else 0, "1")


def _fit_icon(icon: Image.Image, box_w: int | None, box_h: int) -> Image.Image:
    w = round(icon.width * box_h / icon.height)
    h = box_h
    if box_w is not None and w > box_w:
        w, h = box_w, round(icon.height * box_w / icon.width)
    return _to_1bit(icon.convert("L").resize((max(w, 1), max(h, 1)), Image.LANCZOS))


def _fit_line(text: str, font_path: str | None, size: int | None, max_h: int, max_w: int | None):
    """(font, bbox) for one line: given size, or the largest whose glyph box fits max_h x max_w."""
    for s in ([size] if size else range(max_h + 4, 3, -1)):
        f = load_font(font_path, s)
        b = f.getbbox(text)
        if size or (b[3] - b[1] <= max_h and (max_w is None or b[2] - b[0] <= max_w)):
            return f, b
    return f, b


def _fit_text(lines: tuple[str, ...], font_path: str | None, size: int | None, max_h: int, max_w: int | None, gap: int):
    """Per-line (font, bbox, height); block width. Line budgets follow LINE_WEIGHTS."""
    n = len(lines)
    weights = LINE_WEIGHTS.get(n) or (1.0 / n,) * n
    avail = max_h - gap * (n - 1)
    fitted = []
    for text, w in zip(lines, weights):
        f, b = _fit_line(text, font_path, size, max(int(avail * w), 4), max_w)
        fitted.append((f, b, b[3] - b[1]))
    return fitted, max(b[2] - b[0] for _, b, _ in fitted)


def render(d: Design, printer: Printer) -> Image.Image:
    dpi = printer.dpi
    H = printer.tape(d.tape_mm).print
    pad, gap, line_gap = dots(d.margin_mm, dpi), dots(d.gap_mm, dpi), dots(0.3, dpi)
    inner_h = H - 2 * pad
    W = dots(d.length_mm, dpi) if d.length_mm else None
    inner_w = None if W is None else W - 2 * pad

    lines = tuple(t for t in d.lines if t.strip())
    icons = [_fit_icon(load_icon(p), None, inner_h) for p in d.icons]
    stacked = d.layout == "stacked" and icons and lines
    if stacked:
        icons = [_fit_icon(ic, inner_w, round(inner_h * 0.55)) for ic in icons]
    icons_w = sum(ic.width for ic in icons) + gap * max(len(icons) - 1, 0)
    icons_h = max((ic.height for ic in icons), default=0)

    # text area: what's left after the icons
    fitted, tw = [], 0
    if lines:
        if stacked:
            text_h, text_w = inner_h - icons_h - gap, inner_w
        else:
            text_h, text_w = inner_h, None if inner_w is None else inner_w - (icons_w + gap if icons else 0)
        fitted, tw = _fit_text(lines, d.font, d.font_size, text_h, text_w, line_gap)

    if W is None:
        content_w = max(icons_w, tw) if stacked else (icons_w + gap if icons else 0) + tw
        W = content_w + 2 * pad
        inner_w = W - 2 * pad

    im = Image.new("1", (max(W, 1), H), 1)
    draw = ImageDraw.Draw(im)
    x = pad + (inner_w - icons_w) // 2 if stacked else pad
    for ic in icons:
        im.paste(ic, (x, pad if stacked else pad + (inner_h - ic.height) // 2))
        x += ic.width + gap
    if lines:
        area_x = pad if stacked else pad + (icons_w + gap if icons else 0)
        area_w = inner_w if stacked else inner_w - (icons_w + gap if icons else 0)
        area_y = pad + icons_h + gap if stacked else pad
        area_h = inner_h - icons_h - gap if stacked else inner_h
        block_h = sum(h for _, _, h in fitted) + line_gap * (len(fitted) - 1)
        y = area_y + max((area_h - block_h) // 2, 0)
        for t, (f, b, h) in zip(lines, fitted):
            w = b[2] - b[0]
            x = area_x + {"left": 0, "center": (area_w - w) // 2, "right": area_w - w}[d.align]
            draw.text((x - b[0], y - b[1]), t, font=f, fill=0)
            y += h + line_gap
    if d.hires:
        if not printer.hires_dpi:
            raise ValueError(f"{printer.model} has no high-resolution mode")
        im = im.resize((dots(W * 25.4 / dpi, printer.hires_dpi), H), Image.NEAREST)
    return im


def strip_preview(images: list[Image.Image], margin_dots: int) -> Image.Image:
    """Labels in print order with their feed margins and a dotted cut line between them."""
    H = max(im.height for im in images)
    W = sum(im.width + 2 * margin_dots for im in images)
    out = Image.new("1", (W, H), 1)
    x = 0
    for i, im in enumerate(images):
        out.paste(im, (x + margin_dots, (H - im.height) // 2))
        x += im.width + 2 * margin_dots
        if i < len(images) - 1:
            for y in range(0, H, 3):
                out.putpixel((x - 1, y), 0)
    return out
