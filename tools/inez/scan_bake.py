"""Bake the reshaped scan's surface detail into Inez's head UV (tangent space).

    blender -b DRESSED.blend --python tools/inez/scan_bake.py -- \
        --scan-blend assets/characters/inez/model/inez_scan_base.blend \
        --fit scan_fitted.npz --masks scan_masks.npz --output DIR [--preview DIR] [--size 4096x2048]

High poly: the Ten24 L4 crop moved to its scan_fit.py `fitted` positions,
shaded with the publisher Level_04 tangent normal map. Per-vertex transfer
masks (scan_masks.py) fade the publisher normal map out over stubble and
brows and zero everything over hair, scanned eyeballs and the closed lip seam.
Low poly: Inez's head-material faces exactly as built (identity keys at their
defaults, rest pose, head UV layout), so the tangent frame matches the GLB.

Writes scan_detail_normal.png (8-bit tangent normal) and scan_detail_mask.png
(8-bit transfer weight from the geometric-detail mask, 0 where no scan surface
was hit and on the eye-socket/mouth-interior islands) for
model_dress_v04.py --scan-detail. Does not save the .blend.
"""
import argparse
import json
import struct
import sys
import zlib
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scan_common import SCAN_DIR, Studio, VIEWS, clay_material

BODY = 'Inez_ContinuousHumanMesh_UNAPPROVED'
SCAN = 'SCAN_Ten24_L4_SOURCE_NOT_INEZ'


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scan-blend', required=True)
    parser.add_argument('--fit', required=True)
    parser.add_argument('--masks', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--preview')
    parser.add_argument('--size', default='4096x2048')
    parser.add_argument('--cage', type=float, default=0.004)
    parser.add_argument('--distance', type=float, default=0.008)
    parser.add_argument('--samples', type=int, default=4)
    return parser.parse_args(sys.argv[sys.argv.index('--')+1:])


def write_png(path, array, bits):
    """Minimal PNG writer (Blender's Python has no imaging library). `array` is
    HxWxC float 0-1 in Blender row order (bottom row first)."""
    array = np.clip(array[::-1], 0, 1)
    h, w = array.shape[:2]
    channels = 1 if array.ndim == 2 else array.shape[2]
    kind = {1: 0, 3: 2, 4: 6}[channels]
    if bits == 16:
        data = (array*65535+0.5).astype('>u2')
    else:
        data = (array*255+0.5).astype(np.uint8)
    rows = data.reshape(h, -1).view(np.uint8).reshape(h, -1)
    raw = np.concatenate((np.zeros((h, 1), np.uint8), rows), axis=1).tobytes()

    def chunk(tag, payload):
        return struct.pack('>I', len(payload))+tag+payload+struct.pack('>I', zlib.crc32(tag+payload) & 0xffffffff)
    png = b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, bits, kind, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(raw, 6))+chunk(b'IEND', b'')
    Path(path).write_bytes(png)


def image_array(img):
    w, h = img.size
    px = np.empty(w*h*4, np.float32)
    img.pixels.foreach_get(px)
    return px.reshape(h, w, 4)


def clean_mask(arr, W, H, strip_px=3556):
    """Inez-side exclusions and soft edges for the transfer mask.

    The right strip of the head layout holds the eye-socket and mouth-interior
    islands (head_uv.py): inner lids and the oral cavity keep procedural skin.
    The mask is eroded by ~3 texels (hair and seam borders) and softened.
    """
    m = arr[:, :, 0].copy()
    m[:, int(strip_px*W/4096):] = 0
    for _ in range(3):
        m = np.minimum.reduce([m, np.roll(m, 1, 0), np.roll(m, -1, 0), np.roll(m, 1, 1), np.roll(m, -1, 1)])
    for _ in range(2):
        m = (m+np.roll(m, 1, 0)+np.roll(m, -1, 0)+np.roll(m, 1, 1)+np.roll(m, -1, 1))/5
    out = arr.copy()
    out[:, :, 0] = out[:, :, 1] = out[:, :, 2] = m
    return out


