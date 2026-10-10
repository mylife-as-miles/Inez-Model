"""Turn MainHair strands into a runtime strand-hair GLB for Inez (append-only).

    python3 -I tools/inez/hair/build_strand_hair.py --glb assets/characters/inez/model/v06/inez_recovery_v06.glb \
        --strands STRANDS.npz --guides GUIDES.npz --cards RESTYLED.npz --fit FIT.npz \
        --output OUT.glb --report REPORT.json

1. Guides: each 16-point guide is resampled to --particles points by arc
   length; every particle takes the skin weights of the nearest restyled card
   vertex of its card (head, hair.01-04) and the card's scalp-pinning factor.
2. Strands (from groom_with_mainhair.py): points over the pinned part of
   their guide are re-conformed to the guide's height above Inez's scalp
   (MainHair's spread is a 3-D offset and would float or sink them), then
   every point is pushed >= 1 mm out of her skin and 2 mm out of the sweater.
3. Binding: each strand point gets its guide parameter (monotonic projection
   onto the guide) and its offset and tangent in that guide's frame. The frame
   (tangent by central difference, reference normal = the guide root's scalp
   normal, binormal = T x N) is built exactly as viewer/src/hair/strand-hair.js
   builds it, so rest positions reproduce to float precision.
4. A per-point occlusion term (other strand points within 1.2 cm further out
   from the head centre) darkens inner hair.
5. GLB: two LINES primitives are appended - Inez_Hair_Guides (skinned, with
   _HAIR_FREE) and Inez_Hair_Strands (_HAIR_GUIDE, _HAIR_GS, _HAIR_U,
   _HAIR_OFFSET, _HAIR_TANGENT, _HAIR_AO, _HAIR_RADIUS) - plus the soft crown
   scalp patch from the card fit; the old hair node is detached. The original
   binary chunk stays a byte-exact prefix. No joints are added.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import v06_identity_normals_glb as glbmod  # noqa: E402
glbmod.NC['MAT4'] = 16
from v06_identity_normals_glb import GLB  # noqa: E402
from fit_hair_cards import Surface, node_world, rendered_mesh, weld  # noqa: E402
from inject_hair_glb import append_bytes, accessor  # noqa: E402


def resample_polyline(Q, n):
    a = np.r_[0, np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))]
    t = np.linspace(0, a[-1], n)
    return np.stack([np.interp(t, a, Q[:, i]) for i in range(3)], 1)


def quat_from_basis(B, N, T):
    """Rotation whose columns are (B, N, T); same convention as THREE.Quaternion.setFromRotationMatrix."""
    m00, m01, m02 = B[0], N[0], T[0]; m10, m11, m12 = B[1], N[1], T[1]; m20, m21, m22 = B[2], N[2], T[2]
    tr = m00 + m11 + m22
    if tr > 0:
        s = .5 / np.sqrt(tr + 1); return np.array([(m21 - m12) * s, (m02 - m20) * s, (m10 - m01) * s, .25 / s])
    if m00 > m11 and m00 > m22:
        s = 2 * np.sqrt(1 + m00 - m11 - m22); return np.array([.25 * s, (m01 + m10) / s, (m02 + m20) / s, (m21 - m12) / s])
    if m11 > m22:
        s = 2 * np.sqrt(1 + m11 - m00 - m22); return np.array([(m01 + m10) / s, .25 * s, (m12 + m21) / s, (m02 - m20) / s])
    s = 2 * np.sqrt(1 + m22 - m00 - m11); return np.array([(m02 + m20) / s, (m12 + m21) / s, .25 * s, (m10 - m01) / s])


def guide_frames(G, ref):
    """Per-particle quaternions for one guide (K,3) with one reference normal; hemisphere-continuous."""
    K = len(G); q = np.zeros((K, 4))
    for k in range(K):
        i0, i1 = max(0, k - 1), min(K - 1, k + 1)
        T = G[i1] - G[i0]; T = T / max(np.linalg.norm(T), 1e-12)
        N = ref - T * (ref @ T)
        if np.linalg.norm(N) < 1e-6:
            N = np.array([1.0, 0, 0]) - T * T[0]
        N = N / np.linalg.norm(N); B = np.cross(T, N)
        qq = quat_from_basis(B, N, T)
        if k and qq @ q[k - 1] < 0:
            qq = -qq
        q[k] = qq
    return q


def qrot(q, v):
    x, y, z, w = q[..., 0:1], q[..., 1:2], q[..., 2:3], q[..., 3:4]
    u = np.concatenate([x, y, z], -1)
    c = np.cross(u, v)
    return v + 2 * (w * c + np.cross(u, c))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--glb', required=True)
    ap.add_argument('--strands', required=True)
    ap.add_argument('--guides', required=True)
    ap.add_argument('--cards', required=True, help='restyled card npz (skin weights per card vertex)')
    ap.add_argument('--fit', required=True, help='card fit npz (shrink-wrapped package scalp)')
    ap.add_argument('--scalp', required=True, help='package scalp npz (all triangles) for the scalp patch')
    ap.add_argument('--cap-inset', type=float, default=.012)
    ap.add_argument('--cap-fade', type=float, default=.025)
    ap.add_argument('--output', required=True)
    ap.add_argument('--report', required=True)
    ap.add_argument('--particles', type=int, default=12)
    ap.add_argument('--old-hair-node', default='Inez_Hair_lod')
    ap.add_argument('--scalp-keep', type=int, default=3, help='keep every Nth conformed scalp point')
    args = ap.parse_args()
    if Path(args.output).exists():
        raise SystemExit('refusing to overwrite ' + args.output)

    glb = GLB(args.glb); j = glb.json; W = node_world(j)
    names = {n.get('name'): i for i, n in enumerate(j['nodes'])}
    body = Surface(*weld(*rendered_mesh(glb, names['Inez_ContinuousHumanMesh_UNAPPROVED'], W)))
    cloth = [rendered_mesh(glb, i, W) for i, n in enumerate(j['nodes']) if n.get('name', '').startswith(('Inez_Sweater', 'Inez_FineSilverNecklace')) and 'mesh' in n]
    clothS = Surface(np.vstack([p for p, _ in cloth]), np.vstack([f + sum(len(q) for q, _ in cloth[:k]) for k, (_, f) in enumerate(cloth)]))

    st = np.load(args.strands); gd = np.load(args.guides); cards = np.load(args.cards); fit = np.load(args.fit)
    SP = st['position'].astype(float); off = st['offsets'].astype(int); gid = st['guide_id'].astype(int); radius = st['radius'].astype(float)
    n_str = len(off) - 1; K = args.particles
    G16 = gd['points'].astype(float); n_g = len(G16)
    G = np.stack([resample_polyline(g, K) for g in G16])                      # (n_g, K, 3)
    gfree16 = gd['free'].astype(float)
    a16 = [np.r_[0, np.cumsum(np.linalg.norm(np.diff(g, axis=0), axis=1))] for g in G16]
    gfree = np.stack([np.interp(np.linspace(0, a[-1], K), a, f) for a, f in zip(a16, gfree16)])
    gfree = np.maximum.accumulate(gfree, axis=1)
    root_ref = gd['root_normal'].astype(float)

    # ---- guide particle skin weights from the nearest restyled card vertex of the same card
    CP = cards['position'].astype(float); Ccard = cards['card'].astype(int)
    guide_card = gd['card'].astype(int) if 'card' in gd else np.arange(n_g)
    head_joint_idx = [j['nodes'][i]['name'] for i in j['skins'][0]['joints']].index('head')
    gj = np.zeros((n_g, K, 4), np.uint16); gw = np.zeros((n_g, K, 4), np.float32)
    for c in range(n_g):
        ids = np.where(Ccard == guide_card[c])[0] if guide_card[c] >= 0 else []
        if len(ids) == 0:   # added guides (tendrils): head only
            gj[c, :, 0] = head_joint_idx; gw[c, :, 0] = 1; continue
        tree = cKDTree(CP[ids]); _, nn = tree.query(G[c])
        gj[c] = cards['joints'][ids[nn]]; gw[c] = cards['weights'][ids[nn]]

    # ---- 2. conform strands over the pinned guide part, then collisions
    head_h0, _, _ = body.signed(G.reshape(-1, 3)); head_h0 = head_h0.reshape(n_g, K)
    u = np.zeros(len(SP)); g_of_pt = np.zeros(len(SP), int)
    for k in range(n_str):
        a, b = off[k], off[k + 1]
        seg = np.r_[0, np.cumsum(np.linalg.norm(np.diff(SP[a:b], axis=0), axis=1))]
        u[a:b] = seg / max(seg[-1], 1e-9); g_of_pt[a:b] = gid[k]
    # guide parameter by monotonic projection near the expected fraction
    glen = np.array([np.linalg.norm(np.diff(g, axis=0), axis=1).sum() for g in G])
    gs = np.zeros(len(SP))
    for k in range(n_str):
        a, b = off[k], off[k + 1]; g = G[gid[k]]
        trim = min(1.0, (np.linalg.norm(np.diff(SP[a:b], axis=0), axis=1).sum()) / max(glen[gid[k]], 1e-9))
        dense = np.linspace(0, 1, 4 * K); D = np.stack([np.interp(dense * (K - 1), np.arange(K), g[:, i]) for i in range(3)], 1)
        expected = u[a:b] * trim
        d2 = ((SP[a:b, None, :] - D[None]) ** 2).sum(-1) + (.03 * (expected[:, None] - dense[None])) ** 2
        gs[a:b] = np.maximum.accumulate(dense[np.argmin(d2, 1)])
    kk = gs * (K - 1); k0 = np.clip(np.floor(kk).astype(int), 0, K - 2); t = (kk - k0)[:, None]
    free_at = gfree[g_of_pt, k0] * (1 - t[:, 0]) + gfree[g_of_pt, k0 + 1] * t[:, 0]
    h_at = head_h0[g_of_pt, k0] * (1 - t[:, 0]) + head_h0[g_of_pt, k0 + 1] * t[:, 0]
    rng = np.random.default_rng(11)
    pinned_pts = free_at < .5
    proj, nrm, _, _ = body.query(SP[pinned_pts])
    # one height offset per strand (layering), not per point: per-point noise
    # would zig-zag every strand along the scalp and read as frizz
    strand_of_pt = np.repeat(np.arange(n_str), np.diff(off))
    jitter = rng.uniform(-.001, .003, n_str)[strand_of_pt][pinned_pts]
    SP[pinned_pts] = proj + nrm * np.maximum(h_at[pinned_pts] + jitter, .001)[:, None]
    rounds = []
    for _ in range(8):
        sd_b, _, nb = body.signed(SP); sd_c, _, nc = clothS.signed(SP)
        bb = sd_b < .001 - 1e-4; bc = (sd_c < .002 - 1e-4) & (sd_c > -.05)
        rounds.append([int(bb.sum()), int(bc.sum())])
        if not (bb.any() or bc.any()):
            break
        SP[bb] += nb[bb] * (.001 - sd_b[bb])[:, None]; SP[bc] += nc[bc] * (.002 - sd_c[bc])[:, None]

    # ---- decimate the scalp section: conformed points lie flat on the scalp, so
    # every --scalp-keep'th point (plus each strand's ends) is enough there; the
    # saved points pay for the curls in the free part.
    keep = np.ones(len(SP), bool)
    if args.scalp_keep > 1:
        for k in range(n_str):
            a, b = off[k], off[k + 1]
            pin = pinned_pts[a:b]; idx = np.arange(b - a)
            keep[a:b] = ~pin | (idx % args.scalp_keep == 0) | (idx == 0) | (idx == b - a - 1)
    counts = np.add.reduceat(keep.astype(int), off[:-1])
    SP, u, gs, g_of_pt, radius = SP[keep], u[keep], gs[keep], g_of_pt[keep], radius[keep]
    off = np.r_[0, np.cumsum(counts)]
    kk = gs * (K - 1); k0 = np.clip(np.floor(kk).astype(int), 0, K - 2); t = (kk - k0)[:, None]

    # ---- 3. binding in guide frames
    frames = np.stack([guide_frames(G[g], root_ref[g]) for g in range(n_g)])   # (n_g, K, 4)
    qa = frames[g_of_pt, k0]; qb = frames[g_of_pt, k0 + 1]
    q = qa * (1 - t) + qb * t; q /= np.linalg.norm(q, axis=1, keepdims=True)
    base = G[g_of_pt, k0] * (1 - t) + G[g_of_pt, k0 + 1] * t
    qinv = q * np.array([-1, -1, -1, 1])
    offset = qrot(qinv, SP - base)
    tang = np.zeros_like(SP)
    for k in range(n_str):
        a, b = off[k], off[k + 1]; tang[a:b] = np.gradient(SP[a:b], axis=0)
    tang /= np.maximum(np.linalg.norm(tang, axis=1, keepdims=True), 1e-12)
    tang_local = qrot(qinv, tang)
    recon = base + qrot(q, offset)
    recon_err = float(np.abs(recon - SP).max())

    # ---- 4. occlusion: depth below the outer hair surface, per direction from the head centre
    centre = body.P[body.P[:, 1] > 1.6].mean(0)
    rel = SP - centre; radial = np.linalg.norm(rel, axis=1); dirn = rel / radial[:, None]
    th = np.clip((np.arccos(np.clip(dirn[:, 1], -1, 1)) / np.pi * 120).astype(int), 0, 119)
    ph = np.clip(((np.arctan2(dirn[:, 2], dirn[:, 0]) + np.pi) / (2 * np.pi) * 240).astype(int), 0, 239)
    outer = np.zeros((120, 240)); np.maximum.at(outer, (th, ph), radial)
    depth = outer[th, ph] - radial
    ao = 1 - .75 * np.clip(depth / .015, 0, 1)                                   # 1 = outer layer, .25 = deep

    # ---- 5. GLB
    src_bytes = Path(args.glb).read_bytes(); prefix = len(glb.bin)
    skin = j['skins'][0]
    jn = [j['nodes'][i]['name'] for i in skin['joints']]
    j['materials'].append({'name': 'Inez_Hair_Strands_r05', 'pbrMetallicRoughness': {'baseColorFactor': [.07, .043, .028, 1], 'metallicFactor': 0, 'roughnessFactor': .45},
                           'extras': {'renderer': 'viewer/src/hair/strand-hair.js (Kajiya-Kay ribbons); glTF fallback draws lines'}})
    smat = len(j['materials']) - 1
    j['materials'].append({'name': 'Inez_Hair_Guides_hidden', 'pbrMetallicRoughness': {'baseColorFactor': [1, 0, 1, 1]}})
    gmat = len(j['materials']) - 1
    # guides: LINES, one strip per guide
    gidx = np.concatenate([np.stack([np.arange(K - 1), np.arange(1, K)], 1) + g * K for g in range(n_g)]).astype(np.uint32)
    gattrs = {'POSITION': accessor(glb, G.reshape(-1, 3).astype(np.float32), 'VEC3', 5126, minmax=True),
              'JOINTS_0': accessor(glb, np.where(gw.reshape(-1, 4) > 0, gj.reshape(-1, 4), 0).astype(np.uint16), 'VEC4', 5123),
              'WEIGHTS_0': accessor(glb, gw.reshape(-1, 4).astype(np.float32), 'VEC4', 5126),
              '_HAIR_FREE': accessor(glb, gfree.reshape(-1, 1).astype(np.float32), 'SCALAR', 5126),
              '_HAIR_REF': accessor(glb, np.repeat(root_ref, K, axis=0).astype(np.float32), 'VEC3', 5126)}
    j['meshes'].append({'name': 'Inez_Hair_Guides', 'primitives': [{'attributes': gattrs, 'indices': accessor(glb, gidx.reshape(-1, 1), 'SCALAR', 5125, target=34963), 'material': gmat, 'mode': 1}]})
    gmesh = len(j['meshes']) - 1
    sidx = np.concatenate([np.stack([np.arange(off[k], off[k + 1] - 1), np.arange(off[k] + 1, off[k + 1])], 1) for k in range(n_str)]).astype(np.uint32)
    sattrs = {'POSITION': accessor(glb, SP.astype(np.float32), 'VEC3', 5126, minmax=True),
              '_HAIR_GUIDE': accessor(glb, g_of_pt.astype(np.float32)[:, None], 'SCALAR', 5126),
              '_HAIR_GS': accessor(glb, gs.astype(np.float32)[:, None], 'SCALAR', 5126),
              '_HAIR_U': accessor(glb, u.astype(np.float32)[:, None], 'SCALAR', 5126),
              '_HAIR_STRAND': accessor(glb, np.repeat(np.arange(n_str), np.diff(off)).astype(np.float32)[:, None], 'SCALAR', 5126),
              '_HAIR_OFFSET': accessor(glb, offset.astype(np.float32), 'VEC3', 5126),
              '_HAIR_TANGENT': accessor(glb, tang_local.astype(np.float32), 'VEC3', 5126),
              '_HAIR_AO': accessor(glb, ao.astype(np.float32)[:, None], 'SCALAR', 5126),
              '_HAIR_RADIUS': accessor(glb, (radius / max(radius.max(), 1e-9)).astype(np.float32)[:, None], 'SCALAR', 5126)}
    j['meshes'].append({'name': 'Inez_Hair_Strands', 'primitives': [{'attributes': sattrs, 'indices': accessor(glb, sidx.reshape(-1, 1), 'SCALAR', 5125, target=34963), 'material': smat, 'mode': 1}]})
    smesh = len(j['meshes']) - 1
    # Scalp patch: the whole package scalp shrink-wrapped to her head, matte root
    # colour, fading over --cap-fade from its hairline/nape boundary. Unlike the
    # card build it also covers the back of the head, where Inez's head texture
    # has a bare-skin patch left by the old ponytail shell.
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import dijkstra
    CPc = fit['cap_position'].astype(np.float32); head_joint = jn.index('head')
    Tsc = np.load(args.scalp)['triangles'].astype(np.int64)
    e = np.sort(np.vstack([Tsc[:, [0, 1]], Tsc[:, [1, 2]], Tsc[:, [2, 0]]]), 1)
    ue, cnt = np.unique(e, axis=0, return_counts=True)
    elen = np.linalg.norm(CPc[ue[:, 0]] - CPc[ue[:, 1]], axis=1)
    graph = coo_matrix((np.r_[elen, elen], (np.r_[ue[:, 0], ue[:, 1]], np.r_[ue[:, 1], ue[:, 0]])), shape=(len(CPc),) * 2).tocsr()
    inset = dijkstra(graph, indices=np.unique(ue[cnt == 1]), min_only=True)
    x = np.clip((inset - args.cap_inset) / args.cap_fade, 0, 1); cap_alpha = (x * x * (3 - 2 * x)).astype(np.float32)
    cap_tris = Tsc[(cap_alpha[Tsc] > 0).any(1)].astype(np.uint32)
    j['materials'].append({'name': 'Inez_Hair_Scalp_r05', 'alphaMode': 'BLEND', 'pbrMetallicRoughness': {'baseColorFactor': [.0267, .0169, .0106, 1], 'metallicFactor': 0, 'roughnessFactor': .9}})
    cattrs = {'POSITION': accessor(glb, CPc, 'VEC3', 5126, minmax=True), 'NORMAL': accessor(glb, fit['cap_normal'].astype(np.float32), 'VEC3', 5126),
              'COLOR_0': accessor(glb, np.c_[np.ones((len(CPc), 3)), cap_alpha].astype(np.float32), 'VEC4', 5126),
              'JOINTS_0': accessor(glb, np.tile(np.array([[head_joint, 0, 0, 0]], np.uint16), (len(CPc), 1)), 'VEC4', 5123),
              'WEIGHTS_0': accessor(glb, np.tile(np.array([[1, 0, 0, 0]], np.float32), (len(CPc), 1)), 'VEC4', 5126)}
    j['meshes'].append({'name': 'Inez_Hair_Scalp', 'primitives': [{'attributes': cattrs, 'indices': accessor(glb, cap_tris.reshape(-1, 1), 'SCALAR', 5125, target=34963), 'material': len(j['materials']) - 1, 'mode': 4}]})
    cmesh = len(j['meshes']) - 1
    old = names[args.old_hair_node]; parent = next(i for i, n in enumerate(j['nodes']) if old in n.get('children', []))
    extras = {'source': 'Guides from WhiteCap Ponytail MessyWavy (Fab, licensed by the repository owner), restyled to the reference ponytail; strands grown with the user-supplied MainHair node group',
              'tools': ['restyle_ponytail.py', 'groom_with_mainhair.py', 'build_strand_hair.py'], 'artistic_approval': False}
    j['nodes'] += [{'name': 'Inez_Hair_Guides', 'mesh': gmesh, 'extras': {**extras, 'particles_per_guide': K}},
                   {'name': 'Inez_Hair_Strands', 'mesh': smesh, 'extras': extras},
                   {'name': 'Inez_Hair_Scalp', 'mesh': cmesh, 'skin': 0}]
    kids = j['nodes'][parent]['children']; kids.remove(old); kids += [len(j['nodes']) - 3, len(j['nodes']) - 2, len(j['nodes']) - 1]
    j['nodes'][old].setdefault('extras', {})['detached_by'] = 'build_strand_hair.py (rollback: input GLB)'
    glb.write(args.output)
    assert GLB(args.output).bin[:prefix] == glb.bin[:prefix]
    report = {'tool': 'tools/inez/hair/build_strand_hair.py', 'input_sha256': hashlib.sha256(src_bytes).hexdigest(),
              'output_bytes': Path(args.output).stat().st_size, 'guides': n_g, 'particles_per_guide': K, 'strands': n_str, 'points': int(len(SP)),
              'pinned_points_conformed': int(pinned_pts.sum()), 'points_before_decimation': int(len(keep)), 'scalp_keep': args.scalp_keep, 'collision_rounds_skin_cloth': rounds,
              'rest_reconstruction_error_m': recon_err, 'occlusion_mean': float(ao.mean()), 'joints_added': 0, 'artistic_approval': False}
    Path(args.report).write_text(json.dumps(report, indent=1) + '\n')
    print(json.dumps(report, indent=1))


if __name__ == '__main__':
    main()
