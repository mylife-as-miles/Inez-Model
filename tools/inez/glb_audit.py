"""Structural audit of source GLB files (no Blender; numpy + scipy + Pillow).

    python3 -I tools/inez/glb_audit.py FILE.glb [FILE.glb ...] --output audit.json

Reads the binary container directly and reports: container validity, sizes,
scene hierarchy, meshes/primitives (vertex and triangle counts, attributes,
UV sets, morph targets), materials and every embedded texture (format and
pixel size), skins/joints, animations, bounds (scale/units), and geometric
connectivity (separate shells after welding seam-split vertices). Visual
completeness questions (face, hair, clothing) are answered from renders, not
from this file.
"""
import argparse
import io
import json
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

COMPONENT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
WIDTH = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}


def read_glb(path):
    data = Path(path).read_bytes()
    magic, version, length = struct.unpack('<4sII', data[:12])
    report = {'magic': magic.decode('latin1'), 'version': version, 'declared_length': length, 'file_size': len(data),
              'valid_container': magic == b'glTF' and version == 2 and length == len(data)}
    offset, chunks = 12, {}
    while offset < len(data):
        clen, ctype = struct.unpack('<I4s', data[offset:offset+8])
        chunks[ctype] = data[offset+8:offset+8+clen]
        offset += 8+clen
    gltf = json.loads(chunks[b'JSON'])
    return report, gltf, chunks.get(b'BIN\x00', b'')


def accessor(gltf, binary, index):
    acc = gltf['accessors'][index]
    view = gltf['bufferViews'][acc['bufferView']]
    dtype = np.dtype(COMPONENT[acc['componentType']])
    width = WIDTH[acc['type']]
    start = view.get('byteOffset', 0)+acc.get('byteOffset', 0)
    stride = view.get('byteStride', 0)
    if stride and stride != dtype.itemsize*width:
        raw = np.frombuffer(binary, np.uint8, count=stride*acc['count'], offset=start).reshape(acc['count'], stride)
        return raw[:, :dtype.itemsize*width].copy().view(dtype).reshape(acc['count'], width)
    out = np.frombuffer(binary, dtype, count=acc['count']*width, offset=start)
    return out.reshape(acc['count'], width) if width > 1 else out


def shells(positions, indices):
    """Connected components after welding vertices with identical positions."""
    _, weld = np.unique(np.round(positions, 6), axis=0, return_inverse=True)
    weld = weld.ravel()
    tri = weld[indices.reshape(-1, 3)]
    n = int(weld.max())+1
    rows = np.concatenate([tri[:, 0], tri[:, 1], tri[:, 2]])
    cols = np.concatenate([tri[:, 1], tri[:, 2], tri[:, 0]])
    graph = coo_matrix((np.ones(len(rows), np.int8), (rows, cols)), shape=(n, n))
    count, labels = connected_components(graph, directed=False)
    sizes = np.bincount(labels[tri[:, 0]], minlength=count)
    order = np.argsort(-sizes)
    # Edge integrity on the welded mesh: boundary (1 face) and non-manifold (>2 faces).
    edges = np.sort(np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]]), axis=1)
    _, edge_use = np.unique(edges[:, 0].astype(np.int64)*n+edges[:, 1], return_counts=True)
    degenerate = int(((tri[:, 0] == tri[:, 1]) | (tri[:, 1] == tri[:, 2]) | (tri[:, 0] == tri[:, 2])).sum())
    return {'welded_vertices': n, 'shells': int(count),
            'boundary_edges': int((edge_use == 1).sum()), 'non_manifold_edges': int((edge_use > 2).sum()),
            'degenerate_triangles': degenerate,
            'largest_shell_triangles': [int(s) for s in sizes[order[:8]]],
            'triangles_outside_largest_shell': int(sizes.sum()-sizes[order[0]])}, labels, tri


