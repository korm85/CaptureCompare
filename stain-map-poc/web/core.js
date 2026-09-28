// Stain-map transfer core: photo annotation regions -> restoration surface.
// Pure geometry, no rendering dependencies, so it runs in the browser, in Node, or can be ported to the backend.
//
// Conventions
//   photo space : pixels, x right, y down (as annotated)
//   view space  : millimetres in the restoration's front view, x = frame.right, y = frame.up (y up)
//   polygons    : arrays of [x, y], not closed (first point is not repeated)

// ---------------------------------------------------------------- small vector helpers
const dot3 = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross3 = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const norm3 = (a) => { const l = Math.hypot(a[0], a[1], a[2]); return [a[0] / l, a[1] / l, a[2] / l]; };
const scale3 = (a, s) => [a[0] * s, a[1] * s, a[2] * s];
const add3 = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];

export function rotateAround(v, axis, rad) {
  const k = norm3(axis), c = Math.cos(rad), s = Math.sin(rad);
  return add3(add3(scale3(v, c), scale3(cross3(k, v), s)), scale3(k, dot3(k, v) * (1 - c)));
}

function anyPerpendicular(d) {
  const a = Math.abs(d[0]) < 0.9 ? [1, 0, 0] : [0, 1, 0];
  const u = norm3(cross3(d, a));
  return [u, cross3(d, u)];
}

// ---------------------------------------------------------------- mesh
/** Parse binary or ASCII STL, merge duplicate vertices and centre the mesh on its bounding-box centre. */
export function parseSTL(buffer) {
  const dv = new DataView(buffer);
  const binary = buffer.byteLength >= 84 && 84 + 50 * dv.getUint32(80, true) === buffer.byteLength;
  let tri;
  if (binary) {
    const n = dv.getUint32(80, true);
    tri = new Float64Array(n * 9);
    for (let i = 0; i < n; i++) {
      const o = 84 + i * 50 + 12;
      for (let k = 0; k < 9; k++) tri[i * 9 + k] = dv.getFloat32(o + k * 4, true);
    }
  } else {
    const text = new TextDecoder().decode(buffer);
    const re = /vertex\s+(\S+)\s+(\S+)\s+(\S+)/g;
    const v = [];
    let m;
    while ((m = re.exec(text))) v.push(+m[1], +m[2], +m[3]);
    tri = new Float64Array(v);
  }
  const map = new Map(), pos = [], indices = new Uint32Array(tri.length / 3);
  for (let i = 0; i < tri.length / 3; i++) {
    const x = tri[i * 3], y = tri[i * 3 + 1], z = tri[i * 3 + 2];
    const key = `${Math.round(x * 1e5)},${Math.round(y * 1e5)},${Math.round(z * 1e5)}`;
    let id = map.get(key);
    if (id === undefined) { id = pos.length / 3; map.set(key, id); pos.push(x, y, z); }
    indices[i] = id;
  }
  const positions = new Float64Array(pos);
  const lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < positions.length; i += 3)
    for (let k = 0; k < 3; k++) { lo[k] = Math.min(lo[k], positions[i + k]); hi[k] = Math.max(hi[k], positions[i + k]); }
  const center = [0, 1, 2].map((k) => (lo[k] + hi[k]) / 2);
  for (let i = 0; i < positions.length; i += 3) for (let k = 0; k < 3; k++) positions[i + k] -= center[k];
  return { positions, indices, center, extents: [0, 1, 2].map((k) => hi[k] - lo[k]) };
}

function faceData(mesh) {
  const { positions: P, indices: I } = mesh, nF = I.length / 3;
  const N = new Float64Array(nF * 3), A = new Float64Array(nF), C = new Float64Array(nF * 3);
  for (let f = 0; f < nF; f++) {
    const a = I[f * 3] * 3, b = I[f * 3 + 1] * 3, c = I[f * 3 + 2] * 3;
    const e1 = [P[b] - P[a], P[b + 1] - P[a + 1], P[b + 2] - P[a + 2]];
    const e2 = [P[c] - P[a], P[c + 1] - P[a + 1], P[c + 2] - P[a + 2]];
    const n = cross3(e1, e2), l = Math.hypot(n[0], n[1], n[2]);
    A[f] = l / 2;
    if (l > 0) { N[f * 3] = n[0] / l; N[f * 3 + 1] = n[1] / l; N[f * 3 + 2] = n[2] / l; }
    for (let k = 0; k < 3; k++) C[f * 3 + k] = (P[a + k] + P[b + k] + P[c + k]) / 3;
  }
  return { N, A, C, nF };
}

/** Area-weighted |n.d|: proportional to the projected (silhouette) area for a closed mesh without self-overlap. */
function projectedArea(fd, d) {
  let s = 0;
  for (let f = 0; f < fd.nF; f++) s += fd.A[f] * Math.abs(fd.N[f * 3] * d[0] + fd.N[f * 3 + 1] * d[1] + fd.N[f * 3 + 2] * d[2]);
  return s / 2;
}

