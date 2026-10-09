"""v04 curly high-ponytail groom on the actual fitted head (source units).

v03 review: the crown was a thick offset shell that rendered as a glossy
helmet with a jagged edge; strands were thin wires; colors near-black; the
ponytail was a narrow braid. v04 builds:

* a close scalp cap (3 mm) whose strand texture converges on the tie point and
  whose irregular hairline fades through alpha MASK instead of a hard edge;
* pulled-back curly locks lying on the scalp, projected onto the real head
  surface (BVH) so nothing floats or penetrates;
* curly framing ringlets from the temples to about chin level, plus a few short
  forehead curls, kept clear of the face by surface collision;
* a voluminous high ponytail of spiral ringlets (original B rear volume and
  length), a dark elastic tie and fine frizz.

Hidden scalp arrangement and the exact curl count are original-consistent
proposals, not observed facts.
"""
import math

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from model_build import mesh_from_group
from model_geometry import tubes, skin_rigid, mesh_object
from model_materials import save_image, connect_pbr, material
from model_materials_v04 import hair_tile, noise, srgb
from model_hair_cards import hair_atlas, card_strip, card_object

HAIR_BASE = (0.235, 0.160, 0.105)
HAIR_TIP = (0.420, 0.300, 0.190)
HAIR_WARM = (0.470, 0.330, 0.200)


class HeadSurface:
    """Ray casting against the fitted body in source coordinates."""

    def __init__(self, points, faces):
        verts = [Vector(p) for p in points[:13380]]
        polys = [[i for i, t in f] for f in faces]
        self.bvh = BVHTree.FromPolygons(verts, polys)
        self.center = Vector(HEAD_CENTER)

    def project(self, direction, offset):
        """Point on the scalp along direction from the head center, pushed out."""
        d = Vector(direction).normalized()
        origin = self.center+d*3.0
        hit, normal, index, distance = self.bvh.ray_cast(origin, -d, 6.0)
        if hit is None:
            return None, None
        return hit+normal*offset, normal

    def push_out(self, point, clearance):
        p = Vector(point)
        nearest, normal, index, distance = self.bvh.find_nearest(p)
        if nearest is None:
            return p
        outward = (p-nearest)
        inside = outward.dot(normal) < 0
        if inside or distance < clearance:
            return nearest+normal*clearance
        return p


HEAD_CENTER = (0.0, 7.05, 0.45)
# Hairline height (source y) by azimuth around the head (0 = face, pi = nape),
# from the fitted head: forehead, receding temples, sideburn in front of the
# ear, over the ear top (~6.95), behind the ear and down to the nape.
HAIRLINE_KNOTS = [(0.00, 7.30), (0.40, 7.27), (0.72, 7.13), (0.98, 6.92), (1.12, 6.80), (1.24, 6.98),
                  (1.45, 7.04), (1.90, 7.02), (2.10, 6.82), (2.40, 6.58), (2.75, 6.42), (math.pi, 6.40)]


def azimuth(x, z):
    return math.atan2(x, z-HEAD_CENTER[2])


def hairline_height(x, z):
    a = abs(azimuth(x, z))
    base = float(np.interp(a, [k for k, v in HAIRLINE_KNOTS], [v for k, v in HAIRLINE_KNOTS]))
    return base+0.035*math.sin(x*9.0+0.7)+0.020*math.sin(x*23.0)+0.012*math.sin(x*41.0+1.3+z*7.0)


def scalp_faces(points, groups):
    """Head faces from ~2 cm below the hairline upward (the visible hairline is
    an alpha ramp in the texture, not a stepped mesh edge); ears excluded."""
    faces = []
    for face in groups['body']:
        pts = np.asarray([points[i] for i, t in face])
        if pts[:, 1].min() < 6.20:
            continue
        if any(abs(p[0]) > 0.725 and p[1] < 7.12 for p in pts):
            continue
        if all(p[1] > hairline_height(p[0], p[2])-0.20 for p in pts):
            faces.append(face)
    return faces


