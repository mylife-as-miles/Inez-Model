"""Correct the shading normals of Inez's identity-shaped body in a GLB (append-only).

    python3 -I tools/inez/v06_identity_normals_glb.py \
        --input assets/characters/inez/model/v06/inez_recovery_v06.glb \
        --output assets/characters/inez/model/v06/inez_recovery_v06_normals_r01.glb \
        --report assets/characters/inez/qa/v06/normals_r01_patch.json

Why. The body carries seven identity morph targets. Five stay at weight 1
at all times (HeadFit_v03 and the four _v05 layers); they move vertices by up
to 25 cm. glTF stores a NORMAL delta per target and renderers add them
linearly, n = n0 + sum(w_i * dn_i). For deformations this large that sum is
not the normal of the resulting surface. Measured on the V06 default GLB
(sha 3bbb563b...): the face primitive's runtime normal differs from the true
normal of its identity-shaped surface by 3.0 deg median, 19.4 deg at the
95th percentile and up to 142 deg; the torso primitive by 8.4 / 16.5 / 64 deg.
On smooth skin under directional light that shows as contour-like diagonal
bands. They are not in the albedo texture.

What. For the body mesh only:
1. evaluate the identity-shaped positions (base + default weight x POSITION
   delta of every target with a non-zero default weight);
2. recompute smooth, corner-angle-weighted vertex normals, welding vertices
   that share a position across UV seams and across the two primitives;
3. write them as the primitives' base NORMAL, and point the NORMAL of every
   target whose default weight is non-zero to an all-zero accessor, so that
   at the default weights the renderer's normal is the true one;
4. re-orthogonalise TANGENT.xyz against the new normal (Gram-Schmidt; the
   handedness w is kept). Degenerate tangents are rebuilt from UV gradients.
Targets at weight 0 by default (HeadFit v01/v02, expressions, visemes,
blinks) keep their NORMAL deltas, so expressions still shade.

Bytes. The original JSON is edited only where accessors are re-pointed and
new accessors are added; the original binary chunk is kept as a byte-exact
prefix and new data is appended. Positions, UVs, joints, weights, morph
POSITION deltas, materials, images and animations are not touched. The
report records hashes of every preserved accessor's bytes.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

import numpy as np

CT = {5126: np.float32, 5123: np.uint16, 5125: np.uint32, 5121: np.uint8}
NC = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}


class GLB:
    def __init__(self, path):
        data = Path(path).read_bytes()
        magic, version, length = struct.unpack('<4sII', data[:12])
        if magic != b'glTF' or version != 2 or length != len(data):
            raise ValueError('not a GLB 2.0 file')
        jl, jt = struct.unpack('<II', data[12:20])
        self.json = json.loads(data[20:20+jl])
        off = 20+jl
        bl, bt = struct.unpack('<II', data[off:off+8])
        if bt != 0x004E4942:
            raise ValueError('second chunk is not BIN')
        self.bin = bytearray(data[off+8:off+8+bl])
        if len(self.json['buffers']) != 1 or 'uri' in self.json['buffers'][0]:
            raise ValueError('expected one embedded buffer')

    def accessor(self, index):
        a = self.json['accessors'][index]
        n, dt = NC[a['type']], CT[a['componentType']]
        out = np.zeros((a['count'], n), np.float64)
        if 'bufferView' in a:
            bv = self.json['bufferViews'][a['bufferView']]
            stride = bv.get('byteStride', np.dtype(dt).itemsize*n)
            start = bv.get('byteOffset', 0)+a.get('byteOffset', 0)
            raw = np.frombuffer(bytes(self.bin), np.uint8)
            if stride == np.dtype(dt).itemsize*n:
                out = np.frombuffer(raw[start:start+a['count']*stride].tobytes(), dt).reshape(a['count'], n).astype(np.float64)
            else:
                out = np.stack([np.frombuffer(raw[start+i*stride:start+i*stride+np.dtype(dt).itemsize*n].tobytes(), dt) for i in range(a['count'])]).astype(np.float64)
        if 'sparse' in a:
            s = a['sparse']
            idx = self._view(s['indices'], s['count'], 1, CT[s['indices']['componentType']])[:, 0].astype(int)
            out[idx] = self._view(s['values'], s['count'], n, dt)
        if a.get('normalized'):
            raise ValueError('normalized accessors are not supported by this tool')
        return out

    def _view(self, ref, count, n, dt):
        bv = self.json['bufferViews'][ref['bufferView']]
        start = bv.get('byteOffset', 0)+ref.get('byteOffset', 0)
        return np.frombuffer(bytes(self.bin[start:start+count*n*np.dtype(dt).itemsize]), dt).reshape(count, n).astype(np.float64)

    def accessor_bytes_hash(self, index):
        a = self.json['accessors'][index]
        return hashlib.sha256(self.accessor(index).astype(np.float64).tobytes()).hexdigest() if a else None

    def append_float_accessor(self, values, kind):
        values = np.ascontiguousarray(values, np.float32)
        while len(self.bin) % 4:
            self.bin.append(0)
        offset = len(self.bin)
        self.bin.extend(values.tobytes())
        self.json['bufferViews'].append({'buffer': 0, 'byteOffset': offset, 'byteLength': values.nbytes, 'target': 34962})
        accessor = {'bufferView': len(self.json['bufferViews'])-1, 'componentType': 5126, 'count': int(values.shape[0]), 'type': kind}
        self.json['accessors'].append(accessor)
        return len(self.json['accessors'])-1

    def append_zero_accessor(self, count, kind):
        # glTF 2.0: an accessor without bufferView (and without sparse) is all zeros.
        self.json['accessors'].append({'componentType': 5126, 'count': int(count), 'type': kind})
        return len(self.json['accessors'])-1

    def write(self, path):
        while len(self.bin) % 4:
            self.bin.append(0)
        self.json['buffers'][0]['byteLength'] = len(self.bin)
        j = json.dumps(self.json, separators=(',', ':')).encode()
        j += b' '*((4-len(j) % 4) % 4)
        total = 12+8+len(j)+8+len(self.bin)
        out = struct.pack('<4sII', b'glTF', 2, total)+struct.pack('<II', len(j), 0x4E4F534A)+j
        out += struct.pack('<II', len(self.bin), 0x004E4942)+bytes(self.bin)
        Path(path).write_bytes(out)


def corner_angle_normals(positions, triangles, weld=1e-7):
    """Angle-weighted smooth normals over several primitives sharing one space."""
    keys = {}
    ids = []
    for p in positions:
        q = np.round(p/weld).astype(np.int64)
        idx = np.empty(len(p), np.int64)
        for i, k in enumerate(map(tuple, q)):
            idx[i] = keys.setdefault(k, len(keys))
        ids.append(idx)
    acc = np.zeros((len(keys), 3))
    for p, tri, idx in zip(positions, triangles, ids):
        a, b, c = p[tri[:, 0]], p[tri[:, 1]], p[tri[:, 2]]
        n = np.cross(b-a, c-a)
        length = np.linalg.norm(n, axis=1)
        ok = length > 0
        n = n[ok]/length[ok, None]
        corners = ((a, b, c), (b, c, a), (c, a, b))
        for k, (o, p1, p2) in enumerate(corners):
            e1, e2 = (p1-o)[ok], (p2-o)[ok]
            cosang = np.einsum('ij,ij->i', e1, e2)/np.maximum(np.linalg.norm(e1, axis=1)*np.linalg.norm(e2, axis=1), 1e-30)
            ang = np.arccos(np.clip(cosang, -1, 1))
            np.add.at(acc, idx[tri[ok, k]], n*ang[:, None])
    out = []
    for idx in ids:
        v = acc[idx]
        out.append(v/np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-30))
    return out, len(keys)


def uv_tangents(p, uv, tri, normal):
    t = np.zeros_like(p)
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    e1, e2 = p[b]-p[a], p[c]-p[a]
    d1, d2 = uv[b]-uv[a], uv[c]-uv[a]
    det = d1[:, 0]*d2[:, 1]-d2[:, 0]*d1[:, 1]
    ok = np.abs(det) > 1e-12
    f = np.zeros_like(det)
    f[ok] = 1/det[ok]
    tan = (e1*d2[:, 1:2]-e2*d1[:, 1:2])*f[:, None]
    for k in (a, b, c):
        np.add.at(t, k, tan)
    t -= normal*np.einsum('ij,ij->i', t, normal)[:, None]
    return t/np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-30)


def angles(a, b):
    return np.degrees(np.arccos(np.clip(np.einsum('ij,ij->i', a, b), -1, 1)))


def stats(v):
    return {'median_deg': float(np.median(v)), 'p95_deg': float(np.percentile(v, 95)), 'max_deg': float(v.max())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--report', required=True)
    ap.add_argument('--mesh-name', default='Inez_ContinuousHumanMesh_UNAPPROVED')
    args = ap.parse_args()
    if Path(args.output).exists() or Path(args.report).exists():
        raise SystemExit('refusing to overwrite an existing output or report')
    src = Path(args.input).read_bytes()
    glb = GLB(args.input)
    original_bin = bytes(glb.bin)
    mi = next(i for i, m in enumerate(glb.json['meshes']) if m['name'].startswith(args.mesh_name))
    mesh = glb.json['meshes'][mi]
    names = mesh['extras']['targetNames']
    weights = np.array(mesh.get('weights') or [0]*len(names), float)
    active = [k for k, w in enumerate(weights) if w != 0]
    prims = mesh['primitives']
    positions, triangles, before_normals, uvs, tangents = [], [], [], [], []
    for prim in prims:
        p = glb.accessor(prim['attributes']['POSITION'])
        n = glb.accessor(prim['attributes']['NORMAL'])
        for k in range(len(prim['targets'])):
            t = prim['targets'][k]
            if weights[k]:
                p = p+weights[k]*glb.accessor(t['POSITION'])
            if 'NORMAL' in t and weights[k]:
                n = n+weights[k]*glb.accessor(t['NORMAL'])
        positions.append(p)
        triangles.append(glb.accessor(prim['indices']).astype(np.int64).reshape(-1, 3))
        before_normals.append(n/np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-30))
        uvs.append(glb.accessor(prim['attributes']['TEXCOORD_0']))
        tangents.append(glb.accessor(prim['attributes']['TANGENT']) if 'TANGENT' in prim['attributes'] else None)
    normals, welded = corner_angle_normals(positions, triangles)
    preserved = {}
    for pi, prim in enumerate(prims):
        for key, index in prim['attributes'].items():
            if key not in ('NORMAL', 'TANGENT'):
                preserved[f'prim{pi}.{key}'] = glb.accessor_bytes_hash(index)
        for k, t in enumerate(prim['targets']):
            preserved[f'prim{pi}.target{k}.POSITION'] = glb.accessor_bytes_hash(t['POSITION'])
    report = {'input': args.input, 'input_sha256': hashlib.sha256(src).hexdigest(), 'mesh': mesh['name'],
              'default_weights': dict(zip(names, weights.tolist())), 'zeroed_normal_targets': [names[k] for k in active],
              'welded_positions': welded, 'primitives': []}
    for pi, prim in enumerate(prims):
        n = normals[pi]
        entry = {'vertices': int(len(n)), 'before_vs_true': stats(angles(before_normals[pi], n))}
        prim['attributes']['NORMAL'] = glb.append_float_accessor(n, 'VEC3')
        if tangents[pi] is not None:
            t = tangents[pi]
            xyz = t[:, :3]-n*np.einsum('ij,ij->i', t[:, :3], n)[:, None]
            length = np.linalg.norm(xyz, axis=1)
            bad = length < 1e-3
            if bad.any():
                rebuilt = uv_tangents(positions[pi], uvs[pi], triangles[pi], n)
                xyz[bad] = rebuilt[bad]
                length = np.linalg.norm(xyz, axis=1)
            xyz /= np.maximum(length[:, None], 1e-30)
            w = np.where(t[:, 3] < 0, -1.0, 1.0)
            entry['tangent_rebuilt_from_uv'] = int(bad.sum())
            entry['tangent_rotation_deg'] = stats(angles(t[:, :3]/np.maximum(np.linalg.norm(t[:, :3], axis=1, keepdims=True), 1e-30), xyz))
            prim['attributes']['TANGENT'] = glb.append_float_accessor(np.column_stack([xyz, w]), 'VEC4')
        zero = glb.append_zero_accessor(len(n), 'VEC3')
        for k in active:
            if 'NORMAL' in prim['targets'][k]:
                prim['targets'][k]['NORMAL'] = zero
        # Renderer normal after the patch at default weights, for the report.
        after = glb.accessor(prim['attributes']['NORMAL'])
        for k, t in enumerate(prim['targets']):
            if weights[k] and 'NORMAL' in t:
                after = after+weights[k]*glb.accessor(t['NORMAL'])
        after /= np.maximum(np.linalg.norm(after, axis=1, keepdims=True), 1e-30)
        entry['after_vs_true'] = stats(angles(after, n))
        report['primitives'].append(entry)
    if bytes(glb.bin[:len(original_bin)]) != original_bin:
        raise RuntimeError('original binary prefix changed')
    after_preserved = {}
    for pi, prim in enumerate(prims):
        for key, index in prim['attributes'].items():
            if key not in ('NORMAL', 'TANGENT'):
                after_preserved[f'prim{pi}.{key}'] = glb.accessor_bytes_hash(index)
        for k, t in enumerate(prim['targets']):
            after_preserved[f'prim{pi}.target{k}.POSITION'] = glb.accessor_bytes_hash(t['POSITION'])
    if after_preserved != preserved:
        raise RuntimeError('a preserved accessor changed')
    glb.write(args.output)
    out = Path(args.output).read_bytes()
    report.update({'output': args.output, 'output_sha256': hashlib.sha256(out).hexdigest(),
                   'bytes_added': len(out)-len(src), 'original_binary_prefix_preserved': True,
                   'preserved_accessor_hashes': len(preserved),
                   'note': 'Candidate only. Default model unchanged until matched-render review.'})
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: report[k] for k in ('zeroed_normal_targets', 'welded_positions', 'bytes_added')}))
    for i, e in enumerate(report['primitives']):
        print(i, e)


if __name__ == '__main__':
    main()
