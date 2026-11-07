# DepthCapture: removing wet-teeth reflections from multi-angle photos (POC)

## 1. Audit of the earlier suggestion

| Earlier claim | Verdict after building and testing |
|---|---|
| Align frames with EfficientLoFTR + homography | **Partly wrong.** A homography can't model a curved dental arch seen from several angles, or moving lips. It only removes the bulk motion. A dense, non-rigid field is required (see §3). |
| Use EfficientLoFTR through `transformers` | **Right model, broken glue.** In the installed `transformers` version, `post_process_keypoint_matching` pairs `keypoints0[i]` with `keypoints1[i]` instead of `keypoints1[matches[i]]`, and truncates coordinates to int. On a known rotation, under 0.1 % of its matches were correct. We decode the raw outputs ourselves; `tests/test_depthcapture.py` guards this. |
| Detect highlights by "bright + low saturation" | **Wrong for teeth.** Enamel is itself bright and pale, so this flags whole teeth. v2 uses a 2-scale local top-hat, brightness above *local* enamel, near-neutral colour, and a cross-view cue. |
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
| Single-image fill | Own enamel-aware fill in `specular.suppress_glare` (default); OpenCV Telea or LaMa via `simple-lama-inpainting` as options | Apache-2.0 | Glare no other view saw clean |
| Baseline matcher | OpenCV SIFT | Apache-2.0 | Comparison only |

Install with `pip install -r requirements-depthcapture.txt`. It runs on CPU; about 35–40 s for 6 photos at 1024 px.

## 3. Pipeline (`depthcapture/pipeline.py`)

```
photos (N views) ──► resize ──► teeth ROI per photo ──► glare probability
                     (2-scale top-hat × brighter than LOCAL enamel × near-neutral)
                                   │
reference (least glare, sharpest, or --reference); glare blobs bigger than a glint keep only their strong core
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
per glare pixel:  value from other views  if darker AND plausible enamel (colour/brightness)
                  else enamel-aware single-image fill (clean-enamel colour + damped texture)
                                   │
blend with soft strength (strong glints fully, borderline pixels partially)
```

Run it on a folder of photos:

```
python scripts/run_pipeline.py data/smile_set1/*.jpg --reference 3 --out results/ref4
```

Outputs: `output.png`, `compare.jpg` (input | result | where pixels came from), `report.json`. The report covers each view's alignment, glare before/after, and a hold-out accuracy figure.

## 4. Version history (why v2)
v1 removed almost nothing visible on the real photos. Its detector was tuned on the synthetic scene and assumed enamel is clearly yellow; on these photos enamel is nearly neutral white, so it fired on gum edges and missed the glints. Its fallback (Telea inpainting) bled dark gaps into teeth. v2 changes:
* Detection compares against *local* enamel brightness at two scales.
* A new enamel-aware fill replaces inpainting.
* A plausibility gate on values taken from other views removes the grey blotches.
* A blob-size guard stops whole bright teeth being flattened.

## 5. Results

### 5a. Real texture with ground truth (`scripts/eval_injected.py`)
Glint-shaped highlights (4–25 px, soft, some clipped) are painted onto clean enamel of the real photos. The pipeline then has to restore the original. Scores are on frames 3, 4 and 5, 3 random layouts each:

| | PSNR on injected glare (↑) | PSNR of surrounding enamel (↑, damage check) | detected |
|---|---|---|---|
| before | 12.2 dB | – | – |
| **after (v2)** | **25.8 dB** | 36.2 dB | 93 % |

### 5b. Your real photos (`data/smile_set1`)
Visual before/after: `results/before_after_all.jpg`. In every frontal reference, the sharp glints on the upper incisors and most streaks on the lower teeth are removed, without damaging the teeth.

| Reference | Usable other views | Hold-out PSNR of view fusion | Glare mask px | from other views / single-image | Detector glare px before → after |
|---|---|---|---|---|---|
| frame_4 | frame_3, frame_5 | 30.3 dB | 26.3 k | 3.2 k / 23.1 k | 8.6 k → 0.6 k |
| frame_3 | frame_1, frame_4 | 31.6 dB | 22.3 k | 3.3 k / 19.1 k | 7.5 k → 1.4 k |
| frame_5 | frame_4, frame_6 | 27.5 dB | 14.5 k | – | 12.0 k → 9.3 k |

The "before → after" column uses the same detector, so it flatters the result; 5a is the trustworthy number. frame_5 keeps much of its broad shine on purpose: its large overexposed areas are treated as lit enamel, not glints.

