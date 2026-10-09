"""Assemble the production Inez from the rigged figure and the user's two source models.

    blender -b FITTED_BUILD.blend --python tools/inez/source_assemble.py -- \
        --source-blend assets/characters/inez/model/work/source_aligned/source_aligned.blend \
        --regions-a .../SRC_A_regions.npz --regions-b .../SRC_B_regions.npz \
        --output-blend model/inez_master.blend --output-glb model/inez_master.glb \
        --texture-dir assets/characters/inez/textures [--manifest reports/assembly.json]

Input: a model_dress_v04.py build carrying the SourceBodyFit (Asset A pose and
proportions) and SourceHeadWrap (Asset B face) identity layers, built with
--skip-hair. The procedural costume, hair cards and brow tubes are removed and
replaced by the user's own geometry and textures:

  sweater, jeans, boots  Asset A regions (source_regions.py), decimated to a
                         game budget, colour-corrected toward the turnaround
                         (charcoal knit with navy stripes, black denim)
  hair                   Asset B hair shell (curly high ponytail, framing curls)
  head skin colour       Asset B base colour baked onto the 4096x2048 head UV
                         (skin-only bake for the face so B's framing curls are
                         not painted onto the skin; full bake under the hair)

Garments are skinned part-aware: each vertex takes weights from the body part
of its nearest bone segment (sleeves follow the arm even where they lie
against the torso; jean legs never take the other leg's weights). Body faces
hidden under the garments are deleted. The source GLBs are only read.
"""
import argparse
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from model_materials import save_image

BODY = 'Inez_ContinuousHumanMesh_UNAPPROVED'
REGIONS = ['skin', 'hair', 'sweater', 'jeans', 'boots', 'eye', 'other']
REMOVE_PREFIXES = ('Inez_Sweater', 'Inez_Jeans', 'Inez_Boot', 'Inez_Brows_', 'Inez_ScalpHair', 'Inez_Crown',
                   'Inez_Ponytail', 'Inez_Framing', 'Inez_Hair', 'Inez_Baby', 'Inez_Temple', 'Inez_Flyaway',
                   'Inez_Tendril', 'Inez_Tie')


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-blend', required=True)
    parser.add_argument('--regions-a', required=True)
    parser.add_argument('--regions-b', required=True)
    parser.add_argument('--output-blend', required=True)
    parser.add_argument('--output-glb', required=True)
    parser.add_argument('--texture-dir', required=True)
    parser.add_argument('--manifest')
    parser.add_argument('--targets', default='sweater=60000,jeans=50000,boots=40000,hair=110000')
    parser.add_argument('--head-size', default='4096x2048')
    parser.add_argument('--game-head-size', default='2048x1024')
    parser.add_argument('--no-colour-correction', action='store_true')
    # Linear gain on the skin albedo (head bake and body), measured with
    # tools/inez/skin_tone_compare.py against both original portraits.
    # The dressed build's --dump-fitted output: every source vertex, helpers
    # included, after all identity layers (teeth/tongue come from it).
    parser.add_argument('--fitted', default='')
    # Linear gain on the skin albedo (head bake and body). Chroma measured
    # with tools/inez/skin_tone_compare.py against both original portraits
    # (0.89, 1.075, 1.015) at matched exposure. Level x0.42 so the cheek /
    # grey-knit luminance ratio approaches the originals' 2.64-2.70: it read
    # 4.4 at x1.0 and 3.67 at x0.70 (AgX compresses: on-screen ratio ~ level^0.54).
    parser.add_argument('--skin-gain', default='0.3738,0.4515,0.4263')
    # Linear median of the hair albedo. The originals' hair reads R/G ~1.5-1.9,
    # G/B ~1.4-2.0 as rendered; the albedo is set more saturated (2.0, 2.4)
    # because the grey specular sheen desaturates dark strands (measured with
    # the same landmark patches as the skin). Pass 3: the render read 2x the
    # originals' hair/cheek luminance at the crown (0.30 vs 0.14-0.16) and
    # R/G 1.92 at the sides (originals 1.61-1.77), so the albedo is darker and
    # less saturated (R/G 1.78, G/B 1.99) and the sheen lower.
    parser.add_argument('--hair-target-linear', default='0.024,0.0135,0.0068')
    return parser.parse_args(sys.argv[sys.argv.index('--')+1:])


# ---------------------------------------------------------------- parts

def append_sources(path):
    with bpy.data.libraries.load(str(Path(path).resolve()), link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n in ('SRC_A_FullBody', 'SRC_B_HeadBust')]
    objs = {}
    for obj in dst.objects:
        bpy.context.scene.collection.objects.link(obj)
        objs[obj.name] = obj
    # Appended objects carry a stale matrix_world until the depsgraph updates;
    # without this the first extracted part kept raw generator units.
    bpy.context.view_layer.update()
    return objs['SRC_A_FullBody'], objs['SRC_B_HeadBust']


def extract_part(src, labels, wanted, name):
    """New object holding the source faces whose majority vertex label is wanted."""
    mesh = src.data.copy()
    mesh.name = name
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.matrix_world = src.matrix_world
    counts = np.empty(len(mesh.polygons), np.int64)
    mesh.polygons.foreach_get('loop_total', counts)
    loops = np.empty(len(mesh.loops), np.int64)
    mesh.loops.foreach_get('vertex_index', loops)
    starts = np.concatenate(([0], np.cumsum(counts)[:-1]))
    # Triangles (Tripo exports triangles): majority of the three corner labels.
    a, b, c = (labels[loops[starts+k]] for k in range(3))
    majority = np.where((a == b) | (a == c), a, np.where(b == c, b, a))
    keep = np.isin(majority, list(wanted))
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()
    doomed = [bm.faces[i] for i in np.flatnonzero(~keep)]
    bmesh.ops.delete(bm, geom=doomed, context='FACES')
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context='VERTS')
    # Tripo splits vertices along every UV seam, so each atlas island is a
    # disconnected patch; weld exact duplicates (UVs stay per-corner, the seams
    # remain UV seams) so decimation sees one continuous surface.
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bm.to_mesh(mesh)
    bm.free()
    # Bake the placement into the vertices (metric world space).
    mesh.transform(obj.matrix_world)
    obj.matrix_world = Matrix.Identity(4)
    mesh.update()
    return obj


