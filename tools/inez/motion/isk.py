"""Intermediate skeleton (ISK): the hand-off format between motion sources and Inez.

Every source adapter (TERRA MyoFullBody trajectories, CMU ASF/AMC, ...) writes
one ``.npz`` in this format, and ``retarget_to_inez.py`` reads only this
format. Nothing here knows about Inez's rig or about any source's joints.

Conventions
- Metres, right-handed, +Z up, the performer faces -Y at the first frame
  (the direction Inez faces in Blender), feet on z = 0 when standing.
- ``positions[frame, joint]``: world position of each joint centre.
- ``rotations[frame, segment]``: world rotation (w, x, y, z) of each segment
  *relative to the source's own rest pose*: identity means "as in the rest
  pose", so sources with different rest poses stay comparable.
- ``rest_positions[joint]``: joint centres in the rest pose, same frame.
- ``contacts[frame, foot]``: optional per-foot support flags (left, right).

Validation (``validate``) reports missing joints, non-finite values,
non-unit quaternions, frame-count mismatches, and per-joint discontinuities
(largest frame-to-frame jump, metres and degrees).
"""
import json
from pathlib import Path

import numpy as np

JOINTS = (
    'pelvis', 'spine', 'chest', 'neck', 'head', 'head_top',
    'hip_l', 'knee_l', 'ankle_l', 'toe_l',
    'hip_r', 'knee_r', 'ankle_r', 'toe_r',
    'shoulder_l', 'elbow_l', 'wrist_l', 'hand_l',
    'shoulder_r', 'elbow_r', 'wrist_r', 'hand_r',
)
SEGMENTS = ('pelvis', 'chest', 'head', 'foot_l', 'foot_r', 'hand_l', 'hand_r')
FORMAT = 'inez-isk/1'


def save(path, *, positions, rotations, rest_positions, frequency, source, licence, contacts=None, notes=''):
    positions = np.asarray(positions, np.float64)
    rotations = np.asarray(rotations, np.float64)
    meta = {'format': FORMAT, 'joints': list(JOINTS), 'segments': list(SEGMENTS), 'source': source,
            'licence': licence, 'frequency_hz': float(frequency), 'frames': int(len(positions)), 'notes': notes}
    arrays = dict(positions=positions, rotations=rotations, rest_positions=np.asarray(rest_positions, np.float64),
                  frequency=np.float64(frequency), meta=np.array(json.dumps(meta)))
    if contacts is not None:
        arrays['contacts'] = np.asarray(contacts, bool)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **arrays)
    return meta


def load(path):
    with np.load(path, allow_pickle=False) as data:
        out = {k: data[k] for k in data.files}
    out['meta'] = json.loads(str(out['meta']))
    if out['meta'].get('format') != FORMAT:
        raise ValueError(f'{path}: not an {FORMAT} archive')
    return out


