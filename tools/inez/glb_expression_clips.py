"""Add facial-expression clips (morph-weight animations) to an exported Inez GLB,
and repair zero-length tangents left by degenerate UV triangles.

    python3 -I tools/inez/glb_expression_clips.py --input inez_animated.glb --output inez_master.glb \
        [--report expression_clips.json]

Blender exports the skeletal clips; facial expressions are morph targets
(animation_build.py) that are easier to author as short timelines. Each clip
is a glTF animation whose channels target the "weights" of every node whose
mesh carries the expression's morph target (body, lashes, tearlines, teeth).

glTF morph-weight channels write every target of a mesh, so each keyframe
carries the mesh's exported default weights (identity layers such as
Inez_HeadFit_v03 = 1 stay exactly at their defaults) with only the clip's
control targets changed. Clips touch no bones, so a viewer or game can play
them on top of Idle/Walk/Run. The input file is never modified.
"""
import argparse
import json
import struct
from pathlib import Path

import numpy as np

# name: (duration_s, {target: [(time_s, weight), ...]})
CLIPS = {
    'Expr_SubtleFear': (3.0, {'SubtleFear': [(0, 0), (0.4, 1), (2.4, 0.9), (3.0, 0)],
                              'Blink_L': [(0, 0), (1.55, 0), (1.62, 1), (1.72, 1), (1.82, 0), (3.0, 0)],
                              'Blink_R': [(0, 0), (1.55, 0), (1.62, 1), (1.72, 1), (1.82, 0), (3.0, 0)]}),
    'Expr_Confusion': (3.0, {'Confused': [(0, 0), (0.5, 1), (2.5, 1), (3.0, 0)]}),
    'Expr_Anger': (2.8, {'Anger': [(0, 0), (0.3, 1), (2.3, 1), (2.8, 0)]}),
    'Expr_Exhaustion': (4.0, {'Exhaustion': [(0, 0), (0.8, 1), (3.2, 1), (4.0, 0)],
                              'Blink_L': [(0, 0), (1.8, 0), (2.1, 0.75), (2.5, 0.75), (2.8, 0), (4.0, 0)],
                              'Blink_R': [(0, 0), (1.8, 0), (2.1, 0.75), (2.5, 0.75), (2.8, 0), (4.0, 0)]}),
    'Expr_IntenseFear': (2.6, {'IntenseFear': [(0, 0), (0.25, 1), (2.0, 1), (2.6, 0)]}),
    'Expr_Suspicious': (3.0, {'Suspicious': [(0, 0), (0.6, 1), (2.4, 1), (3.0, 0)]}),
    'Expr_Blink': (0.24, {'Blink_L': [(0, 0), (0.07, 1), (0.12, 1), (0.24, 0)],
                          'Blink_R': [(0, 0), (0.07, 1), (0.12, 1), (0.24, 0)]}),
}


def read_glb(path):
    data = Path(path).read_bytes()
    magic, version, length = struct.unpack('<4sII', data[:12])
    if magic != b'glTF' or version != 2:
        raise SystemExit(f'{path} is not a glTF 2.0 binary')
    off, chunks = 12, []
    while off < length:
        n, kind = struct.unpack('<I4s', data[off:off+8])
        chunks.append((kind, data[off+8:off+8+n]))
        off += 8+n
    gltf = json.loads(chunks[0][1])
    binary = bytearray(chunks[1][1]) if len(chunks) > 1 else bytearray()
    return gltf, binary


def write_glb(path, gltf, binary):
    js = json.dumps(gltf, separators=(',', ':')).encode()
    js += b' '*((4-len(js) % 4) % 4)
    binary += b'\0'*((4-len(binary) % 4) % 4)
    total = 12+8+len(js)+8+len(binary)
    out = struct.pack('<4sII', b'glTF', 2, total)+struct.pack('<I4s', len(js), b'JSON')+js
    out += struct.pack('<I4s', len(binary), b'BIN\x00')+bytes(binary)
    Path(path).write_bytes(out)


def add_accessor(gltf, binary, array, kind):
    array = np.ascontiguousarray(array, dtype=np.float32)
    while len(binary) % 4:
        binary.append(0)
    offset = len(binary)
    binary.extend(array.tobytes())
    gltf['bufferViews'].append({'buffer': 0, 'byteOffset': offset, 'byteLength': array.nbytes})
    accessor = {'bufferView': len(gltf['bufferViews'])-1, 'componentType': 5126, 'count': int(array.shape[0]), 'type': kind}
    if kind == 'SCALAR':
        accessor['min'] = [float(array.min())]
        accessor['max'] = [float(array.max())]
    gltf['accessors'].append(accessor)
    return len(gltf['accessors'])-1


