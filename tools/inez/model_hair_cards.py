"""Hair-card atlas and card geometry for the v04 groom.

Cards are double-sided strips with a procedurally drawn strand atlas (alpha
MASK in glTF). V runs from root (0) to tip (1); each atlas column holds one
variant. Strand colors come from sRGB samples of original A/B hair.
"""
import math

import bpy
import numpy as np

from model_geometry import mesh_object
from model_materials import material, save_image, connect_pbr, normal_from_height

VARIANTS = {  # name: (column, strands, crimp amplitude, wavelength, coverage width, tip taper)
    'dense_wavy': (0, 190, 0.018, 0.110, 0.86, 0.50),
    'crimped_lock': (1, 130, 0.034, 0.065, 0.66, 0.70),
    'loose_curly': (2, 110, 0.050, 0.090, 0.76, 0.80),
    'flyaway': (3, 30, 0.050, 0.140, 0.90, 0.95),
}
COLUMNS = 4


def hair_atlas(directory, base, tip, warm, width=2048, height=1024, seed=91):
    """Strand atlas: strands are grouped into clumps that crimp coherently, so
    each card reads as damp curly locks rather than straight streaks."""
    rng = np.random.default_rng(seed)
    col_w = width//COLUMNS
    coverage = np.zeros((height, width), np.float32)
    color = np.zeros((height, width, 3), np.float32)
    rows = np.arange(height, dtype=np.float32)
    v = rows/(height-1)
    for name, (column, count, amp, wave, spread, taper) in VARIANTS.items():
        x0 = column*col_w
        clumps = max(3, count//18)
        clump_params = [(0.5+rng.uniform(-0.5, 0.5)*spread, rng.uniform(0, 2*math.pi), wave*rng.uniform(0.8, 1.25),
                         amp*rng.uniform(0.7, 1.3), rng.uniform(-0.05, 0.05)) for _ in range(clumps)]
        for s in range(count):
            c_u, c_phase, c_lam, c_amp, c_drift = clump_params[rng.integers(0, clumps)]
            offset = rng.normal(0, 0.035)
            start = rng.uniform(0.0, 0.10)
            end = 1.0-rng.uniform(0.0, 0.45)*taper
            phase = c_phase+rng.normal(0, 0.35)
            wobble = 0.6*np.sin(2*math.pi*v/(c_lam*2.7)+rng.uniform(0, 6.3))
            u = (c_u+offset+c_amp*np.sin(2*math.pi*v/c_lam+phase+wobble)
                 + 0.35*c_amp*np.sin(4*math.pi*v/c_lam+2*phase)+c_drift*v
                 + 0.0035*np.sin(2*math.pi*v/0.011+rng.uniform(0, 6.3)))
            # Clumps tighten toward their tips like damp curls.
            u = c_u+(u-c_u)*(1.0-0.35*v)
            u = 0.5+(u-0.5)*(0.82+0.18*np.clip(v*4, 0, 1))
            px = u*(col_w-1)
            w = rng.uniform(0.8, 1.3)*(1.0-0.45*np.clip((v-start)/max(end-start, 1e-3), 0, 1))
            alive = (v >= start) & (v <= end)
            fade = np.clip((end-v)/0.06, 0, 1)*np.clip((v-start)/0.03, 0, 1)
            shade = rng.uniform(0.0, 1.0)
            strand_color = np.asarray(base)*(1-shade*0.35)+np.asarray(warm)*shade*0.35
            if rng.uniform() < 0.18:
                strand_color = np.asarray(warm)
            for off in range(-3, 4):
                cols = np.floor(px).astype(int)+off
                dist = np.abs(cols+0.5-px)
                weight = np.exp(-(dist/np.maximum(w, 0.3))**2*1.6)*fade*alive
                valid = (cols >= 0) & (cols < col_w) & (weight > 1e-3)
                rr, cc = rows[valid].astype(int), cols[valid]+x0
                tipmix = np.clip(v[valid]*1.2, 0, 1)[:, None]
                c = strand_color*(1-tipmix*0.45)+np.asarray(tip)*tipmix*0.45
                np.add.at(coverage, (rr, cc), weight[valid])
                np.add.at(color, (rr, cc), c*weight[valid][:, None])
    alpha = np.clip(coverage*1.15, 0, 1)
    albedo = color/np.maximum(coverage, 1e-4)[:, :, None]
    albedo = np.where(coverage[:, :, None] > 1e-4, albedo, np.asarray(base))
    rgba = np.concatenate((albedo, alpha[:, :, None]), axis=2).astype(np.float32)
    img = bpy.data.images.new('InezHairCards_albedo', width=width, height=height, alpha=True)
    img.colorspace_settings.name = 'sRGB'
    img.pixels.foreach_set(np.clip(rgba, 0, 1).reshape(-1))
    from pathlib import Path
    Path(directory).mkdir(parents=True, exist_ok=True)
    img.filepath_raw = str(Path(directory)/'InezHairCards_albedo.png')
    img.file_format = 'PNG'
    img.save()
    img.pack()
    heightmap = np.clip(coverage, 0, 1.5)
    normal = normal_from_height(heightmap, .35)
    rough = np.full(coverage.shape, .58, np.float32)-0.06*np.clip(coverage, 0, 1)
    rough_img = save_image('InezHairCards_roughness', rough, directory, True)
    normal_img = save_image('InezHairCards_normal', normal, directory, True)
    mat = material('Inez_HairCards_PBR', base, .55)
    connect_pbr(mat, img, rough_img, normal_img, normal_strength=.15)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    albedo_node = next(n for n in nodes if n.type == 'TEX_IMAGE' and n.image == img)
    clip = nodes.new('ShaderNodeMath')
    clip.operation = 'ROUND'
    links.new(albedo_node.outputs['Alpha'], clip.inputs[0])
    links.new(clip.outputs[0], bsdf.inputs['Alpha'])
    mat.surface_render_method = 'DITHERED'
    mat.use_backface_culling = False
    mat['hair_atlas'] = 'Procedural clumped strand atlas; columns: '+', '.join(VARIANTS)
    return mat


def card_strip(path, lateral, widths, variant, curvature=0.18):
    """Vertices/faces/uvs for one card: 3 vertices across (bowed center)."""
    column = VARIANTS[variant][0]
    u0, u1 = column/COLUMNS+0.004, (column+1)/COLUMNS-0.004
    pts, uvs = [], []
    n = len(path)
    for i, p in enumerate(path):
        p = np.asarray(p, float)
        side = np.asarray(lateral[i], float)
        w = widths[i]
        tangent = np.asarray(path[min(i+1, n-1)], float)-np.asarray(path[max(i-1, 0)], float)
        tangent /= max(np.linalg.norm(tangent), 1e-9)
        bow = np.cross(tangent, side)
        bow /= max(np.linalg.norm(bow), 1e-9)
        v = i/(n-1)
        for j, s in enumerate((-1.0, 0.0, 1.0)):
            pts.append(p+side*w*s+bow*w*curvature*(1-abs(s)))
            uvs.append((u0+(u1-u0)*(j/2), v))
    faces = []
    for i in range(n-1):
        for j in range(2):
            a = i*3+j
            faces.append((a, a+1, a+4, a+3))
    return pts, faces, uvs


def card_object(name, cards, transform, mat):
    points, faces, uvs = [], [], []
    for pts, fcs, uv in cards:
        base = len(points)
        points.extend(tuple(p) for p in pts)
        uvs.extend(uv)
        faces.extend(tuple(base+k for k in f) for f in fcs)
    corner_uvs = [[uvs[k] for k in f] for f in faces]
    obj = mesh_object(name, points, faces, transform, mat, uv_faces=corner_uvs)
    obj['hair_card_count'] = len(cards)
    return obj
