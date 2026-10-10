"""Fit the licensed Ponytail MessyWavy hair cards to Inez's rendered head.

    python3 -I tools/inez/hair/fit_hair_cards.py \
        --glb assets/characters/inez/model/v06/inez_recovery_v06.glb \
        --package-npz SCRATCH/hair_work/pkg --lod 0 \
        --out SCRATCH/hair_work/fit_lod0.npz --report assets/characters/inez/hair/qa/fit_r01.json

Inputs are only read. The package meshes come from export_package_meshes.py
(glTF space). Inez's head is the surface the viewer renders at rest: base
positions plus every morph target at its default weight. Her face is never
moved; only the hair is transformed.

1. Similarity ICP (scale, rotation, translation) from the package scalp cap
   to Inez's cranium, trimmed to the closest 85 % of pairs.
2. Local wrap: the residual from each aligned scalp-cap vertex to Inez's
   surface is smoothed over the cap and interpolated onto every card vertex
   (Gaussian weights, 2.5 cm), so cards keep their height above the scalp.
3. Collision clean-up against Inez's body (ears included), sweater and
   necklace: everything beyond the card root stays >= clearance outside;
   pushes are smoothed along each card, then a final hard pass guarantees it.
4. Root-to-tip parameter per card, skin weights on the existing head and
   hair.01-04 bones (no joints are added), and a scalp cap shrink-wrapped
   0.8 mm above her head.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from v06_identity_normals_glb import GLB  # noqa: E402


# ----------------------------------------------------------------- geometry
def closest_points(P, tri_pts, tri_normals_v, tree, k=12):
    """Exact closest point on a triangle soup for each query point.
    tri_pts (T,3,3), tri_normals_v (T,3,3) vertex normals; tree on centroids.
    Returns point, interpolated normal, distance, triangle index."""
    _, cand = tree.query(P, k=k)
    best_d = np.full(len(P), np.inf); best_p = np.zeros_like(P); best_n = np.zeros_like(P); best_t = np.zeros(len(P), int)
    for j in range(k):
        t = cand[:, j]
        a, b, c = tri_pts[t, 0], tri_pts[t, 1], tri_pts[t, 2]
        p, bary = _closest_on_triangle(P, a, b, c)
        d = np.linalg.norm(P - p, axis=1)
        better = d < best_d
        if better.any():
            n = (tri_normals_v[t, 0] * bary[:, :1] + tri_normals_v[t, 1] * bary[:, 1:2] + tri_normals_v[t, 2] * bary[:, 2:3])
            n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
            best_d[better], best_p[better], best_n[better], best_t[better] = d[better], p[better], n[better], t[better]
    return best_p, best_n, best_d, best_t


def _closest_on_triangle(p, a, b, c):
    # Ericson, Real-Time Collision Detection 5.1.5, vectorised; returns point and barycentrics.
    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = (ab * ap).sum(1), (ac * ap).sum(1)
    bp = p - b; d3, d4 = (ab * bp).sum(1), (ac * bp).sum(1)
    cp = p - c; d5, d6 = (ab * cp).sum(1), (ac * cp).sum(1)
    va = d3 * d6 - d5 * d4; vb = d5 * d2 - d1 * d6; vc = d1 * d4 - d3 * d2
    denom = np.where(np.abs(va + vb + vc) < 1e-30, 1e-30, va + vb + vc)
    v = vb / denom; w = vc / denom; u = 1 - v - w
    bary = np.stack([u, v, w], 1)
    def setb(mask, uu, vv, ww):
        bary[mask] = np.stack([uu[mask], vv[mask], ww[mask]], 1)
    one, zero = np.ones(len(p)), np.zeros(len(p))
    # edge/vertex regions (order matters: later assignments win in priority below)
    m = (vc <= 0) & (d1 >= 0) & (d3 <= 0)
    t = d1 / np.where(np.abs(d1 - d3) < 1e-30, 1e-30, d1 - d3); setb(m, 1 - t, t, zero)
    m = (vb <= 0) & (d2 >= 0) & (d6 <= 0)
    t = d2 / np.where(np.abs(d2 - d6) < 1e-30, 1e-30, d2 - d6); setb(m, 1 - t, zero, t)
    m = (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0)
    t = (d4 - d3) / np.where(np.abs((d4 - d3) + (d5 - d6)) < 1e-30, 1e-30, (d4 - d3) + (d5 - d6)); setb(m, zero, 1 - t, t)
    setb((d6 >= 0) & (d5 <= d6), zero, zero, one)
    setb((d3 >= 0) & (d4 <= d3), zero, one, zero)
    setb((d1 <= 0) & (d2 <= 0), one, zero, zero)
    point = a * bary[:, :1] + b * bary[:, 1:2] + c * bary[:, 2:3]
    return point, bary


def vertex_normals(P, F):
    n = np.zeros_like(P)
    fn = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
    for i in range(3):
        np.add.at(n, F[:, i], fn)
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


class Surface:
    def __init__(self, P, F):
        self.P, self.F = P, F
        self.N = vertex_normals(P, F)
        self.tri = P[F]; self.trin = self.N[F]
        self.tree = cKDTree(self.tri.mean(1))

    def query(self, X, k=12):
        return closest_points(X, self.tri, self.trin, self.tree, k)

    def signed(self, X, k=12):
        p, n, d, _ = self.query(X, k)
        s = np.sign(((X - p) * n).sum(1)); s[s == 0] = 1
        return s * d, p, n


def umeyama(src, dst):
    mu_s, mu_d = src.mean(0), dst.mean(0)
    xs, xd = src - mu_s, dst - mu_d
    cov = xd.T @ xs / len(src)
    U, S, Vt = np.linalg.svd(cov)
    D = np.eye(3); D[2, 2] = np.sign(np.linalg.det(U @ Vt))
    R = U @ D @ Vt
    scale = (S * np.diag(D)).sum() / (xs ** 2).sum(1).mean()
    t = mu_d - scale * R @ mu_s
    return scale, R, t


def similarity_pitch(src, dst):
    """Scale, rotation about the X axis only (pitch) and translation, least squares.
    Keeps a symmetric hairstyle level instead of rolling it toward ear asymmetry."""
    mu_s, mu_d = src.mean(0), dst.mean(0)
    xs, xd = src - mu_s, dst - mu_d
    # optimal angle in the y-z plane
    num = (xs[:, 1] * xd[:, 2] - xs[:, 2] * xd[:, 1]).sum()
    den = (xs[:, 1] * xd[:, 1] + xs[:, 2] * xd[:, 2]).sum()
    a = np.arctan2(num, den)
    R = np.array([[1, 0, 0], [0, np.cos(a), -np.sin(a)], [0, np.sin(a), np.cos(a)]])
    scale = (xd * (xs @ R.T)).sum() / (xs ** 2).sum()
    return scale, R, mu_d - scale * R @ mu_s


# ------------------------------------------------------------ GLB scene
def node_world(j):
    W = {}
    def trs(n):
        if 'matrix' in n:
            return np.array(n['matrix'], float).reshape(4, 4).T
        M = np.eye(4)
        if 'scale' in n: M = np.diag([*n['scale'], 1.0]) @ M
        if 'rotation' in n:
            x, y, z, w = n['rotation']
            R = np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)], [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)], [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
            R4 = np.eye(4); R4[:3, :3] = R; M = R4 @ M
        if 'translation' in n:
            T = np.eye(4); T[:3, 3] = n['translation']; M = T @ M
        return M
    def walk(i, parent):
        W[i] = parent @ trs(j['nodes'][i])
        for c in j['nodes'][i].get('children', []):
            walk(c, W[i])
    for r in j['scenes'][j.get('scene', 0)]['nodes']:
        walk(r, np.eye(4))
    return W


def rendered_mesh(glb, node_index, W):
    j = glb.json; node = j['nodes'][node_index]; mesh = j['meshes'][node['mesh']]
    weights = node.get('weights', mesh.get('weights', []))
    Ps, Fs, off = [], [], 0
    for prim in mesh['primitives']:
        P = glb.accessor(prim['attributes']['POSITION'])
        for w, tgt in zip(weights, prim.get('targets', [])):
            if w and 'POSITION' in tgt:
                P = P + w * glb.accessor(tgt['POSITION'])
        F = glb.accessor(prim['indices']).astype(np.int64).reshape(-1, 3)
        M = W[node_index]; P = P @ M[:3, :3].T + M[:3, 3]
        Ps.append(P); Fs.append(F + off); off += len(P)
    return np.vstack(Ps), np.vstack(Fs)


def weld(P, F, tol=1e-6):
    q = np.round(P / tol).astype(np.int64)
    _, first, inv = np.unique(q, axis=0, return_index=True, return_inverse=True)
    return P[first], inv.ravel()[F]


# ------------------------------------------------------------ card helpers
def card_rows(part, s):
    return [np.where(part == c)[0] for c in range(part.max() + 1)]


def smooth_on_mesh(values, F, n_vertices, iterations, mask=None):
    """Uniform Laplacian smoothing of a per-vertex field over mesh edges."""
    e = np.vstack([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    e = np.vstack([e, e[:, ::-1]])
    deg = np.bincount(e[:, 0], minlength=n_vertices).astype(float)
    v = values.copy()
    for _ in range(iterations):
        acc = np.zeros_like(v); np.add.at(acc, e[:, 0], v[e[:, 1]])
        nv = np.where(deg[:, None] > 0, acc / np.maximum(deg[:, None], 1), v)
        v = nv if mask is None else np.where(mask[:, None], nv, v)
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--glb', required=True)
    ap.add_argument('--package-npz', required=True)
    ap.add_argument('--lod', type=int, default=0)
    ap.add_argument('--out', required=True)
    ap.add_argument('--report', required=True)
    ap.add_argument('--clearance', type=float, default=.0015)
    ap.add_argument('--cloth-clearance', type=float, default=.003)
    ap.add_argument('--root-fraction', type=float, default=.06)
    ap.add_argument('--rotation', choices=['full', 'pitch'], default='pitch')
    ap.add_argument('--cap-inset', type=float, default=.012)
    ap.add_argument('--cap-fade', type=float, default=.025)
    ap.add_argument('--cap-min-height', type=float, default=1.68, help='world Y below which the cap fades out (above the ears)')
    args = ap.parse_args()

    glb = GLB(args.glb); j = glb.json; W = node_world(j)
    names = {n.get('name'): i for i, n in enumerate(j['nodes'])}
    body_P, body_F = rendered_mesh(glb, names['Inez_ContinuousHumanMesh_UNAPPROVED'], W)
    body_P, body_F = weld(body_P, body_F)
    cloth = []
    for nm in ('Inez_Sweater', 'Inez_Sweater_HoleFill', 'Inez_FineSilverNecklace'):
        idx = [i for i, n in enumerate(j['nodes']) if n.get('name', '').startswith(nm) and 'mesh' in n]
        for i in idx:
            P, F = rendered_mesh(glb, i, W); cloth.append((P, F))
    cloth_P = np.vstack([c[0] for c in cloth]); cloth_F = np.vstack([c[1] + sum(len(x[0]) for x in cloth[:k]) for k, c in enumerate(cloth)])
    body = Surface(body_P, body_F)
    # cranium region of Inez used for alignment: above the ear canal level
    head_top = body_P[:, 1].max()

    pkg = Path(args.package_npz)
    scalp = dict(np.load(pkg / 'scalp.npz')); cards = dict(np.load(pkg / f'cards_lod{args.lod}.npz'))
    pkg_scalp = Surface(scalp['position'], scalp['triangles'])

    # ---- 1. similarity ICP: package scalp cap -> Inez cranium
    src = scalp['position']
    s, R, t = 1.0, np.eye(3), np.zeros(3)
    # initial guess: match the top of the head and the cap centroid in x/z
    t = np.array([0, head_top - src[:, 1].max(), 0.0])
    cxz = body_P[body_P[:, 1] > head_top - .08][:, [0, 2]].mean(0) - src[src[:, 1] > src[:, 1].max() - .08][:, [0, 2]].mean(0)
    t[[0, 2]] = cxz
    history = []
    for it in range(150):
        X = s * src @ R.T + t
        p, n, d, _ = body.query(X)
        keep = d <= np.quantile(d, .85)
        s, R, t = (umeyama if args.rotation == 'full' else similarity_pitch)(src[keep], p[keep])
        history.append(float(np.mean(d[keep])))
        if it > 5 and abs(history[-2] - history[-1]) < 1e-7:
            break
    X = s * src @ R.T + t
    sd, p, n = body.signed(X)
    angle = float(np.degrees(np.arccos(np.clip((np.trace(R) - 1) / 2, -1, 1))))

    # ---- 2. residual field on the cap, smoothed, applied to cards
    residual = p - X
    residual = smooth_on_mesh(residual, scalp['triangles'], len(X), 40)
    cap_tree = cKDTree(X)
    C = s * cards['position'] @ R.T + t
    dist, nn = cap_tree.query(C, k=24)
    w = np.exp(-(dist / .025) ** 2); w_sum = w.sum(1, keepdims=True)
    interp = (residual[nn] * w[..., None]).sum(1) / np.maximum(w_sum, 1e-12)
    far = w_sum[:, 0] < 1e-6
    interp[far] = residual[nn[far, 0]]
    C = C + interp
    cap_fit = X + residual

    # ---- card structure: part id, root-to-tip parameter from UV
    part = cards['part']; uv = cards['uv']
    n_cards = int(part.max() + 1)
    s_param = np.zeros(len(C)); root_d = np.zeros(n_cards); card_len = np.zeros(n_cards)
    pkg_d = np.abs(pkg_scalp.signed(cards['position'])[0])
    axis_votes = [0, 0]
    for c in range(n_cards):
        ids = np.where(part == c)[0]
        rng = uv[ids].max(0) - uv[ids].min(0)
        ax = int(np.argmax(rng)); axis_votes[ax] += 1
        val = uv[ids, ax]
        lo, hi = val.min(), val.max()
        a_end = ids[val <= lo + .02 * (hi - lo) + 1e-9]; b_end = ids[val >= hi - .02 * (hi - lo) - 1e-9]
        root_is_lo = pkg_d[a_end].mean() <= pkg_d[b_end].mean()
        sp = (val - lo) / max(hi - lo, 1e-9)
        s_param[ids] = sp if root_is_lo else 1 - sp
        root_d[c] = min(pkg_d[a_end].mean(), pkg_d[b_end].mean())
        order = ids[np.argsort(s_param[ids])]
        card_len[c] = np.linalg.norm(np.diff(C[order], axis=0), axis=1).sum() / 2

    # ---- 3. collisions (body incl. ears; cloth for the ponytail)
    clothS = Surface(cloth_P, cloth_F)
    F = cards['triangles']
    before = C.copy()
    movable = s_param > args.root_fraction
    stats = {}
    for rnd in range(12):
        sd_b, pb, nb = body.signed(C); sd_c, pc, nc = clothS.signed(C)
        push = np.zeros_like(C)
        bad_b = movable & (sd_b < args.clearance - 1e-4)
        push[bad_b] += nb[bad_b] * (args.clearance - sd_b[bad_b])[:, None]
        bad_c = movable & (sd_c < args.cloth_clearance - 1e-4) & (sd_c > -.03)
        push[bad_c] += nc[bad_c] * (args.cloth_clearance - sd_c[bad_c])[:, None]
        stats[f'round_{rnd}'] = {'body_violations': int(bad_b.sum()), 'cloth_violations': int(bad_c.sum())}
        if rnd < 3:  # soft rounds, then hard rounds until clear
            # spread the correction along the cards so they bend instead of kinking
            disp = smooth_on_mesh(push, F, len(C), 6)
            C = C + np.maximum(np.linalg.norm(push, axis=1), np.linalg.norm(disp, axis=1))[:, None] * \
                (disp / np.maximum(np.linalg.norm(disp, axis=1, keepdims=True), 1e-12))
        else:
            C = C + push
    sd_b, _, _ = body.signed(C); sd_c, _, _ = clothS.signed(C)
    final = {'body_min_clearance_m_beyond_root': float(sd_b[movable].min()),
             'cloth_min_clearance_m_beyond_root': float(sd_c[movable & (sd_c > -.03)].min()) if (movable & (sd_c > -.03)).any() else None,
             'max_correction_m': float(np.linalg.norm(C - before, axis=1).max()),
             'vertices_moved_over_5mm': int((np.linalg.norm(C - before, axis=1) > .005).sum()),
             'cards_moved_over_5mm': int(len(np.unique(part[np.linalg.norm(C - before, axis=1) > .005]))),
             'large_correction_centroid_m': (C[np.linalg.norm(C - before, axis=1) > .01].mean(0).tolist() if (np.linalg.norm(C - before, axis=1) > .01).any() else None),
             'mean_correction_m': float(np.linalg.norm(C - before, axis=1).mean())}

    # ---- normals: rotate authored package normals
    N = cards['normal'] @ R.T
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)

    # ---- 4. skin weights on existing bones
    skin = j['skins'][0]; jnames = [j['nodes'][i]['name'] for i in skin['joints']]
    def bone_point(name, end):
        # glTF has no tails; use joint world positions; tail of hair.04 from its child-less direction
        return W[skin['joints'][jnames.index(name)]][:3, 3]
    chain_names = ['hair.01', 'hair.02', 'hair.03', 'hair.04']
    heads = np.array([bone_point(nm, 0) for nm in chain_names])
    tail = heads[-1] + (heads[-1] - heads[-2])
    chain = np.vstack([heads, tail])
    seg = np.diff(chain, axis=0); seg_len = np.linalg.norm(seg, axis=1)
    def project(Xp):
        best = np.full(len(Xp), np.inf); best_u = np.zeros(len(Xp))
        acc = np.concatenate([[0], np.cumsum(seg_len)])
        for i in range(len(seg)):
            tt = np.clip(((Xp - chain[i]) @ seg[i]) / seg_len[i] ** 2, 0, 1)
            d = np.linalg.norm(Xp - (chain[i] + tt[:, None] * seg[i]), axis=1)
            b = d < best; best[b] = d[b]; best_u[b] = acc[i] + tt[b] * seg_len[i]
        return best_u / acc[-1], best
    u_chain, d_chain = project(C)
    sd_scalp = np.abs(Surface(cap_fit, scalp['triangles']).signed(C)[0])
    # ponytail membership: vertices behind/below the tie, further than 2 cm from the scalp
    tie = chain[0]
    # Free factor for the runtime simulation: 0 while a card lies on the scalp,
    # rising to 1 once it leaves it (1.2 -> 3 cm above Inez's head), and never
    # decreasing toward the tip, so a card is pinned up to where it lifts off.
    head_sd = body.signed(C)[0]
    free = np.clip((head_sd - .012) / .018, 0, 1)
    for c in range(n_cards):
        ids = np.where(part == c)[0]; order = ids[np.argsort(s_param[ids])]
        free[order] = np.maximum.accumulate(free[order])
    # glTF: +Z is forward, so the ponytail hangs behind (more negative Z) and below the tie
    pony = (C[:, 2] < tie[2] + .03) & (C[:, 1] < tie[1] + .05)
    blend = free * pony
    head_j = jnames.index('head'); hair_j = [jnames.index(nm) for nm in chain_names]
    joints = np.zeros((len(C), 4), np.uint16); weights = np.zeros((len(C), 4), np.float32)
    joints[:, 0] = head_j; weights[:, 0] = 1
    # piecewise-linear along the chain: bone k gets a hat function centred mid-bone
    centers = (np.concatenate([[0], np.cumsum(seg_len)])[:-1] + seg_len / 2) / seg_len.sum()
    for vi in np.where(blend > 0)[0]:
        u = u_chain[vi]
        k = int(np.clip(np.searchsorted(centers, u) - 1, 0, 3)); k2 = min(k + 1, 3)
        a = 0.0 if k == k2 else np.clip((u - centers[k]) / (centers[k2] - centers[k]), 0, 1)
        if u < centers[0]: k, k2, a = 0, 0, 0.0
        wb = blend[vi]
        joints[vi] = [head_j, hair_j[k], hair_j[k2], head_j]
        weights[vi] = [1 - wb, wb * (1 - a), wb * a if k2 != k else 0, 0]
        if k2 == k: weights[vi, 1] = wb
    weights /= weights.sum(1, keepdims=True)

    # ---- scalp cap: shrink-wrap 0.8 mm above Inez's head, interior only.
    # Only triangles at least --cap-inset (geodesic, from the package scalp's
    # boundary = its hairline/nape) are kept, so the cap stays under dense hair
    # and never shows as a band on the forehead or neck. It hides Inez's glossy
    # painted crown between the cards (the crown "ridge").
    _, pc_, nc_ = body.signed(cap_fit)
    cap_final = pc_ + nc_ * .0008
    cap_N = vertex_normals(cap_final, scalp['triangles'])
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import dijkstra
    T = scalp['triangles']
    edges = np.vstack([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
    key = np.sort(edges, 1)
    uniq, counts = np.unique(key, axis=0, return_counts=True)
    boundary = np.unique(uniq[counts == 1])
    lengths = np.linalg.norm(cap_final[uniq[:, 0]] - cap_final[uniq[:, 1]], axis=1)
    graph = coo_matrix((np.r_[lengths, lengths], (np.r_[uniq[:, 0], uniq[:, 1]], np.r_[uniq[:, 1], uniq[:, 0]])), shape=(len(cap_final),) * 2).tocsr()
    inset = dijkstra(graph, indices=boundary, min_only=True)
    # Soft-edged crown patch: opaque on top of the head, fading to zero over
    # --cap-fade toward the package hairline/nape and below --cap-min-height
    # (above the ears), so it never draws a line or a flat patch on the neck.
    def smooth(x):
        x = np.clip(x, 0, 1); return x * x * (3 - 2 * x)
    ear_top = args.cap_min_height
    cap_alpha = smooth((inset - args.cap_inset) / args.cap_fade) * smooth((cap_final[:, 1] - ear_top) / args.cap_fade)
    cap_tris = T[(cap_alpha[T] > 0).any(1)]

    np.savez_compressed(args.out, position=C.astype(np.float32), normal=N.astype(np.float32),
        uv=np.stack([uv[:, 0], 1 - uv[:, 1]], 1).astype(np.float32), triangles=F.astype(np.uint32),
        card=part.astype(np.float32), s=s_param.astype(np.float32), free=free.astype(np.float32), joints=joints, weights=weights,
        cap_position=cap_final.astype(np.float32), cap_normal=cap_N.astype(np.float32),
        cap_uv=np.stack([scalp['uv'][:, 0], 1 - scalp['uv'][:, 1]], 1).astype(np.float32),
        cap_triangles=cap_tris.astype(np.uint32), cap_alpha=cap_alpha.astype(np.float32))

    report = {
        'tool': 'tools/inez/hair/fit_hair_cards.py', 'lod': args.lod, 'artistic_approval': False,
        'input_glb_sha256': hashlib.sha256(Path(args.glb).read_bytes()).hexdigest(),
        'inez_surface': 'rendered rest surface: base + default-weight morph targets (identity layers), welded',
        'similarity': {'mode': args.rotation, 'scale': float(s), 'rotation_deg': angle, 'translation_m': t.tolist(), 'icp_iterations': len(history),
                       'cap_mean_trimmed_distance_m': history[-1],
                       'cap_signed_distance_after_m': {'median': float(np.median(sd)), 'p05': float(np.quantile(sd, .05)), 'p95': float(np.quantile(sd, .95))}},
        'local_wrap': {'residual_max_m': float(np.linalg.norm(residual, axis=1).max()), 'residual_mean_m': float(np.linalg.norm(residual, axis=1).mean()), 'kernel_sigma_m': .025},
        'cards': {'count': n_cards, 'vertices': int(len(C)), 'triangles': int(len(F)), 'uv_axis_votes_u_v': axis_votes,
                  'length_m': {'min': float(card_len.min()), 'median': float(np.median(card_len)), 'max': float(card_len.max())},
                  'root_distance_to_package_scalp_m_median': float(np.median(root_d))},
        'collision': {'clearance_m': args.clearance, 'cloth_clearance_m': args.cloth_clearance, 'root_fraction_exempt': args.root_fraction, 'rounds': stats, **final},
        'free_factor': {'pinned_vertices': int((free == 0).sum()), 'free_vertices': int((free >= 1).sum()), 'cards_with_free_part': int(len(np.unique(part[free > 0])))},
        'skin': {'joints_used': ['head'] + chain_names, 'joints_added': 0, 'ponytail_vertices': int((blend > 0).sum()),
                 'chain_world_m': chain.tolist()},
        'scalp_cap': {'vertices': int(len(cap_final)), 'offset_m': .0008, 'inset_m': args.cap_inset, 'fade_m': args.cap_fade, 'min_height_m': args.cap_min_height, 'triangles_kept': int(len(cap_tris)), 'triangles_total': int(len(T))},
        'bounds_m': {'min': C.min(0).tolist(), 'max': C.max(0).tolist()},
    }
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, indent=1) + '\n')
    print(json.dumps({k: report[k] for k in ('similarity', 'local_wrap', 'cards', 'collision', 'skin')}, indent=1)[:3000])


if __name__ == '__main__':
    main()
