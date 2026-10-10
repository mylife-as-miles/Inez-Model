"""Pack a strand-hair GLB's hair data into a compact web bundle (for a page that
already loads the base Inez model).

    python3 -I tools/inez/hair/pack_strands_web.py --glb STRANDS.glb --out-json hair.json --out-data hair.txt

The bundle holds only the hair added by build_strand_hair.py: guides (rest
points, skin, pinning, reference normals), strands (per point: guide index,
guide parameter, root-to-tip u, offset and tangent in the guide frame,
occlusion, radius) and the scalp patch. Quantised: offsets int16 at 10 um,
tangents and normals int8, parameters uint16/uint8; strand topology is a
point-offset table instead of an index buffer. The binary is base64-encoded
text because the page host serves no raw binary files. The JSON header lists
every section's byte offset, type and scale.
"""
import argparse
import base64
import json
from pathlib import Path

import numpy as np

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import v06_identity_normals_glb as glbmod  # noqa: E402
glbmod.NC['MAT4'] = 16
glbmod.CT[5122] = np.int16; glbmod.CT[5120] = np.int8
from v06_identity_normals_glb import GLB  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--glb', required=True)
    ap.add_argument('--out-json', required=True)
    ap.add_argument('--out-data', required=True)
    ap.add_argument('--label', default='')
    args = ap.parse_args()
    g = GLB(args.glb); j = g.json
    mesh = {m['name']: m for m in j['meshes']}
    node = {n.get('name'): n for n in j['nodes']}
    K = int(node['Inez_Hair_Guides']['extras']['particles_per_guide'])
    ga = mesh['Inez_Hair_Guides']['primitives'][0]['attributes']
    sa = mesh['Inez_Hair_Strands']['primitives'][0]['attributes']
    ca = mesh['Inez_Hair_Scalp']['primitives'][0]
    A = lambda i: g.accessor(i)
    gpos, gj, gw, gfree, gref = A(ga['POSITION']), A(ga['JOINTS_0']), A(ga['WEIGHTS_0']), A(ga['_HAIR_FREE'])[:, 0], A(ga['_HAIR_REF'])
    sguide, sgs, su, sstrand = A(sa['_HAIR_GUIDE'])[:, 0], A(sa['_HAIR_GS'])[:, 0], A(sa['_HAIR_U'])[:, 0], A(sa['_HAIR_STRAND'])[:, 0].astype(int)
    soff, stan, sao, srad = A(sa['_HAIR_OFFSET']), A(sa['_HAIR_TANGENT']), A(sa['_HAIR_AO'])[:, 0], A(sa['_HAIR_RADIUS'])[:, 0]
    offsets = np.r_[0, np.cumsum(np.bincount(sstrand))].astype(np.uint32)
    if not (np.diff(sstrand) >= 0).all():
        raise SystemExit('strand points are not grouped by strand')
    cpos, cnor, ccol = A(ca['attributes']['POSITION']), A(ca['attributes']['NORMAL']), A(ca['attributes']['COLOR_0'])
    ctri = A(ca['indices'])[:, 0].astype(np.uint32)
    OFF_SCALE = 1e-5
    if np.abs(soff).max() / OFF_SCALE > 32767:
        raise SystemExit('offset out of int16 range')
    sections = [
        ('guide_position', gpos.astype(np.float32), 1),
        ('guide_joints', gj.astype(np.uint16), 1),
        ('guide_weights', np.round(gw * 255).astype(np.uint8), 1 / 255),
        ('guide_free', np.round(gfree * 255).astype(np.uint8), 1 / 255),
        ('guide_ref', np.round(gref * 127).astype(np.int8), 1 / 127),
        ('strand_offsets', offsets, 1),
        ('point_guide', sguide.astype(np.uint16), 1),
        ('point_gs', np.round(np.clip(sgs, 0, 1) * 65535).astype(np.uint16), 1 / 65535),
        ('point_u', np.round(np.clip(su, 0, 1) * 255).astype(np.uint8), 1 / 255),
        ('point_offset', np.round(soff / OFF_SCALE).astype(np.int16), OFF_SCALE),
        ('point_tangent', np.round(np.clip(stan, -1, 1) * 127).astype(np.int8), 1 / 127),
        ('point_ao', np.round(np.clip(sao, 0, 1) * 255).astype(np.uint8), 1 / 255),
        ('point_radius', np.round(np.clip(srad, 0, 1) * 255).astype(np.uint8), 1 / 255),
        ('scalp_position', cpos.astype(np.float32), 1),
        ('scalp_normal', np.round(np.clip(cnor, -1, 1) * 127).astype(np.int8), 1 / 127),
        ('scalp_alpha', np.round(np.clip(ccol[:, 3], 0, 1) * 255).astype(np.uint8), 1 / 255),
        ('scalp_index', ctri, 1),
    ]
    blob = bytearray(); table = {}
    for name, arr, scale in sections:
        while len(blob) % 4:
            blob.append(0)
        table[name] = {'offset': len(blob), 'length': int(arr.size), 'type': arr.dtype.name, 'scale': scale,
                       'components': int(arr.shape[1]) if arr.ndim > 1 else 1}
        blob.extend(np.ascontiguousarray(arr).tobytes())
    header = {'format': 'inez-strand-hair-web/1', 'label': args.label, 'source_glb': Path(args.glb).name, 'particles_per_guide': K,
              'guides': int(len(gpos) // K), 'strands': int(len(offsets) - 1), 'points': int(len(sguide)), 'bytes': len(blob), 'sections': table,
              'scalp_material': j['materials'][ca['material']]['pbrMetallicRoughness']['baseColorFactor'],
              'note': 'Licensed hair (WhiteCap Ponytail MessyWavy, Fab) restyled and regroomed; private preview only.'}
    Path(args.out_json).write_text(json.dumps(header, indent=1) + '\n')
    Path(args.out_data).write_text(base64.b64encode(bytes(blob)).decode())
    # quantisation check
    deq = np.round(soff / OFF_SCALE) * OFF_SCALE
    print(json.dumps({'strands': header['strands'], 'points': header['points'], 'binary_bytes': len(blob),
                      'text_bytes': Path(args.out_data).stat().st_size, 'max_offset_error_m': float(np.abs(deq - soff).max())}))


if __name__ == '__main__':
    main()
