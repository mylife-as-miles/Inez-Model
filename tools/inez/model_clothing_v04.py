"""v04 corrected sweater, jeans and platform boots on the licensed topology.

Revision v04 replaces the v03 garment shaping after actual-render review:

* Sweater: the torso hangs vertically from the bust/shoulder blades and keeps
  straight sides below the armpit instead of following the bust. Sleeves are
  smooth dropped-shoulder tubes around the real arm axis, gathered into ribbed
  cuffs. Hem, cuffs and crew neck are real rib extensions. Stripe phase comes
  from measurements of original B: three dark torso bands by height and five
  sleeve bands along the arm axis; the gray yoke, rib hem and cuffs stay gray.
* Jeans: straight barrel legs sized from B's width ratios, a back drape below
  the seat, and a gathered hem that overlaps the boot shaft (no skin gap).
* Boots: a platform under the foot (the caller lifts the character by the sole
  thickness), a footprint that encloses every foot/toe vertex with margins, a
  shaft weighted to the shin above the ankle and to the foot below it.

All inputs are MakeHuman source coordinates (x left, y up, z forward) unless a
name says otherwise. Importing the module creates nothing.
"""
import math

import bpy
import numpy as np
from mathutils import Vector

from model_build import mesh_from_group, attach_weights
from model_geometry import (mesh_object, tubes, loft, skin_rigid, skin_source_nearest,
                            actual_thickness, smooth_geometry, boundary_loops, torus_source)
from model_materials import material, detail_tile
from model_source import source_weight_vectors, joint_point

BODY_VERTICES = 13380
# Original-B stripe measurements (see qa/model/model_dressed_v04_manifest.json).
# Torso: fractions of the front neckline-to-hem span. Sleeves: fractions of the
# shoulder-to-cuff length along the arm axis.
TORSO_DARK_BANDS = ((0.115, 0.206), (0.366, 0.473), (0.664, 0.748))
SLEEVE_DARK_BANDS = ((0.040, 0.130), (0.330, 0.420), (0.550, 0.630), (0.740, 0.820), (0.900, 0.970))


def smoothstep(a, b, x):
    t = np.clip((np.asarray(x, float)-a)/(b-a), 0.0, 1.0)
    return t*t*(3.0-2.0*t)


class BodyWeights:
    """Normalized licensed weights reduced to regional arrays."""

    def __init__(self, weights):
        rows = source_weight_vectors(weights, range(BODY_VERTICES))
        self.rows = rows

        def total(prefixes, side=None):
            out = np.zeros(BODY_VERTICES)
            for i, row in rows.items():
                out[i] = sum(v for n, v in row.items()
                             if n.startswith(prefixes) and (side is None or n.endswith('.'+side)))
            return out
        self.arm = total(('upperarm', 'lowerarm', 'shoulder', 'wrist', 'finger', 'metacarpal'))
        self.upper_limb = total(('upperarm', 'lowerarm'))
        self.hand = total(('finger', 'wrist', 'metacarpal'))
        self.leg = {s: total(('upperleg', 'lowerleg', 'foot', 'toe'), s) for s in ('L', 'R')}
        self.foot = {s: total(('foot', 'toe'), s) for s in ('L', 'R')}
        self.head = total(('head', 'jaw', 'eye', 'levator', 'oris', 'orbicularis',
                           'oculi', 'risorius', 'temporalis', 'tongue', 'special', 'mandible'))


def vertex_normals(points, faces):
    points = np.asarray(points, float)
    normals = np.zeros_like(points)
    for face in faces:
        ids = [i for i, t in face]
        a, b, c = points[ids[:3]]
        normal = np.cross(b-a, c-a)
        if len(ids) == 4:
            normal += np.cross(c-a, points[ids[3]]-a)
        normals[ids] += normal
    lengths = np.linalg.norm(normals, axis=1)
    # Vertices that belong to no selected face keep a zero normal instead of a
    # division blow-up (the v03 hem spike came from such an unstable normal).
    normals[lengths > 1e-9] /= lengths[lengths > 1e-9, None]
    return normals


def convex_radius(points2d, center, angles):
    """Radius of the 2D convex hull of points2d along each angle from center."""
    pts = np.asarray(points2d, float)
    if len(pts) < 3:
        return np.zeros(len(angles))
    order = np.lexsort((pts[:, 1], pts[:, 0]))
    pts = pts[order]

    def cross(o, a, b):
        return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in pts[::-1]:
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = np.array(lower[:-1]+upper[:-1])-center
    result = np.zeros(len(angles))
    directions = np.stack((np.cos(angles), np.sin(angles)), axis=1)
    for i in range(len(hull)):
        a, b = hull[i], hull[(i+1) % len(hull)]
        edge = b-a
        # Solve a + s*edge = r*direction for s in [0,1], r > 0.
        det = directions[:, 0]*(-edge[1])-directions[:, 1]*(-edge[0])
        valid = np.abs(det) > 1e-12
        r = np.where(valid, (a[0]*(-edge[1])-a[1]*(-edge[0]))/np.where(valid, det, 1), 0)
        s = np.where(valid, (directions[:, 0]*a[1]-directions[:, 1]*a[0])/np.where(valid, det, 1), -1)
        hit = valid & (s >= -1e-9) & (s <= 1+1e-9) & (r > 0)
        result = np.where(hit, np.maximum(result, r), result)
    return result


