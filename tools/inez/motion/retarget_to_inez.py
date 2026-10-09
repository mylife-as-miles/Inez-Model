"""Retarget an intermediate-skeleton (ISK) motion onto Inez's rig and bake a clip.

    blender -b ANIMATED.blend --python tools/inez/motion/retarget_to_inez.py -- \
        --isk MOTION_isk.npz --name Mocap_Walk_CMU_02_01 --output-glb CLIP.glb \
        --report REPORT.json [--fps 30] [--root-motion] [--no-contact-fix] \
        [--save-blend CLIP.blend] [--preview-dir DIR]

Works on the real animated master (the same rig, bone rolls and rest pose as
every exported GLB). Mapping (see docs/INEZ_SKELETON_MAPPING.md):

- Pelvis, spine and head: the source segments' rotations relative to their
  own rest pose are applied to Inez's rest orientations. The pelvis-to-chest
  rotation is spread over spine05..spine01, chest-to-head over neck01..head.
- Arms and hands: aimed along the source segment directions (the sources'
  rest poses differ from Inez's A-pose, so rest-relative rotation would
  carry the wrong rest). Twist bones keep their inherited transform; the
  palm is rolled toward the body.
- Legs: two-bone IK from Inez's hip to an ankle target scaled from the
  source leg vector by the leg-length ratio, with the knee plane from the
  source knee. Feet follow the source foot direction relative to its rest.
- Root: Inez's standing pelvis height plus the scaled source pelvis motion.

Contact pass (default on): during source stance frames each boot sole is put
on the ground (Inez's measured sole support points) and its horizontal
position is held from stance start, blended over 3 frames at lift-off. The
pelvis is lowered where a planted leg could not reach. Swing feet are kept
above the floor.

Root motion is solved in world space; unless --root-motion is given the
clip is made in-place by removing the straight-line average root velocity,
which is reported as the matching playback speed (the viewer moves the
character at that speed so planted feet stay planted).

The ponytail spring chain is simulated over the clip (0.5 s settle at the
first pose). The output GLB holds the armature and this one action, so it
plays on any Inez GLB through the same bone names.
"""
import argparse
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import isk  # noqa: E402
from animation_build import (absolute_world_rotation, aim_bone, aim_chain, base_matrix, boot_vectors,  # noqa: E402
                             curl_fingers, hair_chain, reset_pose, rig_lengths, relax_hand, simulate_hair,
                             two_bone_joint, world_translation)

SPINE = ('spine05', 'spine04', 'spine03', 'spine02', 'spine01')
NECK = ('neck01', 'neck02', 'neck03', 'head')
SIDES = {'L': 'l', 'R': 'r'}
HAND_MODE = {'mode': 'forearm', 'curl': 10.0}
GAIT_BONES = ('root', 'spine01', 'neck01', 'upperleg01.L', 'lowerleg01.L', 'foot.L', 'upperleg01.R', 'lowerleg01.R', 'foot.R')


def angle(a, b):
    return math.degrees(math.acos(max(-1.0, min(1.0, a.normalized().dot(b.normalized())))))


def gait_measures(frames, contacts):
    """Knee flexion (180 - hip/knee/ankle angle) at stance and swing, and
    trunk lean (pelvis-to-neck-base vector from vertical; + is forward, -Y)."""
    out = {}
    for k, side in enumerate('LR'):
        stance, swing = [], []
        for f, j in enumerate(frames):
            flex = 180-angle(j['hip_'+side]-j['knee_'+side], j['ankle_'+side]-j['knee_'+side])
            (stance if contacts[f] is not None and contacts[f][k] else swing).append(flex)
        out['knee_flexion_deg_'+side] = {'stance_mean': float(np.mean(stance)) if stance else None,
                                         'stance_max': float(np.max(stance)) if stance else None,
                                         'swing_max': float(np.max(swing)) if swing else None}
    leans = []
    for j in frames:
        v = j['chest']-j['pelvis']
        leans.append(math.degrees(math.atan2(-v.y, v.z)))
    out['trunk_lean_deg'] = {'mean': float(np.mean(leans)), 'min': float(np.min(leans)), 'max': float(np.max(leans))}
    return out


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('--isk', required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--output-glb', required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--fps', type=float, default=30.0)
    parser.add_argument('--root-motion', action='store_true')
    parser.add_argument('--no-contact-fix', action='store_true')
    parser.add_argument('--no-align-travel', action='store_true')
    parser.add_argument('--save-blend')
    parser.add_argument('--trajectory-json', help='write source/target paths and contacts for the viewer lab')
    parser.add_argument('--preview-dir', help='render side and front frames of the baked clip on the full model')
    parser.add_argument('--preview-frames', type=int, default=8)
    parser.add_argument('--hand-mode', choices=('forearm', 'source'), default='forearm',
                        help='forearm: neutral wrist along the forearm (default; optical hand segments are noisy); '
                             'source: aim along the source hand segment')
    parser.add_argument('--finger-curl', type=float, default=10.0, help='extra relaxed finger flexion (degrees)')
    return parser.parse_args(sys.argv[sys.argv.index('--')+1:])


