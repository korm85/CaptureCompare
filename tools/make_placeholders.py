#!/usr/bin/env python3
"""Generate the art and sound for Surprise Egg.

Run from the project root:  python3 tools/make_placeholders.py

File names match scripts/data.gd, so art can be replaced later without code changes.
Shapes are drawn at 2x and downscaled. Parts get a soft top-left light, a darker rim and a
gloss highlight. Toys and clothes use a darker tint of their own colour as the outline,
and stickers get a white die-cut border.
"""
import math
import os
import random
import wave

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ART = os.path.join(ROOT, "assets", "art")
SFX = os.path.join(ROOT, "assets", "sfx")
OUT_PX = 512
SS = 2
W = OUT_PX * SS
RATE = 22050

INK = (61, 43, 63)
WHITE = (255, 255, 255)
CREAM = (255, 246, 232)
BLUSH = (255, 128, 158)
NOSE_PINK = (255, 128, 150)

ORANGE, ORANGE_DARK, PINK_INNER = (255, 170, 96), (226, 124, 62), (255, 184, 200)
DOG, DOG_DARK, RED, GOLD = (216, 162, 106), (170, 114, 68), (232, 70, 82), (255, 208, 86)
BUNNY = (246, 242, 255)
DINO, DINO_DARK, DINO_LIGHT = (126, 212, 126), (80, 166, 102), (208, 244, 178)
UNI, HORN = (252, 248, 255), (255, 204, 80)
RAINBOW = [(255, 118, 170), (255, 190, 90), (255, 240, 120), (130, 225, 150), (120, 180, 255), (190, 140, 245)]
BEAR, BEAR_DARK, TAN = (186, 130, 88), (140, 92, 60), (234, 196, 152)
DUCK, DUCK_DARK, BEAK = (255, 222, 86), (240, 182, 52), (255, 146, 64)

HAT_YELLOW, BOW_PINK, FRAME, SCARF, TEE, CROWN = (255, 216, 92), (255, 126, 170), (98, 72, 116), (234, 66, 80), (116, 178, 255), (255, 202, 72)
JEWELS = [(255, 110, 150), (100, 220, 190), (110, 160, 255)]

STAR, HEART, PETAL, FLOWER_C, SUN_C, MOON_C = (255, 214, 70), (255, 98, 130), (255, 172, 210), (255, 216, 92), (255, 206, 70), (255, 236, 164)
BUTTER_A, BUTTER_B = (172, 132, 255), (255, 164, 222)
WAFFLE, CHERRY = (226, 164, 100), (232, 56, 74)
ICE_PINK, ICE_MINT, ICE_CREAM = (255, 172, 206), (164, 236, 212), (255, 246, 206)

YY, XX = np.mgrid[0:W, 0:W].astype(np.float32)


def S(v):
    return v * SS


def box(cx, cy, rx, ry):
    return [S(cx - rx), S(cy - ry), S(cx + rx), S(cy + ry)]


def pts(points):
    return [(S(x), S(y)) for x, y in points]


def blank():
    return Image.new("L", (W, W), 0)


def ell(cx, cy, rx, ry):
    m = blank()
    ImageDraw.Draw(m).ellipse(box(cx, cy, rx, ry), fill=255)
    return m


def poly(points):
    m = blank()
    ImageDraw.Draw(m).polygon(pts(points), fill=255)
    return m


def line(points, width):
    m = blank()
    d = ImageDraw.Draw(m)
    d.line(pts(points), fill=255, width=S(width), joint="curve")
    r = S(width) / 2
    for x, y in (points[0], points[-1]):
        d.ellipse([S(x) - r, S(y) - r, S(x) + r, S(y) + r], fill=255)
    return m


def rrect(x0, y0, x1, y1, r):
    m = blank()
    ImageDraw.Draw(m).rounded_rectangle([S(x0), S(y0), S(x1), S(y1)], radius=S(r), fill=255)
    return m


def ring(cx, cy, rx, ry, w):
    return ImageChops.subtract(ell(cx, cy, rx, ry), ell(cx, cy, max(rx - w, 1), max(ry - w, 1)))


def union(*ms):
    out = ms[0]
    for m in ms[1:]:
        out = ImageChops.lighter(out, m)
    return out


def cut(a, b):
    return ImageChops.subtract(a, b)


def clip(a, b):
    return ImageChops.multiply(a, b)


def feather(m, px):
    return m.filter(ImageFilter.GaussianBlur(S(px)))


def grow(m, px):
    # Blur then threshold: a cheap outward offset that stays smooth.
    return feather(m, px * 0.8).point(lambda v: 255 if v > 14 else 0)


