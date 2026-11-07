"""Multi-view alignment: EfficientLoFTR matches -> robust homography -> dense
DIS optical-flow refinement.

A single homography is not enough for a smile captured from several angles
(the dental arch is curved, the lips move), so the homography only removes the
large motion and dense flow handles parallax and non-rigid motion. Flow is
computed on "de-highlighted" images, otherwise moving reflections drag it.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from scipy.interpolate import griddata
from scipy.spatial import cKDTree

from .specular import harden, intra_frame_mask


@dataclass
class Alignment:
    warped: np.ndarray        # (H,W,3) frame resampled into reference geometry
    valid: np.ndarray         # (H,W) bool, pixel has a trustworthy correspondence
    confidence: np.ndarray    # (H,W) float in [0,1]
    homography: np.ndarray
    n_matches: int
    n_inliers: int


class EfficientLoFTRMatcher:
    """zju-community/efficientloftr via Hugging Face transformers."""

    def __init__(self, model_id: str = "zju-community/efficientloftr",
                 threshold: float = 0.2, device: str | None = None, long_side: int = 832):
        import torch
        from transformers import AutoImageProcessor, AutoModelForKeypointMatching

        self.torch = torch
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.processor = AutoImageProcessor.from_pretrained(model_id)
        self.model = AutoModelForKeypointMatching.from_pretrained(model_id).to(self.device).eval()
        self.threshold = threshold
        self.long_side = long_side

    def __call__(self, img0_u8: np.ndarray, img1_u8: np.ndarray):
        from PIL import Image

        a, b = Image.fromarray(img0_u8), Image.fromarray(img1_u8)
        # Keep the aspect ratio (default processor squashes everything to 480x640).
        h, w = img0_u8.shape[:2]
        s = self.long_side / max(h, w)
        size = {"height": max(32, int(round(h * s / 32)) * 32), "width": max(32, int(round(w * s / 32)) * 32)}
        inputs = self.processor([[a, b]], size=size, return_tensors="pt").to(self.device)
        with self.torch.inference_mode():
            out = self.model(**inputs)
        # Decode the raw outputs ourselves. In the installed transformers version
        # `post_process_keypoint_matching` pairs keypoints0[i] with keypoints1[i]
        # instead of keypoints1[matches[i]] (and truncates to int), which yields
        # almost entirely wrong correspondences (verified on a known warp).
        kp = out.keypoints[0].float().cpu().numpy()        # (2,N,2) normalised [0,1]
        m0 = out.matches[0, 0].cpu().numpy()               # index into image-1 keypoints
        sc = out.matching_scores[0, 0].float().cpu().numpy()
        ok = (m0 > -1) & (sc > self.threshold)
        wh0 = np.float32([img0_u8.shape[1], img0_u8.shape[0]])
        wh1 = np.float32([img1_u8.shape[1], img1_u8.shape[0]])
        return (kp[0][ok] * wh0).astype(np.float32), (kp[1][m0[ok]] * wh1).astype(np.float32), sc[ok]


class SIFTMatcher:
    """Classical baseline (OpenCV SIFT + ratio test)."""

    def __init__(self, ratio: float = 0.8):
        self.sift = cv2.SIFT_create(nfeatures=8000)
        self.ratio = ratio

    def __call__(self, img0_u8, img1_u8):
        g0 = cv2.cvtColor(img0_u8, cv2.COLOR_RGB2GRAY)
        g1 = cv2.cvtColor(img1_u8, cv2.COLOR_RGB2GRAY)
        k0, d0 = self.sift.detectAndCompute(g0, None)
        k1, d1 = self.sift.detectAndCompute(g1, None)
        if d0 is None or d1 is None:
            return np.zeros((0, 2), np.float32), np.zeros((0, 2), np.float32), np.zeros(0, np.float32)
        knn = cv2.BFMatcher(cv2.NORM_L2).knnMatch(d0, d1, k=2)
        good = [m for m, n in (p for p in knn if len(p) == 2) if m.distance < self.ratio * n.distance]
        p0 = np.float32([k0[m.queryIdx].pt for m in good]).reshape(-1, 2)
        p1 = np.float32([k1[m.trainIdx].pt for m in good]).reshape(-1, 2)
        return p0, p1, np.ones(len(good), np.float32)


def dehighlight(img: np.ndarray, spec_prob: np.ndarray) -> np.ndarray:
    """Fill highlight pixels with a fast inpaint so they don't attract matches/flow."""
    m = harden(spec_prob, 0.4, dilate=2).astype(np.uint8)
    u8 = (np.clip(img, 0, 1) * 255).astype(np.uint8)
    if m.any():
        u8 = cv2.inpaint(u8, m, 5, cv2.INPAINT_TELEA)
    return u8


def _flow_gray(u8: np.ndarray) -> np.ndarray:
    g = cv2.cvtColor(u8, cv2.COLOR_RGB2GRAY)
    return cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(g)


