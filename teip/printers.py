"""Printer capability table. Data only: no printer-specific logic lives outside this file.

Pin splits come straight from Brother's raster command references, section 2.3.5
"Raster line", page 19 in both documents:

- PT-E550W/P750W/P710BT Raster Command Reference v1.02
  https://download.brother.com/welcome/docp100064/cv_pte550wp750wp710bt_eng_raster_102.pdf
- PT-P900/P900W/P950NW/P910BT Raster Command Reference v1.02
  https://download.brother.com/welcome/docp100407/cv_ptp900_eng_raster_102.pdf

The PT-E560BT and PT-P700 are not in either document. ptouch-print drives it with the E550W
command set and the same 128-pin/180 dpi head, so it uses the E550W table here.
"""

from dataclasses import dataclass

USB_VID = 0x04F9


@dataclass(frozen=True)
class TapePins:
    """How the head's pins split for one tape width. left + print + right == Printer.pins.

    `left` pins are sent first (MSB of the first raster byte), then the image rows top
    to bottom, then `right`. This matches the nbuchwitz/ptouch library's tested convention.
    """

    left: int
    print: int
    right: int


@dataclass(frozen=True)
class Printer:
    model: str
    usb_pid: int
    dpi: int  # across the tape, and along it in normal mode
    hires_dpi: int | None  # along-tape dpi with ESC i K bit 6; None = mode unsupported
    pins: int  # head width; a raster line is pins // 8 bytes
    max_tape_mm: int
    half_cut: bool  # ESC i K bit 2
    min_margin_dots: int  # ESC i d floor in normal mode (spec 2.3.3); doubles in hi-res
    min_feed_mm: float  # shortest tape the cutter can produce (spec 2.3.4) = leader waste per job
    packbits: bool  # send raster lines TIFF/PackBits compressed (M 02). E560BT feeds blank tape when compressed
    d460bt: bool  # PT-D410/D460BT/D610BT/E310BT/E560BT firmware: ESC i z n9=2 to finish, ^Z on every page,
    #               chain via ESC i K bit 3, no ESC i M / ESC i A. From ptouch-print (FLAG_D460BT_MAGIC).
    tapes: dict[int, TapePins]  # key = status byte 10 value, mm (3.5 mm tape reports 4)
    max_job_bytes: int | None = None  # split a batch into jobs no bigger than this (None = one job). A job
    #                                  boundary is a feed + full cut; half cuts only exist inside one job.

    def tape(self, width_mm: int) -> TapePins:
        try:
            return self.tapes[width_mm]
        except KeyError:
            raise ValueError(f"{self.model}: no pin data for {width_mm} mm tape") from None

    @property
    def bytes_per_line(self) -> int:
        return self.pins // 8


def dots(mm: float, dpi: int) -> int:
    return round(mm * dpi / 25.4)


# E550W family, section 2.3.5, page 19. Symmetric margins: print area is centred.
TZE_128PIN_180DPI = {
    4: TapePins(52, 24, 52),
    6: TapePins(48, 32, 48),
    9: TapePins(39, 50, 39),
    12: TapePins(29, 70, 29),
    18: TapePins(8, 112, 8),
    24: TapePins(0, 128, 0),
}

# P900 family, section 2.3.5, page 19. NOT centred (left != right): keep the split as given.
TZE_560PIN_360DPI = {
    4: TapePins(248, 48, 264),
    6: TapePins(240, 64, 256),
    9: TapePins(219, 106, 235),
    12: TapePins(197, 150, 213),
    18: TapePins(155, 234, 171),
    24: TapePins(112, 320, 128),
    36: TapePins(45, 454, 61),
}

PRINTERS: dict[str, Printer] = {
    p.model: p
    for p in (
        # packbits: E560BT verified 2026-09-03 (compressed job fed ~1 cm blank tape; raw prints).
        # E550W/P750W: nbuchwitz/ptouch says the cutter only fires with compression on.
        Printer("PT-E560BT", 0x2203, 180, 360, 128, 24, True, 14, 24.5, False, True, TZE_128PIN_180DPI),
        # PT-P700: untested. USB id, 128 pins/180 dpi, PackBits and a half cutter ("precut") from
        # ptouch-print's device table. Its "Editor Lite" switch must be off, or it enumerates as a USB drive.
        Printer("PT-P700", 0x2061, 180, None, 128, 24, True, 14, 24.5, True, False, TZE_128PIN_180DPI),
        Printer("PT-E550W", 0x2060, 180, 360, 128, 24, True, 14, 24.5, True, False, TZE_128PIN_180DPI),
        Printer("PT-P750W", 0x2062, 180, 360, 128, 24, True, 14, 24.5, True, False, TZE_128PIN_180DPI),
        Printer("PT-P710BT", 0x20AF, 180, 360, 128, 24, False, 14, 24.5, True, False, TZE_128PIN_180DPI),
        Printer("PT-P910BT", 0x20C7, 360, None, 560, 36, True, 14, 27.0, True, False, TZE_560PIN_360DPI),
        Printer("PT-P950NW", 0x2086, 360, 720, 560, 36, True, 14, 27.0, True, False, TZE_560PIN_360DPI),
    )
}
BY_PID = {p.usb_pid: p for p in PRINTERS.values()}
