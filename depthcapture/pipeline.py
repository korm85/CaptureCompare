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
from .specular import cross_view_mask, harden, intra_frame_mask, suppress_glare


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
    min_coverage: float = 0.15        # sum of weights below this -> single-image fill
    min_valid_frac: float = 0.35      # reject a view if less of the ROI aligns
    max_align_err: float = 0.06       # reject a view if clean pixels still differ this much
    max_blob: float = 3.0             # glare blobs larger than max_blob * window^2 px are ignored
    # Fill for glare no other view can supply: "suppress" (enamel-aware, keeps
    # texture; default) | "telea" | "ns" | "lama" (needs simple-lama-inpainting)
    inpaint: str = "suppress"


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

    # Teeth ROI per frame: glare detection is calibrated against the enamel in it.
    rois, srcs = [], []
    for im in imgs:
        r, src = (None, "full-frame")
        if cfg.use_roi:
            from .roi import find_roi

            r, src = find_roi((im * 255).astype(np.uint8))
        rois.append(np.ones((h, w), np.float32) if r is None else r)
        srcs.append(src)
    specs = [intra_frame_mask(im, roi=r) for im, r in zip(imgs, rois)]
    ri = _pick_reference(imgs, specs) if cfg.reference == "auto" else int(cfg.reference)
    ref = imgs[ri]
    roi, roi_src = rois[ri], srcs[ri]
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
        clean = a.valid & roi_b & (intra_frame_mask(a.warped, roi=roi) < 0.2) & (specs[ri] < 0.2)
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

    intra = np.stack([specs[ri]] + [intra_frame_mask(x, roi=roi) for x in S[1:]])
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
    # Glints on wet enamel are small relative to a tooth. A "glare" blob bigger
    # than ~3 window^2 is mostly a brightly lit / overexposed / whiter tooth
    # surface, not a reflection, and flattening it destroys the tooth.
    scale = max(9, (min(h, w) // 32) | 1)
    core = (ref_spec > cfg.detect_thresh).astype(np.uint8)
    ncomp, lab, st, _ = cv2.connectedComponentsWithStats(core)
    too_big = np.isin(lab, [i for i in range(1, ncomp) if st[i, cv2.CC_STAT_AREA] > cfg.max_blob * scale ** 2])
    too_big = cv2.dilate(too_big.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    # Inside such a region keep only strong, sharp glints (much brighter than
    # the local enamel), which are still reflections on a bright tooth.
    if too_big.any():
        strict = intra_frame_mask(ref, roi=roi, tophat_thresh=0.08, above_enamel=0.12)
        ref_spec = np.where(too_big, np.minimum(ref_spec, strict), ref_spec)
    hard = harden(ref_spec, cfg.detect_thresh, dilate=cfg.dilate)
    # Soft strength: pixels only slightly above the glare criteria get a partial
    # correction, strong glints a full one (avoids flat, painted-looking teeth).
    alpha = cv2.GaussianBlur(hard.astype(np.float32), (0, 0), cfg.feather)
    alpha = np.minimum(alpha, np.clip(ref_spec * 1.5, 0, 1) + cv2.GaussianBlur(
        hard.astype(np.float32), (0, 0), 1.0) * 0.5)
    alpha = np.clip(alpha, 0, 1) * roi
    has_view = cover > cfg.min_coverage
    # A reflection only ever adds light: a view's value is used only where it is
    # clearly darker than the reference's glare (that view saw the surface clean).
    darker = 1 / (1 + np.exp(-np.clip(((_lum(ref) - _lum(fused)) - 0.02) / 0.015, -50, 50)))
    # Everything else under the glare mask gets the single-image fill.
    glare_prob = np.maximum(ref_spec, hard.astype(np.float32))
    if cfg.inpaint == "suppress":
        single = suppress_glare(ref, glare_prob)
    else:
        single = _inpaint(ref, hard, cfg.inpaint)
    # Plausibility: a value from another view must look like enamel at this spot
    # (same colour as the local diffuse estimate and not much darker), otherwise
    # it is a misregistered gap, gum or stain and would leave a grey/dark blotch.
    def chroma(x):
        return x / np.maximum(x.sum(-1, keepdims=True), 1e-4)

    too_dark = np.maximum(0.0, _lum(single) - _lum(fused) - 0.04)
    plaus = (np.exp(-(too_dark / 0.05) ** 2)
             * np.exp(-(np.abs(chroma(fused) - chroma(single)).sum(-1) / 0.04) ** 2))
    g = has_view * darker * plaus             # 1 = fill from real pixels of other views
    fill = g[..., None] * fused + (1 - g[..., None]) * single
    out = ref * (1 - alpha[..., None]) + fill * alpha[..., None]
    a_use = alpha * g
    holes = hard & (g <= 0.5)

    stats = {
        "n_frames": n, "n_aligned": len(stack) - 1, "reference": ri,
        "glare_mask_px": int(hard.sum()),
        "filled_from_other_views_px": int((hard & (g > 0.5)).sum()),
        "filled_single_image_px": int(holes.sum()),
        "roi": roi_src,
        "ignored_large_blobs_px": int(too_big.sum()),
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
    stats["glare_px_before"] = int((intra_frame_mask(ref, roi=roi) > 0.5).sum())
    stats["glare_px_after"] = int((intra_frame_mask(out, roi=roi) > 0.5).sum())
    return Result(out.astype(np.float32), ref, ri, ref_spec, a_use, holes, cover, roi,
                  fused=fused, aligned=aligned, stats=stats)
