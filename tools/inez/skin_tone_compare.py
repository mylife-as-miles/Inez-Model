"""Compare skin colour between an original reference and a render, region by region.

    python3 -I tools/inez/skin_tone_compare.py --reference references/inez_portraits.jpg \
        --reference-box 640,0,1280,956 --render front.png [--current-gain 1,1,1] [--output tone.json]

MediaPipe face landmarks locate matching skin patches (forehead, both
cheeks, nose bridge, chin) in both images; each patch is a disc of 0.12x the
inter-pupil distance. Per patch the linear-RGB median is taken between the
15th and 85th luminance percentiles, so specular highlights, freckles and
lashes do not dominate. The originals were lit neutrally (the grey knit reads
R/G 1.00 in them), so their skin chroma is usable as a target.

The suggested gain moves the render's average R/G and G/B onto the
reference's at unchanged luminance; it multiplies --current-gain (the gain
already applied to the albedo that produced the render). This is a colour
measurement aid, not an identity score.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from face_landmarks import detect

PATCHES = {'forehead': (151, 108, 337), 'cheek_image_left': (50, 117), 'cheek_image_right': (280, 346),
           'nose_bridge': (197,), 'chin': (199,)}
LUMA = np.array([0.2126, 0.7152, 0.0722])


def linear(img):
    return np.where(img <= 0.04045, img/12.92, ((img+0.055)/1.055)**2.4)


def measure(path, box=None):
    from PIL import Image
    points, pose = detect(path, box)
    if points is None:
        raise SystemExit(f'No face found in {path}')
    img = linear(np.asarray(Image.open(path).convert('RGB'), np.float64)/255)
    h, w = img.shape[:2]
    iod = float(np.linalg.norm(points[468, :2]-points[473, :2]))
    radius = 0.12*iod
    yy, xx = np.mgrid[0:h, 0:w]
    out = {}
    for name, ids in PATCHES.items():
        mask = np.zeros((h, w), bool)
        for i in ids:
            x, y = points[i, :2]
            x0, x1 = int(max(0, x-radius)), int(min(w, x+radius+1))
            y0, y1 = int(max(0, y-radius)), int(min(h, y+radius+1))
            sub = (xx[y0:y1, x0:x1]-x)**2+(yy[y0:y1, x0:x1]-y)**2 < radius**2
            mask[y0:y1, x0:x1] |= sub
        px = img[mask]
        lum = px@LUMA
        lo, hi = np.percentile(lum, (15, 85))
        px = px[(lum >= lo) & (lum <= hi)]
        m = np.median(px, axis=0)
        out[name] = {'linear_rgb': m.tolist(), 'luminance': float(m@LUMA), 'r_over_g': float(m[0]/m[1]),
                     'g_over_b': float(m[1]/m[2]), 'pixels': int(len(px))}
    return out, pose, iod


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--reference', required=True)
    parser.add_argument('--reference-box', default='')
    parser.add_argument('--render', required=True)
    parser.add_argument('--current-gain', default='1,1,1')
    parser.add_argument('--use', default='forehead,cheek_image_left,cheek_image_right,chin')
    parser.add_argument('--output')
    args = parser.parse_args()
    box = tuple(int(v) for v in args.reference_box.split(',')) if args.reference_box else None
    ref, ref_pose, _ = measure(args.reference, box)
    ren, ren_pose, _ = measure(args.render)
    use = args.use.split(',')

    def mean_ratios(d):
        return (float(np.exp(np.mean([np.log(d[k]['r_over_g']) for k in use]))),
                float(np.exp(np.mean([np.log(d[k]['g_over_b']) for k in use]))),
                float(np.exp(np.mean([np.log(d[k]['luminance']) for k in use]))))
    rg_ref, gb_ref, lum_ref = mean_ratios(ref)
    rg_ren, gb_ren, lum_ren = mean_ratios(ren)
    # Relative gain (g = 1): r *= rg_ref/rg_ren, b *= gb_ren/gb_ref; then renormalise luminance.
    rel = np.array([rg_ref/rg_ren, 1.0, gb_ren/gb_ref])
    ren_mean = np.exp(np.mean([np.log(ren[k]['linear_rgb']) for k in use], axis=0))
    rel /= (ren_mean*rel)@LUMA/(ren_mean@LUMA)
    current = np.array([float(v) for v in args.current_gain.split(',')])
    report = {'reference': args.reference, 'reference_box': box, 'render': args.render,
              'reference_pose': ref_pose, 'render_pose': ren_pose,
              'reference_patches': ref, 'render_patches': ren,
              'reference_mean': {'r_over_g': rg_ref, 'g_over_b': gb_ref, 'luminance': lum_ref},
              'render_mean': {'r_over_g': rg_ren, 'g_over_b': gb_ren, 'luminance': lum_ren},
              'chroma_error': {'r_over_g_pct': 100*(rg_ren/rg_ref-1), 'g_over_b_pct': 100*(gb_ren/gb_ref-1)},
              'relative_chroma_gain': rel.tolist(), 'suggested_albedo_gain': (current*rel).tolist(),
              'note': 'colour measurement aid only; not an identity or quality score'}
    text = json.dumps(report, indent=1)
    if args.output:
        Path(args.output).write_text(text+'\n')
    print(json.dumps({'reference_mean': report['reference_mean'], 'render_mean': report['render_mean'],
                      'chroma_error': report['chroma_error'], 'suggested_albedo_gain': report['suggested_albedo_gain']}))


if __name__ == '__main__':
    main()
