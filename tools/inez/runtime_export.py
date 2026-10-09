"""Package the animated Inez master and its runtime LOD exports.

    blender -b ANIMATED.blend --python tools/inez/runtime_export.py -- \
        --character-dir assets/characters/inez --work-dir SCRATCH/runtime [--report runtime_export.json]

Writes (paths below --character-dir):
  textures/master/*.png|jpg    every image the master uses, moved out of the
                               .blend: unmodified source atlases keep their
                               exact bytes, derived colour atlases are JPEG
                               q95, other derived maps PNG. Images already in
                               the repository (the original references) are
                               linked in place and never rewritten.
  model/inez_master.blend      editable master: rig, clips, identity layers;
                               textures linked relatively, file compressed
  WORK/inez_master_raw.glb     full-resolution export (JPEG textures; q92 where
                               re-encoded)
  WORK/inez_runtime_lodN.glb   lossless runtime levels before glTF-Transform:
                               LOD0 hair 45k / knit 26k / jeans 20k / boots 16k
                               LOD1 hair 20k / knit 12k / jeans 9k / boots 7k
                               LOD2 hair 8k / knit 5k / jeans 4k / boots 3k
                               (textures capped at 2048 / 1024 / 512 px)
The master's meshes are never decimated; every level is a separate export
of a reduced copy, so the master asset stays intact. Skinning, morph targets
and every action are exported on every level.
"""
import argparse
import json
import sys
from pathlib import Path

import bpy

LEVELS = {
    'lod0': {'Inez_Hair': 45000, 'Inez_Sweater': 26000, 'Inez_Jeans': 20000, 'Inez_Boots': 16000, 'texture': 2048},
    'lod1': {'Inez_Hair': 20000, 'Inez_Sweater': 12000, 'Inez_Jeans': 9000, 'Inez_Boots': 7000, 'texture': 1024},
    'lod2': {'Inez_Hair': 8000, 'Inez_Sweater': 5000, 'Inez_Jeans': 4000, 'Inez_Boots': 3000, 'texture': 512},
}
COLOUR_JPEG = ('basecolor', 'albedo')
ROOT = Path(__file__).resolve().parents[2]


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('--character-dir', required=True)
    parser.add_argument('--work-dir', required=True)
    parser.add_argument('--report')
    parser.add_argument('--levels', default='lod0,lod1,lod2')
    return parser.parse_args(sys.argv[sys.argv.index('--')+1:])


def triangles(obj):
    return sum(len(p.vertices)-2 for p in obj.data.polygons)


def export(path, objects, arm, image_format='JPEG', quality=92):
    bpy.ops.object.select_all(action='DESELECT')
    arm.select_set(True)
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = arm
    options = dict(filepath=str(path), export_format='GLB', use_selection=True, export_yup=True,
                   export_texcoords=True, export_normals=True, export_tangents=True, export_skins=True,
                   export_morph=True, export_materials='EXPORT', export_all_influences=False,
                   export_morph_animation=False, export_animations=True, export_animation_mode='ACTIONS',
                   export_anim_single_armature=True, export_cameras=False, export_lights=False, export_extras=True,
                   export_apply=False, export_force_sampling=True, export_image_format=image_format,
                   export_image_quality=quality)
    properties = bpy.ops.export_scene.gltf.get_rna_type().properties
    bpy.ops.export_scene.gltf(**{k: v for k, v in options.items() if k in properties})


def image_bytes(img):
    """The packed or on-disk bytes of an unmodified file image, with its format."""
    if img.source != 'FILE' or img.is_dirty:
        return None, None
    data = bytes(img.packed_file.data) if img.packed_file else None
    if data is None:
        path = Path(bpy.path.abspath(img.filepath_raw))
        data = path.read_bytes() if path.is_file() else None
    if data and data.startswith(b'\xff\xd8\xff'):
        return data, 'JPEG'
    if data and data.startswith(b'\x89PNG'):
        return data, 'PNG'
    return None, None


def prune_unconnected_images():
    """Remove image nodes that feed nothing (leftovers of colour correction)."""
    removed = []
    for mat in bpy.data.materials:
        if not mat.use_nodes:
            continue
        for node in list(mat.node_tree.nodes):
            if node.type == 'TEX_IMAGE' and not any(out.links for out in node.outputs):
                removed.append(f'{mat.name}:{node.image.name if node.image else node.name}')
                mat.node_tree.nodes.remove(node)
    return removed


def unpack_images(texdir):
    """Move every used image out of the .blend.

    - Files inside the repository (the original references and the reference
      boards) are linked where they are and never rewritten.
    - Unmodified source images keep their exact bytes (Asset A/B atlases).
    - Derived colour atlases larger than 2048 px are stored as JPEG q95; all
      other derived images as PNG.
    """
    texdir.mkdir(parents=True, exist_ok=True)
    written = {}
    for img in list(bpy.data.images):
        if img.source not in ('FILE', 'GENERATED') or img.size[0] == 0 or not img.users:
            continue
        if img.name.startswith(('headbake_', 'headcov_')):
            continue
        current = Path(bpy.path.abspath(img.filepath)).resolve() if img.filepath else None
        if current and current.is_file() and ROOT in current.parents and texdir.resolve() not in current.parents:
            if img.packed_file:
                img.unpack(method='REMOVE')
            img.filepath = str(current)
            written[img.name] = {'file': str(current.relative_to(ROOT)), 'linked': True}
            continue
        safe = ''.join(c if c.isalnum() or c in '-_' else '_' for c in Path(img.name).stem)
        data, fmt = image_bytes(img)
        colour = any(k in img.name.lower() for k in COLOUR_JPEG) and img.colorspace_settings.name == 'sRGB'
        if data and not (fmt == 'PNG' and colour and max(img.size) > 2048):
            target = texdir/(safe+('.jpg' if fmt == 'JPEG' else '.png'))
            target.write_bytes(data)
            how = 'source bytes'
        else:
            fmt = 'JPEG' if colour else 'PNG'
            target = texdir/(safe+('.jpg' if colour else '.png'))
            img.filepath_raw = str(target)
            img.file_format = fmt
            img.save(filepath=str(target), quality=95)
            how = 'encoded'
        if img.packed_file:
            img.unpack(method='REMOVE')
        img.source = 'FILE'
        img.filepath = str(target)
        img.reload()
        written[img.name] = {'file': target.name, 'size': list(img.size), 'format': fmt, 'written': how,
                             'bytes': target.stat().st_size}
    return written