def drop_small_islands(obj, min_faces):
    """Remove disconnected patches smaller than min_faces (stray mislabelled bits)."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    seen, small = set(), []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack, island = [f], []
        seen.add(f.index)
        while stack:
            g = stack.pop()
            island.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen:
                        seen.add(h.index)
                        stack.append(h)
        if len(island) < min_faces:
            small.extend(island)
    bmesh.ops.delete(bm, geom=small, context='FACES')
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context='VERTS')
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return len(small)


def face_islands(bm):
    seen, islands = set(), []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack, island = [f], []
        seen.add(f.index)
        while stack:
            g = stack.pop()
            island.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen:
                        seen.add(h.index)
                        stack.append(h)
        islands.append(island)
    islands.sort(key=len, reverse=True)
    return islands


def keep_attached_islands(obj, min_faces, max_gap, above_main=0.0):
    """Keep the largest island plus islands of at least min_faces lying within
    max_gap of it and not higher than its top by more than above_main.
    Mislabelled source patches (an iris read as knit, brows read as hair) sit
    away from the garment or hair mass and are removed."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    islands = face_islands(bm)
    main = islands[0]
    main_verts = {v for f in main for v in f.verts}
    tree = KDTree(len(main_verts))
    for i, v in enumerate(main_verts):
        tree.insert(v.co, i)
    tree.balance()
    top = max(v.co.z for v in main_verts)
    doomed, kept = [], 1
    for island in islands[1:]:
        verts = list({v for f in island for v in f.verts})
        gap = min(tree.find(v.co)[2] for v in verts[::max(1, len(verts)//200)])
        high = max(v.co.z for v in verts) > top+above_main
        if len(island) < min_faces or gap > max_gap or high:
            doomed.extend(island)
        else:
            kept += 1
    bmesh.ops.delete(bm, geom=doomed, context='FACES')
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context='VERTS')
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return {'islands_kept': kept, 'islands_removed': len(islands)-kept, 'faces_removed': len(doomed)}


def decimate(obj, target):
    tris = sum(len(p.vertices)-2 for p in obj.data.polygons)
    if tris > target:
        mod = obj.modifiers.new('Decimate', 'DECIMATE')
        mod.ratio = target/tris
        mod.use_collapse_triangulate = True
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=mod.name)
    for p in obj.data.polygons:
        p.use_smooth = True
    if obj.data.has_custom_normals:
        bpy.context.view_layer.objects.active = obj
        bpy.ops.mesh.customdata_custom_splitnormals_clear()
    return tris, sum(len(p.vertices)-2 for p in obj.data.polygons)


# ---------------------------------------------------------------- materials

def image_pixels(img):
    w, h = img.size
    px = np.empty(w*h*4, np.float32)
    img.pixels.foreach_get(px)
    return px.reshape(h, w, 4)


def corrected_material(src_mat, name, region_colours, kind, texdir):
    """Copy the source material with a colour-corrected base-colour atlas copy."""
    mat = src_mat.copy()
    mat.name = name
    nodes = mat.node_tree.nodes
    bsdf = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')
    link = bsdf.inputs['Base Color'].links[0] if bsdf.inputs['Base Color'].links else None
    if link is None:
        return mat, None
    tex = link.from_node
    src_img = tex.image
    px = image_pixels(src_img)
    srgb_lin = lambda c: np.where(np.asarray(c) <= 0.04045, np.asarray(c)/12.92, ((np.asarray(c)+0.055)/1.055)**2.4)
    note = {'mapping': 'none'}
    if kind == 'sweater':
        Lc = srgb_lin(region_colours)@np.array([0.2126, 0.7152, 0.0722])
        dark, light = float(np.percentile(Lc, 30)), float(np.percentile(Lc, 70))
        charcoal = srgb_lin([0.245, 0.245, 0.255]).astype(np.float32)
        navy = srgb_lin([0.034, 0.040, 0.088]).astype(np.float32)
        # The turnaround's stripes read navy/grey luminance ~0.18 (measured on
        # the front and back panels); a smoothstep between the 30th and 70th
        # source percentiles keeps the stripes crisp instead of blending.
        note = {'mapping': 'light knit -> charcoal, dark knit -> navy (smoothstep), knit luminance variation kept',
                'source_dark_light_linear': [dark, light], 'charcoal_srgb': [0.245, 0.245, 0.255],
                'navy_srgb': [0.034, 0.040, 0.088], 'target_navy_grey_luminance_ratio': 0.18}
    elif kind == 'jeans':
        # Turnaround jeans/knit-grey luminance ~0.32 (front and back panels).
        note = {'mapping': 'washed charcoal denim -> black (linear gain 0.28)', 'target_jeans_knit_ratio': 0.32}
    srgb = np.empty(px.shape[:2]+(3,), np.float32)
    for r0 in range(0, px.shape[0], 512):
        rgb = px[r0:r0+512, :, :3]
        lin = np.where(rgb <= 0.04045, rgb/12.92, ((rgb+0.055)/1.055)**2.4)
        if kind == 'sweater':
            L = lin@np.array([0.2126, 0.7152, 0.0722], np.float32)
            t = np.clip((L-dark)/max(light-dark, 1e-4), 0, 1)
            t = (t*t*(3-2*t))[:, :, None]
            ref_L = dark*(1-t)+light*t
            out = (navy*(1-t)+charcoal*t)*np.clip(L[:, :, None]/np.maximum(ref_L, 1e-4), 0.4, 1.8)
        elif kind == 'jeans':
            out = lin*0.28
        else:
            out = lin
        out = np.clip(out, 0, 1)
        srgb[r0:r0+512] = np.where(out <= 0.0031308, out*12.92, 1.055*out**(1/2.4)-0.055)
    del px
    img = save_image(name+'_basecolor', srgb, texdir)
    tex_new = nodes.new('ShaderNodeTexImage')
    tex_new.image = img
    tex_new.location = tex.location+Vector((0, -300))
    for out_link in list(tex.outputs['Color'].links):
        mat.node_tree.links.new(tex_new.outputs['Color'], out_link.to_socket)
    return mat, note


def hair_material(src_mat, hair_colours, texdir, target_linear=(0.042, 0.021, 0.0088)):
    """Asset B's hair reads light auburn; the originals are a darker, less red
    medium brown with golden tips (sampled hair R/G ~1.8, G/B ~1.95 under their
    neutral light). Per-channel linear gain moves B's median hair colour to the
    target while keeping its strand texture and highlights."""
    mat = src_mat.copy()
    mat.name = 'Inez_Hair_FromAssetB'
    nodes = mat.node_tree.nodes
    bsdf = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')
    tex = bsdf.inputs['Base Color'].links[0].from_node
    to_lin = lambda c: np.where(np.asarray(c) <= 0.04045, np.asarray(c)/12.92, ((np.asarray(c)+0.055)/1.055)**2.4)
    median = np.median(to_lin(hair_colours), axis=0)
    target_linear = np.asarray(target_linear, np.float64)
    gain = np.clip(target_linear/np.maximum(median, 1e-4), 0.3, 1.25).astype(np.float32)
    px = image_pixels(tex.image)
    srgb = np.empty(px.shape[:2]+(3,), np.float32)
    for r0 in range(0, px.shape[0], 512):
        lin = to_lin(px[r0:r0+512, :, :3])*gain
        lin = np.clip(lin, 0, 1)
        srgb[r0:r0+512] = np.where(lin <= 0.0031308, lin*12.92, 1.055*lin**(1/2.4)-0.055)
    del px
    img = save_image('Inez_Hair_FromAssetB_basecolor', srgb, texdir)
    new_tex = nodes.new('ShaderNodeTexImage')
    new_tex.image = img
    for link in list(tex.outputs['Color'].links):
        mat.node_tree.links.new(new_tex.outputs['Color'], link.to_socket)
    # Hair is a dielectric: Asset B's map carries a little metalness (median
    # 0.035), which greys the dark strands. A warm specular tint keeps the
    # sheen brown, as on the originals' wet curls.
    for link in list(bsdf.inputs['Metallic'].links):
        mat.node_tree.links.remove(link)
    bsdf.inputs['Metallic'].default_value = 0.0
    bsdf.inputs['Specular IOR Level'].default_value = 0.3
    bsdf.inputs['Specular Tint'].default_value = (1.0, 0.78, 0.58, 1.0)
    to_srgb = lambda c: [float(v) for v in np.where(c <= 0.0031308, c*12.92, 1.055*np.maximum(c, 0)**(1/2.4)-0.055)]
    return mat, {'source_median_srgb': to_srgb(median), 'source_median_linear': median.tolist(),
                 'target_median_linear': target_linear.tolist(), 'target_median_srgb': to_srgb(target_linear),
                 'linear_gain': gain.tolist()}


# ---------------------------------------------------------------- necklace

def build_necklace(body, sweater, arm, parts, texdir):
    """Fine silver chain resting on the neck above the collar and falling in a
    V over the sweater front to a tiny pendant, as in both originals (pendant
    about 6.5 cm below the front neckline). The pendant motif is not
    resolvable in the originals, so it is a plain drop."""
    for name in ('Inez_FineSilverNecklace', 'Inez_TinyUnknownMotifPendant'):
        obj = bpy.data.objects.get(name)
        if obj:
            bpy.data.objects.remove(obj, do_unlink=True)
    rest, _ = body_rest_positions(body)
    sw = np.array([sweater.matrix_world @ v.co for v in sweater.data.vertices])
    eyes = [arm.matrix_world @ arm.data.bones['eye.'+sd].head_local for sd in ('L', 'R')]
    mid_x = (eyes[0].x+eyes[1].x)/2
    front_collar = sw[(np.abs(sw[:, 0]-mid_x) < 0.05) & (sw[:, 1] < np.median(sw[:, 1]))]
    collar_z = float(np.percentile(front_collar[:, 2], 98))
    ring = rest[(rest[:, 2] > collar_z+0.004) & (rest[:, 2] < collar_z+0.03) & (np.abs(rest[:, 0]-mid_x) < 0.09)]
    cx, cy = float(np.median(ring[:, 0])), float(np.median(ring[:, 1]))
    # Neckline height per direction around the neck (front = -Y), from the
    # knit's open boundary near the neck; robust median per 5-degree bin and
    # clamped to a crew neck's rise (the back hole edges must not pull it).
    bm = bmesh.new()
    bm.from_mesh(sweater.data)
    edge_v = {v.index for e in bm.edges if e.is_boundary for v in e.verts}
    bm.free()
    bnd = sw[sorted(edge_v)]
    rel = bnd[:, :2]-np.array([cx, cy])
    rad = np.hypot(rel[:, 0], rel[:, 1])
    ang = np.arctan2(rel[:, 0], -rel[:, 1])
    near = (rad < 0.10) & (bnd[:, 2] > collar_z-0.02) & (bnd[:, 2] < collar_z+0.08)
    bins = np.linspace(-math.pi, math.pi, 73)
    tops = np.full(72, np.nan)
    for k in range(72):
        sel = near & (ang >= bins[k]) & (ang < bins[k+1])
        if sel.sum() >= 2:
            tops[k] = np.median(bnd[sel, 2])
    tops = np.clip(tops, collar_z, collar_z+0.045)
    good = ~np.isnan(tops)
    centres = (bins[:-1]+bins[1:])/2
    tops = np.interp(centres, centres[good], tops[good], period=2*math.pi)
    tops = np.convolve(np.concatenate([tops[-5:], tops, tops[:5]]), np.ones(11)/11, 'valid')

    def collar_top(a):
        return float(np.interp((a+math.pi) % (2*math.pi)-math.pi, centres, tops, period=2*math.pi))
    depsgraph = bpy.context.evaluated_depsgraph_get()
    trees = {}
    verts_all, polys_all = [], []
    for obj in (body, sweater):
        mesh = obj.evaluated_get(depsgraph).to_mesh()
        verts = [obj.matrix_world @ v.co for v in mesh.vertices]
        polys = [list(p.vertices) for p in mesh.polygons]
        if obj == body:
            trees['body'] = BVHTree.FromPolygons(verts, polys)
        base = len(verts_all)
        verts_all += verts
        polys_all += [[base+i for i in p] for p in polys]
        obj.evaluated_get(depsgraph).to_mesh_clear()
    trees['all'] = BVHTree.FromPolygons(verts_all, polys_all)
    side = math.radians(75)
    z_pendant = collar_z-0.065

    def neck_point(a):
        # From the neck axis outward: the first surface is the neck skin, so
        # the chain never lands on the shoulders behind the collar.
        z = collar_top(a)+0.004
        hit = trees['body'].ray_cast(Vector((cx, cy, z)), Vector((math.sin(a), -math.cos(a), 0)), 0.2)
        if hit[0] is None:
            return None
        return hit[0]+hit[1].normalized()*0.0012

    def surface_point(q, lift=0.0015):
        loc, nor, _, _ = trees['all'].find_nearest(q, 0.1)
        return None if loc is None else loc+nor.normalized()*lift
    hit = trees['all'].ray_cast(Vector((cx, cy-0.16, z_pendant)), Vector((0, 1, 0)), 0.3)
    pendant_point = hit[0]+hit[1].normalized()*0.0015
    left, right = neck_point(side), neck_point(-side)

    def chain_arm(a, b, count=40):
        """V arm from a to b: straight in the front view, as in both originals
        and on Asset A's own modelled necklace (pendant ~6.5 cm below the
        front neckline, arms reaching the neck at the collar). Each point is
        the first surface hit from the front; the depth takes the most
        frontal of three neighbours so the chain rests on the knit's crests."""
        pts = []
        for t in np.linspace(0, 1, count):
            q = a+(b-a)*float(t)
            hit = trees['all'].ray_cast(Vector((q.x, q.y-0.25, q.z)), Vector((0, 1, 0)), 0.5)
            pts.append(Vector(hit[0]) if hit[0] is not None else q.copy())
        ys = [p.y for p in pts]
        out = [a]
        for i in range(1, count-1):
            y = min(ys[max(0, i-1):i+2])-0.0014
            out.append(Vector((pts[i].x, y, pts[i].z)))
        out.append(b)
        return out
    neck = [q for q in (neck_point(float(a)) for a in np.linspace(side, 2*math.pi-side, 140)) if q is not None]
    # Pendant -> left arm -> around the back of the neck -> right arm -> pendant.
    path = chain_arm(pendant_point, left)[:-1]+neck+chain_arm(right, pendant_point)[1:-1]
    radius, sides = 0.0004, 6
    points, faces = [], []
    n = len(path)
    for i, p in enumerate(path):
        t = (path[(i+1) % n]-path[i-1]).normalized()
        u = t.orthogonal().normalized()
        w = t.cross(u)
        for j in range(sides):
            ang = 2*math.pi*j/sides
            points.append(p+(u*math.cos(ang)+w*math.sin(ang))*radius)
    for i in range(n):
        for j in range(sides):
            a0, a1 = i*sides+j, i*sides+(j+1) % sides
            b0, b1 = ((i+1) % n)*sides+j, ((i+1) % n)*sides+(j+1) % sides
            faces.append((a0, a1, b1, b0))
    # Pendant: plain rounded drop below the lowest chain point.
    low = pendant_point
    pend_base = len(points)
    for j in range(16):
        ang = 2*math.pi*j/16
        r = 0.0032*(1-0.35*math.sin(ang))
        points.append(low+Vector((r*math.cos(ang), -0.0012, -0.0040+r*math.sin(ang))))
    points.append(low+Vector((0, -0.0022, -0.0040)))
    for j in range(16):
        faces.append((pend_base+j, pend_base+(j+1) % 16, pend_base+16))
    mesh = bpy.data.meshes.new('Inez_FineSilverNecklace')
    mesh.from_pydata([tuple(p) for p in points], [], faces)
    for poly in mesh.polygons:
        poly.use_smooth = True
    obj = bpy.data.objects.new('Inez_FineSilverNecklace', mesh)
    bpy.context.scene.collection.objects.link(obj)
    mat = bpy.data.materials.new('Inez_FineSilverChain_PBR')
    mat.use_nodes = True
    b = mat.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (0.75, 0.75, 0.77, 1)
    b.inputs['Metallic'].default_value = 1.0
    b.inputs['Roughness'].default_value = 0.3
    mesh.materials.append(mat)
    skin_part_aware(obj, body, arm, parts, allowed={'torso', 'head'})
    return {'chain_points': n, 'front_collar_height_m': collar_z, 'pendant_height_m': z_pendant,
            'side_heights_m': [collar_top(side)+0.004, collar_top(-side)+0.004],
            'pendant': 'plain rounded drop (motif not resolvable in originals)'}


# ---------------------------------------------------------------- skinning

SEGMENTS = {
    'upperarm.{s}': ('upperarm01.{s}', 'lowerarm01.{s}', 0.045), 'forearm.{s}': ('lowerarm01.{s}', 'wrist.{s}', 0.038),
    'hand.{s}': ('wrist.{s}', 'finger3-1.{s}', 0.035), 'thigh.{s}': ('upperleg01.{s}', 'lowerleg01.{s}', 0.075),
    'shin.{s}': ('lowerleg01.{s}', 'foot.{s}', 0.055), 'foot.{s}': ('foot.{s}', 'toe1-1.{s}', 0.045),
}
FALLBACK_BONES = {'foot': 'foot.{s}', 'hand': 'wrist.{s}', 'shin': 'lowerleg01.{s}', 'forearm': 'lowerarm01.{s}',
                  'thigh': 'upperleg01.{s}', 'upperarm': 'upperarm01.{s}'}
PART_GROUPS = {
    'upperarm': ('upperarm', 'shoulder', 'clavicle'), 'forearm': ('lowerarm', 'upperarm02'), 'hand': ('wrist', 'finger', 'metacarpal'),
    'thigh': ('upperleg', 'pelvis'), 'shin': ('lowerleg',), 'foot': ('foot', 'toe'),
}


def body_rest_positions(body):
    """World positions and normals of the body as displayed: identity shape
    keys applied, armature at rest. (mesh.vertices[i].co is the raw MakeHuman
    basis, not the fitted Inez shape.)"""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = body.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    n = len(mesh.vertices)
    co = np.empty(n*3, np.float32)
    mesh.vertices.foreach_get('co', co)
    no = np.empty(n*3, np.float32)
    mesh.vertex_normals.foreach_get('vector', no)
    evaluated.to_mesh_clear()
    M = np.array(body.matrix_world)
    co = co.reshape(-1, 3)@M[:3, :3].T+M[:3, 3]
    no = no.reshape(-1, 3)@M[:3, :3].T
    no /= np.maximum(np.linalg.norm(no, axis=1, keepdims=True), 1e-9)
    if n != len(body.data.vertices):
        raise RuntimeError('Evaluated body vertex count differs from mesh data')
    return co, no


def body_parts(body):
    """Dominant part per body vertex from its licensed weights."""
    names = {g.index: g.name for g in body.vertex_groups}
    parts = []
    for v in body.data.vertices:
        best, bestw = 'torso', 0.0
        acc = {}
        for g in v.groups:
            n = names[g.group]
            key = 'torso'
            for part, prefixes in PART_GROUPS.items():
                if n.startswith(prefixes) and n[-2:] in ('.L', '.R'):
                    key = f'{part}.{n[-1]}'
            if n.startswith(('head', 'neck', 'jaw', 'eye')):
                key = 'head'
            acc[key] = acc.get(key, 0.0)+g.weight
        if acc:
            best = max(acc, key=acc.get)
        parts.append(best)
    return parts


def segment_distance(p, a, b):
    ab = b-a
    t = max(0.0, min(1.0, (p-a).dot(ab)/max(ab.length_squared, 1e-12)))
    return (p-(a+ab*t)).length


def skin_part_aware(garment, body, arm, parts, allowed=None, exclude_head=True):
    """Weights from the k nearest body vertices of the same body part as the
    nearest bone segment (plus the torso near shoulder and hip joints).

    Garments and jewellery never take the head's or face's bones (jaw, lids,
    lips...): a collar copying the throat's jaw weights would open with the
    mouth and would carry the facial morph targets into the export."""
    joints = {b.name: arm.matrix_world @ b.head_local for b in arm.data.bones}
    face_bones = {b.name for b in arm.data.bones['head'].children_recursive} | {'head'} if exclude_head else set()
    segs = []
    for side in ('L', 'R'):
        for key, (a, b, radius) in SEGMENTS.items():
            segs.append((key.format(s=side), joints[a.format(s=side)], joints[b.format(s=side)], radius))
    segs.append(('torso', joints['spine05'], joints['neck01'], 0.13))
    segs.append(('head', joints['neck01'], joints['head']+Vector((0, 0, 0.12)), 0.09))
    body_world = [Vector(p) for p in body_rest_positions(body)[0]]
    trees = {}
    for part in set(parts):
        ids = [i for i, p in enumerate(parts) if p == part]
        tree = KDTree(len(ids))
        for k, i in enumerate(ids):
            tree.insert(body_world[i], i)
        tree.balance()
        trees[part] = tree
    names = {g.index: g.name for g in body.vertex_groups}
    rows = [{names[g.group]: g.weight for g in v.groups} for v in body.data.vertices]
    for g in body.vertex_groups:
        if g.name not in garment.vertex_groups:
            garment.vertex_groups.new(name=g.name)
    groups = {g.name: g for g in garment.vertex_groups}
    shoulder = {s: joints[f'upperarm01.{s}'] for s in ('L', 'R')}
    hip = {s: joints[f'upperleg01.{s}'] for s in ('L', 'R')}
    for v in garment.data.vertices:
        p = garment.matrix_world @ v.co
        key = min(segs, key=lambda sg: segment_distance(p, sg[1], sg[2])-sg[3])[0]
        if allowed and key not in allowed and allowed:
            key = min((sg for sg in segs if sg[0] in allowed), key=lambda sg: segment_distance(p, sg[1], sg[2])-sg[3])[0]
        if key not in trees and key.split('.')[0] in FALLBACK_BONES:
            # The dressed base deletes body faces hidden inside the boots, so
            # no body foot vertices remain to copy weights from: the boot's
            # foot region follows the foot bone rigidly (sole stays planar).
            bone = FALLBACK_BONES[key.split('.')[0]].format(s=key[-1])
            groups[bone].add([v.index], 1.0, 'REPLACE')
            continue
        candidates = [key] if key in trees else ['torso']
        side = key[-1] if key[-2:] in ('.L', '.R') else None
        if key.startswith('upperarm') and (p-shoulder[side]).length < 0.07:
            candidates.append('torso')
        if key.startswith('thigh') and (p-hip[side]).length < 0.10:
            candidates.append('torso')
        hits = []
        for part in candidates:
            if part in trees:
                hits += trees[part].find_n(p, 4)
        hits.sort(key=lambda h: h[2])
        hits = hits[:4]
        acc, total = {}, 0.0
        for co, idx, dist in hits:
            w = 1.0/max(dist, 1e-4)
            total += w
            for name, value in rows[idx].items():
                if name in face_bones:
                    # Hand the face's share to the neck (its parent chain).
                    name = 'neck03' if 'neck03' in groups else 'neck01'
                acc[name] = acc.get(name, 0.0)+w*value
        if total == 0:
            continue
        norm = sum(acc.values())
        for name, value in acc.items():
            if value/norm > 0.01:
                groups[name].add([v.index], value/norm, 'REPLACE')
    attach_armature(garment, arm)


def attach_armature(obj, arm):
    mod = obj.modifiers.get('Armature') or obj.modifiers.new('Armature', 'ARMATURE')
    mod.object = arm
    obj.parent = arm
    obj.matrix_parent_inverse = arm.matrix_world.inverted()


def hide_body_by_source(body, a_obj, a_labels, keep_parts, parts, max_distance=0.08):
    """Delete body faces wherever Asset A's nearest surface is clothing.

    The body is fitted to Asset A's proportions, so A's own segmentation says
    where skin is visible (midriff, hands, neck). Garment-covered body faces
    are removed outright: nothing can poke through loose sleeves or jeans,
    and the triangle budget drops. A one-ring margin is kept at openings."""
    co = np.empty(len(a_obj.data.vertices)*3, np.float32)
    a_obj.data.vertices.foreach_get('co', co)
    M = np.array(a_obj.matrix_world)
    co = co.reshape(-1, 3)@M[:3, :3].T+M[:3, 3]
    step = 3
    tree = KDTree(len(co[::step]))
    for i, p in enumerate(co[::step]):
        tree.insert(p, i*step)
    tree.balance()
    clothing = {REGIONS.index(r) for r in ('sweater', 'jeans', 'boots')}
    covered = np.zeros(len(body.data.vertices), bool)
    rest, _ = body_rest_positions(body)
    for i, part in enumerate(parts):
        if part == 'head':
            continue
        _, idx, dist = tree.find(Vector(rest[i]))
        # Hands are kept only beyond the cuff (their nearest source surface is skin).
        covered[i] = dist < max_distance and int(a_labels[idx]) in clothing
    bm = bmesh.new()
    bm.from_mesh(body.data)
    bm.verts.ensure_lookup_table()
    keep = covered.copy()
    for v in bm.verts:
        if covered[v.index] and any(not covered[e.other_vert(v).index] for e in v.link_edges):
            keep[v.index] = False
    doomed = [f for f in bm.faces if all(keep[v.index] for v in f.verts)]
    bmesh.ops.delete(bm, geom=doomed, context='FACES')
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context='VERTS')
    bm.to_mesh(body.data)
    bm.free()
    body.data.update()
    return len(doomed)


