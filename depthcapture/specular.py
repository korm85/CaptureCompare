"""Specular-highlight detection for wet teeth.

Teeth are bright and unsaturated everywhere, so a plain "bright + white"
threshold flags clean enamel as reflection. Two cues are used instead:

* intra-frame: a highlight is much brighter than its *local* neighbourhood
  (white top-hat on the value channel) and close to neutral in colour.
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
    tophat_thresh: float = 0.10,
    sat_thresh: float = 0.30,
    min_value: float = 0.62,
    sat_drop_thresh: float = 0.02,
) -> np.ndarray:
    """Soft specular probability in [0,1] from a single frame.

    ``scale`` is the background window (px); default ~1/32 of the short side,
    i.e. wider than a highlight streak but narrower than a tooth.
    """
    h, w = img.shape[:2]
    if scale is None:
        scale = max(9, (min(h, w) // 32) | 1)
    v, s = value_saturation(img)
    # Local background: morphological opening removes small bright blobs.
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (scale, scale))
    background = cv2.morphologyEx(v, cv2.MORPH_OPEN, k)
    background = cv2.GaussianBlur(background, (0, 0), scale / 4)
    tophat = v - background
    # Dichromatic cue: a reflection carries the light's (white) colour, so it
    # *desaturates* the yellowish enamel underneath. Local enamel saturation is
    # estimated by a median filter (ignores thin streaks and small stains). Tooth edges
    # and the bright rim around stains are brighter than their surroundings
    # but keep the enamel's colour, so this cue rejects them.
    s_bg = cv2.medianBlur((s * 255).astype(np.uint8), min(scale, 255)).astype(np.float32) / 255
    s_bg = cv2.GaussianBlur(s_bg, (0, 0), scale / 4)
    sat_drop = s_bg - s
    p = (
        _sigmoid((tophat - tophat_thresh) / 0.025)
        * _sigmoid((sat_thresh - s) / 0.05)
        * _sigmoid((v - min_value) / 0.03)
        * _sigmoid((sat_drop - sat_drop_thresh) / 0.015)
    )
    # Clipped pixels are always highlights.
    p = np.maximum(p, (img.min(axis=2) > 0.985).astype(np.float32))
    if roi is not None:
        p *= roi
    return p.astype(np.float32)


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
