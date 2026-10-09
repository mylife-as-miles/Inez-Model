"""Measure what a GLB costs to draw, read from the file itself.

    python3 -I tools/inez/glb_stats.py model/inez_runtime.glb [more.glb ...] [--json out.json]

Per file: bytes, triangles, draw calls (one per primitive), skinned meshes,
joints, morph targets, animations, textures with their pixel sizes, and two
texture-memory estimates:

- compressed: 1 byte per texel (BC7 / ASTC 4x4 / ETC2 RGBA, which KTX2 Basis
  transcodes to on desktop and mobile GPUs) plus a third for mipmaps;
- uncompressed: 4 bytes per texel (RGBA8) plus a third for mipmaps, the cost
  of plain JPEG/PNG textures or of a KTX2 fallback.

Texture sizes come from the image headers (KTX2, PNG, JPEG). These are
estimates of GPU residency, not measurements on hardware.
"""
import argparse
import json
import struct
import sys
from pathlib import Path

COMPONENTS = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}
BYTES = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}


def read_glb(path):
    data = Path(path).read_bytes()
    magic, version, length = struct.unpack_from('<4sII', data, 0)
    if magic != b'glTF' or version != 2:
        raise SystemExit(f'{path}: not a glTF 2.0 binary')
    json_length = struct.unpack_from('<I', data, 12)[0]
    document = json.loads(data[20:20+json_length])
    offset = 20+json_length
    binary = b''
    if offset < len(data):
        chunk_length, chunk_type = struct.unpack_from('<II', data, offset)
        binary = data[offset+8:offset+8+chunk_length]
    return document, binary, len(data)


def image_size(blob):
    if blob[:12] == b'\xabKTX 20\xbb\r\n\x1a\n':
        width, height = struct.unpack_from('<II', blob, 20)
        return width, height, 'KTX2'
    if blob[:8] == b'\x89PNG\r\n\x1a\n':
        width, height = struct.unpack_from('>II', blob, 16)
        return width, height, 'PNG'
    if blob[:3] == b'\xff\xd8\xff':
        i = 2
        while i < len(blob):
            if blob[i] != 0xFF:
                i += 1
                continue
            marker = blob[i+1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                height, width = struct.unpack_from('>HH', blob, i+5)
                return width, height, 'JPEG'
            i += 2+struct.unpack_from('>H', blob, i+2)[0]
    return None, None, 'unknown'


def stats(path):
    doc, binary, size = read_glb(path)
    accessors = doc.get('accessors', [])
    views = doc.get('bufferViews', [])
    triangles = primitives = morph_targets = vertices = 0
    skinned = sum(1 for n in doc.get('nodes', []) if 'mesh' in n and 'skin' in n)
    target_names = set()
    for mesh in doc.get('meshes', []):
        names = mesh.get('extras', {}).get('targetNames', [])
        target_names.update(names)
        for prim in mesh['primitives']:
            primitives += 1
            count = accessors[prim['indices']]['count'] if 'indices' in prim else accessors[prim['attributes']['POSITION']]['count']
            triangles += count//3
            vertices += accessors[prim['attributes']['POSITION']]['count']
            morph_targets += len(prim.get('targets', []))
    # Mesh nodes drawn more than once would add draws; this asset has one node per mesh.
    mesh_nodes = sum(1 for n in doc.get('nodes', []) if 'mesh' in n)
    textures = []
    for index, image in enumerate(doc.get('images', [])):
        if 'bufferView' not in image:
            textures.append({'image': index, 'name': image.get('name'), 'format': 'external'})
            continue
        view = views[image['bufferView']]
        blob = binary[view.get('byteOffset', 0):view.get('byteOffset', 0)+view['byteLength']]
        width, height, fmt = image_size(blob)
        textures.append({'image': index, 'name': image.get('name'), 'format': fmt, 'width': width, 'height': height,
                         'bytes': view['byteLength']})
    texels = sum((t.get('width') or 0)*(t.get('height') or 0) for t in textures)
    joints = [len(s['joints']) for s in doc.get('skins', [])]
    animations = doc.get('animations', [])
    return {
        'file': str(path), 'bytes': size, 'triangles': triangles, 'vertices': vertices,
        'draw_calls': primitives, 'mesh_nodes': mesh_nodes, 'skinned_mesh_nodes': skinned,
        'materials': len(doc.get('materials', [])), 'skins': len(joints), 'joints_per_skin': sorted(set(joints)),
        'morph_target_names': len(target_names), 'morph_targets_total': morph_targets,
        'animations': len(animations), 'animation_names': [a.get('name') for a in animations],
        'images': len(textures), 'texels': texels,
        'texture_gpu_mb_compressed_estimate': round(texels*1*4/3/2**20, 1),
        'texture_gpu_mb_uncompressed_estimate': round(texels*4*4/3/2**20, 1),
        'extensions_used': doc.get('extensionsUsed', []), 'textures': textures,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('files', nargs='+')
    parser.add_argument('--json')
    args = parser.parse_args()
    results = [stats(f) for f in args.files]
    print('| File | MB | Triangles | Draw calls | Skinned meshes | Joints | Morph targets (names) | Clips | Textures | Max texture | GPU texture MB (compressed / RGBA8 est.) |')
    print('|---|---|---|---|---|---|---|---|---|---|---|')
    for r in results:
        biggest = max(((t.get('width') or 0, t.get('height') or 0) for t in r['textures']), default=(0, 0))
        print(f"| `{Path(r['file']).name}` | {r['bytes']/2**20:.1f} | {r['triangles']:,} | {r['draw_calls']} | {r['skinned_mesh_nodes']} | "
              f"{', '.join(str(j) for j in r['joints_per_skin'])} | {r['morph_target_names']} | {r['animations']} | {r['images']} | "
              f"{biggest[0]}×{biggest[1]} | {r['texture_gpu_mb_compressed_estimate']} / {r['texture_gpu_mb_uncompressed_estimate']} |")
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2)+'\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