/**
 * Curvature of the surface seen from direction d: fit depth = a + b * r^2 over faces clearly facing d.
 * b < 0 means the surface bulges toward the viewer (facial side); b > 0 means hollow (fitting surface / lingual fossa).
 */
function bulge(fd, d) {
  const [u, v] = anyPerpendicular(d);
  const xs = [], ys = [], zs = [], ws = [];
  for (let f = 0; f < fd.nF; f++) {
    const n = [fd.N[f * 3], fd.N[f * 3 + 1], fd.N[f * 3 + 2]];
    if (dot3(n, d) < 0.3) continue;
    const c = [fd.C[f * 3], fd.C[f * 3 + 1], fd.C[f * 3 + 2]];
    xs.push(dot3(c, u)); ys.push(dot3(c, v)); zs.push(dot3(c, d)); ws.push(fd.A[f]);
  }
  let W = 0, mx = 0, my = 0;
  for (let i = 0; i < ws.length; i++) { W += ws[i]; mx += ws[i] * xs[i]; my += ws[i] * ys[i]; }
  mx /= W; my /= W;
  let sr = 0, sz = 0, srr = 0, srz = 0;
  for (let i = 0; i < ws.length; i++) {
    const r = (xs[i] - mx) ** 2 + (ys[i] - my) ** 2;
    sr += ws[i] * r; sz += ws[i] * zs[i]; srr += ws[i] * r * r; srz += ws[i] * r * zs[i];
  }
  return (W * srz - sr * sz) / (W * srr - sr * sr);
}

/**
 * Automatic front view: the direction with the largest silhouette, on the side where the surface bulges toward
 * the viewer, rolled so the incisal edge points down (the wider end of an anterior crown's outline is incisal).
 */
export function autoFrontView(mesh) {
  const fd = faceData(mesh);
  let best = null, bestS = -1;
  const K = 1500, golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < K; i++) {           // |n.d| is symmetric, a hemisphere is enough
    const z = 1 - (i + 0.5) / K, r = Math.sqrt(1 - z * z), ph = i * golden;
    const d = [r * Math.cos(ph), r * Math.sin(ph), z];
    const s = projectedArea(fd, d);
    if (s > bestS) { bestS = s; best = d; }
  }
  for (let step = (4 * Math.PI) / 180; step > (0.2 * Math.PI) / 180; ) {
    const [u, v] = anyPerpendicular(best);
    let moved = false;
    for (const [a, b] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
      const c = norm3(add3(best, add3(scale3(u, a * Math.tan(step)), scale3(v, b * Math.tan(step)))));
      const s = projectedArea(fd, c);
      if (s > bestS) { bestS = s; best = c; moved = true; }
    }
    if (!moved) step /= 2;
  }
  const view = bulge(fd, best) <= bulge(fd, scale3(best, -1)) ? best : scale3(best, -1);
  return orientFrame(mesh, view, bestS);
}

/**
 * Roll a view direction so the tooth's long axis is vertical and the incisal end points down.
 * The long axis is the outline's axis of best mirror symmetry, searched within ±40° of its principal axis.
 * Returns {view, up, right} (right-handed, not mirrored).
 */
export function orientFrame(mesh, view, area) {
  const [u, v] = anyPerpendicular(view);
  const sil = silhouette(mesh, { view, up: v, right: u }, 256).polygon;
  const pts = resampleClosed(sil, 400);
  const [mx, my] = polygonCentroid(pts);
  let sxx = 0, sxy = 0, syy = 0;
  for (const p of pts) { const x = p[0] - mx, y = p[1] - my; sxx += x * x; sxy += x * y; syy += y * y; }
  const major = 0.5 * Math.atan2(2 * sxy, sxx - syy);
  const poly = resampleClosed(sil, 160);
  const symmetry = (phi) => {
    const c = Math.cos(phi), s = Math.sin(phi);
    const mirrored = poly.map(([x, y]) => {
      const dx = x - mx, dy = y - my, t = dx * c + dy * s;
      return [mx + 2 * t * c - dx, my + 2 * t * s - dy];
    });
    return iou(ensureCCW(poly), ensureCCW(mirrored));
  };
  let ang = major, best = -1;
  for (let d = -40; d <= 40; d += 2) { const phi = major + (d * Math.PI) / 180, s = symmetry(phi); if (s > best) { best = s; ang = phi; } }
  for (let step = (Math.PI / 180); step > 0.002; step /= 2)
    for (const phi of [ang - step, ang + step]) { const s = symmetry(phi); if (s > best) { best = s; ang = phi; } }
  const ax = [Math.cos(ang), Math.sin(ang)], ay = [-ax[1], ax[0]];
  const t = pts.map((p) => (p[0] - mx) * ax[0] + (p[1] - my) * ax[1]);
  const s = pts.map((p) => (p[0] - mx) * ay[0] + (p[1] - my) * ay[1]);
  const tmin = Math.min(...t), tmax = Math.max(...t), L = tmax - tmin;
  const width = (frac) => {
    const x = tmin + frac * L;
    let lo = Infinity, hi = -Infinity;
    t.forEach((ti, i) => { if (Math.abs(ti - x) < 0.05 * L) { lo = Math.min(lo, s[i]); hi = Math.max(hi, s[i]); } });
    return hi - lo;
  };
  const inc = width(0.8) > width(0.2) ? ax : [-ax[0], -ax[1]];   // 2D direction toward the incisal end
  const up = norm3(scale3(add3(scale3(u, inc[0]), scale3(v, inc[1])), -1));
  return { view, up, right: cross3(up, view), area, symmetry: best };
}

