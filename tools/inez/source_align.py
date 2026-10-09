"""Metric scale for Asset A and landmark similarity Asset B -> Asset A (no Blender).

    python3 tools/inez/source_align.py --a-landmarks a_face.json --b-landmarks b_face.json \
        --provisional provisional_report.json --eye-height 1.6335 --output source_transforms.json

A is scaled uniformly about its floor origin so the mean height of its eye
corners equals the production rig's eye height (the delivered GLB has no
physical units). B (a bust in its own normalized units) is then placed on A by
a least-squares similarity (Umeyama) from robust frontal landmarks lifted onto
each surface by scan_landmarks.py, so B's face lands exactly where A's face is.
"""
import argparse
import json
from pathlib import Path

import numpy as np

STABLE = [33, 133, 362, 263, 168, 6, 197, 195, 5, 4, 1, 2, 98, 327, 61, 291, 0, 17, 152, 10, 234, 454]


def umeyama(src, dst):
    ms, md = src.mean(0), dst.mean(0)
    xs, xd = src-ms, dst-md
    U, D, Vt = np.linalg.svd(xd.T@xs/len(src))
    E = np.eye(3)
    if np.linalg.det(U)*np.linalg.det(Vt) < 0:
        E[2, 2] = -1
    R = U@E@Vt
    s = np.trace(np.diag(D)@E)/(xs**2).sum(1).mean()
    return s, R, md-s*R@ms


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--a-landmarks', required=True)
    parser.add_argument('--b-landmarks', required=True)
    parser.add_argument('--provisional', required=True, help='JSON with a_matrix/b_matrix of the provisional blend')
    parser.add_argument('--eye-height', type=float, required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    A = json.loads(Path(args.a_landmarks).read_text())['landmarks']
    B = json.loads(Path(args.b_landmarks).read_text())['landmarks']
    prov = json.loads(Path(args.provisional).read_text())
    eye_a = np.mean([A[str(i)]['world'][2] for i in (33, 133, 362, 263)])
    s_a = args.eye_height/eye_a
    S_a = np.diag([s_a, s_a, s_a, 1.0])
    ids = [i for i in STABLE if str(i) in A and str(i) in B and A[str(i)]['facing'] > 0.3 and B[str(i)]['facing'] > 0.3]
    src = np.array([B[str(i)]['world'] for i in ids])
    dst = np.array([A[str(i)]['world'] for i in ids])*s_a
    s, R, t = umeyama(src, dst)
    S_b = np.eye(4)
    S_b[:3, :3] = s*R
    S_b[:3, 3] = t
    residual = np.linalg.norm(src@(s*R).T+t-dst, axis=1)
    a_matrix = S_a@np.array(prov['a_matrix'])
    b_matrix = S_b@np.array(prov['b_matrix'])
    report = {'a_scale_from_eye_height': s_a, 'a_eye_height_provisional_m': eye_a, 'production_eye_height_m': args.eye_height,
              'b_similarity': {'scale': s, 'rotation_deg': float(np.degrees(np.arccos(np.clip((np.trace(R)-1)/2, -1, 1)))),
                               'landmarks': len(ids), 'rms_mm': float(np.sqrt((residual**2).mean())*1000),
                               'max_mm': float(residual.max()*1000)},
              'a_matrix': a_matrix.tolist(), 'b_matrix': b_matrix.tolist(),
              'a_overall_height_m': float(prov['a_bounds'][1][2]*s_a)}
    Path(args.output).write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if not k.endswith('matrix')}, indent=1))


if __name__ == '__main__':
    main()
