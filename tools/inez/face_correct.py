"""Landmark-driven frontal correction of the head toward the original face.

    blender -b MASTER.blend --python tools/inez/face_correct.py -- \
        --reference references/inez_turnaround.jpg --reference-box 855,0,1280,714 \
        --fitted p2/fitted.npz --passes 3 --output layers/face_correct.npz \
        --report layers/face_correct_report.json --image-dir DIR

The user's facial model (Asset B) is the 3D base, but the original images
govern proportions. Each pass renders the front view with the review studio,
runs MediaPipe Face Landmarker on the render and on the original, aligns
the original's landmarks to the render by the pupils (similarity), and
moves selected landmarks toward the original in the image plane (x, z):

  jaw and chin contour, cheek width (half)     bony outline, full weight
  nose length, alar width                      full weight
  mouth width, lip top/bottom                  half weight: the original
                                               wears a worried, pouting mouth
  eye-corner width                             0.7 in x only

Brows, lid apertures and the forehead are expression or hair dependent and
are pinned (zero displacement), as are the eyeball centres. Symmetric pairs
are averaged so the correction stays symmetric (the original panel is turned
about 3 degrees). Displacements form a Gaussian RBF field (sigma 18 mm)
evaluated on every source vertex of the fitted figure (fitted.npz, eyeballs
moved rigidly); passes accumulate with 0.8 damping. The result is a
post-pose identity layer for model_dress_v04.py --identity-layer
FaceCorrect=FILE. Depth (y) is never changed: no profile evidence exists.
Landmarks are a measurement aid, not a likeness score.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scan_common import Studio

DETECTOR = Path(__file__).resolve().parent/'face_landmarks.py'
BODY = 'Inez_ContinuousHumanMesh_UNAPPROVED'
# index: (weight_x, weight_z, contour)
MOVE = {152: (1, 1, True), 148: (1, 1, True), 377: (1, 1, True), 176: (1, 1, True), 400: (1, 1, True),
        149: (1, 1, True), 378: (1, 1, True), 150: (1, 1, True), 379: (1, 1, True), 136: (1, 1, True),
        365: (1, 1, True), 172: (1, 1, True), 397: (1, 1, True), 58: (1, .5, True), 288: (1, .5, True),
        234: (.5, 0, True), 454: (.5, 0, True),
        1: (0, 1, False), 2: (0, 1, False), 129: (1, .5, False), 358: (1, .5, False),
        61: (.5, .5, False), 291: (.5, .5, False), 0: (0, .5, False), 17: (0, .5, False),
        33: (.7, 0, False), 263: (.7, 0, False), 133: (.7, 0, False), 362: (.7, 0, False)}
PAIRS = [(148, 377), (176, 400), (149, 378), (150, 379), (136, 365), (172, 397), (58, 288), (234, 454),
         (129, 358), (61, 291), (33, 263), (133, 362)]
PIN = [105, 334, 66, 296, 70, 300, 151, 9, 168, 159, 145, 386, 374]
SIGMA, RIDGE, DAMPING = 0.018, 1e-3, 0.8


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('--reference', required=True)
    parser.add_argument('--reference-box', default='')
    parser.add_argument('--fitted', required=True)
    parser.add_argument('--passes', type=int, default=3)
    parser.add_argument('--output', required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--image-dir', required=True)
    parser.add_argument('--center', default='-0.002,-0.10,1.585')
    parser.add_argument('--span', type=float, default=0.36)
    parser.add_argument('--resolution', type=int, default=1000)
    return parser.parse_args(sys.argv[sys.argv.index('--')+1:])


def landmarks(path, box=''):
    cmd = ['python3', '-I', str(DETECTOR), str(path)]+(['--box', box] if box else [])
    run = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(run.stdout.strip().splitlines()[0])
    if not data.get('face'):
        raise SystemExit(f'No face found in {path}')
    return np.array(data['landmarks'])[:, :2], data['pose']


def align(ref, cur):
    """Similarity mapping the reference's pupils onto the render's."""
    a0, a1 = ref[468], ref[473]
    b0, b1 = cur[468], cur[473]
    va, vb = a1-a0, b1-b0
    s = np.linalg.norm(vb)/np.linalg.norm(va)
    ang = np.arctan2(vb[1], vb[0])-np.arctan2(va[1], va[0])
    R = np.array([[np.cos(ang), -np.sin(ang)], [np.sin(ang), np.cos(ang)]])
    return (ref-(a0+a1)/2)@R.T*s+(b0+b1)/2


def rbf(centres, values):
    d2 = ((centres[:, None, :]-centres[None, :, :])**2).sum(-1)
    phi = np.exp(-d2/(2*SIGMA**2))+RIDGE*np.eye(len(centres))
    weights = np.linalg.solve(phi, values)

    def field(points):
        out = np.zeros((len(points), values.shape[1]))
        for a in range(0, len(points), 20000):
            q = points[a:a+20000]
            k = np.exp(-((q[:, None, :]-centres[None, :, :])**2).sum(-1)/(2*SIGMA**2))
            out[a:a+20000] = k@weights
        return out
    return field


def main():
    args = arguments()
    scene = bpy.context.scene
    body = bpy.data.objects[BODY]
    arm = next(o for o in scene.objects if o.type == 'ARMATURE')
    for obj in scene.objects:
        if obj.type == 'LIGHT':
            obj.hide_render = True
    centre = np.array([float(v) for v in args.center.split(',')])
    res, span = args.resolution, args.span
    px = span/res
    out = Path(args.image_dir)
    out.mkdir(parents=True, exist_ok=True)
    fitted = np.load(args.fitted)
    P, scale, ground = fitted['fitted'], float(fitted['scale']), float(fitted['ground_eff'])
    world0 = np.stack([P[:, 0]*scale, -P[:, 2]*scale, (P[:, 1]-ground)*scale], 1)
    allpos = world0.copy()
    src = np.array([a.value for a in body.data.attributes['makehuman_source_index'].data])
    eyes = np.array([arm.matrix_world @ arm.data.bones['eye.'+s].head_local for s in ('L', 'R')])
    eye_helpers = [(np.arange(len(P)) >= 13380) & (np.linalg.norm(world0-e, axis=1) < 0.016) for e in eyes]
    key = body.shape_key_add(name='FaceCorrect_work', from_mix=False)
    key.value = 1.0
    basis = np.array([v.co for v in key.data])
    ref_pts, ref_pose = landmarks(args.reference, args.reference_box)
    studio = Studio(scene, 64, res)
    report = {'reference': args.reference, 'reference_box': args.reference_box, 'reference_pose': ref_pose,
              'sigma_m': SIGMA, 'damping': DAMPING, 'passes': []}
    for p in range(args.passes+1):
        image = out/f'face_correct_pass{p}.png'
        studio.render(Vector(centre), span, 0, image)
        cur, pose = landmarks(image)
        target = align(ref_pts, cur)
        delta_px = target-cur
        residual = {int(i): float(np.hypot(*(delta_px[i]*np.array([w[0] > 0, w[1] > 0]))))*px*1000
                    for i, w in MOVE.items()}
        entry = {'pass': p, 'render': str(image), 'render_pose': pose,
                 'residual_mm_rms': float(np.sqrt(np.mean(np.square(list(residual.values()))))),
                 'residual_mm': residual}
        report['passes'].append(entry)
        print('FACE_CORRECT pass', p, 'rms_mm', round(entry['residual_mm_rms'], 3))
        if p == args.passes:
            break
        # Image-plane displacement (world metres): image x -> +x, image y -> -z.
        d = np.stack([delta_px[:, 0]*px, -delta_px[:, 1]*px], 1)
        for a, b in PAIRS:
            dx, dz = (d[a, 0]-d[b, 0])/2, (d[a, 1]+d[b, 1])/2
            d[a], d[b] = (dx, dz), (-dx, dz)
        # Probe: 3D surface point under each landmark on the current body.
        dg = bpy.context.evaluated_depsgraph_get()
        mesh = body.evaluated_get(dg).to_mesh()
        co = np.array([body.matrix_world @ v.co for v in mesh.vertices])
        no = np.array([(body.matrix_world.to_3x3() @ v.normal).normalized() for v in mesh.vertices])
        bvh = BVHTree.FromPolygons([tuple(c) for c in co], [tuple(pp.vertices) for pp in mesh.polygons])
        body.evaluated_get(dg).to_mesh_clear()
        head = np.linalg.norm(co-eyes.mean(0), axis=1) < 0.16

        eye_plane = float(eyes[:, 1].mean())+0.004

        def probe(i, contour):
            x = centre[0]+(cur[i, 0]/res-0.5)*span
            z = centre[2]+(0.5-cur[i, 1]/res)*span
            if not contour:
                # First hit in front of the eyeball centres; a ray through the
                # lid opening would otherwise land inside the socket.
                hit = bvh.ray_cast(Vector((x, centre[1]-0.5, z)), Vector((0, 1, 0)), 1.0)[0]
                if hit is not None and hit.y < eye_plane:
                    return np.array(hit)
                cand = head & (no[:, 1] < -0.2) & (co[:, 1] < eye_plane)
            else:
                cand = head & (np.abs(no[:, 1]) < 0.4)
            dist = np.hypot(co[:, 0]-x, co[:, 2]-z)
            dist[~cand] = np.inf
            return co[int(np.argmin(dist))]
        centres, values = [], []
        for i, (wx, wz, contour) in MOVE.items():
            centres.append(probe(i, contour))
            values.append((d[i, 0]*wx*DAMPING, 0.0, d[i, 1]*wz*DAMPING))
        for i in PIN:
            centres.append(probe(i, False))
            values.append((0.0, 0.0, 0.0))
        for e in eyes:
            centres.append(np.asarray(e))
            values.append((0.0, 0.0, 0.0))
        field = rbf(np.array(centres), np.array(values))
        step = field(allpos)
        for mask, e in zip(eye_helpers, eyes):
            step[mask] = field(np.asarray(e)[None])[0]
        allpos += step
        # Show the accumulated correction on the body through the work key.
        offs = allpos[src]-world0[src]
        inv = np.array(body.matrix_world.inverted().to_3x3())
        key.data.foreach_set('co', (basis+offs@inv.T).astype(np.float32).ravel())
        body.data.update()
        entry['max_step_mm'] = float(np.linalg.norm(step, axis=1).max()*1000)
    total = allpos-world0
    # World offsets -> source units: world (dx, dy, dz) = s*(dx, -dz, dy).
    offsets = np.stack([total[:, 0], total[:, 2], -total[:, 1]], 1)/scale
    moved = np.flatnonzero(np.linalg.norm(total, axis=1) > 1e-6)
    np.savez_compressed(args.output, source_index=moved, source_offsets=offsets[moved], stage='post_pose')
    report['moved_vertices'] = int(len(moved))
    report['max_displacement_mm'] = float(np.linalg.norm(total, axis=1).max()*1000)
    report['layer'] = args.output
    report['note'] = ('Image-plane correction toward the original face panel; depth unchanged. '
                      'Landmark residuals are a measurement aid, not a likeness score.')
    Path(args.report).write_text(json.dumps(report, indent=1)+'\n')
    print('FACE_CORRECT_DONE', json.dumps({'moved_vertices': report['moved_vertices'],
                                           'max_displacement_mm': report['max_displacement_mm'],
                                           'rms_mm': [e['residual_mm_rms'] for e in report['passes']]}))


if __name__ == '__main__':
    main()
