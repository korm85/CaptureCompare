import fs from 'node:fs';
import * as core from '../web/core.js';
const t0 = performance.now();
const buf = fs.readFileSync(new URL('../web/data/', import.meta.url).pathname + '21.stl');
const mesh = core.parseSTL(buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength));
const t1 = performance.now();
const frame = core.autoFrontView(mesh);
const t2 = performance.now();
const { photos } = core.parseCoco(JSON.parse(fs.readFileSync(new URL('../web/data/', import.meta.url).pathname + 'annotations.json', 'utf8')));
const t3 = performance.now();
console.log(`mesh: ${mesh.positions.length / 3} verts, ${mesh.indices.length / 3} faces  (parse ${(t1 - t0).toFixed(0)} ms)`);
const py = { view: [0.1436, -0.8585, 0.4923], up: [-0.0309, -0.5011, -0.8648] };
const ang = (a, b) => (Math.acos(Math.min(1, a[0] * b[0] + a[1] * b[1] + a[2] * b[2])) * 180) / Math.PI;
console.log(`front view: view ${frame.view.map((v) => v.toFixed(4))}  up ${frame.up.map((v) => v.toFixed(4))}  (${(t2 - t1).toFixed(0)} ms)`);
console.log(`  vs python: view off by ${ang(frame.view, py.view).toFixed(2)} deg, up off by ${ang(frame.up, py.up).toFixed(2)} deg`);
console.log(`photos parsed: ${photos.length} (${(t3 - t2).toFixed(0)} ms); outline from zones: ${photos.filter((p) => p.outlineSource === 'regions').map((p) => p.id).join(',')}`);
console.log('tooth numbers:', photos.map((p) => `${p.id}:${p.tooth ?? '?'}${p.toothSource && p.toothSource !== 'annotation' ? '*' : ''}`).join(' '));
const photo = photos.find((p) => p.id === 27);
const t4 = performance.now();
const r = core.transfer(mesh, frame, core.mirrorPhoto(photo));
const t5 = performance.now();
console.log(`crop_case_007 (#${photo.tooth}, mirrored): IoU ${r.fit.iou.toFixed(3)}  scale ${(r.fit.scale * 1000).toFixed(2)} um/px  rotation ${(r.fit.rotation * 180 / Math.PI).toFixed(1)} deg`);
console.log(`  gap mean ${r.gap.mean.toFixed(3)} mm max ${r.gap.max.toFixed(3)} mm   lambda ${r.lambda}  folds ${r.folds}  edge residual max ${r.edgeResidualMax.toFixed(4)} mm   (${(t5 - t4).toFixed(0)} ms)`);
console.log('  python reference: IoU 0.827, 6.86 um/px, -3.7 deg, gap mean 0.498 max 1.480');
// check silhouette area vs python (78.55 mm2)
console.log(`silhouette area ${Math.abs(core.polygonArea(r.silhouette)).toFixed(2)} mm2 (python 78.55)`);
// all photos
let worst = 1;
for (const p of photos) {
  const mir = core.isContralateral(p.tooth, 21) ? core.mirrorPhoto(p) : p;
  const q = core.transfer(mesh, frame, mir);
  worst = Math.min(worst, q.fit.iou);
  console.log(`  ${String(p.id).padStart(2)} ${p.file.split('/').pop().padEnd(28)} #${p.tooth ?? '?'} ${mir.mirrored ? 'mirror' : '      '} IoU ${q.fit.iou.toFixed(3)} rot ${(q.fit.rotation * 180 / Math.PI).toFixed(1).padStart(5)} gap ${q.gap.max.toFixed(2)} lambda ${q.lambda} folds ${q.folds}`);
}