def update():
    bpy.context.view_layer.update()


def quat(q):
    return Quaternion((float(q[0]), float(q[1]), float(q[2]), float(q[3])))


def sampler(data, align):
    """Time -> (positions, rotations, contacts) with linear/slerp interpolation."""
    P, R, C = data['positions'], data['rotations'], data.get('contacts')
    freq = float(data['meta']['frequency_hz'])
    n = len(P)
    yaw = Quaternion(Vector((0, 0, 1)), align)
    rot = np.array(yaw.to_matrix())

    def at(t):
        f = min(max(t*freq, 0.0), n-1.0)
        i = int(math.floor(f))
        j = min(i+1, n-1)
        a = f-i
        pos = (P[i]*(1-a)+P[j]*a)@rot.T
        rots = [yaw @ quat(R[i, k]).slerp(quat(R[j, k]), a) for k in range(R.shape[1])]
        contact = C[i if a < 0.5 else j] if C is not None else None
        return pos, rots, contact
    return at, (n-1)/freq


def travel_alignment(data):
    """Yaw (radians) that turns the net pelvis displacement to -Y."""
    pel = data['positions'][:, isk.JOINTS.index('pelvis')]
    d = pel[-1]-pel[0]
    if np.hypot(d[0], d[1]) < 0.3:
        return 0.0
    return -math.pi/2-math.atan2(d[1], d[0])


def J(name):
    return isk.JOINTS.index(name)


def S(name):
    return isk.SEGMENTS.index(name)


class Rig:
    def __init__(self, arm, meshes, body):
        self.arm = arm
        self.inv = arm.matrix_world.inverted()
        self.lengths = rig_lengths(arm)
        self.supports = boot_vectors(arm, meshes, body)
        b = arm.data.bones
        self.rest_q = {n: b[n].matrix_local.to_quaternion() for n in
                       ('root',)+SPINE+NECK+tuple(f'{p}.{s}' for p in ('foot', 'wrist') for s in 'LR')}
        self.rest_root = b['root'].head_local.copy()
        self.rest_hip = {s: b['upperleg01.'+s].head_local.copy() for s in 'LR'}
        self.rest_ankle = {s: b['foot.'+s].head_local.copy() for s in 'LR'}
        self.rest_foot_dir = {s: (b['foot.'+s].tail_local-b['foot.'+s].head_local).normalized() for s in 'LR'}
        self.leg = {s: self.lengths[s]['thigh']+self.lengths[s]['shin'] for s in 'LR'}

    def lowest_sole(self, side):
        """Lowest boot support point (armature space z) for the current pose."""
        pb = self.arm.pose.bones['foot.'+side]
        delta = pb.matrix.to_quaternion() @ self.rest_q['foot.'+side].inverted()
        head = pb.matrix.translation
        return min((head+delta @ v).z for v in self.supports[side]['vectors'])


