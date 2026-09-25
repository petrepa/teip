from PIL import Image
import pytest

from teip.printers import PRINTERS, dots
from teip.render import Design, gridfinity_length_mm, render, strip_preview

E560 = PRINTERS["PT-E560BT"]
P950 = PRINTERS["PT-P950NW"]


@pytest.mark.parametrize(
    "printer,tape,length,expected",
    [
        (E560, 9, 37, (262, 50)),
        (E560, 12, 37, (262, 70)),
        (E560, 24, 37, (262, 128)),
        (E560, 4, 20, (142, 24)),
        (E560, 18, 100, (709, 112)),
        (P950, 9, 37, (524, 106)),
        (P950, 36, 37, (524, 454)),
    ],
)
def test_exact_dimensions(printer, tape, length, expected):
    im = render(Design(tape_mm=tape, length_mm=length, lines=("M3x8", "SHCS")), printer)
    assert im.size == expected and im.mode == "1"


def test_hires_doubles_length_only():
    im = render(Design(tape_mm=9, length_mm=37, lines=("x",), hires=True), E560)
    assert im.size == (524, 50)
    with pytest.raises(ValueError):
        render(Design(tape_mm=9, length_mm=37, hires=True), PRINTERS["PT-P910BT"])


def test_auto_length_fits_content_inside_margins():
    im = render(Design(tape_mm=9, lines=("M3x8",), margin_mm=1.0), E560)
    pad = dots(1.0, 180)
    assert im.height == 50 and im.width > 2 * pad
    px = im.load()
    assert all(px[x, y] == 1 for x in range(im.width) for y in list(range(pad)) + list(range(50 - pad, 50)))
    assert any(px[x, y] == 0 for x in range(im.width) for y in range(50))


def test_two_lines_bigger_than_one_line_font():
    one = render(Design(tape_mm=9, lines=("Wide",)), E560)
    two = render(Design(tape_mm=9, lines=("Wide", "Wide")), E560)
    assert one.width > two.width  # auto font shrinks for two lines


def test_fixed_length_shrinks_text_to_fit():
    im = render(Design(tape_mm=9, length_mm=15, lines=("A rather long label text",)), E560)
    assert im.width == dots(15, 180)


def icon_file(tmp_path, size=40):
    p = tmp_path / "icon.png"
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    for x in range(4, size - 4):
        for y in range(4, size - 4):
            im.putpixel((x, y), (0, 0, 0, 255))
    im.save(p)
    return str(p)


def test_icon_side_layout(tmp_path):
    im = render(Design(tape_mm=9, length_mm=37, lines=("M3",), icons=(icon_file(tmp_path),), margin_mm=0.6), E560)
    pad = dots(0.6, 180)
    px = im.load()
    assert im.size == (262, 50)
    # icon fills the inner height on the left, crop to content, so the column just right of pad is black
    assert px[pad, 25] == 0 and px[pad, pad] == 0 and px[pad, 49 - pad] == 0
    assert px[pad - 1, 25] == 1


def test_icon_stacked_layout(tmp_path):
    im = render(Design(tape_mm=24, length_mm=30, lines=("M3",), icons=(icon_file(tmp_path),), layout="stacked"), E560)
    assert im.size == (213, 128)
    px = im.load()
    top = [y for y in range(128) if any(px[x, y] == 0 for x in range(213))]
    assert top[0] < 10 and top[-1] > 70


def test_svg_rejected(tmp_path):
    (tmp_path / "i.svg").write_text("<svg/>")
    with pytest.raises(ValueError):
        render(Design(tape_mm=9, icons=(str(tmp_path / "i.svg"),)), E560)


def test_gridfinity_lengths():
    assert [gridfinity_length_mm(u) for u in (1, 2, 3)] == [37.0, 79.0, 121.0]
    assert gridfinity_length_mm(2, base_mm=36.0) == 78.0


def test_strip_preview_geometry():
    ims = [Image.new("1", (100, 50), 1), Image.new("1", (60, 50), 1)]
    s = strip_preview(ims, 14)
    assert s.size == (100 + 60 + 4 * 14, 50)
    assert s.getpixel((100 + 28 - 1, 0)) == 0  # dotted cut line at the boundary


def test_two_icons_side_by_side(tmp_path):
    one = render(Design(tape_mm=9, lines=("M3",), icons=(icon_file(tmp_path),)), E560)
    two = render(Design(tape_mm=9, lines=("M3",), icons=(icon_file(tmp_path), icon_file(tmp_path))), E560)
    pad, gap = dots(0.6, 180), dots(0.8, 180)
    assert two.width == one.width + (50 - 2 * pad) + gap  # square icon fills inner height


def test_second_line_is_subtitle():
    im = render(Design(tape_mm=9, length_mm=40, lines=("M3×8", "DIN 912")), E560)
    px = im.load()
    rows = [y for y in range(50) if any(px[x, y] == 0 for x in range(im.width))]
    gaps = [y for y in range(rows[0], rows[-1]) if y not in rows]
    assert gaps, "expected a blank row between title and subtitle"
    title = gaps[0] - rows[0]
    subtitle = rows[-1] - gaps[-1]
    assert title > subtitle * 1.3


def test_icon_rotation_suffix(tmp_path):
    p = tmp_path / "tall.png"
    Image.new("RGBA", (10, 30), (0, 0, 0, 255)).save(p)
    from teip.render import load_icon
    assert load_icon(p).size == (10, 30) and load_icon(f"{p}@90").size == (30, 10)