/** Apply manual adjustments to a frame: tilt around right (pitch) and up (yaw) in degrees, roll in 90° steps. */
export function adjustFrame(frame, { pitch = 0, yaw = 0, roll = 0 } = {}) {
  const rad = Math.PI / 180;
  let { view, up, right } = frame;
  if (roll) {
    const r = roll * 90 * rad;
    up = rotateAround(up, view, r); right = rotateAround(right, view, r);
  }
  if (yaw) { view = rotateAround(view, up, yaw * rad); right = rotateAround(right, up, yaw * rad); }
  if (pitch) { view = rotateAround(view, right, pitch * rad); up = rotateAround(up, right, pitch * rad); }
  return { view: norm3(view), up: norm3(up), right: norm3(right), area: frame.area };
}

/** 2D coordinates (mm) of every vertex in the frame. */
export function projectVertices(mesh, frame) {
  const P = mesh.positions, n = P.length / 3, out = new Float64Array(n * 2);
  for (let i = 0; i < n; i++) {
    const p = [P[i * 3], P[i * 3 + 1], P[i * 3 + 2]];
    out[i * 2] = dot3(p, frame.right); out[i * 2 + 1] = dot3(p, frame.up);
  }
  return out;
}

/** Silhouette polygon (mm, CCW) of the whole mesh seen along frame.view. */
export function silhouette(mesh, frame, res = 512) {
  const xy = projectVertices(mesh, frame), I = mesh.indices;
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (let i = 0; i < xy.length; i += 2) {
    x0 = Math.min(x0, xy[i]); x1 = Math.max(x1, xy[i]); y0 = Math.min(y0, xy[i + 1]); y1 = Math.max(y1, xy[i + 1]);
  }
  const pad = 3, sc = (res - 2 * pad) / Math.max(x1 - x0, y1 - y0);
  const ox = x0 - pad / sc, oy = y0 - pad / sc;          // sample (i, j) sits at (ox + i/sc, oy + j/sc)
  const mask = new Uint8Array(res * res);
  const X = (k) => (xy[k * 2] - ox) * sc, Y = (k) => (xy[k * 2 + 1] - oy) * sc;
  for (let f = 0; f < I.length; f += 3)
    rasterTriangle(mask, res, res, X(I[f]), Y(I[f]), X(I[f + 1]), Y(I[f + 1]), X(I[f + 2]), Y(I[f + 2]));
  const loop = largestLoop(traceContours(mask, res, res));
  const polygon = ensureCCW(smoothClosed(loop.map(([i, j]) => [ox + i / sc, oy + j / sc]), 2));
  return { polygon, bounds: [x0, y0, x1, y1] };
}

// ---------------------------------------------------------------- rasters and contours
function rasterTriangle(mask, W, H, ax, ay, bx, by, cx, cy) {
  const area = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax);
  if (Math.abs(area) < 1e-12) return;
  const sg = area > 0 ? 1 : -1;
  const i0 = Math.max(0, Math.ceil(Math.min(ax, bx, cx))), i1 = Math.min(W - 1, Math.floor(Math.max(ax, bx, cx)));
  const j0 = Math.max(0, Math.ceil(Math.min(ay, by, cy))), j1 = Math.min(H - 1, Math.floor(Math.max(ay, by, cy)));
  for (let j = j0; j <= j1; j++)
    for (let i = i0; i <= i1; i++) {
      if (sg * ((bx - ax) * (j - ay) - (by - ay) * (i - ax)) < 0) continue;
      if (sg * ((cx - bx) * (j - by) - (cy - by) * (i - bx)) < 0) continue;
      if (sg * ((ax - cx) * (j - cy) - (ay - cy) * (i - cx)) < 0) continue;
      mask[j * W + i] = 1;
    }
}

/** Even-odd scanline fill of a polygon given in sample units. */
export function fillPolygon(mask, W, H, poly, value = 1) {
  let ymin = Infinity, ymax = -Infinity;
  for (const p of poly) { ymin = Math.min(ymin, p[1]); ymax = Math.max(ymax, p[1]); }
  const n = poly.length;
  for (let j = Math.max(0, Math.ceil(ymin)); j <= Math.min(H - 1, Math.floor(ymax)); j++) {
    const xs = [];
    for (let k = 0; k < n; k++) {
      const [ax, ay] = poly[k], [bx, by] = poly[(k + 1) % n];
      if ((ay <= j && by > j) || (by <= j && ay > j)) xs.push(ax + ((j - ay) * (bx - ax)) / (by - ay));
    }
    xs.sort((a, b) => a - b);
    for (let k = 0; k + 1 < xs.length; k += 2)
      for (let i = Math.max(0, Math.ceil(xs[k])); i <= Math.min(W - 1, Math.floor(xs[k + 1])); i++) mask[j * W + i] = value;
  }
}