def solid(m, color, alpha=255):
    layer = Image.new("RGBA", (W, W), tuple(color) + (0,))
    layer.putalpha(m.point(lambda v: v * alpha // 255))
    return layer


def shaded(m, base, rim=0.22, gloss=0.5):
    a = np.asarray(m, np.float32) / 255.0
    ys, xs = np.nonzero(a > 0.5)
    if xs.size == 0:
        return Image.new("RGBA", (W, W), (0, 0, 0, 0))
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    rx, ry = max((x1 - x0) / 2, 1.0), max((y1 - y0) / 2, 1.0)
    u = (XX - cx) / rx
    v = (YY - cy) / ry
    lum = 1.06 - 0.20 * (0.45 * u + 0.6 * v)
    edge = 1 - np.asarray(feather(m, 9), np.float32) / 255.0
    lum = lum * (1 - rim * np.clip(edge * 2.0, 0, 1))
    gx, gy = cx - rx * 0.36, cy - ry * 0.42
    d = ((XX - gx) / (rx * 0.30)) ** 2 + ((YY - gy) / (ry * 0.22)) ** 2
    spec = np.exp(-0.5 * d) * gloss * a
    rgb = np.array(base, np.float32)[None, None, :] * lum[..., None]
    rgb = rgb * (1 - spec[..., None]) + 255 * spec[..., None]
    out = np.zeros((W, W, 4), np.uint8)
    out[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    out[..., 3] = (a * 255).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def tint(base):
    return tuple(int(c * 0.55) for c in base)


class Art:
    def __init__(self):
        self.img = Image.new("RGBA", (W, W), (0, 0, 0, 0))

    def _over(self, layer):
        self.img = Image.alpha_composite(self.img, layer)

    def paint(self, m, base, rim=0.22, gloss=0.5, border=0):
        if border:
            self._over(solid(grow(m, border), tint(base)))
        self._over(shaded(m, base, rim, gloss))

    def flat(self, m, color, alpha=255):
        self._over(solid(m, color, alpha))

    def soft(self, m, color, alpha=255, blur=8):
        self._over(solid(feather(m, blur), color, alpha))

    def ink(self, m, alpha=255):
        self.flat(m, INK, alpha)

    def save(self, name):
        self.img.resize((OUT_PX, OUT_PX), Image.LANCZOS).save(os.path.join(ART, name + ".png"))


def eyes(a, x1, x2, y, rx=14, ry=19):
    for x in (x1, x2):
        a.ink(ell(x, y, rx, ry))
        a.flat(ell(x + rx * 0.35, y - ry * 0.4, rx * 0.34, ry * 0.3), WHITE)


def blush(a, x1, x2, y):
    for x in (x1, x2):
        a.soft(ell(x, y, 22, 14), BLUSH, 210, 6)


def ground_shadow(a, cx=256, cy=478, rx=128, ry=20):
    a.soft(ell(cx, cy, rx, ry), (40, 25, 50), 100, 14)


# ---------- toys ----------

def toy_cat():
    a = Art()
    ground_shadow(a)
    a.paint(line([(350, 392), (412, 394), (438, 334), (420, 268)], 34), ORANGE, border=6)
    a.paint(ell(256, 372, 126, 106), ORANGE, border=6)
    a.paint(ell(256, 396, 70, 60), CREAM, rim=0.08)
    ears = union(poly([(146, 200), (168, 50), (268, 128)]), ell(166, 74, 22, 22),
                 poly([(366, 200), (344, 50), (244, 128)]), ell(346, 74, 22, 22))
    a.paint(ears, ORANGE, border=6)
    a.flat(union(poly([(170, 164), (182, 92), (230, 130)]), poly([(342, 164), (330, 92), (282, 130)])), PINK_INNER)
    a.paint(ell(256, 216, 132, 118), ORANGE, border=6)
    for x in (230, 256, 282):
        a.flat(line([(x, 110), (x + (x - 256) // 6, 134)], 9), ORANGE_DARK)
    a.paint(ell(256, 270, 62, 46), CREAM, rim=0.08)
    eyes(a, 200, 312, 212)
    blush(a, 166, 346, 262)
    a.flat(poly([(244, 250), (268, 250), (256, 264)]), NOSE_PINK)
    a.ink(line([(256, 264), (256, 276)], 6))
    a.ink(line([(232, 278), (244, 288), (256, 276), (268, 288), (280, 278)], 6))
    for y0, y1 in ((262, 250), (278, 288)):
        a.ink(line([(202, y0), (140, y1)], 4), 200)
        a.ink(line([(310, y0), (372, y1)], 4), 200)
    return a


def toy_dog():
    a = Art()
    ground_shadow(a)
    a.paint(line([(372, 380), (412, 360), (420, 300)], 30), DOG_DARK, border=6)
    a.paint(ell(256, 372, 126, 106), DOG, border=6)
    a.paint(ell(256, 396, 66, 62), CREAM, rim=0.08)
    a.paint(ell(136, 236, 46, 90), DOG_DARK, border=6)
    a.paint(ell(376, 236, 46, 90), DOG_DARK, border=6)
    a.paint(ell(256, 216, 124, 116), DOG, border=6)
    a.paint(ell(256, 272, 64, 48), CREAM, rim=0.08)
    a.ink(ell(256, 252, 24, 17))
    a.flat(ell(248, 246, 7, 4), WHITE)
    eyes(a, 200, 312, 202, 14, 18)
    blush(a, 170, 342, 268)
    a.flat(ell(266, 302, 17, 24), (255, 118, 140))
    a.ink(line([(256, 290), (256, 300)], 5))
    a.ink(line([(226, 282), (246, 296), (256, 290), (266, 296), (286, 282)], 6))
    a.paint(rrect(150, 306, 362, 336, 15), RED, border=5)
    a.paint(ell(256, 350, 17, 17), GOLD, rim=0.3, gloss=0.8, border=4)
    return a


def toy_bunny():
    a = Art()
    ground_shadow(a)
    a.paint(ell(384, 396, 26, 26), WHITE, border=5)
    a.paint(ell(256, 374, 118, 104), BUNNY, border=6)
    a.paint(ell(204, 462, 40, 20), BUNNY, border=5)
    a.paint(ell(308, 462, 40, 20), BUNNY, border=5)
    a.paint(ell(206, 82, 34, 96), BUNNY, border=6)
    a.paint(ell(306, 82, 34, 96), BUNNY, border=6)
    a.flat(ell(206, 88, 15, 66), PINK_INNER)
    a.flat(ell(306, 88, 15, 66), PINK_INNER)
    a.paint(ell(256, 240, 118, 112), BUNNY, border=6)
    eyes(a, 200, 312, 236)
    blush(a, 168, 344, 276)
    a.flat(poly([(248, 262), (264, 262), (256, 272)]), NOSE_PINK)
    a.paint(rrect(250, 276, 262, 298, 3), WHITE, rim=0.05, border=4)
    a.ink(line([(232, 282), (244, 288), (256, 278), (268, 288), (280, 282)], 5))
    return a


def toy_dino():
    a = Art()
    ground_shadow(a, 240, 478, 160, 20)
    a.paint(line([(96, 384), (56, 344), (62, 290)], 34), DINO, border=6)
    for x, top in ((120, 282), (196, 262), (270, 262)):
        a.paint(poly([(x - 34, 320), (x + 2, top - 40), (x + 36, 320)]), DINO_DARK, border=5)
    a.paint(ell(236, 362, 150, 110), DINO, border=6)
    a.flat(ell(226, 394, 104, 60), DINO_LIGHT)
    a.paint(ell(186, 462, 50, 26), DINO_DARK, border=5)
    a.paint(ell(312, 462, 50, 26), DINO_DARK, border=5)
    a.paint(ell(362, 222, 110, 102), DINO, border=6)
    eyes(a, 388, 388, 208, 18, 24)
    a.ink(line([(362, 264), (388, 274), (412, 258)], 6))
    blush(a, 338, 430, 262)
    return a


def toy_unicorn():
    a = Art()
    ground_shadow(a)
    for colour, dy in zip(RAINBOW, (-16, -8, 0, 8, 16, 24)):
        a.paint(line([(180, 150 + dy), (120, 210 + dy), (150, 290 + dy), (210, 320 + dy)], 24), colour, rim=0.12)
    a.paint(ell(256, 376, 126, 106), UNI, rim=0.2, border=6)
    for colour, dy in zip(RAINBOW, (-16, -8, 0, 8, 16, 24)):
        a.paint(line([(398, 388 + dy), (452, 330 + dy), (430, 262 + dy)], 22), colour, rim=0.12)
    a.paint(poly([(258, 150), (300, 14), (322, 156)]), HORN, rim=0.3, gloss=0.8, border=5)
    for y in (70, 104):
        a.flat(line([(282, y + 14), (306, y)], 6), (240, 180, 70))
    a.paint(ell(284, 226, 112, 106), UNI, rim=0.2, border=6)
    a.paint(poly([(196, 160), (220, 124), (240, 162)]), (255, 186, 214), rim=0.1)
    eyes(a, 236, 326, 230)
    for x in (236, 326):
        a.ink(line([(x - 14, 212), (x - 22, 204)], 4))
    blush(a, 206, 352, 280)
    a.ink(line([(262, 282), (280, 292), (298, 282)], 6))
    return a


def toy_bear():
    a = Art()
    ground_shadow(a)
    a.paint(ell(146, 142, 50, 50), BEAR_DARK, border=6)
    a.paint(ell(366, 142, 50, 50), BEAR_DARK, border=6)
    a.flat(ell(146, 146, 24, 24), TAN)
    a.flat(ell(366, 146, 24, 24), TAN)
    a.paint(ell(256, 372, 126, 104), BEAR, border=6)
    a.paint(ell(256, 390, 66, 62), TAN, rim=0.1)
    a.paint(ell(150, 378, 36, 58), BEAR_DARK, border=5)
    a.paint(ell(362, 378, 36, 58), BEAR_DARK, border=5)
    a.paint(ell(200, 466, 46, 24), BEAR_DARK, border=5)
    a.paint(ell(312, 466, 46, 24), BEAR_DARK, border=5)
    a.paint(ell(256, 220, 128, 116), BEAR, border=6)
    a.paint(ell(256, 272, 66, 50), TAN, rim=0.1)
    a.ink(ell(256, 252, 24, 18))
    a.flat(ell(249, 246, 7, 5), WHITE)
    eyes(a, 200, 312, 210)
    blush(a, 168, 344, 268)
    a.ink(line([(234, 288), (246, 298), (256, 290), (266, 298), (278, 288)], 6))
    return a


def toy_duck():
    a = Art()
    ground_shadow(a, 256, 478, 150, 18)
    a.paint(poly([(394, 336), (444, 300), (432, 384)]), DUCK_DARK, border=5)
    a.paint(ell(256, 366, 160, 112), DUCK, border=6)
    a.paint(ell(186, 372, 62, 42), DUCK_DARK, rim=0.3, border=4)
    a.paint(ell(208, 474, 42, 14), BEAK, border=4)
    a.paint(ell(304, 474, 42, 14), BEAK, border=4)
    a.paint(poly([(250, 102), (226, 62), (276, 96)]), DUCK, border=5)
    a.paint(ell(256, 190, 104, 100), DUCK, border=6)
    eyes(a, 226, 290, 176)
    blush(a, 210, 306, 226)
    a.paint(poly([(300, 196), (398, 212), (300, 234)]), BEAK, rim=0.2, border=4)
    a.ink(line([(302, 214), (370, 214)], 4), 200)
    return a


# ---------- clothes (drawn around the centre; the anchor is the centre) ----------

def clothes_hat():
    a = Art()
    cone = poly([(128, 262), (256, 66), (384, 262)])
    a.paint(cone, HAT_YELLOW, border=6)
    stripes = blank()
    d = ImageDraw.Draw(stripes)
    for x in range(-40, 420, 96):
        d.polygon(pts([(x, 300), (x + 40, 300), (x + 136, 40), (x + 96, 40)]), fill=255)
    a.flat(clip(stripes, cone), PETAL, 255)
    a.paint(ell(256, 262, 150, 30), BOW_PINK, border=5)
    a.paint(ell(256, 62, 30, 30), BOW_PINK, rim=0.3, gloss=0.8, border=4)
    return a


def clothes_bow():
    a = Art()
    a.paint(poly([(256, 256), (182, 196), (150, 232), (154, 282), (192, 316)]), BOW_PINK, border=6)
    a.paint(poly([(256, 256), (330, 196), (362, 232), (358, 282), (320, 316)]), BOW_PINK, border=6)
    a.paint(poly([(240, 262), (206, 348), (230, 356), (256, 282)]), (226, 96, 140), border=4)
    a.paint(poly([(272, 262), (306, 348), (282, 356), (256, 282)]), (226, 96, 140), border=4)
    a.paint(ell(256, 256, 32, 30), (255, 96, 146), rim=0.3, gloss=0.8, border=5)
    return a


def clothes_glasses():
    a = Art()
    for x in (176, 336):
        a.flat(ell(x, 256, 70, 70), (200, 236, 255), 90)
        a.flat(ring(x, 256, 70, 70, 14), FRAME)
        a.flat(line([(x - 40, 226), (x - 20, 208)], 7), WHITE)
    a.flat(line([(246, 248), (266, 248)], 14), FRAME)
    a.flat(line([(106, 248), (74, 232)], 12), FRAME)
    a.flat(line([(406, 248), (438, 232)], 12), FRAME)
    return a


def clothes_scarf():
    a = Art()
    band = rrect(116, 222, 396, 296, 36)
    tail = rrect(300, 270, 350, 412, 22)
    a.paint(tail, SCARF, rim=0.3, border=5)
    a.paint(band, SCARF, border=6)
    stripes = blank()
    d = ImageDraw.Draw(stripes)
    for x in range(120, 400, 46):
        d.polygon(pts([(x, 220), (x + 16, 220), (x - 14, 300), (x - 30, 300)]), fill=255)
    a.flat(clip(stripes, band), (255, 220, 214), 210)
    for x in (318, 332, 346):
        a.flat(line([(x, 412), (x - 4, 428)], 7), SCARF)
    return a


def clothes_shirt():
    a = Art()
    body = union(rrect(186, 222, 326, 432, 22), poly([(186, 236), (132, 272), (152, 318), (190, 300)]),
                 poly([(326, 236), (380, 272), (360, 318), (322, 300)]))
    a.paint(body, TEE, border=6)
    a.paint(ell(256, 224, 46, 24), (84, 150, 230), rim=0.3, border=4)
    a.flat(ell(256, 224, 34, 14), (84, 150, 230))
    a.flat(union(line([(256, 290), (256, 292)], 2), ell(256, 330, 20, 20)), WHITE)
    return a


def clothes_crown():
    a = Art()
    crown = poly([(150, 300), (150, 206), (204, 258), (256, 176), (308, 258), (362, 206), (362, 300)])
    a.paint(crown, CROWN, rim=0.3, gloss=0.8, border=6)
    a.paint(rrect(146, 282, 366, 312, 10), (232, 166, 40), rim=0.2, border=0)
    for (x, y), colour in zip([(150, 206), (256, 176), (362, 206)], JEWELS):
        a.paint(ell(x, y, 16, 16), colour, rim=0.2, gloss=0.8, border=4)
    a.paint(ell(256, 296, 12, 12), JEWELS[2], rim=0.2, gloss=0.8, border=3)
    return a


# ---------- stickers (white die-cut border and a soft shadow) ----------

def die_cut(m, draw):
    a = Art()
    a.soft(grow(m, 22), (70, 40, 80), 90, 12)
    a.flat(grow(m, 20), WHITE)
    draw(a)
    return a


def star_mask():
    pts_ = []
    for i in range(10):
        r = 196 if i % 2 == 0 else 92
        ang = -math.pi / 2 + i * math.pi / 5
        pts_.append((256 + r * math.cos(ang), 268 + r * math.sin(ang)))
    return poly(pts_)


def sticker_star():
    m = star_mask()
    return die_cut(m, lambda a: a.paint(m, STAR, rim=0.25, gloss=0.7))


def sticker_heart():
    m = union(ell(196, 206, 98, 94), ell(316, 206, 98, 94), poly([(104, 236), (408, 236), (256, 432)]))
    return die_cut(m, lambda a: a.paint(m, HEART, rim=0.25, gloss=0.7))


def sticker_flower():
    petals = blank()
    for i in range(6):
        ang = i * math.pi / 3
        petals = union(petals, ell(256 + 104 * math.cos(ang), 256 + 104 * math.sin(ang), 78, 78))
    def draw(a):
        a.paint(petals, PETAL, rim=0.2, gloss=0.6)
        a.paint(ell(256, 256, 70, 70), FLOWER_C, rim=0.25, gloss=0.7)
    return die_cut(petals, draw)


def sticker_rainbow():
    m = blank()
    for i in range(len(RAINBOW)):
        r = 220 - i * 30
        m = union(m, arc_band(256, 390, r, 28, 180, 360))
    def draw(a):
        for i, colour in enumerate(RAINBOW):
            r = 220 - i * 30
            a.paint(arc_band(256, 390, r, 28, 180, 360), colour, rim=0.15, gloss=0.5)
        a.paint(ell(120, 396, 52, 38), WHITE, rim=0.05, gloss=0.4)
        a.paint(ell(392, 396, 52, 38), WHITE, rim=0.05, gloss=0.4)
    return die_cut(union(m, ell(120, 396, 52, 38), ell(392, 396, 52, 38)), draw)


def arc_band(cx, cy, r, w, a0, a1):
    m = blank()
    ImageDraw.Draw(m).arc(box(cx, cy, r, r), a0, a1, fill=255, width=S(w))
    return m


def sticker_sun():
    rays = blank()
    for i in range(12):
        ang = i * math.pi / 6
        rays = union(rays, line([(256 + 150 * math.cos(ang), 256 + 150 * math.sin(ang)),
                                 (256 + 200 * math.cos(ang), 256 + 200 * math.sin(ang))], 26))
    body = ell(256, 256, 120, 120)
    def draw(a):
        a.paint(rays, SUN_C, rim=0.1, gloss=0.2)
        a.paint(body, SUN_C, rim=0.2, gloss=0.7)
        eyes(a, 214, 298, 240, 11, 15)
        blush(a, 196, 316, 274)
        a.ink(line([(236, 282), (256, 296), (276, 282)], 6))
    return die_cut(union(rays, body), draw)


def sticker_moon():
    m = cut(ell(256, 256, 170, 170), ell(330, 210, 150, 150))
    def draw(a):
        a.paint(m, MOON_C, rim=0.2, gloss=0.6)
        a.flat(ell(176, 236, 20, 20), (240, 210, 130))
        a.flat(ell(206, 310, 12, 12), (240, 210, 130))
    return die_cut(m, draw)


def sticker_butterfly():
    up = union(ell(170, 196, 96, 88), ell(342, 196, 96, 88))
    low = union(ell(190, 340, 72, 66), ell(322, 340, 72, 66))
    body = rrect(246, 170, 266, 370, 10)
    def draw(a):
        a.paint(low, BUTTER_B, rim=0.2, gloss=0.5)
        a.paint(up, BUTTER_A, rim=0.2, gloss=0.5)
        for x, y in ((150, 190), (190, 220), (362, 190), (322, 220)):
            a.flat(ell(x, y, 10, 10), WHITE)
        for x, y in ((180, 336), (330, 336)):
            a.flat(ell(x, y, 9, 9), WHITE)
        a.paint(body, INK, rim=0.1, gloss=0.3)
        a.ink(line([(254, 166), (214, 112)], 7))
        a.ink(line([(258, 166), (298, 112)], 7))
    return die_cut(union(up, low, body), draw)


def sticker_ice_cream():
    cone = poly([(170, 250), (256, 470), (342, 250)])
    scoops = union(ell(256, 200, 112, 98), ell(184, 244, 84, 78), ell(328, 244, 84, 78))
    def draw(a):
        a.paint(cone, WAFFLE, rim=0.25, gloss=0.4)
        grid = blank()
        d = ImageDraw.Draw(grid)
        for k in range(-3, 4):
            d.line(pts([(256 + k * 40 - 130, 230), (256 + k * 40 + 130, 480)]), fill=255, width=S(8))
            d.line(pts([(256 + k * 40 + 130, 230), (256 + k * 40 - 130, 480)]), fill=255, width=S(8))
        a.flat(clip(grid, cone), (196, 130, 74), 170)
        a.paint(ell(184, 244, 84, 78), ICE_MINT, rim=0.2, gloss=0.6)
        a.paint(ell(328, 244, 84, 78), ICE_CREAM, rim=0.2, gloss=0.6)
        a.paint(ell(256, 200, 112, 98), ICE_PINK, rim=0.2, gloss=0.6)
        a.paint(ell(256, 100, 24, 24), CHERRY, rim=0.2, gloss=0.8)
    return die_cut(union(cone, scoops, ell(256, 100, 24, 24)), draw)


# ---------- eggs, cracks and tools ----------

EGG_BOX = (256, 270, 170, 215)
EGG_VARIANTS = [
    ((255, 196, 214), "dots", (255, 255, 255)),
    ((172, 236, 206), "stripes", (96, 190, 146)),
    ((255, 242, 160), "zigzag", (255, 160, 80)),
    ((176, 216, 255), "stars", (255, 255, 255)),
    ((220, 198, 255), "spots", (150, 110, 230)),
]


def egg_pattern(kind):
    m = blank()
    if kind == "dots":
        for x in range(60, 480, 74):
            for y in range(90, 470, 74):
                m = union(m, ell(x + (37 if (y // 74) % 2 else 0), y, 13, 13))
    elif kind == "stripes":
        d = ImageDraw.Draw(m)
        for y in range(120, 480, 72):
            d.rectangle([0, S(y), W, S(y + 30)], fill=255)
    elif kind == "zigzag":
        for y in range(130, 480, 72):
            m = union(m, line([(i * 64 - 10, y + (28 if i % 2 else 0)) for i in range(10)], 18))
    elif kind == "stars":
        for x, y in [(160, 170), (340, 150), (256, 300), (150, 404), (362, 400)]:
            m = union(m, star_at(x, y, 40, 18))
    elif kind == "spots":
        for x, y in [(170, 200), (330, 230), (250, 360), (160, 400), (350, 400)]:
            m = union(m, ell(x, y, 30, 30))
    return m


def star_at(cx, cy, ro, ri):
    pts_ = []
    for i in range(10):
        r = ro if i % 2 == 0 else ri
        ang = -math.pi / 2 + i * math.pi / 5
        pts_.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    return poly(pts_)


def egg(variant):
    base, kind, pat_col = EGG_VARIANTS[variant]
    cx, cy, rx, ry = EGG_BOX
    body = ell(cx, cy, rx, ry)
    a = Art()
    a.soft(ell(cx, 478, 150, 18), (40, 25, 50), 90, 12)
    a.paint(body, base, rim=0.25, gloss=0.75, border=6)
    a.flat(clip(egg_pattern(kind), body), pat_col, 235)
    return a


def crack(stage):
    a = Art()
    rng = random.Random(stage)
    for _ in range(stage * 3):
        x, y = 256 + rng.randint(-36, 36), 270 + rng.randint(-40, 40)
        path = [(x, y)]
        for _ in range(4):
            x += rng.randint(-34, 34) + (28 if stage % 2 else -28)
            y += rng.randint(12, 34)
            path.append((x, y))
        a.ink(line(path, 11))
        a.flat(line([(px + 3, py + 2) for px, py in path], 3), WHITE, 200)
    return a


def hammer():
    a = Art()
    a.soft(ell(268, 470, 100, 20), (40, 25, 50), 90, 14)
    a.paint(rrect(236, 226, 282, 484, 22), (196, 136, 84), rim=0.3, gloss=0.4, border=6)
    a.paint(rrect(118, 118, 340, 250, 34), (168, 176, 196), rim=0.3, gloss=0.8, border=6)
    return a


def trash():
    a = Art()
    a.soft(ell(256, 462, 130, 22), (40, 25, 50), 90, 14)
    a.paint(rrect(136, 176, 376, 218, 18), (126, 150, 186), rim=0.25, gloss=0.8, border=6)
    a.paint(poly([(160, 216), (352, 216), (330, 452), (182, 452)]), (150, 176, 210), rim=0.3, gloss=0.4, border=6)
    for x in (212, 256, 300):
        a.flat(line([(x, 250), (x + (x - 256) // 10, 420)], 10), (116, 136, 170))
    return a


def shadow_blob():
    img = Image.new("RGBA", (512, 128), (0, 0, 0, 0))
    m = Image.new("L", (512, 128), 0)
    ImageDraw.Draw(m).ellipse([24, 24, 488, 104], fill=255)
    m = m.filter(ImageFilter.GaussianBlur(14))
    img.putalpha(m.point(lambda v: v * 150 // 255))
    img.paste((40, 25, 50, 0), (0, 0), Image.new("L", (512, 128), 255))
    return Image.composite(Image.new("RGBA", (512, 128), (40, 25, 50, 255)), img, img.getchannel("A"))


def spark_texture():
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = 128
    star = [(cx, 6), (cx + 26, cx - 26), (250, cx), (cx + 26, cx + 26), (cx, 250), (cx - 26, cx + 26), (6, cx), (cx - 26, cx - 26)]
    d.polygon(star, fill=(255, 255, 255, 255))
    glow = Image.new("L", (256, 256), 0)
    ImageDraw.Draw(glow).ellipse([80, 80, 176, 176], fill=255)
    glow = glow.filter(ImageFilter.GaussianBlur(18))
    img = Image.alpha_composite(Image.composite(Image.new("RGBA", (256, 256), (255, 255, 255, 255)), Image.new("RGBA", (256, 256), (0, 0, 0, 0)), glow), img)
    return img


def dot_texture():
    img = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    m = Image.new("L", (128, 128), 0)
    ImageDraw.Draw(m).ellipse([20, 20, 108, 108], fill=255)
    m = m.filter(ImageFilter.GaussianBlur(6))
    img.putalpha(m)
    return Image.composite(Image.new("RGBA", (128, 128), (255, 255, 255, 255)), img, img.getchannel("A"))


def confetti_texture():
    img = Image.new("RGBA", (96, 48), (0, 0, 0, 0))
    m = Image.new("L", (96, 48), 0)
    ImageDraw.Draw(m).rounded_rectangle([4, 4, 92, 44], radius=10, fill=255)
    return Image.composite(Image.new("RGBA", (96, 48), (255, 255, 255, 255)), img, m)


# ---------- backgrounds (full scene and a square swatch) ----------

BACKGROUNDS = {
    "sky":   ((150, 218, 255), (246, 252, 255), (150, 224, 178), (118, 200, 150), (96, 176, 132)),
    "mint":  ((178, 240, 220), (246, 255, 250), (140, 214, 196), (110, 190, 170), (84, 166, 150)),
    "peach": ((255, 214, 182), (255, 246, 236), (252, 200, 176), (244, 170, 152), (234, 146, 136)),
    "lilac": ((214, 196, 255), (252, 246, 255), (204, 186, 250), (184, 164, 240), (162, 142, 228)),
}


def background(name):
    top, bottom, h1, h2, h3 = BACKGROUNDS[name]
    W_, H_ = 1280, 720
    Y, X = np.mgrid[0:H_, 0:W_].astype(np.float32)
    t = (Y / H_)[..., None]
    img = np.array(top, np.float32) * (1 - t) + np.array(bottom, np.float32) * t
    glow = np.exp(-(((X - 980) / 420) ** 2 + ((Y - 150) / 300) ** 2))[..., None]
    img = img * (1 - 0.35 * glow) + 255 * 0.35 * glow
    for colour, base, amp, freq, phase in (
        (h1, 500, 46, 0.0042, 0.6), (h2, 560, 36, 0.0061, 2.1), (h3, 630, 26, 0.0085, 4.0)):
        edge = base + amp * np.sin(X * freq + phase) + 0.45 * amp * np.sin(X * freq * 2.3 + phase * 1.7)
        cover = 1 / (1 + np.exp(np.clip(-(Y - edge) / 1.4, -60, 60)))
        shade = 1.0 - 0.18 * np.clip((Y - edge) / 180, 0, 1)
        layer = np.array(colour, np.float32)[None, None, :] * shade[..., None]
        img = img * (1 - cover[..., None]) + layer * cover[..., None]
    rng = random.Random(len(name) * 97 + 3)
    base_img = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    clouds = Image.new("L", (W_, H_), 0)
    cd = ImageDraw.Draw(clouds)
    for _ in range(7):
        x, y = rng.randint(60, 1220), rng.randint(60, 260)
        for k in range(4):
            cd.ellipse([x + k * 30 - 70, y - 22 + rng.randint(-6, 6), x + k * 30 + 20, y + 26], fill=255)
    clouds = clouds.filter(ImageFilter.GaussianBlur(10)).point(lambda v: v * 150 // 255)
    base_img = Image.composite(Image.new("RGBA", (W_, H_), WHITE + (255,)), base_img, clouds)
    sparkles = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sparkles)
    for _ in range(40):
        x, y, r = rng.randint(0, W_), rng.randint(0, 380), rng.randint(2, 5)
        sd.ellipse([x - r, y - r, x + r, y + r], fill=WHITE + (170,))
    return Image.alpha_composite(base_img, sparkles.filter(ImageFilter.GaussianBlur(0.6)))


# ---------- sounds ----------

def t_of(dur):
    return np.arange(int(RATE * dur)) / RATE


def envelope(t, decay, attack=0.005):
    return np.exp(-decay * t) * np.minimum(1.0, t / attack)


def blip(freq, dur, decay=12, shape="sine"):
    t = t_of(dur)
    phase = 2 * np.pi * freq * t
    sig = np.sin(phase) if shape == "sine" else np.sign(np.sin(phase))
    return sig * envelope(t, decay)


def sweep(f0, f1, dur, decay=10, shape="sine"):
    t = t_of(dur)
    freq = np.linspace(f0, f1, t.size)
    phase = 2 * np.pi * np.cumsum(freq) / RATE
    sig = np.sin(phase) if shape == "sine" else np.sign(np.sin(phase))
    return sig * envelope(t, decay)


def noise(dur, decay=15, seed=1):
    t = t_of(dur)
    rng = np.random.default_rng(seed)
    return rng.uniform(-1, 1, t.size) * envelope(t, decay)


def arpeggio(freqs, step, decay=8, shape="sine"):
    return np.concatenate([blip(f, step, decay, shape) for f in freqs])


def whoosh(dur=0.35):
    raw = noise(dur, decay=0, seed=7)
    smooth = np.convolve(raw, np.ones(12) / 12, mode="same")
    t = t_of(dur)
    return smooth * np.sin(np.pi * t / dur) * 2.5


def write_wav(name, samples):
    samples = np.clip(samples, -1, 1)
    pcm = (samples * 32767 * 0.8).astype("<i2")
    with wave.open(os.path.join(SFX, name + ".wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())


TOY_PITCH = {"cat": (700, 900), "dog": (260, 220), "bunny": (900, 1100),
             "dino": (150, 120), "unicorn": (1200, 1500), "bear": (200, 170),
             "duck": (500, 420)}


def make_sounds():
    write_wav("tok", blip(700, 0.07, 45))
    write_wav("crack", noise(0.28, 18, seed=3))
    write_wav("pop", sweep(500, 1400, 0.12, 22))
    write_wav("jingle", arpeggio([523, 659, 784, 1047], 0.12, 9))
    write_wav("boop", sweep(330, 280, 0.16, 12))
    write_wav("whoosh", whoosh())
    write_wav("cheer", arpeggio([784, 988, 1175, 1568, 1568], 0.09, 7))
    for name, (f0, f1) in TOY_PITCH.items():
        write_wav("toy_" + name, sweep(f0, f1, 0.35, 6))


# ---------- main ----------

TOYS = {"cat": toy_cat, "dog": toy_dog, "bunny": toy_bunny, "dino": toy_dino,
        "unicorn": toy_unicorn, "bear": toy_bear, "duck": toy_duck}
CLOTHES = {"hat_party": clothes_hat, "bow_pink": clothes_bow, "glasses_round": clothes_glasses,
           "scarf_red": clothes_scarf, "shirt_blue": clothes_shirt, "crown_gold": clothes_crown}
STICKERS = {"star": sticker_star, "heart": sticker_heart, "flower": sticker_flower,
            "rainbow": sticker_rainbow, "sun": sticker_sun, "moon": sticker_moon,
            "butterfly": sticker_butterfly, "ice_cream": sticker_ice_cream}


def save_image(img, name, size=None):
    if size:
        img = img.resize(size, Image.LANCZOS)
    img.save(os.path.join(ART, name + ".png"))


def main():
    os.makedirs(ART, exist_ok=True)
    os.makedirs(SFX, exist_ok=True)
    for name, fn in TOYS.items():
        fn().save(name)
    for name, fn in CLOTHES.items():
        fn().save(name)
    for name, fn in STICKERS.items():
        fn().save(name)
    for i in range(len(EGG_VARIANTS)):
        egg(i).save("egg_%d" % i)
    for stage in range(1, 5):
        crack(stage).save("crack_%d" % stage)
    hammer().save("hammer")
    trash().save("trash")
    save_image(shadow_blob(), "shadow")
    save_image(spark_texture(), "spark", (128, 128))
    save_image(dot_texture(), "dot", (64, 64))
    save_image(confetti_texture(), "confetti", (48, 24))
    for name in BACKGROUNDS:
        bg = background(name)
        save_image(bg, "bg_" + name)
        square = bg.crop((380, 0, 900, 520)).resize((512, 512), Image.LANCZOS)
        save_image(square, "swatch_" + name)
    make_sounds()
    print("art written to", ART, "and sounds to", SFX)


if __name__ == "__main__":
    main()