def pose_frame(rig, src, rest_src, scale, contact_targets=None, pelvis_drop=0.0):
    """Pose Inez for one sample. Returns the ankle targets and reach errors."""
    arm = rig.arm
    pos, rots, _ = src
    reset_pose(arm)
    d_pelvis, d_chest, d_head = rots[S('pelvis')], rots[S('chest')], rots[S('head')]
    # Root: Inez's standing pelvis plus the scaled source pelvis motion.
    p = Vector(pos[J('pelvis')])
    p_rest = Vector(rest_src[J('pelvis')])
    target = rig.rest_root+Vector(((p.x-p_rest.x)*scale, (p.y-p_rest.y)*scale, (p.z-p_rest.z)*scale-pelvis_drop))
    root = arm.pose.bones['root']
    absolute_world_rotation(root, d_pelvis @ rig.rest_q['root'])
    update()
    world_translation(root, target-root.matrix.translation)
    update()
    # Spine and neck: spread the relative rotations along the chains.
    rel = d_pelvis.inverted() @ d_chest
    for k, name in enumerate(SPINE, 1):
        absolute_world_rotation(arm.pose.bones[name], d_pelvis @ Quaternion().slerp(rel, k/len(SPINE)) @ rig.rest_q[name])
        update()
    rel = d_chest.inverted() @ d_head
    for k, name in enumerate(NECK, 1):
        absolute_world_rotation(arm.pose.bones[name], d_chest @ Quaternion().slerp(rel, k/len(NECK)) @ rig.rest_q[name])
        update()
    result = {}
    for side, s in SIDES.items():
        # Arms by direction.
        sh, el, wr, ha = (Vector(pos[J(n+'_'+s)]) for n in ('shoulder', 'elbow', 'wrist', 'hand'))
        upper = arm.pose.bones['upperarm01.'+side]
        elbow = base_matrix(upper).translation+(el-sh).normalized()*rig.lengths[side]['upper_arm']
        aim_chain(arm, 'upperarm01.'+side, 'lowerarm01.'+side, elbow)
        fore = arm.pose.bones['lowerarm01.'+side]
        wrist = base_matrix(fore).translation+(wr-el).normalized()*rig.lengths[side]['forearm']
        aim_chain(arm, 'lowerarm01.'+side, 'wrist.'+side, wrist)
        hand_dir = (ha-wr).normalized() if HAND_MODE['mode'] == 'source' else (wr-el).normalized()
        aim_bone(arm.pose.bones['wrist.'+side], hand_dir)
        relax_hand(arm, side, hand_dir)
        curl_fingers(arm, side, HAND_MODE['curl'])
        # Legs by IK on the scaled source leg vector.
        hip_s, knee_s, ankle_s, toe_s = (Vector(pos[J(n+'_'+s)]) for n in ('hip', 'knee', 'ankle', 'toe'))
        leg_src = (Vector(rest_src[J('knee_'+s)])-Vector(rest_src[J('hip_'+s)])).length + \
                  (Vector(rest_src[J('ankle_'+s)])-Vector(rest_src[J('knee_'+s)])).length
        hip = base_matrix(arm.pose.bones['upperleg01.'+side]).translation
        ankle = hip+(ankle_s-hip_s)*(rig.leg[side]/leg_src)
        if contact_targets and contact_targets.get(side) is not None:
            ankle = Vector(contact_targets[side])
        pole = knee_s-(hip_s+ankle_s)/2
        knee, reached, error = two_bone_joint(hip, ankle, rig.lengths[side]['thigh'], rig.lengths[side]['shin'], pole)
        aim_chain(arm, 'upperleg01.'+side, 'lowerleg01.'+side, knee)
        aim_chain(arm, 'lowerleg01.'+side, 'foot.'+side, reached)
        # The foot's world rotation comes from the source alone (rest-relative
        # swing of the ankle-to-toe direction), never from the shin's
        # inherited roll, so free and contact-locked solves share it.
        rest_dir_src = (Vector(rest_src[J('toe_'+s)])-Vector(rest_src[J('ankle_'+s)])).normalized()
        now_dir_src = (toe_s-ankle_s).normalized()
        absolute_world_rotation(arm.pose.bones['foot.'+side],
                                rest_dir_src.rotation_difference(now_dir_src) @ rig.rest_q['foot.'+side])
        update()
        result[side] = {'ankle_target': ankle.copy(), 'reach_error_m': float(error), 'hip': hip.copy()}
    return result


