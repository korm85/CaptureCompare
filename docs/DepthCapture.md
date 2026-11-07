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

Mean of 3 scenes (seeds 0–2), metrics inside the mouth:

| Method | PSNR on glare px (↑) | PSNR whole mouth (↑) | PSNR clean px (↑, damage check) | residual glare % (↓) |
|---|---|---|---|---|
| reference, untouched | 19.4 | 28.4 | 38.4 | 84.4 |
| single-image inpaint | 17.9 | 23.7 | 25.8 | 4.5 |
| aligned **min-fusion** (earlier suggestion) | 17.3 | 21.1 | 21.9 | 6.2 |
| aligned median-fusion | 19.9 | 26.8 | 29.9 | 47.2 |
| pipeline, EfficientLoFTR, homography only | **24.1** | **29.6** | **31.5** | 20.2 |
| pipeline, SIFT + dense | 20.4 | 26.5 | 28.9 | 15.6 |
| pipeline, EfficientLoFTR + dense (default) | 21.2 | 28.0 | 31.1 | 29.0 |

Glare-mask detection: precision 0.58, recall 0.59. 15.5 % of glare pixels had no clean view and were inpainted.

How to read it:
* Inpainting and min-fusion "remove" glare (low residual %), but they repaint clean enamel. Their PSNR is far below simply leaving the photo alone.
* The fusion pipeline is the only method that beats the untouched input where the glare is (+2 to +5 dB) and on the mouth as a whole.
* On this rendered scene (rigid, near-planar motion) homography-only is best. On the **real** photos the dense stage is clearly needed: hold-out 30.5 dB vs 26.0 dB, and 2 usable views vs 1. So dense stays the default.
* The synthetic set is a stand-in, not proof. Its textures are procedural, and early on it hid a matcher bug that real photos then exposed.

## 5. Real photos (`data/smile_set1`, 6 phone photos)

There is no ground truth here, so the pipeline reports three things:
* which views it could align;
* glare pixels before/after, measured with the detector itself, so this flatters the result;
* a **hold-out check**: on reference enamel that is *not* glare, how well the fused other views reproduce it. That is the expected accuracy of a replaced pixel.

| Reference | Views usable (of 5) | Hold-out PSNR / MAE | Glare px filled from real views | Glare px inpainted |
|---|---|---|---|---|
| frame_4 (frontal) | 2: frame_3, frame_5 | 30.5 dB / 0.022 | 4.5 k | 8.8 k |
| frame_3 (frontal) | 2: frame_1, frame_4 | 31.6 dB / 0.019 | 6.6 k | 7.5 k |
| frame_5 | 2: frame_4, frame_6 | 29.3 dB / 0.029 | 9.3 k | 14.5 k |

Honest verdict on this set:
* **Small, sharp glints are removed well** from real pixels, and alignment of near-frontal views is accurate (about 2 % error).
* **Broad wet sheen mostly remains.** The light is a large window, so the sheen sits on nearly the same part of each tooth in every frontal shot. There's no clean observation to borrow.
* **Profile shots can't be used** to clean a frontal reference. They see different tooth surfaces, and the pipeline rejects them automatically.
* **Over half the replaced area falls back to inpainting.** That's guessed texture, and it shows up as a few soft or dark smudges. The report and `compare.jpg` mark these regions in magenta.
* MediaPipe found no face in these close-ups (it needs eyes and nose), so the enamel-colour ROI fallback was used.

## 6. What to change to get a good result
1. **Capture.** Cross-polarised flash (a polariser on the light, a crossed one on the lens) removes wet-surface reflections optically. That's what dental photographers use. Software can't recover enamel that is glare in every shot.
2. **Shoot a burst around one pose.** Keep views within about ±15° of each other, and move the **light** (or the phone a little side-to-side) rather than switching between frontal and profile. Profile views are useful for 3D but can't be warped onto a frontal view.
3. **More views of the same pose** raise the share of glare filled from real pixels instead of inpainted.
4. Next engineering steps: a learned single-image specular-removal network for the leftovers, a teeth segmentation model for the ROI, and RAFT/SEA-RAFT flow instead of DIS.
