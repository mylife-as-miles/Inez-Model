"""TERRA MyoFullBody trajectory -> intermediate skeleton (ISK).

Runs inside TERRA's own environment (it needs ``mujoco`` and
``musclemimic_models``, both pinned by TERRA's lockfile):

    source ~/terra-src/terra/.venv/bin/activate
    python tools/inez/motion/terra_to_isk.py --cache-root RESULTS --motion Study/Trial OUTPUT_isk.npz
    python tools/inez/motion/terra_to_isk.py --trajectory motion.npz OUTPUT_isk.npz   # file directly

With ``--cache-root`` the published artifacts are first checked with TERRA's
public read-side validator, ``terra.validate_retarget_artifacts``; its frame
count, frequency and terrain status are copied into the ISK metadata.

Kinematics: if the archive carries body poses (``xpos``/``xquat`` with
``body_names``) they are used; otherwise MuJoCo forward kinematics is run on
``qpos`` with the MyoFullBody model, matching qpos columns to model joints by
name (``joint_names``), never by position. TERRA fits the SMPL body to the
robot (``shape_optimized.pkl``); the robot model itself is not reshaped, so
the stock MyoFullBody XML is the right model for its trajectories.

Landmarks (body origins = joint centres in MyoFullBody):
    pelvis   midpoint of femur_l / femur_r       spine  lumbar1
    chest    cervical_spine (base of the neck)  neck   head (skull base)
    head     skull base + 8.5 cm along the head's up axis; head_top + 17 cm
    hip/knee/ankle/toe   femur/tibia/talus/toes  _l/_r
    shoulder/elbow/wrist/hand   humerus/ulna/lunate/3proxph  _l/_r
Segments (rest-relative world rotation): pelvis, thorax, head, calcn_l/r,
capitate_l/r. The rest pose is the model's qpos0 (anatomical position).

Contacts are estimated from the feet (toe base below 6 cm or ankle below
11 cm above the lowest point of that foot within +-0.5 s, horizontal speed
under 0.20 m/s), and the support height under each planted foot is stored so
non-flat terrain (stairs, ramps) is kept. A TERRA analysis record may hold
better contact evidence; using it is listed as future work in
docs/INEZ_TERRA_INTEGRATION.md.

This adapter does not create motion. Its input must be a real TERRA output
for the result to be called TERRA-derived; --synthetic-test writes a clearly
labelled synthetic MyoFullBody trajectory to test the mechanics only.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isk  # noqa: E402

LANDMARK_BODIES = {
    'spine': 'lumbar1', 'chest': 'cervical_spine', 'neck': 'head',
    'hip_l': 'femur_l', 'knee_l': 'tibia_l', 'ankle_l': 'talus_l', 'toe_l': 'toes_l',
    'hip_r': 'femur_r', 'knee_r': 'tibia_r', 'ankle_r': 'talus_r', 'toe_r': 'toes_r',
    'shoulder_l': 'humerus_l', 'elbow_l': 'ulna_l', 'wrist_l': 'lunate_l', 'hand_l': '3proxph_l',
    'shoulder_r': 'humerus_r', 'elbow_r': 'ulna_r', 'wrist_r': 'lunate_r', 'hand_r': '3proxph_r',
}
SEGMENT_BODIES = {'pelvis': 'pelvis', 'chest': 'thorax', 'head': 'head', 'foot_l': 'calcn_l', 'foot_r': 'calcn_r',
                  'hand_l': 'capitate_l', 'hand_r': 'capitate_r'}
LICENCE_NOTE = ('Derived from a TERRA (Apache-2.0) MyoFullBody trajectory. The source motion and the SMPL-H model used '
                'to produce it keep their own provider terms (AMASS / MPI licences are non-commercial); see '
                'docs/INEZ_MOTION_LICENSES.md before shipping.')


def quat_wxyz_to_matrix(q):
    w, x, y, z = q/np.linalg.norm(q)
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])


def load_model():
    import mujoco
    import musclemimic_models
    model = mujoco.MjModel.from_xml_path(str(musclemimic_models.get_xml_path('myofullbody')))
    return mujoco, model


def body_poses(archive, mujoco, model):
    """(frames, bodies, 3) positions and (frames, bodies, 3, 3) rotations by body name."""
    names = [mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, i) for i in range(model.nbody)]
    if {'xpos', 'xquat', 'body_names'} <= set(archive) and np.asarray(archive['xpos']).size:
        stored = [str(n) for n in archive['body_names']]
        xpos, xquat = np.asarray(archive['xpos']), np.asarray(archive['xquat'])
        pick = [stored.index(n) for n in names if n in stored]
        rot = np.array([[quat_wxyz_to_matrix(q) for q in frame[pick]] for frame in xquat])
        return [names[i] for i in range(len(names)) if names[i] in stored], xpos[:, pick], rot, 'stored body poses'
    qpos = np.asarray(archive['qpos'], np.float64)
    joint_names = [str(n) for n in archive['joint_names']] if 'joint_names' in archive else None
    data = mujoco.MjData(model)
    columns = []
    if joint_names:
        cursor = 0
        sizes = {0: 7, 1: 4, 2: 1, 3: 1}
        for name in joint_names:
            jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
            if jid < 0:
                raise ValueError(f'trajectory joint {name!r} not in MyoFullBody')
            width = sizes[int(model.jnt_type[jid])]
            columns.append((cursor, int(model.jnt_qposadr[jid]), width))
            cursor += width
        if cursor != qpos.shape[1]:
            raise ValueError(f'joint_names cover {cursor} qpos columns, archive has {qpos.shape[1]}')
    elif qpos.shape[1] != model.nq:
        raise ValueError(f'qpos has {qpos.shape[1]} columns, MyoFullBody nq = {model.nq}; joint_names needed')
    P = np.zeros((len(qpos), model.nbody, 3))
    R = np.zeros((len(qpos), model.nbody, 3, 3))
    for f, row in enumerate(qpos):
        data.qpos[:] = model.qpos0
        if columns:
            for src, dst, width in columns:
                data.qpos[dst:dst+width] = row[src:src+width]
        else:
            data.qpos[:] = row
        mujoco.mj_kinematics(model, data)
        P[f] = data.xpos
        R[f] = data.xmat.reshape(-1, 3, 3)
    return names, P, R, 'MuJoCo forward kinematics (MyoFullBody, joints matched by name)'


def rest_poses(mujoco, model):
    data = mujoco.MjData(model)
    data.qpos[:] = model.qpos0
    mujoco.mj_kinematics(model, data)
    return data.xpos.copy(), data.xmat.reshape(-1, 3, 3).copy()


def landmarks(names, P, R, rest_R):
    idx = {n: i for i, n in enumerate(names)}
    head_up_local = rest_R[idx['head']].T@np.array([0, 0, 1.0])
    out = np.zeros(P.shape[:1]+(len(isk.JOINTS), 3))
    for j, joint in enumerate(isk.JOINTS):
        if joint == 'pelvis':
            out[:, j] = (P[:, idx['femur_l']]+P[:, idx['femur_r']])/2
        elif joint in ('head', 'head_top'):
            up = np.einsum('fij,j->fi', R[:, idx['head']], head_up_local)
            out[:, j] = P[:, idx['head']]+up*(0.085 if joint == 'head' else 0.17)
        else:
            out[:, j] = P[:, idx[LANDMARK_BODIES[joint]]]
    return out


def contacts_and_support(P, frequency):
    flags = np.zeros((len(P), 2), bool)
    support = np.full((len(P), 2), np.nan)
    window = max(1, int(round(0.5*frequency)))
    for k, side in enumerate('lr'):
        ankle, toe = P[:, isk.JOINTS.index('ankle_'+side)], P[:, isk.JOINTS.index('toe_'+side)]
        low = np.minimum(ankle[:, 2]-0.08, toe[:, 2]-0.025)
        floor = np.array([low[max(0, f-window):f+window+1].min() for f in range(len(P))])
        for point, limit in ((ankle, 0.11), (toe, 0.06)):
            v = np.zeros(len(P))
            v[1:-1] = np.linalg.norm(point[2:, :2]-point[:-2, :2], axis=1)*frequency/2
            v[0], v[-1] = v[1], v[-2]
            flags[:, k] |= (point[:, 2]-floor < limit) & (v < 0.20)
        support[flags[:, k], k] = floor[flags[:, k]]
    return flags, support


def convert(archive, frequency, mujoco, model):
    names, P_body, R_body, method = body_poses(archive, mujoco, model)
    rest_P, rest_R = rest_poses(mujoco, model)
    all_names = [mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, i) for i in range(model.nbody)]
    keep = [all_names.index(n) for n in names]
    rest_P, rest_R = rest_P[keep], rest_R[keep]
    P = landmarks(names, P_body, R_body, rest_R)
    rest = landmarks(names, rest_P[None], rest_R[None], rest_R)[0]
    F = isk.facing_alignment(P)
    F_rest = isk.facing_alignment(rest[None])
    origin = P[0, isk.JOINTS.index('pelvis')].copy()
    origin[2] = 0.0
    P = (P-origin)@F.T
    rest_origin = rest[isk.JOINTS.index('pelvis')].copy()
    rest_origin[2] = 0.0
    rest = (rest-rest_origin)@F_rest.T
    idx = {n: i for i, n in enumerate(names)}
    rotations = np.zeros((len(P), len(isk.SEGMENTS), 4))
    for k, segment in enumerate(isk.SEGMENTS):
        b = idx[SEGMENT_BODIES[segment]]
        rotations[:, k] = isk.continuous([isk.quat_from_matrix(F@R_body[f, b]@rest_R[b].T@F_rest.T) for f in range(len(P))])
    flags, support = contacts_and_support(P, frequency)
    return P, rotations, rest, flags, support, method


def synthetic_trajectory(path, frequency=60.0, seconds=2.0):
    """A labelled synthetic MyoFullBody trajectory for mechanics tests:
    alternating hip/knee flexion in place from qpos0. Not motion data."""
    mujoco, model = load_model()
    t = np.arange(int(seconds*frequency))/frequency
    qpos = np.tile(model.qpos0, (len(t), 1))
    names = [mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, i) for i in range(model.njnt)]

    def set_joint(name, values):
        jid = names.index(name)
        qpos[:, model.jnt_qposadr[jid]] = values
    phase = 2*np.pi*t/1.0
    set_joint('hip_flexion_l', 0.5*np.clip(np.sin(phase), 0, None))
    set_joint('knee_angle_l', 0.9*np.clip(np.sin(phase), 0, None))
    set_joint('hip_flexion_r', 0.5*np.clip(-np.sin(phase), 0, None))
    set_joint('knee_angle_r', 0.9*np.clip(-np.sin(phase), 0, None))
    set_joint('elbow_flex_l', 0.6+0.3*np.sin(phase))
    np.savez(path, qpos=qpos, qvel=np.zeros((len(t), model.nv)), frequency=np.float64(frequency),
             joint_names=np.array(names), synthetic=np.array('SYNTHETIC TEST INPUT - not motion data, not TERRA output'))
    return {'frames': len(t), 'frequency': frequency, 'joints_driven': ['hip_flexion_l', 'knee_angle_l', 'hip_flexion_r',
                                                                      'knee_angle_r', 'elbow_flex_l']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output')
    parser.add_argument('--trajectory')
    parser.add_argument('--cache-root')
    parser.add_argument('--motion')
    parser.add_argument('--name')
    parser.add_argument('--synthetic-test', action='store_true', help='write and convert a labelled synthetic trajectory')
    parser.add_argument('--report')
    args = parser.parse_args()
    report = {'validator': None}
    terra_generated = False
    if args.synthetic_test:
        traj = Path(args.output).with_name(Path(args.output).stem+'_synthetic_myofullbody.npz')
        report['synthetic_input'] = synthetic_trajectory(traj)
        trajectory_path = traj
    elif args.cache_root and args.motion:
        from terra import validate_retarget_artifacts
        checked = validate_retarget_artifacts(args.cache_root, args.motion)
        report['validator'] = {'num_frames': checked.num_frames, 'frequency': checked.frequency,
                               'qpos_dimension': checked.qpos_dimension, 'nonflat_terrain': checked.nonflat_terrain,
                               'terrain_path': str(checked.terrain_path) if checked.terrain_path else None}
        trajectory_path = checked.trajectory_path
        terra_generated = True
    elif args.trajectory:
        trajectory_path = Path(args.trajectory)
        terra_generated = True
    else:
        parser.error('give --cache-root and --motion, --trajectory, or --synthetic-test')
    with np.load(trajectory_path, allow_pickle=False) as data:
        archive = {k: data[k] for k in data.files}
    synthetic = 'synthetic' in archive
    frequency = float(np.asarray(archive['frequency']).reshape(()))
    mujoco, model = load_model()
    P, R, rest, flags, support, method = convert(archive, frequency, mujoco, model)
    source = {'kind': 'synthetic_myofullbody_test' if synthetic else 'terra_myofullbody',
              'name': args.name or (args.motion or Path(trajectory_path).stem), 'terra': bool(terra_generated and not synthetic),
              'kinematics': method, 'trajectory': Path(trajectory_path).name}
    notes = ('SYNTHETIC TEST INPUT: generated joint curves on MyoFullBody to test the bridge mechanics. '
             'Not motion capture and not a TERRA output.') if synthetic else 'TERRA MyoFullBody trajectory.'
    isk.save(args.output, positions=P, rotations=R, rest_positions=rest, frequency=frequency, source=source,
             licence='synthetic, no licence restrictions' if synthetic else LICENCE_NOTE, contacts=flags, notes=notes)
    np.savez_compressed(Path(args.output).with_name(Path(args.output).stem+'_support.npz'), support_z=support)
    check = isk.validate(isk.load(args.output))
    report.update({'source': source, 'isk': {k: check[k] for k in ('passed', 'frames', 'frequency_hz', 'errors', 'warnings')},
                   'contact_fraction': flags.mean(0).tolist(), 'rest_pelvis_height_m': float(rest[0, 2]),
                   'rest_head_top_m': float(rest[isk.JOINTS.index('head_top'), 2])})
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=1))
    return 0 if check['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
