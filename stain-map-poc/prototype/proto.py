"""End-to-end prototype: photo annotations (COCO) -> fitted + warped onto mesh front silhouette -> UVs -> stained render."""
import json, collections, numpy as np, trimesh
from shapely.geometry import Polygon
from shapely.validation import make_valid
from shapely import affinity
from scipy.optimize import minimize
from scipy.interpolate import RBFInterpolator
from PIL import Image, ImageDraw
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt

IMG_ID, MIRROR = 27, True          # crop_case_007 (= DSC_8088_2, tooth 11) -> restoration 21
STAIN_ORDER = ['Body Zone', 'Cervical zone', 'Incisal Zone', 'Translucent area', 'Halo', 'Mamelon', 'White stain', 'Stain', 'Crack']
COL = {'Body Zone': (120, 190, 110), 'Cervical zone': (215, 80, 70), 'Incisal Zone': (235, 150, 205), 'Translucent area': (70, 170, 215),
       'Halo': (150, 100, 200), 'Mamelon': (250, 150, 60), 'White stain': (245, 245, 245), 'Stain': (190, 175, 40), 'Crack': (20, 20, 110)}

# ---------- photo side ----------
d = json.load(open('../web/data/annotations.json'))
cats = {c['id']: c['name'] for c in d['categories']}
im = next(i for i in d['images'] if i['id'] == IMG_ID); W, H = im['width'], im['height']
anns = [a for a in d['annotations'] if a['image_id'] == IMG_ID and not isinstance(a['segmentation'], dict)]
def pts(a):
    p = np.array(a['segmentation'][0], float).reshape(-1, 2)
    if MIRROR: p[:, 0] = W - p[:, 0]
    return p
outline_px = pts(next(a for a in anns if cats[a['category_id']] == 'Tooth Annotation'))
regions = [(cats[a['category_id']], pts(a)) for a in anns if cats[a['category_id']] in STAIN_ORDER]
regions.sort(key=lambda r: STAIN_ORDER.index(r[0]))
T_img = Polygon(outline_px); T_img = T_img if T_img.is_valid else make_valid(T_img)

# ---------- mesh side ----------
m = trimesh.load('../web/data/21.stl')
fv = np.load('front_view.npz'); view, up, right = fv['view'], fv['up'], fv['right']
V = m.vertices - m.centroid; F = m.faces; N = m.face_normals
sil_mm = np.load('mesh_silhouette_mm.npy'); T_mesh = Polygon(sil_mm).buffer(0)

# ---------- step 1: similarity fit, maximize IoU ----------
# photo px (y down) -> mesh view mm (y up): p' = s*R(th)*(x, -y) + t
def to_mesh(P, x):
    s, th, tx, ty = x; c, sn = np.cos(th), np.sin(th)
    q = np.stack([P[:, 0], -P[:, 1]], 1)
    return np.stack([s*(c*q[:, 0]-sn*q[:, 1]) + tx, s*(sn*q[:, 0]+c*q[:, 1]) + ty], 1)
def iou(x):
    A = Polygon(to_mesh(outline_px, x)).buffer(0)
    return A.intersection(T_mesh).area / A.union(T_mesh).area
s0 = np.sqrt(T_mesh.area / T_img.area)
best = None
for th0 in np.radians([-20, -10, 0, 10, 20]):       # both are incisal-down, so rotation stays small
    x0 = np.array([s0, th0, 0, 0]); c0 = to_mesh(outline_px, x0).mean(0)
    x0[2:] = np.array(T_mesh.centroid.coords[0]) - c0
    r = minimize(lambda x: -iou(x), x0, method='Nelder-Mead', options=dict(xatol=1e-5, fatol=1e-6, maxiter=2000,
                 initial_simplex=[x0, x0+[0.05*s0, 0, 0, 0], x0+[0, 0.05, 0, 0], x0+[0, 0, 0.3, 0], x0+[0, 0, 0, 0.3]]))
    if best is None or r.fun < best.fun: best = r
xs = best.x
print(f'similarity fit: scale {xs[0]*1000:.2f} um/px, rotation {np.degrees(xs[1]):+.1f} deg, IoU {-best.fun:.3f}')

# ---------- step 2: boundary correspondence + TPS warp (mesh mm -> photo px) ----------
def resample(P, n):
    P = np.vstack([P, P[:1]]); seg = np.linalg.norm(np.diff(P, axis=0), axis=1); t = np.r_[0, np.cumsum(seg)]
    u = np.linspace(0, t[-1], n, endpoint=False)
    return np.stack([np.interp(u, t, P[:, 0]), np.interp(u, t, P[:, 1])], 1)