def validate(data):
    """Structural and continuity checks; returns a report dict (never raises)."""
    meta = data['meta']
    report = {'format': meta.get('format'), 'source': meta.get('source'), 'frames': int(meta.get('frames', -1)),
              'frequency_hz': meta.get('frequency_hz'), 'errors': [], 'warnings': []}
    P, R = data['positions'], data['rotations']
    if list(meta.get('joints', [])) != list(JOINTS):
        report['errors'].append('joint list differs from the ISK joint set')
    if P.shape[1:] != (len(JOINTS), 3):
        report['errors'].append(f'positions shape {P.shape}')
    if R.shape[1:] != (len(SEGMENTS), 4):
        report['errors'].append(f'rotations shape {R.shape}')
    if not (len(P) == len(R) == report['frames']):
        report['errors'].append('frame counts disagree between positions, rotations and metadata')
    if not (np.isfinite(P).all() and np.isfinite(R).all()):
        report['errors'].append('non-finite values')
    norms = np.linalg.norm(R, axis=-1)
    report['quaternion_norm_range'] = [float(norms.min()), float(norms.max())]
    if np.abs(norms-1).max() > 1e-4:
        report['errors'].append('rotations are not unit quaternions')
    dt = 1.0/float(meta['frequency_hz'])
    jumps = np.linalg.norm(np.diff(P, axis=0), axis=-1) if len(P) > 1 else np.zeros((0, len(JOINTS)))
    report['max_joint_speed_m_s'] = {j: float(jumps[:, i].max()/dt) for i, j in enumerate(JOINTS)} if len(jumps) else {}
    dots = np.abs((R[1:]*R[:-1]).sum(-1)).clip(0, 1) if len(R) > 1 else np.ones((0, len(SEGMENTS)))
    angles = np.degrees(2*np.arccos(dots))
    report['max_segment_step_deg'] = {s: float(angles[:, i].max()) for i, s in enumerate(SEGMENTS)} if len(angles) else {}
    fast = {j: v for j, v in report['max_joint_speed_m_s'].items() if v > 12.0}
    if fast:
        report['warnings'].append(f'joint speeds above 12 m/s (discontinuity?): {fast}')
    spiky = {s: v for s, v in report['max_segment_step_deg'].items() if v > 30.0}
    if spiky:
        report['warnings'].append(f'segment rotation steps above 30 degrees per frame: {spiky}')
    rest = data['rest_positions']
    for a, b in (('hip_l', 'knee_l'), ('knee_l', 'ankle_l'), ('hip_r', 'knee_r'), ('knee_r', 'ankle_r'),
                 ('shoulder_l', 'elbow_l'), ('elbow_l', 'wrist_l'), ('shoulder_r', 'elbow_r'), ('elbow_r', 'wrist_r')):
        i, k = JOINTS.index(a), JOINTS.index(b)
        lengths = np.linalg.norm(P[:, k]-P[:, i], axis=-1)
        rest_length = float(np.linalg.norm(rest[k]-rest[i]))
        stretch = float(np.abs(lengths-rest_length).max()) if len(lengths) else 0.0
        report.setdefault('segment_length_variation_m', {})[f'{a}-{b}'] = stretch
        if stretch > 0.01:
            report['warnings'].append(f'{a}-{b} length varies by {stretch*1000:.1f} mm')
    report['passed'] = not report['errors']
    return report


def quat_from_matrix(m):
    """(w, x, y, z) from a 3x3 rotation matrix (Shepperd)."""
    m = np.asarray(m, np.float64)
    t = np.trace(m)
    if t > 0:
        s = np.sqrt(t+1.0)*2
        q = [0.25*s, (m[2, 1]-m[1, 2])/s, (m[0, 2]-m[2, 0])/s, (m[1, 0]-m[0, 1])/s]
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = np.sqrt(1.0+m[0, 0]-m[1, 1]-m[2, 2])*2
        q = [(m[2, 1]-m[1, 2])/s, 0.25*s, (m[0, 1]+m[1, 0])/s, (m[0, 2]+m[2, 0])/s]
    elif m[1, 1] > m[2, 2]:
        s = np.sqrt(1.0+m[1, 1]-m[0, 0]-m[2, 2])*2
        q = [(m[0, 2]-m[2, 0])/s, (m[0, 1]+m[1, 0])/s, 0.25*s, (m[1, 2]+m[2, 1])/s]
    else:
        s = np.sqrt(1.0+m[2, 2]-m[0, 0]-m[1, 1])*2
        q = [(m[1, 0]-m[0, 1])/s, (m[0, 2]+m[2, 0])/s, (m[1, 2]+m[2, 1])/s, 0.25*s]
    q = np.asarray(q)
    return q/np.linalg.norm(q)


def continuous(quaternions):
    """Flip signs so consecutive quaternions stay in one hemisphere."""
    q = np.array(quaternions, np.float64)
    for i in range(1, len(q)):
        if (q[i]*q[i-1]).sum() < 0:
            q[i] = -q[i]
    return q


def facing_alignment(positions, joints=JOINTS):
    """Yaw rotation (3x3) that turns the first frame's facing to -Y.

    Facing = (left hip - right hip) x up on the horizontal plane (a figure
    facing -Y has its left side at +X: X x Z = -Y)."""
    hip_l, hip_r = positions[0, joints.index('hip_l')], positions[0, joints.index('hip_r')]
    left = np.array(hip_l-hip_r, np.float64)
    left[2] = 0
    left /= np.linalg.norm(left)
    forward = np.cross(left, np.array([0, 0, 1.0]))
    angle = -np.pi/2-np.arctan2(forward[1], forward[0])
    c, s = np.cos(angle), np.sin(angle)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])
