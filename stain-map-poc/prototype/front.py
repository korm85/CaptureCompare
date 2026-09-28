import numpy as np, trimesh
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from shapely.geometry import Polygon
from shapely.ops import unary_union
exec(open('render.py').read().split("u, v = basis(d0)")[0])  # reuse loader, basis(), render()
d = d0
# 2D silhouette polygon in an arbitrary in-plane basis
u, v = basis(d)
P = np.stack([V@u, V@v], 1)
sil = unary_union([Polygon(P[f]) for f in F[(N@d) > 0] if Polygon(P[f]).area > 1e-12]).buffer(0)
xy = np.asarray(sil.exterior.coords)
# long axis of the silhouette (2D PCA of the filled shape, via boundary samples)
c = xy.mean(0); w, E = np.linalg.eigh(np.cov((xy-c).T)); long2d = E[:,1]
# width profile along the long axis: the incisal end of a central incisor is the wider, straighter end
t = (xy-c)@long2d; s = (xy-c)@np.array([-long2d[1], long2d[0]])
L = t.max()-t.min()
def width_at(frac):
    x = t.min()+frac*L; band = np.abs(t-x) < 0.04*L
    return s[band].max()-s[band].min()
wlo, whi = width_at(0.2), width_at(0.8)
print(f'silhouette: {L:.2f} mm long, width at 20%: {wlo:.2f} mm, at 80%: {whi:.2f} mm, max width {(s.max()-s.min()):.2f} mm, area {sil.area:.1f} mm2')
incisal2d = long2d if whi > wlo else -long2d          # 2D direction pointing to the incisal edge
up3d = -(incisal2d[0]*u + incisal2d[1]*v)              # screen-up = toward cervical/gingiva, like the photo
right3d = np.cross(up3d, d)                            # camera right (right-handed: right x up = toward viewer)
print('front (toward viewer):', np.round(d,4), '\nup (cervical):', np.round(up3d,4), '\nright:', np.round(right3d,4))
np.savez('front_view.npz', view=d, up=up3d, right=right3d, center=m.centroid)
sh, zb, fid = render(d, right3d, up3d, res=420, half=6.5)
Pp = np.stack([V@right3d, V@up3d], 1)
sil2 = unary_union([Polygon(Pp[f]) for f in F[(N@d) > 0] if Polygon(Pp[f]).area > 1e-12]).buffer(0)
q = np.asarray(sil2.exterior.coords)
np.save('mesh_silhouette_mm.npy', q)
res, half = 420, 6.5; s_ = res/(2*half)
fig, ax = plt.subplots(1, 2, figsize=(10, 5.2), gridspec_kw={'width_ratios':[1,0.6]})
ax[0].imshow(sh, cmap='gray', vmin=0, vmax=1)
ax[0].plot(q[:,0]*s_+res/2, res/2-q[:,1]*s_, color='#3fbf5f', lw=2)
ax[0].set_title('Auto front view (incisal edge down)\nwith silhouette contour'); ax[0].axis('off')
sh2, _, _ = render(right3d, -d, up3d, res=420, half=6.5)
ax[1].imshow(sh2, cmap='gray', vmin=0, vmax=1); ax[1].set_title('Side profile\n(facial surface on the left)')
ax[1].set_xlim(100, 320); ax[1].axis('off')
plt.tight_layout(); plt.savefig('front_view.png', dpi=100)
