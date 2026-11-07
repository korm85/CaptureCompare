"""Score the reflection-removal pipeline against baselines on synthetic
multi-angle wet-teeth sequences with ground truth.

    python scripts/eval_synthetic.py --seeds 0 1 2 --frames 5 --out results/synthetic
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
from depthcapture.align import EfficientLoFTRMatcher, SIFTMatcher, align_to_reference  # noqa: E402
from depthcapture.pipeline import Config, _gain_match, prepare, remove_reflections  # noqa: E402
from depthcapture.specular import harden, intra_frame_mask  # noqa: E402
from depthcapture.synth import make_sequence  # noqa: E402


def lum(x):
    return x @ np.float32([0.299, 0.587, 0.114])


def psnr(a, b, m):
    if m.sum() == 0:
        return float("nan")
    mse = ((a - b) ** 2)[m].mean()
    return float(10 * np.log10(1.0 / max(mse, 1e-10)))


def metrics(out, gt, spec_gt, mouth):
    hl = cv2.dilate(spec_gt.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool) & mouth
    clean = mouth & ~hl
    resid = (lum(out) - lum(gt)) > 0.08
    return {
        "psnr_highlights": psnr(out, gt, hl),
        "psnr_mouth": psnr(out, gt, mouth),
        "psnr_clean_px": psnr(out, gt, clean),
        "residual_glare_pct": float(100 * resid[spec_gt & mouth].mean()),
    }


def detection_scores(pred, spec_gt, mouth):
    p, g = pred & mouth, spec_gt & mouth
    tp = (p & g).sum()
    return {"precision": float(tp / max(p.sum(), 1)), "recall": float(tp / max(g.sum(), 1))}


def stack_baselines(frames, ref_i, matcher):
    ref = frames[ref_i]
    specs = [intra_frame_mask(f) for f in frames]
    S, V = [ref], [np.ones(ref.shape[:2], bool)]
    for i, f in enumerate(frames):
        if i == ref_i:
            continue
        a = align_to_reference(ref, f, matcher, specs[ref_i], specs[i])
        if a is None:
            continue
        S.append(_gain_match(a.warped, ref, a.valid & (specs[ref_i] < 0.2)))
        V.append(a.valid)
    S, V = np.stack(S), np.stack(V)
    Sm = np.where(V[..., None], S, np.nan)
    mn = np.nan_to_num(np.nanmin(Sm, 0))
    md = np.nan_to_num(np.nanmedian(Sm, 0))
    return mn, md


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    ap.add_argument("--frames", type=int, default=5)
    ap.add_argument("--max-yaw", type=float, default=14.0)
    ap.add_argument("--out", default="results/synthetic")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    loftr, sift = EfficientLoFTRMatcher(), SIFTMatcher()
    rows = []
    for seed in args.seeds:
        frames_u8, gt, spec_gt, mouth, ri = make_sequence(args.frames, args.max_yaw, seed)
        frames = prepare(frames_u8, 10_000)
        ref = frames[ri]
        res = {}
        res["reference (no-op)"] = ref
        det = harden(intra_frame_mask(ref), 0.5, 2)
        u8 = (ref * 255).astype(np.uint8)
        res["single-image inpaint"] = cv2.inpaint(u8, det.astype(np.uint8), 7, cv2.INPAINT_TELEA) / 255.0
        mn, md = stack_baselines(frames, ri, loftr)
        res["aligned min-fusion"] = mn
        res["aligned median-fusion"] = md
        timings = {}
        for name, cfg, m in [
            ("pipeline: LoFTR, homography only", Config(reference=ri, use_flow=False, use_roi=False), loftr),
            ("pipeline: SIFT + flow", Config(reference=ri, use_roi=False), sift),
            ("pipeline: EfficientLoFTR + flow", Config(reference=ri, use_roi=False), loftr),
        ]:
            t = time.time()
            r = remove_reflections(frames, cfg, matcher=m)
            timings[name] = time.time() - t
            res[name] = r.output
            if name.endswith("LoFTR + flow"):
                main_res = r
        for name, out in res.items():
            row = {"seed": seed, "method": name, **metrics(out.astype(np.float32), gt, spec_gt, mouth)}
            if name in timings:
                row["seconds"] = round(timings[name], 2)
            rows.append(row)
        rows.append({"seed": seed, "method": "_detection (final ref mask)",
                     **detection_scores(main_res.replaced > 0.5, spec_gt, mouth),
                     "inpainted_pct_of_hl": float(100 * (main_res.holes & spec_gt).sum() / max(spec_gt.sum(), 1))})

        # Visual panel: ref | GT | single inpaint | min | median | proposed | |diff|
        ys, xs = np.where(mouth)
        y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
        crop = lambda a: (np.clip(a[y0:y1, x0:x1], 0, 1) * 255).astype(np.uint8)  # noqa: E731
        diff = np.clip(np.abs(main_res.output - gt) * 4, 0, 1)
        tiles = [ref, gt, res["single-image inpaint"], mn, md, main_res.output, diff]
        labels = ["input (ref)", "ground truth", "1-img inpaint", "min-fusion", "median", "PIPELINE", "|err| x4"]
        out_tiles = []
        for t, lab in zip(tiles, labels):
            c = crop(t).copy()
            cv2.putText(c, lab, (8, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
            out_tiles.append(c)
        pad = np.zeros_like(out_tiles[0])
        grid = np.vstack([np.hstack(out_tiles[:4]), np.hstack(out_tiles[4:] + [pad])])
        cv2.imwrite(f"{args.out}/panel_seed{seed}.jpg", cv2.cvtColor(grid, cv2.COLOR_RGB2BGR))
        inputs = np.hstack([crop(f) for f in frames])
        cv2.imwrite(f"{args.out}/inputs_seed{seed}.jpg", cv2.cvtColor(inputs, cv2.COLOR_RGB2BGR))

    with open(f"{args.out}/metrics.json", "w") as f:
        json.dump(rows, f, indent=1)
    # Mean table
    methods = list(dict.fromkeys(r["method"] for r in rows))
    print(f"{'method':38s} {'PSNR hl':>8s} {'PSNR mouth':>10s} {'PSNR clean':>10s} {'glare %':>8s}")
    for m in methods:
        rs = [r for r in rows if r["method"] == m]
        if m.startswith("_"):
            print(f"{m:38s} precision={np.mean([r['precision'] for r in rs]):.2f} "
                  f"recall={np.mean([r['recall'] for r in rs]):.2f} "
                  f"inpainted={np.mean([r['inpainted_pct_of_hl'] for r in rs]):.1f}% of highlights")
            continue
        avg = lambda k: np.nanmean([r[k] for r in rs])  # noqa: E731
        print(f"{m:38s} {avg('psnr_highlights'):8.2f} {avg('psnr_mouth'):10.2f} "
              f"{avg('psnr_clean_px'):10.2f} {avg('residual_glare_pct'):8.1f}")


if __name__ == "__main__":
    main()
