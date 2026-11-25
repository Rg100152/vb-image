"""Regenerate docs/logo.png and docs/banner.png (requires Pillow + DejaVu fonts)."""
from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
DOCS.mkdir(exist_ok=True)

BOLD = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
REG = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


def font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def radial_gradient(size: tuple[int, int], center: tuple[float, float], inner, outer, radius: float):
    w, h = size
    img = Image.new("RGBA", size)
    px = img.load()
    cx, cy = center
    for y in range(h):
        for x in range(w):
            d = math.hypot(x - cx, y - cy) / radius
            d = min(d, 1.0)
            c = mix(inner, outer, d)
            px[x, y] = (*c, 255)
    return img


def rounded_mask(size, radius, box):
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(box, radius=radius, fill=255)
    return mask


def polar(cx, cy, r, angle):
    return (cx + r * math.cos(angle), cy + r * math.sin(angle))


def spacing(draw, xy, text, fnt, fill, gap=4):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=fnt, fill=fill)
        x += draw.textlength(ch, font=fnt) + gap


# --------------------------------------------------------------------------- #
# Logo
# --------------------------------------------------------------------------- #

def build_logo():
    S = 640
    cx = cy = S // 2
    canvas = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    bg = Image.new("RGBA", (S, S))
    bg_px = bg.load()
    for y in range(S):
        for x in range(S):
            t = (x + y) / (2 * S)
            c = mix((16, 25, 43), (8, 12, 22), t)
            bg_px[x, y] = (*c, 255)
    glow = radial_gradient((S, S), (cx, cy), (34, 70, 95), (8, 12, 22), 360)
    bg = Image.blend(bg, glow, 0.45)
    canvas.paste(bg, (0, 0), rounded_mask((S, S), 132, (22, 22, S - 22, S - 22)))

    # Soft aperture glow
    glow_layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow_layer)
    for i in range(6):
        a0 = math.radians(i * 60 - 90)
        a1 = math.radians(i * 60 - 30)
        pts = [polar(cx, cy, 60, a0), polar(cx, cy, 205, a0 + 0.22),
               polar(cx, cy, 205, a1 - 0.06), polar(cx, cy, 60, a1 - 0.10)]
        color = i / 5
        gd.polygon(pts, fill=(*mix((34, 211, 238), (167, 139, 250), color), 190))
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(28))
    canvas.alpha_composite(glow_layer)

    # Crisp blades
    blades = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    bd = ImageDraw.Draw(blades)
    for i in range(6):
        a0 = math.radians(i * 60 - 90)
        a1 = math.radians(i * 60 - 30)
        pts = [polar(cx, cy, 78, a0), polar(cx, cy, 188, a0 + 0.20),
               polar(cx, cy, 188, a1 - 0.07), polar(cx, cy, 78, a1 - 0.11)]
        color = i / 5
        bd.polygon(pts, fill=(*mix((34, 211, 238), (167, 139, 250), color), 235))
        bd.line(pts + [pts[0]], fill=(230, 245, 255, 120), width=2, joint="curve")
    canvas.alpha_composite(blades)

    d = ImageDraw.Draw(canvas)
    d.ellipse((cx - 66, cy - 66, cx + 66, cy + 66), fill=(10, 16, 28, 245))
    d.ellipse((cx - 66, cy - 66, cx + 66, cy + 66), outline=(34, 211, 238, 180), width=3)
    for r, col, w in ((215, (34, 211, 238, 130), 2), (238, (167, 139, 250, 95), 2), (258, (148, 163, 184, 55), 1)):
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=col, width=w)

    # Subtle sparkles
    rnd = random.Random(7)
    for _ in range(45):
        x, y = rnd.randrange(40, S - 40), rnd.randrange(40, S - 40)
        if math.hypot(x - cx, y - cy) < 270:
            continue
        d.ellipse((x, y, x + 2, y + 2), fill=(165, 243, 252, rnd.randrange(60, 160)))

    # Wordmark
    f_big = font(BOLD, 132)
    label = "VB"
    box = d.textbbox((0, 0), label, font=f_big)
    d.text((cx - (box[2] - box[0]) / 2 - box[0], cy - (box[3] - box[1]) / 2 - box[1] - 6),
           label, font=f_big, fill=(245, 250, 255, 255))
    f_small = font(BOLD, 21)
    spacing(d, (cx - 104, cy + 112), "IMAGE AI STUDIO", f_small, (165, 243, 252, 230), gap=3)

    path = DOCS / "logo.png"
    canvas.save(path)
    print("wrote", path)


# --------------------------------------------------------------------------- #
# Banner
# --------------------------------------------------------------------------- #

