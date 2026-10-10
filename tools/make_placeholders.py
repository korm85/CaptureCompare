#!/usr/bin/env python3
"""Generate placeholder art and sound for Surprise Egg.

Run from the project root:  python3 tools/make_placeholders.py

File names match scripts/data.gd, so real art can replace these later
without code changes. Drawing is done at 2x and downscaled for smooth edges.
"""
import os
import random
import wave

import numpy as np
from PIL import Image, ImageChops, ImageDraw

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ART = os.path.join(ROOT, "assets", "art")
SFX = os.path.join(ROOT, "assets", "sfx")
SIZE = 512
SS = 2
RATE = 22050
OUT = (70, 45, 40, 255)  # outline colour for all shapes
WHITE = (255, 255, 255, 255)
BLUSH = (255, 150, 170, 255)


def sc(v):
    return v * SS


def box(cx, cy, rx, ry):
    return [sc(cx - rx), sc(cy - ry), sc(cx + rx), sc(cy + ry)]


def pts(points):
    return [(sc(x), sc(y)) for x, y in points]


def new_canvas():
    img = Image.new("RGBA", (SIZE * SS, SIZE * SS), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def save(img, name):
    img = img.resize((SIZE, SIZE), Image.LANCZOS)
    img.save(os.path.join(ART, name + ".png"))


def ellipse(d, cx, cy, rx, ry, fill, line=True):
    d.ellipse(box(cx, cy, rx, ry), fill=fill, outline=OUT if line else None, width=sc(8))


def polygon(d, points, fill, line=True):
    d.polygon(pts(points), fill=fill)
    if line:
        d.line(pts(points + [points[0]]), fill=OUT, width=sc(8), joint="curve")


def line(d, points, colour, width=8):
    d.line(pts(points), fill=colour, width=sc(width), joint="curve")


def eyes(d, x1, x2, y):
    for x in (x1, x2):
        ellipse(d, x, y, 16, 22, OUT, line=False)
        ellipse(d, x + 5, y - 8, 5, 6, WHITE, line=False)


# ---------- toys (512 canvas, toy centred, anchors in data.gd) ----------

def toy_cat():
    img, d = new_canvas()
    c, dark = (255, 178, 102, 255), (230, 140, 70, 255)
    ellipse(d, 256, 380, 130, 105, c)
    polygon(d, [(140, 170), (165, 40), (255, 120)], c)
    polygon(d, [(372, 170), (347, 40), (257, 120)], c)
    polygon(d, [(152, 150), (165, 80), (222, 128)], BLUSH, line=False)
    polygon(d, [(360, 150), (347, 80), (290, 128)], BLUSH, line=False)
    ellipse(d, 256, 215, 135, 120, c)
    eyes(d, 200, 312, 212)
    ellipse(d, 170, 255, 18, 12, BLUSH, line=False)
    ellipse(d, 342, 255, 18, 12, BLUSH, line=False)
    polygon(d, [(240, 250), (272, 250), (256, 270)], BLUSH)
    line(d, [(256, 270), (256, 282), (238, 292)], OUT, 6)
    line(d, [(256, 270), (256, 282), (274, 292)], OUT, 6)
    return img


def toy_dog():
    img, d = new_canvas()
    c, dark = (200, 150, 100, 255), (150, 100, 60, 255)
    ellipse(d, 256, 380, 130, 105, c)
    ellipse(d, 135, 225, 52, 95, dark)
    ellipse(d, 377, 225, 52, 95, dark)
    ellipse(d, 256, 215, 125, 115, c)
    eyes(d, 200, 312, 205)
    ellipse(d, 256, 262, 60, 42, (235, 205, 165, 255))
    ellipse(d, 256, 248, 24, 17, OUT, line=False)
    ellipse(d, 256, 300, 20, 26, BLUSH)
    return img


def toy_bunny():
    img, d = new_canvas()
    c, pink = (240, 240, 250, 255), (255, 170, 190, 255)
    ellipse(d, 256, 390, 120, 95, c)
    ellipse(d, 205, 95, 35, 95, c)
    ellipse(d, 307, 95, 35, 95, c)
    ellipse(d, 205, 95, 15, 65, pink, line=False)
    ellipse(d, 307, 95, 15, 65, pink, line=False)
    ellipse(d, 256, 245, 125, 115, c)
    eyes(d, 200, 312, 235)
    ellipse(d, 256, 285, 16, 12, pink)
    ellipse(d, 170, 282, 18, 12, BLUSH, line=False)
    ellipse(d, 342, 282, 18, 12, BLUSH, line=False)
    return img


def toy_dino():
    img, d = new_canvas()
    c, light = (120, 200, 120, 255), (190, 235, 170, 255)
    for x in (120, 190, 260, 330, 400):
        polygon(d, [(x - 32, 320), (x, 205), (x + 32, 320)], (90, 170, 100, 255))
    ellipse(d, 256, 330, 170, 120, c)
    ellipse(d, 250, 370, 100, 60, light, line=False)
    ellipse(d, 340, 230, 110, 100, c)
    ellipse(d, 368, 205, 14, 18, OUT, line=False)
    ellipse(d, 190, 440, 50, 28, (90, 170, 100, 255))
    ellipse(d, 330, 440, 50, 28, (90, 170, 100, 255))
    ellipse(d, 420, 250, 16, 10, BLUSH, line=False)
    return img


def toy_unicorn():
    img, d = new_canvas()
    c, mane = (245, 235, 255, 255), (255, 140, 200, 255)
    polygon(d, [(120, 170), (90, 270), (160, 240)], mane)
    polygon(d, [(140, 200), (105, 320), (170, 290)], (150, 200, 255, 255))
    ellipse(d, 256, 380, 130, 105, c)
    polygon(d, [(262, 150), (300, 20), (325, 160)], (255, 210, 90, 255))
    ellipse(d, 285, 220, 115, 105, c)
    ellipse(d, 215, 225, 18, 24, OUT, line=False)
    ellipse(d, 215, 225, 6, 8, WHITE, line=False)
    ellipse(d, 250, 275, 18, 12, BLUSH, line=False)
    ellipse(d, 320, 275, 18, 12, BLUSH, line=False)
    return img


def toy_bear():
    img, d = new_canvas()
    c, dark = (170, 110, 70, 255), (130, 80, 50, 255)
    ellipse(d, 256, 400, 125, 100, c)
    ellipse(d, 150, 130, 55, 55, dark)
    ellipse(d, 362, 130, 55, 55, dark)
    ellipse(d, 256, 230, 130, 120, c)
    ellipse(d, 256, 285, 62, 46, (225, 185, 140, 255))
    ellipse(d, 256, 262, 20, 15, OUT, line=False)
    eyes(d, 200, 312, 210)
    return img


def toy_duck():
    img, d = new_canvas()
    c, orange = (255, 225, 80, 255), (255, 150, 50, 255)
    ellipse(d, 256, 350, 160, 120, c)
    ellipse(d, 190, 360, 55, 35, (240, 200, 60, 255))
    ellipse(d, 256, 185, 100, 100, c)
    polygon(d, [(300, 190), (410, 212), (300, 232)], orange)
    eyes(d, 220, 290, 170)
    ellipse(d, 250, 225, 20, 12, BLUSH, line=False)
    return img


TOY_PAINTERS = {
    "cat": toy_cat, "dog": toy_dog, "bunny": toy_bunny, "dino": toy_dino,
    "unicorn": toy_unicorn, "bear": toy_bear, "duck": toy_duck,
}


# ---------- clothes (drawn around canvas centre; anchor = centre) ----------

def clothes_hat_party():
    img, d = new_canvas()
    polygon(d, [(150, 250), (256, 110), (362, 250)], (255, 220, 80, 255))
    ellipse(d, 256, 110, 22, 22, (255, 110, 150, 255))
    ellipse(d, 256, 250, 150, 26, (255, 110, 150, 255))
    for x, y in [(230, 200), (280, 190), (256, 230)]:
        ellipse(d, x, y, 9, 9, WHITE, line=False)
    return img


def clothes_bow_pink():
    img, d = new_canvas()
    c = (255, 130, 180, 255)
    polygon(d, [(256, 256), (140, 195), (140, 317)], c)
    polygon(d, [(256, 256), (372, 195), (372, 317)], c)
    ellipse(d, 256, 256, 26, 26, (230, 90, 150, 255))
    return img


def clothes_glasses_round():
    img, d = new_canvas()
    ring = (60, 60, 70, 255)
    for x in (180, 332):
        d.ellipse(box(x, 256, 72, 72), fill=(200, 240, 255, 110), outline=ring, width=sc(14))
    line(d, [(252, 250), (260, 250)], ring, 14)
    line(d, [(108, 250), (80, 232)], ring, 12)
    line(d, [(404, 250), (432, 232)], ring, 12)
    return img


def clothes_scarf_red():
    img, d = new_canvas()
    c, dark = (225, 45, 55, 255), (170, 25, 35, 255)
    polygon(d, [(300, 280), (345, 280), (360, 400), (318, 396)], dark)
    d.rounded_rectangle([sc(120), sc(226), sc(392), sc(296)], radius=sc(34), fill=c, outline=OUT, width=sc(8))
    for x in (180, 250, 320):
        line(d, [(x, 240), (x + 14, 282)], dark, 6)
    return img


def clothes_shirt_blue():
    img, d = new_canvas()
    c = (90, 170, 255, 255)
    polygon(d, [(120, 200), (170, 150), (200, 210), (200, 330), (312, 330), (312, 210), (342, 150), (392, 200), (350, 245), (340, 380), (172, 380), (162, 245)], c)
    line(d, [(230, 210), (256, 240), (282, 210)], OUT, 6)
    return img


def clothes_crown_gold():
    img, d = new_canvas()
    gold = (255, 205, 60, 255)
    polygon(d, [(150, 290), (150, 200), (200, 250), (256, 180), (312, 250), (362, 200), (362, 290)], gold)
    for x, y in [(150, 200), (256, 180), (362, 200)]:
        ellipse(d, x, y, 14, 14, (255, 90, 120, 255))
    return img


CLOTHES_PAINTERS = {
    "hat_party": clothes_hat_party, "bow_pink": clothes_bow_pink,
    "glasses_round": clothes_glasses_round, "scarf_red": clothes_scarf_red,
    "shirt_blue": clothes_shirt_blue, "crown_gold": clothes_crown_gold,
}


# ---------- stickers ----------

def star_points(cx, cy, r_out, r_in, n=5):
    out = []
    for i in range(n * 2):
        r = r_out if i % 2 == 0 else r_in
        a = -np.pi / 2 + i * np.pi / n
        out.append((cx + r * np.cos(a), cy + r * np.sin(a)))
    return out


def sticker_star():
    img, d = new_canvas()
    polygon(d, star_points(256, 262, 200, 90), (255, 220, 60, 255))
    return img


def sticker_heart():
    img, d = new_canvas()
    c = (255, 80, 120, 255)
    ellipse(d, 190, 210, 90, 90, c)
    ellipse(d, 322, 210, 90, 90, c)
    polygon(d, [(105, 240), (407, 240), (256, 420)], c)
    ellipse(d, 165, 185, 18, 18, WHITE, line=False)
    return img


def sticker_flower():
    img, d = new_canvas()
    petal = (255, 160, 210, 255)
    for i in range(6):
        a = i * np.pi / 3
        ellipse(d, 256 + 110 * np.cos(a), 256 + 110 * np.sin(a), 80, 80, petal)
    ellipse(d, 256, 256, 70, 70, (255, 215, 60, 255))
    return img


def sticker_rainbow():
    img, d = new_canvas()
    cols = [(255, 90, 90), (255, 170, 60), (255, 230, 80), (120, 220, 120), (90, 170, 255), (170, 120, 230)]
    for i, col in enumerate(cols):
        r = 230 - i * 30
        d.arc(box(256, 380, r, r), start=180, end=360, fill=col + (255,), width=sc(26))
    return img


def sticker_sun():
    img, d = new_canvas()
    yellow = (255, 200, 40, 255)
    for i in range(12):
        a = i * np.pi / 6
        x, y = 256 + 190 * np.cos(a), 256 + 190 * np.sin(a)
        ellipse(d, x, y, 30, 30, yellow)
    ellipse(d, 256, 256, 130, 130, (255, 225, 80, 255))
    ellipse(d, 215, 240, 12, 16, OUT, line=False)
    ellipse(d, 297, 240, 12, 16, OUT, line=False)
    return img


def sticker_moon():
    img, d = new_canvas()
    d.ellipse(box(256, 256, 170, 170), fill=(255, 240, 150, 255), outline=OUT, width=sc(8))
    d.ellipse(box(330, 215, 140, 140), fill=(0, 0, 0, 0))
    return img


def sticker_butterfly():
    img, d = new_canvas()
    c = (170, 120, 255, 255)
    ellipse(d, 165, 190, 100, 90, c)
    ellipse(d, 347, 190, 100, 90, c)
    ellipse(d, 180, 340, 70, 70, (255, 150, 220, 255))
    ellipse(d, 332, 340, 70, 70, (255, 150, 220, 255))
    ellipse(d, 256, 265, 22, 120, OUT, line=False)
    line(d, [(250, 160), (215, 110)], OUT, 6)
    line(d, [(262, 160), (297, 110)], OUT, 6)
    return img


def sticker_ice_cream():
    img, d = new_canvas()
    polygon(d, [(170, 260), (256, 470), (342, 260)], (230, 170, 100, 255))
    ellipse(d, 256, 200, 110, 100, (255, 170, 210, 255))
    ellipse(d, 190, 230, 80, 80, (170, 220, 255, 255))
    ellipse(d, 322, 230, 80, 80, (255, 245, 170, 255))
    ellipse(d, 226, 170, 10, 10, OUT, line=False)
    return img


STICKER_PAINTERS = {
    "star": sticker_star, "heart": sticker_heart, "flower": sticker_flower,
    "rainbow": sticker_rainbow, "sun": sticker_sun, "moon": sticker_moon,
    "butterfly": sticker_butterfly, "ice_cream": sticker_ice_cream,
}


# ---------- egg, cracks, hammer ----------

EGG_BOX = (256, 270, 170, 215)
EGG_VARIANTS = [
    ((255, 190, 210, 255), "dots", (255, 255, 255, 255)),
    ((170, 235, 200, 255), "stripes", (80, 180, 130, 255)),
    ((255, 240, 150, 255), "zigzag", (240, 150, 60, 255)),
    ((170, 210, 255, 255), "stars", (255, 255, 255, 255)),
    ((215, 190, 255, 255), "spots", (140, 100, 220, 255)),
]


def pattern_layer(kind, colour):
    img, d = new_canvas()
    if kind == "dots":
        for x in range(60, 480, 80):
            for y in range(90, 470, 80):
                ellipse(d, x + (40 if (y // 80) % 2 else 0), y, 14, 14, colour, line=False)
    elif kind == "stripes":
        for y in range(120, 480, 70):
            d.rectangle([0, sc(y), sc(SIZE), sc(y + 30)], fill=colour)
    elif kind == "zigzag":
        for y in range(130, 480, 70):
            zz = []
            for i in range(9):
                zz.append((i * 64, y + (30 if i % 2 else 0)))
            line(d, zz, colour, 18)
    elif kind == "stars":
        for x, y in [(160, 170), (340, 150), (256, 300), (150, 400), (360, 400)]:
            polygon(d, star_points(x, y, 40, 18), colour, line=False)
    elif kind == "spots":
        for x, y in [(170, 200), (330, 230), (250, 360), (160, 400), (350, 400)]:
            ellipse(d, x, y, 30, 30, colour, line=False)
    return img


def egg(variant):
    base_col, kind, pat_col = EGG_VARIANTS[variant]
    cx, cy, rx, ry = EGG_BOX
    mask = Image.new("L", (SIZE * SS, SIZE * SS), 0)
    ImageDraw.Draw(mask).ellipse(box(cx, cy, rx, ry), fill=255)
    body = Image.new("RGBA", (SIZE * SS, SIZE * SS), base_col)
    body.putalpha(mask)
    pat = pattern_layer(kind, pat_col)
    pat.putalpha(ImageChops.multiply(pat.getchannel("A"), mask))
    out = Image.alpha_composite(body, pat)
    d = ImageDraw.Draw(out)
    d.ellipse(box(cx, cy, rx, ry), outline=OUT, width=sc(8))
    return out


def crack(stage):
    img, d = new_canvas()
    rng = random.Random(stage)
    for _ in range(stage * 3):
        x, y = 256 + rng.randint(-40, 40), 270 + rng.randint(-40, 40)
        path = [(x, y)]
        for _ in range(4):
            x += rng.randint(-40, 40) + (30 if stage % 2 else -30)
            y += rng.randint(10, 35)
            path.append((x, y))
        line(d, path, OUT, 10)
    return img


def hammer():
    img, d = new_canvas()
    d.rounded_rectangle([sc(120), sc(120), sc(330), sc(250)], radius=sc(30), fill=(150, 150, 165, 255), outline=OUT, width=sc(8))
    d.rounded_rectangle([sc(236), sc(230), sc(282), sc(480)], radius=sc(20), fill=(190, 120, 70, 255), outline=OUT, width=sc(8))
    return img


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
    parts = []
    for f in freqs:
        parts.append(blip(f, step, decay, shape))
    return np.concatenate(parts)


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
        write_wav("toy_" + name, sweep(f0, f1, 0.35, 6, shape="sine"))


def main():
    os.makedirs(ART, exist_ok=True)
    os.makedirs(SFX, exist_ok=True)
    for name, fn in TOY_PAINTERS.items():
        save(fn(), name)
    for name, fn in CLOTHES_PAINTERS.items():
        save(fn(), name)
    for name, fn in STICKER_PAINTERS.items():
        save(fn(), name)
    for i in range(len(EGG_VARIANTS)):
        save(egg(i), "egg_%d" % i)
    for stage in range(1, 5):
        save(crack(stage), "crack_%d" % stage)
    save(hammer(), "hammer")
    make_sounds()
    print("placeholders written to", ART, "and", SFX)


if __name__ == "__main__":
    main()