def arm_frame(points, rig, side):
    """Shoulder -> elbow -> wrist polyline of the real joints (the A-pose
    forearm is not on the straight shoulder-wrist line)."""
    shoulder = np.array(joint_point(points, rig, rig['bones']['upperarm01.'+side]['head']))
    elbow = np.array(joint_point(points, rig, rig['bones']['lowerarm01.'+side]['head']))
    wrist = np.array(joint_point(points, rig, rig['bones']['wrist.'+side]['head']))
    return ArmAxis(shoulder, elbow, wrist)


class ArmAxis:
    def __init__(self, shoulder, elbow, wrist):
        self.points = [shoulder, elbow, wrist]
        self.lengths = [float(np.linalg.norm(elbow-shoulder)), float(np.linalg.norm(wrist-elbow))]
        self.length = sum(self.lengths)
        self.axis = (wrist-shoulder)/np.linalg.norm(wrist-shoulder)

    def locate(self, p):
        """Arc-length fraction t (0 shoulder, 1 wrist, extrapolated beyond),
        the axis point and the local unit tangent nearest to p."""
        best = None
        offset = 0.0
        for k in range(2):
            a, b = self.points[k], self.points[k+1]
            seg = b-a
            L = self.lengths[k]
            u = float((p-a).dot(seg))/(L*L)
            lo = -np.inf if k == 0 else 0.0
            hi = np.inf if k == 1 else 1.0
            uc = min(max(u, lo), hi)
            q = a+seg*uc
            d = float(np.linalg.norm(p-q))
            if best is None or d < best[0]:
                best = (d, (offset+uc*L)/self.length, q, seg/L)
            offset += L
        return best[1], best[2], best[3]


def leg_frame(points, rig, side):
    hip = np.array(joint_point(points, rig, rig['bones']['upperleg01.'+side]['head']))
    knee = np.array(joint_point(points, rig, rig['bones']['lowerleg01.'+side]['head']))
    ankle = np.array(joint_point(points, rig, rig['bones']['foot.'+side]['head']))
    return hip, knee, ankle


def interpolate_profile(t, table):
    keys = [k for k, v in table]
    values = [v for k, v in table]
    return np.interp(t, keys, values)


# -------------------------------------------------------------- relaxation

def garment_relax(P, faces, ids, body_points, body_faces, clearance, iterations=12, strength=0.5, fixed=None):
    """Laplacian relaxation of shaped garment vertices with a body-collision
    constraint: removes steps, creases and printed-through anatomy while every
    vertex stays at least `clearance` (per-vertex array or float) outside the
    licensed body surface."""
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    P = np.asarray(P, float).copy()
    ids = np.array(sorted(ids))
    index = {v: k for k, v in enumerate(ids)}
    neighbors = [set() for _ in ids]
    for face in faces:
        verts = [i for i, t in face]
        for a, b in zip(verts, verts[1:]+verts[:1]):
            neighbors[index[a]].add(index[b])
            neighbors[index[b]].add(index[a])
    boundary_count = {}
    for face in faces:
        verts = [i for i, t in face]
        for a, b in zip(verts, verts[1:]+verts[:1]):
            key = (min(a, b), max(a, b))
            boundary_count[key] = boundary_count.get(key, 0)+1
    on_boundary = np.zeros(len(ids), bool)
    for (a, b), count in boundary_count.items():
        if count == 1:
            on_boundary[index[a]] = on_boundary[index[b]] = True
    bvh = BVHTree.FromPolygons([Vector(p) for p in body_points[:BODY_VERTICES]],
                               [[i for i, t in f] for f in body_faces])
    clear = np.broadcast_to(np.asarray(clearance, float), (len(P),))
    lap_n = [np.array(sorted(n)) for n in neighbors]
    X = P[ids]
    for _ in range(iterations):
        avg = np.array([X[n].mean(axis=0) if len(n) else X[k] for k, n in enumerate(lap_n)])
        # Boundaries relax only along themselves (keep hem/cuff heights).
        step = (avg-X)*strength
        step[on_boundary, 1] = 0.0
        if fixed is not None:
            step[fixed[ids]] = 0.0
        X = X+step
        for k, v in enumerate(ids):
            q = Vector(X[k])
            nearest, normal, _, distance = bvh.find_nearest(q)
            if nearest is None:
                continue
            c = clear[v]
            outside = (q-nearest).dot(normal) >= 0
            if (outside and distance < c) or (not outside and distance < 0.12):
                X[k] = np.array(nearest+normal*c)
    P[ids] = X
    return P


# --------------------------------------------------------------------- sweater

