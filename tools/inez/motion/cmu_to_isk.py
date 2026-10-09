"""CMU Graphics Lab ASF/AMC motion -> intermediate skeleton (ISK).

    python3 -I tools/inez/motion/cmu_to_isk.py SKELETON.asf MOTION.amc OUTPUT.npz \
        --name cmu_02_01 [--frequency 120] [--report report.json]

Source and licence: mocap.cs.cmu.edu. "This data is free for use in research
projects. You may include this data in commercially-sold products, but you
may not resell this data directly, even in converted form." Acknowledgement
text (requested by CMU): "The data used in this project was obtained from
mocap.cs.cmu.edu. The database was created with funding from NSF
EIA-0196217."

Forward kinematics follow the Acclaim ASF/AMC definition as used for the CMU
database: each bone has an axis rotation C (Euler XYZ, degrees, applied as
Rz Ry Rx), AMC values M give the bone's rotation in that frame, and the world
rotation is parent * C * M * C^-1. A bone ends at parent end + length *
rotation * direction. In the zero pose every rotation is identity, so the ISK
"rotation relative to rest" of a segment is its world rotation. Units become
metres with the CMU FAQ factor (1/0.45) * 2.54 / 100 = 0.056444.

This is NOT a TERRA output. It is real optical motion capture used to prove
the source-skeleton -> Inez half of the bridge with permitted data.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isk  # noqa: E402

LICENCE = ('CMU Graphics Lab Motion Capture Database (mocap.cs.cmu.edu): free for research; may be included in '
           'commercially sold products; may not be resold directly, even in converted form. Acknowledgement: '
           '"The data used in this project was obtained from mocap.cs.cmu.edu. The database was created with '
           'funding from NSF EIA-0196217."')
# ISK joint -> (CMU bone whose END is the joint) or a callable on ends.
JOINT_ENDS = {
    'spine': 'lowerback', 'chest': 'thorax', 'neck': 'upperneck', 'head_top': 'head',
    'hip_l': 'lhipjoint', 'knee_l': 'lfemur', 'ankle_l': 'ltibia', 'toe_l': 'lfoot',
    'hip_r': 'rhipjoint', 'knee_r': 'rfemur', 'ankle_r': 'rtibia', 'toe_r': 'rfoot',
    'shoulder_l': 'lclavicle', 'elbow_l': 'lhumerus', 'wrist_l': 'lradius', 'hand_l': 'lhand',
    'shoulder_r': 'rclavicle', 'elbow_r': 'rhumerus', 'wrist_r': 'rradius', 'hand_r': 'rhand',
}
SEGMENT_BONES = {'pelvis': 'root', 'chest': 'thorax', 'head': 'head', 'foot_l': 'lfoot', 'foot_r': 'rfoot',
                 'hand_l': 'lhand', 'hand_r': 'rhand'}
UNIT = (1.0/0.45)*2.54/100.0


def euler_xyz(degrees):
    """Rz @ Ry @ Rx for (rx, ry, rz) in degrees (static XYZ, the Acclaim order)."""
    x, y, z = np.radians(degrees)
    cx, sx, cy, sy, cz, sz = np.cos(x), np.sin(x), np.cos(y), np.sin(y), np.cos(z), np.sin(z)
    rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return rz@ry@rx


def parse_asf(path):
    bones, hierarchy, section, bone = {}, {}, None, None
    for raw in Path(path).read_text(errors='replace').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith(':'):
            section = line.split()[0]
            continue
        parts = line.split()
        if section == ':bonedata':
            if parts[0] == 'begin':
                bone = {'dof': [], 'axis': np.zeros(3)}
            elif parts[0] == 'end':
                bones[bone['name']] = bone
                bone = None
            elif bone is not None and parts[0] == 'name':
                bone['name'] = parts[1]
            elif bone is not None and parts[0] == 'direction':
                bone['direction'] = np.array([float(v) for v in parts[1:4]])
            elif bone is not None and parts[0] == 'length':
                bone['length'] = float(parts[1])
            elif bone is not None and parts[0] == 'axis':
                if parts[4].upper() != 'XYZ':
                    raise ValueError(f'unsupported axis order {parts[4]}')
                bone['axis'] = np.array([float(v) for v in parts[1:4]])
            elif bone is not None and parts[0] == 'dof':
                bone['dof'] = [d.lower() for d in parts[1:]]
        elif section == ':hierarchy' and parts[0] not in ('begin', 'end'):
            hierarchy[parts[0]] = parts[1:]
    return bones, hierarchy, None


def parse_amc(path):
    frames, current = [], None
    for line in Path(path).read_text(errors='replace').splitlines():
        line = line.strip()
        if not line or line.startswith(('#', ':')):
            continue
        parts = line.split()
        if len(parts) == 1 and parts[0].isdigit():
            current = {}
            frames.append(current)
        elif current is not None:
            current[parts[0]] = [float(v) for v in parts[1:]]
    return frames


def forward(bones, hierarchy, frame):
    """World end positions and rotations of every bone for one AMC frame."""
    ends, rotations = {}, {}
    root = frame.get('root', [0]*6)
    ends['root'] = np.array(root[:3])
    rotations['root'] = euler_xyz(root[3:6])
    order = ['root']
    while order:
        parent = order.pop(0)
        for child in hierarchy.get(parent, []):
            bone = bones[child]
            values = dict(zip(bone['dof'], frame.get(child, [0.0]*len(bone['dof']))))
            local = euler_xyz([values.get('rx', 0.0), values.get('ry', 0.0), values.get('rz', 0.0)])
            C = euler_xyz(bone['axis'])
            rotations[child] = rotations[parent]@C@local@C.T
            ends[child] = ends[parent]+bone['length']*rotations[child]@bone['direction']
            order.append(child)
    return ends, rotations


def convert(asf, amc, frequency):
    bones, hierarchy, _ = parse_asf(asf)
    frames = parse_amc(amc)
    # Y-up (CMU) -> Z-up (Blender): (x, y, z) -> (x, -z, y).
    A = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0.0]])

    def sample(frame):
        ends, rots = forward(bones, hierarchy, frame)
        pos = np.zeros((len(isk.JOINTS), 3))
        for j, name in enumerate(isk.JOINTS):
            if name == 'pelvis':
                pos[j] = ends['root']
            elif name == 'head':
                pos[j] = (ends['upperneck']+ends['head'])/2
            else:
                pos[j] = ends[JOINT_ENDS[name]]
        rot = [rots[SEGMENT_BONES[s]] for s in isk.SEGMENTS]
        return (A@(pos*UNIT).T).T, [A@r@A.T for r in rot]

    rest_pos, _ = sample({})
    samples = [sample(f) for f in frames]
    P = np.array([s[0] for s in samples])
    # Canonical frames: the clip is turned so its first frame faces -Y (F),
    # the rest pose by its own facing (F_rest). A segment point then maps
    # rest -> frame t by F (A M A^T) F_rest^T, the ISK rest-relative rotation.
    F = isk.facing_alignment(P)
    F_rest = isk.facing_alignment(rest_pos[None])
    P = P@F.T
    rest_pos = rest_pos@F_rest.T
    R = np.array([[isk.quat_from_matrix(F@r@F_rest.T) for r in s[1]] for s in samples])
    R = np.stack([isk.continuous(R[:, k]) for k in range(R.shape[1])], 1)
    # Ground: CMU's floor is near y = 0 but marker offsets vary; put the
    # 2nd percentile of the toe-base (MTP) joint height at 25 mm.
    toes = P[:, [isk.JOINTS.index('toe_l'), isk.JOINTS.index('toe_r')], 2]
    shift = 0.025-np.percentile(toes, 2)
    P[..., 2] += shift
    rest_pos[:, 2] += 0.025-min(rest_pos[isk.JOINTS.index('toe_l'), 2], rest_pos[isk.JOINTS.index('toe_r'), 2])
    # Start at the origin on the ground plane (root motion kept relative).
    start = P[0, isk.JOINTS.index('pelvis')].copy()
    P[..., 0] -= start[0]
    P[..., 1] -= start[1]
    rest_pos[:, 0] -= rest_pos[isk.JOINTS.index('pelvis'), 0]
    rest_pos[:, 1] -= rest_pos[isk.JOINTS.index('pelvis'), 1]
    contacts = foot_contacts(P, frequency)
    return P, R, rest_pos, contacts, {'amc_frames': len(frames), 'ground_shift_m': float(shift),
                                      'unit_m': UNIT, 'bones': len(bones)}


def foot_contacts(P, frequency, height=(0.11, 0.06), speed=0.20):
    """Support flags per foot: ankle below 11 cm or toe base below 6 cm,
    with that point moving slower than 0.20 m/s horizontally (looser limits
    take in touchdown and lift-off, which then get locked as stance)."""
    out = np.zeros((len(P), 2), bool)
    for k, side in enumerate('lr'):
        ankle, toe = P[:, isk.JOINTS.index('ankle_'+side)], P[:, isk.JOINTS.index('toe_'+side)]
        for point, limit in ((ankle, height[0]), (toe, height[1])):
            v = np.zeros(len(P))
            v[1:-1] = np.linalg.norm(point[2:, :2]-point[:-2, :2], axis=1)*frequency/2
            v[0], v[-1] = v[1], v[-2]
            out[:, k] |= (point[:, 2] < limit) & (v < speed)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('asf')
    parser.add_argument('amc')
    parser.add_argument('output')
    parser.add_argument('--name', required=True)
    parser.add_argument('--frequency', type=float, default=120.0)
    parser.add_argument('--report')
    args = parser.parse_args()
    P, R, rest, contacts, info = convert(args.asf, args.amc, args.frequency)
    meta = isk.save(args.output, positions=P, rotations=R, rest_positions=rest, frequency=args.frequency,
                    source={'kind': 'cmu_mocap', 'name': args.name, 'asf': Path(args.asf).name,
                            'amc': Path(args.amc).name, 'terra': False},
                    licence=LICENCE, contacts=contacts,
                    notes='Real optical motion capture (CMU). Not generated or processed by TERRA.')
    report = isk.validate(isk.load(args.output))
    report.update(info)
    report['contact_fraction'] = {'left': float(contacts[:, 0].mean()), 'right': float(contacts[:, 1].mean())}
    pelvis = P[:, isk.JOINTS.index('pelvis')]
    report['root_travel_m'] = float(np.linalg.norm(pelvis[-1, :2]-pelvis[0, :2]))
    report['root_height_range_m'] = [float(pelvis[:, 2].min()), float(pelvis[:, 2].max())]
    report['duration_s'] = len(P)/args.frequency
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: report[k] for k in ('passed', 'frames', 'duration_s', 'root_travel_m', 'root_height_range_m',
                                             'contact_fraction', 'errors', 'warnings')}, indent=1))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
