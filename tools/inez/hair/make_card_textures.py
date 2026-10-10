"""Build the runtime base-colour+coverage texture for the Ponytail MessyWavy cards.

    python3 -I tools/inez/hair/make_card_textures.py --package DIR --reference-hair PNG --out PNG --report JSON

The package maps are only read:
  fiber_Attribue.png  R = fine strand coverage, G/B = per-strand random values
  fiber_Tangent.tga   RGB = strand tangent, A = position along the strand
Colour is not invented: the medium-brown target is measured from Inez's current
restored hair albedo (the colour the user approved), in linear light. Output RGB
is that colour modulated by the package's per-strand values; alpha is the
package coverage. Root darkening is applied per vertex (COLOR_0), not here.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None


def to_linear(c):
    c = c / 255.0
    return np.where(c <= .04045, c / 12.92, ((c + .055) / 1.055) ** 2.4)


def to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= .0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - .055) * 255


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--package', required=True)
    ap.add_argument('--reference-hair', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--report', required=True)
    ap.add_argument('--size', type=int, default=4096)
    ap.add_argument('--coverage-gain', type=float, default=2.2)
    ap.add_argument('--dark-q', type=float, default=.5, help='quantile of the measured hair tones used for the darkest strands')
    ap.add_argument('--light-q', type=float, default=.95)
    args = ap.parse_args()
    pkg = Path(args.package)
    att = np.asarray(Image.open(pkg / 'fiber_Attribue.png').convert('RGBA')).astype(np.float32)
    tan = np.asarray(Image.open(pkg / 'fiber_Tangent.tga').convert('RGBA')).astype(np.float32)

    ref = np.asarray(Image.open(args.reference_hair).convert('RGB')).astype(np.float32)
    lin = to_linear(ref).reshape(-1, 3)
    lum = lin @ [.2126, .7152, .0722]
    hair = lin[(lum > np.quantile(lum, .15)) & (lum < np.quantile(lum, .98))]
    mid = np.median(hair, axis=0)
    light = np.quantile(hair, args.light_q, axis=0)
    dark = np.quantile(hair, args.dark_q, axis=0)

    seed_g, seed_b = att[..., 1] / 255, att[..., 2] / 255
    coverage = att[..., 0] / 255
    along = tan[..., 3] / 255
    # per-strand value in [0,1] -> blend between measured dark and light hair tones
    v = np.clip(.5 * seed_g + .5 * seed_b, 0, 1)
    colour = dark[None, None] + (light - dark)[None, None] * v[..., None]
    # subtle lightening toward the strand end (sun-faded tips), from the package's along-strand value
    colour *= (1 + .15 * along)[..., None]
    rgb = to_srgb(colour)
    alpha = np.clip(coverage * args.coverage_gain, 0, 1) * 255
    out = np.dstack([rgb, alpha]).astype(np.uint8)
    img = Image.fromarray(out, 'RGBA')
    if args.size != img.width:
        img = img.resize((args.size, args.size), Image.LANCZOS)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    img.save(args.out, optimize=True)
    report = {'tool': 'tools/inez/hair/make_card_textures.py', 'output': str(args.out), 'size': args.size,
              'reference_hair': str(args.reference_hair), 'measured_linear': {'dark': dark.tolist(), 'median': mid.tolist(), 'light': light.tolist()}, 'quantiles': [args.dark_q, args.light_q],
              'coverage_gain': args.coverage_gain, 'bytes': Path(args.out).stat().st_size,
              'coverage_mean': float(alpha.mean() / 255), 'artistic_approval': False}
    Path(args.report).write_text(json.dumps(report, indent=1) + '\n')
    print(json.dumps(report, indent=1))


if __name__ == '__main__':
    main()
