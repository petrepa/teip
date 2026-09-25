"""Brother P-touch raster protocol: job bytes out, status bytes in.

Job layout follows section 2.1 "Print data overview" of the E550W reference; the
per-page choreography for half-cut batches copies the nbuchwitz/ptouch library,
which is verified on E550W hardware:

    invalidate, initialize                       once per job
    per page:
        ESC i a 01        raster mode
        ESC i z ...       print information (media, width, line count, first/other page)
        ESC i M           auto cut         (off when half-cutting a batch)
        ESC i A 01        cut each 1 label (only with auto cut)
        ESC i K           half cut / no chain / hi-res
        ESC i d           margin (feed) dots
        M 02 | M 00       TIFF PackBits or raw
        G ... | Z         raster lines
        FF | ^Z           print, or print with feed on the last page

ptouch-print's "PT-D460BT magic" (1B 69 64 01 00 4D 00) is just ESC i d margin=1
followed by M 00; both are regular commands sent here anyway.
"""

from dataclasses import dataclass, replace
from PIL import Image
from .printers import Printer, TapePins

INVALIDATE = b"\x00" * 100
INITIALIZE = b"\x1b@"
STATUS_REQUEST = b"\x1biS"
RASTER_MODE = b"\x1bia\x01"
PRINT_PAGE = b"\x0c"
PRINT_LAST = b"\x1a"

# ESC i z byte n1 valid-flags (spec 4, "Print information command")
PI_KIND, PI_WIDTH, PI_LENGTH, PI_RECOVER = 0x02, 0x04, 0x08, 0x80
MEDIA_LAMINATED = 0x01

MEDIA_TYPE = {
    0x00: "no media",
    0x01: "laminated",
    0x03: "non-laminated",
    0x11: "heat-shrink 2:1",
    0x17: "heat-shrink 3:1",
    0xFF: "incompatible",
}
ERROR1 = {0x01: "no media", 0x04: "cutter jam", 0x08: "weak batteries", 0x40: "high-voltage adapter"}
ERROR2 = {0x01: "wrong media", 0x10: "cover open", 0x20: "overheating"}
STATUS_TYPE = {0x00: "reply", 0x01: "printing completed", 0x02: "error", 0x06: "phase change"}


@dataclass(frozen=True)
class Status:
    model_code: str
    width_mm: int
    media_type: int
    err1: int
    err2: int
    status_type: int
    phase_type: int
    raw: bytes

    @property
    def errors(self) -> list[str]:
        return [n for m, n in ERROR1.items() if self.err1 & m] + [n for m, n in ERROR2.items() if self.err2 & m]

    @property
    def media(self) -> str:
        return MEDIA_TYPE.get(self.media_type, f"0x{self.media_type:02x}")


def parse_status(raw: bytes) -> Status:
    """32-byte status packet (spec 4, table under ESC i S)."""
    if len(raw) != 32 or raw[0] != 0x80 or raw[1] != 0x20:
        raise ValueError(f"not a status packet: {bytes(raw).hex()}")
    return Status(chr(raw[4]), raw[10], raw[11], raw[8], raw[9], raw[18], raw[19], bytes(raw))


@dataclass(frozen=True)
class JobOptions:
    margin_dots: int = 14  # ESC i d, along-tape dots at the active resolution; spec floor 14 at 180 dpi
    half_cut: bool = True  # between labels of a batch; needs Printer.half_cut
    hires: bool = False  # ESC i K bit 6; images must be rendered at Printer.hires_dpi along the tape
    compress: bool | None = None  # TIFF PackBits; None = Printer.packbits
    chain: bool = False  # leave the last label inside: no feed/cut after it. The next job's leading cut
    #                      releases it with only the margins between, saving ~min_feed_mm per job.
    media_type: int = MEDIA_LAMINATED


def packbits(line: bytes) -> bytes:
    """TIFF PackBits, spec 4 "Select compression mode" example: 20x00 -> ED 00, 2x22 -> FF 22, 6 literals -> 05 ..."""
    out = bytearray()
    i, n = 0, len(line)
    while i < n:
        j = i
        while j + 1 < n and line[j + 1] == line[i] and j - i < 126:
            j += 1
        if j > i:  # run of j-i+1 identical bytes
            out += bytes([256 - (j - i), line[i]])
            i = j + 1
            continue
        j = i + 1
        while j < n and j - i < 128 and not (j + 1 < n and line[j + 1] == line[j]):
            j += 1
        out += bytes([j - i - 1]) + line[i:j]
        i = j
    return bytes(out)


def raster_lines(image: Image.Image, printer: Printer, pins: TapePins) -> list[bytes]:
    """One `pins // 8`-byte line per image column. Bit index = pins.left + row, MSB first."""
    if image.mode != "1":
        image = image.convert("1")
    if image.height != pins.print:
        raise ValueError(f"image height {image.height} != printable dots {pins.print}")
    px = image.load()
    lines = []
    for x in range(image.width):
        bits = 0
        for y in range(pins.print):
            if px[x, y] == 0:  # black
                bits |= 1 << (printer.pins - 1 - (pins.left + y))
        lines.append(bits.to_bytes(printer.bytes_per_line, "big"))
    return lines


