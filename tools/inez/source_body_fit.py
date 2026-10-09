"""Fit the production figure's pose and proportions to Asset A (rig pose + smooth residual).

    blender -b PRODUCTION.blend --python tools/inez/source_body_fit.py -- \
        --a-keypoints a_keypoints.json --p-keypoints p_keypoints.json --fitted fitted.npz \
        --output body_fit_layer.npz --report body_fit_report.json

Both keypoint sets come from pose_register.py with identical cameras, so each
production joint target is its own rig joint moved by the keypoint
displacement between the figures (detector bias cancels where the clothing
matches). Stage 1 poses the real rig: root translation from the hips; spine
and neck aimed at the head keypoints (shoulder keypoints are biased by Asset
A's dropped-shoulder knit and are not used); upper/lower arms, hands, thighs,
shins and feet aimed segment by segment from their current joints (rigid
limbs, licensed skin weights). Stage 2 removes what a pose cannot (segment lengths,
posture offsets) with a smoothed thin-plate spline over the keypoints. The
result is stored as a post-pose identity layer per MakeHuman source vertex
(joint helpers and hidden feet included) for model_dress_v04.py
--identity-layer SourceBodyFit=FILE.
"""
import argparse
import json
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector

BODY = 'Inez_ContinuousHumanMesh_UNAPPROVED'
SIDE = {'left': 'L', 'right': 'R'}


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('--a-keypoints', required=True)
    parser.add_argument('--p-keypoints', required=True)
    parser.add_argument('--fitted', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--tps-smoothing', type=float, default=0.02)
    return parser.parse_args(sys.argv[sys.argv.index('--')+1:])


def tps_fit(src, dst, smoothing):
    """3D biharmonic spline (kernel r) with an affine part; returns an evaluator."""
    n = len(src)
    K = np.linalg.norm(src[:, None]-src[None], axis=2)+np.eye(n)*smoothing
    Pm = np.hstack((np.ones((n, 1)), src))
    A = np.zeros((n+4, n+4))
    A[:n, :n], A[:n, n:], A[n:, :n] = K, Pm, Pm.T
    b = np.zeros((n+4, 3))
    b[:n] = dst-src
    w = np.linalg.solve(A, b)

    def evaluate(points):
        out = np.empty_like(points)
        for k in range(0, len(points), 20000):
            p = points[k:k+20000]
            U = np.linalg.norm(p[:, None]-src[None], axis=2)
            out[k:k+20000] = U@w[:n]+np.hstack((np.ones((len(p), 1)), p))@w[n:]
        return out
    return evaluate


def interpolate(points, values, queries, sigma=0.025, k=16):
    """Gaussian-weighted average of the k nearest point values (no scipy in Blender)."""
    from mathutils.kdtree import KDTree
    tree = KDTree(len(points))
    for i, p in enumerate(points):
        tree.insert(p, i)
    tree.balance()
    out = np.zeros((len(queries), values.shape[1]))
    for qi, q in enumerate(queries):
        hits = tree.find_n(q, k)
        d = np.array([h[2] for h in hits])
        idx = np.array([h[1] for h in hits])
        w = np.exp(-(d/sigma)**2)+1e-12
        out[qi] = (w[:, None]*values[idx]).sum(0)/w.sum()
    return out


def main():
    args = arguments()
    A = json.loads(Path(args.a_keypoints).read_text())['keypoints']
    Pk = json.loads(Path(args.p_keypoints).read_text())['keypoints']
    disp = {n: np.array(A[n]['world'])-np.array(Pk[n]['world']) for n in A}
    fit = np.load(args.fitted)
    src_fitted, scale, ground_eff = fit['fitted'], float(fit['scale']), float(fit['ground_eff'])

    def world(p):
        return np.stack((p[:, 0]*scale, -p[:, 2]*scale, (p[:, 1]-ground_eff)*scale), axis=1)
    rest_world = world(src_fitted)
    arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
    body = bpy.data.objects[BODY]
    for obj in bpy.data.objects:
        if obj.type == 'MESH':
            for mod in obj.modifiers:
                if mod.type == 'SUBSURF':
                    mod.show_viewport = False
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')
    for pb in arm.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()

    def joint(name):
        return Vector(arm.matrix_world @ arm.pose.bones[name].head)

    def mean_disp(names):
        return Vector(np.mean([disp[n] for n in names], axis=0))
    rest_joints = {b.name: Vector(arm.matrix_world @ b.head_local) for b in arm.data.bones}
    targets = {}
    for side, s in SIDE.items():
        targets[f'upperarm01.{s}'] = rest_joints[f'upperarm01.{s}']+Vector(disp[f'{side}_shoulder'])
        targets[f'lowerarm01.{s}'] = rest_joints[f'lowerarm01.{s}']+Vector(disp[f'{side}_elbow'])
        targets[f'wrist.{s}'] = rest_joints[f'wrist.{s}']+Vector(disp[f'{side}_wrist'])
        targets[f'upperleg01.{s}'] = rest_joints[f'upperleg01.{s}']+Vector(disp[f'{side}_hip'])
        targets[f'lowerleg01.{s}'] = rest_joints[f'lowerleg01.{s}']+Vector(disp[f'{side}_knee'])
        targets[f'foot.{s}'] = rest_joints[f'foot.{s}']+Vector(disp[f'{side}_ankle'])
        targets[f'toe1-1.{s}'] = rest_joints[f'toe1-1.{s}']+Vector(disp[f'{side}_foot_index'])
    targets['root'] = rest_joints['root']+mean_disp(['left_hip', 'right_hip'])
    targets['neck01'] = rest_joints['neck01']+mean_disp(['left_shoulder', 'right_shoulder'])
    face = ['nose', 'left_eye', 'right_eye', 'left_ear', 'right_ear', 'mouth_left', 'mouth_right']
    targets['head'] = rest_joints['head']+mean_disp(face)

    KP_BONE = {'nose': 'head', 'left_eye_inner': 'head', 'left_eye': 'head', 'left_eye_outer': 'head',
               'right_eye_inner': 'head', 'right_eye': 'head', 'right_eye_outer': 'head', 'left_ear': 'head',
               'right_ear': 'head', 'mouth_left': 'head', 'mouth_right': 'head'}
    for side, s in SIDE.items():
        KP_BONE.update({f'{side}_shoulder': f'upperarm01.{s}', f'{side}_elbow': f'lowerarm01.{s}',
                        f'{side}_wrist': f'wrist.{s}', f'{side}_pinky': f'wrist.{s}', f'{side}_index': f'wrist.{s}',
                        f'{side}_thumb': f'wrist.{s}', f'{side}_hip': f'upperleg01.{s}', f'{side}_knee': f'lowerleg01.{s}',
                        f'{side}_ankle': f'foot.{s}', f'{side}_heel': f'foot.{s}', f'{side}_foot_index': f'foot.{s}'})

    def carried(name, point):
        """Where a rest-pose point attached rigidly to its bone goes under the current pose."""
        bone = arm.pose.bones[KP_BONE[name]]
        M = arm.matrix_world
        T = M @ bone.matrix @ bone.bone.matrix_local.inverted() @ M.inverted()
        return np.array(T @ Vector(point))

    def aim(bone, child, target_dir, limit=None):
        bpy.context.view_layer.update()
        pb = arm.pose.bones[bone]
        head = joint(bone)
        current = joint(child)-head
        if current.length < 1e-6 or target_dir.length < 1e-6:
            return 0.0
        q = current.normalized().rotation_difference(target_dir.normalized())
        if limit is not None and np.degrees(q.angle) > limit:
            axis, angle = q.to_axis_angle()
            from mathutils import Quaternion
            q = Quaternion(axis, np.radians(limit))
        M = arm.matrix_world
        world = M @ pb.matrix
        world = Matrix.Translation(head) @ q.to_matrix().to_4x4() @ Matrix.Translation(-head) @ world
        pb.matrix = M.inverted() @ world
        bpy.context.view_layer.update()
        return float(np.degrees(q.angle))
    angles = {}
    # Root translation (pose location in bone space).
    root = arm.pose.bones['root']
    shift = targets['root']-rest_joints['root']
    root.matrix = arm.matrix_world.inverted() @ (Matrix.Translation(shift) @ (arm.matrix_world @ root.matrix))
    bpy.context.view_layer.update()
    # Spine and neck follow the head keypoints (eyes/nose/ears/mouth carry no
    # clothing bias; Asset A's dropped-shoulder knit biases its shoulder points).
    head_disp = mean_disp(face)
    angles['spine05'] = aim('spine05', 'neck01', rest_joints['neck01']+head_disp-joint('spine05'))
    angles['neck01'] = aim('neck01', 'head', targets['head']-joint('neck01'))
    for side, s in SIDE.items():
        # Each segment is aimed from where its joint actually is now.
        hand_rest = rest_joints[f'finger3-1.{s}']
        hand_target = hand_rest+mean_disp([f'{side}_index', f'{side}_pinky'])
        angles[f'upperarm01.{s}'] = aim(f'upperarm01.{s}', f'lowerarm01.{s}', targets[f'lowerarm01.{s}']-joint(f'upperarm01.{s}'))
        angles[f'lowerarm01.{s}'] = aim(f'lowerarm01.{s}', f'wrist.{s}', targets[f'wrist.{s}']-joint(f'lowerarm01.{s}'))
        angles[f'wrist.{s}'] = aim(f'wrist.{s}', f'finger3-1.{s}', hand_target-joint(f'wrist.{s}'), limit=25.0)
        angles[f'upperleg01.{s}'] = aim(f'upperleg01.{s}', f'lowerleg01.{s}', targets[f'lowerleg01.{s}']-joint(f'upperleg01.{s}'))
        angles[f'lowerleg01.{s}'] = aim(f'lowerleg01.{s}', f'foot.{s}', targets[f'foot.{s}']-joint(f'lowerleg01.{s}'))
        angles[f'foot.{s}'] = aim(f'foot.{s}', f'toe1-1.{s}', targets[f'toe1-1.{s}']-joint(f'foot.{s}'))
    # Evaluate the posed body against rest.
    depsgraph = bpy.context.evaluated_depsgraph_get()
    mesh = body.evaluated_get(depsgraph).to_mesh()
    n = len(mesh.vertices)
    posed = np.empty(n*3)
    mesh.vertices.foreach_get('co', posed)
    posed = posed.reshape(-1, 3)@np.array(body.matrix_world)[:3, :3].T+np.array(body.matrix_world)[:3, 3]
    body.evaluated_get(depsgraph).to_mesh_clear()
    src_idx = np.array([d.value for d in body.data.attributes['makehuman_source_index'].data])
    rest_body = rest_world[src_idx]
    pose_disp = posed-rest_body
    # Pose displacement for every source point (helpers, hidden feet) from nearby body vertices.
    all_pose_disp = interpolate([Vector(p) for p in rest_body], pose_disp, [Vector(p) for p in rest_world])
    all_pose_disp[src_idx] = pose_disp
    posed_all = rest_world+all_pose_disp
    # Stage 2: residual spline from where the production keypoints went to Asset A's.
    # Head keypoints are left to the face registration onto Asset B (MediaPipe
    # Face is far more precise there than the pose model's eye/ear points).
    names = [nm for nm in A if A[nm]['front_visibility'] > 0.6 and Pk[nm]['front_visibility'] > 0.6
             and not nm.endswith('_shoulder') and KP_BONE[nm] != 'head']
    p_kp = np.array([Pk[nm]['world'] for nm in names])
    p_kp_posed = np.array([carried(nm, Pk[nm]['world']) for nm in names])
    a_kp = np.array([A[nm]['world'] for nm in names])
    residual_before = np.linalg.norm(a_kp-p_kp_posed, axis=1)
    for nm, a_, pp, p0 in zip(names, a_kp, p_kp_posed, p_kp):
        print(f'KP {nm:18s} raw {np.round((a_-p0)*1000).astype(int)} after_pose {np.round((a_-pp)*1000).astype(int)}', flush=True)
    tps = tps_fit(p_kp_posed, a_kp, args.tps_smoothing)
    final_all = posed_all+tps(posed_all)
    after = np.linalg.norm(a_kp-(p_kp_posed+tps(p_kp_posed)), axis=1)
    d_world = final_all-rest_world
    offsets = np.stack((d_world[:, 0], d_world[:, 2], -d_world[:, 1]), axis=1)/scale
    np.savez_compressed(args.output, source_index=np.arange(len(offsets)), source_offsets=offsets, stage='post_pose')
    report = {'stage': 'source_body_fit_asset_a', 'bone_aim_degrees': {k: round(v, 2) for k, v in angles.items()},
              'root_shift_m': list(shift),
              'keypoints_used': names,
              'keypoint_residual_after_pose_mm': {'mean': float(residual_before.mean()*1000), 'max': float(residual_before.max()*1000)},
              'keypoint_residual_after_spline_mm': {'mean': float(after.mean()*1000), 'max': float(after.max()*1000)},
              'max_vertex_displacement_m': float(np.linalg.norm(d_world, axis=1).max()),
              'note': 'Pose and proportions from Asset A (user model); surface shape comes from garment conformance'}
    Path(args.report).write_text(json.dumps(report, indent=2)+'\n')
    print('SOURCE_BODY_FIT '+json.dumps({k: report[k] for k in ('keypoint_residual_after_pose_mm', 'keypoint_residual_after_spline_mm', 'max_vertex_displacement_m')}))


if __name__ == '__main__':
    main()