def scalp_cap(points, uv, groups, transform, arm, directory, tie, resolution=1024):
    faces = scalp_faces(points, groups)
    ids = sorted({i for f in faces for i, t in f})
    center = np.array(HEAD_CENTER)
    capped = [list(p) for p in points]
    for i in ids:
        p = np.asarray(points[i], float)
        d = p-center
        d /= max(np.linalg.norm(d), 1e-9)
        # ~2.5 mm cap rising to ~6 mm of damp volume at the crown.
        lift = 0.024+0.035*max(0.0, (p[1]-7.25)/0.6)+0.006*math.sin(p[0]*17+p[2]*11)
        capped[i] = tuple(p+d*lift)
    # Procedural strand texture rasterized in the cap's own (body) UV space.
    from model_materials_v04 import raster_attributes
    positions, _, mask = raster_attributes(capped, None, uv, faces, resolution)
    x, y, z = positions[:, :, 0], positions[:, :, 1], positions[:, :, 2]
    axis = np.asarray(tie)-center
    axis /= np.linalg.norm(axis)
    rel = positions-center
    # Azimuth around the head-center -> tie axis: meridians converge at the tie
    # like hair pulled into a ponytail.
    ref = np.cross(axis, [1.0, 0.0, 0.0])
    ref /= np.linalg.norm(ref)
    other = np.cross(axis, ref)
    phi = np.arctan2((rel*other).sum(axis=2), (rel*ref).sum(axis=2))
    along = (rel*axis).sum(axis=2)
    warp = 0.35*np.sin(along*9.0+phi*3.0)
    strands = np.zeros(mask.shape, np.float32)
    rng = np.random.default_rng(55)
    for k in range(5):
        strands += np.sin(phi*rng.integers(60, 160)+warp*rng.uniform(1, 3)+rng.uniform(0, 6.3))/(k+1)
    strands = strands/np.abs(strands).max()
    clumps = noise(mask.shape, 3, 56)
    root = np.clip((y-6.6)/0.9, 0, 1)
    color = srgb(HAIR_BASE)*(0.80+0.18*root[:, :, None])
    albedo = color*(1+0.20*strands[:, :, None]+0.08*clumps[:, :, None])
    # Subtle near-center part toward the crown (original A/B: irregular,
    # slightly off-center); the scalp shows through faintly.
    part = np.exp(-((x-0.025)/0.014)**2)*np.clip((z-0.30)*2.0, 0, 1)*(y > 7.30)
    albedo = albedo*(1-0.15*part[:, :, None])+srgb((0.62, 0.46, 0.38))*0.15*part[:, :, None]
    # Alpha: soft irregular hairline all around (front, sideburns, over the
    # ears, nape): ~1.5 cm ramp broken up by fine strands.
    hl = np.vectorize(hairline_height)(x, z)
    edge = (y-hl+0.02)/0.15
    fine = np.sin(phi*240.0+warp*2.0)
    alpha = np.clip(edge+0.30*fine+0.15*clumps, 0, 1)
    alpha = np.where(mask, alpha, 0)
    rgba_albedo = np.concatenate((albedo, alpha[:, :, None]), axis=2)
    rough = np.full(mask.shape, .78, np.float32)+0.05*strands
    normal_height = strands*0.7+clumps*0.3
    from model_materials import normal_from_height, dilate_maps
    normal = normal_from_height(normal_height, .30)
    rgba_albedo, rough, normal = dilate_maps([rgba_albedo, rough, normal], mask, passes=6)
    img = bpy.data.images.new('ScalpHairStrands_albedo', width=resolution, height=resolution, alpha=True)
    img.colorspace_settings.name = 'sRGB'
    img.pixels.foreach_set(np.clip(rgba_albedo, 0, 1).reshape(-1).astype(np.float32))
    from pathlib import Path
    Path(directory).mkdir(parents=True, exist_ok=True)
    img.filepath_raw = str(Path(directory)/'ScalpHairStrands_albedo.png')
    img.file_format = 'PNG'
    img.save()
    img.pack()
    rough_img = save_image('ScalpHairStrands_roughness', rough, directory, True)
    normal_img = save_image('ScalpHairStrands_normal', normal, directory, True)
    mat = material('Inez_ScalpHairStrands_PBR', HAIR_BASE, .78)
    connect_pbr(mat, img, rough_img, normal_img, normal_strength=.18)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    albedo_node = next(n for n in nodes if n.type == 'TEX_IMAGE' and n.image == img)
    # Math ROUND between texture alpha and BSDF alpha exports as glTF alphaMode
    # MASK with cutoff 0.5 (Blender 4.2+ exporter convention).
    clip = nodes.new('ShaderNodeMath')
    clip.operation = 'ROUND'
    links.new(albedo_node.outputs['Alpha'], clip.inputs[0])
    links.new(clip.outputs[0], bsdf.inputs['Alpha'])
    mat.surface_render_method = 'DITHERED'
    obj, _ = mesh_from_group('Inez_ScalpHair', faces, capped, uv, transform, mat)
    skin_rigid(obj, arm, 'head')
    obj['hairline_status'] = 'Irregular hairline alpha mask; partly occluded original hairline reconstructed'
    return obj


