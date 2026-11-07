"""Synthetic multi-angle "wet smile" with ground truth, for testing.

A 2.5D height-field scene (lips, gums, curved upper/lower dental arch, dark oral
cavity) is rendered from several camera angles with a phone-style flash at the
camera plus a second light. Teeth are glossy (sharp Blinn-Phong lobe, which
moves across each tooth as the camera moves); lips are mildly glossy. Each
frame gets its own exposure gain, white-balance drift, sensor noise and a small
non-rigid lip motion. Ground truth = diffuse-only render of the reference view.
"""
from __future__ import annotations

import cv2
import numpy as np


def _noise(rng, h, w, sigma):
    n = rng.standard_normal((h, w)).astype(np.float32)
    return cv2.GaussianBlur(n, (0, 0), sigma) * sigma


def build_scene(h=480, w=720, seed=0):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = w / 2, h / 2
    alb = np.zeros((h, w, 3), np.float32)
    z = np.zeros((h, w), np.float32)
    gloss = np.zeros((h, w), np.float32)   # specular strength
    shin = np.full((h, w), 30.0, np.float32)
    mouth = np.zeros((h, w), bool)

    # Skin / lips background.
    tex = _noise(rng, h, w, 3) * 0.6 + _noise(rng, h, w, 1.2) * 0.5 + _noise(rng, h, w, 12) * 2.0
    alb[:] = np.float32([0.78, 0.55, 0.47])
    ax, ay = w * 0.36, h * 0.30
    r = ((xx - cx) / ax) ** 2 + ((yy - cy) / ay) ** 2
    lips = r < 1.45
    alb[lips] = np.float32([0.70, 0.28, 0.30])
    gloss[lips] = 0.25
    alb *= (1 + 0.25 * tex)[..., None]
    # Distinct non-repetitive features (pores, stubble dots, freckles).
    for _ in range(260):
        px, py = rng.uniform(0, w), rng.uniform(0, h)
        cv2.circle(alb, (int(px), int(py)), int(rng.integers(1, 4)),
                   tuple(float(c) for c in rng.uniform(0.15, 0.45, 3)), -1)
    z += 0.0007 * (xx - cx) ** 2 + 0.0004 * (yy - cy) ** 2   # face curves away
    z -= 18 * np.clip(1.45 - r, 0, 1)                         # lips bulge

    # Mouth opening.
    mouth = r < 1.0
    alb[mouth] = np.float32([0.16, 0.05, 0.06]) * (1 + 0.3 * tex[mouth])[:, None]
    gloss[mouth] = 0.03
    z[mouth] += 25

    def teeth_row(y0, y1, n, upper):
        # Irregular tooth widths so the row isn't perfectly periodic.
        wts = rng.uniform(0.7, 1.3, n)
        xs = cx - ax * 0.86 + np.concatenate([[0], np.cumsum(wts)]) / wts.sum() * ax * 1.72
        for k in range(n):
            x0, x1 = xs[k] + 1.5, xs[k + 1] - 1.5
            xc, hw = (x0 + x1) / 2, (x1 - x0) / 2
            yc, hh = (y0 + y1) / 2, (y1 - y0) / 2
            # narrower teeth towards the corners (perspective of the arch)
            dx = (xx - xc) / hw
            dy = (yy - yc) / hh
            m = (np.abs(dx) < 1) & (np.abs(dy) < 1) & mouth & ((dx ** 4 + dy ** 6) < 1)
            dome = np.sqrt(np.clip(1 - dx ** 2, 0, 1)) * np.sqrt(np.clip(1 - dy ** 6, 0, 1))
            tint = np.float32([0.93, 0.89, 0.80]) * (1 + rng.uniform(-0.04, 0.04, 3)).astype(np.float32)
            stri = 0.04 * np.sin((xx - xc) * 0.9 + rng.uniform(0, 6))
            shade_edge = 1 - 0.18 * np.abs(dy) ** 3 * (1 if upper else 1)
            col = tint[None] * (1 + 0.08 * tex[m] + stri[m])[:, None] * shade_edge[m][:, None]
            alb[m] = col
            for _ in range(int(rng.integers(1, 4))):  # stains / calculus spots
                sx, sy = xc + rng.uniform(-0.7, 0.7) * hw, yc + rng.uniform(-0.8, 0.8) * hh
                sm = m & (((xx - sx) ** 2 + (yy - sy) ** 2) < rng.uniform(4, 25))
                alb[sm] *= np.float32([0.8, 0.68, 0.5])
            arch = 0.0025 * (xc - cx) ** 2
            z[m] = (5 + arch) - 22 * dome[m] * (0.6 + 0.4 * (1 - abs(xc - cx) / ax))
            gloss[m] = 1.0
            shin[m] = 500.0

    top = cy - ay * 0.92
    teeth_row(top + 4, cy - 6, 10, True)
    teeth_row(cy + 18, cy + ay * 0.80, 10, False)
    # gums above the upper teeth
    gum = mouth & (yy < top + 10)
    alb[gum] = np.float32([0.82, 0.42, 0.46]) * (1 + 0.15 * tex[gum])[:, None]
    gloss[gum] = 0.35
    z = cv2.GaussianBlur(z, (0, 0), 1.0)
    return dict(albedo=np.clip(alb, 0, 1), z=z, gloss=gloss, shin=shin, mouth=mouth)


def _rot(yaw, pitch, roll=0.0):
    a, b, c = np.deg2rad([yaw, pitch, roll])
    ry = np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
    rx = np.array([[1, 0, 0], [0, np.cos(b), -np.sin(b)], [0, np.sin(b), np.cos(b)]])
    rz = np.array([[np.cos(c), -np.sin(c), 0], [np.sin(c), np.cos(c), 0], [0, 0, 1]])
    return (rz @ rx @ ry).astype(np.float32)