/** Marching squares on a binary mask. Returns closed loops in sample units (sample (i,j) at (i,j)). */
export function traceContours(mask, W, H) {
  const val = (x, y) => (x < 0 || y < 0 || x >= W || y >= H ? 0 : mask[y * W + x]);
  const W2 = W + 2;
  const hid = (x, y) => ((y + 1) * W2 + (x + 1)) * 2;       // edge between (x,y) and (x+1,y)
  const vid = (x, y) => ((y + 1) * W2 + (x + 1)) * 2 + 1;   // edge between (x,y) and (x,y+1)
  const coord = (id) => {
    const cell = id >> 1, x = (cell % W2) - 1, y = Math.floor(cell / W2) - 1;
    return id & 1 ? [x, y + 0.5] : [x + 0.5, y];
  };
  const adj = new Map();
  const link = (a, b) => {
    (adj.get(a) || adj.set(a, []).get(a)).push(b);
    (adj.get(b) || adj.set(b, []).get(b)).push(a);
  };
  for (let y = -1; y < H; y++)
    for (let x = -1; x < W; x++) {
      const c = val(x, y) * 8 + val(x + 1, y) * 4 + val(x + 1, y + 1) * 2 + val(x, y + 1);
      if (c === 0 || c === 15) continue;
      const T = hid(x, y), R = vid(x + 1, y), B = hid(x, y + 1), L = vid(x, y);
      switch (c) {
        case 1: case 14: link(L, B); break;
        case 2: case 13: link(B, R); break;
        case 3: case 12: link(L, R); break;
        case 4: case 11: link(T, R); break;
        case 6: case 9: link(T, B); break;
        case 7: case 8: link(L, T); break;
        case 5: link(L, B); link(T, R); break;     // saddles: keep diagonal pixels apart
        case 10: link(L, T); link(B, R); break;
      }
    }
  const seen = new Set(), loops = [];
  for (const start of adj.keys()) {
    if (seen.has(start)) continue;
    const loop = [];
    let prev = -1, cur = start;
    for (;;) {
      seen.add(cur); loop.push(coord(cur));
      const nb = adj.get(cur), next = nb[0] !== prev ? nb[0] : nb[1];
      prev = cur; cur = next;
      if (cur === start || seen.has(cur)) break;
    }
    if (loop.length > 2) loops.push(loop);
  }
  return loops;
}

const largestLoop = (loops) => loops.reduce((a, b) => (Math.abs(polygonArea(b)) > Math.abs(polygonArea(a)) ? b : a));

function smoothClosed(P, iterations) {
  let Q = P;
  for (let it = 0; it < iterations; it++) {
    const n = Q.length;
    Q = Q.map((p, i) => {
      const a = Q[(i - 1 + n) % n], b = Q[(i + 1) % n];
      return [0.25 * a[0] + 0.5 * p[0] + 0.25 * b[0], 0.25 * a[1] + 0.5 * p[1] + 0.25 * b[1]];
    });
  }
  return Q;
}

// ---------------------------------------------------------------- polygons
export function polygonArea(P) {
  let s = 0;
  for (let i = 0, n = P.length; i < n; i++) { const a = P[i], b = P[(i + 1) % n]; s += a[0] * b[1] - b[0] * a[1]; }
  return s / 2;
}
export const ensureCCW = (P) => (polygonArea(P) >= 0 ? P : P.slice().reverse());

export function polygonCentroid(P) {
  let cx = 0, cy = 0, a = 0;
  for (let i = 0, n = P.length; i < n; i++) {
    const p = P[i], q = P[(i + 1) % n], c = p[0] * q[1] - q[0] * p[1];
    a += c; cx += (p[0] + q[0]) * c; cy += (p[1] + q[1]) * c;
  }
  return [cx / (3 * a), cy / (3 * a)];
}

