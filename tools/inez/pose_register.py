"""Triangulated 3D body keypoints of selected objects from three identical cameras.

    blender -b FILE.blend --python tools/inez/pose_register.py -- \
        --objects PREFIX[,PREFIX] --output keypoints.json --image-dir DIR [--center 0,0,0.9 --span 1.86]

Front (yaw 0), left side (yaw 90) and right side (yaw -90) orthographic
renders of only the named objects go through MediaPipe Pose
(tools/inez/pose_landmarks.py). Front pixels give x and height; the side view
facing each limb gives depth (the character's left from the left view, right
from the right view, midline as the mean). Running this on Asset A and on the
production figure with the same cameras gives keypoints with the same
detector bias on both, which is what the registration needs.
"""
import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scan_common import Studio

DETECTOR = Path(__file__).resolve().parent/'pose_landmarks.py'


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('--objects', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--image-dir', required=True)
    parser.add_argument('--center', default='0,0,0.9')
    parser.add_argument('--span', type=float, default=1.86)
    parser.add_argument('--resolution', type=int, default=1200)
    return parser.parse_args(sys.argv[sys.argv.index('--')+1:])


def main():
    args = arguments()
    scene = bpy.context.scene
    keep = [k for k in args.objects.split(',') if k]
    for obj in scene.objects:
        if obj.type in ('LIGHT', 'CAMERA', 'FONT'):
            obj.hide_render = True
        if obj.type == 'MESH':
            obj.hide_render = not any(obj.name.startswith(k) for k in keep)
            for mod in obj.modifiers:
                if mod.type == 'SUBSURF':
                    mod.show_render = False
    center = Vector(tuple(float(v) for v in args.center.split(',')))
    studio = Studio(scene, 16, args.resolution)
    out = Path(args.image_dir)
    out.mkdir(parents=True, exist_ok=True)
    views = {}
    for name, yaw in (('front', 0), ('left', 90), ('right', -90)):
        path = out/f'pose_{name}.png'
        studio.render(center, args.span, yaw, path)
        run = subprocess.run(['python3', str(DETECTOR), str(path)], capture_output=True, text=True)
        data = json.loads(run.stdout.strip().splitlines()[-1]) if run.stdout.strip() else {'pose': False}
        if not data.get('pose'):
            raise SystemExit(f'No pose detected in {path}')
        views[name] = data
    res, span = args.resolution, args.span

    def unproject(u, v, yaw):
        r = math.radians(yaw)
        right = Vector((math.cos(r), math.sin(r), 0))
        return center+right*((u/res-0.5)*span)+Vector((0, 0, (0.5-v/res)*span))
    names = views['front']['names']
    points = {}
    for k, name in enumerate(names):
        fu, fv, _, fvis = views['front']['landmarks'][k]
        front = unproject(fu, fv, 0)
        side = 'left' if name.startswith('left_') else 'right' if name.startswith('right_') else None
        depths, heights = [], [front.z]
        for view, yaw in (('left', 90), ('right', -90)):
            if side and view != side:
                continue
            su, sv, _, svis = views[view]['landmarks'][k]
            p = unproject(su, sv, yaw)
            depths.append(p.y)
            heights.append(p.z)
        points[name] = {'world': [front.x, sum(depths)/len(depths), sum(heights)/len(heights)],
                        'front_visibility': fvis, 'height_spread_m': max(heights)-min(heights)}
    report = {'objects': keep, 'center': list(center), 'span_m': span, 'resolution': res, 'keypoints': points,
              'note': 'MediaPipe Pose measurement aid; identical cameras for every registered figure'}
    Path(args.output).write_text(json.dumps(report, indent=1)+'\n')
    print('POSE_REGISTER', json.dumps({'objects': keep, 'keypoints': len(points),
                                       'max_height_spread_m': max(p['height_spread_m'] for p in points.values())}))


if __name__ == '__main__':
    main()
