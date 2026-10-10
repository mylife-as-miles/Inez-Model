"""Garment luminance and stripe-colour ratios, original turnaround vs render.

    python3 -I tools/inez/garment_ratios.py \
        --front assets/characters/inez/renders/final_v05/body_front.png \
        --back assets/characters/inez/renders/final_v05/body_back.png

Fixed pixel boxes cover the sweater torso (below the ponytail on the back) and
the jeans thighs: in the turnaround's front and back panels, and in the
1000x1000 body renders from final_renders.py. The knit splits into its stripe
and grey tones by an iterated two-means threshold on linear luminance; each
tone's median linear RGB is reported. The ratios are colour measurements
for the identity spec's garment gate, not a likeness score.
"""
import argparse
import json

import numpy as np
from PIL import Image

LUMA = np.array([0.2126, 0.7152, 0.0722])
TURNAROUND = 'references/inez_turnaround.jpg'
BOXES = {
    'original_front': (TURNAROUND, (160, 150, 265, 265), (160, 330, 260, 520)),
    'original_back': (TURNAROUND, (560, 190, 720, 285), (585, 330, 690, 520)),
    'render_front': (None, (430, 215, 570, 370), (420, 470, 580, 760)),
    'render_back': (None, (430, 280, 570, 380), (420, 560, 580, 760)),
}


def linear(path, box):
    image = np.asarray(Image.open(path).convert('RGB')).astype(float)/255.0
    x0, y0, x1, y1 = box
    rgb = image[y0:y1, x0:x1].reshape(-1, 3)
    return np.where(rgb <= 0.04045, rgb/12.92, ((rgb+0.055)/1.055)**2.4)


def two_tone(pixels):
    y = pixels@LUMA
    low, high = np.percentile(y, [30, 70])
    for _ in range(20):
        threshold = (low+high)/2
        low, high = np.median(y[y < threshold]), np.median(y[y >= threshold])
    threshold = (low+high)/2
    return np.median(pixels[y < threshold], 0), np.median(pixels[y >= threshold], 0)


def measure(path, sweater, jeans):
    stripe, grey = two_tone(linear(path, sweater))
    denim = np.median(linear(path, jeans), 0)
    return {'stripe_over_grey': float(stripe@LUMA/(grey@LUMA)), 'jeans_over_grey': float(denim@LUMA/(grey@LUMA)),
            'stripe_g_over_b': float(stripe[1]/stripe[2]), 'grey_r_over_g': float(grey[0]/grey[1])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--front', required=True)
    parser.add_argument('--back', required=True)
    args = parser.parse_args()
    paths = {'render_front': args.front, 'render_back': args.back}
    result = {name: measure(path or paths[name], sweater, jeans) for name, (path, sweater, jeans) in BOXES.items()}
    for side in ('front', 'back'):
        original, render = result['original_'+side], result['render_'+side]
        result['delta_'+side] = {k: render[k]/original[k]-1 for k in original}
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
