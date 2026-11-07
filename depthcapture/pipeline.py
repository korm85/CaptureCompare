"""Multi-view specular-reflection removal for wet teeth.

Pipeline
--------
1. load + resize frames, pick a reference frame
2. mouth ROI (MediaPipe Face Landmarker, optional)
3. per-frame highlight probability (intra-frame cue)
4. align every frame to the reference (EfficientLoFTR -> MAGSAC homography
   -> DIS flow with forward/backward check)
5. per-channel gain matching (exposure / white-balance drift between shots)
6. cross-view highlight cue (brighter than the aligned per-pixel median)
7. confidence-weighted fusion of the non-specular observations
8. replace only the reference's highlight pixels (feathered), and inpaint the
   pixels that were a highlight in *every* view
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import cv2
import numpy as np

from .align import EfficientLoFTRMatcher, SIFTMatcher, align_to_reference
from .specular import cross_view_mask, harden, intra_frame_mask


@dataclass
class Config:
    max_side: int = 1024
    reference: int | str = "auto"     # index, or "auto" = sharpest of the least-glare half
    matcher: str = "efficientloftr"   # or "sift"
    use_flow: bool = True
    use_roi: bool = True
    cross_margin: float = 0.08
    feather: float = 2.5
    detect_thresh: float = 0.5
    dilate: int = 2                   # px grown around detected glare
    min_coverage: float = 0.15        # sum of weights below this -> inpaint
    min_valid_frac: float = 0.35      # reject a view if less of the ROI aligns
    max_align_err: float = 0.06       # reject a view if clean pixels still differ this much
    inpaint: str = "telea"            # "telea" | "ns" | "lama" (needs simple-lama-inpainting)


@dataclass
class Result:
    output: np.ndarray                # float32 RGB [0,1]
    reference: np.ndarray
    ref_index: int
    ref_spec: np.ndarray              # soft highlight mask of the reference
    replaced: np.ndarray              # alpha actually applied
    holes: np.ndarray                 # pixels inpainted (no clean view available)
    coverage: np.ndarray
    roi: np.ndarray
    fused: np.ndarray | None = None   # glare-free estimate from the other views
    aligned: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)


def load_images(paths, max_side=1024):
    imgs = []
    for p in paths:
        bgr = cv2.imread(str(p), cv2.IMREAD_COLOR)
        if bgr is None:
            raise ValueError(f"cannot read {p}")
        imgs.append(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    return prepare(imgs, max_side)


def prepare(imgs_u8, max_side=1024):
    """Resize all frames to the size of the first one (after max_side cap)."""
    h, w = imgs_u8[0].shape[:2]
    s = min(1.0, max_side / max(h, w))
    size = (int(round(w * s)), int(round(h * s)))
    out = []
    for im in imgs_u8:
        if (im.shape[1], im.shape[0]) != size:
            im = cv2.resize(im, size, interpolation=cv2.INTER_AREA)
        out.append(im.astype(np.float32) / 255.0)
    return out


def _sharpness(img):
    g = cv2.cvtColor((img * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY)
    return cv2.Laplacian(g, cv2.CV_64F).var()


def _pick_reference(imgs, specs):
    glare = np.array([s.mean() for s in specs])
    order = np.argsort(glare)[: max(1, (len(imgs) + 1) // 2)]
    return int(max(order, key=lambda i: _sharpness(imgs[i])))


def _gain_match(src, ref, mask):
    """Per-channel multiplicative gain so that src matches ref on `mask`."""
    if mask.sum() < 50:
        return src
    g = np.median(ref[mask], axis=0) / np.maximum(np.median(src[mask], axis=0), 1e-3)
    return np.clip(src * np.clip(g, 0.5, 2.0)[None, None], 0, 1)


def _lum(img):
    return img @ np.float32([0.299, 0.587, 0.114])


def _inpaint(img, mask, method):
    if not mask.any():
        return img
    u8 = (np.clip(img, 0, 1) * 255).astype(np.uint8)
    m = mask.astype(np.uint8) * 255
    if method == "lama":
        from PIL import Image
        from simple_lama_inpainting import SimpleLama

        out = np.asarray(SimpleLama()(Image.fromarray(u8), Image.fromarray(m)))[: u8.shape[0], : u8.shape[1]]
    else:
        flag = cv2.INPAINT_NS if method == "ns" else cv2.INPAINT_TELEA
        out = cv2.inpaint(u8, m, 7, flag)
    return out.astype(np.float32) / 255.0


def remove_reflections(imgs, cfg: Config | None = None, matcher=None) -> Result:
    """imgs: list of float32 RGB [0,1] frames of identical size."""
    cfg = cfg or Config()
    n = len(imgs)
    h, w = imgs[0].shape[:2]

    # ROI on each frame isn't needed; computed on the reference only.
    specs = [intra_frame_mask(im) for im in imgs]
    ri = _pick_reference(imgs, specs) if cfg.reference == "auto" else int(cfg.reference)
    ref = imgs[ri]

    roi, roi_src = None, "full-frame"
    if cfg.use_roi:
        from .roi import find_roi

        roi, roi_src = find_roi((ref * 255).astype(np.uint8))
    roi = np.ones((h, w), np.float32) if roi is None else roi
    roi_b = roi > 0.5

    if matcher is None:
        matcher = SIFTMatcher() if cfg.matcher == "sift" else EfficientLoFTRMatcher()

    stack, valid, conf, aligned = [ref], [np.ones((h, w), bool)], [np.ones((h, w), np.float32)], []
    for i, im in enumerate(imgs):
        if i == ri:
            continue
        a = align_to_reference(ref, im, matcher, specs[ri], specs[i], use_flow=cfg.use_flow)
        if a is None:
            aligned.append({"index": i, "ok": False})
            continue
        clean = a.valid & roi_b & (intra_frame_mask(a.warped) < 0.2) & (specs[ri] < 0.2)
        g = _gain_match(a.warped, ref, clean)
        valid_frac = float(a.valid[roi_b].mean())
        err = float(np.median(np.abs(g - ref).mean(-1)[clean])) if clean.sum() > 50 else 1.0
        info = {"index": i, "matches": a.n_matches, "inliers": a.n_inliers,
                "valid_frac": round(valid_frac, 3), "median_abs_err": round(err, 4)}
        # Views too different from the reference (e.g. a side profile vs a
        # frontal reference) cannot be warped onto it with a 2D field: drop them.
        if valid_frac < cfg.min_valid_frac or err > cfg.max_align_err:
            aligned.append({**info, "ok": False})
            continue
        stack.append(g)
        valid.append(a.valid)
        conf.append(a.confidence)
        aligned.append({**info, "ok": True})

    S = np.stack(stack)                       # (K,H,W,3)
    V = np.stack(valid)
    C = np.stack(conf)
    L = _lum(S)

    intra = np.stack([intra_frame_mask(s) for s in S])
    cross = cross_view_mask(L, V, cfg.cross_margin)
    # For the reference, only trust the cross-view cue where the *other* views
    # agree with each other; at occlusion edges misaligned views scatter and
    # would otherwise flag clean enamel next to a dark gap as glare.
    if len(S) >= 3:
        Lo = np.where(V[1:], L[1:], np.nan)
        with np.errstate(all="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            med_o = np.nanmedian(Lo, axis=0)
            mad_o = np.nanmedian(np.abs(Lo - med_o[None]), axis=0)
        consistent = np.nan_to_num(np.exp(-(mad_o / 0.04) ** 2), nan=0.0)
        z = np.clip(((L[0] - np.nan_to_num(med_o, nan=9.0)) - cfg.cross_margin) / 0.02, -50, 50)
        cross[0] = (1 / (1 + np.exp(-z))
                    * consistent)
    spec = np.maximum(intra, cross) * V       # (K,H,W)

    # Photometric agreement with the robust median suppresses residual misalignment.
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        med = np.nanmedian(np.where(V[..., None], S, np.nan), axis=0)
    med = np.nan_to_num(med, nan=0.0)
    dev = np.abs(S - med[None]).mean(-1)
    agree = np.exp(-(dev / 0.06) ** 2)

    W = C * V * (1 - spec) ** 2 * agree
    W[0] *= 0.0                               # never take the reference's own glare
    cover = W.sum(0)
    fused = (W[..., None] * S).sum(0) / np.maximum(cover, 1e-6)[..., None]

    ref_spec = spec[0] * roi
    hard = harden(ref_spec, cfg.detect_thresh, dilate=cfg.dilate)
    alpha = cv2.GaussianBlur(hard.astype(np.float32), (0, 0), cfg.feather)
    alpha = np.maximum(alpha, ref_spec) * roi
    has_view = cover > cfg.min_coverage
    holes = hard & ~has_view
    # A reflection only ever adds light: never replace a pixel with something
    # brighter, and fade out where the replacement is not clearly darker.
    darker = 1 / (1 + np.exp(-((_lum(ref) - _lum(fused)) - 0.02) / 0.015))
    a_use = alpha * has_view * darker
    out = ref * (1 - a_use[..., None]) + fused * a_use[..., None]
    out = _inpaint(out, holes, cfg.inpaint)

    stats = {
        "n_frames": n, "n_aligned": len(stack) - 1, "reference": ri,
        "ref_spec_px": int(hard.sum()),
        "replaced_from_views_px": int((hard & has_view).sum()),
        "inpainted_px": int(holes.sum()),
        "roi": roi_src,
    }
    # Hold-out check on real data (no ground truth needed): on reference pixels
    # that are NOT glare, the fusion of the other views should reproduce the
    # reference. Its error is what a replaced glare pixel can be expected to have.
    hold = roi_b & (ref_spec < 0.1) & (cover > cfg.min_coverage) & (_lum(ref) > 0.35)
    if hold.sum() > 100:
        mse = float(((fused - ref) ** 2)[hold].mean())
        stats["holdout_psnr_db"] = round(10 * np.log10(1 / max(mse, 1e-10)), 2)
        stats["holdout_mae"] = round(float(np.abs(fused - ref)[hold].mean()), 4)
        stats["holdout_px"] = int(hold.sum())
    stats["glare_px_before"] = int((intra_frame_mask(ref) * roi > 0.5).sum())
    stats["glare_px_after"] = int((intra_frame_mask(out) * roi > 0.5).sum())
    return Result(out.astype(np.float32), ref, ri, ref_spec, a_use, holes, cover, roi,
                  fused=fused, aligned=aligned, stats=stats)
