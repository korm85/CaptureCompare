"""Specular-highlight detection for wet teeth.

Teeth are bright and unsaturated everywhere, so a plain "bright + white"
threshold flags clean enamel as reflection. Two cues are used instead:

* intra-frame: a highlight is brighter than its local neighbourhood at two
  scales, brighter than typical enamel, and near-neutral (``intra_frame_mask``).
* cross-frame: once frames are aligned, a highlight is view dependent, so a
  pixel that is much brighter than the per-pixel median of the stack is a
  highlight in that frame (``cross_view_mask``).
"""
from __future__ import annotations

import warnings

import cv2
import numpy as np


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -50, 50)))


def value_saturation(img: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """img: float32 RGB in [0,1]. Returns (V, S) as float32."""
    mx = img.max(axis=2)
    mn = img.min(axis=2)
    s = (mx - mn) / np.maximum(mx, 1e-4)
    return mx.astype(np.float32), s.astype(np.float32)


def intra_frame_mask(
    img: np.ndarray,
    roi: np.ndarray | None = None,
    scale: int | None = None,
    tophat_thresh: float = 0.05,
    above_enamel: float = 0.05,
    max_sat: float = 0.15,
) -> np.ndarray:
    """Soft glare probability in [0,1] from a single frame.

    Tuned on real phone photos, where enamel is itself almost neutral white
    (saturation ~0.02-0.10), so colour alone cannot separate glare from teeth.
    A pixel is glare when it is
      * brighter than its neighbourhood at two scales (white top-hat with a
        window of ``scale`` and ``2*scale+1`` px; glints are 5-60 px wide), and
      * brighter than the *local* typical enamel (normalised convolution over
        bright, low-saturation pixels) by ``above_enamel``, and
      * near-neutral (rejects wet pink gums/lips edges and stains).
    """
    h, w = img.shape[:2]
    if scale is None:
        scale = max(9, (min(h, w) // 32) | 1)
    v, s = value_saturation(img)
    tophat = np.zeros_like(v)
    for sc in (scale, 2 * scale + 1):
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (sc, sc))
        bg = cv2.GaussianBlur(cv2.morphologyEx(v, cv2.MORPH_OPEN, k), (0, 0), sc / 4)
        tophat = np.maximum(tophat, v - bg)
    region = (roi > 0.5) if roi is not None else np.ones((h, w), bool)
    cand = (region & (s < 0.25) & (v > 0.4)).astype(np.float32)
    # *Local* typical enamel brightness (teeth in shadow have dimmer enamel but
    # their glare is still glare): normalised convolution over enamel pixels.
    sig = 3 * scale
    local = cv2.GaussianBlur(v * cand, (0, 0), sig) / np.maximum(cv2.GaussianBlur(cand, (0, 0), sig), 1e-4)
    glob_v = float(np.percentile(v[cand > 0], 60)) if cand.sum() > 100 else 0.8
    enamel_v = np.where(cv2.GaussianBlur(cand, (0, 0), sig) > 0.05, local, glob_v)
    p = (
        _sigmoid((tophat - tophat_thresh) / 0.02)
        * _sigmoid((v - (enamel_v + above_enamel)) / 0.02)
        * _sigmoid((max_sat - s) / 0.03)
    )
    # Clipped pixels are always glare.
    p = np.maximum(p, (img.min(axis=2) > 0.985).astype(np.float32))
    if roi is not None:
        p *= roi
    return p.astype(np.float32)


def suppress_glare(img: np.ndarray, prob: np.ndarray, scale: int | None = None,
                   detail: float = 0.35) -> np.ndarray:
    """Single-image fallback for glare no other view can fill.

    The diffuse colour under the glare is estimated by normalised convolution
    over *clean enamel only* (bright, low-saturation, non-glare pixels), so dark
    inter-dental gaps and pink gums don't bleed in (plain inpainting does).
    A damped copy of the original fine detail is added back so the surface
    texture survives, and the result is never brighter than the input.
    Returns the corrected image; blend it with a soft mask.
    """
    h, w = img.shape[:2]
    if scale is None:
        scale = max(9, (min(h, w) // 32) | 1)
    v, s = value_saturation(img)
    support = ((prob < 0.2) & (v > 0.35) & (s < 0.35)).astype(np.float32)
    out = img.copy()
    num = np.zeros_like(img)
    den = np.zeros((h, w), np.float32)
    done = np.zeros((h, w), bool)
    # Smallest neighbourhood with enough clean support wins (keeps local colour);
    # grow it for large glare patches.
    for sig in (scale / 2, scale, 2 * scale, 4 * scale):
        n = cv2.GaussianBlur(img * support[..., None], (0, 0), sig)
        d = cv2.GaussianBlur(support, (0, 0), sig)
        take = ~done & (d > (0.25 if sig < 4 * scale else 1e-4))
        num[take], den[take] = n[take], d[take]
        done |= take
    base = num / np.maximum(den, 1e-6)[..., None]
    hi = img - cv2.GaussianBlur(img, (0, 0), 1.5)
    diffuse = np.minimum(img, base + detail * hi)
    has = done
    out[has] = diffuse[has]
    return np.clip(out, 0, 1).astype(np.float32)


def cross_view_mask(
    stack_lum: np.ndarray, valid: np.ndarray, margin: float = 0.08
) -> np.ndarray:
    """stack_lum: (N,H,W) luminance of aligned, gain-matched frames.
    valid: (N,H,W) bool. Returns (N,H,W) soft prob that frame i is specular."""
    masked = np.where(valid, stack_lum, np.nan)
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        med = np.nanmedian(masked, axis=0)
    med = np.nan_to_num(med, nan=1.0)
    excess = stack_lum - med[None]
    p = _sigmoid((excess - margin) / 0.02)
    return (p * valid).astype(np.float32)


def harden(p: np.ndarray, thresh: float = 0.5, dilate: int = 3) -> np.ndarray:
    m = (p > thresh).astype(np.uint8)
    if dilate > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * dilate + 1,) * 2)
        m = cv2.dilate(m, k)
    return m.astype(bool)
