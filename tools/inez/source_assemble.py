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
        dark, light = float(np.percentile(Lc, 25)), float(np.percentile(Lc, 80))
        charcoal = srgb_lin([0.245, 0.245, 0.255]).astype(np.float32)
        navy = srgb_lin([0.072, 0.080, 0.150]).astype(np.float32)
        note = {'mapping': 'light knit -> charcoal, dark knit -> navy, knit luminance variation kept',
                'source_dark_light_linear': [dark, light], 'charcoal_srgb': [0.245, 0.245, 0.255],
                'navy_srgb': [0.072, 0.080, 0.150]}
    elif kind == 'jeans':
        note = {'mapping': 'washed charcoal denim -> washed black (linear gain 0.42)'}
    srgb = np.empty(px.shape[:2]+(3,), np.float32)
    for r0 in range(0, px.shape[0], 512):
        rgb = px[r0:r0+512, :, :3]
        lin = np.where(rgb <= 0.04045, rgb/12.92, ((rgb+0.055)/1.055)**2.4)
        if kind == 'sweater':
            L = lin@np.array([0.2126, 0.7152, 0.0722], np.float32)
            t = np.clip((L-dark)/max(light-dark, 1e-4), 0, 1)[:, :, None]
            ref_L = dark*(1-t)+light*t
            out = (navy*(1-t)+charcoal*t)*np.clip(L[:, :, None]/np.maximum(ref_L, 1e-4), 0.4, 1.8)
        elif kind == 'jeans':
            out = lin*0.42
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


# ---------------------------------------------------------------- skinning

SEGMENTS = {
    'upperarm.{s}': ('upperarm01.{s}', 'lowerarm01.{s}', 0.045), 'forearm.{s}': ('lowerarm01.{s}', 'wrist.{s}', 0.038),
    'hand.{s}': ('wrist.{s}', 'finger3-1.{s}', 0.035), 'thigh.{s}': ('upperleg01.{s}', 'lowerleg01.{s}', 0.075),
    'shin.{s}': ('lowerleg01.{s}', 'foot.{s}', 0.055), 'foot.{s}': ('foot.{s}', 'toe1-1.{s}', 0.045),
}
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


def skin_part_aware(garment, body, arm, parts, allowed=None):
    """Weights from the k nearest body vertices of the same body part as the
    nearest bone segment (plus the torso near shoulder and hip joints)."""
    joints = {b.name: arm.matrix_world @ b.head_local for b in arm.data.bones}
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


# ---------------------------------------------------------------- head bake

def bake_head_from_b(body, b_obj, b_labels, size, texdir):
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
    full = b_obj.copy()
    full.data = b_obj.data.copy()
    scene.collection.objects.link(full)
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
    b_labels = np.load(args.regions_b)['labels']
    a_colours = np.load(args.regions_a)['colours'].astype(np.float32)
    targets = dict((k, int(v)) for k, v in (item.split('=') for item in args.targets.split(',')))
    report = {'removed_procedural_objects': removed, 'parts': {}}
    parts = body_parts(body)
    a_mat = a_src.data.materials[0]
    for region, name in (('sweater', 'Inez_Sweater'), ('jeans', 'Inez_Jeans'), ('boots', 'Inez_Boots')):
        obj = extract_part(a_src, a_labels, {REGIONS.index(region)}, name)
        before, after = decimate(obj, targets[region])
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
    hair = extract_part(b_src, b_labels, {REGIONS.index('hair')}, 'Inez_Hair')
    before, after = decimate(hair, targets['hair'])
    # Brows and irises are hair-coloured but belong to the face: keep only the
    # connected hair masses (scalp, ponytail, framing curls).
    drop_small_islands(hair, 150)
    hair.data.materials.clear()
    hair.data.materials.append(b_src.data.materials[0])
    for g in body.vertex_groups:
        if g.name not in hair.vertex_groups:
            hair.vertex_groups.new(name=g.name)
    hair.vertex_groups['head'].add(list(range(len(hair.data.vertices))), 1.0, 'REPLACE')
    attach_armature(hair, arm)
    hair['source'] = f'Asset B (Inez Facial Model.glb) hair shell, decimated {before} -> {after} triangles'
    report['parts']['Inez_Hair'] = {'source': 'Asset B', 'region': 'hair', 'triangles_source': before, 'triangles': after}
    garments = [scene.objects['Inez_Sweater'], scene.objects['Inez_Jeans'], scene.objects['Inez_Boots']]
    report['body_faces_removed_under_source_clothing'] = hide_body_by_source(body, a_src, a_labels, {'head'}, parts)
    parts = body_parts(body)
    report['body_faces_hidden_under_garments'] = hide_body_under(body, garments, {'head', 'hand.L', 'hand.R'}, parts)
    # Head colour from Asset B.
    size = tuple(int(v) for v in args.head_size.split('x'))
    game = tuple(int(v) for v in args.game_head_size.split('x'))
    baked = bake_head_from_b(body, b_src, b_labels, size, texdir)
    head_mat = next(m for m in body.data.materials if m and m.name.startswith('Inez_Head_Skin'))
    bsdf = next(n for n in head_mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    albedo_node = bsdf.inputs['Base Color'].links[0].from_node
    if tuple(albedo_node.image.size) != size:
        albedo_node.image.scale(*size)
    proc = image_pixels(albedo_node.image)
    # Byte images hold sRGB-encoded values; the bakes are linear radiance.
    proc[:, :, :3] = np.where(proc[:, :, :3] <= 0.04045, proc[:, :, :3]/12.92, ((proc[:, :, :3]+0.055)/1.055)**2.4)
    skin_c = np.clip(baked['skin_cov'], 0, 1)[:, :, None]
    full_c = np.clip(baked['full_cov'], 0, 1)[:, :, None]*(1-skin_c)
    rgb = baked['skin'][:, :, :3]*skin_c+baked['full'][:, :, :3]*full_c+proc[:, :, :3]*(1-skin_c-full_c)
    srgb = np.clip(rgb, 0, 1)
    srgb = np.where(srgb <= 0.0031308, srgb*12.92, 1.055*srgb**(1/2.4)-0.055)
    hi_img = save_image('inez_head_albedo_assetB', srgb, texdir/'highres')
    hi_img.scale(*game)
    hi_img.filepath_raw = str(texdir/'inez_head_albedo_assetB.png')
    hi_img.save()
    hi_img.pack()
    albedo_node.image = hi_img
    head_mat['albedo_source'] = 'Asset B base colour baked onto the head UV (skin-only face pass, full pass under hair)'
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
