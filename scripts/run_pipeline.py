"""Remove wet-teeth reflections from a set of photos taken from several angles.

    python scripts/run_pipeline.py data/smile_set1/*.jpg --out results/smile_set1
    python scripts/run_pipeline.py imgs/*.jpg --reference 3 --matcher sift

Writes: output.png, compare.jpg (input | output | glare mask), masks.jpg,
report.json (alignment per view, glare before/after, hold-out accuracy).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from depthcapture.pipeline import Config, load_images, remove_reflections  # noqa: E402


def _u8(x):
    return (np.clip(x, 0, 1) * 255).astype(np.uint8)


def save_masks(res, out_dir, names):
    """Reflection masks only, drawn on the UNEDITED reference photo.
    red = reflection found in this photo itself, blue = added because the other
    photos are clearly darker at that spot, yellow outline = large bright area
    deliberately treated as lit enamel (not edited), grey = outside teeth area."""
    os.makedirs(out_dir, exist_ok=True)
    ref = res.reference
    ov = ref.copy()
    ov[res.roi < 0.5] *= 0.45
    ov[res.mask_single] = ov[res.mask_single] * 0.25 + np.float32([0.95, 0.1, 0.1]) * 0.75
    ov[res.mask_cross] = ov[res.mask_cross] * 0.25 + np.float32([0.1, 0.4, 1.0]) * 0.75
    ign = res.ignored_bright.astype(np.uint8)
    edge = ign - cv2.erode(ign, np.ones((3, 3), np.uint8))
    ov[edge > 0] = [1.0, 0.9, 0.0]
    binary = np.dstack([res.glare_mask.astype(np.float32)] * 3)
    cv2.imwrite(f"{out_dir}/mask_overlay_full.png", cv2.cvtColor(_u8(ov), cv2.COLOR_RGB2BGR))
    cv2.imwrite(f"{out_dir}/mask_binary_full.png", _u8(binary))
    ys, xs = np.nonzero(res.roi > 0.5)
    pad = 20
    y0, y1 = max(ys.min() - pad, 0), ys.max() + pad
    x0, x1 = max(xs.min() - pad, 0), xs.max() + pad
    crop = lambda a: _u8(a[y0:y1, x0:x1]).copy()  # noqa: E731
    tiles = [crop(ref), crop(ov), crop(binary)]
    for t, lab in zip(tiles, ["original (unedited)", "red=glare, blue=glare vs other photos", "final mask"]):
        cv2.putText(t, lab, (10, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
    cv2.imwrite(f"{out_dir}/masks.jpg", cv2.cvtColor(np.hstack(tiles), cv2.COLOR_RGB2BGR))
    rep = {"reference": names[res.ref_index],
           "mask_px": int(res.glare_mask.sum()),
           "found_in_photo_px": int(res.mask_single.sum()),
           "added_by_other_photos_px": int(res.mask_cross.sum()),
           "ignored_bright_area_px": int(res.ignored_bright.sum()),
           "teeth_area_px": int((res.roi > 0.5).sum())}
    with open(f"{out_dir}/masks.json", "w") as f:
        json.dump(rep, f, indent=1)
    return rep


def save_outputs(res, out_dir, names):
    os.makedirs(out_dir, exist_ok=True)
    cv2.imwrite(f"{out_dir}/output.png", cv2.cvtColor(_u8(res.output), cv2.COLOR_RGB2BGR))
    cv2.imwrite(f"{out_dir}/reference.png", cv2.cvtColor(_u8(res.reference), cv2.COLOR_RGB2BGR))

    overlay = res.reference.copy()
    overlay[res.replaced > 0.3] = overlay[res.replaced > 0.3] * 0.3 + np.float32([0, 0.7, 0])  # green: from other views
    overlay[res.holes] = overlay[res.holes] * 0.3 + np.float32([0.7, 0, 0.7])                  # magenta: single-image fill
    ys, xs = np.nonzero(res.roi > 0.5)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    crop = lambda a: _u8(a[y0:y1, x0:x1])  # noqa: E731
    tiles = [crop(res.reference), crop(res.output), crop(overlay)]
    for t, lab in zip(tiles, ["input (reference view)", "reflections removed", "green=from other photos, magenta=single-image fill"]):
        cv2.putText(t, lab, (10, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 0), 2)
    cv2.imwrite(f"{out_dir}/compare.jpg", cv2.cvtColor(np.hstack(tiles), cv2.COLOR_RGB2BGR))

    report = {"inputs": names, "reference": names[res.ref_index], "stats": res.stats,
              "views": [{**a, "file": names[a["index"]]} for a in res.aligned]}
    with open(f"{out_dir}/report.json", "w") as f:
        json.dump(report, f, indent=1)
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("images", nargs="+")
    ap.add_argument("--out", default="results/run")
    ap.add_argument("--reference", default="auto", help="index into the image list, or 'auto'")
    ap.add_argument("--matcher", default="efficientloftr", choices=["efficientloftr", "sift"])
    ap.add_argument("--max-side", type=int, default=1024)
    ap.add_argument("--no-flow", action="store_true")
    ap.add_argument("--no-roi", action="store_true")
    ap.add_argument("--inpaint", default="suppress", choices=["suppress", "telea", "ns", "lama"])
    ap.add_argument("--masks-only", action="store_true",
                    help="only write the reflection masks on the unedited photo (no edited image)")
    args = ap.parse_args()

    names = [os.path.basename(p) for p in args.images]
    imgs = load_images(args.images, args.max_side)
    ref = args.reference if args.reference == "auto" else int(args.reference)
    cfg = Config(max_side=args.max_side, reference=ref, matcher=args.matcher,
                 use_flow=not args.no_flow, use_roi=not args.no_roi, inpaint=args.inpaint)
    t = time.time()
    res = remove_reflections(imgs, cfg)
    res.stats["seconds"] = round(time.time() - t, 1)
    if args.masks_only:
        print(json.dumps(save_masks(res, args.out, names), indent=1))
        return
    report = save_outputs(res, args.out, names)
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
