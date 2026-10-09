"""Place the user's two GLBs in one metric frame (object transforms only).

    blender -b --python tools/inez/source_prepare.py -- \
        --a assets/characters/inez/source/asset_a/Inez.glb \
        --b "assets/characters/inez/source/asset_b/Inez Facial Model.glb" \
        --output assets/characters/inez/model/work/source_aligned/source_aligned.blend \
        [--transforms source_transforms.json]

Vertex data is never edited: each source keeps its delivered mesh, UVs and
textures; only its object matrix changes. Without --transforms the placement
is provisional (A scaled to 1.746 m overall, B rotated +90 deg to face -Y and
set on A's head by bounding boxes); source_align.py then derives the final
metric scale of A (production eye height) and the landmark similarity B->A.
The .blend is a local working copy (git-ignored): rebuild it from the
read-only sources with this script.
"""
import argparse
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix

A_NAME, B_NAME = 'SRC_A_FullBody', 'SRC_B_HeadBust'
PROVISIONAL_HEIGHT_M = 1.746  # 1.70 m body + 4.6 cm platform sole


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('--a', required=True)
    parser.add_argument('--b', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--transforms')
    return parser.parse_args(sys.argv[sys.argv.index('--')+1:])


def import_single(path, name):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(Path(path).resolve()))
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == 'MESH']
    if len(meshes) != 1:
        raise RuntimeError(f'{path}: expected one mesh, found {[o.name for o in meshes]}')
    obj = meshes[0]
    # Bake any importer parent/axis transform into the object matrix and drop helpers.
    world = obj.matrix_world.copy()
    obj.parent = None
    obj.matrix_world = world
    for other in new:
        if other is not obj:
            bpy.data.objects.remove(other)
    obj.name = name
    obj['source_file'] = str(path)
    obj['source_policy'] = 'delivered mesh/UV/texture data untouched; placement by object matrix only'
    return obj


def bounds(obj):
    co = np.array([v.co for v in obj.data.vertices])
    M = np.array(obj.matrix_world)
    world = co@M[:3, :3].T+M[:3, 3]
    return world.min(0), world.max(0)


def main():
    args = arguments()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    a = import_single(args.a, A_NAME)
    b = import_single(args.b, B_NAME)
    base_a = a.matrix_world.copy()
    base_b = Matrix.Rotation(math.radians(90), 4, 'Z') @ b.matrix_world
    lo, hi = bounds(a)
    s = PROVISIONAL_HEIGHT_M/(hi[2]-lo[2])
    a.matrix_world = Matrix.Scale(s, 4) @ base_a
    b.matrix_world = Matrix.Scale(s, 4) @ base_b
    alo, ahi = bounds(a)
    blo, bhi = bounds(b)
    # Provisional: B's top onto A's top, centred over A's head.
    b.matrix_world = Matrix.Translation((0-(blo[0]+bhi[0])/2, 0-(blo[1]+bhi[1])/2, ahi[2]-bhi[2])) @ b.matrix_world
    report = {'provisional_scale': s}
    if args.transforms:
        t = json.loads(Path(args.transforms).read_text())
        a.matrix_world = Matrix(t['a_matrix'])
        b.matrix_world = Matrix(t['b_matrix'])
        report['transforms'] = args.transforms
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out.resolve()))
    report.update({'a_matrix': [list(r) for r in a.matrix_world], 'b_matrix': [list(r) for r in b.matrix_world],
                   'a_bounds': [list(map(float, x)) for x in bounds(a)], 'b_bounds': [list(map(float, x)) for x in bounds(b)]})
    print('SOURCE_PREPARE '+json.dumps(report))


if __name__ == '__main__':
    main()