def foot_state(rig, side):
    """Current foot rotation (relative to rest), ankle and lowest sole point."""
    pb = rig.arm.pose.bones['foot.'+side]
    delta = pb.matrix.to_quaternion() @ rig.rest_q['foot.'+side].inverted()
    ankle = pb.matrix.translation.copy()
    index = min(range(len(rig.supports[side]['vectors'])), key=lambda i: (delta @ rig.supports[side]['vectors'][i]).z)
    return delta, ankle, index


def solve(rig, at, duration, fps, rest_src, scale, contact_fix):
    """Free retarget, then a rolling no-slip contact plan, then pelvis drops.

    Stance (source contact flags): the sole point in contact keeps the ground
    position it had at the previous frame, so the foot rolls heel -> toe
    without slipping, and that point sits at z = 0. Lift-off blends back to
    the free trajectory over three frames."""
    count = int(math.floor(duration*fps+1e-6))+1
    samples = [at(k/fps) for k in range(count)]
    contacts = [smp[2] for smp in samples]

    def free_pass(base):
        frames = []
        for smp in samples:
            res = pose_frame(rig, smp, rest_src, scale, None, base)
            frame = {}
            for side, r in res.items():
                delta, ankle, index = foot_state(rig, side)
                frame[side] = {'ankle': ankle, 'delta': delta, 'contact_index': index,
                               'sole': ankle+delta @ rig.supports[side]['vectors'][index],
                               'reach_error_m': r['reach_error_m']}
            frames.append(frame)
        return frames

    # The source's rest pose holds its feet differently from walking stance,
    # so its rest pelvis height does not put Inez's soles on the floor. The
    # median stance sole height of a first pass is a constant pelvis offset.
    free = free_pass(0.0)
    heights = [free[f][side]['sole'].z for f in range(count) for k, side in enumerate('LR')
               if contacts[f] is not None and contacts[f][k]]
    base = float(np.median(heights)) if heights else 0.0
    if abs(base) > 1e-4:
        free = free_pass(base)
    plan = [dict() for _ in range(count)]
    if contact_fix and contacts[0] is not None:
        for k, side in enumerate('LR'):
            vectors = rig.supports[side]['vectors']
            column = [bool(c[k]) for c in contacts]
            i = 0
            while i < count:
                if not column[i]:
                    i += 1
                    continue
                start = i
                while i < count and column[i]:
                    i += 1
                # Anchor at mid-stance (foot flat) and roll outward both ways,
                # so the correction is split between touchdown and lift-off.
                mid = (start+i-1)//2
                sole = free[mid][side]['sole']
                plan[mid][side] = Vector((sole.x, sole.y, 0.0))-free[mid][side]['delta'] @ vectors[free[mid][side]['contact_index']]
                # Between frames f-1 and f the point that must not move is the
                # one in contact at the later frame f (forward and backward).
                for order in (range(mid+1, i), range(mid-1, start-1, -1)):
                    for f in order:
                        g = f-1 if f > mid else f+1
                        later = f if f > mid else g
                        index = free[later][side]['contact_index']
                        ground = plan[g][side]+free[g][side]['delta'] @ vectors[index]
                        if f > mid:
                            ground.z = 0.0
                        plan[f][side] = ground-free[f][side]['delta'] @ vectors[index]
                        if f < mid:
                            # Keep the earlier frame's own contact point on the floor.
                            low = plan[f][side]+free[f][side]['delta'] @ vectors[free[f][side]['contact_index']]
                            plan[f][side].z -= low.z
                for b in range(1, 4):
                    f = i-1+b
                    if f < count and not column[f]:
                        w = 1-b/4
                        plan[f][side] = plan[i-1][side]*w+free[f][side]['ankle']*(1-w)
                # Touchdown: blend from the free trajectory over three frames.
                for b in range(1, 4):
                    f = start-b
                    if f >= 0 and not column[f] and side not in plan[f]:
                        w = 1-b/4
                        plan[f][side] = plan[start][side]*w+free[f][side]['ankle']*(1-w)
    # Swing (and lift-off blends): keep the lowest sole point 3 mm above the
    # floor; the scaled source clearance is for thin shoes, Inez wears 4.6 cm
    # platform boots.
    # Swing targets become absolute (from the free solve) so lowering the
    # pelvis for a planted leg does not push the swinging boot into the floor.
    if contact_fix:
        for f in range(count):
            for k, side in enumerate('LR'):
                if contacts[f] is not None and contacts[f][k]:
                    continue
                ankle = plan[f].get(side, free[f][side]['ankle']).copy()
                height = free[f][side]['ankle'].z-free[f][side]['sole'].z
                if ankle.z-height < 0.003:
                    ankle.z = 0.003+height
                plan[f][side] = ankle
    drops = []
    for i, smp in enumerate(samples):
        drop = 0.0
        if plan[i]:
            res = pose_frame(rig, smp, rest_src, scale, plan[i], base)
            for side, target in plan[i].items():
                hip = res[side]['hip']
                reach = rig.leg[side]*0.995
                horizontal = math.hypot(target.x-hip.x, target.y-hip.y)
                if horizontal < reach:
                    drop = max(drop, hip.z-(target.z+math.sqrt(reach*reach-horizontal*horizontal)))
        drops.append(drop)
    # Smooth the pelvis drop: a 5-frame running maximum (keeps every planted
    # leg reachable) followed by a 5-frame mean (no bobbing steps).
    if drops:
        n = len(drops)
        peak = [max(drops[max(0, j-2):j+3]) for j in range(n)]
        drops = [sum(peak[max(0, j-2):j+3])/len(peak[max(0, j-2):j+3]) for j in range(n)]
    drops = [base+d for d in drops]
    return samples, plan, drops, free, contacts, base