def curl_path(start, direction_points, turns, radius, seed, samples, frizz=0.0):
    """Helix around a smooth guide polyline (ringlet). direction_points is the
    guide (list of numpy points); the helix uses a parallel-transport frame."""
    guide = np.asarray(direction_points, float)
    # Resample the guide uniformly.
    seg = np.linalg.norm(np.diff(guide, axis=0), axis=1)
    cum = np.concatenate(([0], np.cumsum(seg)))
    s = np.linspace(0, cum[-1], samples)
    resampled = np.stack([np.interp(s, cum, guide[:, k]) for k in range(3)], axis=1)
    rng = np.random.default_rng(seed)
    phase = rng.uniform(0, 2*math.pi)
    tangent_prev = None
    normal = None
    path = []
    for i, p in enumerate(resampled):
        t = i/(samples-1)
        tangent = resampled[min(i+1, samples-1)]-resampled[max(i-1, 0)]
        tangent /= max(np.linalg.norm(tangent), 1e-9)
        if normal is None:
            helper = np.array([1.0, 0, 0]) if abs(tangent[0]) < 0.9 else np.array([0, 0, 1.0])
            normal = np.cross(tangent, helper)
            normal /= np.linalg.norm(normal)
        else:
            normal = normal-tangent*normal.dot(tangent)
            normal /= max(np.linalg.norm(normal), 1e-9)
        binormal = np.cross(tangent, normal)
        angle = phase+t*turns*2*math.pi
        r = radius*min(1.0, t*6.0+0.15)*(1.0-0.25*t)
        offset = normal*math.cos(angle)*r+binormal*math.sin(angle)*r
        if frizz:
            offset += rng.normal(0, frizz, 3)*min(1.0, t*4)
        path.append(tuple(p+offset))
    return path


def oriented_torus(name, center, axis, major, minor, transform, mat, segments=24, sides=6):
    axis = np.asarray(axis, float)/np.linalg.norm(axis)
    ref = np.cross(axis, [1.0, 0.0, 0.0])
    ref /= np.linalg.norm(ref)
    other = np.cross(axis, ref)
    points, faces = [], []
    for i in range(segments):
        a = 2*math.pi*i/segments
        radial = ref*math.cos(a)+other*math.sin(a)
        for j in range(sides):
            b = 2*math.pi*j/sides
            points.append(tuple(np.asarray(center)+radial*(major+minor*math.cos(b))+axis*minor*math.sin(b)))
    for i in range(segments):
        for j in range(sides):
            i2, j2 = (i+1) % segments, (j+1) % sides
            faces.append((i*sides+j, i2*sides+j, i2*sides+j2, i*sides+j2))
    return mesh_object(name, points, faces, transform, mat)


def surface_path(surface, start, end, steps, lift_profile, rng, wave=0.0, part_push=None):
    """Points from start to end projected onto the scalp with a lift profile."""
    path = []
    for i in range(steps+1):
        t = i/steps
        p = np.asarray(start)*(1-t)+np.asarray(end)*t
        if part_push is not None:
            p = p+np.asarray(part_push)*math.sin(math.pi*min(1.0, t*2.2))
        d = Vector(p)-surface.center
        lift = float(np.interp(t, [0, 0.35, 0.75, 1.0], lift_profile))
        proj, normal = surface.project(d, lift)
        if proj is None:
            proj, normal = Vector(p), d.normalized()
        q = np.array(proj)
        if wave:
            side = np.cross(np.array(normal), (np.asarray(end)-np.asarray(start)))
            side /= max(np.linalg.norm(side), 1e-9)
            q = q+side*wave*math.sin(t*math.pi*3+rng.uniform(0, 6.28))*math.sin(math.pi*t)
        path.append((q, np.array(normal)))
    return path