def repair_tangents(gltf, binary):
    """Replace zero-length TANGENT vectors (degenerate UV triangles in the
    source shells) with a unit vector orthogonal to the vertex normal, so the
    file passes the Khronos validator (ACCESSOR_VECTOR3_NON_UNIT)."""
    fixed = 0
    for mesh in gltf['meshes']:
        for prim in mesh['primitives']:
            attrs = prim['attributes']
            if 'TANGENT' not in attrs or 'NORMAL' not in attrs:
                continue
            ta, na = gltf['accessors'][attrs['TANGENT']], gltf['accessors'][attrs['NORMAL']]
            if ta.get('componentType') != 5126 or 'sparse' in ta:
                continue
            tv, nv = gltf['bufferViews'][ta['bufferView']], gltf['bufferViews'][na['bufferView']]
            t_off = tv.get('byteOffset', 0)+ta.get('byteOffset', 0)
            n_off = nv.get('byteOffset', 0)+na.get('byteOffset', 0)
            t_stride, n_stride = tv.get('byteStride', 16), nv.get('byteStride', 12)
            count = ta['count']
            if t_stride != 16 or n_stride != 12:
                continue
            tan = np.frombuffer(binary, np.float32, count*4, t_off).reshape(-1, 4).copy()
            nor = np.frombuffer(binary, np.float32, count*3, n_off).reshape(-1, 3)
            bad = np.linalg.norm(tan[:, :3], axis=1) < 1e-6
            if not bad.any():
                continue
            for i in np.flatnonzero(bad):
                n = nor[i]/max(np.linalg.norm(nor[i]), 1e-9)
                ref = np.array([1.0, 0, 0]) if abs(n[0]) < 0.9 else np.array([0, 1.0, 0])
                t = ref-n*np.dot(ref, n)
                tan[i, :3] = t/np.linalg.norm(t)
                tan[i, 3] = 1.0
            binary[t_off:t_off+count*16] = tan.astype(np.float32).tobytes()
            fixed += int(bad.sum())
    return fixed


def curve(keys, times):
    t = np.array([k[0] for k in keys], np.float64)
    v = np.array([k[1] for k in keys], np.float64)
    return np.interp(times, t, v)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--report')
    parser.add_argument('--fps', type=float, default=30.0)
    args = parser.parse_args()
    if Path(args.input).resolve() == Path(args.output).resolve():
        raise SystemExit('Write to a separate output; the input GLB is not modified')
    gltf, binary = read_glb(args.input)
    tangents_fixed = repair_tangents(gltf, binary)
    gltf.setdefault('animations', [])
    existing = {a.get('name') for a in gltf['animations']}
    targets_by_node = {}
    for ni, node in enumerate(gltf['nodes']):
        if 'mesh' not in node:
            continue
        mesh = gltf['meshes'][node['mesh']]
        names = (mesh.get('extras') or {}).get('targetNames')
        if not names:
            continue
        defaults = mesh.get('weights') or [0.0]*len(names)
        targets_by_node[ni] = (names, [float(w) for w in defaults])
    report = {'input': args.input, 'output': args.output, 'clips': {}, 'zero_tangents_repaired': tangents_fixed}
    for clip, (duration, tracks) in CLIPS.items():
        if clip in existing:
            raise SystemExit(f'{clip} already present in the input')
        times = np.round(np.arange(0, duration+1e-6, 1/args.fps), 6)
        if times[-1] < duration:
            times = np.append(times, duration)
        time_acc = add_accessor(gltf, binary, times, 'SCALAR')
        samplers, channels, nodes = [], [], []
        for ni, (names, defaults) in targets_by_node.items():
            touched = [t for t in tracks if t in names]
            if not touched:
                continue
            values = np.tile(np.array(defaults, np.float32), (len(times), 1))
            for t in touched:
                values[:, names.index(t)] = curve(tracks[t], times)
            out_acc = add_accessor(gltf, binary, values.reshape(-1), 'SCALAR')
            samplers.append({'input': time_acc, 'output': out_acc, 'interpolation': 'LINEAR'})
            channels.append({'sampler': len(samplers)-1, 'target': {'node': ni, 'path': 'weights'}})
            nodes.append({'node': gltf['nodes'][ni].get('name'), 'targets': touched,
                          'identity_defaults_kept': {n: w for n, w in zip(names, defaults) if w and n not in tracks}})
        if not channels:
            continue
        gltf['animations'].append({'name': clip, 'samplers': samplers, 'channels': channels,
                                   'extras': {'inez_layer': 'facial', 'one_shot': True, 'bones_touched': False}})
        report['clips'][clip] = {'duration_s': duration, 'keyframes': int(len(times)), 'nodes': nodes}
    gltf['buffers'][0]['byteLength'] = len(binary)+((4-len(binary) % 4) % 4)
    write_glb(args.output, gltf, binary)
    report['animation_count'] = len(gltf['animations'])
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'clips': list(report['clips']), 'animation_count': report['animation_count'],
                      'zero_tangents_repaired': tangents_fixed,
                      'output_bytes': Path(args.output).stat().st_size}))


if __name__ == '__main__':
    main()
