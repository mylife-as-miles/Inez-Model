"""Matched-view landmark comparison against the original images.

    python3 -I tools/inez/likeness_compare.py --output-dir DIR --report REPORT.json \
        --pair LABEL=REF_IMAGE@x0,y0,x1,y1=CANDIDATE.png[,CANDIDATE2.png...] [--pair ...]

For each pair the candidate whose MediaPipe yaw is closest to the reference's
is chosen. Its landmarks are aligned to the reference's by a similarity
transform (scale, rotation, translation) fitted on expression-stable points:
eye corners, nose bridge, nose tip and subnasale. The remaining error is then
reported per region in units of the reference's inter-pupil distance (IPD):

- jawline: the lower face contour, ear to ear through the chin
- nose, eyes, brows, lips: outline points

The script also writes a sheet: the reference crop, the candidate warped into
the reference frame with the same transform, and both landmark sets drawn
over a blend of the two.

Limits:
- This is 2D image geometry. It is sensitive to residual yaw and pitch and to
  expression. The originals show worried and sad expressions, so the brow and
  lip errors include expression, not only shape.
- It is not a biometric identity score, and a low error does not prove
  likeness. Use it beside a visual review, and compare it with the error
  between the two originals themselves (pass them as a pair) as the
  same-person floor.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from face_landmarks import detect  # noqa: E402

STABLE = [33, 133, 362, 263, 168, 6, 197, 1, 2]
REGIONS = {
    'jawline': [234, 93, 132, 58, 172, 136, 150, 149, 176, 148, 152, 377, 400, 378, 379, 365, 397, 288, 361, 323, 454],
    'nose': [168, 6, 197, 195, 5, 4, 1, 19, 94, 2, 98, 327, 129, 358, 49, 279, 64, 294, 48, 278, 115, 344],
    'eyes': [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246,
             263, 249, 390, 373, 374, 380, 381, 382, 362, 398, 384, 385, 386, 387, 388, 466],
    'brows': [70, 63, 105, 66, 107, 55, 65, 52, 53, 46, 300, 293, 334, 296, 336, 285, 295, 282, 283, 276],
    'lips': [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185],
}


def similarity(source, target):
    """Least-squares s, R, t with target ≈ s R source + t (Umeyama, 2D)."""
    ms, mt = source.mean(0), target.mean(0)
    a, b = source-ms, target-mt
    u, sig, vt = np.linalg.svd(b.T@a/len(a))
    d = np.sign(np.linalg.det(u@vt))
    D = np.diag([1, d])
    R = u@D@vt
    s = (sig*np.diag(D)).sum()/((a**2).sum()/len(a))
    return s, R, mt-s*R@ms


def crop_box(points, margin=1.25):
    lo, hi = points[:, :2].min(0), points[:, :2].max(0)
    centre, half = (lo+hi)/2, (hi-lo).max()/2*margin
    return [float(v) for v in (centre[0]-half, centre[1]-half*1.05, centre[0]+half, centre[1]+half*0.95)]


def compare(label, ref_path, box, candidates, out_dir):
    ref_pts, ref_pose = detect(ref_path, box)
    if ref_pts is None:
        return {'label': label, 'error': 'no face found in reference'}
    options = []
    for path in candidates:
        pts, pose = detect(path, None)
        if pts is not None:
            options.append((abs((pose or {}).get('yaw', 0)-(ref_pose or {}).get('yaw', 0)), path, pts, pose))
    if not options:
        return {'label': label, 'error': 'no face found in any candidate'}
    yaw_gap, cand_path, cand_pts, cand_pose = min(options, key=lambda o: o[0])
    ref2, cand2 = ref_pts[:, :2], cand_pts[:, :2]
    s, R, t = similarity(cand2[STABLE], ref2[STABLE])
    moved = (s*(R@cand2.T)).T+t
    ipd = float(np.linalg.norm(ref2[468]-ref2[473]))
    regions = {name: float(np.sqrt(((moved[idx]-ref2[idx])**2).sum(1).mean())/ipd) for name, idx in REGIONS.items()}
    every = sorted({i for idx in REGIONS.values() for i in idx})
    regions['all_outlines'] = float(np.sqrt(((moved[every]-ref2[every])**2).sum(1).mean())/ipd)
    # Sheet: reference crop | candidate warped into the reference frame | overlay.
    ref_img = Image.open(ref_path).convert('RGB')
    cand_img = Image.open(cand_path).convert('RGB')
    inverse = np.linalg.inv(np.vstack([np.hstack([s*R, t[:, None]]), [0, 0, 1]]))
    warped = cand_img.transform(ref_img.size, Image.AFFINE, tuple(inverse[:2].ravel()), resample=Image.BICUBIC,
                                fillcolor=(40, 40, 40))
    region = crop_box(ref2[every])
    size = 420
    panels = [im.crop(tuple(int(round(v)) for v in region)).resize((size, size), Image.LANCZOS) for im in (ref_img, warped)]
    overlay = Image.blend(panels[0], panels[1], 0.5)
    draw = ImageDraw.Draw(overlay)
    scale = size/(region[2]-region[0])
    for pts, colour in ((ref2, (60, 230, 90)), (moved, (240, 60, 200))):
        for idx in REGIONS.values():
            line = [((pts[i, 0]-region[0])*scale, (pts[i, 1]-region[1])*scale) for i in idx]
            draw.line(line, fill=colour, width=2)
    sheet = Image.new('RGB', (size*3, size+46), (24, 24, 24))
    d = ImageDraw.Draw(sheet)
    for i, (panel, title) in enumerate(zip(panels+[overlay], [f'{label}: original (evidence)',
                                                               f'{Path(cand_path).name} (render, aligned)',
                                                               'green original / magenta render'])):
        sheet.paste(panel, (i*size, 46))
        d.text((i*size+6, 6), title, fill=(235, 235, 235))
    d.text((6, 24), f"yaw ref {ref_pose['yaw']:.1f} / render {cand_pose['yaw']:.1f}   "
                    f"error/IPD: jaw {regions['jawline']:.3f} nose {regions['nose']:.3f} eyes {regions['eyes']:.3f} "
                    f"brows {regions['brows']:.3f} lips {regions['lips']:.3f}", fill=(200, 200, 200))
    out = out_dir/f'likeness_{label}.png'
    sheet.save(out)
    return {'label': label, 'reference': str(ref_path), 'reference_box': box, 'candidate': str(cand_path),
            'reference_pose': ref_pose, 'candidate_pose': cand_pose, 'yaw_gap_deg': yaw_gap,
            'error_over_ipd': {k: round(v, 4) for k, v in regions.items()}, 'sheet': str(out)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pair', action='append', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for spec in args.pair:
        label, ref, cands = spec.split('=', 2)
        ref_path, _, box = ref.partition('@')
        box = tuple(int(v) for v in box.split(',')) if box else None
        results.append(compare(label, ref_path, box, cands.split(','), out_dir))
        print(json.dumps(results[-1].get('error_over_ipd', results[-1]), sort_keys=True), results[-1]['label'], flush=True)
    Path(args.report).write_text(json.dumps(results, indent=2)+'\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
