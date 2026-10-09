"""Label every vertex of an aligned source GLB mesh by material region (no Blender).

    python3 -I tools/inez/source_regions.py --mesh SRC_A_FullBody.npz --glb source/asset_a/Inez.glb \
        --kind body --output SRC_A_regions.npz
    python3 -I tools/inez/source_regions.py --mesh SRC_B_HeadBust.npz --glb "source/asset_b/Inez Facial Model.glb" \
        --kind head --output SRC_B_regions.npz

Regions are read from the delivered base colour (sampled at each vertex's own
UV) with metric height and side priors from the aligned frame, then cleaned
by a nearest-neighbour majority vote (96 neighbours, about 1 cm on Asset A). Labels steer which source surface each
production part conforms to (sweater -> sweater, jeans -> jeans, ...) and
which part of Asset B becomes the hair shell. They are segmentation aids,
not artistic decisions.
"""
import argparse
import io
import json
import struct
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.spatial import cKDTree

Image.MAX_IMAGE_PIXELS = None
REGIONS = ['skin', 'hair', 'sweater', 'jeans', 'boots', 'eye', 'other']


def base_colour(glb):
    data = Path(glb).read_bytes()
    off, chunks = 12, {}
    while off < len(data):
        n, t = struct.unpack('<I4s', data[off:off+8])
        chunks[t] = data[off+8:off+8+n]
        off += 8+n
    g = json.loads(chunks[b'JSON'])
    binary = chunks[b'BIN\x00']
    tex = g['materials'][0]['pbrMetallicRoughness']['baseColorTexture']['index']
    view = g['bufferViews'][g['images'][g['textures'][tex]['source']]['bufferView']]
    blob = binary[view.get('byteOffset', 0):view.get('byteOffset', 0)+view['byteLength']]
    return np.asarray(Image.open(io.BytesIO(blob)).convert('RGB'), np.float32)/255


def sample(tex, uv):
    h, w = tex.shape[:2]
    # 5-tap average reduces single-texel noise (knit, stubble of hair strands).
    out = np.zeros((len(uv), 3), np.float32)
    for du, dv in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
        x = np.clip((uv[:, 0]*w).astype(int)+du, 0, w-1)
        y = np.clip(((1-uv[:, 1])*h).astype(int)+dv, 0, h-1)
        out += tex[y, x]
    return out/5


def smooth_labels(points, labels, neighbours=96, passes=2):
    tree = cKDTree(points)
    labels = labels.copy()
    for _ in range(passes):
        # Vote among each anchor's nearest neighbours (spacing-independent:
        # Asset B is ~8x denser than A in metric space), then copy to all points.
        idx = np.arange(0, len(points), 3)
        _, hood = tree.query(points[idx], k=neighbours)
        votes = np.array([np.bincount(labels[h], minlength=len(REGIONS)).argmax() for h in hood])
        _, near = cKDTree(points[idx]).query(points)
        labels = votes[near]
    return labels


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mesh', required=True)
    parser.add_argument('--glb', required=True)
    parser.add_argument('--kind', choices=('body', 'head'), required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    mesh = np.load(args.mesh)
    P, uv = mesh['vertices'].astype(np.float64), mesh['uv']
    c = sample(base_colour(args.glb), uv)
    L = c.mean(1)
    sat = c.max(1)-c.min(1)
    warm = c[:, 0]-c[:, 2]
    z = P[:, 2]
    labels = np.full(len(P), REGIONS.index('other'))
    warm_coloured = (warm > 0.05) & (sat > 0.06)
    # Skin is brighter and less chromatic than brown hair.
    skin_like = warm_coloured & (L > 0.36) & (sat/np.maximum(L, 1e-3) < 0.62)
    hair_like = warm_coloured & ~skin_like
    if args.kind == 'body':
        neutral = ~warm_coloured
        bluish = warm < -0.012
        labels[neutral & (z < 0.30)] = REGIONS.index('boots')
        labels[neutral & (z >= 0.30) & ~bluish & (z < 1.12)] = REGIONS.index('jeans')
        labels[neutral & bluish & (z >= 0.55)] = REGIONS.index('sweater')
        labels[neutral & ~bluish & (z >= 1.12)] = REGIONS.index('sweater')
        labels[skin_like] = REGIONS.index('skin')
        labels[hair_like & (z > 1.40)] = REGIONS.index('hair')
        labels[hair_like & (z <= 1.40)] = REGIONS.index('skin')
    else:
        # Asset B's skin is warm and saturated enough to overlap a fixed hair
        # rule, so the two colour classes are learnt from unambiguous samples:
        # skin around the nose/cheeks (front of the face at eye height minus
        # 3-6 cm) and hair on the crown and the hanging ponytail.
        N = mesh['normals']
        face_front = P[np.argmin(P[:, 1])]  # nose tip faces -Y
        skin_seed = (np.linalg.norm(P-(face_front+np.array([0, 0.02, 0.0])), axis=1) < 0.035) & (N[:, 1] < -0.5)
        top = P[:, 2].max()
        hair_seed = ((P[:, 2] > top-0.03) | ((P[:, 1] > 0.06) & (P[:, 2] > top-0.30))) & warm_coloured
        lab = np.log(np.maximum(c, 1e-3))

        def stats(sel):
            mu = lab[sel].mean(0)
            cov = np.cov(lab[sel].T)+np.eye(3)*1e-4
            return mu, np.linalg.inv(cov)
        (ms, Is), (mh, Ih) = stats(skin_seed), stats(hair_seed)
        ds = np.einsum('ij,jk,ik->i', lab-ms, Is, lab-ms)
        dh = np.einsum('ij,jk,ik->i', lab-mh, Ih, lab-mh)
        dark_blue = (warm < 0.0) & (L < 0.45)
        labels[dark_blue] = REGIONS.index('sweater')
        labels[warm_coloured & (ds < dh)] = REGIONS.index('skin')
        labels[warm_coloured & (ds >= dh)] = REGIONS.index('hair')
        white = (sat < 0.10) & (L > 0.55)
        labels[white] = REGIONS.index('eye')
    labels = smooth_labels(P, labels)
    counts = {name: int((labels == k).sum()) for k, name in enumerate(REGIONS)}
    np.savez_compressed(args.output, labels=labels.astype(np.int8), colours=c.astype(np.float16), names=np.array(REGIONS))
    print(json.dumps({'mesh': args.mesh, 'counts': counts}))


if __name__ == '__main__':
    main()
