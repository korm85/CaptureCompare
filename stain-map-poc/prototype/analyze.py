import trimesh, numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union
m = trimesh.load('../web/data/21.stl')
V, F = m.vertices - m.centroid, m.faces
N, A = m.face_normals, m.area_faces

def basis(d):
    d = d/np.linalg.norm(d)
    a = np.array([1,0,0]) if abs(d[0])<0.9 else np.array([0,1,0])
    u = np.cross(d,a); u/=np.linalg.norm(u); v = np.cross(d,u)
    return u, v

def sil_area(d):
    u, v = basis(d)
    P = np.stack([V@u, V@v],1)
    front = (N@d) > 0
    polys = [Polygon(P[f]) for f in F[front]]
    polys = [p for p in polys if p.area>1e-12]
    return unary_union(polys).area

# fibonacci sphere, approximate projected area = 0.5*sum|n.d|A
k = 4000
i = np.arange(k)+0.5
phi = np.arccos(1-2*i/k); th = np.pi*(1+5**0.5)*i
D = np.stack([np.cos(th)*np.sin(phi), np.sin(th)*np.sin(phi), np.cos(phi)],1)
approx = 0.5*np.abs(D@N.T)@A
j = np.argmax(approx)
print('approx max area', approx[j], 'dir', D[j])
w, vecs = np.linalg.eigh(np.cov(V.T))
pmin = vecs[:,0]
print('PCA thinnest axis', pmin, 'angle to max-area dir (deg)', np.degrees(np.arccos(abs(pmin@D[j]))))
# refine with exact silhouette area around best
best = D[j]; bestA = sil_area(best)
for step in [8, 4, 2, 1, 0.5]:
    improved = True
    while improved:
        improved = False
        u, v = basis(best)
        for du, dv in [(1,0),(-1,0),(0,1),(0,-1)]:
            c = best + np.tan(np.radians(step))*(du*u+dv*v); c/=np.linalg.norm(c)
            a = sil_area(c)
            if a > bestA: best, bestA, improved = c, a, True
print('exact max silhouette area', bestA, 'dir', best)
print('silhouette area along PCA thinnest', sil_area(pmin))
# area falloff: how sensitive is the area to tilt?
u, v = basis(best)
for ang in [5, 10, 15, 20]:
    vals = []
    for t in np.linspace(0, 2*np.pi, 8, endpoint=False):
        c = best + np.tan(np.radians(ang))*(np.cos(t)*u+np.sin(t)*v); c/=np.linalg.norm(c)
        vals.append(sil_area(c))
    print(f'tilt {ang:2d} deg: area {min(vals):.1f}..{max(vals):.1f}  ({100*min(vals)/bestA:.1f}%..{100*max(vals)/bestA:.1f}%)')
np.save('front_dir.npy', best)
