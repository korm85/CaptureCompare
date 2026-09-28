# Stain map transfer: proof of concept

Maps staining regions annotated on a photo of a tooth (e.g. tooth 11) onto a 3D restoration (e.g. a 21 veneer), so a
technician sees where each stain goes on the restoration's facial surface.

Hosted demo of this exact code: https://claude.ai/artifact/PLTM93LLj1MJzByS8jiGSp (private to the owner).

## Layout

| Path | What it is |
|---|---|
| `web/core.js` | All geometry. Pure ES module, no rendering or DOM dependencies. Runs in the browser and in Node; this is the part to port into the app (or to Python for the backend). |
| `web/index.html` | Demo UI: three.js viewer, 2D fit panel, layer toggles, file loaders. three.js 0.170 from jsDelivr via an import map. |
| `web/data/21.stl` | Sample restoration: exocad veneer for tooth 21 (22,490 triangles, closed). |
| `web/data/21.stl.json` | Same STL as base64 in JSON (the hosted demo can't serve `.stl`; the page loads this one). |
| `web/data/annotations.json` | Trimmed CVAT COCO export: 30 photos, 361 polygons, 15 classes. See "Data notes". |
| `AGENT_PROMPT.md` | Ready-to-paste brief for the agent integrating this into the app. |
| `tests/test_core.mjs` | Runs the full pipeline in Node on every photo and prints fit metrics. |
| `prototype/*.py` | First Python prototype (numpy, scipy, trimesh, shapely, Pillow, matplotlib) used to validate the approach. |

Run the demo: `cd web && npx http-server -c-1 .` then open `http://localhost:8080/`.
It must be served over HTTP (it fetches `data/` and imports `core.js`).

Run the check: `cd tests && node test_core.mjs` (Node 18+).

## Pipeline (`core.transfer`)

Coordinates: photo space is pixels with y down. View space is millimetres in the restoration's front view, with
x = `frame.right` and y = `frame.up`.

1. **Front view** (`autoFrontView`)
   - Direction: the one with the largest projected area (area-weighted |n·d| over a Fibonacci hemisphere, then
     refined locally).
   - Side: of the two opposite directions, pick the one where the surface bulges toward the viewer (fit
     depth = a + b·r²; b < 0 is the facial side). For a veneer the other side is the hollow fitting surface.
   - Roll: the long axis is the outline's axis of best mirror symmetry, searched within ±40° of its principal axis.
     The wider end is incisal, and incisal goes down.
   - Manual pitch/yaw tilt and 90° roll: `adjustFrame`.
   - Note: the maximum is flat (tilting 10° loses only ~1% area), so this is a good default rather than a precise
     answer. The photo's real camera tilt can differ; the warp absorbs most of it.
2. **Silhouette** (`silhouette`): rasterise every triangle at 512², trace the outer loop with marching squares,
   giving a polygon in mm.
3. **Similarity fit** (`fitSimilarity`): scale, rotation and shift that maximise IoU between the photo outline and
   the silhouette.
   - IoU is computed exactly and continuously via Green's theorem on the boundary segments inside the other polygon.
   - Search: a coarse rotation scan over ±45°, then Nelder–Mead from the two best starts.
4. **Boundary pairs** (`correspond`): resample both outlines by arc length (128 points) and take the best cyclic
   shift.
5. **Warp** (`TPS`): thin-plate spline mapping view mm to photo px, fitted on the boundary pairs, so the photo
   outline lands exactly on the silhouette.
   - A Jacobian sign check flags folds. On a fold, smoothing λ is raised step by step (0 → 100).
6. **Per-vertex UV**: `photoPx[v] = TPS(project(v))`. UVs point straight into the photo, so the texture is simply
   the annotation polygons (or the photo itself) drawn in photo space.
7. **Stainable surface** (in the fragment shader in `index.html`): stain only where the surface faces the front
   view and is not hidden in it.
   - Visibility is a depth map rendered from an orthographic front camera, with 3×3 PCF and a slope-scaled bias.
   - This excludes the lingual/fitting surface and anything occluded.

Mirroring (`mirrorPhoto`, x → width − x) is switched on automatically when the photo and restoration are
contralateral teeth (`isContralateral`, FDI numbers: 11↔21, 12↔22, …).

## Results on the sample data (21 veneer, all 29 annotated photos)

| Metric | Result |
|---|---|
| IoU after similarity fit | 0.82–0.97 |
| Rotation | within ±12° |
| Warp folds | none |
| Largest outline gap closed by the warp | ≤ 1.5 mm, except 2.6 mm for the #13 photo (a canine onto a central incisor) |
| Time per fit | about 0.3–0.9 s |

`crop_case_007` (#11, mirrored) gives IoU 0.827 and 6.86 µm/px, identical in Python, Node and the browser.

## Data notes (from `instances_default.json`)

- In 9 photos (`frontal_tooth/*`, image ids 1–4, 6, 7, 10–12) the "Tooth Annotation" is a small circle marker, not
  the outline.
  - `parseCoco` detects this (outline area < 50% of the regions' union) and rebuilds the outline from all on-tooth
    regions.
  - The rebuild uses a morphological closing to bridge small gaps between zones. Reflection, extraneous matter and
    artificial tooth are excluded from it.
- `crop_case_001–010` are the same 10 photos as `frontal_tooth/*`, annotated a second time, without tooth numbers.
  - Their tooth numbers were copied from the twin into `attributes["Tooth number (from twin)"]`, and the raw
    `Tooth number` was left untouched.
  - This is a train/validation leakage risk for the U-Net if the split is random.
- Regions overlap as layers rather than tiling the tooth. They are drawn in a fixed order: zones first,
  characterisations on top.
- Stain layers on by default:
  - Body, Cervical, Incisal
  - Translucent area, Halo, Mamelon
  - White stain, Stain, Crack
- Off by default: Caries, Filling, Artificial tooth, Extraneous matter, Reflection.
- The file has no photos or colours. The demo shows class colours; "Add photo image" wraps the real photo onto the
  restoration to check alignment.

## Open questions for integration

1. Region shades: the app computes colour sample points per region. Feed them in so the stain map shows real shades.
2. Production input: the live U-Net output format.
   - `parseCoco` reads polygons (and COCO RLE).
   - A per-pixel class map would need contour tracing per class. `traceContours` already does this for a binary mask.
3. Where it runs: everything is light enough for the browser. For the backend, port `core.js` 1:1 to Python and
   export a glTF (mesh + UVs + stain texture).
4. Possible improvements:
   - Optimise the view tilt (±15°) jointly with the fit.
   - Monotone (DTW) boundary correspondence instead of uniform arc length.
   - Export of the stain map.
