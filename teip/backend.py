"""Printer backends. MockBackend writes the strip PNG and job bytes to disk; UsbBackend talks libusb."""

import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Protocol

from PIL import Image

from .printers import BY_PID, USB_VID, Printer
from .raster import INITIALIZE, INVALIDATE, STATUS_REQUEST, JobOptions, Status, build_job, build_jobs, parse_status
from .render import strip_preview

STATUS_COMPLETED, STATUS_ERROR = 0x01, 0x02
log = logging.getLogger("teip")


class PrinterBackend(Protocol):
    printer: Printer

    def status(self) -> Status | None:  # None = not connected
        ...

    def print(self, images: list[Image.Image], opts: JobOptions) -> str:  # human-readable job result
        ...


class MockBackend:
    """Default. Same job bytes as UsbBackend, written to <out_dir>/<timestamp>.bin next to a strip preview .png."""

    def __init__(self, printer: Printer, out_dir: str | Path, tape_mm: int = 9):
        self.printer, self.out_dir, self.tape_mm = printer, Path(out_dir), tape_mm

    def status(self) -> Status:
        raw = bytearray(32)
        raw[0], raw[1], raw[4], raw[10], raw[11] = 0x80, 0x20, ord("?"), self.tape_mm, 0x01
        return parse_status(bytes(raw))

    def print(self, images: list[Image.Image], opts: JobOptions = JobOptions()) -> str:
        job = build_job(self.printer, self.tape_mm, images, opts)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        stem = self.out_dir / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        stem.with_suffix(".bin").write_bytes(job)
        png = stem.with_suffix(".png")
        strip_preview(images, opts.margin_dots).save(png)
        return f"mock: {len(images)} label(s), {len(job)} job bytes -> {png}"


def _usb():
    import usb.core
    import usb.util

    kw = {}
    try:  # Windows has no system libusb; the libusb-package wheel bundles one
        import libusb_package

        kw["backend"] = libusb_package.get_libusb1_backend()
    except ImportError:
        pass
    return usb, kw


def probe() -> list[Printer]:
    """Supported printers currently on the bus."""
    usb, kw = _usb()
    found = usb.core.find(find_all=True, idVendor=USB_VID, **kw)
    return [BY_PID[d.idProduct] for d in found if d.idProduct in BY_PID]


