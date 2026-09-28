# Task: integrate "stain map transfer" into the app

## Goal
A technician stains a 3D-printed/milled restoration (e.g. a veneer for tooth 21) by hand. Our U-Net already segments a
frontal photo of the patient's contralateral tooth (e.g. 11) into a tooth outline plus staining regions (body, cervical,
incisal, translucency, halo, mamelons, stains, cracks…). Build the feature that takes **one photo's segmentation + one
restoration STL** and shows those regions correctly placed on the restoration's facial surface in the app's 3D viewer,
as a stain map the technician can rotate and inspect.

## A working proof of concept already exists: start from it, don't redesign it
Repo (public): https://github.com/korm85/CaptureCompare, branch `claude/tooth-contour-uv-mapping-jqh9oc`, folder `stain-map-poc/`
```
git clone -b claude/tooth-contour-uv-mapping-jqh9oc https://github.com/korm85/CaptureCompare.git
```
Read `stain-map-poc/README.md` first. Key files:
- `web/core.js`: all geometry as a pure ES module, with no DOM or three.js dependency. **Port/import this as-is.**
- `web/index.html`: reference three.js integration: shader, depth pass, stain texture, camera presets.
- `tests/test_core.mjs`: `node test_core.mjs` runs the pipeline on the sample data and prints fit metrics. Use it as a
  regression check if you touch core.js.
- `web/data/`: sample veneer `21.stl` and a COCO annotation file. The photo and STL are from **different patients**,
  so fits are worse than a real case will be.
- Run the demo: `cd stain-map-poc/web && npx http-server -c-1 .`

## Pipeline (all in core.js)
1. `parseSTL(arrayBuffer)` returns `{positions: Float64Array (centred), indices: Uint32Array, center, extents}`.
   Duplicate vertices are merged.
2. `autoFrontView(mesh)` returns `frame = {view, up, right}` (unit vectors).
   - `view` is the direction with the largest silhouette, on the side that bulges toward the viewer (facial).
   - `up` points cervical, on the outline's symmetry axis, with the incisal edge down.
   - The result doesn't depend on how the file is oriented: tested on 20 random rotations, within 0.5°.
   - ~0.3 s for 22k triangles.
   - `adjustFrame(frame, {pitch, yaw, roll})` applies manual tilts, with roll in 90° steps.
3. `mirrorPhoto(photo)` when the teeth are contralateral: `isContralateral(photoTooth, restorationTooth)`, FDI numbering,
   11↔21, 12↔22…
4. `transfer(mesh, frame, photo)` does the silhouette, IoU-max similarity fit, boundary pairing, thin-plate-spline
   warp (with a fold check) and per-vertex projection. It returns:
   - `photoPx`: a Float64Array with 2 values per vertex, the photo pixel each vertex maps to. These are the UVs.
   - `fit`: `{iou, scale (mm per px), rotation}`.
   - `gap`: `{mean, max}` in mm, how much the warp had to bend.
   - `folds`, `silhouette`, `aligned`, `pairs`, `tps`.
5. Rendering (see index.html):
   - Draw the region polygons into a canvas in photo-pixel space, cropped to the outline's bounding box.
   - UV = `((px - crop.x0)/crop.w, 1 - (py - crop.y0)/crop.h)`.
   - Stain only fragments that face the front view **and** pass a depth test against an orthographic depth map
     rendered from the front view (`renderDepth`, fragment shader).
   - The hollow fitting surface and hidden sides stay unstained.

`photo` input shape: `{width, height, outline: [[x,y],…], regions: [{cls, polygon: [[x,y],…]}, …]}` in pixel coordinates,
with y pointing down.

## Integration pitfalls
- **Vertex order must match.** `photoPx[i]` belongs to vertex `i` of the mesh object you passed in. Build the rendered
  BufferGeometry from that same `positions`/`indices` (as index.html does). Alternatively, pass your existing
  geometry's positions and index into `transfer`. A non-indexed STLLoader geometry needs indices `0..n-1` or
  `mergeVertices` first. Don't compute UVs on one vertex array and render another.
- The frame, the depth-pass camera and the rendered mesh must share one coordinate system. index.html rotates the mesh
  so the front view is +Z (`applyFrame`); you can instead keep the model fixed and place the ortho camera along `view`.
- Custom ShaderMaterial output is in display space (no colorspace chunk). The base colour is passed as raw sRGB.
- Resizing a CanvasTexture needs `texture.dispose()` first, or WebGL rejects the upload.

## What you must discover in the app codebase first
1. Where the 3D restoration viewer lives (three.js? version?) and how the STL is loaded.
2. **The real U-Net output format** for one photo. core.js expects polygons per class.
   - If the backend returns a per-pixel class map, convert each class to polygons. `traceContours(mask, W, H)` in
     core.js does marching squares on a binary mask.
   - Also get the tooth outline, or rebuild it as the union of the tooth regions.
3. Where the tooth numbers live: the photo tooth and the restoration tooth, both FDI.
4. The per-region colour sample points the app already computes. Use them to colour the stain layers instead of class
   colours if available.
5. Whether the app has any existing orientation or camera presets for STLs. It currently has **no auto front view**, and
   `autoFrontView` is intended to be exposed as its own feature too (orient STL on load).

## Scope for this first integration
- Run fully in the browser; a backend port is a later phase.
- UI:
  - The stained restoration in the existing 3D viewer.
  - Layer toggles per class.
  - Opacity.
  - Camera presets: front, mesial, distal, incisal. The mesial side is viewer-left for quadrants 2/3, viewer-right
    for 1/4.
  - A small fit readout (overlap/IoU, largest gap in mm, fold warning).
  - Warn when IoU < 0.8, or when the photo and restoration are different tooth types.
- Default stain classes:
  - On: Body, Cervical, Incisal, Translucent area, Halo, Mamelon, White stain, Stain, Crack.
  - Off: Caries, Filling, Artificial tooth, Extraneous matter, Reflection.
- Optional: overlay the actual photo as the texture (same UVs) to judge alignment by eye.

## Known limits (don't try to solve them now; flag them if hit)
- autoFrontView is validated on one veneer only. It targets anterior teeth. For premolars/molars the largest
  silhouette is probably the occlusal view.
- No per-photo camera tilt estimation yet. The warp absorbs it.
- Boundary pairing is uniform arc length. A DTW pairing may be a later improvement.

## Done when
- A real case (one photo segmentation + one STL, same patient) loads in the app and shows the stain map on the facial
  surface, with layers, opacity, presets and the fit readout.
- `autoFrontView` orients any loaded anterior STL on load.
- `node stain-map-poc/tests/test_core.mjs` still prints the same metrics if core.js was changed.
- Summarise what you changed, the U-Net format you found and how you adapted it, and any open questions.
