"""Draw the built-in icon set: clean silhouettes in the style of 3D-printed bin labels.

Heads and rivets are side profiles, head on the left, shank/body to the right. Drives, nuts and
washers are top views. Everything is plain geometry drawn here, black on transparent, 256 px.
Run:  python icons/generate.py
"""

import math
from pathlib import Path

from PIL import Image, ImageDraw

S = 256
OUT = Path(__file__).resolve().parent


def canvas():
    im = Image.new("LA", (S * 4, S * 4), (0, 0))  # 4x supersampled, downscaled at save
    return im, ImageDraw.Draw(im)


def save(im, folder, name):
    im = im.resize((S, S), Image.LANCZOS)
    rgba = Image.new("RGBA", im.size, (0, 0, 0, 0))
    rgba.putalpha(im.getchannel("A"))
    (OUT / folder).mkdir(parents=True, exist_ok=True)
    rgba.save(OUT / folder / f"{name}.png")


def poly(d, pts, on=True):
    d.polygon([(x * 4, y * 4) for x, y in pts], fill=(0, 255) if on else (0, 0))


def rect(d, x0, y0, x1, y1, on=True, r=0):
    d.rounded_rectangle((x0 * 4, y0 * 4, x1 * 4, y1 * 4), radius=r * 4, fill=(0, 255) if on else (0, 0))


def ellipse(d, x0, y0, x1, y1, on=True):
    d.ellipse((x0 * 4, y0 * 4, x1 * 4, y1 * 4), fill=(0, 255) if on else (0, 0))


def ngon(d, cx, cy, r, n, rot=0.0, on=True):
    poly(d, [(cx + r * math.cos(rot + 2 * math.pi * i / n), cy + r * math.sin(rot + 2 * math.pi * i / n)) for i in range(n)], on)


# ---- heads: side view, head left, shank right. Centre line y=128 ---------------------------
CY, SHANK_H, HEAD_H = 128, 56, 150
X_END = 250


def shank(d, x0, h=SHANK_H, x1=X_END):
    rect(d, x0, CY - h / 2, x1, CY + h / 2)


def wood_shank(d, x0):
    """Tapered, pointed, with thread ridges."""
    poly(d, [(x0, CY - 34), (200, CY - 22), (X_END, CY), (200, CY + 22), (x0, CY + 34)])
    for x in range(x0 + 14, 200, 22):
        poly(d, [(x, CY - 34 - 12), (x + 9, CY - 34 - 12), (x + 22, CY + 34 + 12), (x + 13, CY + 34 + 12)])


def head_countersunk(d):
    poly(d, [(6, CY - HEAD_H / 2), (22, CY - HEAD_H / 2), (72, CY - SHANK_H / 2), (72, CY + SHANK_H / 2), (22, CY + HEAD_H / 2), (6, CY + HEAD_H / 2)])
    return 72


def head_socket_cap(d):
    rect(d, 6, CY - HEAD_H / 2, 80, CY + HEAD_H / 2, r=10)
    return 80


def head_cheese(d):
    rect(d, 6, CY - 62, 62, CY + 62, r=6)
    rect(d, 6, CY - 9, 30, CY + 9, on=False)  # slot
    return 62


def head_button(d):
    ellipse(d, 76 - 66, CY - HEAD_H / 2, 76 + 66, CY + HEAD_H / 2)  # dome bulges left, flat underside right
    rect(d, 76, 0, S, S, on=False)
    return 76


def head_pan(d):
    rect(d, 6, CY - HEAD_H / 2, 62, CY + HEAD_H / 2, r=26)
    rect(d, 40, CY - HEAD_H / 2, 62, CY + HEAD_H / 2)
    return 62


def head_flange_pan(d):
    x = head_pan(d)
    rect(d, x, CY - 100, x + 14, CY + 100)
    return x + 14


def head_hex(d):
    rect(d, 6, CY - HEAD_H / 2, 76, CY + HEAD_H / 2)
    rect(d, 6, CY - 27, 76, CY - 21, on=False)  # facet lines
    rect(d, 6, CY + 21, 76, CY + 27, on=False)
    return 76


def head_flange_hex(d):
    x = head_hex(d)
    rect(d, x, CY - 100, x + 14, CY + 100)
    return x + 14


def head_truss(d):
    ellipse(d, 56 - 48, CY - 100, 56 + 48, CY + 100)
    rect(d, 56, 0, S, S, on=False)
    return 56


