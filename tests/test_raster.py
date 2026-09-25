from PIL import Image
import pytest

from teip.printers import PRINTERS
from teip.raster import INITIALIZE, INVALIDATE, JobOptions, build_job, build_jobs, packbits, parse_status, raster_lines

E560 = PRINTERS["PT-E560BT"]
E550 = PRINTERS["PT-E550W"]
P950 = PRINTERS["PT-P950NW"]


def unpack(data: bytes) -> bytes:
    out, i = bytearray(), 0
    while i < len(data):
        n = data[i]
        if n < 128:
            out += data[i + 1 : i + 2 + n]
            i += 2 + n
        else:
            out += bytes([data[i + 1]]) * (257 - n)
            i += 2
    return bytes(out)


def test_packbits_spec_example():
    raw = bytes(20) + b"\x22\x22" + bytes.fromhex("23 BA BF A2 22 2B")
    assert packbits(raw) == bytes.fromhex("ED 00 FF 22 05 23 BA BF A2 22 2B")


def test_packbits_roundtrip():
    import random

    rng = random.Random(1)
    for _ in range(200):
        raw = bytes(rng.choice([0, 0, 0, 255, rng.randrange(256)]) for _ in range(rng.randrange(1, 300)))
        assert unpack(packbits(raw)) == raw


def dot(printer, width_mm, x, y, w=3):
    pins = printer.tape(width_mm)
    im = Image.new("1", (w, pins.print), 1)
    im.putpixel((x, y), 0)
    return im


def test_raster_line_bit_positions_e560_9mm():
    lines = raster_lines(dot(E560, 9, 1, 0), E560, E560.tape(9))
    assert len(lines) == 3 and all(len(l) == 16 for l in lines)
    assert lines[0] == bytes(16) and lines[2] == bytes(16)
    assert lines[1][4] == 0x01 and sum(lines[1]) == 1  # left 39 pins -> bit index 39 -> byte 4, LSB
    last = raster_lines(dot(E560, 9, 0, 49, 1), E560, E560.tape(9))[0]
    assert last[11] == 0x80 and sum(last) == 0x80  # index 88 -> byte 11, MSB


def test_raster_line_p950_24mm_offcentre():
    line = raster_lines(dot(P950, 24, 0, 0, 1), P950, P950.tape(24))[0]
    assert len(line) == 70 and line[14] == 0x80 and sum(line) == 0x80  # left 112 -> byte 14 MSB


def test_raster_rejects_wrong_height():
    with pytest.raises(ValueError):
        raster_lines(Image.new("1", (5, 49), 1), E560, E560.tape(9))


def blank(printer, width_mm, w):
    return Image.new("1", (w, printer.tape(width_mm).print), 1)


def test_single_label_job_structure():
    job = build_job(E550, 9, [blank(E560, 9, 10)])
    assert job.startswith(INVALIDATE + INITIALIZE + b"\x1bia\x01")
    assert job.endswith(b"\x1a") and b"\x0c" not in job
    i = job.index(b"\x1biz")
    assert job[i + 3 : i + 13] == bytes([0x86, 0x01, 9, 0, 10, 0, 0, 0, 0, 0])
    assert b"\x1biM\x40" in job and b"\x1biA\x01" in job  # single label: auto cut
    assert b"\x1biK\x08" in job  # no half cut, no chain
    assert b"\x1bid\x0e\x00" in job and b"M\x02" in job
    assert job.count(b"Z") == 10  # blank columns compress to Z


def test_batch_half_cut_job():
    job = build_job(E550, 12, [blank(E560, 12, 4)] * 3, JobOptions(margin_dots=20))
    pages = job.split(b"\x1bia\x01")[1:]
    assert [p[-1] for p in pages] == [0x0C, 0x0C, 0x1A]  # FF, FF, ^Z
    assert b"\x1biM\x00" in job and b"\x1biM\x40" not in job  # auto cut off
    assert b"\x1biK\x0c" in job  # half cut + no chain
    assert b"\x1bid\x14\x00" in job
    pages = job.split(b"\x1biz")[1:]
    assert [p[8] for p in pages] == [0, 1, 1]  # n9: first page 0, others 1


