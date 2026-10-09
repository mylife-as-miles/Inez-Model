"""Reshape the Ten24 scan into Inez's proportions (no Blender; numpy + scipy).

    python3 tools/inez/scan_fit.py --scan-mesh scan_L4.npz --inez-mesh inez.npz \
        --scan-landmarks scan_landmarks.json --inez-landmarks inez_landmarks.json \
        --output scan_fitted.npz --report report.json

Pass 1 (align): similarity transform from robust frontal landmarks.
Pass 2 (landmark warp): smoothed thin-plate spline moving every reliable scan
    landmark onto the matching Inez landmark (both detected with the same
    cameras by scan_landmarks.py). Grazing silhouette hits are excluded.
Pass 3 (frequency split): the normal-direction residual from the warped scan
    to Inez's smooth (subdivided) head is Gaussian-filtered over the scan
    surface and added back. Inez therefore keeps every shape broader than the
    filter (skull, cheeks, jaw, brow ridge, nose and lip volumes), while the
    scan contributes only finer real anatomy (lid folds, creases, nostril and
    lip borders, ear relief). Feature regions use a wider filter than broad
    cheek/forehead/jaw areas so less donor shape survives where the male donor
    differs most.
The scan is not Inez; this script only moves scan vertices and records how.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy.interpolate import RBFInterpolator
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scan_landmark_sets import FEATURE, FACE_OVAL, IRIS, LIPS_INNER, LIPS_OUTER, NOSE, LEFT_EYE, RIGHT_EYE

# Inner-lip points follow the mouth opening (closed on the scan, parted on
# Inez) and the upper face outline follows the hairline; neither is a
# surface correspondence. Lip corners stay.
EXCLUDED = (set(LIPS_INNER)-{78, 308}) | {10, 338, 297, 332, 284, 251, 389, 356, 127, 162, 21, 54, 103, 67, 109}

STABLE_FRONTAL = [33, 133, 362, 263, 168, 6, 197, 195, 5, 4, 1, 2, 98, 327, 61, 291, 0, 17]


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scan-mesh', required=True)
    parser.add_argument('--inez-mesh', required=True)
    parser.add_argument('--scan-landmarks', required=True)
    parser.add_argument('--inez-landmarks', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--sigma-feature', type=float, default=0.0045)
    parser.add_argument('--sigma-broad', type=float, default=0.0025)
    parser.add_argument('--min-facing', type=float, default=0.30)
    parser.add_argument('--smooth-feature', type=float, default=2e-4)
    parser.add_argument('--smooth-other', type=float, default=3e-3)
    return parser.parse_args()


def umeyama(src, dst):
    ms, md = src.mean(0), dst.mean(0)
    xs, xd = src-ms, dst-md
    U, D, Vt = np.linalg.svd(xd.T@xs/len(src))
    E = np.eye(3)
    if np.linalg.det(U)*np.linalg.det(Vt) < 0:
        E[2, 2] = -1
    R = U@E@Vt
    s = np.trace(np.diag(D)@E)/(xs**2).sum(1).mean()
    return s, R, md-s*R@ms


def vertex_normals(points, triangles):
    n = np.zeros_like(points)
    a, b, c = (points[triangles[:, k]] for k in range(3))
    f = np.cross(b-a, c-a)
    for k in range(3):
        np.add.at(n, triangles[:, k], f)
    return n/np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def gaussian_smooth(points, values, weights, sigma, anchors_step=0.0015):
    """Normalized Gaussian filter of per-point vectors over a dense surface sampling.

    Evaluated on a voxel-subsampled anchor set, then interpolated back to every
    point with a narrow Gaussian over the nearest anchors.
    """
    keys = np.floor(points/anchors_step).astype(np.int64)
    _, first = np.unique(keys, axis=0, return_index=True)
    anchors = points[first]
    tree = cKDTree(points)
    smooth = np.zeros((len(anchors), values.shape[1]))
    total = np.zeros(len(anchors))
    for start in range(0, len(anchors), 4000):
        chunk = anchors[start:start+4000]
        hood = tree.query_ball_point(chunk, 3*sigma)
        for k, ids in enumerate(hood):
            ids = np.asarray(ids)
            if not len(ids):
                continue
            g = np.exp(-np.sum((points[ids]-chunk[k])**2, axis=1)/(2*sigma**2))*weights[ids]
            total[start+k] = g.sum()
            smooth[start+k] = g@values[ids]
    valid = total > 1e-6
    smooth[valid] /= total[valid, None]
    anchor_tree = cKDTree(anchors[valid])
    d, idx = anchor_tree.query(points, k=8)
    g = np.exp(-d**2/(2*(anchors_step*1.2)**2))
    g /= np.maximum(g.sum(1, keepdims=True), 1e-12)
    coverage = np.zeros(len(points))
    cov_anchor = np.clip(total[valid]/np.percentile(total[valid], 60), 0, 1)
    coverage = (g*cov_anchor[idx]).sum(1)
    return (g[:, :, None]*smooth[valid][idx]).sum(1), coverage


def main():
    args = arguments()
    scan = np.load(args.scan_mesh)
    inez = np.load(args.inez_mesh)
    A = json.loads(Path(args.scan_landmarks).read_text())['landmarks']
    B = json.loads(Path(args.inez_landmarks).read_text())['landmarks']
    main_object = json.loads(Path(args.inez_landmarks).read_text())['object']
    report = {'passes': {}}

    def usable(i):
        a, b = A.get(str(i)), B.get(str(i))
        return (a and b and i not in IRIS and i not in EXCLUDED and a['facing'] >= args.min_facing and b['facing'] >= args.min_facing
                and b.get('object', main_object) == main_object)
    ids = [i for i in range(468) if usable(i)]
    src = np.array([A[str(i)]['world'] for i in ids])
    dst = np.array([B[str(i)]['world'] for i in ids])
    stable = [ids.index(i) for i in STABLE_FRONTAL if i in ids]
    s, R, t = umeyama(src[stable], dst[stable])
    P = scan['vertices'].astype(np.float64)@(s*R).T+t
    src_aligned = src@(s*R).T+t
    err = np.linalg.norm(src_aligned-dst, axis=1)
    report['passes']['1_align'] = {'scale': float(s), 'rotation_deg': float(np.degrees(np.arccos(np.clip((np.trace(R)-1)/2, -1, 1)))),
                                   'stable_landmarks': len(stable), 'used_landmarks': len(ids),
                                   'landmark_rms_mm': float(np.sqrt((err**2).mean())*1000), 'landmark_max_mm': float(err.max()*1000)}
    # Pass 2: smoothed TPS. Feature landmarks are trusted more than the
    # model-interpolated cheek/forehead points and the face outline.
    smoothing = np.array([args.smooth_feature if i in FEATURE else args.smooth_other for i in ids])
    tps = RBFInterpolator(src_aligned, dst-src_aligned, kernel='thin_plate_spline', smoothing=smoothing, degree=1)
    disp = np.vstack([tps(P[k:k+20000]) for k in range(0, len(P), 20000)])
    # Far from the face the spline only extrapolates; fade it toward the mean
    # landmark displacement beyond 9 cm from the nearest landmark.
    d_land, _ = cKDTree(src_aligned).query(P)
    fade = np.clip((d_land-0.06)/0.03, 0, 1)[:, None]
    disp = disp*(1-fade)+(dst-src_aligned).mean(0)*fade
    W = P+disp
    after = np.linalg.norm(tps(src_aligned)+src_aligned-dst, axis=1)
    feat = np.array([i in FEATURE for i in ids])
    report['passes']['2_landmark_warp'] = {'kernel': 'thin_plate_spline', 'smoothing_feature': args.smooth_feature,
                                           'smoothing_other': args.smooth_other,
                                           'feature_landmark_rms_mm': float(np.sqrt((after[feat]**2).mean())*1000),
                                           'landmark_rms_mm': float(np.sqrt((after**2).mean())*1000),
                                           'landmark_max_mm': float(after.max()*1000),
                                           'max_vertex_displacement_mm': float(np.linalg.norm(disp, axis=1).max()*1000)}
    # Pass 3: frequency split against Inez's smooth head surface.
    land = np.array([B[str(i)]['world'] for i in ids])
    chin_z = B['152']['world'][2]
    sub = inez['sub_vertices'].astype(np.float64)
    subn = inez['sub_normals'].astype(np.float64)
    head = sub[:, 2] > chin_z-0.10
    sub, subn = sub[head], subn[head]
    tree = cKDTree(sub)
    dist, near = tree.query(W)
    n_s = subn[near]
    offset = W-sub[near]
    normal_part = np.sum(offset*n_s, axis=1)
    lateral = np.linalg.norm(offset-normal_part[:, None]*n_s, axis=1)
    scan_normals = vertex_normals(W, scan['triangles'])
    agree = np.sum(scan_normals*n_s, axis=1)
    residual = -normal_part[:, None]*n_s
    valid = (lateral < 0.004) & (agree > 0.3) & (np.abs(normal_part) < 0.025)
    w = valid.astype(float)*np.clip((agree-0.3)/0.4, 0, 1)
    smooth_feature, cov_f = gaussian_smooth(W, residual, w, args.sigma_feature)
    smooth_broad, cov_b = gaussian_smooth(W, residual, w, args.sigma_broad)
    # Feature mask: distance to eye, nose and lip landmarks on Inez.
    feature_pts = np.array([B[str(i)]['world'] for i in RIGHT_EYE+LEFT_EYE+NOSE+LIPS_OUTER+LIPS_INNER if str(i) in B])
    d_feat, _ = cKDTree(feature_pts).query(W)
    feature = np.clip(1-(d_feat-0.006)/0.008, 0, 1)
    smooth = smooth_feature*feature[:, None]+smooth_broad*(1-feature[:, None])
    coverage = cov_f*feature+cov_b*(1-feature)
    F = W+smooth*np.clip(coverage, 0, 1)[:, None]
    # Diagnostics on the face region (within 2 cm of any landmark).
    face = d_land < 0.02
    res_after = []
    _, near_f = tree.query(F[face])
    res_after = np.abs(np.sum((F[face]-sub[near_f])*subn[near_f], axis=1))
    report['passes']['3_frequency_split'] = {
        'sigma_feature_mm': args.sigma_feature*1000, 'sigma_broad_mm': args.sigma_broad*1000,
        'valid_fraction_face': float(valid[face].mean()),
        'face_normal_residual_before_mm': {'median': float(np.median(np.abs(normal_part[face]))*1000),
                                           'p95': float(np.percentile(np.abs(normal_part[face]), 95)*1000)},
        'face_normal_residual_after_mm': {'median': float(np.median(res_after)*1000), 'p95': float(np.percentile(res_after, 95)*1000),
                                          'note': 'remaining offset = scan detail finer than the filter'}}
    np.savez_compressed(args.output, aligned=P.astype(np.float32), warped=W.astype(np.float32), fitted=F.astype(np.float32),
                        valid=valid, feature=feature.astype(np.float32), coverage=coverage.astype(np.float32),
                        landmark_distance=d_land.astype(np.float32), similarity=np.concatenate([[s], R.ravel(), t]))
    report['landmark_ids'] = ids
    report['inputs'] = {'scan_mesh': args.scan_mesh, 'inez_mesh': args.inez_mesh}
    Path(args.report).write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report['passes'], indent=1))


if __name__ == '__main__':
    main()
