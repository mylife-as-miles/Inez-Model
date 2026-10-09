"""Contact sheets of the baked clips on the actual animated Inez .blend.

    blender -b ANIMATED.blend --python tools/inez/clip_review_render.py -- \
        --output-dir DIR [--clips Idle,Walk,...] [--samples-per-clip 6] [--resolution 420]

For each clip, evenly spaced frames are rendered with the neutral review
studio from the side (gaits, crouch) or front three-quarter (look-around,
turns); expression shapes are rendered as face close-ups. Each clip becomes
one labelled strip PNG plus a JSON index. Evidence for rig/animation QA; the
.blend is never saved.
"""
import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scan_common import Studio

VIEW = {'Idle': 90, 'Walk': 90, 'Run': 90, 'Crouch': 90, 'CrouchDown': 90, 'CrouchUp': 90,
        'LookAround': 20, 'TurnLeft': 20, 'TurnRight': 20}
EXPRESSIONS = ('Neutral', 'SubtleFear', 'Confused', 'Anger', 'Exhaustion', 'IntenseFear', 'Suspicious',
               'Blink_L', 'Viseme_AA', 'Viseme_OH')


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--clips', default='Idle,Walk,Run,LookAround,TurnLeft,TurnRight,CrouchDown,Crouch,CrouchUp')
    parser.add_argument('--samples-per-clip', type=int, default=6)
    parser.add_argument('--resolution', type=int, default=420)
    parser.add_argument('--render-samples', type=int, default=12)
    parser.add_argument('--expressions', action='store_true')
    return parser.parse_args(sys.argv[sys.argv.index('--')+1:])


def strip(paths, labels, out):
    """Join rendered frames side by side (Blender image API, no PIL)."""
    imgs = [bpy.data.images.load(str(p)) for p in paths]
    w, h = imgs[0].size
    sheet = bpy.data.images.new(out.stem, w*len(imgs), h, alpha=False)
    import numpy as np
    canvas = np.zeros((h, w*len(imgs), 4), np.float32)
    for i, img in enumerate(imgs):
        px = np.empty(w*h*4, np.float32)
        img.pixels.foreach_get(px)
        canvas[:, i*w:(i+1)*w] = px.reshape(h, w, 4)
    sheet.pixels.foreach_set(canvas.ravel())
    sheet.filepath_raw = str(out)
    sheet.file_format = 'PNG'
    sheet.save()


def main():
    args = arguments()
    scene = bpy.context.scene
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    arm = next(o for o in scene.objects if o.type == 'ARMATURE')
    for obj in scene.objects:
        if obj.type == 'LIGHT':
            obj.hide_render = True
        if obj.type == 'MESH':
            for mod in obj.modifiers:
                if mod.type == 'SUBSURF':
                    mod.show_render = False
    studio = Studio(scene, args.render_samples, args.resolution)
    index = {}
    for clip in [c for c in args.clips.split(',') if c]:
        action = bpy.data.actions.get(clip)
        if action is None:
            index[clip] = 'missing'
            continue
        arm.animation_data.action = action
        first, last = (int(v) for v in action.frame_range)
        frames = [round(first+(last-first)*i/max(1, args.samples_per_clip-1)) for i in range(args.samples_per_clip)]
        paths = []
        for f in frames:
            scene.frame_set(f)
            path = out/f'{clip}_f{f:03d}.png'
            centre = arm.matrix_world @ arm.pose.bones['root'].matrix.translation
            studio.render(Vector((centre.x, centre.y, 0.92)), 2.0, VIEW.get(clip, 90), path)
            paths.append(path)
        strip(paths, frames, out/f'{clip}_strip.png')
        index[clip] = {'frames': frames, 'strip': f'{clip}_strip.png', 'view_yaw_deg': VIEW.get(clip, 90)}
    if args.expressions:
        arm.animation_data.action = bpy.data.actions.get('Idle')
        scene.frame_set(1)
        meshes = [o for o in scene.objects if o.type == 'MESH' and o.data.shape_keys]
        head = arm.matrix_world @ arm.pose.bones['head'].matrix.translation
        paths = []
        for name in EXPRESSIONS:
            for o in meshes:
                for k in o.data.shape_keys.key_blocks:
                    if k.name in EXPRESSIONS or k.name.startswith(('Viseme_', 'Blink_')):
                        k.value = 1.0 if (k.name == name or (name == 'Blink_L' and k.name == 'Blink_R')) else 0.0
            path = out/f'expr_{name}.png'
            studio.render(Vector((head.x, head.y-0.09, head.z-0.015)), 0.30, 0, path)
            paths.append(path)
        strip(paths, list(EXPRESSIONS), out/'expressions_strip.png')
        index['expressions'] = {'names': list(EXPRESSIONS), 'strip': 'expressions_strip.png'}
    (out/'clip_review_index.json').write_text(json.dumps(index, indent=1)+'\n')
    print('CLIP_REVIEW', json.dumps(index))


if __name__ == '__main__':
    main()