class SweaterPlan:
    """Shaped sweater positions plus per-vertex parameters for texturing."""

    def __init__(self, points, weights, rig, levels):
        self.levels = levels
        self.points = np.asarray(points, float)
        self.weights = weights
        self.rig = rig
        self.arm_t = np.zeros(len(points))
        self.sleeve = np.zeros(len(points))
        self.arm_frames = {s: arm_frame(self.points, rig, s) for s in ('L', 'R')}

    def torso_table(self):
        """Per-height convex hull radii, draped downward from the armpit and
        smoothed so bust/nipple detail cannot print through the knit."""
        body = self.points[:BODY_VERTICES]
        w = self.weights
        lv = self.levels
        mask = (w.arm[:BODY_VERTICES] < 0.20) & (w.hand < 0.05) & (w.head < 0.30)
        mask &= (body[:, 1] > lv['hem_y']-0.6) & (body[:, 1] < lv['neck_y']+0.2)
        mask &= (w.leg['L']+w.leg['R']) < 0.3
        pts = body[mask]
        step = 0.06
        levels_y = np.arange(lv['hem_y']-0.5, lv['neck_y']+0.15, step)
        angles = np.linspace(-math.pi, math.pi, 181)
        centers, radii = [], []
        for y in levels_y:
            sel = pts[np.abs(pts[:, 1]-y) < step*0.75]
            if len(sel) < 8:
                centers.append(centers[-1] if centers else 0.3)
                radii.append(radii[-1] if radii else np.full(len(angles), 1.0))
                continue
            zc = 0.5*(sel[:, 2].min()+sel[:, 2].max())
            centers.append(zc)
            radii.append(convex_radius(sel[:, [0, 2]], np.array([0.0, zc]), angles))
        centers = np.array(centers)
        # One smooth center line so neighbouring rings stay coaxial.
        centers = np.convolve(np.pad(centers, 3, mode='edge'), np.ones(7)/7, mode='valid')
        radii = np.array(radii)
        draped = radii.copy()
        start = int(np.searchsorted(levels_y, lv['armpit_y']))
        for k in range(min(start, len(levels_y)-1)-1, -1, -1):
            draped[k] = np.maximum(radii[k], draped[k+1])
        side_weight = np.abs(np.cos(angles))
        for k, y in enumerate(levels_y):
            below = float(smoothstep(lv['armpit_y'], lv['hem_y'], y))
            draped[k] = draped[k]*(1.0-0.06*below*side_weight)
        # Separable smoothing over height (~2.5 cm) and angle (~8 deg), then
        # never fall more than 0.06 below the body hull (ease covers the rest).
        smooth = draped.copy()
        hk = np.array([1, 2, 3, 4, 3, 2, 1], float)
        hk /= hk.sum()
        for j in range(smooth.shape[1]):
            smooth[:, j] = np.convolve(np.pad(smooth[:, j], 3, mode='edge'), hk, mode='valid')
        ak = np.array([1, 2, 3, 2, 1], float)
        ak /= ak.sum()
        for k in range(smooth.shape[0]):
            smooth[k] = np.convolve(np.concatenate((smooth[k, -3:-1], smooth[k], smooth[k, 1:3])), ak, mode='valid')
        smooth = np.maximum(smooth, radii-0.06)
        return levels_y, step, angles, centers, smooth

    def shape(self, ids):
        P = self.points.copy()
        body = self.points[:BODY_VERTICES]
        w = self.weights
        lv = self.levels
        levels_y, step, angles, centers, table = self.torso_table()
        nang = len(angles)-1
        arm_t = np.zeros(len(P))
        sleeve_weight = np.zeros(len(P))
        self.fold = np.zeros_like(P)
        for i in sorted(ids):
            if i >= BODY_VERTICES:
                continue
            x, y, z = body[i]
            aw = w.arm[i]
            k = float(np.clip((y-levels_y[0])/step, 0, len(levels_y)-1.001))
            k0 = int(k)
            f = k-k0
            zc = centers[k0]*(1-f)+centers[k0+1]*f
            angle = math.atan2(z-zc, x)
            a = (angle+math.pi)/(2*math.pi)*nang
            a0 = int(a) % nang
            g = a-int(a)
            drape_r = ((table[k0, a0]*(1-g)+table[k0, a0+1]*g)*(1-f)
                       + (table[k0+1, a0]*(1-g)+table[k0+1, a0+1]*g)*f)
            r_body = math.hypot(x, z-zc)
            hem_ease = float(smoothstep(lv['armpit_y'], lv['hem_y'], y))
            neck_close = float(smoothstep(lv['neck_y']-0.55, lv['neck_y']-0.05, y))
            ease = (0.12+0.07*hem_ease)*(1-neck_close)+0.05*neck_close
            target_r = max(r_body*neck_close+drape_r*(1-neck_close), r_body)+ease
            torso_pos = np.array([math.cos(angle)*target_r, y, zc+math.sin(angle)*target_r])
            torso_fold = np.array([math.cos(angle), 0.0, math.sin(angle)])*0.026*math.sin(angle*11+y*1.7)*hem_ease
            # Sleeve around the piecewise shoulder-elbow-wrist axis.
            frame = self.arm_frames['L' if x > 0 else 'R']
            t, axis_point, tangent = frame.locate(body[i])
            radial = body[i]-axis_point
            radial -= tangent*radial.dot(tangent)
            r_arm = float(np.linalg.norm(radial))
            u = radial/max(r_arm, 1e-9)
            tube = interpolate_profile(t, [(-0.2, 0.62), (0.08, 0.60), (0.30, 0.56), (0.52, 0.51),
                                           (0.75, 0.47), (0.90, 0.43), (1.00, 0.36), (1.2, 0.32)])
            min_ease = interpolate_profile(t, [(0.0, 0.09), (0.85, 0.08), (1.0, 0.06)])
            new_r = max(r_arm+min_ease, tube)
            # Bunching just above the cuff and soft elbow folds.
            ref = np.cross(tangent, [0.0, 0.0, 1.0])
            ref /= max(np.linalg.norm(ref), 1e-9)
            phi = math.atan2(u.dot(np.cross(tangent, ref)), u.dot(ref))
            bunch = float(smoothstep(0.70, 0.88, t)*(1-smoothstep(0.97, 1.02, t)))
            sleeve_fold = u*(bunch*(0.028*math.sin(t*frame.length*30+phi*2)+0.016*math.sin(phi*5+t*9))
                             + 0.014*math.exp(-((t-0.5)/0.06)**2)*math.sin(phi*3))
            down = np.array([0.0, -1.0, 0.0])-tangent*(-tangent[1])
            down /= max(np.linalg.norm(down), 1e-9)
            droop = 0.25*max(0.0, tube-r_arm)*float(smoothstep(0.15, 0.4, t))
            sleeve_pos = axis_point+u*new_r+down*droop
            s = float(smoothstep(0.22, 0.55, aw))
            P[i] = torso_pos*(1-s)+sleeve_pos*s
            self.fold[i] = torso_fold*(1-s)+sleeve_fold*s
            arm_t[i] = t
            sleeve_weight[i] = s
        self.arm_t = arm_t
        self.sleeve = sleeve_weight
        return P