def audit(path):
    report, gltf, binary = read_glb(path)
    report['file'] = str(path)
    report['generator'] = gltf.get('asset', {}).get('generator')
    report['extensions_used'] = gltf.get('extensionsUsed', [])
    report['nodes'] = [{k: v for k, v in node.items() if k in ('name', 'mesh', 'skin', 'children', 'translation', 'rotation', 'scale', 'matrix')}
                       for node in gltf.get('nodes', [])]
    report['skins'] = [{'name': s.get('name'), 'joints': len(s.get('joints', []))} for s in gltf.get('skins', [])]
    report['animations'] = [{'name': a.get('name'), 'channels': len(a.get('channels', []))} for a in gltf.get('animations', [])]
    images = []
    for i, image in enumerate(gltf.get('images', [])):
        view = gltf['bufferViews'][image['bufferView']]
        blob = binary[view.get('byteOffset', 0):view.get('byteOffset', 0)+view['byteLength']]
        with Image.open(io.BytesIO(blob)) as im:
            images.append({'index': i, 'name': image.get('name'), 'mime': image.get('mimeType'), 'bytes': view['byteLength'],
                           'size': list(im.size), 'mode': im.mode})
    report['images'] = images
    report['materials'] = gltf.get('materials', [])
    meshes = []
    for m, mesh in enumerate(gltf.get('meshes', [])):
        for p, prim in enumerate(mesh['primitives']):
            attrs = prim['attributes']
            pos = accessor(gltf, binary, attrs['POSITION']).astype(np.float64)
            idx = accessor(gltf, binary, prim['indices']).astype(np.int64) if 'indices' in prim else np.arange(len(pos))
            entry = {'mesh': mesh.get('name'), 'primitive': p, 'mode': prim.get('mode', 4), 'attributes': sorted(attrs),
                     'uv_sets': sorted(a for a in attrs if a.startswith('TEXCOORD')),
                     'vertices': int(len(pos)), 'triangles': int(len(idx)//3),
                     'morph_targets': len(prim.get('targets', [])), 'skinned': 'JOINTS_0' in attrs,
                     'bounds_min': pos.min(0).round(5).tolist(), 'bounds_max': pos.max(0).round(5).tolist()}
            extent = pos.max(0)-pos.min(0)
            entry['extent'] = extent.round(5).tolist()
            info, labels, tri = shells(pos, idx)
            entry['connectivity'] = info
            if 'TEXCOORD_0' in attrs:
                uv = accessor(gltf, binary, attrs['TEXCOORD_0']).astype(np.float64)
                entry['uv0_range'] = [uv.min(0).round(4).tolist(), uv.max(0).round(4).tolist()]
                # UV area coverage estimate (triangles' UV area sum, overlap counted twice).
                t = idx.reshape(-1, 3)
                a, b, c = uv[t[:, 0]], uv[t[:, 1]], uv[t[:, 2]]
                area = 0.5*np.abs((b[:, 0]-a[:, 0])*(c[:, 1]-a[:, 1])-(c[:, 0]-a[:, 0])*(b[:, 1]-a[:, 1]))
                entry['uv0_area_sum'] = float(area.sum())
            meshes.append(entry)
    report['primitives'] = meshes
    report['totals'] = {'vertices': sum(e['vertices'] for e in meshes), 'triangles': sum(e['triangles'] for e in meshes),
                        'materials': len(gltf.get('materials', [])), 'textures': len(gltf.get('textures', [])),
                        'skeleton': bool(gltf.get('skins')), 'morph_targets': sum(e['morph_targets'] for e in meshes),
                        'animations': len(gltf.get('animations', []))}
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('files', nargs='+')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    reports = [audit(f) for f in args.files]
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(reports, indent=2)+'\n')
    for r in reports:
        print(json.dumps({'file': r['file'], 'valid': r['valid_container'], 'totals': r['totals'],
                          'images': [(i['name'], i['size']) for i in r['images']],
                          'extent': [p['extent'] for p in r['primitives']],
                          'connectivity': [p['connectivity'] for p in r['primitives']]}, indent=1))


if __name__ == '__main__':
    sys.exit(main())
