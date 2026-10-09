"""Bake editable Inez animation onto the licensed, fitted source rig.

Prepared before the head gate. Do not run until root explicitly enables rig
work and supplies the actual dressed source .blend. The --root-enabled flag
records that handoff; it does not grant artistic approval to a model.

blender -b -t 4 --python tools/inez/animation_build.py -- \
  --root-enabled --source SOURCE.blend --output-blend ANIMATED.blend \
  --output-glb ANIMATED.glb --report animation_manifest.json

Creates real skeletal Idle/Walk/Run actions, optional eyelid Blink action,
mesh expression/viseme/blink controls, and weighted ponytail secondary bones.
The original model is never overwritten.
"""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector
from mathutils.kdtree import KDTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from animation_motion import arm_cycle, clamp, foot_cycle, gait_specs


EXPRESSION_NAMES = ('Neutral', 'Confused', 'Suspicious', 'SubtleFear',
                    'IntenseFear', 'Anger', 'Exhaustion')
VISEME_NAMES = ('Viseme_AA', 'Viseme_EE', 'Viseme_OH', 'Viseme_MM', 'Viseme_FV')
BLINK_NAMES = ('Blink_L', 'Blink_R')
CONTROL_NAMES = EXPRESSION_NAMES + VISEME_NAMES + BLINK_NAMES
X, Y, Z = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root-enabled', action='store_true')
    parser.add_argument('--source', required=True)
    parser.add_argument('--output-blend', required=True)
    parser.add_argument('--output-glb', required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--fps', type=int, default=24)
    return parser.parse_args(sys.argv[sys.argv.index('--')+1:])


def update():
    bpy.context.view_layer.update()


def reset_pose(arm):
    for pb in arm.pose.bones:
        pb.rotation_mode = 'QUATERNION'
        pb.rotation_quaternion = Quaternion()
        pb.location = (0, 0, 0)
        pb.scale = (1, 1, 1)
    update()


def base_matrix(pb):
    if pb.parent:
        return pb.parent.matrix @ pb.parent.bone.matrix_local.inverted() @ pb.bone.matrix_local
    return pb.bone.matrix_local.copy()


def world_delta(pb, delta):
    """Rotate around a world/armature-space axis, retaining parent motion."""
    base = base_matrix(pb).to_quaternion()
    pb.rotation_quaternion = base.inverted() @ delta @ base


def absolute_world_rotation(pb, rotation):
    pb.rotation_quaternion = base_matrix(pb).to_quaternion().inverted() @ rotation


def world_translation(pb, offset):
    pb.location = base_matrix(pb).to_3x3().inverted() @ Vector(offset)


def aim_chain(arm, start, endpoint, target):
    """Rigidly rotate a split/twist chain by its full joint-to-joint vector.

    MakeHuman upperleg01/02 and upperarm01/02 are not equal straight halves.
    Aiming only the first bone's Y axis produces a wrong knee/elbow position.
    This uses the distal joint's actual bind position while leaving twist
    intermediates at their inherited local transform.
    """
    pb = arm.pose.bones[start]
    base = base_matrix(pb)
    rest = pb.bone.matrix_local
    rest_endpoint = arm.data.bones[endpoint].matrix_local.translation
    reference = rest.to_quaternion().inverted() @ (rest_endpoint-rest.translation)
    expected = base.to_quaternion() @ reference
    desired = Vector(target)-base.translation
    if desired.length > 1e-8 and expected.length > 1e-8:
        delta = expected.rotation_difference(desired)
        q = base.to_quaternion()
        pb.rotation_quaternion = q.inverted() @ delta @ q
    update()


def aim_bone(pb, direction):
    base = base_matrix(pb).to_quaternion()
    expected = base @ Y
    delta = expected.rotation_difference(Vector(direction).normalized())
    pb.rotation_quaternion = base.inverted() @ delta @ base
    update()


def relax_hand(arm, side, direction):
    """Set the palm toward the torso and curl around an anatomical plane.

    Licensed bone rolls differ between sides, so a guessed local-X bend would
    splay some fingers sideways. The wrist/index/pinky plane supplies the real
    bend normal, and the current finger direction supplies each rotation axis.
    """
    sign = 1 if side == 'L' else -1
    wrist = arm.pose.bones['wrist.'+side]
    axis = Vector(direction).normalized()
    index = arm.pose.bones['finger2-1.'+side].matrix.translation-wrist.matrix.translation
    pinky = arm.pose.bones['finger5-1.'+side].matrix.translation-wrist.matrix.translation
    palm = index.cross(pinky)
    inward = Vector((-sign, 0, 0))
    desired = inward-axis*inward.dot(axis)
    if palm.length > 1e-8 and desired.length > 1e-8:
        palm.normalize()
        if palm.dot(inward) < 0:
            palm.negate()
        desired.normalize()
        angle = math.atan2(palm.cross(desired).dot(axis), clamp(palm.dot(desired), -1, 1))
        absolute_world_rotation(wrist, Quaternion(axis, angle) @ wrist.matrix.to_quaternion())
        update()
    palm = desired.normalized() if desired.length > 1e-8 else inward
    for finger in range(2, 6):
        for segment in range(1, 4):
            name = 'finger%d-%d.%s' % (finger, segment, side)
            if name not in arm.pose.bones:
                continue
            pb = arm.pose.bones[name]
            current_direction = base_matrix(pb).to_quaternion() @ Y
            bend_axis = current_direction.cross(palm)
            if bend_axis.length > 1e-8:
                world_delta(pb, Quaternion(bend_axis.normalized(), math.radians((4, 8, 5)[segment-1])))
                update()


def two_bone_joint(hip, ankle, thigh_length, shin_length, pole):
    vector = ankle-hip
    distance = vector.length
    direction = vector.normalized()
    safe_distance = max(abs(thigh_length-shin_length)+1e-5,
                        min(distance, (thigh_length+shin_length)*0.9995))
    projected = (thigh_length**2-shin_length**2+safe_distance**2)/(2*safe_distance)
    height = math.sqrt(max(0.0, thigh_length**2-projected**2))
    pole_direction = Vector(pole)-direction*Vector(pole).dot(direction)
    if pole_direction.length < 1e-5:
        pole_direction = X-direction*X.dot(direction)
    joint = hip+direction*projected+pole_direction.normalized()*height
    reached = hip+direction*safe_distance
    return joint, reached, abs(distance-safe_distance)


def weight_maps(obj, arm):
    names = {vg.index: vg.name for vg in obj.vertex_groups if vg.name in arm.data.bones}
    result = defaultdict(dict)
    for vertex in obj.data.vertices:
        total = sum(g.weight for g in vertex.groups if g.group in names)
        if total < 1e-9:
            continue
        for group in vertex.groups:
            if group.group in names:
                result[names[group.group]][vertex.index] = group.weight/total
    return dict(result)


def descendant_names(arm, name):
    if name not in arm.data.bones:
        return set()
    return {name} | {b.name for b in arm.data.bones[name].children_recursive}


def mask(weights, bones, count):
    values = [0.0]*count
    for bone in bones:
        for index, weight in weights.get(bone, {}).items():
            values[index] += weight
    return [min(1.0, value) for value in values]


def sum_delta(*items):
    return [sum((item[i] for item in items), Vector()) for i in range(len(items[0]))]


def scaled_delta(item, factor):
    return [v*factor for v in item]


def face_deltas(obj, arm, scale):
    """Conservative fitted-coordinate shape deltas from real skin regions.

    Expressions do not alter the Basis or the active head-fit shape. Jaw and
    eyelid shapes are bind-space linear skinning of the actual jaw/lid bones.
    Displacements are added to Basis, so the fitted identity remains active.
    """
    count = len(obj.data.vertices)
    weights = weight_maps(obj, arm)
    to_arm = arm.matrix_world.inverted() @ obj.matrix_world
    from_arm = to_arm.inverted().to_3x3()
    basis = obj.data.shape_keys.key_blocks[0] if obj.data.shape_keys else None
    coordinates = [v.co.copy() for v in (basis.data if basis else obj.data.vertices)]
    if obj.data.shape_keys:
        for key in obj.data.shape_keys.key_blocks[1:]:
            if key.name in CONTROL_NAMES or not key.value:
                continue
            relative = key.relative_key
            for i in range(count):
                coordinates[i] += (key.data[i].co-relative.data[i].co)*key.value
    points = [to_arm @ p for p in coordinates]

    def displacement(values, vector):
        vector = from_arm @ Vector(vector)
        return [vector*value for value in values]

    def rotation_delta(bone, angle, values):
        center = arm.data.bones[bone].matrix_local.translation
        rotation = Quaternion(X, angle)
        return [from_arm @ ((rotation @ (p-center)-(p-center))*values[i])
                for i, p in enumerate(points)]

    zero = [Vector() for _ in range(count)]
    pieces = {}
    eye_center_z = sum(arm.data.bones['eye.'+side].head_local.z for side in ('L', 'R'))/2
    eye_half_span = abs(arm.data.bones['eye.L'].head_local.x)
    for side in ('L', 'R'):
        sign = 1 if side == 'L' else -1
        brow = mask(weights, descendant_names(arm, 'oculi02.'+side), count)
        # Inner and outer masks overlap smoothly rather than carving brows.
        inner = [v*clamp(1.6-abs(p.x)/max(eye_half_span, 1e-5)) for v, p in zip(brow, points)]
        outer = [v*(1.0-clamp(1.6-abs(p.x)/max(eye_half_span, 1e-5))) for v, p in zip(brow, points)]
        pieces['InnerUp_'+side] = displacement(inner, (-sign*0.0005*scale, -0.0004*scale, 0.0052*scale))
        pieces['OuterUp_'+side] = displacement(outer, (0, -0.0002*scale, 0.0038*scale))
        pieces['BrowDown_'+side] = displacement(brow, (-sign*0.0012*scale, -0.0003*scale, -0.0038*scale))
        upper = mask(weights, ('orbicularis03.'+side,), count)
        lower = mask(weights, ('orbicularis04.'+side,), count)
        upper_tail = arm.data.bones['orbicularis03.'+side].tail_local-arm.data.bones['orbicularis03.'+side].head_local
        lower_tail = arm.data.bones['orbicularis04.'+side].tail_local-arm.data.bones['orbicularis04.'+side].head_local
        upper_angle = math.atan2(upper_tail.z, -upper_tail.y)
        lower_angle = math.atan2(lower_tail.z, -lower_tail.y)
        pieces['Blink_'+side] = sum_delta(rotation_delta('orbicularis03.'+side, upper_angle, upper),
                                          rotation_delta('orbicularis04.'+side, lower_angle, lower))
        pieces['EyeWide_'+side] = sum_delta(displacement(upper, (0, 0, 0.0018*scale)),
                                            displacement(lower, (0, 0, -0.0008*scale)))
        pieces['EyeNarrow_'+side] = scaled_delta(pieces['Blink_'+side], 0.18)
    upper_lip = mask(weights, ('oris05', 'oris03.L', 'oris03.R'), count)
    lower_lip = mask(weights, ('oris01', 'oris07.L', 'oris07.R'), count)
    lips = [min(1, a+b) for a, b in zip(upper_lip, lower_lip)]
    corners = mask(weights, ('oris03.L', 'oris03.R', 'oris07.L', 'oris07.R', 'levator05.L', 'levator05.R'), count)
    cheek = mask(weights, ('risorius03.L', 'risorius03.R'), count)
    pieces['LipPress'] = sum_delta(displacement(upper_lip, (0, 0.0002*scale, -0.0008*scale)),
                                    displacement(lower_lip, (0, 0.0002*scale, 0.0010*scale)))
    pieces['CornersDown'] = displacement(corners, (0, 0, -0.0016*scale))
    pieces['CornersTense'] = [from_arm @ Vector((math.copysign(0.0015*scale, p.x)*v, 0, 0))
                             for p, v in zip(points, corners)]
    pieces['Wide'] = [from_arm @ Vector((math.copysign(0.0032*scale, p.x)*v, 0, 0))
                       for p, v in zip(points, lips)]
    pieces['Pucker'] = [from_arm @ Vector((-math.copysign(0.0040*scale, p.x)*v, -0.0012*scale*v, 0))
                         for p, v in zip(points, lips)]
    pieces['CheekTense'] = displacement(cheek, (0, -0.0008*scale, 0.0009*scale))
    jaw_mask = mask(weights, descendant_names(arm, 'jaw'), count)

    def jaw(degrees):
        return rotation_delta('jaw', math.radians(degrees), jaw_mask)

    def mix(*terms):
        return sum_delta(*[scaled_delta(pieces[n], value) for n, value in terms])

    result = {'Neutral': zero,
              'Confused': mix(('InnerUp_L', 0.8), ('OuterUp_L', 0.3), ('BrowDown_R', 0.22),
                              ('EyeNarrow_R', 0.28), ('CornersDown', 0.15)),
              'Suspicious': mix(('BrowDown_L', 0.45), ('BrowDown_R', 0.32),
                                ('EyeNarrow_L', 0.75), ('EyeNarrow_R', 0.6), ('LipPress', 0.35)),
              'SubtleFear': sum_delta(mix(('InnerUp_L', 0.48), ('InnerUp_R', 0.48),
                                         ('EyeWide_L', 0.4), ('EyeWide_R', 0.4),
                                         ('CornersTense', 0.22)), jaw(1.5)),
              'IntenseFear': sum_delta(mix(('InnerUp_L', 0.95), ('InnerUp_R', 0.95),
                                          ('OuterUp_L', 0.75), ('OuterUp_R', 0.75),
                                          ('EyeWide_L', 0.9), ('EyeWide_R', 0.9),
                                          ('CornersTense', 0.42)), jaw(7.0)),
              'Anger': mix(('BrowDown_L', 0.9), ('BrowDown_R', 0.9),
                           ('EyeNarrow_L', 0.38), ('EyeNarrow_R', 0.38),
                           ('LipPress', 0.7), ('CheekTense', 0.3)),
              'Exhaustion': mix(('BrowDown_L', 0.24), ('BrowDown_R', 0.24),
                                ('EyeNarrow_L', 1.3), ('EyeNarrow_R', 1.3), ('CornersDown', 0.55)),
              'Viseme_AA': sum_delta(jaw(15), scaled_delta(pieces['Wide'], 0.18)),
              'Viseme_EE': sum_delta(jaw(7), scaled_delta(pieces['Wide'], 0.72)),
              'Viseme_OH': sum_delta(jaw(12), scaled_delta(pieces['Pucker'], 0.85)),
              'Viseme_MM': pieces['LipPress'],
              'Viseme_FV': sum_delta(jaw(3.0), displacement(lower_lip, (0, -0.0004*scale, 0.0018*scale))),
              'Blink_L': pieces['Blink_L'], 'Blink_R': pieces['Blink_R']}
    return result


def install_shapes(obj, deltas):
    if not obj.data.shape_keys:
        obj.shape_key_add(name='Basis')
    basis = obj.data.shape_keys.key_blocks[0]
    report = {}
    for name, delta in deltas.items():
        key = obj.data.shape_keys.key_blocks.get(name) or obj.shape_key_add(name=name)
        key.relative_key = basis
        for i, d in enumerate(delta):
            key.data[i].co = basis.data[i].co+d
        key.value = 0.0
        report[name] = {'affected_vertices': sum(d.length > 1e-7 for d in delta),
                        'maximum_displacement_m': max((d.length for d in delta), default=0.0)}
    return report


def facial_shapes(body, arm, meshes, scale):
    deltas = face_deltas(body, arm, scale)
    result = {body.name: install_shapes(body, deltas)}
    tree = KDTree(len(body.data.vertices))
    fitted = [v.co.copy() for v in body.data.shape_keys.key_blocks[0].data]
    for key in body.data.shape_keys.key_blocks[1:]:
        if key.name not in CONTROL_NAMES and key.value:
            for i in range(len(fitted)):
                fitted[i] += (key.data[i].co-key.relative_key.data[i].co)*key.value
    for i, p in enumerate(fitted):
        tree.insert(body.matrix_world @ p, i)
    tree.balance()
    for obj in meshes:
        if obj == body:
            continue
        overlay = any(token in obj.name.lower() for token in ('brow', 'lash', 'tearline'))
        weights = weight_maps(obj, arm)
        jaw_geometry = any(n in weights for n in descendant_names(arm, 'jaw'))
        if overlay:
            local_from_body = obj.matrix_world.inverted().to_3x3() @ body.matrix_world.to_3x3()
            mapped = {n: [] for n in CONTROL_NAMES}
            distant = 0
            for vertex in obj.data.vertices:
                _, index, distance = tree.find(obj.matrix_world @ vertex.co)
                if distance > 0.024*scale:
                    distant += 1
                for name in CONTROL_NAMES:
                    mapped[name].append(local_from_body @ deltas[name][index] if distance < 0.024*scale else Vector())
            result[obj.name] = install_shapes(obj, mapped)
            result[obj.name]['mapping_vertices_beyond_24mm'] = distant
        elif jaw_geometry:
            result[obj.name] = install_shapes(obj, face_deltas(obj, arm, scale))
    return result


def add_ponytail(arm, meshes):
    hair = [obj for obj in meshes if 'ponytail' in obj.name.lower()]
    if not hair:
        return {'status': 'no ponytail mesh available', 'bones': []}
    points = [arm.matrix_world.inverted() @ obj.matrix_world @ v.co
              for obj in hair for v in obj.data.vertices]
    top, bottom = max(p.z for p in points), min(p.z for p in points)
    center_x = sum(p.x for p in points)/len(points)
    center_y = sum(p.y for p in points)/len(points)
    top -= (top-bottom)*0.06
    span = max(0.06, top-bottom)
    bpy.ops.object.select_all(action='DESELECT')
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    for i in range(3):
        name = 'hair.%02d' % (i+1)
        bone = arm.data.edit_bones.get(name) or arm.data.edit_bones.new(name)
        bone.head = (center_x, center_y-0.012, top-span*i/3)
        bone.tail = (center_x, center_y+0.010, top-span*(i+1)/3)
        bone.parent = arm.data.edit_bones['head' if i == 0 else 'hair.%02d' % i]
        bone.use_connect = i > 0
        bone.use_deform = True
    bpy.ops.object.mode_set(mode='OBJECT')
    for obj in hair:
        obj.vertex_groups.clear()
        groups = {name: obj.vertex_groups.new(name=name) for name in ('head', 'hair.01', 'hair.02', 'hair.03')}
        to_arm = arm.matrix_world.inverted() @ obj.matrix_world
        for vertex in obj.data.vertices:
            t = clamp((top-(to_arm @ vertex.co).z)/span)
            head_weight = max(0.0, 1.0-t/0.12)*0.8
            q = clamp(t*3-0.5, 0.0, 2.0)
            left, right = min(2, int(math.floor(q))), min(2, int(math.ceil(q)))
            ratio = q-left
            values = defaultdict(float)
            values['head'] = head_weight
            values['hair.%02d' % (left+1)] += (1.0-ratio)*(1.0-head_weight)
            values['hair.%02d' % (right+1)] += ratio*(1.0-head_weight)
            for name, weight in values.items():
                if weight > 1e-7:
                    groups[name].add([vertex.index], weight, 'REPLACE')
        modifier = next((m for m in obj.modifiers if m.type == 'ARMATURE'), None)
        if not modifier:
            modifier = obj.modifiers.new('Ponytail_Skin', 'ARMATURE')
        modifier.object = arm
        obj.parent = arm
    return {'status': 'three deforming bones with normalized longitudinal weights',
            'bones': ['hair.01', 'hair.02', 'hair.03'], 'meshes': [o.name for o in hair],
            'span_m': span}


def boot_vectors(arm, meshes, body):
    result = {}
    for side in ('L', 'R'):
        foot = arm.data.bones['foot.'+side]
        matching = [o for o in meshes if 'boot' in o.name.lower()
                    and o.vertex_groups.get('foot.'+side)]
        points = []
        for obj in matching:
            transform = arm.matrix_world.inverted() @ obj.matrix_world
            points.extend(transform @ v.co-foot.head_local for v in obj.data.vertices)
        if not points:
            weights = weight_maps(body, arm)
            indices = mask(weights, descendant_names(arm, 'foot.'+side), len(body.data.vertices))
            transform = arm.matrix_world.inverted() @ body.matrix_world
            points = [transform @ v.co-foot.head_local for v, w in zip(body.data.vertices, indices) if w > 0.5]
        if not points:
            raise RuntimeError('No foot/boot support vertices found for '+side)
        result[side] = {'vectors': points, 'meshes': [o.name for o in matching],
                        'neutral_ankle_height': -min(p.z for p in points)}
    return result


def rig_lengths(arm):
    result = {}
    for side in ('L', 'R'):
        names = ['upperleg01.'+side, 'lowerleg01.'+side, 'foot.'+side,
                 'upperarm01.'+side, 'lowerarm01.'+side, 'wrist.'+side]
        points = [arm.data.bones[n].head_local.copy() for n in names]
        result[side] = {'thigh': (points[1]-points[0]).length,
                        'shin': (points[2]-points[1]).length,
                        'upper_arm': (points[4]-points[3]).length,
                        'forearm': (points[5]-points[4]).length}
    return result


def root_drop(gait, arm, supports, lengths):
    if gait.name == 'Idle':
        return -0.012*gait.scale
    travel = max(abs(foot_cycle(gait, i/400)['y']) for i in range(400))
    drops = []
    for side in ('L', 'R'):
        hip = arm.data.bones['upperleg01.'+side].head_local
        foot = arm.data.bones['foot.'+side].head_local
        maximum_reach = (lengths[side]['thigh']+lengths[side]['shin'])*0.992
        y_distance = travel+abs(foot.y-hip.y)
        target_z = math.sqrt(max(0.03, maximum_reach**2-y_distance**2))
        vertical = hip.z-supports[side]['neutral_ankle_height']
        drops.append(target_z-vertical)
    return min(0.0, min(drops))-0.006*gait.scale


def pose_gait(arm, gait, phase, supports, lengths, drop):
    reset_pose(arm)
    p = phase % 1.0
    idle = gait.name == 'Idle'
    bob = gait.vertical_bob*(math.sin(2*math.pi*p)**2 if gait.name == 'Walk'
                             else (0.5+0.5*math.cos(4*math.pi*(p-0.46))))
    if idle:
        bob = gait.vertical_bob*math.sin(2*math.pi*p)
    root = arm.pose.bones['root']
    yaw = math.radians(0.6 if idle else 2.5)*math.sin(2*math.pi*p)
    roll = math.radians(0.4 if idle else 1.1)*math.sin(2*math.pi*p)
    lean = math.radians(gait.forward_lean_deg)
    world_delta(root, Quaternion(Z, yaw) @ Quaternion(Y, roll) @ Quaternion(X, lean))
    world_translation(root, (gait.lateral_sway*math.sin(2*math.pi*p), 0, drop+bob))
    update()
    world_delta(arm.pose.bones['spine03'], Quaternion(Z, -yaw*0.55))
    world_delta(arm.pose.bones['spine01'], Quaternion(Z, -yaw*0.35) @ Quaternion(X, math.radians(0.35)*math.sin(2*math.pi*p)))
    update()
    # Most head stabilization lives in the neck, avoiding a stiff torso/head.
    world_delta(arm.pose.bones['neck01'], Quaternion(X, -lean*0.3))
    update()
    world_delta(arm.pose.bones['head'], Quaternion(Z, -yaw*0.2) @ Quaternion(X, math.radians(0.3)*math.sin(2*math.pi*p)))
    update()
    feet = {}
    for side in ('L', 'R'):
        sign = 1 if side == 'L' else -1
        cycle = foot_cycle(gait, p+(0 if side == 'L' else 0.5))
        rest_hip = arm.data.bones['upperleg01.'+side].head_local
        rest_foot = arm.data.bones['foot.'+side].head_local
        foot_delta = Quaternion(Z, math.radians(sign*2.5)) @ Quaternion(X, cycle['pitch'])
        ankle_z = -min((foot_delta @ v).z for v in supports[side]['vectors'])+cycle['lift']
        target = Vector((rest_hip.x*1.02, rest_foot.y+cycle['y'], ankle_z))
        hip = base_matrix(arm.pose.bones['upperleg01.'+side]).translation
        joint, reached, reach_error = two_bone_joint(hip, target, lengths[side]['thigh'], lengths[side]['shin'],
                                                     (sign*0.025, -1.0, 0.04))
        aim_chain(arm, 'upperleg01.'+side, 'lowerleg01.'+side, joint)
        aim_chain(arm, 'lowerleg01.'+side, 'foot.'+side, reached)
        absolute_world_rotation(arm.pose.bones['foot.'+side], foot_delta @ arm.data.bones['foot.'+side].matrix_local.to_quaternion())
        update()
        feet[side] = dict(cycle, ankle_target=list(target), knee_target=list(joint), unreachable_error_m=reach_error)
        upper, lower = arm_cycle(gait, p, side)
        upper_direction = Vector((sign*0.15, math.sin(upper), -math.cos(upper))).normalized()
        elbow = base_matrix(arm.pose.bones['upperarm01.'+side]).translation+upper_direction*lengths[side]['upper_arm']
        aim_chain(arm, 'upperarm01.'+side, 'lowerarm01.'+side, elbow)
        lower_direction = Vector((sign*0.10, math.sin(lower), -math.cos(lower))).normalized()
        wrist = base_matrix(arm.pose.bones['lowerarm01.'+side]).translation+lower_direction*lengths[side]['forearm']
        aim_chain(arm, 'lowerarm01.'+side, 'wrist.'+side, wrist)
        aim_bone(arm.pose.bones['wrist.'+side], lower_direction)
        relax_hand(arm, side, lower_direction)
    for i in range(1, 4):
        name = 'hair.%02d' % i
        if name in arm.pose.bones:
            amplitude = math.radians((0.7 if idle else 2.8 if gait.name == 'Walk' else 5.5)*(0.65+i*0.2))
            world_delta(arm.pose.bones[name], Quaternion(X, amplitude*math.sin(2*math.pi*p-i*0.55))
                        @ Quaternion(Z, amplitude*0.3*math.sin(2*math.pi*p-i*0.9)))
            update()
    # Actual eye pivots, a tiny changing gaze. The viewer can override after Mixer.update.
    head_delta = arm.pose.bones['head'].matrix.to_quaternion() @ arm.data.bones['head'].matrix_local.to_quaternion().inverted()
    for side in ('L', 'R'):
        angle = math.radians(1.1 if idle else 0.35)*math.sin(2*math.pi*p)
        world_delta(arm.pose.bones['eye.'+side], Quaternion(head_delta @ Z, angle))
    update()
    return feet


def bake_actions(arm, specs, supports, lengths, fps):
    arm.animation_data_create()
    driven = ['root', 'spine03', 'spine01', 'neck01', 'head', 'eye.L', 'eye.R']
    for side in ('L', 'R'):
        driven += [prefix+'.'+side for prefix in ('upperleg01', 'lowerleg01', 'foot', 'upperarm01', 'lowerarm01', 'wrist')]
        driven += ['finger%d-%d.%s' % (finger, segment, side) for finger in range(2, 6) for segment in range(1, 4)]
    driven += ['hair.%02d' % i for i in range(1, 4) if 'hair.%02d' % i in arm.pose.bones]
    report = {}
    for name, gait in specs.items():
        existing = bpy.data.actions.get(name)
        if existing and existing.get('inez_generated_animation'):
            bpy.data.actions.remove(existing)
        action = bpy.data.actions.new(name)
        action.use_fake_user = True
        action['inez_generated_animation'] = True
        action['in_place'] = True
        arm.animation_data.action = action
        count = max(2, round(gait.duration*fps))
        duration = count/fps
        drop = root_drop(gait, arm, supports, lengths)
        maximum_reach_error = 0.0
        for i in range(count+1):
            frame = i+1
            bpy.context.scene.frame_set(frame)
            feet = pose_gait(arm, gait, i/count, supports, lengths, drop)
            maximum_reach_error = max(maximum_reach_error, *(f['unreachable_error_m'] for f in feet.values()))
            for bone in driven:
                pb = arm.pose.bones[bone]
                pb.keyframe_insert(data_path='rotation_quaternion', frame=frame, group=bone)
                if bone == 'root':
                    pb.keyframe_insert(data_path='location', frame=frame, group=bone)
        for curve in action.fcurves:
            for point in curve.keyframe_points:
                point.interpolation = 'LINEAR'
        report[name] = {'duration_s': duration, 'sample_count': count+1, 'frame_range': [1, count+1],
                        'stance_fraction': gait.stance_fraction, 'stride_m': gait.stride,
                        'matching_viewer_speed_m_s': 0.0 if name == 'Idle' else gait.stride/(duration*gait.stance_fraction),
                        'maximum_ik_reach_error_m': maximum_reach_error, 'root_drop_m': drop,
                        'root_motion': False, 'driven_bones': driven}
    # A separate real lid-bone clip also permits an additive blink overlay.
    action = bpy.data.actions.new('Blink')
    action.use_fake_user = True
    action['inez_generated_animation'] = True
    arm.animation_data.action = action
    reset_pose(arm)
    for frame, progress in ((1, 0.0), (2, 0.55), (3, 1.0), (4, 0.70), (6, 0.0)):
        for side in ('L', 'R'):
            for prefix in ('orbicularis03', 'orbicularis04'):
                pb = arm.pose.bones[prefix+'.'+side]
                vector = pb.bone.tail_local-pb.bone.head_local
                angle = math.atan2(vector.z, -vector.y)*progress
                world_delta(pb, Quaternion(X, angle))
                pb.keyframe_insert(data_path='rotation_quaternion', frame=frame, group=pb.name)
    for curve in action.fcurves:
        for point in curve.keyframe_points:
            point.interpolation = 'LINEAR'
    report['Blink'] = {'duration_s': 5/fps, 'frame_range': [1, 6],
                       'driven_bones': ['orbicularis03.L', 'orbicularis03.R', 'orbicularis04.L', 'orbicularis04.R'],
                       'use': 'optional additive/one-shot; do not combine with Blink morph at the same time'}
    arm.animation_data.action = bpy.data.actions['Idle']
    bpy.context.scene.frame_set(1)
    return report


def skin_audit(meshes, arm):
    result = {}
    for obj in meshes:
        modifier = next((m for m in obj.modifiers if m.type == 'ARMATURE' and m.object == arm), None)
        if not modifier:
            result[obj.name] = {'skinned': False}
            continue
        names = {vg.index: vg.name for vg in obj.vertex_groups}
        totals = [sum(g.weight for g in v.groups if names.get(g.group) in arm.data.bones) for v in obj.data.vertices]
        bad = [i for i, total in enumerate(totals) if abs(total-1.0) > 0.002]
        unknown = [vg.name for vg in obj.vertex_groups if vg.name not in arm.data.bones]
        result[obj.name] = {'skinned': True, 'vertex_count': len(totals),
                            'weight_sum_range': [min(totals, default=0), max(totals, default=0)],
                            'unnormalized_or_unweighted_vertices': len(bad), 'unknown_groups': unknown}
    return result


def runtime_skin_weights(meshes, arm):
    """Make the runtime's four-influence skin explicit in the editable output.

    Three.js's standard SkinnedMesh shader consumes JOINTS_0/WEIGHTS_0 only.
    The untouched dressed source retains every normalized licensed influence.
    Pruning here makes Blender's evaluated-mesh audit use the same skin as the
    exported browser mesh instead of silently changing it during GLB export.
    Expression deltas are authored before this adaptation so their anatomical
    region masks retain the complete source face weighting.
    """
    result = {}
    for obj in meshes:
        if not any(m.type == 'ARMATURE' and m.object == arm for m in obj.modifiers):
            continue
        groups = {g.index: g for g in obj.vertex_groups if g.name in arm.data.bones}
        excess, removed_mass, zero = 0, [], 0
        for vertex in obj.data.vertices:
            values = sorted(((groups[g.group], float(g.weight)) for g in vertex.groups
                             if g.group in groups and g.weight > 1e-8),
                            key=lambda value: (-value[1], value[0].name))
            total = sum(weight for _, weight in values)
            if total < 1e-9:
                zero += 1
                continue
            kept = values[:4]
            kept_total = sum(weight for _, weight in kept)
            excess += len(values) > 4
            removed_mass.append((total-kept_total)/total)
            for group, _ in values[4:]:
                group.remove([vertex.index])
            for group, weight in kept:
                group.add([vertex.index], weight/kept_total, 'REPLACE')
        result[obj.name] = {
            'runtime_influences_per_vertex': 4,
            'vertices_with_source_influences_above_four': excess,
            'maximum_discarded_normalized_weight': max(removed_mass, default=0.0),
            'mean_discarded_normalized_weight': sum(removed_mass)/max(1, len(removed_mass)),
            'unweighted_vertices': zero,
            'original_skin_preserved_in': 'untouched source_blend',
        }
    return result


def evaluated_bounds(obj, depsgraph):
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    points = [evaluated.matrix_world @ v.co for v in mesh.vertices]
    evaluated.to_mesh_clear()
    if not points:
        return None
    return [[min(p[a] for p in points), max(p[a] for p in points)] for a in range(3)]


def deformation_audit(arm, body, meshes, specs, clips, supports):
    result = {}
    for name in ('Idle', 'Walk', 'Run'):
        arm.animation_data.action = bpy.data.actions[name]
        count = clips[name]['frame_range'][1]-1
        frames = sorted({1+round(count*i/16) for i in range(17)})
        records = []
        foot_contact_errors = []
        for frame in frames:
            bpy.context.scene.frame_set(frame)
            update()
            depsgraph = bpy.context.evaluated_depsgraph_get()
            feet = {}
            phase = (frame-1)/count
            for side in ('L', 'R'):
                objects = [o for o in meshes if o.name in supports[side]['meshes']]
                bounds = [evaluated_bounds(o, depsgraph) for o in objects]
                bounds = [b for b in bounds if b]
                minimum_z = min((b[2][0] for b in bounds), default=None)
                expected = foot_cycle(specs[name], phase+(0 if side == 'L' else 0.5))
                actual_ankle = arm.matrix_world @ arm.pose.bones['foot.'+side].matrix.translation
                actual_knee = arm.matrix_world @ arm.pose.bones['lowerleg01.'+side].matrix.translation
                feet[side] = {'minimum_boot_z_m': minimum_z, 'expected_sole_lift_m': expected['lift'],
                              'stance_contact': expected['contact'], 'ankle': list(actual_ankle), 'knee': list(actual_knee)}
                if minimum_z is not None and expected['contact']:
                    foot_contact_errors.append(abs(minimum_z))
            records.append({'frame': frame, 'phase': phase, 'body_bounds': evaluated_bounds(body, depsgraph), 'feet': feet})
        first = records[0]['feet']
        last = records[-1]['feet']
        loop_error = max((Vector(first[s]['ankle'])-Vector(last[s]['ankle'])).length for s in ('L', 'R'))
        result[name] = {'sampled_frame_count': len(records), 'loop_ankle_error_m': loop_error,
                        'maximum_stance_boot_ground_error_m': max(foot_contact_errors, default=None),
                        'sample_frames': records,
                        'clipping_review': 'Numerical support/loop check only; rendered body/clothes review still required'}
    arm.animation_data.action = bpy.data.actions['Idle']
    bpy.context.scene.frame_set(1)
    return result


def face_bone_axes(arm):
    # glTF conversion maps Blender (x,y,z) to (x,z,-y).
    convert = Matrix(((1, 0, 0), (0, 0, 1), (0, -1, 0)))
    result = {}
    for name in ('head', 'neck01', 'neck02', 'neck03', 'eye.L', 'eye.R', 'jaw'):
        matrix = arm.data.bones[name].matrix_local
        rotation = convert @ matrix.to_3x3()
        result[name] = {'gltf_bind_head': list(convert @ matrix.translation),
                        'gltf_bind_axis_x': list(rotation.col[0]),
                        'gltf_bind_axis_y': list(rotation.col[1]),
                        'gltf_bind_axis_z': list(rotation.col[2]),
                        'quaternion_local_order': 'Blender wxyz; Three.js xyzw',
                        'note': 'Compose gaze in head-relative world axes, then transform through the current eye parent'}
    return result


def export_glb(arm, meshes, output):
    bpy.ops.object.select_all(action='DESELECT')
    arm.select_set(True)
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = arm
    options = dict(filepath=str(output), export_format='GLB', use_selection=True,
                   export_yup=True, export_texcoords=True, export_normals=True,
                   export_tangents=True, export_skins=True, export_morph=True,
                   export_materials='EXPORT', export_all_influences=False,
                   export_morph_animation=False, export_animations=True,
                   export_animation_mode='ACTIONS', export_anim_single_armature=True,
                   export_cameras=False, export_lights=False, export_extras=True,
                   export_apply=False, export_force_sampling=True)
    properties = bpy.ops.export_scene.gltf.get_rna_type().properties
    options = {key: value for key, value in options.items() if key in properties}
    bpy.ops.export_scene.gltf(**options)


def main():
    args = arguments()
    if not args.root_enabled:
        raise RuntimeError('Animation execution is staged: explicit root enablement required before loading the actual model')
    source, blend, glb, report_path = map(Path, (args.source, args.output_blend, args.output_glb, args.report))
    if not source.is_file() or source.resolve() == blend.resolve():
        raise RuntimeError('Supply an existing actual source and a separate editable animated output')
    bpy.ops.wm.open_mainfile(filepath=str(source))
    arm = bpy.data.objects.get('InezRig_PROTOTYPE') or next((o for o in bpy.context.scene.objects if o.type == 'ARMATURE'), None)
    body = bpy.data.objects.get('Inez_ContinuousHumanMesh_UNAPPROVED') or next((o for o in bpy.context.scene.objects if o.type == 'MESH' and o.data.attributes.get('makehuman_source_index')), None)
    if not arm or not body or not body.data.shape_keys or any(n not in arm.data.bones for n in ('root', 'upperleg01.L', 'foot.L', 'jaw', 'eye.L', 'orbicularis03.L')):
        raise RuntimeError('Actual licensed fitted humanoid/facial skeleton and continuous body are required')
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH' and not o.hide_render]
    identity_defaults = {key.name: float(key.value)
                         for key in body.data.shape_keys.key_blocks
                         if key.name.startswith('Inez_HeadFit_')}
    reset_pose(arm)
    if arm.animation_data:
        arm.animation_data.action = None
    bpy.context.scene.render.fps = args.fps
    height = float(bpy.context.scene.get('provisional_height_m', 1.68))
    specs = gait_specs(height)
    ponytail = add_ponytail(arm, meshes)
    reset_pose(arm)
    face = facial_shapes(body, arm, meshes, height/1.68)
    runtime_weights = runtime_skin_weights(meshes, arm)
    supports = boot_vectors(arm, meshes, body)
    lengths = rig_lengths(arm)
    clips = bake_actions(arm, specs, supports, lengths, args.fps)
    weights = skin_audit(meshes, arm)
    deformation = deformation_audit(arm, body, meshes, specs, clips, supports)
    preserved_defaults = {key.name: float(key.value)
                          for key in body.data.shape_keys.key_blocks
                          if key.name.startswith('Inez_HeadFit_')}
    if preserved_defaults != identity_defaults:
        raise RuntimeError('Animation preparation changed an individual identity morph source default')
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = clips['Idle']['frame_range'][1]
    bpy.context.scene['INEZ_RIG_STAGE'] = 'Editable animation prototype; visual/browser critique required'
    arm['rig_status'] = 'Baked skeletal gait + facial morph prototype; see animation_manifest.json'
    failures = [n for n, r in weights.items() if r.get('unnormalized_or_unweighted_vertices', 0)]
    report = {'status': 'editable rig/animation prototype', 'production_approved': False,
              'source_blend': str(source), 'animated_blend': str(blend), 'animated_glb': str(glb),
              'armature': arm.name, 'body': body.name, 'bone_count': len(arm.data.bones),
              'provisional_height_m': height, 'fps': args.fps,
              'clip_info': clips, 'skin_weight_integrity': weights,
              'runtime_weight_adaptation': runtime_weights,
              'source_license': 'CC0-1.0 MakeHuman asset rig/skin; model/base-source/LICENSE.ASSETS.md',
              'weight_failures': failures, 'face_shape_deformation': face,
              'expression_morph_names': list(EXPRESSION_NAMES), 'viseme_morph_names': list(VISEME_NAMES),
              'blink_morph_names': list(BLINK_NAMES),
              'identity_morph_source_defaults': identity_defaults,
              'preserve_identity_morphs': 'Each pre-existing Inez_HeadFit_* key retains its exact individual source default; inactive revisions remain zero',
              'ponytail': ponytail, 'bone_axes': face_bone_axes(arm), 'deformation_samples': deformation,
              'limitations': ['A procedural bake needs rendered and browser critique before any quality claim.',
                             'Morph expressions are restrained extrapolations; original references provide neutral/tension cues only.',
                             'Teeth/tongue interiors, profile anatomy and ponytail interior remain reference unknowns.',
                             'Crossfades and movement need browser validation; clips are genuinely in place.']}
    for path in (blend, glb, report_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    export_glb(arm, meshes, glb)
    report['export_size_bytes'] = glb.stat().st_size
    report_path.write_text(json.dumps(report, indent=2)+'\n')
    print('INEZ_ANIMATION_MANIFEST '+json.dumps({k: report[k] for k in ('status', 'animated_blend', 'animated_glb', 'bone_count', 'weight_failures', 'export_size_bytes')}))


if __name__ == '__main__':
    main()