def lateral_on_surface(path):
    lateral = []
    n = len(path)
    for i, (p, normal) in enumerate(path):
        tangent = path[min(i+1, n-1)][0]-path[max(i-1, 0)][0]
        side = np.cross(normal, tangent)
        side /= max(np.linalg.norm(side), 1e-9)
        lateral.append(side)
    return lateral


def hanging_path(surface, guide, samples, clearance, rng, sway=0.05):
    guide = np.asarray(guide, float)
    seg = np.linalg.norm(np.diff(guide, axis=0), axis=1)
    cum = np.concatenate(([0], np.cumsum(seg)))
    s = np.linspace(0, cum[-1], samples)
    pts = np.stack([np.interp(s, cum, guide[:, k]) for k in range(3)], axis=1)
    phase = rng.uniform(0, 6.28)
    out = []
    for i, q in enumerate(pts):
        t = i/(samples-1)
        q = q+np.array([sway*math.sin(t*math.pi*2.2+phase), 0, sway*0.6*math.cos(t*math.pi*1.7+phase)])*t
        out.append(np.array(surface.push_out(q, clearance)))
    return out


def x_cards(path, widths, variant, twist):
    """Two crossed strips along a hanging path: visible from every angle."""
    cards = []
    n = len(path)
    for k, base_angle in enumerate((0.0, math.pi/2)):
        lateral = []
        for i, p in enumerate(path):
            tangent = path[min(i+1, n-1)]-path[max(i-1, 0)]
            tangent /= max(np.linalg.norm(tangent), 1e-9)
            ref = np.cross(tangent, [0.0, 0.0, 1.0])
            if np.linalg.norm(ref) < 1e-6:
                ref = np.cross(tangent, [1.0, 0.0, 0.0])
            ref /= np.linalg.norm(ref)
            other = np.cross(tangent, ref)
            a = base_angle+twist*i/(n-1)
            lateral.append(ref*math.cos(a)+other*math.sin(a))
        cards.append(card_strip(path, lateral, widths, variant, curvature=0.12))
    return cards


def scalp_point(surface, a, y, lift):
    """Scalp point at azimuth a (0 = face) and approximate height y."""
    d = (math.sin(a), (y-HEAD_CENTER[1])/0.72, math.cos(a))
    return surface.project(d, lift)


