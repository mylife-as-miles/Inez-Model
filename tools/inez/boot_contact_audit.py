"""Per-boot ground contact audit of baked clips, on the evaluated mesh.

    blender -b assets/characters/inez/model/inez_master.blend \
        --python tools/inez/boot_contact_audit.py -- \
        --actions Walk Run TurnLeft CrouchDown --speed Walk=0.92 Run=2.40 \
        [--clip-blend animation/blender/inez_mocap_walk_cmu_02_01.blend --speed Mocap_Walk_CMU_02_01=1.128] \
        --report assets/characters/inez/qa/technical/boot_contact_audit.json

Both boots are one mesh. Each vertex is assigned to the left or right boot by
which side's bones carry most of its weight; only sole vertices (the lowest
3 cm of each boot at bind) are used. For every frame of each action:

- each boot's lowest sole point (0 = on the ground; negative = through it);
- whether that boot is planted (lowest point within 2 mm of the ground,
  below the retargeter's 3 mm swing clearance);
- per planted phase, the slip, by the retargeter's definition: the summed
  horizontal travel of the sole vertex in contact at each later frame since
  the frame before (the same material point). Rolling over the heel or toe
  is therefore not counted as slip.

In-place clips are measured with the character moved forward (-Y in
Blender) at the clip's matching speed (--speed NAME=m/s), as the game and the
viewer play them; otherwise a planted foot would read as sliding backward.

The figures are measured on the deformed mesh, independently of the
retargeter's support-point bookkeeping, and per boot, so one foot's contact
can no longer hide the other's float.
"""
import argparse
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from animation_build import vertex_side  # noqa: E402


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('--actions', nargs='*', default=['Walk', 'Run', 'TurnLeft', 'TurnRight', 'CrouchDown', 'CrouchUp', 'Idle'])
    parser.add_argument('--clip-blend', nargs='*', default=[], help='.blend files holding one retargeted action each')
    parser.add_argument('--speed', nargs='*', default=[], help='NAME=m/s matching speed of in-place clips')
    parser.add_argument('--clip-fps', type=float, default=30.0, help='frame rate the --clip-blend actions were baked at')
    parser.add_argument('--hz', type=float, help='Sample fractional frames at this rate, including the exact authored endpoint')
    # 2 mm sits between contact (0) and the retargeter's 3 mm swing clearance,
    # so early-swing frames with the toe just off the floor are not counted.
    parser.add_argument('--band', type=float, default=0.002)
    parser.add_argument('--report', required=True)
    return parser.parse_args(sys.argv[sys.argv.index('--')+1:])


def audit(arm, boots, sides, sole, band, speed=0.0, fps=None, hz=None):
    action = arm.animation_data.action
    scene = bpy.context.scene
    fps = fps or scene.render.fps/scene.render.fps_base
    if hz is not None:
        if hz <= 0 or not math.isfinite(hz):
            raise ValueError('Sampling rate must be finite and positive')
        first, last = map(float, action.frame_range)
        frames = np.linspace(first, last, round((last-first)*hz/fps)+1)
    else:
        first, last = (int(round(v)) for v in action.frame_range)
        frames = range(first, last+1)
    lows = {'L': [], 'R': []}
    phases = {'L': [], 'R': []}
    current = {'L': None, 'R': None}
    previous = None
    for frame in frames:
        frame = float(frame)
        scene.frame_set(math.floor(frame), subframe=frame-math.floor(frame))
        depsgraph = bpy.context.evaluated_depsgraph_get()
        evaluated = boots.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        co = np.empty(len(mesh.vertices)*3)
        mesh.vertices.foreach_get('co', co)
        evaluated.to_mesh_clear()
        world = np.asarray(boots.matrix_world)
        P = co.reshape(-1, 3)@world[:3, :3].T+world[:3, 3]
        P[:, 1] -= speed*(frame-first)/fps
        for side in 'LR':
            idx = sole[side]
            k = idx[np.argmin(P[idx, 2])]
            z = float(P[k, 2])
            lows[side].append(z)
            planted = z < band
            step = float(math.hypot(*(P[k, :2]-previous[k, :2]))) if previous is not None else 0.0
            if planted and current[side] is None:
                current[side] = {'frames': [frame, frame], 'slip_m': 0.0}
            elif planted:
                current[side]['slip_m'] += step
                current[side]['frames'][1] = frame
            if not planted and current[side] is not None:
                phases[side].append(current[side])
                current[side] = None
        previous = P
    for side in 'LR':
        if current[side] is not None:
            phases[side].append(current[side])
    out = {'frames': [first, last], 'travel_speed_m_s': speed}
    if hz is not None:
        out.update({'sampling_hz': hz, 'samples': len(frames), 'duration_s': (last-first)/fps})
    for side in 'LR':
        minimum_frames = 3*fps/hz if hz is not None else 3
        kept = [p for p in phases[side] if p['frames'][1]-p['frames'][0] >= minimum_frames-1e-6]
        out[side] = {'lowest_sole_mm': round(min(lows[side])*1000, 2), 'highest_sole_mm': round(max(lows[side])*1000, 2),
                     'planted_phases': [{'frames': p['frames'], 'slip_mm': round(p['slip_m']*1000, 2)} for p in kept],
                     'max_phase_slip_mm': round(max((p['slip_m'] for p in kept), default=0.0)*1000, 2)}
    return out


def main():
    args = arguments()
    speeds = {k: float(v) for k, v in (item.split('=') for item in args.speed)}
    scene = bpy.context.scene
    arm = next(o for o in scene.objects if o.type == 'ARMATURE')
    boots = next(o for o in scene.objects if o.type == 'MESH' and 'boot' in o.name.lower())
    # Only the boots need evaluating: pause the other meshes' modifiers.
    for obj in scene.objects:
        if obj.type == 'MESH' and obj != boots:
            for mod in obj.modifiers:
                mod.show_viewport = False
    sides = np.array([vertex_side(boots, v) or '?' for v in boots.data.vertices])
    rest = np.array([tuple(boots.matrix_world @ v.co) for v in boots.data.vertices])
    sole = {}
    for side in 'LR':
        idx = np.where(sides == side)[0]
        floor = rest[idx, 2].min()
        sole[side] = idx[rest[idx, 2] < floor+0.03]
    report = {'blend': bpy.data.filepath, 'boots_mesh': boots.name, 'band_m': args.band,
              'sole_vertices': {s: int(len(v)) for s, v in sole.items()},
              'boot_vertices': {s: int((sides == s).sum()) for s in 'LR'}, 'clips': {}}
    for name in args.actions:
        if name not in bpy.data.actions:
            report['clips'][name] = 'missing'
            continue
        arm.animation_data.action = bpy.data.actions[name]
        report['clips'][name] = audit(arm, boots, sides, sole, args.band, speeds.get(name, 0.0), hz=args.hz)
        print('AUDIT', name, json.dumps({s: {k: report['clips'][name][s][k] for k in ('lowest_sole_mm', 'max_phase_slip_mm')} for s in 'LR'}))
    for path in args.clip_blend:
        with bpy.data.libraries.load(str(Path(path).resolve()), link=False) as (source, target):
            target.actions = list(source.actions)
        for action in target.actions:
            arm.animation_data.action = action
            report['clips'][action.name] = audit(arm, boots, sides, sole, args.band, speeds.get(action.name, 0.0), args.clip_fps, args.hz)
            report['clips'][action.name]['source_blend'] = path
            print('AUDIT', action.name, json.dumps({s: {k: report['clips'][action.name][s][k] for k in ('lowest_sole_mm', 'max_phase_slip_mm')} for s in 'LR'}))
    Path(args.report).write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
