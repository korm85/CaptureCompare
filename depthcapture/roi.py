"""Mouth region of interest via MediaPipe Face Landmarker (Apache-2.0).

Falls back to the full frame when no face is found (e.g. tight intra-oral
crops, where the whole image is already the region of interest).
"""
from __future__ import annotations

import os
import urllib.request

import cv2
import numpy as np

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
DEFAULT_MODEL = os.path.expanduser("~/.cache/depthcapture/face_landmarker.task")

# Inner-lip contour indices of the 478-point MediaPipe face mesh.
INNER_LIPS = [78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308,
              324, 318, 402, 317, 14, 87, 178, 88, 95]

_landmarker = None


def _get_landmarker(model_path: str = DEFAULT_MODEL):
    global _landmarker
    if _landmarker is not None:
        return _landmarker
    from mediapipe.tasks.python import BaseOptions, vision

    if not os.path.exists(model_path):
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        urllib.request.urlretrieve(MODEL_URL, model_path)
    opts = vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=model_path), num_faces=1
    )
    _landmarker = vision.FaceLandmarker.create_from_options(opts)
    return _landmarker


def teeth_roi_color(img_u8: np.ndarray, grow: float = 0.06) -> np.ndarray | None:
    """Fallback for close-ups where no full face is visible (MediaPipe needs
    eyes/nose): enamel-coloured pixels (yellowish hue, moderate saturation,
    bright; excludes grey beard hairs and pink lips/skin), keep the main
    cluster, take its convex hull and grow it."""
    h, w = img_u8.shape[:2]
    hsv = cv2.cvtColor(img_u8, cv2.COLOR_RGB2HSV).astype(np.float32)
    hh, s, v = hsv[..., 0], hsv[..., 1] / 255, hsv[..., 2] / 255
    seed = ((hh > 12) & (hh < 35) & (s > 0.12) & (s < 0.6) & (v > 0.45)).astype(np.uint8)
    seed = cv2.morphologyEx(seed, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    n, lab, st, cen = cv2.connectedComponentsWithStats(seed)
    if n <= 1:
        return None
    # Keep components near the largest one (teeth come in a cluster).
    big = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    keep = [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] > 150
            and np.linalg.norm(cen[i] - cen[big]) < 0.35 * max(h, w)]
    pts = np.column_stack(np.nonzero(np.isin(lab, keep)))[:, ::-1].astype(np.int32)
    if len(pts) < 500:
        return None
    m = np.zeros((h, w), np.uint8)
    cv2.fillConvexPoly(m, cv2.convexHull(pts), 1)
    r = int(grow * max(h, w))
    m = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1,) * 2))
    return m.astype(np.float32)


def find_roi(img_u8: np.ndarray) -> tuple[np.ndarray | None, str]:
    m = mouth_mask(img_u8)
    if m is not None:
        return m, "mediapipe"
    m = teeth_roi_color(img_u8)
    if m is not None:
        return m, "enamel-colour"
    return None, "full-frame"


def mouth_mask(img_u8: np.ndarray, pad: int = 6) -> np.ndarray | None:
    """img_u8: uint8 RGB. Returns float32 mask (1 inside the open mouth) or None."""
    try:
        import mediapipe as mp

        lm = _get_landmarker()
        res = lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(img_u8)))
    except Exception:
        return None
    if not res.face_landmarks:
        return None
    h, w = img_u8.shape[:2]
    pts = np.array([[res.face_landmarks[0][i].x * w, res.face_landmarks[0][i].y * h]
                    for i in INNER_LIPS], np.int32)
    m = np.zeros((h, w), np.uint8)
    cv2.fillPoly(m, [pts], 1)
    if pad:
        m = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * pad + 1,) * 2))
    return m.astype(np.float32)