def build_hair_v04(points, uv, groups, transform, arm, directory):
    rng = np.random.default_rng(72269)
    surface = HeadSurface(points, groups['body'])
    atlas = hair_atlas(directory, HAIR_BASE, HAIR_TIP, HAIR_WARM)
    lockmat = hair_tile('MediumBrownHair', directory, HAIR_BASE, HAIR_TIP, .50, 3)
    tiemat = material('Inez_GrayElasticHairTie', (.18, .18, .19), .62)  # linear; light-gray band (original B rear)
    tie, tie_normal = surface.project((0.0, 0.66, -0.75), 0.04)
    tie = np.array(tie)
    tie_normal = np.array(tie_normal)
    objects = [scalp_cap(points, uv, groups, transform, arm, directory, tie)]
    # ---- cards on the scalp, from all around the hairline to the tie -------
    scalp_cards = []
    starts = []
    for a in np.linspace(-1.05, 1.05, 19):
        if abs(a) < 0.04:
            continue
        starts.append((a, 0.02, 0.14))
        starts.append((a+0.05, 0.30, 0.15))
        starts.append((a-0.03, 0.62, 0.15))
    for sign in (-1, 1):
        for a in np.linspace(1.25, 2.05, 6):
            starts.append((sign*a, 0.06, 0.15))
            starts.append((sign*a+0.08, 0.40, 0.15))
        for a in np.linspace(2.12, 3.08, 8):
            starts.append((sign*a, 0.03, 0.15))
            starts.append((sign*a, 0.38, 0.15))
    for k, (a, above, half) in enumerate(starts):
        a += rng.normal(0, 0.035)
        above += rng.uniform(-0.03, 0.05)
        x_dir, z_dir = math.sin(a), math.cos(a)
        y0 = hairline_height(0.7*x_dir, HEAD_CENTER[2]+0.7*z_dir)+above
        start, _ = scalp_point(surface, a, y0, 0.045)
        if start is None:
            continue
        start = np.array(start)
        push = None
        if abs(a) < 0.30:
            push = (math.copysign(0.10, a), 0.05, 0.0)
        path = surface_path(surface, start, tie, 16, (0.045, 0.080, 0.090, 0.085), rng, wave=0.025, part_push=push)
        lateral = lateral_on_surface(path)
        widths = list(np.interp(np.linspace(0, 1, len(path)), [0, 0.6, 1.0], [half, half*0.85, 0.05]))
        scalp_cards.append(card_strip([p for p, n in path], lateral, widths, 'dense_wavy', curvature=0.10))
    # Soft hairline: short sparse cards rooted just below the hairline.
    for a in np.linspace(-1.15, 1.15, 26):
        a += rng.normal(0, 0.02)
        x_dir, z_dir = math.sin(a), math.cos(a)
        y0 = hairline_height(0.7*x_dir, HEAD_CENTER[2]+0.7*z_dir)-0.03
        start, normal = scalp_point(surface, a, y0, 0.03)
        if start is None:
            continue
        start = np.array(start)
        target = np.array(start)+(tie-np.array(start))*0.22
        path = surface_path(surface, start, target, 6, (0.03, 0.05, 0.06, 0.06), rng, wave=0.01)
        lateral = lateral_on_surface(path)
        scalp_cards.append(card_strip([p for p, n in path], lateral, [0.07]*len(path), 'flyaway', curvature=0.05))
    # Curly volume at the temples/sides above the ears (original A).
    for sign in (-1, 1):
        for k in range(11):
            a = sign*rng.uniform(0.85, 1.75)
            y0 = rng.uniform(6.98, 7.38)
            start, normal = scalp_point(surface, a, y0, 0.10+rng.uniform(0.0, 0.08))
            if start is None:
                continue
            start = np.array(start)
            path = surface_path(surface, start, tie, 12, (0.12, 0.17, 0.15, 0.09), rng, wave=0.05)
            lateral = lateral_on_surface(path)
            widths = list(np.interp(np.linspace(0, 1, len(path)), [0, 0.5, 1.0], [0.16, 0.18, 0.06]))
            scalp_cards.append(card_strip([p for p, n in path], lateral, widths, 'loose_curly', curvature=0.18))
    # Crown frizz halo (original A: uneven fine flyaways).
    for k in range(18):
        a = rng.uniform(-1.4, 1.4)
        start, normal = scalp_point(surface, a, 7.55+rng.uniform(0, 0.25), 0.12+rng.uniform(0, 0.06))
        if start is None:
            continue
        start = np.array(start)
        end = start+(tie-start)*rng.uniform(0.35, 0.6)+np.array(normal)*0.05
        path = [start*(1-t)+end*t+np.array(normal)*0.04*math.sin(math.pi*t) for t in np.linspace(0, 1, 8)]
        side = np.cross(np.array(normal), end-start)
        side /= max(np.linalg.norm(side), 1e-9)
        scalp_cards.append(card_strip(path, [side]*len(path), [0.09]*len(path), 'flyaway', curvature=0.05))
    crown = card_object('Inez_Crown_PulledCurlyLocks', scalp_cards, transform, atlas)
    skin_rigid(crown, arm, 'head')
    objects.append(crown)
    # ---- face-framing tendrils (temples to jaw/neck) ------------------------
    tendril_cards, tendril_tubes, tendril_radii = [], [], []
    for sign in (-1, 1):
        for k in range(12):
            a = sign*rng.uniform(0.42, 1.12)
            x_dir, z_dir = math.sin(a), math.cos(a)
            y0 = hairline_height(0.7*x_dir, HEAD_CENTER[2]+0.7*z_dir)+0.03
            root, normal = scalp_point(surface, a, y0, 0.05)
            if root is None:
                continue
            root = np.array(root)
            outward = np.array([x_dir, 0.0, z_dir*0.35])
            end_y = rng.uniform(5.45, 6.30)
            drop = root[1]-end_y
            mid = root+outward*rng.uniform(0.10, 0.22)+np.array([0, -drop*0.45, 0])
            end = root+outward*rng.uniform(0.12, 0.30)+np.array([0, -drop, rng.uniform(-0.25, 0.0)])
            path = hanging_path(surface, [root, root*0.6+mid*0.4, mid, end], 18, 0.07, rng, 0.045)
            widths = list(np.interp(np.linspace(0, 1, len(path)), [0, 0.3, 1.0], [0.06, 0.11, 0.045]))
            tendril_cards.extend(x_cards(path, widths, 'crimped_lock', rng.uniform(-0.8, 0.8)))
            if k % 3 == 0:
                tube = curl_path(root, path, rng.uniform(10, 14), 0.014, seed=5000+k*(sign+3), samples=60, frizz=0.002)
                tendril_tubes.append([tuple(surface.push_out(q, 0.06)) for q in tube])
                tendril_radii.append(0.016)
    frame = card_object('Inez_FramingCurls', tendril_cards, transform, atlas)
    skin_rigid(frame, arm, 'head')
    objects.append(frame)
    if tendril_tubes:
        frametubes = tubes('Inez_FramingCurlLocks', tendril_tubes, tendril_radii, transform, lockmat, sides=4)
        skin_rigid(frametubes, arm, 'head')
        objects.append(frametubes)
    # ---- ponytail: short, voluminous, crimped (original B rear) ---------------
    pony_cards, pony_tubes, pony_radii = [], [], []
    up = np.array([0.0, 1.0, 0.0])
    for k in range(72):
        a = rng.uniform(0, 2*math.pi)
        rr = math.sqrt(rng.uniform(0, 1))*0.09
        lateral_axis = np.cross(tie_normal, up)
        lateral_axis /= np.linalg.norm(lateral_axis)
        vertical_axis = np.cross(lateral_axis, tie_normal)
        root = tie+lateral_axis*rr*math.cos(a)+vertical_axis*rr*math.sin(a)
        length = rng.uniform(1.7, 2.45)
        spread = rng.uniform(-0.85, 0.85)
        depth = rng.uniform(-0.18, 0.15)
        p1 = root+tie_normal*0.22+up*0.06+lateral_axis*spread*0.25
        p2 = root+tie_normal*0.42-up*0.30+lateral_axis*spread*0.75
        p3 = root+tie_normal*(0.45+depth)-up*length*0.60+lateral_axis*spread
        p4 = root+tie_normal*(0.35+depth)-up*length+lateral_axis*spread*0.55
        path = hanging_path(surface, [root, p1, p2, p3, p4], 20, 0.14, rng, 0.05)
        widths = list(np.interp(np.linspace(0, 1, len(path)), [0, 0.25, 0.7, 1.0], [0.08, 0.20, 0.17, 0.05]))
        pony_cards.extend(x_cards(path, widths, 'crimped_lock' if k % 2 else 'loose_curly', rng.uniform(-1.2, 1.2)))
        if k % 7 == 0:
            tube = curl_path(root, path, rng.uniform(11, 15), 0.03, seed=6000+k, samples=70, frizz=0.003)
            pony_tubes.append([tuple(surface.push_out(q, 0.13)) for q in tube])
            pony_radii.append(rng.uniform(0.018, 0.026))
    pony = card_object('Inez_Ponytail_Curls', pony_cards, transform, atlas)
    skin_rigid(pony, arm, 'head')
    objects.append(pony)
    ponytubes = tubes('Inez_Ponytail_WarmAccentCurls', pony_tubes, pony_radii, transform, lockmat, sides=5)
    skin_rigid(ponytubes, arm, 'head')
    objects.append(ponytubes)
    # ---- elastic tie around the ponytail base -----------------------------------
    tieobj = oriented_torus('Inez_HairTie', tie+tie_normal*0.07, tie_normal, 0.10, 0.03, transform, tiemat)
    skin_rigid(tieobj, arm, 'head')
    objects.append(tieobj)
    for obj in objects:
        obj['hair_geometry_status'] = 'v04 hair cards + crimp locks; original-guided proposal for hidden areas'
        obj['source_authority'] = 'Original A framing/crown; original B high curly ponytail rear volume'
    report = {'tie_point_source': [float(v) for v in tie], 'tie_normal': [float(v) for v in tie_normal],
              'scalp_cards': len(scalp_cards), 'tendril_cards': len(tendril_cards),
              'ponytail_cards': len(pony_cards), 'tube_locks': len(tendril_tubes)+len(pony_tubes)}
    return objects, report
