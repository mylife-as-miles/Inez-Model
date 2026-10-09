"""Wrap Inez's animation topology onto the reshaped scan (no Blender; numpy + scipy).

    python3 -I tools/inez/scan_wrap.py --inez-mesh inez.npz --scan-mesh scan_L4.npz --fit scan_fitted.npz \
        --masks scan_masks.npz --inez-landmarks inez_landmarks.json --fit-report scan_fit_report.json \
        --output scan_wrap.npz --report scan_wrap_report.json

Moves only face-region vertices of the existing MakeHuman/Inez mesh (topology,
UVs, weights and loops are untouched) onto the reshaped scan surface. The
result is stored per MakeHuman source vertex as an identity layer
(Inez_ScanWrap_<rev>), never baked into the base shape.

Excluded: eye-socket and mouth-interior islands plus two rings around them
(lid margins and inner lips keep their animation shape), ears, the scalp
above the scan's skin, and any target the masks mark as hair, scanned
eyeball or the scan's closed lip seam. Offsets are clamped, lightly smoothed
over the mesh (the low-poly mesh can only hold what its vertices resolve; finer
detail goes to the baked normal map) and faded at the region border.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from head_uv import head_islands, head_weight_vector
from model_source import read_obj

SOURCE_UNIT_M = 0.10589
MAX_OFFSET = 0.004


def arguments():
    parser = argparse.ArgumentParser()
    for name in ('inez-mesh', 'scan-mesh', 'fit', 'masks', 'inez-landmarks', 'fit-report', 'output', 'report'):
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--smooth-iterations', type=int, default=2)
    return parser.parse_args()


def vertex_normals(points, triangles):
    n = np.zeros_like(points)
    a, b, c = (points[triangles[:, k]] for k in range(3))
    f = np.cross(b-a, c-a)
    for k in range(3):
        np.add.at(n, triangles[:, k], f)
    return n/np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def adjacency(count, triangles):
    pairs = np.concatenate([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]])
    pairs = np.concatenate([pairs, pairs[:, ::-1]])
    pairs = np.unique(pairs, axis=0)
    neighbors = [[] for _ in range(count)]
    for a, b in pairs:
        neighbors[a].append(b)
    return neighbors


def rings(neighbors, seeds, depth):
    ring = np.full(len(neighbors), depth+1)
    frontier = list(seeds)
    ring[frontier] = 0
    for level in range(1, depth+1):
        nxt = []
        for v in frontier:
            for n in neighbors[v]:
                if ring[n] > level:
                    ring[n] = level
                    nxt.append(n)
        frontier = nxt
    return ring


def main():
    args = arguments()
    inez = np.load(args.inez_mesh)
    scan = np.load(args.scan_mesh)
    fit = np.load(args.fit)
    masks = np.load(args.masks)
    V = inez['vertices'].astype(np.float64)
    tri = inez['triangles']
    src = inez['makehuman_source_index']
    F = fit['fitted'].astype(np.float64)
    FN = vertex_normals(F, scan['triangles'])
    VN = vertex_normals(V, tri)
    lm = json.loads(Path(args.inez_landmarks).read_text())['landmarks']
    used = json.loads(Path(args.fit_report).read_text())['landmark_ids']
    L = np.array([lm[str(i)]['world'] for i in used])
    # Region: face within 18 mm of a used landmark, fading out by 30 mm.
    d_land, _ = cKDTree(L).query(V)
    region = np.clip(1-(d_land-0.018)/0.012, 0, 1)
    ear_x = max(abs(lm['234']['world'][0]), abs(lm['454']['world'][0]))
    region *= np.clip(1-(np.abs(V[:, 0])-ear_x)/0.004, 0, 1)
    # Socket and mouth-interior islands (plus two rings) keep their shape.
    points, texcoords, groups = read_obj()
    faces = groups['body']
    islands = head_islands(points, faces, head_weight_vector())
    protected_src = {i for name in ('mouth_interior', 'eye_socket_R', 'eye_socket_L') for f in islands[name] for i, _ in faces[f]}
    seeds = np.flatnonzero(np.isin(src, list(protected_src)))
    ring = rings(adjacency(len(V), tri), seeds, 3)
    protect = np.choose(np.minimum(ring, 3), [0.0, 0.0, 0.5, 1.0])
    region *= protect
    candidates = np.flatnonzero(region > 0)
    ok = masks['detail'] > 0.5
    tree = cKDTree(F)
    offsets = np.zeros_like(V)
    valid = np.zeros(len(V), bool)
    reasons = {'no_valid_target': 0, 'too_far': 0}
    dist, idx = tree.query(V[candidates], k=32)
    for row, v in enumerate(candidates):
        choice = None
        for d, j in zip(dist[row], idx[row]):
            if ok[j] and FN[j]@VN[v] > 0.5:
                choice = j
                break
        if choice is None:
            reasons['no_valid_target'] += 1
            continue
        o = -((V[v]-F[choice])@FN[choice])*FN[choice]
        if np.linalg.norm(o) > MAX_OFFSET:
            reasons['too_far'] += 1
            continue
        offsets[v] = o
        valid[v] = True
    neighbors = adjacency(len(V), tri)
    w = valid.astype(float)
    for _ in range(args.smooth_iterations):
        new = offsets.copy()
        for v in candidates:
            nb = neighbors[v]
            weight = w[v]+0.5*w[nb].sum()
            if weight > 0:
                new[v] = (offsets[v]*w[v]+0.5*(offsets[nb]*w[nb, None]).sum(0))/weight
        offsets = new
    offsets *= region[:, None]
    # Source-unit deltas per MakeHuman vertex: world (X, Y, Z) = (x, -z, y)*s.
    source_offsets = np.stack((offsets[:, 0], offsets[:, 2], -offsets[:, 1]), axis=1)/SOURCE_UNIT_M
    moved = np.linalg.norm(offsets, axis=1)
    np.savez_compressed(args.output, source_index=src.astype(np.int64), world_offsets=offsets.astype(np.float32),
                        source_offsets=source_offsets.astype(np.float32), region=region.astype(np.float32), valid=valid)
    report = {'stage': 'scan_wrap', 'candidates': int(len(candidates)), 'valid': int(valid.sum()), 'skipped': reasons,
              'moved_vertices_over_0.2mm': int((moved > 0.0002).sum()),
              'offset_mm': {'median_moved': float(np.median(moved[moved > 0.0002])*1000) if (moved > 0.0002).any() else 0.0,
                            'p95': float(np.percentile(moved[moved > 0.0002], 95)*1000) if (moved > 0.0002).any() else 0.0,
                            'max': float(moved.max()*1000)},
              'max_offset_clamp_mm': MAX_OFFSET*1000, 'smooth_iterations': args.smooth_iterations,
              'protected': 'eye-socket and mouth-interior islands + 2 rings; ears; non-face region',
              'storage': 'per MakeHuman source vertex, source units (x lateral, y up, z forward)'}
    Path(args.report).write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=1))


if __name__ == '__main__':
    main()