def sweater_faces(points, groups, weights, frames, levels):
    """Torso = every non-arm face between the knit bottom and the neckline;
    sleeves = arm faces up to the cuff (no lateral cut that opened side holes)."""
    selected = []
    for face in groups['body']:
        ids = [i for i, t in face]
        center = np.mean([points[i] for i in ids], axis=0)
        arm = np.mean([weights.arm[i] for i in ids])
        hand = np.mean([weights.hand[i] for i in ids])
        head = np.mean([weights.head[i] for i in ids])
        if head > 0.35 or center[1] > levels['neck_y']:
            continue
        side = 'L' if center[0] > 0 else 'R'
        t, _, _ = frames[side].locate(center)
        sleeve = arm >= 0.40 and t < levels['cuff_t']
        torso = arm < 0.40 and center[1] > levels['knit_bottom_y'] and max(weights.leg['L'][i]+weights.leg['R'][i] for i in ids) < 0.3
        if torso or sleeve:
            selected.append(face)
    if len(selected) < 300:
        raise RuntimeError('Sweater topology selection failed')
    return selected


def jean_faces(points, groups, weights, levels):
    selected = []
    for face in groups['body']:
        ids = [i for i, t in face]
        center = np.mean([points[i] for i in ids], axis=0)
        arm = np.mean([weights.arm[i] for i in ids])
        hand = np.mean([weights.hand[i] for i in ids])
        if levels['jean_hem_y']-0.25 < center[1] < levels['waist_top_y'] and arm < 0.12 and hand < 0.12 \
                and abs(center[0]) < 2.6:
            selected.append(face)
    if len(selected) < 300:
        raise RuntimeError('Jeans topology selection failed')
    return selected


def shape_jeans(points, ids, weights, rig, levels, normals):
    """Returns (positions, folds). Pelvis: real surface normal + ease growing
    from the waistband to the seat. Legs: straight barrel tubes from original
    B width ratios with a depth-only seat drape. Transition blends both."""
    P = np.asarray(points, float).copy()
    body = np.asarray(points, float)
    folds = np.zeros_like(P)
    frames = {s: leg_frame(points, rig, s) for s in ('L', 'R')}
    crotch_y = levels['crotch_y']
    hem_y = levels['jean_hem_y']
    top = levels['waist_top_y']
    seat = {}
    for side, sign in (('L', 1), ('R', -1)):
        sel = (np.sign(body[:BODY_VERTICES, 0]) == sign) & (body[:BODY_VERTICES, 1] > crotch_y-1.5) \
            & (body[:BODY_VERTICES, 1] < crotch_y+1.2) & (weights.arm < 0.1)
        back = body[:BODY_VERTICES][sel]
        seat[side] = back[np.argmin(back[:, 2])]
    for i in ids:
        if i >= BODY_VERTICES:
            continue
        x, y, z = body[i]
        side = 'L' if x > 0 else 'R'
        sign = 1 if side == 'L' else -1
        hip, knee, ankle = frames[side]
        # Pelvis target.
        ease = 0.09+0.07*float(smoothstep(top, top-1.0, y))
        pelvis = body[i]+normals[i]*ease
        # Leg tube target.
        if y > knee[1]:
            t = (hip[1]-y)/(hip[1]-knee[1])
            center = hip+(knee-hip)*t
        else:
            t = (knee[1]-y)/(knee[1]-ankle[1])
            center = knee+(ankle-knee)*t
        center = center.copy()
        center[1] = y
        radial = body[i]-center
        radial[1] = 0
        r_body = float(np.linalg.norm(radial))
        u = radial/max(r_body, 1e-9)
        tube = interpolate_profile(-y, [(-crotch_y, 0.86), (-(crotch_y-1.6), 0.80),
                                        (-knee[1], 0.72), (-(knee[1]-1.6), 0.66),
                                        (-(hem_y+0.6), 0.64), (-hem_y, 0.66), (-(hem_y-0.3), 0.66)])
        leg = center+u*max(r_body+0.07, tube)
        if u[2] < -0.30:
            hang = float(smoothstep(crotch_y-2.2, crotch_y-0.2, y))*float(smoothstep(0.30, 0.70, -u[2]))
            seat_z = seat[side][2]-0.10
            if leg[2] > seat_z:
                leg[2] = leg[2]*(1-hang)+seat_z*hang
        if u[0]*sign < 0 and (leg[0]-sign*0.06)*sign < 0:
            leg[0] = sign*0.06
        # Blend: pelvis above the crotch, leg tubes below; inner thighs switch
        # to the tube earlier so no web forms between the legs.
        inner = float(smoothstep(0.9, 0.3, abs(x)))
        w_leg = float(smoothstep(crotch_y+0.55-0.35*inner, crotch_y-0.25, y))
        P[i] = pelvis*(1-w_leg)+leg*w_leg
        # Folds (applied after relaxation).
        gather = float(smoothstep(hem_y+0.9, hem_y+0.15, y))
        phi = math.atan2(u[2], u[0])
        amount = gather*(0.055*math.sin(y*24+phi*3)+0.03*math.sin(phi*7+y*9))
        amount += 0.018*math.sin(y*6.5+phi*2)*float(smoothstep(crotch_y-0.5, hem_y+1.0, y))
        folds[i] = u*amount*w_leg
        if y < hem_y+0.05:
            P[i][1] = hem_y+0.04*math.sin(phi*3+0.6)
    return P, folds