export function pointInPolygon(x, y, P) {
  let inside = false;
  for (let i = 0, j = P.length - 1; i < P.length; j = i++) {
    const [xi, yi] = P[i], [xj, yj] = P[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

export function resampleClosed(P, n) {
  const L = [0];
  for (let i = 0; i < P.length; i++) {
    const a = P[i], b = P[(i + 1) % P.length];
    L.push(L[i] + Math.hypot(b[0] - a[0], b[1] - a[1]));
  }
  const total = L[P.length], out = [];
  let k = 0;
  for (let i = 0; i < n; i++) {
    const t = (i * total) / n;
    while (L[k + 1] < t) k++;
    const a = P[k], b = P[(k + 1) % P.length], f = (t - L[k]) / (L[k + 1] - L[k] || 1);
    out.push([a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1])]);
  }
  return out;
}

/**
 * Exact intersection area of two simple CCW polygons (Green's theorem): the boundary of A∩B is the part of
 * ∂A inside B plus the part of ∂B inside A. Continuous in the polygon coordinates, so it optimises well.
 */
export function intersectionArea(A, B) { return boundaryInside(A, B) + boundaryInside(B, A); }
function boundaryInside(A, B) {
  let sum = 0;
  const n = A.length, m = B.length;
  for (let i = 0; i < n; i++) {
    const p = A[i], q = A[(i + 1) % n], dx = q[0] - p[0], dy = q[1] - p[1];
    const ts = [0, 1];
    for (let j = 0; j < m; j++) {
      const r = B[j], s = B[(j + 1) % m], ex = s[0] - r[0], ey = s[1] - r[1];
      const den = dx * ey - dy * ex;
      if (Math.abs(den) < 1e-15) continue;
      const wx = r[0] - p[0], wy = r[1] - p[1];
      const t = (wx * ey - wy * ex) / den, u = (wx * dy - wy * dx) / den;
      if (t > 0 && t < 1 && u >= 0 && u < 1) ts.push(t);
    }
    ts.sort((a, b) => a - b);
    for (let k = 0; k + 1 < ts.length; k++) {
      const t0 = ts[k], t1 = ts[k + 1];
      if (t1 - t0 < 1e-12) continue;
      const tm = (t0 + t1) / 2;
      if (!pointInPolygon(p[0] + dx * tm, p[1] + dy * tm, B)) continue;
      const x0 = p[0] + dx * t0, y0 = p[1] + dy * t0, x1 = p[0] + dx * t1, y1 = p[1] + dy * t1;
      sum += x0 * y1 - x1 * y0;
    }
  }
  return sum / 2;
}
export function iou(A, B) {
  const i = intersectionArea(A, B);
  return i / (Math.abs(polygonArea(A)) + Math.abs(polygonArea(B)) - i);
}

// ---------------------------------------------------------------- optimisation
export function nelderMead(f, x0, steps, { maxIter = 600, tol = 1e-7 } = {}) {
  const n = x0.length;
  let S = [x0.slice()];
  for (let i = 0; i < n; i++) { const x = x0.slice(); x[i] += steps[i]; S.push(x); }
  let F = S.map(f);
  for (let it = 0; it < maxIter; it++) {
    const ord = F.map((v, i) => i).sort((a, b) => F[a] - F[b]);
    S = ord.map((i) => S[i]); F = ord.map((i) => F[i]);
    if (Math.abs(F[n] - F[0]) < tol) break;
    const c = new Array(n).fill(0);
    for (let i = 0; i < n; i++) for (let k = 0; k < n; k++) c[k] += S[i][k] / n;
    const at = (t) => c.map((ck, k) => ck + t * (S[n][k] - ck));
    const xr = at(-1), fr = f(xr);
    if (fr < F[0]) {
      const xe = at(-2), fe = f(xe);
      if (fe < fr) { S[n] = xe; F[n] = fe; } else { S[n] = xr; F[n] = fr; }
    } else if (fr < F[n - 1]) { S[n] = xr; F[n] = fr; }
    else {
      const xc = fr < F[n] ? at(-0.5) : at(0.5), fc = f(xc);
      if (fc < Math.min(fr, F[n])) { S[n] = xc; F[n] = fc; }
      else {
        for (let i = 1; i <= n; i++) { S[i] = S[i].map((v, k) => S[0][k] + 0.5 * (v - S[0][k])); F[i] = f(S[i]); }
      }
    }
  }
  const b = F.indexOf(Math.min(...F));
  return { x: S[b], f: F[b] };
}

// ---------------------------------------------------------------- similarity fit (photo px -> view mm)
/** x = [log scale, rotation rad, tx, ty]; photo y is flipped so both frames are y-up. */
export function makeSimilarity(x, pivot) {
  const s = Math.exp(x[0]), c = Math.cos(x[1]), sn = Math.sin(x[1]);
  const fwd = ([px, py]) => {
    const qx = px - pivot[0], qy = -(py - pivot[1]);
    return [s * (c * qx - sn * qy) + x[2], s * (sn * qx + c * qy) + x[3]];
  };
  const inv = ([mx, my]) => {
    const ax = (mx - x[2]) / s, ay = (my - x[3]) / s;
    return [c * ax + sn * ay + pivot[0], -(-sn * ax + c * ay) + pivot[1]];
  };
  return { fwd, inv, scale: s, rotation: x[1] };
}

/** Scale, rotate and shift the photo outline onto the silhouette for maximum overlap (IoU). */
export function fitSimilarity(outlinePx, silMM, { nPts = 128, maxRotation = 45 } = {}) {
  const P = resampleClosed(outlinePx, nPts), S = ensureCCW(resampleClosed(silMM, nPts));
  const pivot = polygonCentroid(P), target = polygonCentroid(S);
  const s0 = Math.sqrt(Math.abs(polygonArea(S)) / Math.abs(polygonArea(P)));
  const cost = (x) => { const T = makeSimilarity(x, pivot); return -iou(ensureCCW(P.map(T.fwd)), S); };
  // coarse rotation scan with centroids and areas matched, then refine the two best starts
  const scan = [];
  for (let deg = -maxRotation; deg <= maxRotation; deg += 5) {
    const x = [Math.log(s0), (deg * Math.PI) / 180, target[0], target[1]];
    scan.push({ x, f: cost(x) });
  }
  scan.sort((a, b) => a.f - b.f);
  let best = null;
  for (const start of scan.slice(0, 2)) {
    const r = nelderMead(cost, start.x, [0.05, 0.08, 0.3, 0.3]);
    if (!best || r.f < best.f) best = r;
  }
  const T = makeSimilarity(best.x, pivot);
  return { ...T, x: best.x, pivot, iou: -best.f };
}

// ---------------------------------------------------------------- boundary correspondence
/** Resample both closed curves by arc length and pick the cyclic shift that pairs them best. */
export function correspond(A, B, n = 128) {
  const a = resampleClosed(ensureCCW(A), n), b = resampleClosed(ensureCCW(B), n);
  let best = 0, bestD = Infinity;
  for (let k = 0; k < n; k++) {
    let d = 0;
    for (let i = 0; i < n; i++) { const q = b[(i + k) % n]; d += (a[i][0] - q[0]) ** 2 + (a[i][1] - q[1]) ** 2; }
    if (d < bestD) { bestD = d; best = k; }
  }
  return { A: a, B: a.map((_, i) => b[(i + best) % n]) };
}

// ---------------------------------------------------------------- thin-plate spline
function solve(M, rhs) {       // Gaussian elimination with partial pivoting; M is n×n (array of rows), rhs n×k
  const n = M.length, k = rhs[0].length;
  const A = M.map((row, i) => [...row, ...rhs[i]]);
  for (let c = 0; c < n; c++) {
    let p = c;
    for (let r = c + 1; r < n; r++) if (Math.abs(A[r][c]) > Math.abs(A[p][c])) p = r;
    [A[c], A[p]] = [A[p], A[c]];
    const piv = A[c][c];
    for (let r = c + 1; r < n; r++) {
      const f = A[r][c] / piv;
      if (f) for (let j = c; j < n + k; j++) A[r][j] -= f * A[c][j];
    }
  }
  const X = Array.from({ length: n }, () => new Array(k).fill(0));
  for (let r = n - 1; r >= 0; r--)
    for (let j = 0; j < k; j++) {
      let s = A[r][n + j];
      for (let c = r + 1; c < n; c++) s -= A[r][c] * X[c][j];
      X[r][j] = s / A[r][r];
    }
  return X;
}

export class TPS {
  /** Smooth map with TPS(src[i]) ≈ dst[i]; lambda > 0 trades exactness for smoothness. */
  constructor(src, dst, lambda = 0) {
    const n = src.length, U = (r2) => (r2 > 0 ? 0.5 * r2 * Math.log(r2) : 0);
    const M = Array.from({ length: n + 3 }, () => new Array(n + 3).fill(0));
    for (let i = 0; i < n; i++) {
      for (let j = 0; j < n; j++) M[i][j] = U((src[i][0] - src[j][0]) ** 2 + (src[i][1] - src[j][1]) ** 2) + (i === j ? lambda : 0);
      M[i][n] = M[n][i] = 1; M[i][n + 1] = M[n + 1][i] = src[i][0]; M[i][n + 2] = M[n + 2][i] = src[i][1];
    }
    const rhs = [...dst.map((p) => [p[0], p[1]]), [0, 0], [0, 0], [0, 0]];
    const X = solve(M, rhs);
    this.src = src; this.n = n;
    this.wx = Float64Array.from(X.slice(0, n), (r) => r[0]);
    this.wy = Float64Array.from(X.slice(0, n), (r) => r[1]);
    this.a = X.slice(n);
  }
  map(x, y) {
    const a = this.a;
    let u = a[0][0] + a[1][0] * x + a[2][0] * y, v = a[0][1] + a[1][1] * x + a[2][1] * y;
    for (let i = 0; i < this.n; i++) {
      const r2 = (x - this.src[i][0]) ** 2 + (y - this.src[i][1]) ** 2;
      if (r2 > 0) { const k = 0.5 * r2 * Math.log(r2); u += this.wx[i] * k; v += this.wy[i] * k; }
    }
    return [u, v];
  }
  /** Sign of the Jacobian over the inside of a polygon; a mixed sign means the warp folds over itself. */
  foldCheck(poly, grid = 48) {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const p of poly) { x0 = Math.min(x0, p[0]); x1 = Math.max(x1, p[0]); y0 = Math.min(y0, p[1]); y1 = Math.max(y1, p[1]); }
    const h = 1e-3 * Math.max(x1 - x0, y1 - y0);
    let pos = 0, neg = 0, dmin = Infinity, dmax = -Infinity;
    for (let i = 0; i <= grid; i++)
      for (let j = 0; j <= grid; j++) {
        const x = x0 + ((x1 - x0) * i) / grid, y = y0 + ((y1 - y0) * j) / grid;
        if (!pointInPolygon(x, y, poly)) continue;
        const [ax, ay] = this.map(x + h, y), [bx, by] = this.map(x - h, y), [cx, cy] = this.map(x, y + h), [dx, dy] = this.map(x, y - h);
        const det = ((ax - bx) * (cy - dy) - (ay - by) * (cx - dx)) / (4 * h * h);
        det > 0 ? pos++ : neg++;
        dmin = Math.min(dmin, det); dmax = Math.max(dmax, det);
      }
    return { folds: pos > 0 && neg > 0, detMin: dmin, detMax: dmax };
  }
}