def ccw(P): return P if Polygon(P).exterior.is_ccw else P[::-1]
n = 160
A = resample(ccw(np.asarray(T_mesh.exterior.coords)[:-1]), n)          # mesh silhouette, mm
Bm = resample(ccw(to_mesh(outline_px, xs)), n)                           # photo outline in mesh frame, mm
shift = min(range(n), key=lambda k: np.sum((A - np.roll(Bm, -k, 0))**2))
Bm = np.roll(Bm, -shift, 0)
# map aligned points back to photo pixels (invert the similarity) -> TPS target
s, th, tx, ty = xs; c, sn = np.cos(-th), np.sin(-th); q = (Bm - [tx, ty]) / s
B_px = np.stack([c*q[:, 0]-sn*q[:, 1], -(sn*q[:, 0]+c*q[:, 1])], 1)
tps = RBFInterpolator(A, B_px, kernel='thin_plate_spline', smoothing=1e-3)
print(f'boundary residual after similarity: mean {np.mean(np.linalg.norm(A-Bm, axis=1)):.3f} mm, max {np.max(np.linalg.norm(A-Bm, axis=1)):.3f} mm')
# fold check: Jacobian sign on a grid inside the silhouette
gx, gy = np.meshgrid(np.linspace(*T_mesh.bounds[0::2], 80), np.linspace(*T_mesh.bounds[1::2], 80))
G = np.stack([gx.ravel(), gy.ravel()], 1); G = G[[T_mesh.contains(Polygon([(x-1e-3, y-1e-3), (x+1e-3, y-1e-3), (x, y+1e-3)])) for x, y in G]]
e = 1e-3; J = np.stack([(tps(G+[e, 0])-tps(G-[e, 0]))/(2*e), (tps(G+[0, e])-tps(G-[0, e]))/(2*e)], 2)
det = J[:, 0, 0]*J[:, 1, 1] - J[:, 0, 1]*J[:, 1, 0]
print(f'warp Jacobian det (px/mm)^2: all same sign = {np.all(det < 0) or np.all(det > 0)}  (min {det.min():.0f}, max {det.max():.0f})')

# ---------- step 3: per-vertex UV = photo pixel of its front-view projection ----------
P2 = np.stack([V@right, V@up], 1)
uv_px = tps(P2)                                   # photo pixel coords per vertex
exec(open('render.py').read().split("u, v = basis(d0)")[0].split("def render")[0])  # loader only
def render_bary(d, u, v, res, half, center=np.zeros(3)):
    s_ = res/(2*half); X = (V-center)@u*s_ + res/2; Y = res/2 - (V-center)@v*s_; Z = V@d
    zb = np.full((res, res), -np.inf); fid = -np.ones((res, res), int); bary = np.zeros((res, res, 3))
    for i, (a, b, c_) in enumerate(F):
        xs_, ys_ = X[[a, b, c_]], Y[[a, b, c_]]
        x0, x1 = int(max(np.floor(xs_.min()), 0)), int(min(np.ceil(xs_.max()), res-1))
        y0, y1 = int(max(np.floor(ys_.min()), 0)), int(min(np.ceil(ys_.max()), res-1))
        if x1 < x0 or y1 < y0: continue
        gx_, gy_ = np.meshgrid(np.arange(x0, x1+1)+0.5, np.arange(y0, y1+1)+0.5)
        den = (ys_[1]-ys_[2])*(xs_[0]-xs_[2]) + (xs_[2]-xs_[1])*(ys_[0]-ys_[2])
        if abs(den) < 1e-12: continue
        l0 = ((ys_[1]-ys_[2])*(gx_-xs_[2]) + (xs_[2]-xs_[1])*(gy_-ys_[2]))/den
        l1 = ((ys_[2]-ys_[0])*(gx_-xs_[2]) + (xs_[0]-xs_[2])*(gy_-ys_[2]))/den; l2 = 1-l0-l1
        ins = (l0 >= -1e-9) & (l1 >= -1e-9) & (l2 >= -1e-9); z = l0*Z[a]+l1*Z[b]+l2*Z[c_]
        sub = zb[y0:y1+1, x0:x1+1]; upd = ins & (z > sub)
        sub[upd] = z[upd]; fid[y0:y1+1, x0:x1+1][upd] = i
        bary[y0:y1+1, x0:x1+1][upd] = np.stack([l0, l1, l2], -1)[upd]
    return zb, fid, bary
# visibility from the front view: vertex depth vs z-buffer
res, half = 600, 6.5
zb, fid, _ = render_bary(view, right, up, res, half)
s_ = res/(2*half); vx = np.clip((P2[:, 0]*s_ + res/2).astype(int), 0, res-1); vy = np.clip((res/2 - P2[:, 1]*s_).astype(int), 0, res-1)
vn = m.vertex_normals
visible = ((V@view) >= zb[vy, vx] - 0.05) & ((vn@view) > -0.05)
print(f'visible (stainable) vertices: {visible.sum()} of {len(V)}')

# ---------- stain map in photo space (vector polygons -> RGBA image, layered) ----------
stain = Image.new('RGBA', (W, H), (0, 0, 0, 0))
for name, p in regions:
    lay = Image.new('RGBA', (W, H), (0, 0, 0, 0)); ImageDraw.Draw(lay).polygon([tuple(q) for q in p], fill=COL[name]+(255,))
    stain = Image.alpha_composite(stain, lay)
