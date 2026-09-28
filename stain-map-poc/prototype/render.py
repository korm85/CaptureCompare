import trimesh, numpy as np
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
m = trimesh.load('../web/data/21.stl')
V, F = m.vertices - m.centroid, m.faces
N = m.face_normals
d0 = np.load('front_dir.npy')

def basis(d):
    d = d/np.linalg.norm(d)
    a = np.array([1,0,0]) if abs(d[0])<0.9 else np.array([0,1,0])
    u = np.cross(d,a); u/=np.linalg.norm(u); v = np.cross(d,u)
    return u, v

def render(d, u, v, res=360, half=6.0):
    """orthographic z-buffer; camera looks along -d (sits at +d side). returns shade, depth, faceid"""
    s = res/(2*half)
    X = (V@u)*s + res/2; Y = res/2 - (V@v)*s; Z = V@d   # larger Z = closer to camera
    zb = np.full((res,res), -np.inf); fid = -np.ones((res,res), int)
    for i,(a,b,c) in enumerate(F):
        xs, ys = X[[a,b,c]], Y[[a,b,c]]
        x0,x1 = int(max(np.floor(xs.min()),0)), int(min(np.ceil(xs.max()),res-1))
        y0,y1 = int(max(np.floor(ys.min()),0)), int(min(np.ceil(ys.max()),res-1))
        if x1<x0 or y1<y0: continue
        gx, gy = np.meshgrid(np.arange(x0,x1+1)+0.5, np.arange(y0,y1+1)+0.5)
        den = (ys[1]-ys[2])*(xs[0]-xs[2]) + (xs[2]-xs[1])*(ys[0]-ys[2])
        if abs(den) < 1e-12: continue
        l0 = ((ys[1]-ys[2])*(gx-xs[2]) + (xs[2]-xs[1])*(gy-ys[2]))/den
        l1 = ((ys[2]-ys[0])*(gx-xs[2]) + (xs[0]-xs[2])*(gy-ys[2]))/den
        l2 = 1-l0-l1
        inside = (l0>=-1e-9)&(l1>=-1e-9)&(l2>=-1e-9)
        z = l0*Z[a]+l1*Z[b]+l2*Z[c]
        sub = zb[y0:y1+1, x0:x1+1]; subf = fid[y0:y1+1, x0:x1+1]
        upd = inside & (z > sub)
        sub[upd] = z[upd]; subf[upd] = i
    shade = np.full((res,res), np.nan)
    ok = fid>=0
    shade[ok] = np.clip(N[fid[ok]]@d, 0, 1)*0.8+0.2
    return shade, zb, fid

u, v = basis(d0)
fig, axs = plt.subplots(1, 3, figsize=(15,5.4))
stats = {}
for ax, (name, d, uu) in zip(axs, [('+d', d0, u), ('-d', -d0, -u)]):
    sh, zb, fid = render(d, uu, v)
    ok = fid>=0
    # convexity test: depth at silhouette center vs near the silhouette edge
    ys, xs = np.nonzero(ok)
    cy, cx = ys.mean(), xs.mean()
    r = np.hypot(ys-cy, xs-cx); rmax = r.max()
    zc = zb[ys[r<0.25*rmax], xs[r<0.25*rmax]].mean()
    ze = zb[ys[r>0.75*rmax], xs[r>0.75*rmax]].mean()
    # fraction of visible pixels whose face normal points toward camera
    stats[name] = (zc-ze, ok.sum())
    ax.imshow(sh, cmap='gray', vmin=0, vmax=1); ax.set_title(f'view from {name}: center-minus-edge depth {zc-ze:+.2f} mm'); ax.axis('off')
# side view (perpendicular) to see the profile
sh, zb, fid = render(u, v, d0)
axs[2].imshow(sh, cmap='gray', vmin=0, vmax=1); axs[2].set_title('side view (+d is to the right)'); axs[2].axis('off')
plt.tight_layout(); plt.savefig('views.png', dpi=90)
print(stats)
# thickness map along d: for each pixel, front depth - back depth
sh1, zf, f1 = render(d0, u, v)
sh2, zbk, f2 = render(-d0, -u, v)
zbk = zbk[:, ::-1]  # mirror back view to align pixels
okb = (f1>=0)&(f2[:, ::-1]>=0)
th = zf[okb] + zbk[okb]
print('thickness along view axis: median %.2f  p10 %.2f  p90 %.2f  max %.2f mm' % (np.median(th), *np.percentile(th,[10,90]), th.max()))