def hide_body_under(body, garments, keep_parts, parts):
    """Delete body faces whose every vertex sits under a garment (ray along the normal)."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    verts, polys = [], []
    for g in garments:
        mesh = g.evaluated_get(depsgraph).to_mesh()
        base = len(verts)
        verts += [g.matrix_world @ v.co for v in mesh.vertices]
        polys += [[base+i for i in p.vertices] for p in mesh.polygons]
        g.evaluated_get(depsgraph).to_mesh_clear()
    bvh = BVHTree.FromPolygons(verts, polys)
    hidden = []
    rest, normals = body_rest_positions(body)
    for i, part in enumerate(parts):
        if part in keep_parts:
            hidden.append(False)
            continue
        p, n = Vector(rest[i]), Vector(normals[i])
        hit = bvh.ray_cast(p+n*0.001, n, 0.12)[0]
        hidden.append(hit is not None)
    hidden = np.array(hidden)
    # Keep a one-ring margin at garment openings so no gap opens when moving.
    bm = bmesh.new()
    bm.from_mesh(body.data)
    bm.verts.ensure_lookup_table()
    keep = hidden.copy()
    for v in bm.verts:
        if hidden[v.index] and any(not hidden[e.other_vert(v).index] for e in v.link_edges):
            keep[v.index] = False
    doomed = [f for f in bm.faces if all(keep[v.index] for v in f.verts)]
    bmesh.ops.delete(bm, geom=doomed, context='FACES')
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context='VERTS')
    bm.to_mesh(body.data)
    bm.free()
    body.data.update()
    return len(doomed)


def prune_hair_on_skin(hair, body, eye_z, below=0.04, distance=0.004):
    """Remove hair-shell faces lying on the neck skin below the ears.

    Asset B is one fused shell, so wherever its neck is painted dark (shadow,
    wisps) the hair cut keeps patches of B's neck surface. Below ear level a
    face that lies within 4 mm of the production neck and parallel to it is
    such a patch; the ponytail hangs away from the neck and is kept."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    bm_body = bmesh.new()
    bm_body.from_object(body, depsgraph)
    bm_body.transform(body.matrix_world)
    bvh = BVHTree.FromBMesh(bm_body)
    bm = bmesh.new()
    bm.from_mesh(hair.data)
    bm.normal_update()
    doomed = []
    for f in bm.faces:
        c = hair.matrix_world @ f.calc_center_median()
        if c.z > eye_z-below:
            continue
        loc, nor, _, dist = bvh.find_nearest(c, distance)
        if loc is not None and f.normal.dot(nor) > 0.5:
            doomed.append(f)
    bmesh.ops.delete(bm, geom=doomed, context='FACES')
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context='VERTS')
    bm.to_mesh(hair.data)
    bm.free()
    bm_body.free()
    hair.data.update()
    return len(doomed)