def head_wafer(d):
    rect(d, 6, CY - 100, 34, CY + 100, r=6)
    return 34


def head_shoulder(d):
    rect(d, 6, CY - HEAD_H / 2, 66, CY + HEAD_H / 2, r=8)
    rect(d, 66, CY - 48, 170, CY + 48)
    return 170


HEADS = {
    "countersunk": (head_countersunk, shank),
    "socket-cap": (head_socket_cap, shank),
    "button": (head_button, shank),
    "pan": (head_pan, shank),
    "flange-pan": (head_flange_pan, shank),
    "cheese": (head_cheese, shank),
    "hex": (head_hex, shank),
    "flange-hex": (head_flange_hex, shank),
    "shoulder": (head_shoulder, shank),
    "truss": (head_truss, shank),
    "wafer": (head_wafer, shank),
    "wood-countersunk": (head_countersunk, wood_shank),
    "wood-pan": (head_pan, wood_shank),
    "wood-hex": (head_hex, wood_shank),
}


def gen_heads():
    for name, (head, sh) in HEADS.items():
        im, d = canvas()
        x = head(d)
        sh(d, x)
        save(im, "head", name)
    im, d = canvas()  # set screw: plain shank with a socket cut into the left end
    rect(d, 20, CY - 40, 236, CY + 40, r=4)
    ngon(d, 44, CY, 22, 6, on=False)
    save(im, "head", "set-screw")


# ---- drives: top view in a ring -----------------------------------------------------------
C = 128


def ring(d, r_out=118, w=20):
    ellipse(d, C - r_out, C - r_out, C + r_out, C + r_out)
    ellipse(d, C - r_out + w, C - r_out + w, C + r_out - w, C + r_out - w, on=False)


def bar(d, w, h, angle=0.0, on=True):
    a = math.radians(angle)
    pts = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
    poly(d, [(C + x * math.cos(a) - y * math.sin(a), C + x * math.sin(a) + y * math.cos(a)) for x, y in pts], on)


def torx(d, on=True):
    ellipse(d, C - 40, C - 40, C + 40, C + 40, on)
    for i in range(6):
        a = 2 * math.pi * i / 6
        x, y = C + 46 * math.cos(a), C + 46 * math.sin(a)
        ellipse(d, x - 22, y - 22, x + 22, y + 22, on)
    for i in range(6):  # scallops between lobes
        a = 2 * math.pi * (i + 0.5) / 6
        x, y = C + 62 * math.cos(a), C + 62 * math.sin(a)
        ellipse(d, x - 16, y - 16, x + 16, y + 16, not on)


DRIVES = {
    "hex-socket": lambda d: (ring(d), ngon(d, C, C, 62, 6)),
    "torx": lambda d: (ring(d), torx(d)),
    "torx-security": lambda d: (ring(d), torx(d), ellipse(d, C - 13, C - 13, C + 13, C + 13, on=False)),
    "phillips": lambda d: (ring(d), bar(d, 130, 30), bar(d, 30, 130)),
    "pozidriv": lambda d: (ring(d), bar(d, 130, 30), bar(d, 30, 130), bar(d, 120, 10, 45), bar(d, 120, 10, -45)),
    "robertson": lambda d: (ring(d), rect(d, C - 42, C - 42, C + 42, C + 42)),
    "slotted": lambda d: (ring(d), bar(d, 136, 28)),
    "hex-external": lambda d: (ngon(d, C, C, 118, 6, math.pi / 6), ngon(d, C, C, 78, 6, math.pi / 6, on=False)),
    "hex-flange": lambda d: (ring(d), ngon(d, C, C, 74, 6, math.pi / 6)),
    "square-external": lambda d: (rect(d, C - 100, C - 100, C + 100, C + 100, r=10), rect(d, C - 64, C - 64, C + 64, C + 64, on=False, r=6)),
}


def gen_drives():
    for name, fn in DRIVES.items():
        im, d = canvas()
        fn(d)
        save(im, "drive", name)


# ---- nuts and washers: top view ------------------------------------------------------------
def nut_hex(d, r=118, hole=46):
    ngon(d, C, C, r, 6, math.pi / 6)
    ellipse(d, C - hole, C - hole, C + hole, C + hole, on=False)


