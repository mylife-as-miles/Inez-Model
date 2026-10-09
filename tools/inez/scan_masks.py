"""Per-vertex masks for the Ten24 scan crop (what may and may not transfer to Inez).

    python3 -I tools/inez/scan_masks.py --scan-mesh scan_L4.npz --scan-landmarks scan_landmarks.json \
        --colour "Colour_8k.jpg" --output scan_masks.npz [--preview DIR]

hair     scalp/sideburn/nostril-dark regions from the publisher colour map
stubble  beard-shadow region (cool, low-warmth skin around jaw, chin, upper lip)
eyeball  scanned eye surface inside the scan's own eye contours (Inez keeps her eyes)
seam     scanned closed lip seam (Inez's lips part; the seam must not transfer)
brow     scanned brow hair band (Inez has her own brows)
face     inside the scan's own face outline (no ears, sideburns, scalp)
marks    donor-specific marks (a raised mole on the nasal bridge) excluded
under    the donor's lower-lid fold is softened (it reads as age)

The colour map is only measured here; no donor colour is written to any Inez
texture. Outputs `detail` (geometry may transfer) and `normal_strength`
(the publisher normal map may transfer: also excludes stubble and brows).
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scan_landmark_sets import FACE_OVAL, LEFT_EYE, LIPS_INNER, RIGHT_EYE

Image.MAX_IMAGE_PIXELS = None
FIELD = 2048
# Donor-specific surface marks (scan UV, radius m) never transferred to Inez.
DONOR_MARKS = [((0.7595, 0.2004), 0.003, 'raised mole on the nasal bridge')]
UNDER_EYE_FACTOR = 0.6  # soften the donor's lower-lid fold (adds age)


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scan-mesh', required=True)
    parser.add_argument('--scan-landmarks', required=True)
    parser.add_argument('--colour', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--preview')
    return parser.parse_args()


def gaussian(a, radius):
    return gaussian_filter(a.astype(np.float32), radius)


def colour_fields(path):
    rgb = np.asarray(Image.open(path).convert('RGB').resize((FIELD, FIELD), Image.BOX), np.float32)/255
    R, G, B = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    L = 0.2126*R+0.7152*G+0.0722*B
    warm = R-B
    hair = np.clip((0.40-L)/0.12, 0, 1)*np.clip((0.16-warm)/0.08+0.5, 0, 1)
    hair = gaussian(np.maximum(hair, np.clip((0.30-L)/0.08, 0, 1)), 1.0)
    stubble = np.clip((0.17-gaussian(warm, 2.0))/0.06, 0, 1)*(1-hair)
    return np.clip(hair, 0, 1), np.clip(gaussian(stubble, 1.5), 0, 1)


def sample(field, uv):
    h, w = field.shape
    x = np.clip(uv[:, 0]*(w-1), 0, w-1)
    y = np.clip((1-uv[:, 1])*(h-1), 0, h-1)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    x1, y1 = np.minimum(x0+1, w-1), np.minimum(y0+1, h-1)
    fx, fy = x-x0, y-y0
    return (field[y0, x0]*(1-fx)*(1-fy)+field[y0, x1]*fx*(1-fy)+field[y1, x0]*(1-fx)*fy+field[y1, x1]*fx*fy)


def inside(points, polygon):
    x, y = points[:, 0], points[:, 1]
    result = np.zeros(len(points), bool)
    px, py = polygon[:, 0], polygon[:, 1]
    for i in range(len(polygon)):
        j = i-1
        cross = ((py[i] > y) != (py[j] > y)) & (x < (px[j]-px[i])*(y-py[i])/(py[j]-py[i]+1e-12)+px[i])
        result ^= cross
    return result


def polyline_distance(points, line):
    best = np.full(len(points), np.inf)
    for a, b in zip(line[:-1], line[1:]):
        ab = b-a
        t = np.clip((points-a)@ab/max(ab@ab, 1e-12), 0, 1)
        best = np.minimum(best, np.linalg.norm(points-(a+t[:, None]*ab), axis=1))
    return best


def main():
    args = arguments()
    scan = np.load(args.scan_mesh)
    P, uv, N = scan['vertices'].astype(np.float64), scan['uv'], scan['normals']
    lm = json.loads(Path(args.scan_landmarks).read_text())
    L = {int(k): np.array(v['world']) for k, v in lm['landmarks'].items()}
    hair_field, stubble_field = colour_fields(args.colour)
    hair = sample(hair_field, uv)
    stubble = sample(stubble_field, uv)
    # The scanned hair edge is a raised ridge on the surface: keep ~5 mm of
    # skin around any hair out of the transfer.
    hair_pts = P[hair > 0.5]
    if len(hair_pts):
        d_hair, _ = cKDTree(hair_pts).query(P)
        hair = np.maximum(hair, np.clip(1-(d_hair-0.003)/0.003, 0, 1))
    # Eyeballs: inside each eye contour as seen in the frontal landmark render,
    # on the front surface near the contour depth.
    front = lm['views']['front']
    px = np.array(front['landmarks_px'])[:, :2]
    center, span, res = np.array(lm['center_world']), lm['span_m'], lm['resolution']
    proj = np.stack((((P[:, 0]-center[0])/span+0.5)*res, (0.5-(P[:, 2]-center[2])/span)*res), axis=1)
    eyeball = np.zeros(len(P), bool)
    for contour in (RIGHT_EYE, LEFT_EYE):
        depth = np.mean([L[i][1] for i in contour if i in L])
        eyeball |= inside(proj, px[contour]) & (np.abs(P[:, 1]-depth) < 0.015) & (N[:, 1] < 0)
    # Closed lip seam: within 1.2 mm of the inner-lip landmark loop.
    loop = np.array([L[i] for i in LIPS_INNER+[LIPS_INNER[0]] if i in L])
    seam = polyline_distance(P, loop) < 0.0012
    # Brow band: distance to each brow's mid-line (between its upper and
    # lower landmark rows), not to isolated landmark points.
    d_brow = np.full(len(P), np.inf)
    for upper, lower in (([70, 63, 105, 66, 107], [46, 53, 52, 65, 55]),
                         ([300, 293, 334, 296, 336], [276, 283, 282, 295, 285])):
        mid = np.array([(L[a]+L[b])/2 for a, b in zip(upper, lower) if a in L and b in L])
        d_brow = np.minimum(d_brow, polyline_distance(P, mid))
    brow = np.clip(1-(d_brow-0.004)/0.004, 0, 1)
    # Face region: inside the scan's own frontal face outline (MediaPipe
    # face oval), front surface only, softened over 10 mm (sideburn edges). Excludes ears,
    # sideburns and scalp by construction.
    oval = px[FACE_OVAL]
    inside_oval = inside(proj, oval)
    edge = np.full(len(P), np.inf)
    for a, b in zip(oval, np.roll(oval, -1, axis=0)):
        ab = b-a
        t = np.clip((proj-a)@ab/max(ab@ab, 1e-9), 0, 1)
        edge = np.minimum(edge, np.linalg.norm(proj-(a+t[:, None]*ab), axis=1))
    edge_m = edge*span/res
    face_depth = np.mean([L[i][1] for i in FACE_OVAL if i in L])
    front_surface = (N[:, 1] < 0.5) & (P[:, 1] < face_depth+0.05)
    face_region = np.where(inside_oval & front_surface, np.clip(edge_m/0.010, 0, 1), 0.0)
    # Temples and lateral cheeks carry the donor's sideburns (pits up to
    # 1.7 mm survived the outline ramp) and no anatomy worth transferring:
    # full weight to 10 mm beyond the outer eye corners, zero by 18 mm.
    mid_x = (L[133][0]+L[362][0])/2
    corner = (abs(L[33][0]-mid_x)+abs(L[263][0]-mid_x))/2
    beyond = np.abs(P[:, 0]-mid_x)-corner
    face_region *= np.clip(1-(beyond-0.010)/0.008, 0, 1)
    marks = np.zeros(len(P))
    for (mu, mv), radius, _ in DONOR_MARKS:
        near_uv = np.linalg.norm(uv-np.array([mu, mv]), axis=1) < 12/8192
        if near_uv.any():
            centre = P[near_uv].mean(0)
            d = np.linalg.norm(P-centre, axis=1)
            marks = np.maximum(marks, np.clip(1-(d-radius)/0.002, 0, 1))
    under = np.zeros(len(P))
    for lower in ([33, 7, 163, 144, 145, 153, 154, 155, 133], [263, 249, 390, 373, 374, 380, 381, 382, 362]):
        line = np.array([L[i] for i in lower if i in L])
        d = polyline_distance(P, line)
        below = P[:, 2] < line[:, 2].max()
        under = np.maximum(under, np.where(below, np.clip(1-np.abs(d-0.008)/0.006, 0, 1), 0))
    detail = (1-hair)*(~eyeball)*(~seam)*face_region*(1-marks)*(1-0.5*stubble)*(1-(1-UNDER_EYE_FACTOR)*under)
    normal_strength = detail*(1-stubble)*(1-0.5*brow)
    np.savez_compressed(args.output, hair=hair.astype(np.float32), stubble=stubble.astype(np.float32),
                        face_region=face_region.astype(np.float32), donor_marks=marks.astype(np.float32),
                        under_eye=under.astype(np.float32),
                        eyeball=eyeball, seam=seam, brow=brow.astype(np.float32),
                        detail=detail.astype(np.float32), normal_strength=normal_strength.astype(np.float32))
    face = np.linalg.norm(P-L[1], axis=1) < 0.09
    print(json.dumps({'vertices': len(P), 'face_vertices': int(face.sum()),
                      'face_fraction': {k: float(np.mean(v[face] > 0.5)) for k, v in
                                        (('hair', hair), ('stubble', stubble), ('eyeball', eyeball), ('seam', seam), ('brow', brow),
                                         ('face_region', face_region), ('donor_marks', marks), ('under_eye', under))},
                      'donor_marks': [m[2] for m in DONOR_MARKS]}))
    if args.preview:
        out = Path(args.preview)
        out.mkdir(parents=True, exist_ok=True)
        Image.fromarray((np.clip(np.stack((hair_field, stubble_field, np.zeros_like(hair_field)), -1), 0, 1)*255).astype(np.uint8)).save(out/'scan_colour_masks_uv.png')


if __name__ == '__main__':
    main()
