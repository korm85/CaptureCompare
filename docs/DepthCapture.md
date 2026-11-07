# DepthCapture: removing wet-teeth reflections from multi-angle photos (POC)

## 1. Audit of the earlier suggestion

| Earlier claim | Verdict after building and testing |
|---|---|
| Align frames with EfficientLoFTR + homography | **Partly wrong.** A homography can't model a curved dental arch seen from several angles, or moving lips. It only removes the bulk motion. A dense, non-rigid field is required (see §3). |
| Use EfficientLoFTR through `transformers` | **Right model, broken glue.** In the installed `transformers` version, `post_process_keypoint_matching` pairs `keypoints0[i]` with `keypoints1[i]` instead of `keypoints1[matches[i]]`, and truncates coordinates to int. On a known rotation, under 0.1 % of its matches were correct. We decode the raw outputs ourselves; `tests/test_depthcapture.py` guards this. |
| Detect highlights by "bright + low saturation" | **Wrong for teeth.** Enamel is itself bright and pale, so this flags whole teeth. We use a local top-hat (brighter than the neighbourhood) **and** a local saturation drop (a reflection is white, enamel is yellowish), plus a cross-view cue. |
| Fuse with per-pixel minimum | **Rejected.** On the benchmark it darkens and damages clean enamel (PSNR on clean pixels about 22 dB vs 38 dB untouched). We use confidence-weighted fusion of glare-free observations, applied only to the reference's glare pixels. |
| Depth Anything V2 helps | **Not needed in the core path.** It predicts relative depth only. It neither detects nor removes reflections, and wet highlights corrupt its depth. Left out. It's useful later if you want 3D or a depth-aware ROI. |
| Cross-polarised lighting is the most reliable fix | **Still true, and the real photos confirm it** (see §5). |

## 2. Libraries and models

| Component | Library / model | License | Role |
|---|---|---|---|
| Matching | `zju-community/efficientloftr` via `transformers` + `torch` | Apache-2.0 | Semi-dense correspondences between views |
| Robust fit | OpenCV `findHomography(USAC_MAGSAC)` | Apache-2.0 | Bulk motion |
| Dense warp | SciPy `griddata` + `cKDTree` | BSD | Match field with local outlier rejection |
| Refinement | OpenCV DIS optical flow (+ forward/backward check) | Apache-2.0 | Last few pixels; per-pixel confidence |
| Mouth ROI | MediaPipe Face Landmarker (needs a full face) → enamel-colour fallback | Apache-2.0 | Restrict edits to the teeth |
| Hole filling | OpenCV Telea (default); optional LaMa via `simple-lama-inpainting` | Apache-2.0 | Glare seen in **every** view |
| Baseline matcher | OpenCV SIFT | Apache-2.0 | Comparison only |

Install with `pip install -r requirements-depthcapture.txt`. It runs on CPU; about 35–40 s for 6 photos at 1024 px.

## 3. Pipeline (`depthcapture/pipeline.py`)

```
photos (N views) ──► resize ──► per-frame glare probability (top-hat × saturation-drop)
                                   │
reference (least glare, sharpest, or --reference) ──► mouth ROI (MediaPipe / enamel colour)
                                   │
for each other view:  EfficientLoFTR (glare pixels masked) ─► MAGSAC homography
                      ─► dense field from matches (local-median outlier rejection)
                      ─► DIS flow residual + forward/backward confidence
                      ─► reject view if <35 % of ROI aligns or clean pixels disagree
                      ─► per-channel gain match (exposure / white balance)
                                   │
cross-view glare cue (brighter than the other views' consistent median)
                                   │
weighted fusion of glare-free, well-aligned observations
                                   │
replace ONLY reference glare pixels (feathered; only with darker values)
                                   │
pixels that are glare in every usable view ─► inpaint (flagged in the report)
```

Run it on a folder of photos:

```
python scripts/run_pipeline.py data/smile_set1/*.jpg --reference 3 --out results/smile_set1_ref4
```

Outputs: `output.png`, `compare.jpg` (input | result | where pixels came from), `report.json`. The report covers each view's alignment, glare before/after, and a hold-out accuracy figure.

## 4. Synthetic benchmark (ground truth available)

`scripts/eval_synthetic.py` renders a glossy curved dental arch from 5 angles (±14° yaw, random pitch/roll/shift, lip motion, exposure/white-balance drift, sensor noise). It has a co-located "phone flash" and a second light. The ground truth is the diffuse-only render.

RESULTS_TABLE

## 5. Real photos (`data/smile_set1`, 6 phone photos)

REAL_RESULTS

## 6. What to change to get a good result
1. **Capture.** Cross-polarised flash (a polariser on the light, a crossed one on the lens) removes wet-surface reflections optically. That's what dental photographers use. Software can't recover enamel that is glare in every shot.
2. **Shoot a burst around one pose.** Keep views within about ±15° of each other, and move the **light** (or the phone a little side-to-side) rather than switching between frontal and profile. Profile views are useful for 3D but can't be warped onto a frontal view.
3. **More views of the same pose** raise the share of glare filled from real pixels instead of inpainted.
4. Next engineering steps: a learned single-image specular-removal network for the leftovers, a teeth segmentation model for the ROI, and RAFT/SEA-RAFT flow instead of DIS.