### 5b-2. Frontal photos with the light moved (`data/smile_set2`, 5 photos)
This was captured as recommended: roughly frontal, light source moved between shots. Two changes were needed for this kind of set:
* **Shading match.** Each aligned photo gets a smooth, spatially varying per-channel gain (normalised convolution over clean pixels) so that its shading matches the reference. Fine detail is kept. Without it, the different lighting looked like misalignment and every photo was rejected.
* **Low flow-confidence floor.** Optical flow assumes constant brightness, which a moving light breaks. Its confidence drops to 0.3–0.6, so the coverage threshold was lowered (0.15 → 0.05).

Other changes:
* Strength comes from the added brightness: full replacement once a pixel is 0.05 brighter than its glare-free estimate.
* No borrowing from other photos right at strong edges, where a 1–2 px misalignment pulls in dark mouth background.
* The teeth mask hugs the teeth, so it no longer reaches the beard.

Injected-glint test (`eval_injected.py --multi`, each photo in turn as the reference, 2 layouts):

| Restore using | PSNR on glare (before 11.2 dB) | surrounding enamel | filled from other photos |
|---|---|---|---|
| that photo alone | 22.5 dB | 35.2 dB | 0 % |
| **all 5 light-moved photos** | **23.7 dB** | 34.7 dB | 50 % |

On the first set (camera moved, fixed window light), only ~12 % of real glare could be filled from other photos. With the light moved it's ~40–60 %, and the result is about 1.2 dB better than one photo alone. The gain is limited by alignment accuracy: a hand-held burst with slight zoom and pose changes, plus one photo with the jaw open. The borrowed values themselves are about 24.5–27 dB accurate.

Visual: `results/set2_before_after.jpg`. With light_4 or light_5 as the reference the result is clean and matte. light_2 (the glariest shot) improves. Dark marks it used to introduce at the lateral incisors' edges are fixed by an enamel brightness floor: removing glare can never leave a spot darker than the clean enamel around it.

PSNR (dB) measures how close an image is to the correct one: 10·log10(1/mean squared error), with pixels on a 0–1 scale. Higher is better; +6 dB means half the typical pixel error.

To see only what is classified as reflection, without editing anything, run `python scripts/run_pipeline.py <photos> --reference N --masks-only`.

### 5c. Synthetic scene (`scripts/eval_synthetic.py`, 3 scenes)

| Method | PSNR glare px | PSNR mouth | PSNR clean px | residual glare % |
|---|---|---|---|---|
| reference, untouched | 19.4 | 28.4 | 38.4 | 84.4 |
| aligned min-fusion (my original idea) | 15.7 | 21.2 | 22.9 | 10.9 |
| aligned median-fusion | 18.5 | 25.9 | 29.8 | 50.9 |
| pipeline (current), homography only | 21.8 | 28.2 | 30.9 | 6.1 |
| pipeline (current), default | 20.6 | 27.4 | 30.5 | 4.5 |
| (pipeline v1, default) | 21.2 | 28.0 | 31.1 | 29.0 |

The current version removes far more synthetic glare than v1 (residual 4.5 % vs 29 %) at a slightly lower PSNR. The synthetic highlights are long, full-height streaks over strongly shaded fake teeth, so a flat enamel fill loses the shading. That scene doesn't resemble real wet-teeth glare, so v2 was tuned on the real photos (5a, 5b). Treat 5c as a sanity check only.

### Limits
* **Only near-frontal views help.** Profile shots see different tooth surfaces and are rejected automatically (2 of 5 views usable per reference here).
* **Most glare is filled from the single photo**, because the window light puts the sheen in the same place in every frontal shot. The fill keeps texture, but it is an estimate, not the true enamel.
* **Overexposed areas can't be recovered.** Where enamel itself clips to white, nothing is recoverable.
* **MediaPipe needs a full face**, so these close-ups used the enamel-colour ROI fallback.

## 6. What to change to get a better result
1. **Capture.** Cross-polarised flash (a polariser on the light, a crossed one on the lens) removes wet-surface reflections optically. That's what dental photographers use. Software can't recover enamel that is glare in every shot.
2. **Keep the camera fixed and move the light** (verified in 5b-2). Use a phone on a stand, the same zoom, and the jaw in the same position in every shot. Alignment error is now the main limit, so a tripod or stand should give the biggest further gain.
3. **More views of the same pose** raise the share of glare filled from real pixels instead of estimated.
4. Next engineering steps: a learned single-image specular-removal network for the leftovers, a teeth segmentation model for the ROI, and RAFT/SEA-RAFT flow instead of DIS.
