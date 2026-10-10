"""Paint the old hair out of Inez's head albedo where the new strand hair leaves skin bare.

    python3 -I tools/inez/hair/clean_head_albedo.py --glb STRANDS.glb --output OUT.glb \
        --report REPORT.json [--debug-dir DIR]

The recovery head texture (lod_2048_inez_head_albedo_assetB_restored_v06)
has the previous haircut painted into it, including a fringe that reaches
the eyebrows and covers the temples. The old hair mesh hid it; the strand hair
is pulled back (as in the references), so the painted fringe showed through as
a sheer veil of hair over her forehead.

1. The head primitive is rasterised in UV space: every texel gets its rest
   position on the head.
2. Coverage: distance from that position to the nearest strand segment lying
   on the scalp (within 6 mm of the skin), and the opacity of the scalp patch.
   Texels within 3 mm of strands, or under the opaque patch, keep the painted
   hair (it darkens the roots); the repaint weight rises to 1 at 8 mm.
3. Painted hair is detected by colour (CIELAB: hair a* < ~8 and darker than
   skin), closed and dilated so strand highlights go too, then feathered.
4. Brows and eyes are protected by fixed ellipses measured on this texture
   (the tool checks the image name and size), and only the main head island is
   touched (not the ear islands).
5. Fill: the skin colour field is a multi-scale normalised convolution of the
   upper face's bare skin (coarse scales only, away from the painted hair whose
   shadow is baked around it) and, below the eyes, of the cheek skin next to it; plus fine grain with
   the forehead skin's measured high-pass amplitude. The bare forehead is
   repainted whole, so thin painted strands and that baked shadow go too.
6. The new image is appended as a JPEG (quality 92) and the head material's
   base colour texture is pointed at it; nothing else changes and the input's
   binary chunk stays a byte-exact prefix.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy.spatial import cKDTree

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import v06_identity_normals_glb as glbmod  # noqa: E402
glbmod.NC['MAT4'] = 16; glbmod.NC['VEC2'] = 2
from v06_identity_normals_glb import GLB  # noqa: E402
from fit_hair_cards import Surface, node_world, rendered_mesh, weld  # noqa: E402
from inject_hair_glb import append_bytes  # noqa: E402

IMAGE_NAME = 'lod_2048_inez_head_albedo_assetB_restored_v06'
IMAGE_SIZE = (2048, 1024)
# (centre x, centre y, semi-axis x, semi-axis y) in texels of IMAGE_NAME
PROTECT = {'brow_left': (818, 496, 52, 13), 'brow_right': (982, 492, 64, 13),
           'eye_left': (788, 530, 50, 28), 'eye_right': (995, 530, 54, 28)}
MAIN_ISLAND_MAX_X = 1750


def rasterise(UV, P, T, W, H):
    pos = np.zeros((H, W, 3)); valid = np.zeros((H, W), bool)
    px = UV * [W, H] - .5
    for tri in T:
        a, b, c = px[tri]
        x0, x1 = int(np.floor(min(a[0], b[0], c[0]))), int(np.ceil(max(a[0], b[0], c[0])))
        y0, y1 = int(np.floor(min(a[1], b[1], c[1]))), int(np.ceil(max(a[1], b[1], c[1])))
        x0, y0 = max(x0, 0), max(y0, 0); x1, y1 = min(x1, W - 1), min(y1, H - 1)
        if x1 < x0 or y1 < y0:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(d) < 1e-12:
            continue
        l0 = ((b[1] - c[1]) * (gx - c[0]) + (c[0] - b[0]) * (gy - c[1])) / d
        l1 = ((c[1] - a[1]) * (gx - c[0]) + (a[0] - c[0]) * (gy - c[1])) / d
        l2 = 1 - l0 - l1
        m = (l0 >= -1e-3) & (l1 >= -1e-3) & (l2 >= -1e-3)
        if not m.any():
            continue
        q = l0[m, None] * P[tri[0]] + l1[m, None] * P[tri[1]] + l2[m, None] * P[tri[2]]
        pos[gy[m], gx[m]] = q; valid[gy[m], gx[m]] = True
    return pos, valid


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--glb', required=True, help='strand-hair GLB from build_strand_hair.py')
    ap.add_argument('--output', required=True)
    ap.add_argument('--report', required=True)
    ap.add_argument('--debug-dir')
    args = ap.parse_args()
    if Path(args.output).exists():
        raise SystemExit('refusing to overwrite ' + args.output)
    glb = GLB(args.glb); j = glb.json; W4 = node_world(j); prefix = len(glb.bin)
    names = {n.get('name'): i for i, n in enumerate(j['nodes'])}
    body_node = names['Inez_ContinuousHumanMesh_UNAPPROVED']
    mesh = j['meshes'][j['nodes'][body_node]['mesh']]
    mat = next(i for i, m in enumerate(j['materials']) if m['name'] == 'Inez_Head_Skin_PBR')
    prim = next(p for p in mesh['primitives'] if p['material'] == mat)
    tex = j['materials'][mat]['pbrMetallicRoughness']['baseColorTexture']['index']
    img_index = j['textures'][tex]['source']; img = j['images'][img_index]
    if img.get('name') != IMAGE_NAME:
        raise SystemExit('unexpected head albedo ' + str(img.get('name')))
    bv = j['bufferViews'][img['bufferView']]
    src = Image.open(io.BytesIO(bytes(glb.bin[bv.get('byteOffset', 0):bv.get('byteOffset', 0) + bv['byteLength']]))).convert('RGB')
    if src.size != IMAGE_SIZE:
        raise SystemExit('unexpected head albedo size')
    Wt, Ht = src.size
    rgb = np.asarray(src).astype(np.float32) / 255

    # ---- 1. rest position per texel (same morph weights / node transform as the hair build)
    P = glb.accessor(prim['attributes']['POSITION'])
    weights = j['nodes'][body_node].get('weights', mesh.get('weights', []))
    for w, tgt in zip(weights, prim.get('targets', [])):
        if w and 'POSITION' in tgt:
            P = P + w * glb.accessor(tgt['POSITION'])
    M = W4[body_node]; P = P @ M[:3, :3].T + M[:3, 3]
    UV = glb.accessor(prim['attributes']['TEXCOORD_0'])
    T = glb.accessor(prim['indices']).astype(np.int64).reshape(-1, 3)
    pos, valid = rasterise(UV, P, T, Wt, Ht)

    # ---- 2. coverage: strands lying on the scalp (segments, densified: the
    # scalp part of each strand is decimated) and the opaque part of the scalp patch
    body = Surface(*weld(*rendered_mesh(glb, body_node, W4)))
    sm = j['meshes'][j['nodes'][names['Inez_Hair_Strands']]['mesh']]['primitives'][0]
    SP = glb.accessor(sm['attributes']['POSITION']); SE = glb.accessor(sm['indices']).astype(np.int64).reshape(-1, 2)
    near = np.abs(body.signed(SP)[0]) < .006
    SE = SE[near[SE[:, 0]] & near[SE[:, 1]]]
    seg = np.linalg.norm(SP[SE[:, 1]] - SP[SE[:, 0]], axis=1); nsub = np.ceil(seg / .0015).astype(int)
    rep = np.repeat(np.arange(len(SE)), nsub); t = (np.arange(nsub.sum()) - np.repeat(np.cumsum(nsub) - nsub, nsub)) / np.repeat(nsub, nsub)
    dense = SP[SE[rep, 0]] * (1 - t[:, None]) + SP[SE[rep, 1]] * t[:, None]
    d = np.full((Ht, Wt), 1.0); d[valid] = cKDTree(dense).query(pos[valid])[0]
    cm = j['meshes'][j['nodes'][names['Inez_Hair_Scalp']]['mesh']]['primitives'][0]
    CP = glb.accessor(cm['attributes']['POSITION']); CA = glb.accessor(cm['attributes']['COLOR_0'])[:, 3]
    patch = np.zeros((Ht, Wt)); dc, ic = cKDTree(CP).query(pos[valid]); patch[valid] = np.where(dc < .005, CA[ic], 0)
    uncovered = (smoothstep(.003, .008, d) * (1 - smoothstep(.3, .7, patch))).astype(np.float32)

    # ---- 3. painted hair by colour
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)   # float input: L 0-100, a/b signed
    L, A = lab[..., 0], lab[..., 1]
    hair = (A < 9.5) & (L < 58) | (L < 40)
    hair = cv2.morphologyEx(hair.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    hair = cv2.dilate(hair, np.ones((5, 5), np.uint8)).astype(np.float32)
    hair = cv2.GaussianBlur(hair, (0, 0), 2.0)

    # ---- 4. protected zones and region
    yy, xx = np.mgrid[0:Ht, 0:Wt].astype(np.float32)
    protect = np.zeros((Ht, Wt), np.float32)
    for cx, cy, rx, ry in PROTECT.values():
        r = np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)
        protect = np.maximum(protect, 1 - smoothstep(1.0, 1.25, r))
    region = valid & (xx < MAIN_ISLAND_MAX_X)
    region = cv2.dilate(region.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)   # UV seam gutter
    # leave the central face (nose, nostrils, mouth) alone: below the eyes only
    # the sides of the face, in front of the ears, can carry painted hair
    central = (np.abs(pos[..., 0]) < .035) & (pos[..., 2] > .03)
    y_ok = np.where(central, smoothstep(1.615, 1.63, pos[..., 1]), smoothstep(1.50, 1.52, pos[..., 1])).astype(np.float32)
    y_ok = np.where(valid, y_ok, cv2.dilate(y_ok, np.ones((3, 3), np.uint8)))
    unc = np.where(valid, uncovered, cv2.dilate(uncovered, np.ones((3, 3), np.uint8)))
    w = hair * unc * (1 - protect) * region * y_ok
    w = np.clip(w, 0, 1).astype(np.float32)

    # ---- 5. fill: push-pull (multi-scale normalised convolution) of the bare
    # skin above the eyes, so the fill takes the forehead/temple tone, not the
    # pinker freckled cheeks; plus fine grain matched to that skin
    def push_pull(src, sigmas):
        # coarsest estimate everywhere, then each finer scale blended in by its
        # own support (soft, so no edge where one scale takes over)
        fill = None
        for sigma in sorted(sigmas, reverse=True):
            num = cv2.GaussianBlur(rgb * src[..., None], (0, 0), sigma); den = cv2.GaussianBlur(src, (0, 0), sigma)
            est = num / np.maximum(den, 1e-6)[..., None]
            if fill is None:
                fill = np.where(den[..., None] > 1e-3, est, rgb[src > 0].mean(0)); continue
            a = smoothstep(.05, .35, den)[..., None]
            fill = est * a + fill * (1 - a)
        return fill
    base = valid & ~(hair > .05) & (protect < .5)
    # above the eyes: a smooth, coarse field from the skin of the upper face
    # (eroded away from painted hair, whose shadow is baked around it), so the
    # forehead matches the face below it; below: the cheek skin next to it
    skin = cv2.erode((base & (L > 45) & (pos[..., 1] > 1.60)).astype(np.uint8), np.ones((13, 13), np.uint8)).astype(np.float32)
    up = smoothstep(1.615, 1.635, pos[..., 1])[..., None]
    fill = push_pull(skin, (40, 100)) * up + push_pull((base & (L > 45)).astype(np.float32), (6, 16, 40, 100)) * (1 - up)
    # the bare forehead is repainted whole (thin painted strands and the baked
    # shadow of the old fringe go too), not only where hair is detected
    forehead = valid & (pos[..., 2] > .06) & (np.abs(pos[..., 0]) < .065)
    forehead = smoothstep(1.645, 1.658, pos[..., 1]) * forehead
    # inside the brow ellipses only the brow hairs themselves are kept
    w = np.clip(np.maximum(w, forehead * unc * (1 - protect * hair)), 0, 1).astype(np.float32)
    hp = (rgb - cv2.GaussianBlur(rgb, (0, 0), 4))[skin > 0]
    grain_sd = 1.4826 * np.median(np.abs(hp - np.median(hp, 0)), 0)          # robust per-channel std
    noise = cv2.GaussianBlur(np.random.default_rng(12).standard_normal((Ht, Wt)).astype(np.float32), (0, 0), 1.0)
    noise /= noise.std()
    out = rgb * (1 - w[..., None]) + np.clip(fill + noise[..., None] * grain_sd, 0, 1) * w[..., None]
    out8 = (np.clip(out, 0, 1) * 255 + .5).astype(np.uint8)
    buf = io.BytesIO(); Image.fromarray(out8).save(buf, 'JPEG', quality=92, subsampling=0); data = buf.getvalue()

    # ---- 6. GLB: new image + texture, head material points at it
    view = append_bytes(glb, data)
    j['images'].append({'name': IMAGE_NAME + '_hairline_clean_r12', 'mimeType': 'image/jpeg', 'bufferView': view})
    j['textures'].append({'sampler': j['textures'][tex].get('sampler', 0), 'source': len(j['images']) - 1})
    j['materials'][mat]['pbrMetallicRoughness']['baseColorTexture'] = {**j['materials'][mat]['pbrMetallicRoughness']['baseColorTexture'], 'index': len(j['textures']) - 1}
    j['materials'][mat].setdefault('extras', {})['head_albedo_hairline_clean'] = {'tool': 'tools/inez/hair/clean_head_albedo.py', 'previous_image': IMAGE_NAME}
    glb.write(args.output)
    assert GLB(args.output).bin[:prefix] == glb.bin[:prefix]
    changed = w > .02
    report = {'tool': 'tools/inez/hair/clean_head_albedo.py', 'input_sha256': hashlib.sha256(Path(args.glb).read_bytes()).hexdigest(),
              'image': IMAGE_NAME, 'texels_valid': int(valid.sum()), 'texels_repainted': int(changed.sum()),
              'texels_fully_repainted': int((w > .98).sum()), 'mean_abs_change': float(np.abs(out - rgb)[changed].mean()) if changed.any() else 0.0,
              'protected_ellipses_px': PROTECT, 'jpeg_bytes': len(data), 'output_bytes': Path(args.output).stat().st_size}
    Path(args.report).write_text(json.dumps(report, indent=1) + '\n')
    print(json.dumps(report, indent=1))
    if args.debug_dir:
        dd = Path(args.debug_dir); dd.mkdir(parents=True, exist_ok=True)
        Image.fromarray(out8).save(dd / 'albedo_clean.png')
        dbg = (rgb * .5 * 255).astype(np.uint8); dbg[..., 0] = np.maximum(dbg[..., 0], (w * 255).astype(np.uint8)); dbg[..., 2] = np.maximum(dbg[..., 2], (protect * 200).astype(np.uint8))
        Image.fromarray(dbg).save(dd / 'repaint_weight.png')
        Image.fromarray((uncovered * 255).astype(np.uint8)).save(dd / 'uncovered.png')


if __name__ == '__main__':
    main()
