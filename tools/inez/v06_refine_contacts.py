"""Refine the existing recovery's contact keys against its emitted runtime rig.

Run in Blender on the untouched recovery Blend. Only six leg rotations in
four clips are replaced. The GLB is patched by appending those samples, so
geometry, textures, skinning, morphs and every other channel retain their bytes.
The versioned Blend keeps the original 60-fps timeline with fractional keys.
Use this tool to reproduce the surgical export; a generic 120-Hz export would
discard the denser interpolation. No production or likeness approval is implied.
"""
import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from animation_build import leg_ik, reset_pose, rig_lengths, update
from animation_validate_glb import Scene
from glb_expression_clips import add_accessor, read_glb, write_glb
from v06_prepare import IDENTITY

CLIPS = ('Walk', 'Run', 'CrouchDown', 'CrouchUp')
LEGS = tuple(prefix + side for side in 'LR'
             for prefix in ('upperleg01.', 'lowerleg01.', 'foot.'))
PATHS = {f'pose.bones["{name}"].rotation_quaternion' for name in LEGS}
# glTF joint axes retain Blender's bone axes; only global coordinates change.
TO_BLENDER = np.array(((1, 0, 0, 0), (0, 0, -1, 0),
                       (0, 1, 0, 0), (0, 0, 0, 1)), dtype=float)


def unchanged_curves():
    records = []
    for action in bpy.data.actions:
        for curve in action.fcurves:
            if action.name in CLIPS and curve.data_path in PATHS:
                continue
            records.append((action.name, curve.data_path, curve.array_index,
                [(tuple(p.co), tuple(p.handle_left), tuple(p.handle_right),
                  p.interpolation, p.handle_left_type, p.handle_right_type)
                 for p in curve.keyframe_points]))
    return hashlib.sha256(json.dumps(records).encode()).hexdigest()


def supports(runtime, arm):
    matrices, changes = runtime.globals()
    result = {}
    for side in 'LR':
        points = []
        for i, node in enumerate(runtime.nodes):
            if 'mesh' not in node or 'boot' not in node.get('name', '').lower():
                continue
            p = runtime.vertices(i, matrices, changes)
            mask = runtime.region_mask(i, ('foot', 'toe', 'lowerleg', 'upperleg'), side)
            selected = p[mask]
            if len(selected):
                selected = selected[selected[:, 1] < selected[:, 1].min() + .03]
                points.extend(selected @ TO_BLENDER[:3, :3].T)
        if not points:
            raise ValueError('Actual exported sole geometry required for ' + side)
        head = arm.data.bones['foot.' + side].head_local
        result[side] = [Vector(p) - head for p in points]
    return result