clip = Image.new('L', (W, H), 0); ImageDraw.Draw(clip).polygon([tuple(q) for q in outline_px], fill=255)
stain.putalpha(Image.fromarray(np.minimum(np.array(stain)[..., 3], np.array(clip))))
stain_np = np.array(stain).astype(float)/255

def shade_view(d, u, v, res=520, half=6.5):
    zb_, fid_, bary_ = render_bary(d, u, v, res, half)
    img = np.ones((res, res, 3))
    ok = fid_ >= 0; f = F[fid_[ok]]; b = bary_[ok]
    uv = (uv_px[f] * b[..., None]).sum(1); vis = (visible[f].astype(float) * b).sum(1)
    lam = np.clip(np.abs(N[fid_[ok]]@d), 0, 1)*0.65 + 0.35
    base = np.array([0.93, 0.91, 0.86])
    xi = np.clip(uv[:, 0].astype(int), 0, W-1); yi = np.clip(uv[:, 1].astype(int), 0, H-1)
    sm = stain_np[yi, xi]; a = sm[:, 3:4] * 0.85 * np.clip(vis, 0, 1)[:, None]
    img[ok] = ((1-a)*base + a*sm[:, :3]) * lam[:, None]
    return img
def rot(vec, axis, deg):
    axis = axis/np.linalg.norm(axis); t = np.radians(deg)
    return vec*np.cos(t) + np.cross(axis, vec)*np.sin(t) + axis*np.dot(axis, vec)*(1-np.cos(t))
views = [('front view', view, right, up)]
for name, deg in [('rotated 35° mesially', 35), ('rotated 35° distally', -35)]:
    dv = rot(view, up, deg); views.append((name, dv, np.cross(up, dv), up))
dv = rot(view, right, 35); views.append(('from above-incisal 35°', dv, right, np.cross(dv, right)))

fig = plt.figure(figsize=(20, 10.5))
ax = fig.add_subplot(2, 4, 1)
ax.imshow(np.array(stain)); ax.plot(*outline_px[[*range(len(outline_px)), 0]].T, 'k', lw=1.5)
x0, y0, x1, y1 = T_img.bounds; pad = 0.08*(x1-x0); ax.set_xlim(x0-pad, x1+pad); ax.set_ylim(y1+pad, y0-pad)
ax.set_title(f'photo annotations ({im["file_name"]}, #11)\nmirrored -> 21', fontsize=11); ax.axis('off')
ax = fig.add_subplot(2, 4, 2)
ax.fill(*sil_mm.T, color='#cfd8dc'); ax.plot(*sil_mm.T, color='#37474f', lw=2, label='mesh silhouette')
ax.plot(*np.vstack([to_mesh(outline_px, xs), to_mesh(outline_px, xs)[:1]]).T, color='#d81b60', lw=1.5, label=f'photo outline, best fit (IoU {-best.fun:.3f})')
for k in range(0, n, 8): ax.plot([A[k, 0], Bm[k, 0]], [A[k, 1], Bm[k, 1]], color='#fb8c00', lw=1)
ax.set_aspect('equal'); ax.legend(loc='lower center', fontsize=9, bbox_to_anchor=(0.5, -0.18)); ax.set_title('step 1-2: similarity fit + boundary pairs (orange)', fontsize=11); ax.axis('off')
# warped annotation in mesh frame (2D check)
ax = fig.add_subplot(2, 4, 3)
gxx, gyy = np.meshgrid(np.linspace(-6.5, 6.5, 400), np.linspace(6.5, -6.5, 400)); Gp = np.stack([gxx.ravel(), gyy.ravel()], 1)
inside = np.array([T_mesh.contains(Polygon([(x, y), (x+1e-4, y), (x, y+1e-4)])) for x, y in Gp]).reshape(400, 400)
q = tps(Gp); xi = np.clip(q[:, 0].astype(int), 0, W-1); yi = np.clip(q[:, 1].astype(int), 0, H-1)
w2 = stain_np[yi, xi].reshape(400, 400, 4); w2[~inside] = [1, 1, 1, 1]
ax.imshow(w2[..., :3]*w2[..., 3:]+(1-w2[..., 3:]), extent=[-6.5, 6.5, -6.5, 6.5]); ax.plot(*sil_mm.T, color='#37474f', lw=1.5)
ax.set_title('step 3: regions warped into\nmesh silhouette (front view, 2D)', fontsize=11); ax.axis('off')
fig.add_subplot(2, 4, 4).axis('off')
for k, (name, dv, uu, vv) in enumerate(views):
    ax = fig.add_subplot(2, 4, 5+k); ax.imshow(shade_view(dv, uu, vv)); ax.set_title(f'stained 21 veneer: {name}', fontsize=11); ax.axis('off')
handles = [plt.Line2D([], [], color=np.array(COL[n_])/255, lw=8, label=n_) for n_ in STAIN_ORDER if any(r[0] == n_ for r in regions)]
fig.legend(handles=handles, loc='upper right', bbox_to_anchor=(0.98, 0.92), fontsize=12, title='stain layers')
plt.tight_layout(); plt.savefig('prototype_result.png', dpi=80)
print('regions:', collections.Counter(r[0] for r in regions))
