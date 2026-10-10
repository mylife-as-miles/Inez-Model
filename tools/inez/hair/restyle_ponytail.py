"""Restyle the fitted Ponytail MessyWavy cards toward Inez's reference ponytail.

    python3 -I tools/inez/hair/restyle_ponytail.py --glb assets/characters/inez/model/v06/inez_recovery_v06.glb \
        --fit FIT.npz --out RESTYLED.npz --guides GUIDES.npz --report REPORT.json

The package is a short, high crown ponytail whose tail rises and falls to ear
level. The two original references show the hair gathered at the back of the
head and the tail hanging straight down past the collar to the upper back.
Inez's existing ponytail joints (hair.01 -> hair.04) already trace that path,
so they define the new tail axis:

1. Tie: every on-scalp vertex near the package tie is moved toward hair.01
   (Gaussian falloff, 6 cm), then put back at its original height above her
   scalp, so the front hairline does not move.
2. Tail: each ponytail card's free part is re-laid along the joint chain by
   arc length (lengthened so the median tail reaches the chain end). Its offset
   from the tail bundle's mean axis and its own width and waves are carried
   over by parallel-transported frames; a short blend joins it to the tie.
3. Collisions with skin and sweater, then skin weights (head -> hair.01-04 by
   arc length) and the scalp-pinning factor are recomputed.
4. Guide curves: one 16-point centreline per card, for the MainHair groom.
Face-framing and side strands keep the fitted shape.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import v06_identity_normals_glb as glbmod  # noqa: E402
glbmod.NC['MAT4'] = 16
from v06_identity_normals_glb import GLB  # noqa: E402
from fit_hair_cards import Surface, node_world, rendered_mesh, weld, smooth_on_mesh  # noqa: E402


def centreline(P, ids, s, samples):
    """Weighted card centre at each sample parameter."""
    out = np.zeros((len(samples), 3))
    band = .75 / max(len(samples) - 1, 1)
    for k, sk in enumerate(samples):
        d = np.abs(s[ids] - sk); w = np.clip(1 - d / band, 0, None)
        if w.sum() == 0:
            w = (d == d.min()).astype(float)
        out[k] = (P[ids] * w[:, None]).sum(0) / w.sum()
    return out


def arclength(Q):
    return np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))])


def resample(Q, step, length=None):
    a = arclength(Q); L = a[-1] if length is None else length
    t = np.arange(0, L + 1e-9, step)
    return np.stack([np.interp(t, a, Q[:, i]) for i in range(3)], 1), t


def transport_frames(A, n0):
    """Parallel-transported orthonormal frames (columns T, N, B) along a polyline."""
    T = np.gradient(A, axis=0); T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-12)
    F = np.zeros((len(A), 3, 3))
    n = n0 - T[0] * (n0 @ T[0]); n /= np.linalg.norm(n)
    for i in range(len(A)):
        if i:
            n = n - T[i] * (n @ T[i]); n /= max(np.linalg.norm(n), 1e-12)
        F[i] = np.stack([T[i], n, np.cross(T[i], n)], 1)
    return F


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--glb', required=True)
    ap.add_argument('--fit', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--guides', required=True)
    ap.add_argument('--report', required=True)
    ap.add_argument('--tie-sigma', type=float, default=.06)
    ap.add_argument('--tie-radius', type=float, default=.04)
    ap.add_argument('--tail-reach', type=float, default=1.0, help='median tail length as a fraction of the joint chain length')
    ap.add_argument('--spread', type=float, default=.7, help='scale of each card offset from the tail axis')
    ap.add_argument('--length-power', type=float, default=.6)
    ap.add_argument('--blend', type=float, default=.04, help='arc length over which the tail joins the tie')
    ap.add_argument('--guide-points', type=int, default=16)
    args = ap.parse_args()

    glb = GLB(args.glb); j = glb.json; W = node_world(j)
    names = {n.get('name'): i for i, n in enumerate(j['nodes'])}
    body = Surface(*weld(*rendered_mesh(glb, names['Inez_ContinuousHumanMesh_UNAPPROVED'], W)))
    cloth = [rendered_mesh(glb, i, W) for i, n in enumerate(j['nodes']) if n.get('name', '').startswith(('Inez_Sweater', 'Inez_FineSilverNecklace')) and 'mesh' in n]
    clothS = Surface(np.vstack([p for p, _ in cloth]), np.vstack([f + sum(len(q) for q, _ in cloth[:k]) for k, (_, f) in enumerate(cloth)]))
    skin = j['skins'][0]; jn = [j['nodes'][i]['name'] for i in skin['joints']]
    chain_names = ['hair.01', 'hair.02', 'hair.03', 'hair.04']
    heads = np.array([W[skin['joints'][jn.index(n)]][:3, 3] for n in chain_names])
    chain = np.vstack([heads, heads[-1] + (heads[-1] - heads[-2])])

    fit = dict(np.load(args.fit))
    P = fit['position'].astype(float).copy(); N = fit['normal'].astype(float).copy()
    s = fit['s'].astype(float); free = fit['free'].astype(float); card = fit['card'].astype(int)
    n_cards = card.max() + 1
    cards = [np.where(card == c)[0] for c in range(n_cards)]
    order = [ids[np.argsort(s[ids])] for ids in cards]
    height0, _, _ = body.signed(P)

    # ---- classify ponytail cards: everything gathered at the package tie.
    # The tie is where the lifting cards converge (median lift-off point behind
    # and above the ears); a ponytail card passes within --tie-radius of it and
    # its tail is the part after its closest approach.
    lift_s = np.ones(n_cards); lift_p = np.full((n_cards, 3), np.nan)
    for c, o in enumerate(order):
        fr = free[o]
        if fr.max() >= .5:
            k = int(np.argmax(fr > .05)); lift_s[c] = s[o[k]]; lift_p[c] = P[o[k]]
    behind = (lift_p[:, 2] < -.04) & (lift_p[:, 1] > 1.68)
    tie_old = np.median(lift_p[behind], axis=0)
    tail = np.zeros(n_cards, bool); tie_s = np.ones(n_cards)
    for c, o in enumerate(order):
        sk = np.linspace(0, 1, 48); Q = centreline(P, o, s, sk)
        d = np.linalg.norm(Q - tie_old, axis=1); k = int(np.argmin(d))
        rest = arclength(Q[k:])[-1] if k < len(Q) - 1 else 0
        if d[k] < args.tie_radius and rest > .03 and free[o].max() > .5:
            tail[c] = True; tie_s[c] = sk[k]
    lift_s = np.where(tail, tie_s, lift_s)
    # new tie: on the scalp surface behind hair.01 (the old ponytail root)
    p_tie, n_tie, _, _ = body.query(chain[:1]); tie_new = p_tie[0] + n_tie[0] * .004
    chain = np.vstack([tie_new, chain[1:]])

    # ---- 1. move the scalp part toward the new tie, keep the height above the scalp
    before_tie = s < lift_s[card]
    on_scalp = (free < 1) | before_tie
    w = np.exp(-(np.linalg.norm(P - tie_old, axis=1) / args.tie_sigma) ** 2) * on_scalp
    moved = P + w[:, None] * (tie_new - tie_old)
    proj, nrm, _, _ = body.query(moved)
    P_scalp = np.where(on_scalp[:, None], proj + nrm * height0[:, None], P)
    P_scalp = np.where((w > 1e-4)[:, None], P_scalp, P)

    # ---- 2. tail bundle axis (arc length from each card's lift-off point)
    step = .005
    tails = {}
    for c in np.where(tail)[0]:
        o = order[c]; sk = np.linspace(lift_s[c], 1, 24)
        Q = centreline(P, o, s, sk)
        tails[c] = (sk, Q, arclength(Q))
    lengths = np.array([v[2][-1] for v in tails.values()])
    A_len = np.quantile(lengths, .8)
    grid = np.arange(0, A_len + 1e-9, step)
    acc = np.zeros((len(grid), 3)); cnt = np.zeros(len(grid))
    for sk, Q, a in tails.values():
        m = grid <= a[-1]
        acc[m] += np.stack([np.interp(grid[m], a, Q[:, i]) for i in range(3)], 1); cnt[m] += 1
    A = acc / np.maximum(cnt, 1)[:, None]
    head_c = body.P[body.P[:, 1] > 1.6].mean(0)
    FA = transport_frames(A, A[0] - head_c)
    chain_len = arclength(chain)[-1]
    # Per-card target length: the longest tails (90th percentile) end at the
    # chain end (upper back); shorter ones scale sub-linearly, so the tail
    # stays layered and no card is stretched past the chain.
    q90 = np.quantile(lengths, .9)
    target_len = {c: args.tail_reach * chain_len * min(1.0, tails[c][2][-1] / q90) ** args.length_power for c in tails}
    k_card = {c: max(1.0, target_len[c] / max(tails[c][2][-1], 1e-6)) for c in tails}
    k_len = float(np.median(list(k_card.values())))
    C_dense, Ct = resample(chain, step)
    reach = max(target_len.values())
    if Ct[-1] < reach:   # extend straight past the last joint if needed
        extra = np.arange(Ct[-1] + step, reach + step, step)
        d = (chain[-1] - chain[-2]) / np.linalg.norm(chain[-1] - chain[-2])
        C_dense = np.vstack([C_dense, chain[-1] + (extra - arclength(chain)[-1])[:, None] * d]); Ct = np.r_[Ct, extra]
    FC = transport_frames(C_dense, C_dense[0] - head_c)

    def axis_at(F, X, t, grid_t):
        i = np.clip(np.searchsorted(grid_t, t) - 1, 0, len(grid_t) - 2)
        u = np.clip((t - grid_t[i]) / (grid_t[i + 1] - grid_t[i]), 0, 1)[:, None]
        return X[i] * (1 - u) + X[i + 1] * u, F[np.where(u[:, 0] < .5, i, i + 1)]

    P_new = P_scalp.copy(); N_new = N.copy(); tail_param = np.full(len(P), -1.0)
    for c, (sk, Q, a) in tails.items():
        o = order[c]; vt = o[s[o] >= lift_s[c]]
        av = np.interp(s[vt], sk, a)                                   # arc length of each vertex
        Qv = np.stack([np.interp(s[vt], sk, Q[:, i]) for i in range(3)], 1)
        Av, Fa = axis_at(FA, A, np.minimum(av, A_len), grid)
        Cv, Fc = axis_at(FC, C_dense, av * k_card[c], Ct)
        R = np.einsum('nij,nkj->nik', Fc, Fa)                          # Fc * Fa^T
        off_card = np.einsum('nij,nj->ni', R, (Qv - Av) * args.spread)
        off_vert = np.einsum('nij,nj->ni', R, P[vt] - Qv)
        newp = Cv + off_card + off_vert
        # join to the (moved) lift-off point over the first --blend metres
        joint = P_scalp[o[min(np.searchsorted(s[o], lift_s[c]), len(o) - 1)]]
        start = newp[np.argmin(av)]
        fade = np.clip(1 - av / args.blend, 0, 1)[:, None]
        newp += fade * (joint - start)
        P_new[vt] = newp; N_new[vt] = np.einsum('nij,nj->ni', R, N[vt]); tail_param[vt] = av * k_card[c] / chain_len

    # ---- 3. collisions for moved vertices (skin 1.5 mm, cloth 3 mm), smoothed then hard
    F = fit['triangles'].astype(np.int64)
    movable = (np.linalg.norm(P_new - P, axis=1) > 1e-6) & (free > 0)
    before = P_new.copy(); rounds = []
    for rnd in range(10):
        sd_b, _, nb = body.signed(P_new); sd_c, _, nc = clothS.signed(P_new)
        push = np.zeros_like(P_new)
        bb = movable & (sd_b < .0015 - 1e-4); push[bb] += nb[bb] * (.0015 - sd_b[bb])[:, None]
        bc = movable & (sd_c < .003 - 1e-4) & (sd_c > -.05); push[bc] += nc[bc] * (.003 - sd_c[bc])[:, None]
        rounds.append([int(bb.sum()), int(bc.sum())])
        if not (bb.any() or bc.any()):
            break
        if rnd < 3:
            disp = smooth_on_mesh(push, F, len(P_new), 6)
            P_new += np.maximum(np.linalg.norm(push, axis=1), np.linalg.norm(disp, axis=1))[:, None] * (disp / np.maximum(np.linalg.norm(disp, axis=1, keepdims=True), 1e-12))
        else:
            P_new += push
    sd_b, _, _ = body.signed(P_new)

    # ---- free factor and weights (head -> hair chain by arc length along the tail)
    free_new = np.clip((sd_b - .012) / .018, 0, 1)
    for o in order:
        free_new[o] = np.maximum.accumulate(free_new[o])
    head_j = jn.index('head'); hair_j = [jn.index(n) for n in chain_names]
    seg = np.linalg.norm(np.diff(chain, axis=0), axis=1); centers = (np.r_[0, np.cumsum(seg)][:-1] + seg / 2) / seg.sum()
    joints = np.zeros((len(P), 4), np.uint16); weights = np.zeros((len(P), 4), np.float32)
    joints[:, 0] = head_j; weights[:, 0] = 1
    for v in np.where(tail_param >= 0)[0]:
        u = tail_param[v]; wb = free_new[v]
        k = int(np.clip(np.searchsorted(centers, u) - 1, 0, 3)); k2 = min(k + 1, 3)
        t = 0.0 if k == k2 or u < centers[0] else float(np.clip((u - centers[k]) / (centers[k2] - centers[k]), 0, 1))
        joints[v] = [head_j, hair_j[k], hair_j[k2], 0]
        weights[v] = [1 - wb, wb * (1 - t), wb * t, 0]
        if k == k2:
            weights[v, 1] = wb; weights[v, 2] = 0
    weights /= weights.sum(1, keepdims=True)
    joints = np.where(weights > 0, joints, 0).astype(np.uint16)

    out = dict(fit); out.update(position=P_new.astype(np.float32), normal=(N_new / np.linalg.norm(N_new, axis=1, keepdims=True)).astype(np.float32),
                               free=free_new.astype(np.float32), joints=joints, weights=weights)
    np.savez_compressed(args.out, **out)

    # ---- 4. guide curves (card centrelines)
    G = args.guide_points; gs = np.linspace(0, 1, G)
    guides = np.stack([centreline(P_new, ids, s, gs) for ids in cards]).astype(np.float32)
    gfree = np.stack([np.interp(gs, s[o], free_new[o]) for o in order]).astype(np.float32)
    root_n = np.stack([body.query(g[:1])[1][0] for g in guides]).astype(np.float32)
    np.savez_compressed(args.guides, points=guides, free=gfree, root_normal=root_n, card=np.arange(n_cards, dtype=np.int32), tail=tail)

    report = {'tool': 'tools/inez/hair/restyle_ponytail.py', 'artistic_approval': False,
              'input_fit_sha256': hashlib.sha256(Path(args.fit).read_bytes()).hexdigest(),
              'tie_old_m': tie_old.tolist(), 'tie_new_m': tie_new.tolist(), 'tie_shift_m': float(np.linalg.norm(tie_new - tie_old)),
              'ponytail_cards': int(tail.sum()), 'tail_length_median_m': float(np.median(lengths)), 'chain_length_m': float(chain_len),
              'lengthening_median': float(k_len), 'lengthening_max': float(max(k_card.values())), 'target_length_m': {'min': float(min(target_len.values())), 'max': float(max(target_len.values()))}, 'tail_tip_y_m': {'min': float(P_new[tail_param >= 0, 1].min()), 'median_tip': float(np.median([P_new[order[c][-1], 1] for c in np.where(tail)[0]]))},
              'collision_rounds_body_cloth': rounds, 'min_skin_clearance_moved_m': float(sd_b[movable].min()) if movable.any() else None,
              'max_move_m': float(np.linalg.norm(P_new - P, axis=1).max()),
              'guides': {'count': int(n_cards), 'points': G}, 'free': {'pinned': int((free_new == 0).sum()), 'free': int((free_new >= 1).sum())}}
    Path(args.report).write_text(json.dumps(report, indent=1) + '\n')
    print(json.dumps(report, indent=1))


if __name__ == '__main__':
    main()