def bake(rig, name, samples, plan, drops, rest_src, scale, fps, root_motion):
    arm = rig.arm
    arm.animation_data_create()
    old = bpy.data.actions.get(name)
    if old:
        bpy.data.actions.remove(old)
    action = bpy.data.actions.new(name)
    action.use_fake_user = True
    arm.animation_data.action = action
    bpy.context.scene.render.fps = int(round(fps))
    names = hair_chain(arm)
    driven = ['root', *SPINE, *NECK]
    for side in 'LR':
        driven += [f'{p}.{side}' for p in ('upperleg01', 'lowerleg01', 'foot', 'upperarm01', 'lowerarm01', 'wrist')]
        driven += [f'finger{f}-{g}.{side}' for f in range(2, 6) for g in range(1, 4)]
    dt = 1.0/fps
    state = None
    for _ in range(int(0.5*fps)):
        pose_frame(rig, samples[0], rest_src, scale, plan[0] or None, drops[0])
        state = simulate_hair(arm, names, state, dt)
    roots, soles, reach, feet, joints = [], {'L': [], 'R': []}, [], {'L': [], 'R': []}, []
    for i, smp in enumerate(samples):
        frame = i+1
        bpy.context.scene.frame_set(frame)
        res = pose_frame(rig, smp, rest_src, scale, plan[i] or None, drops[i])
        state = simulate_hair(arm, names, state, dt)
        roots.append(arm.pose.bones['root'].matrix.translation.copy())
        joints.append({n: arm.pose.bones[n].matrix.translation.copy() for n in GAIT_BONES})
        for side in 'LR':
            delta, ankle, index = foot_state(rig, side)
            feet[side].append((delta, ankle, index))
            soles[side].append(ankle+delta @ rig.supports[side]['vectors'][index])
        reach.append(max(r['reach_error_m'] for r in res.values()))
        for bone in driven+names:
            pb = arm.pose.bones[bone]
            pb.keyframe_insert(data_path='rotation_quaternion', frame=frame, group=bone)
            if bone == 'root':
                pb.keyframe_insert(data_path='location', frame=frame, group=bone)
    # In-place: remove the straight-line average root velocity from the root
    # location keys (vertical motion kept).
    travel = (roots[-1]-roots[0])
    duration = (len(samples)-1)/fps
    velocity = Vector((travel.x, travel.y, 0))/duration if duration > 0 else Vector()
    if not root_motion:
        root = arm.pose.bones['root']
        to_local = root.bone.matrix_local.to_3x3().inverted()
        curves = [c for c in action.fcurves if c.data_path == 'pose.bones["root"].location']
        for curve in curves:
            for point in curve.keyframe_points:
                t = (point.co.x-1)/fps
                shift = to_local @ (velocity*t)
                point.co.y -= shift[curve.array_index]
    for curve in action.fcurves:
        for point in curve.keyframe_points:
            point.interpolation = 'LINEAR'
    action['inez_generated_animation'] = True
    action['in_place'] = not root_motion
    return action, {'roots': roots, 'soles': soles, 'feet': feet, 'joints': joints, 'reach_error_m': reach, 'velocity': velocity,
                    'driven_bones': driven+names}