def cubic(p0, p1, p2, p3, steps=160):
    points = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        x = u**3 * p0[0] + 3 * u*u*t * p1[0] + 3 * u*t*t * p2[0] + t**3 * p3[0]
        y = u**3 * p0[1] + 3 * u*u*t * p1[1] + 3 * u*t*t * p2[1] + t**3 * p3[1]
        points.append((x, y))
    return points


def build_banner():
    W, H = 1600, 420
    img = Image.new("RGBA", (W, H))
    px = img.load()
    for y in range(H):
        for x in range(W):
            t = (x / W) * 0.55 + (y / H) * 0.45
            c = mix((13, 19, 32), (9, 13, 23), t)
            px[x, y] = (*c, 255)

    # Ambient colour glows
    for cx, cy, color, radius in ((210, 210, (34, 150, 180), 360), (1400, 200, (120, 90, 210), 380)):
        glow = radial_gradient((W, H), (cx, cy), color, (10, 14, 24), radius).convert("RGBA")
        glow.putalpha(glow.getchannel("R").point(lambda v: max(0, min(70, int((v - 10) * 0.4)))))
        img.alpha_composite(glow)

    # Grid
    d = ImageDraw.Draw(img, "RGBA")
    for x in range(0, W, 40):
        d.line((x, 0, x, H), fill=(148, 163, 184, 14), width=1)
    for y in range(0, H, 40):
        d.line((0, y, W, y), fill=(148, 163, 184, 14), width=1)

    # Flowing ribbons with blur
    ribbons = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    rd = ImageDraw.Draw(ribbons)
    curves = [
        ((880, 420), (1080, 40), (1320, 400), (1600, 90), (34, 211, 238, 150), 20),
        ((720, -20), (1020, 360), (1250, 20), (1600, 330), (167, 139, 250, 140), 26),
        ((960, 440), (1180, 120), (1420, 430), (1620, 180), (244, 114, 182, 90), 12),
    ]
    for p0, p1, p2, p3, color, width in curves:
        rd.line(cubic(p0, p1, p2, p3), fill=color, width=width, joint="curve")
    img.alpha_composite(ribbons.filter(ImageFilter.GaussianBlur(12)))
    img.alpha_composite(ribbons)

    # Aperture motif on the right
    ocx, ocy = 1370, 210
    od = ImageDraw.Draw(img, "RGBA")
    for i in range(6):
        a0 = math.radians(i * 60 - 90)
        a1 = math.radians(i * 60 - 30)
        pts = [polar(ocx, ocy, 30, a0), polar(ocx, ocy, 112, a0 + 0.20),
               polar(ocx, ocy, 112, a1 - 0.07), polar(ocx, ocy, 30, a1 - 0.11)]
        od.polygon(pts, fill=(*mix((34, 211, 238), (167, 139, 250), i / 5), 70))
    for r, col in ((125, (34, 211, 238, 110)), (145, (167, 139, 250, 80))):
        od.ellipse((ocx - r, ocy - r, ocx + r, ocy + r), outline=col, width=2)

    # Text panel
    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pd = ImageDraw.Draw(panel, "RGBA")
    pd.rounded_rectangle((60, 48, 1010, 372), radius=26, fill=(8, 13, 24, 175),
                         outline=(148, 163, 184, 45), width=2)
    img.alpha_composite(panel)

    d = ImageDraw.Draw(img, "RGBA")
    f_eye = font(BOLD, 21)
    f_title = font(BOLD, 72)
    f_sub = font(REG, 25)
    f_chip = font(BOLD, 17)
    spacing(d, (104, 86), "OPEN SOURCE  ·  MIT LICENSED", f_eye, (34, 211, 238, 255), gap=2)
    d.text((100, 132), "VB IMAGE AI STUDIO", font=f_title, fill=(240, 246, 255, 255))
    d.text((104, 238), "Free AI image generation — no key, no GPU, no limits.", font=f_sub,
           fill=(176, 190, 210, 255))
    d.text((104, 282), "Built by Raj Gautam  ·  Flask + Vanilla JS  ·  Multi-engine failover",
           font=f_sub, fill=(130, 148, 172, 255))

    x = 104
    for text, col in (("FLUX", (34, 211, 238)), ("SDXL", (167, 139, 250)), ("POLLINATIONS", (244, 114, 182))):
        w = int(d.textlength(text, font=f_chip)) + 30
        d.rounded_rectangle((x, 326, x + w, 356), radius=15, fill=(*col, 35), outline=(*col, 120), width=1)
        d.text((x + 15, 332), text, font=f_chip, fill=(*col, 255))
        x += w + 10

    path = DOCS / "banner.png"
    img.convert("RGB").save(path, quality=95)
    print("wrote", path)


if __name__ == "__main__":
    build_logo()
    build_banner()