def _page(printer: Printer, pins: TapePins, width_mm: int, image: Image.Image, o: JobOptions, first: bool, last: bool, half_cut: bool) -> bytes:
    auto_cut = not half_cut
    compress = printer.packbits if o.compress is None else o.compress
    n_lines = image.width
    out = bytearray(RASTER_MODE)
    if printer.d460bt:
        # ptouch-print's verified sequence for this family: ESC i z with no valid flags and n9=2,
        # margin, compression mode, ESC i K only to chain, raster, ^Z. Never FF, never ESC i M.
        out += bytes([0x1B, 0x69, 0x7A, 0, 0, width_mm, 0]) + n_lines.to_bytes(4, "little") + bytes([2, 0])
        if first:  # auto cut: cuts the blank leader off the first label (a peel tab). Pages are sent as
            # separate jobs; on the later ones this would cut again where the previous page already half-cut.
            out += b"\x1biM\x40"
        out += b"\x1bid" + o.margin_dots.to_bytes(2, "little")
        out += b"M\x02" if compress else b"M\x00"
        out += bytes([0x1B, 0x69, 0x4B, (half_cut << 2) | ((last and not o.chain) << 3) | (o.hires << 6)])
    else:
        out += bytes([0x1B, 0x69, 0x7A, PI_KIND | PI_WIDTH | PI_RECOVER, o.media_type, width_mm, 0])
        out += n_lines.to_bytes(4, "little") + bytes([0 if first else 1, 0])
        out += bytes([0x1B, 0x69, 0x4D, 0x40 if auto_cut else 0x00])
        if auto_cut:
            out += b"\x1biA\x01"
        out += bytes([0x1B, 0x69, 0x4B, (half_cut << 2) | ((not o.chain) << 3) | (o.hires << 6)])
        out += b"\x1bid" + o.margin_dots.to_bytes(2, "little")
        out += b"M\x02" if compress else b"M\x00"
    for line in raster_lines(image, printer, pins):
        if compress:
            if not any(line):
                out += b"Z"
                continue
            line = packbits(line)
        out += b"G" + len(line).to_bytes(2, "little") + line
    out += PRINT_LAST if (last or printer.d460bt) else PRINT_PAGE
    return bytes(out)


def build_jobs(printer: Printer, width_mm: int, images: list[Image.Image], o: JobOptions = JobOptions(), max_bytes: int | None = None) -> list[bytes]:
    """The batch as one or more jobs on `width_mm` tape, each invalidate + initialize + consecutive
    pages, each at most `max_bytes` (None: one job). Pages inside a job chain with half cuts between
    them; a job boundary is a feed and full cut, because the printer releases held tape with a full
    cut when the next job arrives (E560BT, verified)."""
    if not images:
        raise ValueError("no images")
    if o.half_cut and not printer.half_cut:
        raise ValueError(f"{printer.model} has no half cutter")
    if o.hires and not printer.hires_dpi:
        raise ValueError(f"{printer.model} has no high-resolution mode")
    floor = printer.min_margin_dots * (2 if o.hires else 1)
    if o.margin_dots < floor:
        raise ValueError(f"margin {o.margin_dots} dots below printer floor {floor}")
    pins = printer.tape(width_mm)
    # E560BT: the half-cut bit also turns the leading cut into a half cut (peel tab), so set it for single labels too
    half = o.half_cut and (len(images) > 1 or printer.d460bt)
    sizes = [len(_page(printer, pins, width_mm, im, o, first=False, last=False, half_cut=half)) for im in images]
    groups: list[list[int]] = [[]]
    for i, n in enumerate(sizes):
        if groups[-1] and max_bytes and len(INVALIDATE + INITIALIZE) + sum(sizes[k] for k in groups[-1]) + n > max_bytes:
            groups.append([])
        groups[-1].append(i)
    jobs = []
    for g, group in enumerate(groups):
        opts = o if g == len(groups) - 1 else replace(o, chain=False)  # only the batch's last label may be held
        job = bytearray(INVALIDATE + INITIALIZE)
        for k, i in enumerate(group):
            job += _page(printer, pins, width_mm, images[i], opts, first=k == 0, last=k == len(group) - 1, half_cut=half)
        jobs.append(bytes(job))
    return jobs


def build_job(printer: Printer, width_mm: int, images: list[Image.Image], o: JobOptions = JobOptions()) -> bytes:
    """Whole batch as one job (mock backend, files)."""
    return b"".join(build_jobs(printer, width_mm, images, o))


if __name__ == "__main__":  # status probe: python -m teip.raster [MODEL]
    import sys
    from .backend import UsbBackend
    from .printers import PRINTERS

    p = PRINTERS[sys.argv[1] if len(sys.argv) > 1 else "PT-E560BT"]
    st = UsbBackend(p).status()
    if st is None:
        sys.exit(f"{p.model} (04f9:{p.usb_pid:04x}) not found on USB")
    print(f"model_code={st.model_code!r} tape={st.width_mm} mm {st.media} errors={st.errors or 'none'}")
    print(st.raw.hex(" "))