# ----------------------------------------------------------------------- boots

def foot_outline(points, weights, side, margins):
    """Footprint frame enclosing every actual foot/toe vertex with margins.

    The long axis follows the foot's principal direction (toe-out included)."""
    sel = weights.foot[side] > 0.30
    foot = np.asarray(points[:BODY_VERTICES], float)[sel]
    xz = foot[:, [0, 2]]
    mean = xz.mean(axis=0)
    cov = np.cov((xz-mean).T)
    values, vectors = np.linalg.eigh(cov)
    forward = vectors[:, np.argmax(values)]
    if forward[1] < 0:
        forward = -forward
    lateral = np.array([forward[1], -forward[0]])
    local_f = (xz-mean)@forward
    local_l = (xz-mean)@lateral
    return {'mean': mean, 'forward': forward, 'lateral': lateral,
            'front': local_f.max()+margins['toe'], 'back': local_f.min()-margins['heel'],
            'half_w': 0.5*(local_l.max()-local_l.min())+margins['side'],
            'lateral_center': 0.5*(local_l.max()+local_l.min()),
            'top': foot[:, 1].max(), 'bottom': foot[:, 1].min(),
            'toe_out_degrees': math.degrees(math.atan2(forward[0], forward[1]))}


def footprint_ring(o, n, scale_w=1.0, front_scale=1.0, back_scale=1.0):
    """Superellipse footprint: broad round toe, narrower heel. Ring index i
    always maps to the same angle so rings loft cleanly."""
    center_f = 0.5*(o['front']+o['back'])
    half_front = (o['front']-center_f)*front_scale
    half_back = (center_f-o['back'])*back_scale
    result = []
    for i in range(n):
        a = 2*math.pi*i/n
        c, s = math.cos(a), math.sin(a)
        forward = s > 0
        width = o['half_w']*scale_w*(1.0 if forward else 0.86)
        e = 2.5 if forward else 2.2
        lat = width*math.copysign(abs(c)**(2/e), c)
        fwd = (half_front if forward else half_back)*math.copysign(abs(s)**(2/e), s)
        xz = o['mean']+o['forward']*(center_f+fwd)+o['lateral']*(o['lateral_center']+lat)
        result.append((float(xz[0]), float(xz[1])))
    return result


def boot_ring(o, h, ground, ankle, knee, top_y, n):
    """Upper cross-section at source height ground+h: footprint near the sole,
    a toe box/vamp that recedes with height, and a round shaft above the ankle."""
    y = ground+h
    front_scale = float(np.interp(h, [0.0, 0.15, 0.28, 0.38, 0.48, 0.60, 0.75, 0.9],
                                  [1.0, 0.99, 0.95, 0.86, 0.70, 0.52, 0.38, 0.30]))
    width_scale = float(np.interp(h, [0.0, 0.2, 0.4, 0.6, 0.8], [1.0, 0.98, 0.93, 0.86, 0.80]))
    foot = footprint_ring(o, n, width_scale, front_scale, 0.97)
    blend = float(smoothstep(ankle[1]-0.05, ankle[1]+0.55, y))
    t = max(0.0, (y-ankle[1])/max(knee[1]-ankle[1], 1e-6))
    lc = ankle+(knee-ankle)*min(1.0, t)
    shaft_r = 0.46+0.035*float(smoothstep(top_y-1.4, top_y, y))
    ring = []
    for i, (fx, fz) in enumerate(foot):
        a = 2*math.pi*i/n
        sx = lc[0]+shaft_r*math.cos(a)*o['lateral'][0]+shaft_r*1.08*math.sin(a)*o['forward'][0]
        sz = lc[2]+0.06+shaft_r*math.cos(a)*o['lateral'][1]+shaft_r*1.08*math.sin(a)*o['forward'][1]
        ring.append((fx*(1-blend)+sx*blend, y, fz*(1-blend)+sz*blend))
    return ring


