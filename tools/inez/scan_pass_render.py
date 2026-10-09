"""Render scan-reconstruction passes (or an Inez mesh) in the shared clay rig.

    blender -b assets/characters/inez/model/inez_scan_base.blend --python tools/inez/scan_pass_render.py -- \
        --fit scan_fitted.npz --passes aligned,warped,fitted --output DIR
    blender -b INEZ.blend --python tools/inez/scan_pass_render.py -- --inez-object NAME --output DIR \
        --label "INEZ r4 BEFORE SCAN DETAIL" [--hide Hair,...]

Pass arrays from scan_fit.py replace the scan crop's vertex positions (same
vertex order as scan_export.py). Inez meshes are rendered in the same clay with
their evaluated geometry. Every image carries its stage label in-frame.
"""
import argparse
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scan_common import Studio, VIEWS, clay_material

LABELS = {'aligned': 'PASS 1 ALIGNED SCAN - NOT INEZ', 'warped': 'PASS 2 LANDMARK-WARPED SCAN - NOT FINAL',
          'fitted': 'PASS 3 SCAN RESHAPED TO INEZ PROPORTIONS'}


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--fit')
    parser.add_argument('--passes', default='aligned,warped,fitted')
    parser.add_argument('--scan-object', default='SCAN_Ten24_L4_SOURCE_NOT_INEZ')
    parser.add_argument('--inez-object')
    parser.add_argument('--label', default='')
    parser.add_argument('--hide', default='')
    parser.add_argument('--views', default='front,three_quarter,left')
    parser.add_argument('--center', default='')
    parser.add_argument('--span', type=float, default=0.30)
    parser.add_argument('--samples', type=int, default=48)
    parser.add_argument('--resolution', type=int, default=900)
    parser.add_argument('--no-normal-map', action='store_true')
    parser.add_argument('--wrap', help='scan_wrap.npz: preview the wrap offsets on --inez-object as a temporary key')
    return parser.parse_args(sys.argv[sys.argv.index('--')+1:])


def main():
    args = arguments()
    scene = bpy.context.scene
    hide = [h for h in args.hide.split(',') if h]
    for obj in list(scene.objects):
        if obj.name.startswith('ScanLabel') or obj.name.startswith('ScanCamera'):
            bpy.data.objects.remove(obj)
    for obj in scene.objects:
        if obj.type == 'LIGHT':
            obj.hide_render = True
        if obj.type == 'MESH':
            for mod in obj.modifiers:
                if mod.type == 'SUBSURF':
                    mod.show_render = mod.show_viewport = False
            if any(h in obj.name for h in hide):
                obj.hide_render = True
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    studio = Studio(scene, args.samples, args.resolution)
    if args.inez_object:
        target = bpy.data.objects[args.inez_object]
        if args.wrap:
            wrap = np.load(args.wrap)
            rot = np.array(target.matrix_world.inverted().to_3x3())
            local = wrap['world_offsets'].astype(np.float64)@rot.T
            keys = target.data.shape_keys
            key = target.shape_key_add(name='Preview_ScanWrap', from_mix=False)
            basis = keys.key_blocks[0]
            for i, d in enumerate(local):
                key.data[i].co = basis.data[i].co+Vector(d)
            key.value = 1.0
        clay = clay_material('InezClay')
        target.data.materials.clear()
        target.data.materials.append(clay)
        center = Vector(tuple(float(v) for v in args.center.split(','))) if args.center else None
        if center is None:
            arm = next(o for o in scene.objects if o.type == 'ARMATURE')
            eyes = [arm.matrix_world @ arm.data.bones['eye.'+s].head_local for s in ('L', 'R')]
            center = (eyes[0]+eyes[1])/2+Vector((0, 0, -0.035))
        studio.set_label(args.label or 'INEZ MESH (clay)')
        for view in args.views.split(','):
            studio.render(center, args.span, VIEWS[view], out/f'{view}.png')
        return
    fit = np.load(args.fit)
    target = bpy.data.objects[args.scan_object]
    if args.no_normal_map:
        target.data.materials.clear()
        target.data.materials.append(clay_material('ScanClayPlain'))
    inverse = np.array(target.matrix_world.inverted())
    for name in args.passes.split(','):
        world = fit[name].astype(np.float64)
        local = world@inverse[:3, :3].T+inverse[:3, 3]
        target.data.vertices.foreach_set('co', local.astype(np.float32).ravel())
        target.data.update()
        if args.center:
            center = Vector(tuple(float(v) for v in args.center.split(',')))
        else:
            center = Vector(fit['center']) if 'center' in fit else None
        studio.set_label(LABELS.get(name, name.upper()))
        for view in args.views.split(','):
            studio.render(center, args.span, VIEWS[view], out/f'{name}_{view}.png')


if __name__ == '__main__':
    main()