def trim_boundary_spikes(obj, passes=2):
    """Remove faces with two or more open edges along the garment's cut
    boundary (single-triangle spikes left by the per-vertex region vote)."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    removed = 0
    for _ in range(passes):
        doomed = [f for f in bm.faces if sum(1 for e in f.edges if e.is_boundary) >= 2]
        if not doomed:
            break
        removed += len(doomed)
        bmesh.ops.delete(bm, geom=doomed, context='FACES')
        loose = [v for v in bm.verts if not v.link_faces]
        bmesh.ops.delete(bm, geom=loose, context='VERTS')
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return {'boundary_spike_faces_removed': removed}


def mirror_complete_knit(obj, reach=0.012, zmin=1.25):
    """Symmetric completion of Asset A's knit where its long hair hid it.

    A wears its hair down the back, so its sweater has a hole down the upper
    back. Faces of the intact right half are mirrored across the body's
    midplane (x = 0) wherever the mirror image lands in a hole (no knit within
    12 mm along the mirrored normal). The copies keep A's UVs, so the knit and
    stripes continue; the hole's central strip mirrors onto itself and stays
    under the ponytail."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.normal_update()
    bvh = BVHTree.FromBMesh(bm)
    M = obj.matrix_world
    if not np.allclose(np.array(M), np.eye(4)):
        raise RuntimeError('mirror completion expects baked world coordinates')
    uv_layer = bm.loops.layers.uv.active
    ys = [v.co.y for v in bm.verts]
    back = float(np.median(ys))
    new_faces = []
    for f in list(bm.faces):
        c = f.calc_center_median()
        if c.x > -0.004 or c.y < back or c.z < zmin:
            continue
        cm = Vector((-c.x, c.y, c.z))
        nm = Vector((-f.normal.x, f.normal.y, f.normal.z))
        if bvh.ray_cast(cm, nm, reach)[0] is not None or bvh.ray_cast(cm, -nm, reach)[0] is not None:
            continue
        new_faces.append(([Vector((-l.vert.co.x, l.vert.co.y, l.vert.co.z)) for l in f.loops],
                          [l[uv_layer].uv.copy() for l in f.loops], f.material_index))
    for cos, uvs, mi in new_faces:
        verts = [bm.verts.new(co) for co in reversed(cos)]
        face = bm.faces.new(verts)
        face.material_index = mi
        face.smooth = True
        for loop, uv in zip(face.loops, reversed(uvs)):
            loop[uv_layer].uv = uv
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return {'mirrored_faces': len(new_faces), 'midplane_x': 0.0, 'back_y_from': back}


def sweater_hole_fill(proc, sweater, arm, reach=0.03):
    """Fill Asset A's sweater where A's long hair covered it (a hole down the
    upper back) with the production knit fitted to the same body: only the
    production faces with no Asset A knit within 3 cm along their normal are
    kept, so the fill shows exactly through the holes. It carries the
    turnaround-calibrated striped knit material and the build's weights."""
    if proc is None:
        return None
    depsgraph = bpy.context.evaluated_depsgraph_get()
    bm_sw = bmesh.new()
    bm_sw.from_object(sweater, depsgraph)
    bm_sw.transform(sweater.matrix_world)
    bvh = BVHTree.FromBMesh(bm_sw)
    for mod in proc.modifiers:
        if mod.type == 'ARMATURE':
            mod.show_viewport = False
    bm = bmesh.new()
    bm.from_mesh(proc.data)
    M = proc.matrix_world
    R = M.to_3x3()
    top = max((sweater.matrix_world @ v.co).z for v in sweater.data.vertices)
    back = float(np.median([(sweater.matrix_world @ v.co).y for v in sweater.data.vertices]))
    doomed = []
    for f in bm.faces:
        c = M @ f.calc_center_median()
        n = (R @ f.normal).normalized()
        covered = (bvh.ray_cast(c, n, reach)[0] is not None or bvh.ray_cast(c, -n, reach)[0] is not None)
        if covered or c.z < 1.15 or c.z > top-0.004 or c.y < back:
            doomed.append(f)
    bmesh.ops.delete(bm, geom=doomed, context='FACES')
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context='VERTS')
    bm.to_mesh(proc.data)
    bm.free()
    bm_sw.free()
    proc.data.update()
    for mod in proc.modifiers:
        if mod.type == 'ARMATURE':
            mod.show_viewport = True
    kept = len(proc.data.polygons)
    if kept == 0:
        bpy.data.objects.remove(proc, do_unlink=True)
        return None
    dropped = drop_small_islands(proc, 30)
    # The production knit was skinned before the face rig existed in its
    # neighbourhood: hand any head/face bone share to the neck, as for the
    # source garments (no jaw-driven collar, no facial morphs on knit).
    face = {b.name for b in arm.data.bones['head'].children_recursive} | {'head'}
    neck = proc.vertex_groups.get('neck03') or proc.vertex_groups.new(name='neck03')
    face_groups = [g for g in proc.vertex_groups if g.name in face]
    for v in proc.data.vertices:
        moved = sum(g.weight for g in v.groups if proc.vertex_groups[g.group].name in face)
        if moved > 0:
            current = next((g.weight for g in v.groups if g.group == neck.index), 0.0)
            neck.add([v.index], current+moved, 'REPLACE')
    for g in face_groups:
        proc.vertex_groups.remove(g)
    proc.name = 'Inez_Sweater_HoleFill'
    proc['source'] = 'production knit (turnaround-calibrated) shown only where Asset A had no knit (hidden under its hair)'
    proc['source_report'] = json.dumps({'faces': len(proc.data.polygons), 'small_island_faces_dropped': dropped})
    return proc


