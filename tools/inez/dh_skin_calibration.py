"""Calibrate Inez's skin albedo for physically based rendering.

    python3 -I tools/inez/dh_skin_calibration.py \
        --out assets/characters/inez/textures/digital_human/skin_calibration.json

Why. The skin textures were colour-matched in pass 3 against Cycles renders
(AgX view transform, bright area-light studio, subsurface). As material
albedo they are too dark and too saturated (linear luminance ~0.115,
R/G ~2.1-2.2), so under neutral physically based lighting the face renders
at about half the brightness of the original images, and too red.

What. Two in-image facts from the original references, both independent of
exposure:
1. skin chroma: the R/G and G/B of cheek and forehead patches (MediaPipe
   landmarks, linear RGB, 15th-85th luminance percentile median), as in
   tools/inez/skin_tone_compare.py;
2. skin brightness relative to the grey knit in the same image (by default
   from the evenly lit turnaround face panel only; the portraits are lit by
   a key that falls off toward the knit and read 3.4-3.6 instead of 2.8): the ratio of
   skin luminance to the light-grey knit tone (two-tone split of
   low-saturation sweater pixels in a fixed box). The knit is a neutral
   reference that appears in every panel.
The target skin albedo is then: luminance = ratio x the knit's albedo in
Inez's own sweater texture; chroma = the originals' (geometric mean over
panels). The shader multiplies each skin texture by the per-channel gain
that moves its median skin texel onto that target. Spatial detail (freckles,
pigmentation, lip colour) is untouched: a constant gain per channel.

Limits, stated in the JSON: the ratio assumes cheek and chest receive
similar light in the originals (both face the camera and key light), and
SSS shifts rendered chroma slightly redder than albedo chroma; the result is
a calibrated starting point, verified afterwards on renders, not a
measurement of Inez's real skin.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from skin_tone_compare import LUMA, linear, measure  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
TEX = REPO/'assets/characters/inez/textures/master'
PANELS = [
    # name, image, face box, knit box
    ('turnaround_B_face', 'references/inez_turnaround.jpg', (855, 0, 1280, 714), (860, 480, 1275, 714)),
    ('portrait_A_left', 'references/inez_portraits.jpg', (0, 0, 640, 956), (40, 640, 600, 956)),
    ('portrait_A_right', 'references/inez_portraits.jpg', (640, 0, 1280, 956), (680, 640, 1260, 956)),
]
SKIN_TEXTURES = {'Inez_Head_Skin_PBR': 'inez_head_albedo_assetB.jpg',
                 'Inez_Skin_Freckles_Pores_Lips_PBR': 'inez_body_albedo_tone_matched.png'}
KNIT_TEXTURE = 'Inez_Sweater_FromAssetA_basecolor.jpg'


def knit_grey(pixels):
    """Median linear RGB of the lighter tone of low-saturation knit pixels."""
    sat = (pixels.max(1)-pixels.min(1))/np.maximum(pixels.max(1), 1e-6)
    grey = pixels[(sat < 0.25) & (pixels@LUMA > 0.005)]
    y = grey@LUMA
    t = np.median(y)
    for _ in range(20):
        lo, hi = np.median(y[y < t]), np.median(y[y >= t])
        t = (lo+hi)/2
    return np.median(grey[y >= t], 0), int((y >= t).sum())


def skin_texels(path):
    px = linear(np.asarray(Image.open(path).convert('RGB'), np.float64).reshape(-1, 3)/255)
    skin = px[(px[:, 0] > px[:, 1]) & (px[:, 1] > px[:, 2]) & (px@LUMA > 0.01)]
    y = skin@LUMA
    lo, hi = np.percentile(y, [25, 75])
    return np.median(skin[(y >= lo) & (y <= hi)], 0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    parser.add_argument('--luminance-panels', nargs='+', default=['turnaround_B_face'],
                        help='panels whose skin/knit ratio sets the albedo level (the evenly lit frontal panel by default; '
                             'the portraits are lit by a key that falls off down the frame, which inflates their ratio)')
    args = parser.parse_args()
    panels = []
    for name, image, face_box, knit_box in PANELS:
        patches, pose, _ = measure(str(REPO/image), face_box)
        use = [k for k in patches if patches[k]['pixels'] > 20]
        skin = np.exp(np.mean([np.log(patches[k]['linear_rgb']) for k in use], 0))
        img = linear(np.asarray(Image.open(REPO/image).convert('RGB'), np.float64)/255)
        x0, y0, x1, y1 = knit_box
        knit, knit_pixels = knit_grey(img[y0:y1, x0:x1].reshape(-1, 3))
        panels.append({'panel': name, 'pose_deg': pose, 'skin_patches': use, 'skin_linear_rgb': skin.round(5).tolist(),
                       'skin_luminance': float(skin@LUMA), 'skin_r_over_g': float(skin[0]/skin[1]), 'skin_g_over_b': float(skin[1]/skin[2]),
                       'knit_light_grey_linear_rgb': knit.round(5).tolist(), 'knit_luminance': float(knit@LUMA), 'knit_pixels': knit_pixels,
                       'skin_over_knit': float((skin@LUMA)/(knit@LUMA))})
    ratio = float(np.exp(np.mean([np.log(p['skin_over_knit']) for p in panels if p['panel'] in args.luminance_panels])))
    rg = float(np.exp(np.mean([np.log(p['skin_r_over_g']) for p in panels])))
    gb = float(np.exp(np.mean([np.log(p['skin_g_over_b']) for p in panels])))
    knit_albedo, _ = knit_grey(linear(np.asarray(Image.open(TEX/KNIT_TEXTURE).convert('RGB'), np.float64).reshape(-1, 3)/255))
    target_lum = ratio*float(knit_albedo@LUMA)
    g = target_lum/(LUMA[0]*rg+LUMA[1]+LUMA[2]/gb)
    target = np.array([rg*g, g, g/gb])
    materials = {}
    for material, texture in SKIN_TEXTURES.items():
        median = skin_texels(TEX/texture)
        gain = target/median
        materials[material] = {'texture': texture, 'median_skin_texel_linear_rgb': median.round(5).tolist(),
                               'median_luminance': float(median@LUMA), 'r_over_g': float(median[0]/median[1]), 'g_over_b': float(median[1]/median[2]),
                               'albedo_gain_linear_rgb': gain.round(4).tolist()}
    result = {
        'method': 'tools/inez/dh_skin_calibration.py (see docstring)',
        'panels': panels,
        'skin_over_knit_used': ratio, 'luminance_panels': args.luminance_panels, 'skin_over_knit_range': [min(p['skin_over_knit'] for p in panels), max(p['skin_over_knit'] for p in panels)],
        'skin_chroma_target': {'r_over_g': rg, 'g_over_b': gb},
        'knit_texture': KNIT_TEXTURE, 'knit_albedo_linear_rgb': knit_albedo.round(5).tolist(), 'knit_albedo_luminance': float(knit_albedo@LUMA),
        'target_skin_albedo_linear_rgb': target.round(5).tolist(), 'target_skin_albedo_luminance': target_lum,
        'materials': materials,
        'limits': ['Assumes cheek and chest receive similar light in the originals.',
                   'Subsurface scattering shifts rendered chroma slightly redder than albedo chroma.',
                   'A calibrated starting point, verified on renders; not a measurement of real skin.'],
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k: result[k] for k in ('skin_over_knit_used', 'luminance_panels', 'skin_over_knit_range', 'skin_chroma_target', 'knit_albedo_luminance',
                                              'target_skin_albedo_linear_rgb', 'target_skin_albedo_luminance')}, indent=1))
    for k, v in materials.items():
        print(k, v['albedo_gain_linear_rgb'], 'from median', v['median_skin_texel_linear_rgb'])


if __name__ == '__main__':
    main()