def test_uncompressed_and_hires():
    job = build_job(E560, 9, [blank(E560, 9, 2)], JobOptions(hires=True, margin_dots=28))  # E560BT default: raw
    assert b"M\x00" in job and b"Z" not in job and job.count(b"G\x10\x00" + bytes(16)) == 2
    assert b"\x1biK\x4c" in job  # hires bit 6 + half cut + no chain


def test_e560bt_family_sequence():
    (job,) = build_jobs(E560, 9, [blank(E560, 9, 3)] * 2)
    assert job.startswith(INVALIDATE + INITIALIZE) and job.count(INITIALIZE) == 1  # one job, pages chained inside it
    pages = job.split(b"\x1bia\x01")[1:]
    assert len(pages) == 2 and all(p[-1] == 0x1A for p in pages)  # ^Z on every page, never FF
    assert job.count(b"\x1biM\x40") == 1 and job.index(b"\x1biM\x40") < job.index(b"\x1a") and b"\x1biA" not in job  # leader cut once
    for p, k in zip(pages, (0x04, 0x0C)):  # first: half cut + chain; last: half cut + no chain
        assert p[:3] == b"\x1biz" and p[3:5] == b"\x00\x00" and p[5] == 9 and p[7:11] == (3).to_bytes(4, "little")
        assert p[11] == 2, "n9 must be 2 on this family"
        assert b"\x1biK" + bytes([k]) in p
    single = build_job(E560, 9, [blank(E560, 9, 3)])
    assert b"\x1biK\x0c" in single and single.endswith(b"\x1a")  # half-cut bit on: leading cut becomes a half cut


def test_jobs_split_by_size():
    ims = [blank(E560, 9, 100)] * 3
    one = len(build_jobs(E560, 9, ims[:1])[0])
    jobs = build_jobs(E560, 9, ims, max_bytes=one + 10)  # room for one page per job
    assert len(jobs) == 3 and all(j.startswith(INVALIDATE + INITIALIZE) and b"\x1biK\x0c" in j for j in jobs)  # each ends feed + full cut
    assert [j.count(b"\x1biM\x40") for j in jobs] == [1, 1, 1]
    jobs = build_jobs(E560, 9, ims, JobOptions(chain=True), max_bytes=2 * one + 10)
    assert len(jobs) == 2 and b"\x1biK\x0c" in jobs[0] and b"\x1biK\x04" in jobs[1] and b"\x1biK\x0c" not in jobs[1]  # only the last label held


def test_compression_follows_printer_table():
    assert b"M\x02" in build_job(PRINTERS["PT-E550W"], 9, [blank(E560, 9, 2)])
    assert b"M\x00" in build_job(E560, 9, [blank(E560, 9, 2)])


def test_job_validation():
    with pytest.raises(ValueError):
        build_job(PRINTERS["PT-P710BT"], 9, [blank(E560, 9, 2)] * 2)  # no half cutter
    with pytest.raises(ValueError):
        build_job(E560, 9, [blank(E560, 9, 2)], JobOptions(margin_dots=5))
    with pytest.raises(ValueError):
        build_job(PRINTERS["PT-P910BT"], 9, [blank(P950, 9, 2)], JobOptions(hires=True, margin_dots=28))
    with pytest.raises(ValueError):
        build_job(E560, 21, [blank(E560, 9, 2)])


def test_parse_status():
    raw = bytearray(32)
    raw[0], raw[1], raw[4], raw[8], raw[9], raw[10], raw[11] = 0x80, 0x20, ord("f"), 0x08, 0x10, 12, 0x01
    st = parse_status(bytes(raw))
    assert (st.model_code, st.width_mm, st.media) == ("f", 12, "laminated")
    assert st.errors == ["weak batteries", "cover open"]
    with pytest.raises(ValueError):
        parse_status(bytes(31))


def test_chain_leaves_last_label_inside():
    job = build_job(E560, 9, [blank(E560, 9, 3)] * 2, JobOptions(chain=True))
    pages = job.split(b"\x1bia\x01")[1:]
    assert b"\x1biK\x04" in pages[0] and b"\x1biK\x04" in pages[1]  # no-chain bit never set
    job = build_job(E550, 9, [blank(E560, 9, 3)], JobOptions(chain=True))
    assert b"\x1biK\x00" in job
