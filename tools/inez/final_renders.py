"""Canonical review renders of the Inez master (Cycles, neutral studio).

    blender -b inez_master.blend --python tools/inez/final_renders.py -- --output-dir renders/master_v1

Face views (span 0.36 m) at yaw 0, ±35, ±90 and at ±13 / ±25 degrees, which
match the head turns MediaPipe measures on the original portraits; body views
(span 1.95 m) front, three-quarter, left, right and back. Rest pose, neutral
face, identity layers at their defaults. Subdivision is off, so the images show
the exported mesh. The .blend is never saved.
"""
import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scan_common import Studio

FACE = {'face_front': 0, 'face_three_quarter': 35, 'face_left': 90, 'face_right': -90, 'face_three_quarter_right': -35,
        'face_yaw_p5': 5, 'face_yaw_p13': 13, 'face_yaw_p18': 18, 'face_yaw_m13': -13, 'face_yaw_p25': 25, 'face_yaw_m25': -25}
BODY = {'body_front': 0, 'body_three_quarter': 35, 'body_left': 90, 'body_right': -90, 'body_back': 180}


def main():
    argv = sys.argv[sys.argv.index('--')+1:]
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--samples', type=int, default=64)
    parser.add_argument('--face-resolution', type=int, default=1000)
    parser.add_argument('--body-resolution', type=int, default=1000)
    parser.add_argument('--only', default='')
    args = parser.parse_args(argv)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    arm = next(o for o in scene.objects if o.type == 'ARMATURE')
    if arm.animation_data:
        arm.animation_data.action = None
    for pb in arm.pose.bones:
        pb.rotation_mode = 'QUATERNION'
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
    for obj in scene.objects:
        if obj.type == 'LIGHT':
            obj.hide_render = True
        if obj.type == 'MESH':
            for mod in obj.modifiers:
                if mod.type == 'SUBSURF':
                    mod.show_render = False
            if obj.data.shape_keys:
                for key in obj.data.shape_keys.key_blocks:
                    if not key.name.startswith('Inez_') and key != obj.data.shape_keys.key_blocks[0]:
                        key.value = 0.0
    bpy.context.view_layer.update()
    eyes = [arm.matrix_world @ arm.data.bones['eye.'+s].head_local for s in ('L', 'R')]
    eye = (eyes[0]+eyes[1])/2
    face_centre = Vector((eye.x, eye.y-0.01, eye.z-0.053))
    only = set(filter(None, args.only.split(',')))
    index = {}
    studio = Studio(scene, args.samples, args.face_resolution)
    for name, yaw in FACE.items():
        if only and name not in only:
            continue
        studio.render(face_centre, 0.36, yaw, out/f'{name}.png')
        index[name] = {'yaw_deg': yaw, 'span_m': 0.36, 'centre': list(face_centre)}
    scene.render.resolution_x = scene.render.resolution_y = args.body_resolution
    for name, yaw in BODY.items():
        if only and name not in only:
            continue
        studio.render(Vector((0.0, 0.0, 0.90)), 1.95, yaw, out/f'{name}.png', distance=3.0)
        index[name] = {'yaw_deg': yaw, 'span_m': 1.95, 'centre': [0.0, 0.0, 0.90]}
    (out/'render_index.json').write_text(json.dumps(index, indent=1)+'\n')
    print('FINAL_RENDERS', json.dumps(sorted(index)))


if __name__ == '__main__':
    main()