// ---------------------------------------------------------------- COCO annotations
function rleCounts(seg) {
  if (Array.isArray(seg.counts)) return seg.counts;
  const s = seg.counts, cnts = [];          // compressed string form (pycocotools rleFrString)
  let p = 0;
  while (p < s.length) {
    let x = 0, k = 0, more = 1;
    while (more) {
      const c = s.charCodeAt(p) - 48;
      x |= (c & 0x1f) << (5 * k);
      more = c & 0x20; p++; k++;
      if (!more && c & 0x10) x |= -1 << (5 * k);
    }
    if (cnts.length > 2) x += cnts[cnts.length - 2];
    cnts.push(x);
  }
  return cnts;
}

/** COCO RLE -> polygons in pixel coordinates (via a downscaled raster). */
export function rleToPolygons(seg, maxRes = 600) {
  const [h, w] = seg.size, cnts = rleCounts(seg);
  const sc = Math.min(1, maxRes / Math.max(w, h)), W = Math.ceil(w * sc), H = Math.ceil(h * sc);
  const mask = new Uint8Array(W * H);
  let pos = 0, val = 0;
  for (const c of cnts) {
    if (val) for (let k = pos; k < pos + c; k++) { const col = Math.floor(k / h), row = k % h; mask[Math.floor(row * sc) * W + Math.floor(col * sc)] = 1; }
    pos += c; val ^= 1;
  }
  return traceContours(mask, W, H).filter((l) => Math.abs(polygonArea(l)) > 4).map((l) => l.map(([i, j]) => [(i + 0.5) / sc, (j + 0.5) / sc]));
}