def decimate_copy(obj, target):
    copy = obj.copy()
    copy.data = obj.data.copy()
    copy.name = obj.name+'_lod'
    bpy.context.scene.collection.objects.link(copy)
    before = triangles(copy)
    if before > target and not copy.data.shape_keys:
        mod = copy.modifiers.new('LOD_Decimate', 'DECIMATE')
        mod.ratio = target/before
        mod.use_collapse_triangulate = True
        bpy.context.view_layer.objects.active = copy
        while copy.modifiers[0] != mod:
            bpy.ops.object.modifier_move_up(modifier=mod.name)
        bpy.ops.object.modifier_apply(modifier=mod.name)
    return copy, before, triangles(copy)


def scaled_images(limit, work):
    """Downscaled copies of every image above the limit; returns {orig: copy}.

    Each copy is saved as a PNG in the work directory: the glTF exporter reuses
    an unmodified image's file bytes, which would otherwise be the full-size
    original."""
    mapping = {}
    used = {node.image for mat in bpy.data.materials if mat.use_nodes
            for node in mat.node_tree.nodes if node.type == 'TEX_IMAGE' and node.image}
    for img in used:
        if img.size[0] == 0 or max(img.size) <= limit:
            continue
        copy = img.copy()
        copy.name = f'{img.name}_{limit}'
        w, h = img.size
        s = limit/max(w, h)
        copy.scale(max(1, int(w*s)), max(1, int(h*s)))
        safe = ''.join(c if c.isalnum() or c in '-_' else '_' for c in Path(img.name).stem)
        path = work/f'lod_{limit}_{safe}.png'
        copy.filepath_raw = str(path)
        copy.file_format = 'PNG'
        copy.save()
        if copy.packed_file:
            copy.unpack(method='REMOVE')
        copy.filepath = str(path)
        copy.reload()
        mapping[img] = copy
    return mapping


def swap_images(mapping, forward=True):
    for mat in bpy.data.materials:
        if not mat.use_nodes:
            continue
        for node in mat.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image:
                if forward and node.image in mapping:
                    node.image = mapping[node.image]
                elif not forward:
                    for orig, copy in mapping.items():
                        if node.image == copy:
                            node.image = orig


def main():
    args = arguments()
    char = Path(args.character_dir)
    work = Path(args.work_dir)
    work.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    arm = next(o for o in scene.objects if o.type == 'ARMATURE')
    meshes = [o for o in scene.objects if o.type == 'MESH' and not o.hide_render]
    report = {'source_blend': bpy.data.filepath, 'levels': {}}
    report['unconnected_image_nodes_removed'] = prune_unconnected_images()
    report['master_textures'] = unpack_images(char/'textures'/'master')
    bpy.ops.file.make_paths_relative()
    master_blend = char/'model'/'inez_master.blend'
    master_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(master_blend.resolve()), compress=True, relative_remap=True)
    report['master_blend'] = {'path': str(master_blend), 'bytes': master_blend.stat().st_size}
    # export_apply is off, so modifiers other than the armature are not
    # exported; subdivision is disabled anyway so nothing depends on that.
    for obj in meshes:
        for mod in obj.modifiers:
            if mod.type == 'SUBSURF':
                mod.show_viewport = mod.show_render = False
    raw = work/'inez_master_raw.glb'
    export(raw, meshes, arm)
    report['master_glb_raw'] = {'path': str(raw), 'bytes': raw.stat().st_size,
                                'triangles': {o.name: triangles(o) for o in meshes}}
    for level in [l for l in args.levels.split(',') if l]:
        spec = LEVELS[level]
        copies, originals, info = [], [], {}
        for obj in meshes:
            if obj.name in spec:
                copy, before, after = decimate_copy(obj, spec[obj.name])
                obj.hide_set(True)
                copies.append(copy)
                originals.append(obj)
                info[obj.name] = [before, after]
        objects = [o for o in meshes if o not in originals]+copies
        mapping = scaled_images(spec['texture'], work)
        swap_images(mapping, True)
        path = work/f'inez_runtime_{level}.glb'
        # Lossless intermediates: glTF-Transform re-encodes them to KTX2.
        export(path, objects, arm, image_format='AUTO')
        swap_images(mapping, False)
        for copy in copies:
            bpy.data.objects.remove(copy, do_unlink=True)
        for img in mapping.values():
            bpy.data.images.remove(img)
        for obj in originals:
            obj.hide_set(False)
        report['levels'][level] = {'path': str(path), 'bytes': path.stat().st_size, 'decimated': info,
                                   'texture_limit_px': spec['texture'],
                                   'triangles_total': sum(triangles(o) for o in meshes if o.name not in spec)+sum(v[1] for v in info.values())}
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2)+'\n')
    print('RUNTIME_EXPORT '+json.dumps({k: (v if k != 'master_textures' else len(v)) for k, v in report.items()}))


if __name__ == '__main__':
    main()