def prune_hair_on_ears(hair, body, eyes, distance=0.0015):
    """Remove hair-shell faces coincident with the production ears (within
    1.5 mm and parallel: Asset B's own ear surface cut with its hair). Curls
    lying over the ears stay; both originals show the ears mostly covered."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    bm_body = bmesh.new()
    bm_body.from_object(body, depsgraph)
    bm_body.transform(body.matrix_world)
    bvh = BVHTree.FromBMesh(bm_body)
    eye_y = sum(e.y for e in eyes)/2
    eye_z = sum(e.z for e in eyes)/2
    bm = bmesh.new()
    bm.from_mesh(hair.data)
    bm.normal_update()
    doomed = []
    for f in bm.faces:
        c = hair.matrix_world @ f.calc_center_median()
        if abs(c.x) < 0.06 or c.y-eye_y < 0.045 or not (eye_z-0.065 < c.z < eye_z+0.04):
            continue
        loc, nor, _, _ = bvh.find_nearest(c, distance)
        if loc is not None and abs(f.normal.dot(nor)) > 0.7:
            doomed.append(f)
    bmesh.ops.delete(bm, geom=doomed, context='FACES')
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context='VERTS')
    bm.to_mesh(hair.data)
    bm.free()
    bm_body.free()
    hair.data.update()
    return len(doomed)


def drop_hair_coloured_knit(obj, image, zmin=1.40):
    """Remove knit faces whose Asset A colour is brown hair (A wears its hair
    down over the collar; a few strands fell into the knit cut)."""
    px = image_pixels(image)[:, :, :3]
    h, w = px.shape[:2]
    uv = obj.data.uv_layers.active.data
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    uv_layer = bm.loops.layers.uv.active
    doomed = []
    for f in bm.faces:
        c = obj.matrix_world @ f.calc_center_median()
        if c.z < zmin:
            continue
        u = sum(l[uv_layer].uv.x for l in f.loops)/len(f.loops)
        v = sum(l[uv_layer].uv.y for l in f.loops)/len(f.loops)
        r, g, b = px[min(h-1, max(0, int(v*h))), min(w-1, max(0, int(u*w)))]
        if r-b > 0.035 and r >= g:
            doomed.append(f)
    bmesh.ops.delete(bm, geom=doomed, context='FACES')
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context='VERTS')
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return len(doomed)


def prune_hair_near_eyes(hair, eyes, radius=0.022):
    """Remove hair-shell faces around the eyes. Asset B's painted lids, lashes
    and brows are dark enough to fall into the hair cut and would sit over the
    production eyes; the brows are carried by the baked head colour."""
    bm = bmesh.new()
    bm.from_mesh(hair.data)
    front = max(e.y for e in eyes)+0.012
    doomed = []
    for f in bm.faces:
        c = hair.matrix_world @ f.calc_center_median()
        if c.y < front and min((c-e).length for e in eyes) < radius:
            doomed.append(f)
    bmesh.ops.delete(bm, geom=doomed, context='FACES')
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context='VERTS')
    bm.to_mesh(hair.data)
    bm.free()
    hair.data.update()
    return len(doomed)


def smoothstep(v, a, b):
    t = np.clip((v-a)/(b-a), 0, 1)
    return t*t*(3-2*t)


def box_blur(field, radius):
    """Separable box blur (integer radius in texels) via cumulative sums."""
    out = field.astype(np.float32)
    for axis in (0, 1):
        pad = np.pad(out, [(radius+1, radius) if a == axis else (0, 0) for a in (0, 1)], mode='edge')
        c = np.cumsum(pad, axis=axis, dtype=np.float64)
        hi = np.take(c, np.arange(2*radius+1, c.shape[axis]), axis=axis)
        lo = np.take(c, np.arange(0, c.shape[axis]-2*radius-1), axis=axis)
        out = ((hi-lo)/(2*radius+1)).astype(np.float32)
    return out


def texels_per_mm(positions, mask):
    """Median texel spacing on the surface, from neighbouring texel positions."""
    both = mask[:, 1:] & mask[:, :-1]
    step = np.linalg.norm(positions[:, 1:]-positions[:, :-1], axis=-1)[both]
    step = step[(step > 0) & (step < 0.002)]
    return 0.001/float(np.median(step)) if len(step) else 6.0


def eye_area_tone(rgb, positions, mask, eyes):
    """Brows and under-eye tone per the originals.

    Both originals show dense dark-brown brows and soft darkness under the
    lower lids (fatigue cues that must not be beautified away). Asset B's
    brows are thin strokes and its under-eye skin is clean.

    Brows: only texels clearly darker than the skin around them (brow hair,
    not skin) inside a soft window over each brow are taken; the stroke mask
    is widened by about 1.3 mm and tinted dark brown, keeping the strokes'
    own shape and placement from Asset B. The window has soft edges, so no
    skin outside the brow changes and no rectangle shows. Run before the
    freckles, which would otherwise read as brow hair."""
    x, y, z = positions[..., 0], positions[..., 1], positions[..., 2]
    lum = rgb@np.array([0.2126, 0.7152, 0.0722], np.float32)
    out = rgb.copy()
    per_mm = texels_per_mm(positions, mask)
    strokes = np.zeros(mask.shape, np.float32)
    window = np.zeros(mask.shape, np.float32)
    for e in eyes:
        side = 1.0 if e.x > 0 else -1.0
        lat, dz = (x-e.x)*side, z-e.z
        front = mask & (y < e.y+0.006)
        win = (smoothstep(lat, -0.027, -0.020)*(1-smoothstep(lat, 0.031, 0.039))
               * smoothstep(dz, 0.003, 0.008)*(1-smoothstep(dz, 0.027, 0.034)))*front
        core = win > 0.5
        if core.sum() < 100:
            continue
        ref = np.percentile(lum[core], 70)
        hair = np.clip(((ref-lum)/max(ref, 1e-4)-0.10)/0.20, 0, 1)*win
        strokes = np.maximum(strokes, hair)
        window = np.maximum(window, win)
    radius = max(1, int(round(1.3*per_mm)))
    dense = np.clip(box_blur(strokes, radius)*2.6, 0, 1)
    brow = np.maximum(strokes, dense*0.9)*window
    brow_linear = np.array([0.022, 0.014, 0.009], np.float32)
    alpha = (0.82*brow)[..., None]
    out = out*(1-alpha)+brow_linear*alpha
    for e in eyes:
        dx, dz = x-e.x, z-e.z
        front = mask & (y < e.y+0.006)
        crescent = np.exp(-((dx/0.016)**2+((dz+0.0135)/0.0055)**2))*front
        out *= (1-crescent[..., None]*np.array([0.15, 0.18, 0.12], np.float32))
    return out, {'brow_texels': int((brow > 0.3).sum()), 'brow_widening_mm': round(radius/per_mm, 2),
                 'texels_per_mm': round(per_mm, 2), 'brow_colour_linear': brow_linear.tolist(),
                 'brow_opacity_max': 0.82, 'under_eye_darkening_max': 0.18,
                 'evidence': 'dense dark brows and under-eye darkness visible in both originals'}


def lid_margin_tone(rgb, positions, mask, eyes, radius):
    """Asset B's eyeballs bake onto the production lid margins (the thin lid
    surfaces that touch the eyeball) as white rims. Texels within 1.2 mm of
    the eyeball surface take the lid-margin tone, the surrounding skin darker
    and redder, fading out by 2.0 mm."""
    out = rgb.copy()
    replaced = 0
    for e in eyes:
        c = np.array(e, np.float32)
        gap = np.linalg.norm(positions-c, axis=-1)-radius
        ring = mask & (gap > 0.004) & (gap < 0.010) & (positions[..., 1] < c[1])
        if ring.sum() < 50:
            continue
        target = np.median(rgb[ring], axis=0)*np.array([0.74, 0.55, 0.52], np.float32)
        w = (1-smoothstep(gap, 0.0012, 0.0020))*mask
        out = out*(1-w[..., None])+target*w[..., None]
        replaced += int((w > 0.5).sum())
    return out, {'texels_replaced': replaced, 'eyeball_radius_m': round(float(radius), 4),
                 'note': 'Asset B eyeball colour removed from the production lid margins'}


def head_seam_points(body):
    """World rest positions of body vertices on the head-material boundary."""
    head_index = next(i for i, m in enumerate(body.data.materials) if m and m.name.startswith('Inez_Head_Skin'))
    rest, _ = body_rest_positions(body)
    head_v, other_v = set(), set()
    for poly in body.data.polygons:
        (head_v if poly.material_index == head_index else other_v).update(poly.vertices)
    seam = sorted(head_v & other_v)
    return rest[seam] if seam else np.zeros((0, 3), np.float32)


def seam_distance(positions, mask, seam, chunk=200000):
    """Distance (m) from each covered texel position to the nearest seam vertex."""
    out = np.full(mask.shape, np.inf, np.float32)
    ids = np.flatnonzero(mask.ravel())
    if len(seam) == 0:
        return out
    pts = positions.reshape(-1, 3)[ids].astype(np.float32)
    seam = seam.astype(np.float32)
    d = np.empty(len(ids), np.float32)
    for a in range(0, len(ids), chunk):
        q = pts[a:a+chunk]
        d2 = (q*q).sum(1)[:, None]-2*q@seam.T+(seam*seam).sum(1)[None, :]
        d[a:a+chunk] = np.sqrt(np.maximum(d2.min(1), 0))
    out.ravel()[ids] = d
    return out


# ---------------------------------------------------------------- mouth

def build_mouth_interior(fitted_path, arm, texdir):
    """Teeth and tongue from the CC0 MakeHuman helpers (base.obj groups
    helper-upper-teeth / helper-lower-teeth / helper-tongue) at their fitted
    positions, so they sit behind the corrected lips. Upper teeth follow the
    head; lower teeth and tongue the jaw (animation_build then gives them the
    jaw part of every viseme/expression). Individual teeth are suggested by
    vertex-colour gaps along the arch; the inner mouth darkens toward the
    throat. Unseen in the originals: generic, labelled as such."""
    if not fitted_path:
        return None
    data = np.load(fitted_path)
    P, scale, ground = data['fitted'], float(data['scale']), float(data['ground_eff'])
    world = np.stack([P[:, 0]*scale, -P[:, 2]*scale, (P[:, 1]-ground)*scale], 1)
    groups, cur = {}, None
    base = Path(__file__).resolve().parents[2]/'assets/characters/inez/model/base-source/base.obj'
    with open(base) as fh:
        for line in fh:
            if line.startswith('g '):
                cur = line.split()[1]
            elif line.startswith('f ') and cur in ('helper-upper-teeth', 'helper-lower-teeth', 'helper-tongue'):
                groups.setdefault(cur, []).append([int(t.split('/')[0])-1 for t in line.split()[1:]])
    # Offsets (m): the helper incisal edges sat level with the upper lip's
    # lower edge, so no tooth showed in an open mouth; ~3 mm of upper
    # incisor below a relaxed upper lip is typical for a young adult.
    specs = {'helper-upper-teeth': ('Inez_TeethUpper', 'head', 2, (0, 0, -0.0055)),
             'helper-lower-teeth': ('Inez_TeethLower', 'jaw', 2, (0, -0.002, 0.0015)),
             'helper-tongue': ('Inez_Tongue', 'jaw', 1, (0, 0, -0.001))}
    report = {}
    for group, (name, bone, levels, offset) in specs.items():
        faces = groups.get(group)
        if not faces:
            continue
        used = sorted({v for f in faces for v in f})
        remap = {v: i for i, v in enumerate(used)}
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata([tuple(world[v]+np.array(offset)) for v in used], [], [[remap[v] for v in f] for f in faces])
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(mesh)
        bm.free()
        mod = obj.modifiers.new('Smooth', 'SUBSURF')
        mod.levels = mod.render_levels = levels
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=mod.name)
        for poly in mesh.polygons:
            poly.use_smooth = True
        co = np.array([v.co for v in mesh.vertices])
        colour = np.ones((len(co), 4), np.float32)
        if 'teeth' in group:
            centre = np.array([co[:, 0].mean(), co[:, 1].max()+0.012])
            ang = np.arctan2(co[:, 0]-centre[0], -(co[:, 1]-centre[1]))
            radius = np.median(np.hypot(co[:, 0]-centre[0], co[:, 1]-centre[1]))
            arc = np.abs(ang)*radius*1000
            gaps = np.zeros(len(co))
            for edge in (0.0, 8.5, 15.0, 22.5, 29.5, 36.5):
                gaps = np.maximum(gaps, np.exp(-((arc-edge)/0.45)**2))
            depth = np.clip((co[:, 1]-co[:, 1].min())/max(np.ptp(co[:, 1]), 1e-6), 0, 1)
            tint = np.array([0.80, 0.76, 0.68])*(1-0.45*gaps[:, None])*(1-0.55*depth[:, None])
        else:
            depth = np.clip((co[:, 1]-co[:, 1].min())/max(np.ptp(co[:, 1]), 1e-6), 0, 1)
            tint = np.array([0.50, 0.21, 0.21])*(1-0.6*depth[:, None])
        colour[:, :3] = tint
        attr = mesh.color_attributes.new('Col', 'FLOAT_COLOR', 'POINT')
        attr.data.foreach_set('color', colour.ravel())
        mat = bpy.data.materials.new(name+'_PBR')
        mat.use_nodes = True
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        bsdf = nodes['Principled BSDF']
        node = nodes.new('ShaderNodeVertexColor')
        node.layer_name = 'Col'
        links.new(node.outputs['Color'], bsdf.inputs['Base Color'])
        bsdf.inputs['Roughness'].default_value = 0.28 if 'teeth' in group else 0.5
        mesh.materials.append(mat)
        vg = obj.vertex_groups.new(name=bone)
        vg.add(list(range(len(mesh.vertices))), 1.0, 'REPLACE')
        attach_armature(obj, arm)
        obj['source'] = f'MakeHuman CC0 {group} at the fitted positions; generic, not visible in the originals'
        report[name] = {'faces': len(mesh.polygons), 'bone': bone, 'offset_m': list(offset)}
    return report


# ---------------------------------------------------------------- eyes

def iris_albedo(resolution=1024, seed=11):
    """Hazel iris measured on the originals (MediaPipe iris rings, both
    images): olive-khaki outer field (linear R/G ~1.3, G/B ~2) around a
    warmer golden collarette, darker limbal ring, radial stroma fibres.
    Values are the measured iris/cheek ratios applied to the calibrated skin
    albedo, raised ~1.4x for the lid and brow shadow over the originals' eyes
    and ~1.2x for the cornea layer."""
    q = (np.arange(resolution, dtype=np.float32)+0.5)/resolution*2-1
    x, y = np.meshgrid(q, q)
    r = np.sqrt(x*x+y*y)
    a = np.arctan2(y, x)
    rng = np.random.default_rng(seed)
    fib = np.zeros_like(r)
    for k in range(7):
        f = rng.uniform(60, 220)
        fib += np.sin(a*f+rng.uniform(0, 6.3)+r*rng.uniform(4, 22))/(1+0.5*k)
    fib /= np.abs(fib).max()
    crypt = np.zeros_like(r)
    for _ in range(45):
        rr, aa = rng.uniform(0.42, 0.8), rng.uniform(-np.pi, np.pi)
        d2 = (x-rr*np.cos(aa))**2+(y-rr*np.sin(aa))**2
        crypt += np.exp(-d2/(2*rng.uniform(0.012, 0.03)**2))*rng.uniform(0.3, 0.7)
    to_lin = lambda c: np.where(np.asarray(c) <= 0.04045, np.asarray(c)/12.92, ((np.asarray(c)+0.055)/1.055)**2.4)
    outer, inner, limbal = to_lin((0.50, 0.45, 0.31)), to_lin((0.53, 0.42, 0.25)), to_lin((0.21, 0.20, 0.14))
    t = np.clip((r-0.36)/0.20, 0, 1)[..., None]
    col = inner*(1-t)+outer*t
    col = col*(1+0.22*fib[..., None])*(1-0.35*np.clip(crypt, 0, 1)[..., None])
    collarette = np.exp(-((r-0.47)/0.03)**2)[..., None]
    col = col*(1+0.18*collarette)
    lim = np.clip((r-0.80)/0.16, 0, 1)[..., None]
    col = col*(1-lim)+limbal*lim
    pupil = np.clip((0.315-r)/0.025, 0, 1)[..., None]
    col = col*(1-pupil)+0.004*pupil
    col = np.clip(col, 0, 1)
    return np.where(col <= 0.0031308, col*12.92, 1.055*col**(1/2.4)-0.055).astype(np.float32)


def refine_eyes(scene, eyes, texdir):
    """Iris colour from the originals, no tearline strips and finer lower
    lashes (the 30 thick strands read as a black comb at portrait range)."""
    report = {}
    img = save_image('inez_iris_hazel_albedo_v05', iris_albedo(), texdir)
    for obj in scene.objects:
        if obj.type != 'MESH':
            continue
        for mat in obj.data.materials:
            if mat and mat.name.startswith('Inez_Muted_GreenHazel_Iris'):
                bsdf = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
                link = bsdf.inputs['Base Color'].links
                if link:
                    link[0].from_node.image = img
                mat['color_evidence'] = ('v05: MediaPipe iris-ring medians on both originals as ratios to the '
                                         'cheek, applied to the calibrated skin albedo; shadow/cornea compensated')
    report['iris'] = {'albedo': img.name, 'outer_srgb': [0.50, 0.45, 0.31], 'inner_srgb': [0.53, 0.42, 0.25]}
    for side in ('L', 'R'):
        # The tearline strips were fitted to the dressed base's lid margins;
        # after the lid-opening layer they float off the lids and render as
        # white polylines (eye close-ups, pass 3). The cornea's specular
        # carries the wet look, so the strips are removed.
        tear = scene.objects.get(f'Inez_Tearline_{side}')
        if tear:
            bpy.data.objects.remove(tear, do_unlink=True)
            report[f'tearline_{side}'] = 'removed (misaligned after the lid-opening layer)'
        lashes = scene.objects.get(f'Inez_LashesLower_{side}')
        if lashes is None:
            continue
        eye = eyes[0] if side == 'L' else eyes[1]
        bm = bmesh.new()
        bm.from_mesh(lashes.data)
        bm.verts.ensure_lookup_table()
        islands = face_islands(bm)
        for island in islands:
            verts = list({v for f in island for v in f.verts})
            world = [lashes.matrix_world @ v.co for v in verts]
            root = min(world, key=lambda w: (w-eye).length)
            inv = lashes.matrix_world.inverted()
            for v, w in zip(verts, world):
                v.co = inv @ (root+(w-root)*0.6)
        bm.to_mesh(lashes.data)
        bm.free()
        lashes.data.update()
        for mat in lashes.data.materials:
            bsdf = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
            if mat.name == 'Inez_NaturalBrownLashes':
                low = mat.copy()
                low.name = 'Inez_NaturalBrownLashes_Lower'
                b2 = next(n for n in low.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
                b2.inputs['Base Color'].default_value = (0.035, 0.022, 0.015, 1)
                lashes.data.materials[0] = low
                break
        report[f'lower_lashes_{side}'] = {'strands': len(islands), 'scaled_about_root': 0.6}
    return report


# ---------------------------------------------------------------- head bake

def ear_weights(points, edges, faces, normals, eye_mid, rings=3):
    """Per-vertex ear membership by thickness: a ray into the surface from an
    ear vertex exits the flap within ~12 mm, while from the skull it crosses
    the head. Grown by three rings to take in the concha and the ear's root."""
    bvh = BVHTree.FromPolygons([tuple(p) for p in points], faces)
    rel = points-eye_mid
    box = (np.abs(points[:, 0]) > 0.055) & (rel[:, 1] > 0.035) & (rel[:, 2] > -0.075) & (rel[:, 2] < 0.05)
    w = np.zeros(len(points))
    for i in np.flatnonzero(box):
        n = Vector(normals[i])
        hit = bvh.ray_cast(Vector(points[i])-n*0.0005, -n, 0.012)
        if hit[0] is not None:
            w[i] = 1.0
    for _ in range(rings):
        grow = w.copy()
        np.maximum.at(grow, edges[:, 0], w[edges[:, 1]])
        np.maximum.at(grow, edges[:, 1], w[edges[:, 0]])
        w = grow*box
    return w