def plan(runtime, animation, arm, vectors, hz, speed, fraction, clearance):
    duration = max(float(runtime.accessor(s['input']).max()) for s in animation['samplers'])
    count = round(duration * hz)
    dt = duration / count
    looping = animation['name'] in ('Walk', 'Run')
    # Preserve the world-space foot pitch/roll of the already repaired 60-Hz
    # contact poses, instead of retaining their unwanted subframe oscillation.
    reference = {s: [] for s in 'LR'}
    base_count = round(duration * 60)
    indices = {n['name']: i for i, n in enumerate(runtime.nodes)}
    for t in np.linspace(0, duration, base_count + 1):
        matrices, _ = runtime.globals(animation, float(t))
        for side in 'LR':
            m = Matrix(TO_BLENDER @ matrices[indices['foot.' + side]])
            reference[side].append((m.translation.copy(),
                m.to_quaternion() @ arm.data.bones['foot.' + side].matrix_local.to_quaternion().inverted()))
    total = 3 * count + 1 if looping else count + 1
    free, flags = {s: [] for s in 'LR'}, {s: [] for s in 'LR'}
    for i in range(total):
        phase = (i % count) / count if looping else i / count
        x = phase * base_count
        left = min(int(x), base_count - 1)
        u = x - left
        for side in 'LR':
            a, qa = reference[side][left]
            b, qb = reference[side][left + 1]
            ankle = a.lerp(b, u) if looping else reference[side][0][0].copy()
            rotation = qa.slerp(qb, u) if looping else reference[side][0][1].copy()
            ankle.y -= speed * i * dt
            offsets = [rotation @ v for v in vectors[side]]
            index = min(range(len(offsets)), key=lambda k: offsets[k].z)
            free[side].append({'ankle': ankle, 'rotation': rotation,
                               'offsets': offsets, 'index': index})
            flags[side].append(not looping or ((phase + (0 if side == 'L' else .5)) % 1) < fraction)
    targets = {s: [f['ankle'].copy() for f in free[s]] for s in 'LR'}
    for side in 'LR':
        f, column = free[side], flags[side]
        i = 0
        while i < total:
            if not column[i]:
                i += 1
                continue
            start = i
            while i < total and column[i]:
                i += 1
            end = i - 1
            mid = (start + end) // 2
            sole = f[mid]['ankle'] + f[mid]['offsets'][f[mid]['index']]
            targets[side][mid] = Vector((sole.x, sole.y, clearance)) - f[mid]['offsets'][f[mid]['index']]
            for order in (range(mid + 1, end + 1), range(mid - 1, start - 1, -1)):
                for k in order:
                    previous = k - 1 if k > mid else k + 1
                    later = k if k > mid else previous
                    idx = f[later]['index']
                    contact = targets[side][previous] + f[previous]['offsets'][idx]
                    targets[side][k] = contact - f[k]['offsets'][idx]
                    targets[side][k].z = clearance - min(v.z for v in f[k]['offsets'])
        # Keep the existing lift, interpolate the small contact displacement
        # through swing, and retain its 3-mm minimum ground clearance.
        for k in range(total):
            if column[k]:
                continue
            a = k - 1
            while a >= 0 and not column[a]:
                a -= 1
            b = k + 1
            while b < total and not column[b]:
                b += 1
            da = targets[side][a] - f[a]['ankle'] if a >= 0 else Vector()
            db = targets[side][b] - f[b]['ankle'] if b < total else Vector()
            u = (k - a) / max(1, b - a)
            u = u * u * (3 - 2 * u)
            targets[side][k] = f[k]['ankle'] + da * (1 - u) + db * u
            targets[side][k].z = max(targets[side][k].z,
                clearance + .003 - min(v.z for v in f[k]['offsets']))
    begin = count if looping else 0
    return duration, np.linspace(0, duration, count + 1), dt, begin, free, targets


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-glb', required=True)
    p.add_argument('--output-blend', required=True)
    p.add_argument('--output-glb', required=True)
    p.add_argument('--report', required=True)
    p.add_argument('--hz', type=int, default=480)
    p.add_argument('--clearance', type=float, default=.00025, help='Sole clearance in metres')
    args = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
    if args.hz < 120 or args.hz % 120 or not 0 <= args.clearance < .002:
        raise ValueError('Use a multiple of 120 Hz and clearance below the contact band')
    source = Path(bpy.data.filepath).resolve()
    input_glb = Path(args.input_glb).resolve()
    output_blend, output_glb = Path(args.output_blend).resolve(), Path(args.output_glb).resolve()
    if output_blend == source or output_glb == input_glb:
        raise ValueError('Choose versioned outputs; keep the inputs untouched')
    for output in (output_blend, output_glb, Path(args.report)):
        if output.exists():
            raise ValueError('Output already exists: ' + str(output))
        output.parent.mkdir(parents=True, exist_ok=True)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    input_hash = hashlib.sha256(input_glb.read_bytes()).hexdigest()
    runtime = Scene(input_glb)
    original_data, binary = read_glb(input_glb)
    data = copy.deepcopy(original_data)
    prefix = bytes(binary)
    scene = bpy.context.scene
    arm = next(o for o in scene.objects if o.type == 'ARMATURE')
    body = bpy.data.objects['Inez_ContinuousHumanMesh_UNAPPROVED']
    for name, value in IDENTITY.items():
        assert body.data.shape_keys.key_blocks[name].value == value
    assert len(arm.data.bones) == 167
    untouched = unchanged_curves()
    original_ranges = {a.name: tuple(a.frame_range) for a in bpy.data.actions}
    modifier_flags = [(m, m.show_viewport) for o in scene.objects if o.type == 'MESH' for m in o.modifiers]
    for mod, _ in modifier_flags:
        mod.show_viewport = False
    arm.animation_data.action = None
    reset_pose(arm)
    vectors = supports(runtime, arm)
    lengths = rig_lengths(arm)
    indices = {n['name']: i for i, n in enumerate(runtime.nodes)}
    manifest = json.loads((Path(__file__).resolve().parents[2] / 'assets/characters/inez/rig/animation_manifest.json').read_text())
    report = {'source': str(source), 'source_sha256': source_hash,
        'input_glb': str(input_glb), 'input_glb_sha256': input_hash,
        'output_blend': str(output_blend), 'output_glb': str(output_glb),
        'sampling_hz': args.hz, 'sole_clearance_m': args.clearance,
        'production_approved': False, 'clips': {}, 'changed_bones': list(LEGS)}
    for name in CLIPS:
        animation = next(a for a in runtime.data['animations'] if a['name'] == name)
        action = bpy.data.actions[name]
        speed = manifest['clip_info'][name].get('matching_viewer_speed_m_s', 0)
        fraction = manifest['clip_info'][name].get('stance_fraction', 1)
        duration, times, dt, begin, free, targets = plan(runtime, animation, arm, vectors, args.hz, speed, fraction, args.clearance)
        arm.animation_data.action = action
        first, last = map(float, action.frame_range)
        fps = scene.render.fps / scene.render.fps_base
        rows = []
        emitted = {bone: [] for bone in LEGS}
        max_reach = 0
        for i, t in enumerate(times):
            frame = first + t * fps
            scene.frame_set(int(frame), subframe=frame - int(frame))
            matrices, _ = runtime.globals(animation, float(t))
            # Solve against the ACTUAL runtime parent interpolation. These
            # temporary evaluated matrices never replace the source curves.
            for parent in ('root', 'pelvis.L', 'pelvis.R'):
                arm.pose.bones[parent].matrix = arm.matrix_world.inverted() @ Matrix(TO_BLENDER @ matrices[indices[parent]])
                update()
            for side in 'LR':
                k = begin + i
                target = targets[side][k].copy()
                target.y += speed * k * dt
                _, error = leg_ik(arm, side, target, free[side][k]['rotation'], lengths)
                max_reach = max(max_reach, error)
            row = {}
            for bone in LEGS:
                pb = arm.pose.bones[bone]
                q = pb.rotation_quaternion.copy()
                if rows and q.dot(Quaternion(rows[-1][bone])) < 0:
                    q.negate()
                row[bone] = tuple(q)
                local = pb.parent.matrix.inverted() @ pb.matrix
                q_local = local.to_quaternion().normalized()
                value = np.array((q_local.x, q_local.y, q_local.z, q_local.w))
                if emitted[bone] and value @ emitted[bone][-1] < 0:
                    value = -value
                emitted[bone].append(value)
            rows.append(row)
        for curve in list(action.fcurves):
            if curve.data_path in PATHS:
                action.fcurves.remove(curve)
        for t, row in zip(times, rows):
            for bone, q in row.items():
                arm.pose.bones[bone].rotation_quaternion = q
                arm.pose.bones[bone].keyframe_insert(data_path='rotation_quaternion',
                    frame=min(last, first + float(t) * fps), group=bone)
        for curve in action.fcurves:
            if curve.data_path in PATHS:
                for key in curve.keyframe_points:
                    key.interpolation = 'LINEAR'
        target_animation = next(a for a in data['animations'] if a['name'] == name)
        input_accessor = add_accessor(data, binary, times.astype(np.float32), 'SCALAR')
        for channel in target_animation['channels']:
            bone = runtime.nodes[channel['target']['node']]['name']
            if channel['target']['path'] != 'rotation' or bone not in LEGS:
                continue
            output_accessor = add_accessor(data, binary, np.asarray(emitted[bone], np.float32), 'VEC4')
            channel['sampler'] = len(target_animation['samplers'])
            target_animation['samplers'].append({'input': input_accessor, 'output': output_accessor, 'interpolation': 'LINEAR'})
        report['clips'][name] = {'duration_s': duration, 'matching_speed_m_s': speed,
            'samples': len(times), 'max_reach_error_mm': max_reach * 1000}
        print('REFINED', name, report['clips'][name], flush=True)
    assert untouched == unchanged_curves(), 'An unrelated source curve changed'
    assert all(tuple(a.frame_range) == original_ranges[a.name] for a in bpy.data.actions), 'Authored frame range changed'
    for mod, flag in modifier_flags:
        mod.show_viewport = flag
    arm.animation_data.action = None
    reset_pose(arm)
    # Keep all existing accessor offsets and bytes, including embedded images.
    assert bytes(binary[:len(prefix)]) == prefix
    for key in ('nodes', 'meshes', 'skins', 'materials', 'textures', 'images'):
        assert data[key] == original_data[key], key + ' changed'
    data['buffers'][0]['byteLength'] = len(binary) + (-len(binary) % 4)
    write_glb(output_glb, data, binary)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend), compress=True, relative_remap=True)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    assert hashlib.sha256(input_glb.read_bytes()).hexdigest() == input_hash
    report.update({'inputs_unchanged': True, 'source_unrelated_curves_sha256': untouched,
        'original_binary_prefix_sha256': hashlib.sha256(prefix).hexdigest(),
        'original_binary_prefix_unchanged': True, 'identity_defaults': IDENTITY,
        'joint_count': len(arm.data.bones), 'clip_names': [a['name'] for a in data['animations']],
        'source_frame_ranges_unchanged': original_ranges,
        'output_blend_sha256': hashlib.sha256(output_blend.read_bytes()).hexdigest(),
        'output_glb_sha256': hashlib.sha256(output_glb.read_bytes()).hexdigest(),
        'export_method': 'append six local leg rotations in four clips; retain original runtime parent channels'})
    Path(args.report).write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
