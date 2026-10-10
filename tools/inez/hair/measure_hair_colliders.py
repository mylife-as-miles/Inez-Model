"""Measure collision proxies for the hair simulation from Inez's rendered surface.

    python3 -I tools/inez/hair/measure_hair_colliders.py \
        --glb assets/characters/inez/model/v06/inez_recovery_v06.glb \
        --out assets/characters/inez/hair/presets/inez_messywavy_cards_r01.json

Spheres and capsules are placed at fixed anatomical seeds (relative to the
head, neck and spine joints) and each radius is the measured distance from
the proxy to the nearest point of Inez's skin or sweater, minus a margin, so
every proxy is inscribed in her real surface. Proxies are stored in the local
space of the joint that carries them; the viewer transforms them each tick.
No hair geometry is read; this file holds no licensed content.
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
    ap.add_argument('--out', required=True)
    ap.add_argument('--margin', type=float, default=.002)
    args = ap.parse_args()
    glb = GLB(args.glb); j = glb.json; W = node_world(j)
    names = {n.get('name'): i for i, n in enumerate(j['nodes'])}
    bP, bF = weld(*rendered_mesh(glb, names['Inez_ContinuousHumanMesh_UNAPPROVED'], W))
    body = Surface(bP, bF)  # inside/outside comes from the closed skin surface only
    cloth = [rendered_mesh(glb, i, W) for i, n in enumerate(j['nodes']) if n.get('name', '').startswith('Inez_Sweater') and 'mesh' in n]
    cP = np.vstack([p for p, _ in cloth]); cF = np.vstack([f + sum(len(q) for q, _ in cloth[:k]) for k, (_, f) in enumerate(cloth)])
    sweater = Surface(cP, cF)

    def clearance(X):
        """Signed distance: negative inside the skin; magnitude limited by the sweater too."""
        sd, _, _ = body.signed(X)
        d_cloth = sweater.query(X)[2]
        return np.where(sd < 0, -np.minimum(-sd, d_cloth), sd)

    def joint(name):
        return W[names[name]]
    def pos(name):
        return joint(name)[:3, 3]

    head = pos('head'); n1, n3 = pos('neck01'), pos('neck03'); sp = pos('spine01')
    seeds = []
    # cranium: a row of spheres along the head's front-back axis, and one higher up
    for dz in (-.05, -.025, 0, .025):
        seeds.append(('sphere', 'head', head + [0, .06, dz]))
    seeds.append(('sphere', 'head', head + [0, .1, -.01]))
    # temples and cheeks (face-framing strands), jaw
    for sx in (-1, 1):
        seeds.append(('sphere', 'head', head + [sx * .045, .03, .0]))   # temples / above the ears
        seeds.append(('sphere', 'jaw', head + [sx * .03, -.04, .02]))   # jaw angle, for face-framing strands
    seeds.append(('sphere', 'jaw', head + [0, -.05, .045]))             # chin
    # neck and upper back
    seeds.append(('capsule', 'neck01', (n1, n1 + .6 * (n3 - n1))))
    seeds.append(('capsule', 'spine01', (sp + [0, .05, -.02], n1 + [0, -.02, -.01])))

    colliders = []
    for kind, bone, geo in seeds:
        M = joint(bone); Minv = np.linalg.inv(M)
        if kind == 'sphere':
            # move the seed to the deepest point within +-1.5 cm (largest inscribed sphere)
            g = np.linspace(-.015, .015, 7)
            cand = np.asarray(geo, float)[None] + np.stack(np.meshgrid(g, g, g, indexing='ij'), -1).reshape(-1, 3)
            sd = clearance(cand)
            best = int(np.argmin(sd)); geo = cand[best]
            r = float(-sd[best] - args.margin)
            if sd[best] > 0 or r < .01:
                continue  # no inscribed sphere of useful size near this seed
            local = (Minv @ np.r_[geo, 1])[:3]
            colliders.append({'type': 'sphere', 'bone': bone, 'center': local.round(5).tolist(), 'radius': round(r, 5)})
        else:
            a, b = (np.asarray(x, float) for x in geo)
            ts = np.linspace(0, 1, 9)
            pts = a[None] + ts[:, None] * (b - a)[None]
            sd = clearance(pts)
            r = float(np.abs(sd).min() - args.margin)
            if (sd > 0).any() or r < .01:
                continue
            colliders.append({'type': 'capsule', 'bone': bone, 'a': (Minv @ np.r_[a, 1])[:3].round(5).tolist(),
                              'b': (Minv @ np.r_[b, 1])[:3].round(5).tolist(), 'radius': round(r, 5)})
    preset = {
        'status': 'Measured proxies and provisional tuning for the fitted Ponytail MessyWavy cards; not artistically approved',
        'units': 'metres, seconds, kilograms; compliance in m/N',
        'source_glb': args.glb, 'margin_m': args.margin,
        'colliders': colliders,
        'solver': {'hz': 60, 'iterations': 6, 'particlesPerCard': 8, 'particleRadius': .003, 'mass': .001,
                   'stretchCompliance': 0, 'bendCompliance': .2,
                   'shapeComplianceRoot': .05, 'shapeComplianceTip': 5,
                   'drag': 4, 'friction': .3, 'maxSpeed': 12, 'maxDelta': .25, 'maxSubsteps': 6, 'teleportDistance': .5, 'teleportSpeed': 6,
                   'gravity': [0, -9.81, 0], 'gravityMode': 'head-relative'},
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(preset, indent=1) + '\n')
    print(json.dumps({'colliders': len(colliders), 'radii': [c['radius'] for c in colliders], 'bones': [c['bone'] for c in colliders]}))


if __name__ == '__main__':
    main()
