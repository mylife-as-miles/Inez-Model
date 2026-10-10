"""Tidy restyled guides toward the references' clean, pulled-back hair.

    python3 -I tools/inez/hair/tidy_guides.py --glb assets/characters/inez/model/v06/inez_recovery_v06.glb \
        --guides RESTYLED_GUIDES.npz --fit FIT.npz --scalp SCALP.npz --out TIDY_GUIDES.npz --report REPORT.json

In the references Inez's hair is pulled back smoothly into the ponytail, with
only the temple tendrils hanging loose. The restyled package guides still carry
some of the package's loose hair, which the strand groom turns into frizz:

1. Loose scalp hair (every guide that is not ponytail): each guide is cut where
   it first lifts off the scalp (pinning factor > --lift) or where it leaves the
   scalp patch after having been on it (patch opacity < .5: the hairline at the
   nape and over the ears). What remains lies on the scalp and is fully pinned.
   This removes the crown tuft and the side and nape locks that hung below the
   ears; guides left shorter than --min-length are dropped.
2. Ponytail strays: the tail bundle's centre line is the per-height median of
   the free ponytail points; a guide straying further than --tail-radius from it
   is pulled in (its offset scaled down, faded in with its pinning factor).

Guides keep 16 points; the ponytail, roots and normals are otherwise unchanged.
"""
import argparse
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
from build_strand_hair import scalp_alpha  # noqa: E402


def arclength(Q):
    return np.r_[0, np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))]


def cut(Q, s_end, n):
    a = arclength(Q); t = np.linspace(0, s_end, n)
    return np.stack([np.interp(t, a, Q[:, i]) for i in range(3)], 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--glb', required=True)
    ap.add_argument('--guides', required=True)
    ap.add_argument('--fit', required=True)
    ap.add_argument('--scalp', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--report', required=True)
    ap.add_argument('--lift', type=float, default=.25, help='pinning factor at which loose scalp hair is cut')
    ap.add_argument('--min-length', type=float, default=.015)
    ap.add_argument('--tail-radius', type=float, default=.075, help='max distance of a ponytail guide from the bundle centre line')
    ap.add_argument('--cap-inset', type=float, default=.012)
    ap.add_argument('--cap-fade', type=float, default=.025)
    args = ap.parse_args()
    glb = GLB(args.glb); j = glb.json; W = node_world(j)
    names = {n.get('name'): i for i, n in enumerate(j['nodes'])}
    body = Surface(*weld(*rendered_mesh(glb, names['Inez_ContinuousHumanMesh_UNAPPROVED'], W)))
    g = dict(np.load(args.guides)); G = g['points'].astype(float); F = g['free'].astype(float); tail = g['tail'].astype(bool)
    n_g, n_pts, _ = G.shape
    fit = np.load(args.fit); CP = fit['cap_position'].astype(float)
    alpha = scalp_alpha(CP, np.load(args.scalp)['triangles'].astype(np.int64), args.cap_inset, args.cap_fade)
    tree = cKDTree(CP)

    def patch_alpha(Q):
        d, i = tree.query(Q)
        return np.where(d < .02, alpha[i], 0.0)

    # ---- 1. loose scalp hair
    keep = np.ones(n_g, bool); trimmed = []; out_pts = G.copy(); out_free = F.copy()
    for c in np.where(~tail)[0]:
        Q = G[c]; f = F[c]; a = arclength(Q); pa = patch_alpha(Q)
        s_end = a[-1]; why = None
        lift = np.where(f > args.lift)[0]
        if len(lift):
            k = lift[0]
            s_end = a[k - 1] + (a[k] - a[k - 1]) * (args.lift - f[k - 1]) / max(f[k] - f[k - 1], 1e-9) if k else 0.0
            why = 'lift'
        on = np.where(pa >= .5)[0]
        if len(on):
            off = np.where((pa < .5) & (np.arange(n_pts) > on[0]))[0]
            if len(off) and a[off[0]] < s_end:
                s_end = a[off[0]]; why = 'hairline'
        if why is None:
            continue
        if s_end < args.min_length:
            keep[c] = False; trimmed.append({'guide': int(c), 'action': 'dropped', 'reason': why, 'from_m': round(float(a[-1]), 4)}); continue
        R = cut(Q, s_end, n_pts)
        # lie on the scalp at the guide's own root height
        h = max(float(body.signed(Q[:1])[0][0]), .001)
        p, nrm, _, _ = body.query(R); R = p + nrm * h; R[0] = Q[0]
        out_pts[c] = R; out_free[c] = 0
        trimmed.append({'guide': int(c), 'action': 'cut', 'reason': why, 'from_m': round(float(a[-1]), 4), 'to_m': round(float(s_end), 4)})

    # ---- 2. ponytail strays
    pt = np.where(tail)[0]; fr = F[pt] > .5; allp = G[pt][fr]
    ys = np.linspace(allp[:, 1].min(), allp[:, 1].max(), 30)
    cen = np.array([np.median(allp[np.abs(allp[:, 1] - y) < .02][:, [0, 2]], 0) for y in ys])
    pulled = []
    for i, c in enumerate(pt):
        Q = G[c]; cxz = np.stack([np.interp(Q[:, 1], ys, cen[:, 0]), np.interp(Q[:, 1], ys, cen[:, 1])], 1)
        d = np.linalg.norm(Q[:, [0, 2]] - cxz, axis=1) * (F[c] > .5)
        if d.max() <= args.tail_radius:
            continue
        s = 1 - (1 - args.tail_radius / d.max()) * F[c]           # 1 at the pinned root, full pull where free
        R = Q.copy(); R[:, [0, 2]] = cxz + (Q[:, [0, 2]] - cxz) * s[:, None]
        out_pts[c] = R; pulled.append({'guide': int(c), 'max_offset_m': round(float(d.max()), 4)})

    out = {k: v[keep] for k, v in g.items()}
    out['points'] = out_pts[keep].astype(np.float32); out['free'] = out_free[keep].astype(np.float32)
    np.savez_compressed(args.out, **out)
    report = {'tool': 'tools/inez/hair/tidy_guides.py', 'guides_in': int(n_g), 'guides_out': int(keep.sum()),
              'loose_cut': sum(t['action'] == 'cut' for t in trimmed), 'loose_dropped': sum(t['action'] == 'dropped' for t in trimmed),
              'ponytail_pulled_in': len(pulled), 'tail_radius_m': args.tail_radius, 'lift': args.lift, 'trimmed': trimmed, 'pulled': pulled}
    Path(args.report).write_text(json.dumps(report, indent=1) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('trimmed', 'pulled')}, indent=1))


if __name__ == '__main__':
    main()