def head_raster(low, W, H, eye_mid):
    """World position and ear membership per head-UV texel."""
    from model_materials_v04 import raster_attributes
    mesh = low.data
    points = np.array([tuple(low.matrix_world @ v.co) for v in mesh.vertices])
    normals = np.array([tuple((low.matrix_world.to_3x3() @ v.normal).normalized()) for v in mesh.vertices])
    edges = np.array([tuple(e.vertices) for e in mesh.edges])
    ears = ear_weights(points, edges, [tuple(p.vertices) for p in mesh.polygons], normals, np.asarray(eye_mid))
    uv = mesh.uv_layers.active.data
    texcoords, faces = [], []
    for poly in mesh.polygons:
        face = []
        for li in poly.loop_indices:
            texcoords.append(tuple(uv[li].uv))
            face.append((mesh.loops[li].vertex_index, len(texcoords)-1))
        faces.append(face)
    positions, attrs, mask = raster_attributes(points, ears[:, None], texcoords, faces, (W, H))
    return positions, mask, attrs[:, :, 0], int((ears > 0.5).sum())


def freckle_field(positions, mask, eye_mid, seed=1299):
    """Freckles per original A: dense over the nose bridge and upper cheeks,
    sparse and smaller on the forehead. Exact marks are not visible in the
    references, so placement is a disclosed procedural distribution."""
    rng = np.random.default_rng(seed)
    x, y, z = positions[..., 0], positions[..., 1], positions[..., 2]
    front = mask & (y < eye_mid[1]+0.015) & (np.abs(x-eye_mid[0]) < 0.078) & (z > eye_mid[2]-0.11) & (z < eye_mid[2]+0.10)
    ids = np.flatnonzero(front.ravel())
    fx, fz = x.ravel()[ids], z.ravel()[ids]
    order = np.argsort(fx)
    sx = fx[order]
    spots = np.zeros(len(ids), np.float32)
    centers = []
    # The originals show clearly visible freckles across the nose bridge and
    # upper cheeks at portrait distance, lighter on the forehead and chin.
    for _ in range(900):
        cx = rng.normal(0, 0.031)
        cz = eye_mid[2]-0.016+rng.normal(0, 0.013)
        if abs(cx) < 0.072:
            centers.append((eye_mid[0]+cx, cz, rng.uniform(.00045, .0012), rng.uniform(.22, .55)))
    for _ in range(160):
        centers.append((eye_mid[0]+rng.uniform(-.05, .05), eye_mid[2]+rng.uniform(.03, .085), rng.uniform(.00035, .0008), rng.uniform(.12, .28)))
    for _ in range(70):
        centers.append((eye_mid[0]+rng.uniform(-.035, .035), eye_mid[2]-rng.uniform(.075, .105), rng.uniform(.00035, .0008), rng.uniform(.10, .22)))
    for cx, cz, radius, strength in centers:
        a, b = np.searchsorted(sx, (cx-3*radius, cx+3*radius))
        sel = order[a:b]
        d2 = ((fx[sel]-cx)**2+(fz[sel]-cz)**2)/radius**2
        near = d2 < 9
        spots[sel[near]] += np.exp(-d2[near]*1.4)*strength
    out = np.zeros(mask.shape, np.float32)
    out.ravel()[ids] = np.minimum(spots, 0.65)
    return out, len(centers)