def stance_slip(feet, supports, contacts):
    """Slip of the sole point in contact during each stance phase.

    Per frame f the contact point is the lowest support point i_f; its slip
    is the horizontal displacement of that same point between f-1 and f
    (rolling heel-to-toe has zero slip). Reported per phase: total and the
    largest single-frame slip, in metres (world, with root motion)."""
    out = {}
    for k, side in enumerate('LR'):
        vectors = supports[side]['vectors']
        flags = [bool(c[k]) if c is not None else False for c in contacts]
        phases, f = [], 0
        while f < len(flags):
            if not flags[f]:
                f += 1
                continue
            start = f
            while f < len(flags) and flags[f]:
                f += 1
            total, largest = 0.0, 0.0
            for g in range(start+1, f):
                (dq, ankle, index), (pdq, pankle, _) = feet[side][g], feet[side][g-1]
                now = ankle+dq @ vectors[index]
                before = pankle+pdq @ vectors[index]
                step = math.hypot(now.x-before.x, now.y-before.y)
                total += step
                largest = max(largest, step)
            if f-start >= 3:
                phases.append({'frames': [start, f-1], 'slip_total_m': total, 'slip_max_step_m': largest})
        out[side] = {'phases': phases, 'max_phase_slip_m': max((p['slip_total_m'] for p in phases), default=0.0)}
    return out


def render_previews(scene, arm, folder, frames, count):
    """Side (yaw 90) and front frames of the baked clip on the full model."""
    from scan_common import Studio
    folder.mkdir(parents=True, exist_ok=True)
    for obj in scene.objects:
        if obj.type == 'LIGHT':
            obj.hide_render = True
    studio = Studio(scene, 16, 480)
    picks = sorted({1+round(i*(frames-1)/max(count-1, 1)) for i in range(count)})
    written = []
    for frame in picks:
        scene.frame_set(frame)
        root = arm.pose.bones['root'].matrix.translation
        centre = Vector((root.x, root.y, 0.9))
        for yaw, view in ((90, 'side'), (0, 'front')):
            path = folder/f'{view}_{frame:03d}.png'
            studio.render(centre, 1.95, yaw, path)
            written.append(str(path))
    return written


def export_clip(arm, path):
    bpy.ops.object.select_all(action='DESELECT')
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    options = dict(filepath=str(path), export_format='GLB', use_selection=True, export_yup=True,
                   export_animations=True, export_animation_mode='ACTIVE_ACTIONS', export_force_sampling=True,
                   export_skins=False, export_morph=False, export_materials='NONE', export_cameras=False,
                   export_lights=False, export_extras=True, export_apply=False, export_def_bones=False,
                   export_anim_single_armature=True)
    props = bpy.ops.export_scene.gltf.get_rna_type().properties
    bpy.ops.export_scene.gltf(**{k: v for k, v in options.items() if k in props})