class UsbBackend:
    def __init__(self, printer: Printer, timeout_s: float = 60.0):
        self.printer, self.timeout_s = printer, timeout_s
        self._lock = threading.Lock()  # WinUSB allows one open handle: status polls must not overlap a print
        self._last: Status | None = None
        self._rx = bytearray()
        self.busy = False

    def _open(self):
        usb, kw = _usb()
        dev = usb.core.find(idVendor=USB_VID, idProduct=self.printer.usb_pid, **kw)
        if dev is None:
            return None
        try:
            if dev.is_kernel_driver_active(0):
                dev.detach_kernel_driver(0)
        except (NotImplementedError, usb.core.USBError):
            pass
        try:
            dev.set_configuration()
        except usb.core.USBError:
            pass
        intf = dev.get_active_configuration()[(0, 0)]
        is_out = lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT
        ep_out = usb.util.find_descriptor(intf, custom_match=is_out)
        ep_in = usb.util.find_descriptor(intf, custom_match=lambda e: not is_out(e))
        return usb, dev, ep_out, ep_in

    def _read_status(self, usb, ep_in, timeout_s: float) -> Status | None:
        """Next 32-byte status packet, or None. WinUSB returns 0-byte reads, and can return two
        packets in one 64-byte read, so bytes are accumulated and consumed 32 at a time."""
        deadline = time.monotonic() + timeout_s
        while True:
            if len(self._rx) >= 32:
                pkt, self._rx = bytes(self._rx[:32]), self._rx[32:]
                if pkt[:2] == b"\x80\x20":
                    return parse_status(pkt)
                log.warning("dropping non-status bytes: %s", pkt.hex(" "))
                continue
            if time.monotonic() >= deadline:
                return None
            try:
                self._rx += bytes(ep_in.read(64, timeout=500))
            except usb.core.USBTimeoutError:
                continue

    def _drain(self, usb, ep_in):
        """Discard status packets a previous, interrupted client left queued."""
        while self._read_status(usb, ep_in, 0.3) is not None:
            pass

    def status(self) -> Status | None:
        if not self._lock.acquire(timeout=1.0):
            return self._last  # a print is running; report what we knew
        try:
            h = self._open()
            if h is None:
                self._last = None
                return None
            usb, dev, out, inp = h
            try:
                self._drain(usb, inp)
                out.write(INVALIDATE + INITIALIZE + STATUS_REQUEST)
                st = self._read_status(usb, inp, 3.0)
                if st is None:
                    raise RuntimeError(f"{self.printer.model}: no status reply")
                self._last = st
                return st
            finally:
                usb.util.dispose_resources(dev)
        finally:
            self._lock.release()

    def print(self, images: list[Image.Image], opts: JobOptions = JobOptions()) -> str:
        with self._lock:
            self.busy = True
            try:
                return self._print(images, opts)
            finally:
                self.busy = False

    def _print(self, images: list[Image.Image], opts: JobOptions) -> str:
        h = self._open()
        if h is None:
            raise RuntimeError(f"{self.printer.model} not connected")
        usb, dev, out, inp = h
        try:
            self._drain(usb, inp)
            out.write(INVALIDATE + INITIALIZE + STATUS_REQUEST)
            st = self._read_status(usb, inp, 3.0)
            if st is None:
                raise RuntimeError(f"{self.printer.model}: no status reply")
            if st.errors:
                raise RuntimeError("printer error: " + ", ".join(st.errors))
            if st.width_mm == 0:
                raise RuntimeError("no tape loaded")
            jobs = build_jobs(self.printer, st.width_mm, images, opts, self.printer.max_job_bytes)
            log.info("batch: %d labels, %d bytes in %d job(s), options %s", len(images), sum(map(len, jobs)), len(jobs), opts)
            dpi_x = self.printer.hires_dpi if opts.hires else self.printer.dpi
            mm_per_page = [(im.width + 2 * opts.margin_dots) * 25.4 / dpi_x for im in images]
            # One write per job. The printer NAKs the OUT pipe while it prints, so a multi-page write blocks
            # until the printer has room; the timeout must cover the whole job's print time.
            # ponytail: a 6-label, 64 KB job once came out as 1 good label + blanks; if that repeats,
            # Printer.max_job_bytes splits the batch (full cut at each split), see printers.py.
            k = 0
            for j, job in enumerate(jobs):
                n = job.count(b"\x1bia\x01")
                mm = sum(mm_per_page[k : k + n]) + self.printer.min_feed_mm
                k += n
                t = time.monotonic()
                out.write(job, timeout=int(1000 * (self.timeout_s + 0.2 * mm + 5 * n)))
                log.info("job %d/%d: %d labels, %d bytes, write took %.1f s", j + 1, len(jobs), n, len(job), time.monotonic() - t)
                self._wait_done(usb, inp, out, 3.0 + 0.1 * mm)
                log.info("job %d/%d printed, %.0f mm in %.1f s", j + 1, len(jobs), mm, time.monotonic() - t)
            return f"printed {len(images)} label(s) on {st.width_mm} mm tape"
        finally:
            usb.util.dispose_resources(dev)

    def _wait_done(self, usb, inp, out, estimate: float) -> None:
        """Block until the page is printed. E550W-family printers report "printing completed". The E560BT
        sends nothing and NAKs the OUT pipe while printing, so we keep offering ESC i S (1 s timeout each);
        the first one it accepts is answered idle, within about a second of the cutter stopping."""
        t0 = time.monotonic()
        deadline = t0 + self.timeout_s + estimate
        settle = 1.5  # ponytail: an idle answer sooner than this is the printer still parsing the page, not done
        while time.monotonic() < deadline:
            s = self._read_status(usb, inp, 0.3)
            if s is not None:
                log.info("status: type=%#04x phase=%#04x err=%#04x/%#04x raw=%s", s.status_type, s.phase_type, s.err1, s.err2, s.raw.hex(" "))
                if s.status_type == STATUS_ERROR or s.errors:
                    raise RuntimeError("printer error: " + (", ".join(s.errors) or s.raw.hex(" ")))
                if s.status_type == STATUS_COMPLETED or (s.status_type == 0 and s.phase_type == 0 and time.monotonic() - t0 >= settle):
                    self._last = s
                    return
                continue
            try:
                out.write(STATUS_REQUEST, timeout=1000)
            except usb.core.USBTimeoutError:
                continue  # OUT pipe busy: still printing
        raise TimeoutError(f"printer did not report idle within {deadline - t0:.0f} s")
