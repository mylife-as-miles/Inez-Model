"""Add face-framing tendril guides at Inez's temples (the references show loose
curly tendrils in front of the ears, hanging to about the jaw).

    python3 -I tools/inez/hair/add_tendrils.py --glb assets/characters/inez/model/v06/inez_recovery_v06.glb \
        --guides GUIDES.npz --out GUIDES_WITH_TENDRILS.npz --report REPORT.json [--per-side 9]

Roots are taken from the existing hairline: guide roots on the temple side of
the head, in front of the ear (|x| 4.5-7.5 cm, z > 0, y 1.62-1.72 m). From each
root a 16-point guide first follows the scalp down and slightly back for about
1.5 cm, then hangs down in front of the ear with a slight outward and forward
lean, kept at a clearance from her skin that grows from 4 mm to 16 mm at the tip.
Lengths are 10-16 cm (tips near the jaw). The pinning factor is 0 for the
first two points (on the scalp) and 1 from the fourth point on. The MainHair
groom curls them like the rest. Appended guides are flagged kind = 1 and are
skinned to the head joint only.
"""
import argparse
import json
from pathlib import Path

import numpy as np

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import v06_identity_normals_glb as glbmod  # noqa: E402
glbmod.NC['MAT4'] = 16
from v06_identity_normals_glb import GLB  # noqa: E402
from fit_hair_cards import Surface, node_world, rendered_mesh, weld  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--glb', required=True)
    ap.add_argument('--guides', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--report', required=True)
    ap.add_argument('--per-side', type=int, default=9)
    ap.add_argument('--seed', type=int, default=5)
    args = ap.parse_args()
    glb = GLB(args.glb); j = glb.json; W = node_world(j)
    names = {n.get('name'): i for i, n in enumerate(j['nodes'])}
    body = Surface(*weld(*rendered_mesh(glb, names['Inez_ContinuousHumanMesh_UNAPPROVED'], W)))
    g = dict(np.load(args.guides)); G = g['points'].astype(float); n_pts = G.shape[1]
    rng = np.random.default_rng(args.seed)
    roots = G[:, 0]
    new, report_sides = [], {}
    # Temple hairline roots: taken from the side with more candidate guide roots
    # and mirrored (then projected onto her skin) so both sides match.
    def candidates(sx):
        return np.where((sx * roots[:, 0] > .045) & (sx * roots[:, 0] < .075) & (roots[:, 2] > 0) & (roots[:, 1] > 1.62) & (roots[:, 1] < 1.72))[0]
    src = max((-1, 1), key=lambda sx: len(candidates(sx)))
    cand = candidates(src)
    if len(cand) < 3:
        raise SystemExit('too few temple hairline roots')
    order = cand[np.argsort(roots[cand, 1])]
    base = roots[order[np.linspace(0, len(order) - 1, args.per_side).round().astype(int)]]
    for sx in (-1, 1):
        anchors = base * np.array([sx * src, 1, 1])
        report_sides['left' if sx > 0 else 'right'] = {'source_side': 'left' if src > 0 else 'right', 'candidates': int(len(cand)), 'roots_y_m': anchors[:, 1].round(4).tolist()}
        for a in anchors:
            p, n, _, _ = body.query((a + rng.uniform(-.003, .003, 3))[None])
            p = p[0] + n[0] * .002
            L = rng.uniform(.10, .16); step = L / (n_pts - 1)
            pts = [p]
            for k in range(1, n_pts):
                f = k / (n_pts - 1)
                if k <= 2:   # follow the scalp down and slightly back
                    d = np.array([0, -1, -.25])
                else:        # hang in front of the ear, lean out and forward a little
                    d = np.array([sx * .18, -1, .12 + rng.uniform(-.05, .05)])
                d = d / np.linalg.norm(d)
                q = pts[-1] + d * step
                sd, sp, sn = body.signed(q[None])
                clearance = .004 + .012 * f
                if sd[0] < clearance:
                    q = sp[0] + sn[0] * clearance
                pts.append(q)
            new.append(np.array(pts))
    T = np.array(new)
    free_t = np.clip((np.arange(n_pts) - 1) / 2, 0, 1)[None].repeat(len(T), 0)
    rn = np.stack([body.query(t[:1])[1][0] for t in T])
    out = dict(g)
    out['points'] = np.concatenate([g['points'], T.astype(np.float32)])
    out['free'] = np.concatenate([g['free'], free_t.astype(np.float32)])
    out['root_normal'] = np.concatenate([g['root_normal'], rn.astype(np.float32)])
    out['card'] = np.concatenate([g['card'], -np.ones(len(T), np.int32)])
    out['tail'] = np.concatenate([g['tail'], np.zeros(len(T), bool)])
    out['kind'] = np.concatenate([np.zeros(len(g['points']), np.int8), np.ones(len(T), np.int8)])
    np.savez_compressed(args.out, **out)
    lengths = np.linalg.norm(np.diff(T, axis=1), axis=2).sum(1)
    report = {'tool': 'tools/inez/hair/add_tendrils.py', 'tendrils': int(len(T)), 'per_side': args.per_side, 'sides': report_sides,
              'length_m': {'min': float(lengths.min()), 'max': float(lengths.max())}, 'tip_y_m': {'min': float(T[:, -1, 1].min()), 'max': float(T[:, -1, 1].max())},
              'guides_total': int(len(out['points']))}
    Path(args.report).write_text(json.dumps(report, indent=1) + '\n')
    print(json.dumps(report, indent=1))


if __name__ == '__main__':
    main()