def main():
    args = arguments()
    HAND_MODE.update(mode=args.hand_mode, curl=args.finger_curl)
    data = isk.load(args.isk)
    check = isk.validate(data)
    if not check['passed']:
        raise SystemExit('ISK validation failed: '+json.dumps(check['errors']))
    scene = bpy.context.scene
    arm = next(o for o in scene.objects if o.type == 'ARMATURE')
    meshes = [o for o in scene.objects if o.type == 'MESH' and not o.hide_render]
    body = next(o for o in meshes if o.data.attributes.get('makehuman_source_index'))
    # Posing evaluates the depsgraph many times per frame; mesh deformation is
    # irrelevant to the solve, so armature modifiers are paused meanwhile.
    paused = []
    for obj in meshes:
        for mod in obj.modifiers:
            if mod.show_viewport:
                mod.show_viewport = False
                paused.append(mod)
    if arm.animation_data:
        arm.animation_data.action = None
    rig = Rig(arm, meshes, body)
    align = 0.0 if args.no_align_travel else travel_alignment(data)
    at, duration = sampler(data, align)
    rest_src = data['rest_positions']@np.array(Quaternion(Vector((0, 0, 1)), align).to_matrix()).T
    leg_src = np.mean([np.linalg.norm(rest_src[J('knee_'+s)]-rest_src[J('hip_'+s)]) +
                       np.linalg.norm(rest_src[J('ankle_'+s)]-rest_src[J('knee_'+s)]) for s in 'lr'])
    scale = float(np.mean(list(rig.leg.values()))/leg_src)
    samples, plan, drops, free, contacts, base = solve(rig, at, duration, args.fps, rest_src, scale, not args.no_contact_fix)
    action, baked = bake(rig, args.name, samples, plan, drops, rest_src, scale, args.fps, args.root_motion)
    for mod in paused:
        mod.show_viewport = True
    # Slip of the free (uncorrected) solve, measured the same way.
    free_feet = {side: [(f[side]['delta'], f[side]['ankle'], f[side]['contact_index']) for f in free] for side in 'LR'}
    slide_before = stance_slip(free_feet, rig.supports, contacts)
    slide_after = stance_slip(baked['feet'], rig.supports, contacts)
    lowest = min(min(p.z for p in baked['soles'][s]) for s in 'LR')
    planted_heights = [baked['soles'][side][i].z for k, side in enumerate('LR') for i, c in enumerate(contacts)
                       if c is not None and c[k]]
    # Keyed-rotation integrity.
    norms, steps = [], {}
    for curve_group in {c.data_path for c in action.fcurves if c.data_path.endswith('rotation_quaternion')}:
        curves = sorted([c for c in action.fcurves if c.data_path == curve_group], key=lambda c: c.array_index)
        qs = np.array([[c.evaluate(f) for c in curves] for f in range(1, len(samples)+1)])
        norms.extend(np.linalg.norm(qs, axis=1).tolist())
        dots = np.abs((qs[1:]*qs[:-1]).sum(1)/np.maximum(np.linalg.norm(qs[1:], axis=1)*np.linalg.norm(qs[:-1], axis=1), 1e-9))
        steps[curve_group.split('"')[1]] = float(np.degrees(2*np.arccos(np.clip(dots, 0, 1))).max()) if len(dots) else 0.0
    source_root = [s[0][J('pelvis')] for s in samples]
    source_path = sum(np.linalg.norm(np.array(source_root[i+1][:2])-np.array(source_root[i][:2])) for i in range(len(samples)-1))
    target_path = sum((baked['roots'][i+1]-baked['roots'][i]).to_2d().length for i in range(len(samples)-1))
    report = {
        'clip': args.name, 'source': data['meta']['source'], 'source_licence': data['meta']['licence'],
        'terra_generated': bool(data['meta']['source'].get('terra', False)),
        'isk_validation': {k: check[k] for k in ('passed', 'frames', 'frequency_hz', 'errors', 'warnings')},
        'hand_mode': args.hand_mode, 'finger_curl_deg': args.finger_curl,
        'fps': args.fps, 'output_frames': len(samples), 'duration_s': (len(samples)-1)/args.fps,
        'source_frames': int(data['meta']['frames']), 'source_duration_s': (int(data['meta']['frames'])-1)/data['meta']['frequency_hz'],
        'travel_alignment_deg': math.degrees(align), 'leg_scale': scale,
        'root_motion': 'kept' if args.root_motion else 'removed (in place)',
        'matching_speed_m_s': baked['velocity'].length, 'average_velocity_m_s': list(baked['velocity']),
        'root_path_m': {'source': float(source_path), 'source_scaled': float(source_path*scale), 'inez': float(target_path)},
        'contact_fix': not args.no_contact_fix, 'pelvis_height_offset_m': base,
        'pelvis_drop_range_m': [float(min(drops)), float(max(drops))] if drops else None,
        'ik_reach_error_max_m': float(max(baked['reach_error_m'])),
        'stance_slip_before_fix': slide_before, 'stance_slip_after_fix': slide_after,
        'lowest_sole_z_m': float(lowest),
        'planted_sole_z_range_m': [float(min(planted_heights)), float(max(planted_heights))] if planted_heights else None,
        'quaternion_norm_range': [float(min(norms)), float(max(norms))] if norms else None,
        'max_rotation_step_deg': steps, 'driven_bones': baked['driven_bones'],
        'missing_tracks': [b for b in baked['driven_bones'] if f'pose.bones["{b}"].rotation_quaternion' not in
                           {c.data_path for c in action.fcurves}],
    }
    report['frame_count_preserved'] = abs(report['duration_s']-report['source_duration_s']) <= 1.0/args.fps
    src_frames = [{'pelvis': Vector(s[0][J('pelvis')]), 'chest': Vector(s[0][J('chest')]),
                   **{f'{n}_{side}': Vector(s[0][J(n+'_'+side.lower())]) for side in 'LR' for n in ('hip', 'knee', 'ankle')}}
                  for s in samples]
    inez_frames = [{'pelvis': (j['upperleg01.L']+j['upperleg01.R'])/2, 'chest': j['neck01'],
                    **{f'{n}_{side}': j[b+'.'+side] for side in 'LR' for n, b in (('hip', 'upperleg01'), ('knee', 'lowerleg01'), ('ankle', 'foot'))}}
                   for j in baked['joints']]
    report['gait'] = {'source': gait_measures(src_frames, contacts), 'inez': gait_measures(inez_frames, contacts)}
    report['checks'] = {
        'isk_valid': check['passed'],
        'all_driven_bones_keyed': not report['missing_tracks'],
        'unit_quaternions': bool(norms) and max(abs(n-1) for n in norms) < 1e-3,
        'no_rotation_step_over_30deg': max(steps.values()) < 30.0,
        'frame_count_preserved': report['frame_count_preserved'],
        'ik_reach_error_under_5mm': report['ik_reach_error_max_m'] < 0.005,
        'stance_slip_under_10mm_per_phase': all(v['max_phase_slip_m'] < 0.010 for v in slide_after.values()) if not args.no_contact_fix else None,
        'no_ground_penetration_over_5mm': report['lowest_sole_z_m'] > -0.005,
    }
    out = Path(args.output_glb)
    out.parent.mkdir(parents=True, exist_ok=True)
    arm.animation_data.action = action
    if args.preview_dir:
        report['previews'] = render_previews(scene, arm, Path(args.preview_dir), len(samples), args.preview_frames)
    export_clip(arm, out)
    report['output_glb'] = str(out)
    report['output_bytes'] = out.stat().st_size
    if args.trajectory_json:
        step = max(1, int(round(args.fps/15)))
        traj = {'clip': args.name, 'fps': args.fps, 'every': step, 'frames': len(samples),
                'joints': list(isk.JOINTS), 'leg_scale': scale, 'in_place': not args.root_motion,
                'average_velocity_m_s': list(baked['velocity']),
                'source_joints': [[[round(float(v), 4) for v in (Vector(p)*scale)] for p in s[0]] for s in samples[::step]],
                'inez_root': [[round(float(v), 4) for v in r] for r in baked['roots'][::step]],
                'soles': {side: [[round(float(v), 4) for v in p] for p in baked['soles'][side][::step]] for side in 'LR'},
                'contacts': [[bool(c[0]), bool(c[1])] if c is not None else [False, False] for c in contacts[::step]]}
        Path(args.trajectory_json).write_text(json.dumps(traj)+'\n')
    if args.save_blend:
        for obj in list(scene.objects):
            if obj.type != 'ARMATURE':
                bpy.data.objects.remove(obj, do_unlink=True)
        for act in list(bpy.data.actions):
            if act != action:
                bpy.data.actions.remove(act)
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(args.save_blend).resolve()), compress=True)
        report['blend'] = args.save_blend
    Path(args.report).write_text(json.dumps(report, indent=2, default=lambda v: list(v))+'\n')
    print('RETARGET '+json.dumps({k: report[k] for k in ('clip', 'output_frames', 'matching_speed_m_s', 'ik_reach_error_max_m',
                                                          'lowest_sole_z_m', 'checks')}, default=list))


if __name__ == '__main__':
    main()
