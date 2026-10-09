"""Wrap the production head onto Asset B's face (identity layer; no Blender).

    python3 -I tools/inez/source_head_wrap.py --body body.npz --fitted fitted.npz \
        --inez-landmarks inez_face.json --b-landmarks b_face.json \
        --b-mesh SRC_B_HeadBust.npz --b-regions SRC_B_regions.npz \
        --output head_wrap.npz --report head_wrap_report.json

Asset B (the user's facial model) is the face authority among the existing
models. The production head keeps its animation topology, UVs and weights and
adopts B's shape:
  1. A smoothed thin-plate spline from production face landmarks to B's
     (identical cameras/detector; hairline-dependent outline points, inner
     lips and irises excluded) moves the whole head, eyes and mouth helpers
     included, fading out over the neck so the Asset A body fit is kept.
  2. Face, ears and neck vertices are then projected onto B's skin surface
     (B's region labels), except the eye-socket and mouth-interior islands
     and two rings around them, which keep the spline result so lids and lips
     still open and close.
The scalp stays under B's hair shell (no projection). Output is a post-pose
layer per MakeHuman source vertex for model_dress_v04.py --identity-layer.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy.interpolate import RBFInterpolator
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from head_uv import head_islands, head_weight_vector
from model_source import read_obj
from scan_landmark_sets import FACE_OVAL, FEATURE, IRIS, LEFT_EYE, LIPS_INNER, RIGHT_EYE
from scan_wrap import adjacency, rings, vertex_normals

EXCLUDED = (set(LIPS_INNER)-{78, 308}) | {10, 338, 297, 332, 284, 251, 389, 356, 127, 162, 21, 54, 103, 67, 109}


def arguments():
    parser = argparse.ArgumentParser()
    for name in ('body', 'fitted', 'inez-landmarks', 'b-landmarks', 'b-mesh', 'b-regions', 'output', 'report'):
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--max-projection', type=float, default=0.008)
    parser.add_argument('--eye-radius', type=float, default=0.012, help='eyeball radius (m); MakeHuman helper is 17 mm')
    parser.add_argument('--eye-open', type=float, default=0.34,
                        help='target lid opening / eye width (originals ~0.37 with a worried expression; '
                             'Asset B 0.19, heavy-lidded)')
    return parser.parse_args()


def set_lid_margins(W, src_idx, neighbours, islands, faces, B, eye_open):
    """Move the production lid margins onto Asset B's measured eye contour,
    with the upper lid opened to `eye_open` (lid gap / corner distance), and
    spread the change over four rings on both sides of the margin."""
    head_main = {i for f in islands['head_main'] for i, _ in faces[f]}
    report = {}
    total = np.zeros_like(W)
    for name, contour in (('eye_socket_R', RIGHT_EYE), ('eye_socket_L', LEFT_EYE)):
        socket = {i for f in islands[name] for i, _ in faces[f]}
        margin_src = socket & head_main
        margin = np.flatnonzero(np.isin(src_idx, list(margin_src)))
        pts = {i: np.array(B[str(i)]['world']) for i in contour if str(i) in B}
        # MediaPipe contour order: corner, lower lid ..., other corner, upper lid ...
        c0, c1 = pts[contour[0]], pts[contour[8]]
        inner, outer = (c1, c0) if abs(c1[0]) < abs(c0[0]) else (c0, c1)
        x_axis = (outer-inner)/np.linalg.norm(outer-inner)
        forward = np.array([0.0, -1.0, 0.0])
        y_axis = np.cross(forward, x_axis)
        y_axis /= np.linalg.norm(y_axis)
        if y_axis[2] < 0:
            y_axis = -y_axis
        width = np.linalg.norm(outer-inner)
        lower = [pts[i] for i in contour[1:8] if i in pts]
        upper = [pts[i] for i in contour[9:] if i in pts]

        def local(p):
            d = p-inner
            return np.array([d@x_axis/width, d@y_axis/width])
        lo_l = np.array([local(p) for p in lower])
        up_l = np.array([local(p) for p in upper])
        gap_b = np.interp(0.5, *zip(*sorted(zip(up_l[:, 0], up_l[:, 1]))))-np.interp(0.5, *zip(*sorted(zip(lo_l[:, 0], lo_l[:, 1]))))
        up_scale = max(1.0, (eye_open+np.interp(0.5, *zip(*sorted(zip(lo_l[:, 0], lo_l[:, 1])))))/max(np.interp(0.5, *zip(*sorted(zip(up_l[:, 0], up_l[:, 1])))), 1e-4))
        def curve(points_local, depth_points, t):
            order = np.argsort(points_local[:, 0])
            xs = np.concatenate(([0.0], points_local[order, 0], [1.0]))
            ys = np.concatenate(([0.0], points_local[order, 1], [0.0]))
            ds = np.concatenate(([0.0], [(depth_points[k]-inner)@forward for k in order], [(outer-inner)@forward]))
            return np.interp(t, xs, ys), np.interp(t, xs, ds)
        upper_scaled = up_l.copy()
        upper_scaled[:, 1] *= up_scale
        for v in margin:
            lx, ly = local(W[v])
            t = np.clip(lx, 0, 1)
            if ly >= 0:
                yy, dd = curve(upper_scaled, upper, t)
            else:
                yy, dd = curve(lo_l, lower, t)
            target = inner+x_axis*(t*width)+y_axis*(yy*width)+forward*dd
            total[v] = target-W[v]
        report[name] = {'margin_vertices': int(len(margin)), 'b_opening_ratio': float(gap_b),
                        'upper_lid_scale': float(up_scale), 'target_opening_ratio': eye_open,
                        'eye_width_mm': float(width*1000)}
    # Spread over four rings on both sides (lid skin and inner lid).
    spread = total.copy()
    weight = (np.linalg.norm(total, axis=1) > 0).astype(float)
    frontier = set(np.flatnonzero(weight > 0))
    for decay in (0.75, 0.45, 0.2, 0.08):
        nxt = set()
        for v in frontier:
            for n in neighbours[v]:
                if weight[n] == 0:
                    nxt.add(n)
        for n in nxt:
            nb = [m for m in neighbours[n] if weight[m] > 0]
            spread[n] = np.mean([spread[m] for m in nb], axis=0)*decay
            weight[n] = decay
        frontier = nxt
    return W+spread, report


def main():
    args = arguments()
    body = np.load(args.body)
    fit = np.load(args.fitted)
    scale, ground_eff = float(fit['scale']), float(fit['ground_eff'])
    src = fit['fitted']
    world_all = np.stack((src[:, 0]*scale, -src[:, 2]*scale, (src[:, 1]-ground_eff)*scale), axis=1)
    I = json.loads(Path(args.inez_landmarks).read_text())
    B = json.loads(Path(args.b_landmarks).read_text())['landmarks']
    main_object = I['object']
    I = I['landmarks']
    ids = [i for i in range(468) if str(i) in I and str(i) in B and i not in IRIS and i not in EXCLUDED
           and I[str(i)]['facing'] > 0.3 and B[str(i)]['facing'] > 0.3 and I[str(i)].get('object', main_object) == main_object]
    p_i = np.array([I[str(i)]['world'] for i in ids])
    p_b = np.array([B[str(i)]['world'] for i in ids])
    smoothing = np.array([2e-4 if i in FEATURE else 3e-3 for i in ids])
    tps = RBFInterpolator(p_i, p_b-p_i, kernel='thin_plate_spline', smoothing=smoothing, degree=1)
    chin = np.array(I['152']['world'])
    # Head weight: 1 above the chin, fading to 0 by 9 cm below it (neck base).
    def head_weight(points):
        return np.clip((points[:, 2]-(chin[2]-0.09))/0.07, 0, 1)
    # Far from the face the spline only extrapolates its affine part; that is
    # the head's global placement/scale/tilt, which is wanted on the scalp.
    w_all = head_weight(world_all)[:, None]
    disp_all = np.zeros_like(world_all)
    sel = w_all[:, 0] > 0
    # Beyond the landmark cloud the spline kernel extrapolates wildly (8 cm on
    # the occiput): blend to B's rigid similarity from 2 cm to 6 cm away.
    ms, md = p_i.mean(0), p_b.mean(0)
    U, D, Vt = np.linalg.svd((p_b-md).T@(p_i-ms)/len(p_i))
    E = np.eye(3)
    if np.linalg.det(U)*np.linalg.det(Vt) < 0:
        E[2, 2] = -1
    R = U@E@Vt
    s = np.trace(np.diag(D)@E)/((p_i-ms)**2).sum(1).mean()
    def similarity(points):
        return (points-ms)@(s*R).T+md-points
    d_land, _ = cKDTree(p_i).query(world_all[sel])
    blend = np.clip(1-(d_land-0.02)/0.04, 0, 1)[:, None]
    disp_all[sel] = (tps(world_all[sel])*blend+similarity(world_all[sel])*(1-blend))*w_all[sel]
    warped_all = world_all+disp_all
    tps_fit = tps(p_i)+p_i-p_b
    # Projection of the body mesh's face/ear/neck vertices onto B's skin.
    V = body['vertices'].astype(np.float64)
    src_idx = body['makehuman_source_index']
    W = warped_all[src_idx]
    VN = vertex_normals(W, body['triangles'])
    Bmesh = np.load(args.b_mesh)
    labels = np.load(args.b_regions)['labels']
    BP = Bmesh['vertices'].astype(np.float64)
    BN = vertex_normals(BP, Bmesh['triangles'])
    skin = labels == 0
    tree = cKDTree(BP[skin])
    skin_ids = np.flatnonzero(skin)
    points, texcoords, groups = read_obj()
    faces = groups['body']
    islands = head_islands(points, faces, head_weight_vector())
    protected_src = {i for name in ('mouth_interior', 'eye_socket_R', 'eye_socket_L') for f in islands[name] for i, _ in faces[f]}
    seeds = np.flatnonzero(np.isin(src_idx, list(protected_src)))
    neighbours = adjacency(len(W), body['triangles'])
    ring = rings(neighbours, seeds, 3)
    protect = np.choose(np.minimum(ring, 3), [0.0, 0.0, 0.5, 1.0])
    # Eyelids: B's lids are fused to its eyeball surface; projecting lid skin
    # onto it retracts the production lids (opening 0.45 vs B 0.19). Lid skin
    # within 5 rings of the socket islands takes no projection; the lid
    # margins are set explicitly below.
    eye_src = {i for name in ('eye_socket_R', 'eye_socket_L') for f in islands[name] for i, _ in faces[f]}
    eye_seeds = np.flatnonzero(np.isin(src_idx, list(eye_src)))
    eye_ring = rings(neighbours, eye_seeds, 6)
    protect = np.minimum(protect, np.clip((eye_ring-4)/2.0, 0, 1))
    W, eye_report = set_lid_margins(W, src_idx, neighbours, islands, faces, B, args.eye_open)
    region = head_weight(W)*protect
    candidates = np.flatnonzero(region > 0)
    offset = np.zeros_like(W)
    valid = np.zeros(len(W), bool)
    dist, idx = tree.query(W[candidates], k=16)
    for row, v in enumerate(candidates):
        for d, j in zip(dist[row], idx[row]):
            if d > args.max_projection*2:
                break
            b = skin_ids[j]
            if BN[b]@VN[v] > 0.5:
                o = -((W[v]-BP[b])@BN[b])*BN[b]
                if np.linalg.norm(o) <= args.max_projection:
                    offset[v] = o
                    valid[v] = True
                break
    w = valid.astype(float)
    for _ in range(2):
        new = offset.copy()
        for v in candidates:
            nb = neighbours[v]
            total = w[v]+0.5*w[nb].sum()
            if total > 0:
                new[v] = (offset[v]*w[v]+0.5*(offset[nb]*w[nb, None]).sum(0))/total
        offset = new
    offset *= region[:, None]
    final_all = warped_all.copy()
    final_all[src_idx] = W+offset
    # Eyes are placed explicitly and rigidly: the build rebuilds each eyeball
    # at the eye joint with the median helper radius, so the helper sphere is
    # reset to a 12 mm radius (MakeHuman's is 17 mm) centred behind Asset B's
    # measured pupil, cornea apex on B's eye surface. Interpolated layer
    # displacements must never inflate or shear it.
    forward = (s*R)@np.array([0.0, -1.0, 0.0])
    forward /= np.linalg.norm(forward)
    eye_report = dict(eye_report)
    group_ids = {g: sorted({i for f in fs for i, _ in f}) for g, fs in groups.items()}
    for side, pupil in (('l', 473), ('r', 468)):
        target = np.array(B[str(pupil)]['world'])-forward*(args.eye_radius+0.002)
        joint = np.array(group_ids[f'joint-{side}-eye'])
        centre = final_all[joint].mean(0)
        shift = target-centre
        for g in (f'joint-{side}-eye', f'joint-{side}-eye-target'):
            final_all[group_ids[g]] += shift
        helper = np.array(group_ids[f'helper-{side}-eye'])
        dirs = final_all[helper]+shift-target
        dirs /= np.maximum(np.linalg.norm(dirs, axis=1, keepdims=True), 1e-9)
        final_all[helper] = target+dirs*args.eye_radius
        eye_report[f'eyeball_{side}'] = {'centre_m': target.tolist(), 'radius_m': args.eye_radius,
                                         'pupil_landmark_m': B[str(pupil)]['world'], 'shift_mm': float(np.linalg.norm(shift)*1000)}
    d_world = final_all-world_all
    source_offsets = np.stack((d_world[:, 0], d_world[:, 2], -d_world[:, 1]), axis=1)/scale
    np.savez_compressed(args.output, source_index=np.arange(len(source_offsets)), source_offsets=source_offsets,
                        stage='post_pose')
    moved = np.linalg.norm(offset, axis=1)
    report = {'stage': 'source_head_wrap_asset_b', 'landmarks': len(ids),
              'similarity': {'scale': float(s), 'rotation_deg': float(np.degrees(np.arccos(np.clip((np.trace(R)-1)/2, -1, 1))))},
              'tps_landmark_rms_mm': float(np.sqrt((np.linalg.norm(tps_fit, axis=1)**2).mean())*1000),
              'tps_max_vertex_displacement_mm': float(np.linalg.norm(disp_all, axis=1).max()*1000),
              'projected_vertices': int(valid.sum()), 'projection_candidates': int(len(candidates)),
              'projection_mm': {'median': float(np.median(moved[valid])*1000) if valid.any() else 0.0,
                                'p95': float(np.percentile(moved[valid], 95)*1000) if valid.any() else 0.0},
              'eyelids': eye_report,
              'note': 'Face shape adopted from Asset B (user model); lid opening set toward the original '
                      'references; topology, UVs, weights unchanged'}
    Path(args.report).write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=1))


if __name__ == '__main__':
    main()
