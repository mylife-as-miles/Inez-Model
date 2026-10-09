"""Read licensed MakeHuman source without Blender or a paid image generator.

All source indices are zero based after parsing. MakeHuman coordinates are
X lateral, Y up, Z toward the face. Source has CC0 provenance in base-source.
"""
from pathlib import Path
import json
import math

ROOT = Path('/workspace')
CHARACTER = ROOT / 'assets/characters/inez'
SOURCE = CHARACTER / 'model/base-source'


def read_obj(path=SOURCE / 'base.obj'):
    vertices, texcoords, groups = [], [], {}
    group = 'ungrouped'
    for line in path.read_text().splitlines():
        row = line.split()
        if not row:
            continue
        kind = row[0]
        if kind == 'v':
            vertices.append(tuple(float(n) for n in row[1:4]))
        elif kind == 'vt':
            texcoords.append(tuple(float(n) for n in row[1:3]))
        elif kind == 'g':
            group = row[1]
            groups.setdefault(group, [])
        elif kind == 'f':
            face = []
            for part in row[1:]:
                values = part.split('/')
                face.append((int(values[0])-1, int(values[1])-1))
            groups.setdefault(group, []).append(face)
    return vertices, texcoords, groups


def read_target(path):
    values = {}
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        row = line.split()
        values[int(row[0])] = tuple(float(n) for n in row[1:4])
    return values


def shape_vertices(vertices, target_weights):
    result = [list(v) for v in vertices]
    for filename, weight in target_weights.items():
        if not weight:
            continue
        for index, delta in read_target(SOURCE / filename).items():
            for axis in range(3):
                result[index][axis] += weight*delta[axis]
    return result


def fit_vertices(vertices, controls):
    """Smooth bounded local shape controls, not a color projection.

    Control radii and delta are source-coordinate lengths. Front-only masks
    protect back-of-skull geometry. Every control is explicit in the config,
    suitable for manual replacement with sculpted shape keys later.
    """
    result = [list(v) for v in vertices]
    for control in controls:
        if 'vertex_deltas' in control:
            # Indexed exterior-topology sculpt controls preserve correspondence
            # and cannot accidentally deform helper eyes or hidden interior rows.
            for item in control['vertex_deltas']:
                index=int(item['index'])
                if not 0 <= index < len(result):
                    raise ValueError('Indexed sculpt vertex outside source topology')
                for axis in range(3):
                    result[index][axis] += item['delta'][axis]
            continue
        center = control['center']
        radius = control['radius']
        delta = control['delta']
        if len(radius) != 3 or any(r <= 0 for r in radius):
            raise ValueError('Every fitting control needs three positive radii')
        if len(center) != 3 or len(delta) != 3:
            raise ValueError('Every fitting control needs a 3D center/delta')
        for index, point in enumerate(vertices):
            if control.get('body_only') and index >= 13380:
                continue
            q = sum(((point[a]-center[a])/radius[a])**2 for a in range(3))
            if control.get('falloff') == 'compact':
                if q >= 1:
                    continue
                weight = (1-q)**2
            else:
                if q > 12:
                    continue
                weight = math.exp(-0.5*q)
            if control.get('front_only') and point[2] < 0.75:
                weight *= max(0.0, min(1.0, (point[2]-0.25)/0.5))
            for axis in range(3):
                result[index][axis] += delta[axis]*weight
    return result


def source_weight_vectors(weights, source_ids):
    """Return normalized actual licensed weights, preserving every bone name."""
    rows = {src: {} for src in source_ids}
    for bone, values in weights['weights'].items():
        for src, value in values:
            if src in rows and value > 0:
                rows[src][bone] = rows[src].get(bone, 0.0)+value
    for src, values in rows.items():
        total = sum(values.values())
        if total <= 1e-10:
            raise ValueError(f'Licensed source vertex {src} has no skin weights')
        rows[src] = {bone: value/total for bone,value in values.items()}
    return rows


def source_bounds(vertices, ids):
    return [[min(vertices[i][a] for i in ids), max(vertices[i][a] for i in ids)]
            for a in range(3)]


def rig_sources():
    return (json.loads((SOURCE/'default.mhskel').read_text()),
            json.loads((SOURCE/'default_weights.mhw').read_text()))


def joint_point(vertices, rig, name):
    ids = rig['joints'][name]
    return tuple(sum(vertices[i][a] for i in ids)/len(ids) for a in range(3))