def teeth(d, r0, r1, n=12, on=True):
    for i in range(n):
        a = 2 * math.pi * i / n
        da = math.pi / n * 0.55
        poly(d, [(C + r0 * math.cos(a - da), C + r0 * math.sin(a - da)), (C + r1 * math.cos(a), C + r1 * math.sin(a)), (C + r0 * math.cos(a + da), C + r0 * math.sin(a + da))], on)


NUTS = {
    "hex": lambda d: nut_hex(d),
    "nyloc": lambda d: (nut_hex(d), ellipse(d, C - 70, C - 70, C + 70, C + 70, on=False), ellipse(d, C - 62, C - 62, C + 62, C + 62), ellipse(d, C - 46, C - 46, C + 46, C + 46, on=False)),
    "cap": lambda d: (ngon(d, C, C, 118, 6, math.pi / 6), ellipse(d, C - 76, C - 76, C + 76, C + 76, on=False), ellipse(d, C - 58, C - 58, C + 58, C + 58)),
    "square": lambda d: (rect(d, C - 104, C - 104, C + 104, C + 104, r=8), ellipse(d, C - 46, C - 46, C + 46, C + 46, on=False)),
    "flange": lambda d: (ring(d, 122, 16), nut_hex(d, 96, 42)),
    "wing": lambda d: (nut_hex(d, 70, 30), poly(d, [(C - 62, C - 20), (C - 122, C - 70), (C - 122, C + 10), (C - 62, C + 20)]), poly(d, [(C + 62, C - 20), (C + 122, C - 70), (C + 122, C + 10), (C + 62, C + 20)])),
}
WASHERS = {
    "flat": lambda d: ring(d, 118, 60),
    "fender": lambda d: ring(d, 122, 88),
    "split": lambda d: (ring(d, 118, 56), poly(d, [(C, C), (C + 140, C - 34), (C + 140, C + 10)], on=False), poly(d, [(C + 70, C + 6), (C + 130, C - 8), (C + 130, C + 30), (C + 70, C + 44)])),
    "tooth-external": lambda d: (ring(d, 96, 46), teeth(d, 92, 122)),
    "tooth-internal": lambda d: (ring(d, 118, 40), teeth(d, 80, 42)),
}


def gen_nuts():
    for folder, table in (("nuts", NUTS), ("washers", WASHERS)):
        for name, fn in table.items():
            im, d = canvas()
            fn(d)
            save(im, folder, name)


# ---- blind rivets and rivet nuts: side view. Mandrel stem out through the head to the left, hollow
# ---- body to the right, mandrel head at the blind end. Rivet nut: flange left, threaded bore -----
RX = 100  # x where the head's underside meets the body


def rivet(d, head):
    rect(d, 6, CY - 11, RX, CY + 11)  # mandrel stem
    head(d)
    rect(d, RX, CY - 30, 220, CY + 30)  # body
    ellipse(d, 250 - 68, CY - 35, 250, CY + 35)  # mandrel head


def rhead_dome(d):
    ellipse(d, RX - 36, CY - 62, RX + 36, CY + 62)
    rect(d, RX, 0, S, S, on=False)


def rhead_countersunk(d):  # 120 degree
    poly(d, [(RX - 28, CY - 64), (RX - 19, CY - 64), (RX, CY - 31), (RX, CY + 31), (RX - 19, CY + 64), (RX - 28, CY + 64)])


def rhead_large_flange(d):
    ellipse(d, RX - 44, CY - 54, RX, CY + 54)  # shallow dome on a wide thin flange
    rect(d, RX - 22, 0, S, S, on=False)
    rect(d, RX - 22, CY - 104, RX, CY + 104, r=6)


def rivet_nut(d):
    rect(d, 6, CY - 66, 26, CY + 66, r=5)  # flange
    rect(d, 26, CY - 42, 250, CY + 42, r=8)  # body
    rect(d, 6, CY - 16, 236, CY + 16, on=False)  # threaded bore
    for x in range(34, 230, 26):
        rect(d, x, CY - 16, x + 11, CY + 16)


RIVETS = {
    "dome": lambda d: rivet(d, rhead_dome),
    "countersunk": lambda d: rivet(d, rhead_countersunk),
    "large-flange": lambda d: rivet(d, rhead_large_flange),
    "nut": rivet_nut,
}


def gen_rivets():
    for name, fn in RIVETS.items():
        im, d = canvas()
        fn(d)
        save(im, "rivets", name)


if __name__ == "__main__":
    gen_heads()
    gen_drives()
    gen_nuts()
    gen_rivets()
    print("icons written to", OUT)
