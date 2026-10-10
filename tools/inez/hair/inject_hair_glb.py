"""Replace Inez's hair in a GLB with fitted hair cards (append-only).

    python3 -I tools/inez/hair/inject_hair_glb.py --input BASE.glb --fit FIT.npz \
        --texture HAIR_RGBA.png --output OUT.glb --report REPORT.json

The base GLB's binary chunk stays a byte-exact prefix; the new hair, its scalp
cap, material and texture are appended. The old hair node is detached from the
scene (its data stay in the file for rollback and comparison); the skeleton,
the 17 clips, morph targets and every other mesh are untouched. The hair is
skinned to the existing skin with the existing head and hair.01-04 joints.

Runtime data for the per-card simulation travel as glTF custom attributes:
  _HAIR_CARD  card index (float, constant per card)
  _HAIR_S     root (0) to tip (1) position along the card
  _HAIR_FREE  0 where the card lies on the scalp (pinned), 1 where it hangs free
COLOR_0 carries a root-to-tip shade (darker roots) and a small per-card tint.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from v06_identity_normals_glb import GLB  # noqa: E402


def append_bytes(glb, data, target=None):
    while len(glb.bin) % 4:
        glb.bin.append(0)
    off = len(glb.bin); glb.bin.extend(data)
    bv = {'buffer': 0, 'byteOffset': off, 'byteLength': len(data)}
    if target:
        bv['target'] = target
    glb.json['bufferViews'].append(bv)
    return len(glb.json['bufferViews']) - 1


def accessor(glb, array, kind, ctype, target=34962, minmax=False, normalized=False):
    array = np.ascontiguousarray(array)
    bv = append_bytes(glb, array.tobytes(), target)
    a = {'bufferView': bv, 'componentType': ctype, 'count': int(array.shape[0]), 'type': kind}
    if normalized:
        a['normalized'] = True
    if minmax:
        flat = array.reshape(array.shape[0], -1)
        a['min'] = flat.min(0).astype(float).tolist(); a['max'] = flat.max(0).astype(float).tolist()
    glb.json['accessors'].append(a)
    return len(glb.json['accessors']) - 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', required=True)
    ap.add_argument('--fit', required=True)
    ap.add_argument('--texture', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--report', required=True)
    ap.add_argument('--old-hair-node', default='Inez_Hair_lod')
    ap.add_argument('--alpha-cutoff', type=float, default=.3)
    ap.add_argument('--roughness', type=float, default=.42)
    ap.add_argument('--root-shade', type=float, default=.7)
    ap.add_argument('--root-length', type=float, default=.06, help='fraction of each card (from the root) that is darkened')
    ap.add_argument('--scalp-cap', action='store_true', help='add the inset scalp cap under the cards (hides the glossy painted crown)')
    ap.add_argument('--scalp-color', type=float, nargs=3, default=[.0115, .0068, .0042], help='linear RGB of the scalp cap')
    args = ap.parse_args()
    if Path(args.output).exists():
        raise SystemExit('refusing to overwrite ' + args.output)
    src_bytes = Path(args.input).read_bytes()
    glb = GLB(args.input); j = glb.json
    prefix_len = len(glb.bin); prefix_hash = hashlib.sha256(bytes(glb.bin)).hexdigest()
    n_acc, n_nodes = len(j['accessors']), len(j['nodes'])
    fit = dict(np.load(args.fit))

    # ---- texture + materials
    png = Path(args.texture).read_bytes()
    j.setdefault('images', []).append({'name': 'Inez_Hair_MessyWavy_cards_basecolor_r01', 'mimeType': 'image/png',
                                       'bufferView': append_bytes(glb, png)})
    j.setdefault('samplers', []).append({'magFilter': 9729, 'minFilter': 9987, 'wrapS': 33071, 'wrapT': 33071})
    j.setdefault('textures', []).append({'sampler': len(j['samplers']) - 1, 'source': len(j['images']) - 1})
    tex = len(j['textures']) - 1
    j['materials'].append({
        'name': 'Inez_Hair_MessyWavy_Cards_r01', 'doubleSided': True, 'alphaMode': 'MASK', 'alphaCutoff': args.alpha_cutoff,
        'pbrMetallicRoughness': {'baseColorTexture': {'index': tex}, 'metallicFactor': 0, 'roughnessFactor': args.roughness},
        'extensions': {'KHR_materials_specular': {'specularFactor': .6, 'specularColorFactor': [1.0, .78, .58]}},
        'extras': {'source': 'WhiteCap Ponytail MessyWavy (Fab), licensed by the repository owner; see hair/qa/intake_v01.json'}})
    hair_mat = len(j['materials']) - 1
    dark = list(args.scalp_color)  # linear root tone of the hair, for the scalp under the cards
    if args.scalp_cap:
        j['materials'].append({'name': 'Inez_Hair_MessyWavy_Scalp_r01', 'alphaMode': 'BLEND',
                               'pbrMetallicRoughness': {'baseColorFactor': [*dark, 1], 'metallicFactor': 0, 'roughnessFactor': .9}})
        scalp_mat = len(j['materials']) - 1

    # ---- vertex data
    P = fit['position'].astype(np.float32); N = fit['normal'].astype(np.float32)
    s = fit['s'].astype(np.float32); card = fit['card'].astype(np.float32)
    rng = np.random.default_rng(7)
    tint = rng.uniform(.86, 1.0, int(card.max()) + 1)[card.astype(int)]  # COLOR_0 must stay within 0..1
    shade = (args.root_shade + (1 - args.root_shade) * np.clip(s / args.root_length, 0, 1)) * tint
    color = np.stack([shade, shade, shade, np.ones_like(shade)], 1).astype(np.float32)
    attrs = {
        'POSITION': accessor(glb, P, 'VEC3', 5126, minmax=True),
        'NORMAL': accessor(glb, N, 'VEC3', 5126),
        'TEXCOORD_0': accessor(glb, fit['uv'].astype(np.float32), 'VEC2', 5126),
        'COLOR_0': accessor(glb, color, 'VEC4', 5126),
        'JOINTS_0': accessor(glb, np.where(fit['weights'] > 0, fit['joints'], 0).astype(np.uint16), 'VEC4', 5123),
        'WEIGHTS_0': accessor(glb, fit['weights'].astype(np.float32), 'VEC4', 5126),
        '_HAIR_CARD': accessor(glb, card[:, None], 'SCALAR', 5126),
        '_HAIR_S': accessor(glb, s[:, None], 'SCALAR', 5126),
        '_HAIR_FREE': accessor(glb, fit['free'].astype(np.float32)[:, None], 'SCALAR', 5126),
    }
    idx = accessor(glb, fit['triangles'].astype(np.uint32).reshape(-1, 1), 'SCALAR', 5125, target=34963)
    j['meshes'].append({'name': 'Inez_Hair_MessyWavy_Cards_LOD0', 'primitives': [{'attributes': attrs, 'indices': idx, 'material': hair_mat, 'mode': 4}]})
    hair_mesh = len(j['meshes']) - 1

    CP = fit['cap_position'].astype(np.float32)
    cap_mesh = None
    if args.scalp_cap:
        head_joint = fit['joints'][0, 0]
        cap_attrs = {
            'POSITION': accessor(glb, CP, 'VEC3', 5126, minmax=True),
            'NORMAL': accessor(glb, fit['cap_normal'].astype(np.float32), 'VEC3', 5126),
            'TEXCOORD_0': accessor(glb, fit['cap_uv'].astype(np.float32), 'VEC2', 5126),
            'COLOR_0': accessor(glb, np.c_[np.ones((len(CP), 3)), fit['cap_alpha']].astype(np.float32), 'VEC4', 5126),
            'JOINTS_0': accessor(glb, np.tile(np.array([[head_joint, 0, 0, 0]], np.uint16), (len(CP), 1)), 'VEC4', 5123),
            'WEIGHTS_0': accessor(glb, np.tile(np.array([[1, 0, 0, 0]], np.float32), (len(CP), 1)), 'VEC4', 5126),
        }
        cap_idx = accessor(glb, fit['cap_triangles'].astype(np.uint32).reshape(-1, 1), 'SCALAR', 5125, target=34963)
        j['meshes'].append({'name': 'Inez_Hair_MessyWavy_Scalp', 'primitives': [{'attributes': cap_attrs, 'indices': cap_idx, 'material': scalp_mat, 'mode': 4}]})
        cap_mesh = len(j['meshes']) - 1

    # ---- nodes: attach under the armature node that owns the old hair, detach the old hair
    old = next(i for i, n in enumerate(j['nodes']) if n.get('name') == args.old_hair_node)
    parent = next(i for i, n in enumerate(j['nodes']) if old in n.get('children', []))
    extras = {'source': 'WhiteCap Ponytail MessyWavy hair cards LOD0 (Fab), supplied and licensed by the repository owner',
              'fit_tool': 'tools/inez/hair/fit_hair_cards.py', 'simulation': 'per-card guides from _HAIR_CARD/_HAIR_S; see viewer/src/hair/card-simulation.js',
              'artistic_approval': False}
    j['nodes'].append({'name': 'Inez_Hair_MessyWavy_Cards', 'mesh': hair_mesh, 'skin': 0, 'extras': extras})
    kids = j['nodes'][parent]['children']
    kids.remove(old)
    kids.append(len(j['nodes']) - 1)
    if cap_mesh is not None:
        j['nodes'].append({'name': 'Inez_Hair_MessyWavy_Scalp', 'mesh': cap_mesh, 'skin': 0})
        kids.append(len(j['nodes']) - 1)
    j['nodes'][old].setdefault('extras', {})['detached_by'] = 'inject_hair_glb.py (rollback: input GLB)'

    glb.write(args.output)
    out = GLB(args.output)
    assert bytes(out.bin[:prefix_len]) == bytes(glb.bin[:prefix_len]) and hashlib.sha256(bytes(out.bin[:prefix_len])).hexdigest() == prefix_hash
    report = {'tool': 'tools/inez/hair/inject_hair_glb.py', 'input': args.input, 'input_sha256': hashlib.sha256(src_bytes).hexdigest(),
              'output': args.output, 'output_sha256': hashlib.sha256(Path(args.output).read_bytes()).hexdigest(), 'output_bytes': Path(args.output).stat().st_size,
              'binary_prefix_preserved_bytes': prefix_len, 'original_accessors_unchanged': n_acc, 'original_nodes': n_nodes,
              'old_hair_node_detached': args.old_hair_node, 'hair_vertices': int(len(P)), 'hair_triangles': int(len(fit['triangles'])),
              'cards': int(card.max()) + 1, 'scalp_cap': bool(args.scalp_cap), 'joints_added': 0,
              'material': {'alphaMode': 'MASK', 'alphaCutoff': args.alpha_cutoff, 'roughness': args.roughness, 'root_shade': args.root_shade, 'root_length': args.root_length},
              'texture_bytes': len(png), 'artistic_approval': False}
    Path(args.report).write_text(json.dumps(report, indent=1) + '\n')
    print(json.dumps(report, indent=1))


if __name__ == '__main__':
    main()