def bake_low(body):
    """Evaluated head-material faces of the body as a standalone bake target."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    mesh = bpy.data.meshes.new_from_object(body.evaluated_get(depsgraph), preserve_all_data_layers=True,
                                           depsgraph=depsgraph)
    head_index = next(i for i, m in enumerate(body.data.materials) if m and m.name.startswith('Inez_Head_Skin'))
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index != head_index], context='FACES')
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.clear()
    mesh.polygons.foreach_set('material_index', [0]*len(mesh.polygons))
    low = bpy.data.objects.new('ScanBake_LowHead', mesh)
    low.matrix_world = body.matrix_world
    bpy.context.scene.collection.objects.link(low)
    return low


def scan_material(normal_image, emission=False):
    mat = bpy.data.materials.new('ScanBakeSource_Emission' if emission else 'ScanBakeSource_Normal')
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    attr = nodes.new('ShaderNodeAttribute')
    attr.attribute_name = 'TransferMask'
    if emission:
        nodes.clear()
        out = nodes.new('ShaderNodeOutputMaterial')
        em = nodes.new('ShaderNodeEmission')
        attr = nodes.new('ShaderNodeAttribute')
        attr.attribute_name = 'TransferMask'
        sep = nodes.new('ShaderNodeSeparateColor')
        links.new(attr.outputs['Color'], sep.inputs['Color'])
        links.new(sep.outputs['Green'], em.inputs['Strength'])
        em.inputs['Color'].default_value = (1, 1, 1, 1)
        links.new(em.outputs['Emission'], out.inputs['Surface'])
        return mat
    bsdf = nodes['Principled BSDF']
    uv = nodes.new('ShaderNodeUVMap')
    uv.uv_map = 'ScanUV'
    tex = nodes.new('ShaderNodeTexImage')
    tex.image = normal_image
    tex.interpolation = 'Cubic'
    links.new(uv.outputs['UV'], tex.inputs['Vector'])
    nmap = nodes.new('ShaderNodeNormalMap')
    nmap.uv_map = 'ScanUV'
    links.new(tex.outputs['Color'], nmap.inputs['Color'])
    geo = nodes.new('ShaderNodeNewGeometry')
    sep = nodes.new('ShaderNodeSeparateColor')
    links.new(attr.outputs['Color'], sep.inputs['Color'])
    mix = nodes.new('ShaderNodeMix')
    mix.data_type = 'VECTOR'
    links.new(sep.outputs['Red'], mix.inputs['Factor'])
    links.new(geo.outputs['Normal'], mix.inputs['A'])
    links.new(nmap.outputs['Normal'], mix.inputs['B'])
    norm = nodes.new('ShaderNodeVectorMath')
    norm.operation = 'NORMALIZE'
    links.new(mix.outputs['Result'], norm.inputs[0])
    links.new(norm.outputs['Vector'], bsdf.inputs['Normal'])
    return mat


def main():
    args = arguments()
    W, H = (int(v) for v in args.size.split('x'))
    scene = bpy.context.scene
    body = bpy.data.objects[BODY]
    for obj in scene.objects:
        if obj.type == 'MESH':
            for mod in obj.modifiers:
                if mod.type == 'SUBSURF':
                    mod.show_render = mod.show_viewport = False
    low = bake_low(body)
    with bpy.data.libraries.load(str(Path(args.scan_blend).resolve()), link=False) as (src, dst):
        dst.objects = [SCAN]
    scan = dst.objects[0]
    scene.collection.objects.link(scan)
    fit = np.load(args.fit)
    masks = np.load(args.masks)
    # The appended object keeps the OBJ importer's axis rotation, and its
    # matrix_world is stale until a depsgraph update; fitted positions are
    # world coordinates, so clear the transform and write them as local.
    scan.location, scan.rotation_euler, scan.scale = (0, 0, 0), (0, 0, 0), (1, 1, 1)
    local = fit['fitted'].astype(np.float64)
    if len(local) != len(scan.data.vertices):
        raise RuntimeError('Fit does not match the scan crop vertex count')
    scan.data.vertices.foreach_set('co', local.astype(np.float32).ravel())
    scan.data.update()
    colour = scan.data.color_attributes.new('TransferMask', 'FLOAT_COLOR', 'POINT')
    values = np.zeros((len(local), 4), np.float32)
    values[:, 0] = masks['normal_strength']
    values[:, 1] = masks['detail']
    values[:, 3] = 1
    colour.data.foreach_set('color', values.ravel())
    normal_image = bpy.data.images.load(str(SCAN_DIR/'Normal Maps/Level_04_Normal.PSD'))
    normal_image.colorspace_settings.name = 'Non-Color'
    scan.data.materials.clear()
    scan.data.materials.append(scan_material(normal_image))
    # Bake target images on the low-poly head.
    target_mat = bpy.data.materials.new('ScanBakeTarget')
    target_mat.use_nodes = True
    node = target_mat.node_tree.nodes.new('ShaderNodeTexImage')
    low.data.materials.append(target_mat)
    target_mat.node_tree.nodes.active = node
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = False
    bake = scene.render.bake
    bake.use_selected_to_active = True
    bake.use_cage = False
    bake.cage_extrusion = args.cage
    bake.max_ray_distance = args.distance
    bake.margin = 16
    bake.margin_type = 'EXTEND'
    bake.normal_space = 'TANGENT'
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action='DESELECT')
    scan.select_set(True)
    low.select_set(True)
    bpy.context.view_layer.objects.active = low
    results = {}
    for name, kind, emission in (('scan_detail_normal', 'NORMAL', False), ('scan_detail_mask', 'EMIT', True)):
        img = bpy.data.images.new(name, W, H, alpha=False, float_buffer=True)
        img.colorspace_settings.name = 'Non-Color'
        node.image = img
        if emission:
            scan.data.materials[0] = scan_material(None, emission=True)
            img.generated_color = (0, 0, 0, 1)
        bpy.ops.object.bake(type=kind)
        arr = image_array(img)
        if emission:
            arr = clean_mask(arr, W, H)
        results[name] = arr
        if kind == 'NORMAL':
            write_png(out/f'{name}.png', arr[:, :, :3], 8)
        else:
            write_png(out/f'{name}.png', arr[:, :, 0], 8)
        print('SCAN_BAKE', name, flush=True)
    m = results['scan_detail_mask'][:, :, 0]
    n = results['scan_detail_normal'][:, :, :3]*2-1
    tilt = np.degrees(np.arccos(np.clip(n[:, :, 2], -1, 1)))
    report = {'size': [W, H], 'cage_extrusion_m': args.cage, 'max_ray_distance_m': args.distance,
              'mask_coverage_fraction': float((m > 0.05).mean()),
              'detail_tilt_deg_where_masked': {'median': float(np.median(tilt[m > 0.5])) if (m > 0.5).any() else 0.0,
                                               'p95': float(np.percentile(tilt[m > 0.5], 95)) if (m > 0.5).any() else 0.0},
              'source': 'Ten24 sample scan L4 + Level_04 normal map, reshaped to Inez (scan_fit.py)',
              'credit': 'ten24.info', 'not_inez_source': True}
    (out/'scan_bake_report.json').write_text(json.dumps(report, indent=2)+'\n')
    print('SCAN_BAKE_REPORT', json.dumps(report))
    if args.preview:
        # Clay preview of the low-poly head with the masked detail applied.
        # Written to disk and reloaded: an unsaved generated image can be
        # regenerated (flat) at render time in background mode.
        weight = m[:, :, None]
        blend = n*weight+np.array([0, 0, 1])*(1-weight)
        blend /= np.linalg.norm(blend, axis=2, keepdims=True)
        pv = Path(args.preview)
        pv.mkdir(parents=True, exist_ok=True)
        write_png(pv/'preview_masked_detail_normal.png', blend*0.5+0.5, 16)
        img = bpy.data.images.load(str(pv/'preview_masked_detail_normal.png'))
        img.colorspace_settings.name = 'Non-Color'
        low.data.materials.clear()
        low.data.materials.append(clay_material('PreviewClay', img, 1.0, uv_map=low.data.uv_layers[0].name))
        for obj in scene.objects:
            if obj.type == 'MESH' and obj is not low:
                obj.hide_render = True
        arm = next(o for o in scene.objects if o.type == 'ARMATURE')
        eyes = [arm.matrix_world @ arm.data.bones['eye.'+s].head_local for s in ('L', 'R')]
        center = (eyes[0]+eyes[1])/2
        center.z -= 0.035
        for obj in scene.objects:
            if obj.name.startswith(('Inez_Eyeball', 'Inez_Cornea', 'Inez_Iris')):
                obj.hide_render = False
        studio = Studio(scene, 48, 900)
        studio.set_label('PASS 5 INEZ HEAD + BAKED SCAN DETAIL (clay)')
        for view in ('front', 'three_quarter', 'left'):
            studio.render(center, 0.30, VIEWS[view], pv/f'{view}.png')


if __name__ == '__main__':
    main()