def bake_head_from_b(body, b_obj, b_labels, size, texdir, eye_mid):
    """Asset B base colour onto the head UV: skin-only pass (face), full pass (scalp)."""
    W, H = size
    scene = bpy.context.scene
    depsgraph = bpy.context.evaluated_depsgraph_get()
    mesh = bpy.data.meshes.new_from_object(body.evaluated_get(depsgraph), preserve_all_data_layers=True, depsgraph=depsgraph)
    head_index = next(i for i, m in enumerate(body.data.materials) if m and m.name.startswith('Inez_Head_Skin'))
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index != head_index], context='FACES')
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.clear()
    mesh.polygons.foreach_set('material_index', [0]*len(mesh.polygons))
    low = bpy.data.objects.new('HeadBake_Low', mesh)
    low.matrix_world = body.matrix_world
    scene.collection.objects.link(low)
    # Emission source material on copies of B (skin-only and full).
    src_mat = b_obj.data.materials[0]
    bsdf = next(n for n in src_mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    base_tex = bsdf.inputs['Base Color'].links[0].from_node

    def emission_copy(obj, name):
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        nodes.clear()
        out = nodes.new('ShaderNodeOutputMaterial')
        em = nodes.new('ShaderNodeEmission')
        tex = nodes.new('ShaderNodeTexImage')
        tex.image = base_tex.image
        links.new(tex.outputs['Color'], em.inputs['Color'])
        links.new(em.outputs['Emission'], out.inputs['Surface'])
        obj.data.materials.clear()
        obj.data.materials.append(mat)
    skin_only = extract_part(b_obj, b_labels, {REGIONS.index('skin'), REGIONS.index('eye')}, 'HeadBake_BSkin')
    # Under-hair pass: B's hair and skin only (its sweater collar must not be
    # painted onto the nape).
    full = extract_part(b_obj, b_labels, {REGIONS.index('skin'), REGIONS.index('eye'), REGIONS.index('hair')}, 'HeadBake_BFull')
    emission_copy(skin_only, 'HeadBake_BSkinEmit')
    emission_copy(full, 'HeadBake_BFullEmit')
    target = bpy.data.materials.new('HeadBake_Target')
    target.use_nodes = True
    node = target.node_tree.nodes.new('ShaderNodeTexImage')
    low.data.materials.append(target)
    target.node_tree.nodes.active = node
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 4
    bake = scene.render.bake
    bake.use_selected_to_active = True
    bake.use_cage = False
    bake.margin = 16
    bake.target = 'IMAGE_TEXTURES'
    results = {}
    for name, source, extrusion, distance in (('skin', skin_only, 0.006, 0.012), ('full', full, 0.03, 0.06)):
        for obj in scene.objects:
            obj.select_set(False)
            if obj.type == 'MESH':
                obj.hide_render = obj not in (low, source)
        img = bpy.data.images.new(f'headbake_{name}', W, H, alpha=True, float_buffer=True)
        img.generated_color = (0, 0, 0, 0)
        node.image = img
        bake.cage_extrusion = extrusion
        bake.max_ray_distance = distance
        source.select_set(True)
        low.select_set(True)
        bpy.context.view_layer.objects.active = low
        bpy.ops.object.bake(type='EMIT', save_mode='INTERNAL')
        results[name] = image_pixels(img)
        # Coverage pass: white emission.
        cov_mat = bpy.data.materials.new(f'cov_{name}')
        cov_mat.use_nodes = True
        cov_mat.node_tree.nodes.clear()
        o = cov_mat.node_tree.nodes.new('ShaderNodeOutputMaterial')
        e = cov_mat.node_tree.nodes.new('ShaderNodeEmission')
        cov_mat.node_tree.links.new(e.outputs['Emission'], o.inputs['Surface'])
        keep = list(source.data.materials)
        source.data.materials.clear()
        source.data.materials.append(cov_mat)
        cimg = bpy.data.images.new(f'headcov_{name}', W, H, alpha=False, float_buffer=True)
        node.image = cimg
        bake.margin = 0
        bpy.ops.object.bake(type='EMIT', save_mode='INTERNAL')
        bake.margin = 16
        results[name+'_cov'] = image_pixels(cimg)[:, :, 0]
        source.data.materials.clear()
        for m in keep:
            source.data.materials.append(m)
    results['raster'] = head_raster(low, W, H, eye_mid)
    for obj in (low, skin_only, full):
        bpy.data.objects.remove(obj, do_unlink=True)
    for obj in scene.objects:
        if obj.type == 'MESH':
            obj.hide_render = False
    return results


def main():
    args = arguments()
    scene = bpy.context.scene
    body = bpy.data.objects[BODY]
    arm = next(o for o in scene.objects if o.type == 'ARMATURE')
    texdir = Path(args.texture_dir)
    texdir.mkdir(parents=True, exist_ok=True)
    removed = []
    proc_sweater = scene.objects.get('Inez_Sweater')
    if proc_sweater is not None:
        proc_sweater.name = 'ProcSweater_FillSource'
    for obj in list(scene.objects):
        if obj.type == 'MESH' and obj.name.startswith(REMOVE_PREFIXES):
            removed.append(obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)
    for obj in scene.objects:
        if obj.type == 'MESH':
            for mod in obj.modifiers:
                if mod.type == 'SUBSURF':
                    mod.show_viewport = mod.show_render = False
    a_src, b_src = append_sources(args.source_blend)
    a_labels = np.load(args.regions_a)['labels']
    b_regions = np.load(args.regions_b)
    b_labels = b_regions['labels']
    b_fine = b_regions['fine_labels'] if 'fine_labels' in b_regions.files else b_labels
    SKIN, HAIR, EYE = REGIONS.index('skin'), REGIONS.index('hair'), REGIONS.index('eye')
    # Where the fine vote says skin (ears, nape, hairline gaps) Asset B's
    # surface is skin: it is cut from the hair shell and baked as skin.
    b_skin_fine = np.isin(b_fine, [SKIN, EYE]) & (b_labels == HAIR)
    b_bake_labels = np.where(b_skin_fine, SKIN, b_labels)
    # Asset B's painted sclera must not be baked onto the production lid
    # margins (it read as a white rim); the separate eyeballs carry the eye.
    b_head_bake_labels = np.where(b_bake_labels == EYE, REGIONS.index('other'), b_bake_labels)
    skin_gain = np.array([float(v) for v in args.skin_gain.split(',')], np.float32)
    eyes = [arm.matrix_world @ arm.data.bones['eye.'+sd].head_local for sd in ('L', 'R')]
    eye_mid = np.array((eyes[0]+eyes[1])/2)
    a_colours = np.load(args.regions_a)['colours'].astype(np.float32)
    targets = dict((k, int(v)) for k, v in (item.split('=') for item in args.targets.split(',')))
    report = {'removed_procedural_objects': removed, 'parts': {}}
    parts = body_parts(body)
    a_mat = a_src.data.materials[0]
    for region, name in (('sweater', 'Inez_Sweater'), ('jeans', 'Inez_Jeans'), ('boots', 'Inez_Boots')):
        obj = extract_part(a_src, a_labels, {REGIONS.index(region)}, name)
        before, after = decimate(obj, targets[region])
        if region == 'sweater':
            a_bsdf = next(n for n in a_mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
            hair_strands = drop_hair_coloured_knit(obj, a_bsdf.inputs['Base Color'].links[0].from_node.image)
            # One knit mass; detached bits (Asset A's dark irises read as knit) go.
            dropped = keep_attached_islands(obj, 40, 0.012)
            dropped['hair_coloured_faces_removed'] = hair_strands
            dropped['boundary_spikes'] = trim_boundary_spikes(obj)
            dropped['mirror_completion'] = mirror_complete_knit(obj)
        else:
            dropped = drop_small_islands(obj, 40)
        if args.no_colour_correction or region == 'boots':
            mat, note = a_mat, None
        else:
            mat, note = corrected_material(a_mat, f'Inez_{region.capitalize()}_FromAssetA', a_colours[a_labels == REGIONS.index(region)], region, texdir)
        obj.data.materials.clear()
        obj.data.materials.append(mat)
        allowed = None
        if region == 'jeans':
            allowed = {f'{p}.{s}' for p in ('thigh', 'shin') for s in ('L', 'R')} | {'torso'}
        if region == 'boots':
            allowed = {f'{p}.{s}' for p in ('shin', 'foot') for s in ('L', 'R')}
        skin_part_aware(obj, body, arm, parts, allowed)
        obj['source'] = f'Asset A (Inez.glb) {region} region, decimated {before} -> {after} triangles'
        report['parts'][name] = {'source': 'Asset A', 'region': region, 'triangles_source': before,
                                 'triangles': after, 'small_island_faces_dropped': dropped, 'colour_correction': note}
    hair = extract_part(b_src, b_bake_labels, {HAIR}, 'Inez_Hair')
    before, after = decimate(hair, targets['hair'])
    neck_patches = prune_hair_on_skin(hair, body, float(eye_mid[2]))
    eye_fragments = prune_hair_near_eyes(hair, eyes)
    ear_fragments = prune_hair_on_ears(hair, body, eyes)
    # Brows and irises are hair-coloured but belong to the face: keep only the
    # hair mass (scalp, ponytail, framing curls) and pieces touching it.
    islands = keep_attached_islands(hair, 150, 0.006)
    hair.data.materials.clear()
    hair_colours = b_regions['colours'].astype(np.float32)[b_bake_labels == HAIR]
    hair_target = tuple(float(v) for v in args.hair_target_linear.split(','))
    hair_mat, hair_note = hair_material(b_src.data.materials[0], hair_colours, texdir, hair_target)
    hair_note['neck_patch_faces_removed'] = neck_patches
    hair_note['eye_region_faces_removed'] = eye_fragments
    hair_note['ear_faces_removed'] = ear_fragments
    hair_note['islands'] = islands
    hair_note['fine_skin_vertices_cut_from_hair'] = int(b_skin_fine.sum())
    hair.data.materials.append(hair_mat)
    report['hair_colour'] = hair_note
    for g in body.vertex_groups:
        if g.name not in hair.vertex_groups:
            hair.vertex_groups.new(name=g.name)
    hair.vertex_groups['head'].add(list(range(len(hair.data.vertices))), 1.0, 'REPLACE')
    attach_armature(hair, arm)
    hair['source'] = f'Asset B (Inez Facial Model.glb) hair shell, decimated {before} -> {after} triangles'
    report['parts']['Inez_Hair'] = {'source': 'Asset B', 'region': 'hair', 'triangles_source': before, 'triangles': after}
    garments = [scene.objects['Inez_Sweater'], scene.objects['Inez_Jeans'], scene.objects['Inez_Boots']]
    fill = sweater_hole_fill(proc_sweater, scene.objects['Inez_Sweater'], arm)
    if fill is not None:
        garments.append(fill)
        report['sweater_hole_fill'] = json.loads(fill['source_report'])
    report['necklace'] = build_necklace(body, scene.objects['Inez_Sweater'], arm, parts, texdir)
    report['eyes'] = refine_eyes(scene, eyes, texdir)
    report['mouth_interior'] = build_mouth_interior(args.fitted, arm, texdir)
    report['body_faces_removed_under_source_clothing'] = hide_body_by_source(body, a_src, a_labels, {'head'}, parts)
    parts = body_parts(body)
    report['body_faces_hidden_under_garments'] = hide_body_under(body, garments, {'head', 'hand.L', 'hand.R'}, parts)
    # Head colour from Asset B.
    size = tuple(int(v) for v in args.head_size.split('x'))
    game = tuple(int(v) for v in args.game_head_size.split('x'))
    baked = bake_head_from_b(body, b_src, b_head_bake_labels, size, texdir, eye_mid)
    head_mat = next(m for m in body.data.materials if m and m.name.startswith('Inez_Head_Skin'))
    bsdf = next(n for n in head_mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    albedo_node = bsdf.inputs['Base Color'].links[0].from_node
    if tuple(albedo_node.image.size) != size:
        albedo_node.image.scale(*size)
    proc = image_pixels(albedo_node.image)
    # Byte images hold sRGB-encoded values; the bakes are linear radiance.
    proc[:, :, :3] = np.where(proc[:, :, :3] <= 0.04045, proc[:, :, :3]/12.92, ((proc[:, :, :3]+0.055)/1.055)**2.4)
    positions, raster_mask, ear_tex, ear_vertices = baked['raster']
    eyeball = scene.objects['Inez_Eyeball_L']
    eyeball_radius = float(np.median([(eyeball.matrix_world @ v.co-eyes[0]).length for v in eyeball.data.vertices]))
    skin_c = np.clip(baked['skin_cov'], 0, 1)[:, :, None]
    # Below the nape hairline (ear-lobe level) the hair/skin pass would paint
    # Asset B's shadowed neck; the neck takes the skin pass or the body skin.
    z = positions[:, :, 2]
    nape = np.clip((z-(eye_mid[2]-0.085))/0.02, 0, 1)[:, :, None]
    full_c = np.clip(baked['full_cov'], 0, 1)[:, :, None]*(1-skin_c)*nape
    # Measured skin gain (skin_tone_compare.py) on Asset B's skin; scalp texels
    # of the hair/skin pass take the hair gain so they match the hair shell.
    hair_gain = np.asarray(hair_note['linear_gain'], np.float32)
    full = baked['full'][:, :, :3]
    log_full = np.log(np.maximum(full, 1e-4))
    skin_ref = np.log(np.maximum(np.median(baked['skin'][:, :, :3][baked['skin_cov'] > 0.9], axis=0), 1e-4))
    hair_ref = np.log(np.maximum(np.asarray(hair_note['source_median_linear'], np.float32), 1e-4))
    hairlike = (((log_full-hair_ref)**2).sum(-1) < ((log_full-skin_ref)**2).sum(-1))[:, :, None]
    full = full*np.where(hairlike, hair_gain, skin_gain)
    # Body skin (neck below the head island, hands, midriff) toned to the
    # corrected face; the procedural head skin that fills uncovered texels
    # shares the body's texture statistics and takes the same gain.
    face_skin = baked['skin'][:, :, :3][(baked['skin_cov'] > 0.9)]
    lum = face_skin@np.array([0.2126, 0.7152, 0.0722], np.float32)
    keep = (lum > np.percentile(lum, 40)) & (lum < np.percentile(lum, 95))
    target = np.median(face_skin[keep], axis=0)*skin_gain
    body_mat = next(m for m in body.data.materials if m and m.name.startswith('Inez_Skin_Freckles'))
    bbsdf = next(n for n in body_mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    body_node = bbsdf.inputs['Base Color'].links[0].from_node
    bpx = image_pixels(body_node.image)
    blin = np.where(bpx[:, :, :3] <= 0.04045, bpx[:, :, :3]/12.92, ((bpx[:, :, :3]+0.055)/1.055)**2.4)
    bl = blin.reshape(-1, 3)
    bl_lum = bl@np.array([0.2126, 0.7152, 0.0722], np.float32)
    current = np.median(bl[(bl_lum > 0.05)], axis=0)
    # The clamp only guards against a degenerate measurement; the face gain
    # calibrated against the originals needs body gains near 0.5.
    body_gain = np.clip(target/np.maximum(current, 1e-4), 0.3, 1.6).astype(np.float32)
    rgb = (baked['skin'][:, :, :3]*skin_gain*skin_c+full*full_c+proc[:, :, :3]*body_gain*(1-skin_c-full_c))
    # Feather the head bake into the body skin over 2 cm above the head/body
    # material seam so the neck shows no colour step.
    seam = head_seam_points(body)
    dist = seam_distance(positions, raster_mask, seam)
    w = np.clip((dist-0.003)/0.02, 0, 1)
    w = (w*w*(3-2*w))[:, :, None]
    rgb = rgb*w+proc[:, :, :3]*body_gain*(1-w)
    # Asset B's ears sit elsewhere; its bake paints hair and scalp onto the
    # production ears. The ears take the tone-matched skin, slightly warmer.
    # (The small separate UV islands at the atlas edge are the eye-socket and
    # nasal/oral linings, hidden behind the eyes and lips; Asset B's eye colour
    # baked there is not visible.)
    ear = np.clip(ear_tex, 0, 1)[:, :, None]
    rgb = rgb*(1-ear)+proc[:, :, :3]*body_gain*np.array([1.04, 0.97, 0.96], np.float32)*ear
    report['ears'] = {'ear_vertices': ear_vertices, 'ear_texels': int((ear[:, :, 0] > 0.5).sum()),
                      'note': 'ears coloured with the tone-matched production skin, not Asset B (misaligned ears)'}
    rgb, report['lid_margins'] = lid_margin_tone(rgb, positions, raster_mask, eyes, eyeball_radius)
    # Brows first: freckles in the brow window would otherwise read as hair.
    rgb, eye_area = eye_area_tone(rgb, positions, raster_mask, eyes)
    report['eye_area'] = eye_area
    freckles, freckle_count = freckle_field(positions, raster_mask, eye_mid)
    rgb = rgb*(1-freckles[:, :, None]*np.array([0.40, 0.52, 0.60], np.float32))
    report['freckles'] = {'count': freckle_count, 'note': 'procedural distribution per original A (nose bridge, upper cheeks, sparse forehead)'}
    srgb = np.clip(rgb, 0, 1)
    srgb = np.where(srgb <= 0.0031308, srgb*12.92, 1.055*srgb**(1/2.4)-0.055)
    hi_img = save_image('inez_head_albedo_assetB', srgb, texdir/'highres')
    hi_img.scale(*game)
    hi_img.filepath_raw = str(texdir/'inez_head_albedo_assetB.png')
    hi_img.save()
    hi_img.pack()
    albedo_node.image = hi_img
    head_mat['albedo_source'] = 'Asset B base colour baked onto the head UV (skin-only face pass, hair/skin pass under hair)'
    out_lin = np.clip(blin*body_gain, 0, 1)
    out_srgb = np.where(out_lin <= 0.0031308, out_lin*12.92, 1.055*out_lin**(1/2.4)-0.055)
    body_img = save_image('inez_body_albedo_tone_matched', out_srgb, texdir)
    body_node.image = body_img
    report['body_skin_tone'] = {'target_linear': target.tolist(), 'previous_linear': current.tolist(),
                                'gain': body_gain.tolist(), 'face_skin_gain': skin_gain.tolist(),
                                'note': 'face skin gain measured against both original portraits (skin_tone_compare.py)'}
    report['head_seam'] = {'seam_vertices': int(len(seam)), 'feather_m': [0.003, 0.023]}
    report['head_bake'] = {'size': list(size), 'embedded': list(game),
                           'skin_coverage': float((baked['skin_cov'] > 0.5).mean()),
                           'full_coverage': float((baked['full_cov'] > 0.5).mean())}
    for obj in (a_src, b_src):
        bpy.data.objects.remove(obj, do_unlink=True)
    scene['INEZ_STAGE'] = 'master assembled from the user\'s Asset A (body/costume) and Asset B (face/hair) on the rigged production topology'
    out = Path(args.output_blend)
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out.resolve()))
    from model_dress import export_glb
    export_glb(Path(args.output_glb))
    report['outputs'] = {'blend': str(out), 'glb': args.output_glb}
    if args.manifest:
        Path(args.manifest).write_text(json.dumps(report, indent=2, default=float)+'\n')
    print('SOURCE_ASSEMBLE '+json.dumps({k: v for k, v in report.items() if k != 'removed_procedural_objects'}, default=float))


if __name__ == '__main__':
    main()
