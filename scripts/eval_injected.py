"""Ground truth on REAL texture: paint artificial wet glints onto clean enamel
of real photos, run the pipeline (single-image path), and measure how close the
result gets back to the original photo.

    python scripts/eval_injected.py data/smile_set1/frame_3.jpg data/smile_set1/frame_4.jpg
    # multi-frame: inject into each photo of a set in turn, restore it using
    # (a) that photo alone and (b) all photos of the set
    python scripts/eval_injected.py data/smile_set2/*.jpg --multi
"""
from __future__ import annotations

import argparse
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from depthcapture.pipeline import Config, load_images, remove_reflections  # noqa: E402
from depthcapture.roi import find_roi  # noqa: E402
from depthcapture.specular import intra_frame_mask, value_saturation  # noqa: E402


def inject(img, roi, rng, n=25):
    """Add glints shaped like the real ones: small ellipses/streaks, 4-25 px,
    additive white light with a soft falloff, some clipped."""
    h, w = img.shape[:2]
    v, s = value_saturation(img)
    clean = (roi > 0.5) & (intra_frame_mask(img, roi=roi) < 0.05) & (v > 0.55) & (s < 0.3)
    clean = cv2.erode(clean.astype(np.uint8), np.ones((25, 25), np.uint8)).astype(bool)
    ys, xs = np.nonzero(clean)
    spec = np.zeros((h, w), np.float32)
    for _ in range(n):
        j = rng.integers(len(ys))
        layer = np.zeros((h, w), np.float32)
        ax = (int(rng.uniform(2, 8)), int(rng.uniform(4, 25)))
        cv2.ellipse(layer, (int(xs[j]), int(ys[j])), ax, rng.uniform(-30, 30), 0, 360, 1.0, -1)
        layer = cv2.GaussianBlur(layer, (0, 0), rng.uniform(1.0, 3.0))
        spec = np.maximum(spec, layer * rng.uniform(0.25, 0.6))
    out = np.clip(img + spec[..., None], 0, 1)
    return out, spec > 0.05


def psnr(a, b, m):
    return float(10 * np.log10(1 / max(((a - b) ** 2)[m].mean(), 1e-10)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+")
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    ap.add_argument("--out", default="results/injected")
    ap.add_argument("--multi", action="store_true", help="also restore using the other photos of the set")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    rows = []
    from depthcapture.align import EfficientLoFTRMatcher

    matcher = EfficientLoFTRMatcher() if args.multi else None
    all_imgs = load_images(args.images, 1024) if args.multi else None
    for idx, path in enumerate(args.images):
        img = all_imgs[idx] if args.multi else load_images([path], 1024)[0]
        roi, _ = find_roi((img * 255).astype(np.uint8))
        roi = np.ones(img.shape[:2], np.float32) if roi is None else roi
        for seed in args.seeds:
            rng = np.random.default_rng(seed)
            glared, gmask = inject(img, roi, rng)
            m = gmask & (intra_frame_mask(img, roi=roi) < 0.2)
            ring = cv2.dilate(gmask.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool) & ~gmask
            modes = {"single": ([glared], 0)}
            if args.multi:
                frames = list(all_imgs)
                frames[idx] = glared
                modes["multi"] = (frames, idx)
            row = {"file": os.path.basename(path), "seed": seed, "psnr_glare_before": psnr(glared, img, m)}
            for name, (frames, ri) in modes.items():
                res = remove_reflections(frames, Config(reference=ri), matcher=matcher or (lambda *a: None))
                row[f"psnr_glare_after_{name}"] = psnr(res.output, img, m)
                row[f"psnr_surround_{name}"] = psnr(res.output, img, ring)
                row[f"from_views_{name}"] = float((res.replaced[m] > 0.3).mean()) if m.any() else 0.0
                if seed == args.seeds[0]:
                    ys, xs = np.nonzero(roi > 0.5)
                    c = lambda a: (np.clip(a[ys.min():ys.max(), xs.min():xs.max()], 0, 1) * 255).astype(np.uint8)  # noqa: E731
                    cv2.imwrite(f"{args.out}/{os.path.basename(path)}_{name}_s{seed}.jpg",
                                cv2.cvtColor(np.hstack([c(img), c(glared), c(res.output)]), cv2.COLOR_RGB2BGR))
            rows.append(row)
    for r in rows:
        print(r)
    k = lambda key: np.mean([r[key] for r in rows])  # noqa: E731
    print(f"\nMEAN injected-glare PSNR before: {k('psnr_glare_before'):.2f} dB")
    for name in ["single", "multi"]:
        if f"psnr_glare_after_{name}" in rows[0]:
            print(f"  {name:6s}: after {k(f'psnr_glare_after_{name}'):.2f} dB | surrounding enamel "
                  f"{k(f'psnr_surround_{name}'):.2f} dB | filled from other photos {100 * k(f'from_views_{name}'):.0f}%")

if __name__ == "__main__":
    main()