def render(scene, yaw=0.0, pitch=0.0, roll=0.0, shift=(0, 0), lip_wobble=0.0,
           specular=True, f=900.0, dist=900.0, os_=2):
    alb, z, gloss, shin = scene["albedo"], scene["z"], scene["gloss"], scene["shin"]
    h, w = z.shape
    cx, cy = w / 2, h / 2
    # Oversampled surface parameterisation.
    up = lambda a: cv2.resize(a, (w * os_, h * os_), interpolation=cv2.INTER_LINEAR)  # noqa: E731
    A, Z, G, SH = up(alb), up(z), up(gloss), up(shin)
    vv, uu = np.mgrid[0:h * os_, 0:w * os_].astype(np.float32) / os_
    if lip_wobble:
        lipzone = (Z < 0) & (Z > -19)
        vv = vv + lip_wobble * np.sin(uu / 60.0) * lipzone

    X = (uu - cx) * dist / f
    Y = (vv - cy) * dist / f
    P = np.stack([X, Y, dist + Z], -1)
    # Normals of the height field (in the reference camera frame).
    dzdu = cv2.Sobel(Z, cv2.CV_32F, 1, 0, ksize=3) / 8 * os_ * f / dist
    dzdv = cv2.Sobel(Z, cv2.CV_32F, 0, 1, ksize=3) / 8 * os_ * f / dist
    N = np.stack([dzdu, dzdv, -np.ones_like(Z)], -1)
    N /= np.linalg.norm(N, axis=-1, keepdims=True)

    R = _rot(yaw, pitch, roll)
    c = np.float32([0, 0, dist])
    Pc = (P - c) @ R.T + c + np.float32([shift[0], shift[1], 0])
    Nc = N @ R.T

    # Lights in camera frame: flash at the lens and a ring/overhead light.
    def shade(lpos, power):
        L = lpos[None, None] - Pc
        L /= np.linalg.norm(L, axis=-1, keepdims=True)
        V = -Pc / np.linalg.norm(Pc, axis=-1, keepdims=True)
        Hh = L + V
        Hh /= np.linalg.norm(Hh, axis=-1, keepdims=True)
        nl = np.clip((Nc * L).sum(-1), 0, 1)
        nh = np.clip((Nc * Hh).sum(-1), 0, 1)
        return power * nl, power * G * nh ** SH * (nl > 0)

    d1, s1 = shade(np.float32([0, 0, 0]), 0.50)
    d2, s2 = shade(np.float32([220, -260, 60]), 0.30)
    col = A * (0.15 + d1 + d2)[..., None]
    if specular:
        col = col + (1.6 * (s1 + s2))[..., None] * np.float32([1.0, 1.0, 0.98])

    # Project + z-buffer splat (nearest surface wins).
    u = f * Pc[..., 0] / Pc[..., 2] + cx
    v = f * Pc[..., 1] / Pc[..., 2] + cy
    ui, vi = np.round(u).astype(int).ravel(), np.round(v).astype(int).ravel()
    zz = Pc[..., 2].ravel()
    ok = (ui >= 0) & (ui < w) & (vi >= 0) & (vi < h)
    ui, vi, zz, cc = ui[ok], vi[ok], zz[ok], col.reshape(-1, 3)[ok]
    order = np.argsort(-zz)              # far first, near overwrites
    img = np.zeros((h, w, 3), np.float32)
    filled = np.zeros((h, w), np.uint8)
    img[vi[order], ui[order]] = cc[order]
    filled[vi[order], ui[order]] = 1
    holes = (filled == 0).astype(np.uint8)
    if holes.any():
        u8 = (np.clip(img, 0, 1) * 255).astype(np.uint8)
        img = cv2.inpaint(u8, holes, 3, cv2.INPAINT_TELEA).astype(np.float32) / 255
    return cv2.GaussianBlur(np.clip(img, 0, 1.5), (0, 0), 0.6)


def make_sequence(n=5, max_yaw=14.0, seed=0, h=480, w=720, noise=0.01):
    """Returns frames(list uint8), gt_diffuse(float, ref view), gt_spec_mask, mouth_mask, ref_index."""
    rng = np.random.default_rng(seed + 100)
    scene = build_scene(h, w, seed)
    yaws = np.linspace(-max_yaw, max_yaw, n)
    ref = n // 2
    frames = []
    for i, yw in enumerate(yaws):
        pitch = 0.0 if i == ref else rng.uniform(-4, 4)
        roll = 0.0 if i == ref else rng.uniform(-2, 2)
        shift = (0, 0) if i == ref else tuple(rng.uniform(-15, 15, 2))
        wob = 0.0 if i == ref else rng.uniform(-2.5, 2.5)
        img = render(scene, yw if i != ref else 0.0, pitch, roll, shift, wob)
        gain = 1.0 if i == ref else rng.uniform(0.88, 1.10)
        wb = np.float32([1, 1, 1]) if i == ref else (1 + rng.uniform(-0.04, 0.04, 3)).astype(np.float32)
        img = img * gain * wb + rng.normal(0, noise, img.shape).astype(np.float32)
        frames.append((np.clip(img, 0, 1) * 255).astype(np.uint8))
    gt = render(scene, 0.0, specular=False)
    full = render(scene, 0.0, specular=True)
    spec_gt = (_lum(full) - _lum(gt)) > 0.06
    mouth = render({**scene, "albedo": np.repeat(scene["mouth"][..., None].astype(np.float32), 3, -1),
                    "gloss": np.zeros_like(scene["gloss"])}, 0.0, specular=False)[..., 0] > 0.05
    return frames, np.clip(gt, 0, 1), spec_gt, mouth, ref


def _lum(img):
    return img @ np.float32([0.299, 0.587, 0.114])