/** Classes that are not part of the tooth surface and never shape the rebuilt outline. */
const OFF_TOOTH = ['Reflection', 'Extraneous matter', 'Artificial tooth'];

/** Approximate Euclidean distance (pixels) to the nearest pixel whose value is `target` (two-pass 3-4 chamfer). */
function chamfer(mask, W, H, target) {
  const d = new Float64Array(W * H);
  for (let i = 0; i < W * H; i++) d[i] = mask[i] === target ? 0 : 1e9;
  for (let y = 0; y < H; y++)
    for (let x = 0; x < W; x++) {
      const i = y * W + x;
      let v = d[i];
      if (x > 0) v = Math.min(v, d[i - 1] + 3);
      if (y > 0) {
        v = Math.min(v, d[i - W] + 3);
        if (x > 0) v = Math.min(v, d[i - W - 1] + 4);
        if (x < W - 1) v = Math.min(v, d[i - W + 1] + 4);
      }
      d[i] = v;
    }
  for (let y = H - 1; y >= 0; y--)
    for (let x = W - 1; x >= 0; x--) {
      const i = y * W + x;
      let v = d[i];
      if (x < W - 1) v = Math.min(v, d[i + 1] + 3);
      if (y < H - 1) {
        v = Math.min(v, d[i + W] + 3);
        if (x < W - 1) v = Math.min(v, d[i + W + 1] + 4);
        if (x > 0) v = Math.min(v, d[i + W - 1] + 4);
      }
      d[i] = v;
    }
  for (let i = 0; i < W * H; i++) d[i] /= 3;
  return d;
}

/** Morphological closing (dilate, then erode) with radius r pixels: bridges gaps narrower than about 2r. */
function morphClose(mask, W, H, r) {
  const toFg = chamfer(mask, W, H, 1), grown = new Uint8Array(W * H);
  for (let i = 0; i < W * H; i++) grown[i] = toFg[i] <= r ? 1 : 0;
  const toBg = chamfer(grown, W, H, 0), out = new Uint8Array(W * H);
  for (let i = 0; i < W * H; i++) out[i] = toBg[i] > r ? 1 : 0;
  return out;
}

/** Outer outline of the union of polygons (pixel coords), with gaps up to ~2·closeFrac of the size bridged. */
function unionOutline(polys, maxRes = 700, closeFrac = 0.025) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const P of polys) for (const p of P) { x0 = Math.min(x0, p[0]); x1 = Math.max(x1, p[0]); y0 = Math.min(y0, p[1]); y1 = Math.max(y1, p[1]); }
  const r = closeFrac * maxRes, pad = Math.ceil(r) + 4, sc = (maxRes - 2 * pad) / Math.max(x1 - x0, y1 - y0);
  const ox = x0 - pad / sc, oy = y0 - pad / sc;
  const mask = new Uint8Array(maxRes * maxRes);
  for (const P of polys) fillPolygon(mask, maxRes, maxRes, P.map(([x, y]) => [(x - ox) * sc, (y - oy) * sc]));
  const closed = morphClose(mask, maxRes, maxRes, r);
  return smoothClosed(largestLoop(traceContours(closed, maxRes, maxRes)).map(([i, j]) => [ox + i / sc, oy + j / sc]), 2);
}

