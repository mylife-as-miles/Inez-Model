"""Fit a v04 head refinement from CC0 MakeHuman feature targets (no Blender).

    python3 tools/inez/head_refine_fit.py --config tools/inez/model_head_config_v03.json \
        --map qa/model/head_landmarks_v04_iter0.json --reference-image ORIGINAL_B --reference-box 853,0,1280,714 \
        --targets assets/characters/inez/model/base-source/targets --output tools/inez/model_head_refine_v04.json \
        [--previous tools/inez/model_head_refine_v04.json]

Landmarks detected on a real render of the current head are compared with the
landmarks of original B (eye-aligned, IPD-normalized). Each target's effect on
the mapped licensed vertices gives a linear model; bounded ridge least squares
picks small target weights. The result is a separate refinement layer over the
reviewed v03 fit; identity fit defaults are untouched. Expression-sensitive
landmarks (brows, inner lips) are down-weighted. This is proportion fitting,
not a biometric likeness claim.
"""
import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import lsq_linear

sys.path.insert(0, str(Path(__file__).resolve().parent))
from model_source import read_obj, shape_vertices, fit_vertices, rig_sources, joint_point
from model_head_targets import MODIFIERS, FIELDS, target_delta, field_delta, refinement_delta

GROUPS = {
    'lower_oval': ([454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234], 1.0),
    'upper_oval': ([10, 338, 297, 332, 284, 251, 389, 356, 127, 162, 21, 54, 103, 67, 109], 0.15),
    'lips_outer': ([61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185], 0.9),
    'nose': ([1, 2, 98, 327, 129, 358, 49, 279, 48, 278, 64, 294, 168, 6, 197, 195, 5, 4, 19, 94], 1.0),
    'eyes': ([263, 249, 390, 373, 374, 380, 381, 382, 362, 398, 384, 385, 386, 387, 388, 466,
              33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246], 0.55),
    'brows': ([276, 283, 282, 295, 285, 300, 293, 334, 296, 336, 46, 53, 52, 65, 55, 70, 63, 105, 66, 107], 0.10),
}
def normalized(points2d, left, right):
    """Eye-aligned, IPD-normalized image coordinates (x right, y down)."""
    mid = (left+right)/2
    axis = right-left
    ipd = np.linalg.norm(axis)
    c, s = axis/ipd
    rot = np.array([[c, s], [-s, c]])
    return (points2d-mid)@rot.T/ipd


def detect(image, box=None):
    command = [sys.executable, str(Path(__file__).resolve().parent/'face_landmarks.py'), image]
    if box:
        command += ['--box', box]
    out = subprocess.run(command, capture_output=True, text=True)
    data = json.loads(out.stdout.strip().splitlines()[-1])
    if not data.get('face'):
        raise SystemExit('No face detected in '+image)
    return np.array(data['landmarks'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    parser.add_argument('--map', required=True)
    parser.add_argument('--reference-image', required=True)
    parser.add_argument('--reference-box')
    parser.add_argument('--targets', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--previous')
    parser.add_argument('--ridge', type=float, default=0.02)
    parser.add_argument('--bound', type=float, default=0.9)
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    source, uv, groups = read_obj()
    basis = shape_vertices(source, config['source_shape_weights'])
    fitted = np.array(fit_vertices(basis, config['fit_controls']))
    previous = json.loads(Path(args.previous).read_text())['weights'] if args.previous else {}
    rig, _ = rig_sources()
    count = len(fitted)
    deltas = {}
    for name, (lo, hi) in MODIFIERS.items():
        deltas[name] = (target_delta(args.targets, lo, count), target_delta(args.targets, hi, count))
    current = fitted+refinement_delta(fitted, previous, args.targets)
    for name in FIELDS:
        field = field_delta(current, name)
        deltas[name] = (-field, field)
    mapping = json.loads(Path(args.map).read_text())
    model_px = np.array(mapping['landmarks_px'])[:, :2]
    reference_px = detect(args.reference_image, args.reference_box)[:, :2]
    use, weights = [], []
    for name, (indices, weight) in GROUPS.items():
        for i in indices:
            if str(i) in mapping['mapping']:
                use.append(i)
                weights.append(weight)
    use = np.array(use)
    weights = np.array(weights)
    model_n = normalized(model_px, model_px[468], model_px[473])
    reference_n = normalized(reference_px, reference_px[468], reference_px[473])
    residual = (reference_n[use]-model_n[use])  # (k, 2)
    source_ids = np.array([mapping['mapping'][str(i)]['source_index'] for i in use])

    def eye_centers(points):
        return [np.array(joint_point(points, rig, rig['bones']['eye.'+s]['head'])) for s in ('L', 'R')]

    def project(points):
        # Front view: image x = source x, image y (down) = -source y.
        pts = points[source_ids]
        L, R = eye_centers(points)
        # Image-left pupil (MediaPipe 468) is the character's right eye (-x).
        img = np.stack((pts[:, 0], -pts[:, 1]), axis=1)
        return normalized(img, np.array([R[0], -R[1]]), np.array([L[0], -L[1]]))
    base_proj = project(current)
    columns, names = [], []
    for name, (lo, hi) in deltas.items():
        for sign, delta in ((-1, lo), (1, hi)):
            if delta is None:
                continue
            moved = project(current+delta)
            columns.append((moved-base_proj).reshape(-1))
            names.append((name, sign))
    J = np.stack(columns, axis=1)
    W = np.repeat(np.sqrt(weights), 2)
    A = np.vstack((J*W[:, None], np.sqrt(args.ridge)*np.eye(J.shape[1])))
    b = np.concatenate((residual.reshape(-1)*W, np.zeros(J.shape[1])))
    upper = []
    for name, sign in names:
        prev = previous.get(name, 0.0)
        # Remaining room so the cumulative signed weight stays within the bound.
        room = args.bound-prev*sign if prev*sign > 0 else args.bound
        upper.append(max(1e-6, room))
    solution = lsq_linear(A, b, bounds=(np.zeros(len(names)), np.array(upper)), method='bvls')
    step = {}
    for (name, sign), value in zip(names, solution.x):
        step[name] = step.get(name, 0.0)+sign*float(value)
    combined = {k: round(previous.get(k, 0.0)+step.get(k, 0.0), 4) for k in set(previous) | set(step)}
    combined = {k: v for k, v in combined.items() if abs(v) > 0.01}
    predicted = residual.reshape(-1)-J@solution.x
    report = {
        'revision': 'v04', 'base_revision': 'v03', 'method': 'bounded ridge least squares on eye-aligned landmarks',
        'reference': 'original B face panel (frontal, final facial authority shared with original A)',
        'weights': dict(sorted(combined.items())),
        'step_weights': {k: round(v, 4) for k, v in sorted(step.items()) if abs(v) > 0.005},
        'landmark_rms_before': float(np.sqrt(np.mean(residual**2))),
        'landmark_rms_predicted_after': float(np.sqrt(np.mean(predicted**2))),
        'targets_source': 'CC0 MakeHuman targets (model/base-source/targets, provenance.json)',
        'expression_note': 'Original B shows a worried expression; brows/inner lips are down-weighted.',
        'not_biometric': True,
    }
    Path(args.output).write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: report[k] for k in ('landmark_rms_before', 'landmark_rms_predicted_after', 'step_weights')}, indent=1))


if __name__ == '__main__':
    main()