def build_boots(points, weights, rig, transform, arm, directory, levels):
    leather = detail_tile('BootBlackLeather', directory, (.055, .056, .058), .44, 'leather')
    rubber = detail_tile('BootBlackRubberSole', directory, (.045, .046, .048), .86, 'rubber')
    lace_mat = material('Inez_Boot_Black_WovenLaces', (.022, .023, .024), .88)
    stitch_mat = material('Inez_Boot_Subtle_BlackStitching', (.060, .061, .062), .80)
    eyelet_mat = material('Inez_Boot_BlackenedMetalEyelets', (.050, .051, .054), .38, .70)
    objects = []
    report = {}
    ground = levels['foot_bottom_y']
    sole_bottom = ground-levels['platform_units']
    top_y = levels['boot_top_y']
    n = 48
    for side in ('L', 'R'):
        o = foot_outline(points, weights, side, {'side': 0.08, 'toe': 0.20, 'heel': 0.09})
        hip, knee, ankle = leg_frame(points, rig, side)
        # Platform sole under the foot: slightly proud of the upper, rounded edge.
        sole_rings = []
        for y, grow in [(sole_bottom, 0.0), (sole_bottom+0.035, 0.035), (ground-0.08, 0.04),
                        (ground-0.015, 0.035), (ground+0.02, 0.012)]:
            ring = footprint_ring(o, n, 1.0+grow/0.5, 1.0+grow/1.3, 1.0+grow/1.0)
            sole_rings.append([(x, y, z) for x, z in ring])
        sole = loft('Inez_Boot_Sole_'+side, sole_rings, transform, rubber)
        skin_rigid(sole, arm, 'foot.'+side)
        objects.append(sole)
        heights = [0.0, 0.08, 0.16, 0.26, 0.36, 0.46, 0.56, 0.66, 0.80, 0.98, 1.25, 1.55, 1.85,
                   (top_y-ground)-0.25, top_y-ground]
        rings = [boot_ring(o, h, ground, ankle, knee, top_y, n) for h in heights]
        # Close the toe box: cap the lowest-front opening by a dome ring.
        upper = loft('Inez_Boot_'+side, rings, transform, leather, capped=False)
        actual_thickness(upper, .0028, clamp=1.0)
        objects.append(upper)
        _skin_boot_part(upper, arm, side, ankle, transform)
        # Lacing: rows from the vamp to the shaft top on the actual ring fronts.
        front_rows = []
        for h in np.linspace(0.62, (top_y-ground)-0.12, 9):
            ring = np.asarray(boot_ring(o, h, ground, ankle, knee, top_y, n))
            front_rows.append(ring)
        def front_point(ring, lateral):
            # Point on the front half of the ring at a lateral offset.
            local = ring[:, [0, 2]]-o['mean']
            lat = local@o['lateral']-o['lateral_center']
            fwd = local@o['forward']
            best = np.argmax(np.where(np.abs(lat-lateral) < 0.12, fwd, -1e9))
            return ring[best]
        laces, eyelets = [], []
        for row, ring in enumerate(front_rows):
            for sign in (-1, 1):
                p = front_point(ring, sign*0.21)
                outward = np.array([o['forward'][0], 0, o['forward'][1]])*0.012
                eyelets.append((row, sign, p+outward))
        for row in range(len(front_rows)-1):
            for sign in (-1, 1):
                a = eyelets[row*2+(0 if sign < 0 else 1)][2]
                b = eyelets[(row+1)*2+(1 if sign < 0 else 0)][2]
                mid = 0.5*(a+b)+np.array([o['forward'][0], 0, o['forward'][1]])*0.02
                laces.append([tuple(a*(1-t)**2+2*mid*t*(1-t)+b*t*t) for t in np.linspace(0, 1, 9)])
        for row, sign, center in eyelets:
            eyelet = torus_source('Inez_Boot_Eyelet_%s_%d_%d' % (side, row, sign), tuple(center), .022, .007,
                                  transform, eyelet_mat)
            objects.append(eyelet)
            _skin_boot_part(eyelet, arm, side, ankle, transform)
        lace = tubes('Inez_Boot_Laces_'+side, laces, .011, transform, lace_mat, sides=5)
        objects.append(lace)
        _skin_boot_part(lace, arm, side, ankle, transform)
        # Tongue under the laces.
        tonguepoints = []
        for ring in front_rows:
            for lateral in (-0.17, 0.0, 0.17):
                p = front_point(ring, lateral)
                tonguepoints.append(tuple(p-np.array([o['forward'][0], 0, o['forward'][1]])*0.004))
        tongue = mesh_object('Inez_Boot_Tongue_'+side, tonguepoints,
                             [(i*3+j, i*3+j+1, (i+1)*3+j+1, (i+1)*3+j) for i in range(len(front_rows)-1) for j in range(2)],
                             transform, leather)
        actual_thickness(tongue, .0022)
        objects.append(tongue)
        _skin_boot_part(tongue, arm, side, ankle, transform)
        # Padded collar at the shaft top.
        lc = ankle+(knee-ankle)*min(1.0, max(0.0, (top_y-ankle[1])/max(knee[1]-ankle[1], 1e-6)))
        collar = []
        for d, dy in [(0.0, -0.12), (0.035, -0.05), (0.035, 0.015), (0.0, 0.045)]:
            ring = []
            for i in range(n):
                a = 2*math.pi*i/n
                r = 0.495+d
                x = lc[0]+r*math.cos(a)*o['lateral'][0]+r*1.08*math.sin(a)*o['forward'][0]
                z = lc[2]+0.06+r*math.cos(a)*o['lateral'][1]+r*1.08*math.sin(a)*o['forward'][1]
                ring.append((x, top_y+dy, z))
            collar.append(ring)
        collarobj = loft('Inez_Boot_PaddedCollar_'+side, collar, transform, leather, capped=False)
        objects.append(collarobj)
        _skin_boot_part(collarobj, arm, side, ankle, transform)
        # Welt stitch and toe-cap seam.
        welt = [(x, ground+0.03, z) for x, z in footprint_ring(o, n, 1.012, 1.008, 1.008)]
        welt.append(welt[0])
        toecap = [tuple(p) for p in np.asarray(boot_ring(o, 0.30, ground, ankle, knee, top_y, n))[n//8:3*n//8+1]]
        stitches = tubes('Inez_Boot_StitchedPanels_'+side, [welt, toecap], .0055, transform, stitch_mat, sides=4)
        objects.append(stitches)
        _skin_boot_part(stitches, arm, side, ankle, transform)
        report[side] = {'toe_out_degrees': o['toe_out_degrees'],
                        'boot_length_m': (o['front']-o['back'])*abs(transform((1, 0, 0))[0]-transform((0, 0, 0))[0]),
                        'boot_width_m': 2*o['half_w']*abs(transform((1, 0, 0))[0]-transform((0, 0, 0))[0]),
                        'foot_margins_source_units': {'side': 0.08, 'toe': 0.20, 'heel': 0.09}}
    return objects, report


def _skin_boot_part(obj, arm, side, ankle, transform):
    """Foot below the ankle, shin above it, smooth 4 cm transition."""
    ankle_z = transform(tuple(ankle))[2]
    foot_group = obj.vertex_groups.new(name='foot.'+side)
    shin_group = obj.vertex_groups.new(name='lowerleg02.'+side)
    for v in obj.data.vertices:
        shin = float(smoothstep(ankle_z+0.005, ankle_z+0.045, v.co.z))
        if shin < 1:
            foot_group.add([v.index], 1-shin, 'REPLACE')
        if shin > 0:
            shin_group.add([v.index], shin, 'REPLACE')
    modifier = obj.modifiers.new('Inez_Boot_Skin', 'ARMATURE')
    modifier.object = arm
    obj.parent = arm
    obj['weight_authoring'] = 'Boot: foot below ankle, lowerleg02 shaft above, 4 cm blend'


# ----------------------------------------------------------------------- trims

def rib_extension(name, loop_points, center, direction, length, gather, transform, mat, rows=5, ribs=None):
    """Ribbed band continuing a garment boundary loop."""
    loop = [np.asarray(p, float) for p in loop_points]
    n = len(loop)
    ribs = ribs or max(24, n//2)
    rings = []
    for k in range(rows):
        t = k/(rows-1)
        ring = []
        for j, p in enumerate(loop):
            radial = p-center
            radial -= direction*radial.dot(direction)
            rlen = np.linalg.norm(radial)
            u = radial/max(rlen, 1e-9)
            r = rlen*(1-gather*math.sin(math.pi*0.5*t))
            rib = 0.012*math.cos(2*math.pi*j*ribs/n)
            q = center+(p-center).dot(direction)*direction+direction*length*t+u*(r+rib)
            ring.append(tuple(q))
        rings.append(ring)
    return loft(name, rings, transform, mat, capped=False)


def ordered_loop_positions(obj, loop):
    return [obj.data.vertices[i].co.copy() for i in loop]


# ------------------------------------------------------------ jean details

def nearest_surface(points, ids, x, y, front=True, lift=0.02):
    """Nearest garment vertex by (x, y) on the requested side, pushed out."""
    P = np.asarray(points, float)[ids]
    cost = (P[:, 0]-x)**2+(P[:, 1]-y)**2
    zc = np.median(P[:, 2])
    cost += np.where((P[:, 2] > zc) == front, 0.0, 4.0)
    best = P[int(np.argmin(cost))]
    return (float(x), float(y), float(best[2]+(lift if front else -lift)))


def seam_line(points, ids, side, ys, which):
    """Outer or inner leg seam. Among the near-extreme lateral vertices of each
    height band, keep the one closest in depth to the previous seam point so
    the seam never jumps between front and back."""
    P = np.asarray(points, float)[ids]
    sign = 1 if side == 'L' else -1
    path = []
    previous_z = None
    for y in ys:
        band = P[(np.abs(P[:, 1]-y) < 0.07) & (np.sign(P[:, 0]) == sign)]
        if len(band) == 0:
            continue
        lateral = band[:, 0]*sign
        extreme = lateral.max() if which == 'outer' else lateral.min()
        near = band[np.abs(lateral-extreme) < 0.04]
        reference = np.median(band[:, 2]) if previous_z is None else previous_z
        best = near[np.argmin(np.abs(near[:, 2]-reference))]
        previous_z = best[2]
        offset = 0.015 if which == 'outer' else -0.012
        path.append((best[0]+sign*offset, best[1], best[2]))
    return path


def add_jean_details_v04(jeans, shaped, body_points, transform, arm, weights, denim, thread, levels):
    ids = np.array([d.value for d in jeans.data.attributes['makehuman_source_index'].data])
    top = levels['waist_top_y']
    crotch = levels['crotch_y']
    hem = levels['jean_hem_y']
    objects = []
    paths = []
    # Waistband stitching lines (front and back) and the yoke.
    for front in (True, False):
        for dy in (0.04, 0.40):
            paths.append([nearest_surface(shaped, ids, x, top-dy, front) for x in np.linspace(-1.15, 1.15, 46)])
    for side, sign in (('L', 1), ('R', -1)):
        # Front pocket opening curve and coin-pocket hint.
        paths.append([nearest_surface(shaped, ids, sign*(0.55+0.45*t), top-0.42-0.50*t**1.3, True)
                      for t in np.linspace(0, 1, 18)])
        # Outer and inner leg seams.
        paths.append(seam_line(shaped, ids, side, np.linspace(top-0.6, hem+0.25, 64), 'outer'))
        paths.append(seam_line(shaped, ids, side, np.linspace(crotch-0.25, hem+0.25, 52), 'inner'))
        # Back yoke V and rear patch pocket.
        paths.append([nearest_surface(shaped, ids, sign*x, top-0.45-0.30*(1-x/1.2), False)
                      for x in np.linspace(0.02, 1.2, 16)])
        outline = [(sign*0.32, top-0.95), (sign*0.98, top-1.02), (sign*0.94, top-1.95), (sign*0.66, top-2.15),
                   (sign*0.36, top-1.92)]
        pocketpoints = [nearest_surface(shaped, ids, x, y, False, 0.028) for x, y in outline]
        center = sum((Vector(p) for p in pocketpoints), Vector())/len(pocketpoints)
        pocketpoints.append(tuple(center+Vector((0, 0, -.004))))
        faces = [(i, (i+1) % 5, 5) for i in range(5)]
        pocket = mesh_object('Inez_Jeans_RearPatchPocket_'+side, pocketpoints, faces, transform, denim)
        skin_source_nearest(pocket, arm, body_points, weights, transform)
        actual_thickness(pocket, .0009)
        objects.append(pocket)
        paths.append(pocketpoints[:5]+[pocketpoints[0]])
    # Fly: J-stitch on the wearer's left of center.
    fly = [nearest_surface(shaped, ids, 0.16, y, True) for y in np.linspace(top-0.45, crotch+0.55, 22)]
    fly += [nearest_surface(shaped, ids, 0.16-0.16*math.sin(math.pi*0.5*t), crotch+0.55-0.25*t, True)
            for t in np.linspace(0, 1, 8)]
    paths.append(fly)
    paths.append([nearest_surface(shaped, ids, 0.0, y, True) for y in np.linspace(top-0.45, crotch+0.2, 26)])
    seams = tubes('Inez_Jeans_SewnSeams', [p for p in paths if len(p) > 1], .0065, transform, thread, sides=4)
    skin_source_nearest(seams, arm, body_points, weights, transform)
    objects.append(seams)
    for index, (x, front) in enumerate([(-0.88, True), (0.88, True), (-0.80, False), (0.80, False), (0.0, False)]):
        p = nearest_surface(shaped, ids, x, top-0.22, front, 0.03)
        dz = .012 if front else -.012
        vertices = [(p[0]-.065, p[1]-.24, p[2]+dz), (p[0]+.065, p[1]-.24, p[2]+dz),
                    (p[0]+.06, p[1]+.20, p[2]+dz), (p[0]-.06, p[1]+.20, p[2]+dz)]
        loop = mesh_object('Inez_Jeans_BeltLoop_'+str(index), vertices, [(0, 1, 2, 3)], transform, denim)
        skin_source_nearest(loop, arm, body_points, weights, transform)
        actual_thickness(loop, .0013)
        objects.append(loop)
    metal = material('Inez_Jeans_RestrainedDarkHardware', (.16, .15, .135), .42, .72)
    for index, (x, dy) in enumerate([(0.0, 0.22), (-0.56, 0.44), (0.56, 0.44), (-1.0, 0.92), (1.0, 0.92)]):
        center = nearest_surface(shaped, ids, x, top-dy, True, 0.03)
        rivet = torus_source('Inez_Jeans_ButtonOrRivet_'+str(index), center, .026 if index == 0 else .012, .006,
                             transform, metal)
        skin_source_nearest(rivet, arm, body_points, weights, transform)
        objects.append(rivet)
    return objects


def necklace_v04(body_points, sweater_points, sweater_ids, transform, arm, weights, directory, levels):
    """Fine chain resting on the neck skin and sweater; tiny pendant whose
    exact motif is not inferred (original silhouette only)."""
    silver = detail_tile('FineSilverChainAndTinyPendant', directory, (.62, .64, .66), .22, 'silver', resolution=256)
    silver.node_tree.nodes.get('Principled BSDF').inputs['Metallic'].default_value = .95
    body = np.asarray(body_points[:BODY_VERTICES], float)
    sweater = np.asarray(sweater_points, float)[sorted(sweater_ids)]

    def outermost(x, y):
        best = None
        for cloud in (body, sweater):
            near = cloud[(np.abs(cloud[:, 0]-x) < 0.06) & (np.abs(cloud[:, 1]-y) < 0.06) & (cloud[:, 2] > 0.2)]
            if len(near):
                z = near[:, 2].max()
                best = z if best is None else max(best, z)
        return (x, y, (best if best is not None else 1.0)+0.012)
    pendant_y = levels['pendant_y']
    paths = []
    for side in (-1, 1):
        path = []
        for t in np.linspace(0, 1, 44):
            x = side*0.46*(1-t)**1.15
            y = levels['necklace_top_y']-(levels['necklace_top_y']-pendant_y)*t
            path.append(outermost(x, y))
        paths.append(path)
    chain = tubes('Inez_FineSilverNecklace', paths, .0062, transform, silver, sides=5)
    skin_source_nearest(chain, arm, body_points, weights, transform)
    c = outermost(0.0, pendant_y-0.02)
    pendantpaths = [[(c[0]-.018, c[1]+.014, c[2]+.006), (c[0], c[1]-.036, c[2]+.010), (c[0]+.018, c[1]+.016, c[2]+.006)],
                    [(c[0], c[1]-.020, c[2]+.009), (c[0]+.024, c[1]+.002, c[2]+.008)]]
    pendant = tubes('Inez_TinyUnknownMotifPendant', pendantpaths, .008, transform, silver, sides=5)
    skin_source_nearest(pendant, arm, body_points, weights, transform)
    pendant['motif_status'] = 'Original tiny silhouette uncertain; no exact motif inference'
    return [chain, pendant]