def align_to_reference(
    ref: np.ndarray, frame: np.ndarray, matcher, ref_spec=None, frame_spec=None,
    use_flow: bool = True, fb_thresh: float = 1.5,
) -> Alignment | None:
    """ref/frame: float32 RGB [0,1], same size. Returns None if alignment fails."""
    h, w = ref.shape[:2]
    ref_spec = intra_frame_mask(ref) if ref_spec is None else ref_spec
    frame_spec = intra_frame_mask(frame) if frame_spec is None else frame_spec
    ref_u8, frm_u8 = dehighlight(ref, ref_spec), dehighlight(frame, frame_spec)

    k0, k1, _ = matcher(ref_u8, frm_u8)
    n_matches = len(k0)
    if n_matches < 8:
        return None
    # Drop matches landing on highlights in either image (view-dependent => wrong).
    def on_spec(p, s):
        xi = np.clip(p[:, 0].round().astype(int), 0, w - 1)
        yi = np.clip(p[:, 1].round().astype(int), 0, h - 1)
        return s[yi, xi] > 0.3
    keep = ~(on_spec(k0, ref_spec) | on_spec(k1, frame_spec))
    k0, k1 = k0[keep], k1[keep]
    if len(k0) < 8:
        return None
    # Loose threshold: the homography only removes the bulk motion; parallax of
    # the curved arch is handled by the dense stage below.
    H, inl = cv2.findHomography(k1, k0, cv2.USAC_MAGSAC, 0.02 * max(h, w),
                                maxIters=5000, confidence=0.999)
    if H is None:
        return None
    n_inliers = int(inl.sum())

    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    Hinv = np.linalg.inv(H)

    def h_map(H_):  # ref pixel -> frame pixel through a homography
        p = np.stack([gx, gy, np.ones_like(gx)], -1) @ H_.T
        return (p[..., 0] / p[..., 2]).astype(np.float32), (p[..., 1] / p[..., 2]).astype(np.float32)

    mx, my = h_map(Hinv)
    conf = np.ones((h, w), np.float32)
    support = np.ones((h, w), bool)

    if use_flow:
        # Stage 1: dense field from the semi-dense matches themselves. Each match
        # gives the residual (frame position) - (homography prediction) at k0.
        pred = cv2.perspectiveTransform(k0[None], Hinv)[0]
        res = k1 - pred
        tree = cKDTree(k0)
        nn = min(12, len(k0))
        _, idx = tree.query(k0, k=nn)
        local_med = np.median(res[idx], axis=1)
        ok = np.linalg.norm(res - local_med, axis=1) < max(3.0, 0.006 * max(h, w))
        k0g, resg = k0[ok], res[ok]
        if len(k0g) >= 8:
            field = _interp_field(k0g, resg, h, w)
            mx, my = mx + field[..., 0].astype(np.float32), my + field[..., 1].astype(np.float32)
            d, _ = cKDTree(k0g).query(np.stack([gx.ravel(), gy.ravel()], 1), k=1)
            support = d.reshape(h, w) < 0.04 * max(h, w)

        # Stage 2: small residual with DIS flow + forward/backward check.
        frm_w8 = cv2.remap(frm_u8, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
        g_ref, g_frm = _flow_gray(ref_u8), _flow_gray(frm_w8)
        fwd = dis.calc(g_ref, g_frm, None)
        bwd = dis.calc(g_frm, g_ref, None)
        fwd = np.clip(fwd, -0.02 * max(h, w), 0.02 * max(h, w))  # residual must be small
        ax, ay = gx + fwd[..., 0], gy + fwd[..., 1]
        bwd_at = cv2.remap(bwd, ax, ay, cv2.INTER_LINEAR)
        fb = np.linalg.norm(fwd + bwd_at, axis=2)
        conf = np.exp(-(fb / fb_thresh) ** 2).astype(np.float32)
        mx = cv2.remap(mx, ax, ay, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        my = cv2.remap(my, ax, ay, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

    frame_w = cv2.remap(frame, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    valid = (mx >= 0) & (mx <= w - 1) & (my >= 0) & (my <= h - 1) & support
    if use_flow:
        valid &= fb < 3 * fb_thresh
    return Alignment(frame_w.astype(np.float32), valid, conf * valid, H, n_matches, n_inliers)


def _interp_field(pts: np.ndarray, vals: np.ndarray, h: int, w: int, step: int = 8) -> np.ndarray:
    """Smooth dense (H,W,2) field from scattered samples (linear inside the
    convex hull, nearest outside), computed on a coarse grid then upsampled."""
    gh, gw = (h + step - 1) // step, (w + step - 1) // step
    cy, cx = np.mgrid[0:gh, 0:gw].astype(np.float32) * step
    q = np.stack([cx.ravel(), cy.ravel()], 1)
    out = np.empty((gh * gw, 2), np.float32)
    for c in range(2):
        lin = griddata(pts, vals[:, c], q, method="linear")
        near = griddata(pts, vals[:, c], q, method="nearest")
        out[:, c] = np.where(np.isnan(lin), near, lin)
    f = out.reshape(gh, gw, 2)
    f = cv2.GaussianBlur(f, (0, 0), 1.0)
    return cv2.resize(f, (gw * step, gh * step), interpolation=cv2.INTER_LINEAR)[:h, :w]