/**
 * Parse a COCO export into photos: {id, file, width, height, tooth, toothSource, outline, outlineSource, regions}.
 * If the "Tooth Annotation" is missing or is only a small marker, the outline is rebuilt from the union of all
 * on-tooth regions.
 */
export function parseCoco(json, outlineCategory = 'Tooth Annotation') {
  const cats = Object.fromEntries(json.categories.map((c) => [c.id, c.name]));
  const byImage = new Map();
  for (const a of json.annotations) (byImage.get(a.image_id) || byImage.set(a.image_id, []).get(a.image_id)).push(a);
  const photos = [];
  for (const im of json.images) {
    const anns = byImage.get(im.id) || [];
    let outline = null, tooth = null, toothSource = null;
    const regions = [];
    for (const a of anns) {
      const cls = cats[a.category_id];
      const polys = Array.isArray(a.segmentation)
        ? a.segmentation.filter((s) => s.length >= 6).map((s) => { const P = []; for (let i = 0; i < s.length; i += 2) P.push([s[i], s[i + 1]]); return P; })
        : rleToPolygons(a.segmentation);
      if (cls === outlineCategory) {
        if (polys.length) outline = polys.reduce((p, q) => (Math.abs(polygonArea(q)) > Math.abs(polygonArea(p)) ? q : p));
        const at = a.attributes || {};
        if (typeof at['Tooth number'] === 'number') { tooth = at['Tooth number']; toothSource = 'annotation'; }
        else if (typeof at['Tooth number (from twin)'] === 'number') { tooth = at['Tooth number (from twin)']; toothSource = `twin photo ${at.twin || ''}`.trim(); }
      } else polys.forEach((P) => regions.push({ cls, polygon: P }));
    }
    const onTooth = regions.filter((r) => !OFF_TOOTH.includes(r.cls)).map((r) => r.polygon);
    let outlineSource = 'annotation';
    if (onTooth.length && (!outline || Math.abs(polygonArea(outline)) < 0.5 * Math.abs(polygonArea(unionOutline(onTooth, 200))))) {
      outline = unionOutline(onTooth);
      outlineSource = 'regions';
    }
    if (!outline || !regions.length) continue;
    photos.push({ id: im.id, file: im.file_name, width: im.width, height: im.height, tooth, toothSource, outline, outlineSource, regions });
  }
  return { photos, categories: json.categories.map((c) => c.name).filter((n) => n !== outlineCategory) };
}

export function mirrorPhoto(photo) {
  const W = photo.width, m = (P) => P.map(([x, y]) => [W - x, y]);
  return { ...photo, outline: m(photo.outline), regions: photo.regions.map((r) => ({ ...r, polygon: m(r.polygon) })), mirrored: true };
}

/** FDI helpers: 11 and 21 are the same tooth type on opposite sides. */
export const toothType = (t) => (t ? t % 10 : null);
export const toothQuadrant = (t) => (t ? Math.floor(t / 10) : null);
export const isContralateral = (a, b) => a && b && toothType(a) === toothType(b) && toothQuadrant(a) % 2 !== toothQuadrant(b) % 2;

// ---------------------------------------------------------------- full transfer
/**
 * Map a photo (already mirrored if needed) onto the restoration seen in `frame`.
 * Returns per-vertex photo pixel coordinates plus everything needed to inspect the fit.
 */
export function transfer(mesh, frame, photo, { nFit = 128, nWarp = 128 } = {}) {
  const sil = silhouette(mesh, frame, 512).polygon;
  const fit = fitSimilarity(photo.outline, sil, { nPts: nFit });
  const aligned = photo.outline.map(fit.fwd);
  const pairs = correspond(sil, aligned, nWarp);
  const gaps = pairs.A.map((a, i) => Math.hypot(a[0] - pairs.B[i][0], a[1] - pairs.B[i][1]));
  const targetPx = pairs.B.map(fit.inv);
  let tps, check, lambda = 0;
  for (lambda of [0, 1e-3, 1e-2, 0.1, 1, 10, 100]) {
    tps = new TPS(pairs.A, targetPx, lambda);
    check = tps.foldCheck(sil);
    if (!check.folds) break;
  }
  const xy = projectVertices(mesh, frame), n = xy.length / 2, photoPx = new Float64Array(n * 2);
  for (let i = 0; i < n; i++) { const [u, v] = tps.map(xy[i * 2], xy[i * 2 + 1]); photoPx[i * 2] = u; photoPx[i * 2 + 1] = v; }
  const edgeRes = pairs.A.map((a, i) => { const [u, v] = tps.map(a[0], a[1]); return Math.hypot(u - targetPx[i][0], v - targetPx[i][1]) * fit.scale; });
  return {
    silhouette: sil, fit, aligned, pairs, tps, lambda, folds: check.folds,
    gap: { mean: gaps.reduce((s, g) => s + g, 0) / gaps.length, max: Math.max(...gaps) },
    edgeResidualMax: Math.max(...edgeRes),
    photoPx,
  };
}
