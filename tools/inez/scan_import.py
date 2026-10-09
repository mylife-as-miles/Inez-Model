"""Import the Ten24 sample scan untouched and render it as a labelled source.

    blender -b --python tools/inez/scan_import.py -- \
        --output assets/characters/inez/model/inez_scan_base.blend \
        --renders assets/characters/inez/renders/scan_source [--level 4]

Reads the publisher OBJ export (ZBrush SubD levels, metres, +Y up, +Z forward)
from scans/source/ten24_sample/extracted. Only a head/neck crop is kept; vertex
positions are not altered, and every kept vertex records its source OBJ index
(`scan_vertex_index`). Renders use clay plus the publisher's tangent-space
normal map for that level; the donor colour texture is never applied.
The .blend is a local working file (git-ignored) because it contains the raw
scan surface: rebuild it from the manifest-verified download with this script.
"""
import argparse
import json
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scan_common import CHARACTER, SCAN_DIR, Studio, VIEWS, clay_material, import_obj, keep_faces

CROP_Z = 1.48  # metres; keeps head, neck and the top of the collar region


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--renders', required=True)
    parser.add_argument('--level', type=int, default=4)
    parser.add_argument('--samples', type=int, default=48)
    parser.add_argument('--resolution', type=int, default=900)
    return parser.parse_args(sys.argv[sys.argv.index('--')+1:])


def main():
    args = arguments()
    if Path(args.output).resolve().name in ('inez.blend',):
        raise SystemExit('Refusing to overwrite a canonical model file')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    objects = {}
    for level in sorted({1, args.level}):
        obj = import_obj(SCAN_DIR/f'OBJ/Export SubD/Ten24_Sample_OBJ_SubD_Level{level}.OBJ',
                         f'SCAN_Ten24_L{level}_SOURCE_NOT_INEZ')
        keep_faces(obj, lambda co: min(c.z for c in co) > CROP_Z)
        uv = obj.data.uv_layers[0]
        uv.name = 'ScanUV'
        image = bpy.data.images.load(str(SCAN_DIR/f'Normal Maps/Level_{level:02d}_Normal.PSD'))
        image.colorspace_settings.name = 'Non-Color'
        obj.data.materials.clear()
        obj.data.materials.append(clay_material(f'ScanClay_L{level}', image, 1.0, uv_map='ScanUV'))
        for poly in obj.data.polygons:
            poly.use_smooth = True
        obj['scan_source'] = 'Ten24 sample scan 2016 (ten24.info), OBJ Package SubD level %d' % level
        obj['scan_crop'] = f'faces with every vertex above z={CROP_Z} m; positions unaltered'
        obj['not_inez'] = True
        objects[level] = obj
    main_obj = objects[args.level]
    for level, obj in objects.items():
        obj.hide_render = level != args.level
        obj.hide_viewport = level != args.level
    coords = [main_obj.matrix_world @ v.co for v in main_obj.data.vertices]
    head = [c for c in coords if c.z > 1.60]
    xs, ys, zs = [c.x for c in head], [c.y for c in head], [c.z for c in head]
    center = ((min(xs)+max(xs))/2, (min(ys)+max(ys))/2, 1.715)
    studio = Studio(scene, args.samples, args.resolution)
    studio.set_label('TEN24 SOURCE SCAN (L%d + normal map) - NOT INEZ' % args.level)
    out = Path(args.renders)
    out.mkdir(parents=True, exist_ok=True)
    for name in ('front', 'three_quarter', 'left'):
        studio.render(center, 0.36, VIEWS[name], out/f'scan_source_{name}.png')
    report = {
        'stage': 'scan_source_untouched', 'level': args.level, 'crop_z_m': CROP_Z,
        'objects': {o.name: {'vertices': len(o.data.vertices), 'faces': len(o.data.polygons)} for o in objects.values()},
        'head_bounds_m': {'x': [min(xs), max(xs)], 'y': [min(ys), max(ys)], 'z': [min(zs), max(zs)]},
        'render_center_m': list(center), 'renders': [f'scan_source_{n}.png' for n in ('front', 'three_quarter', 'left')],
        'material': 'neutral clay + publisher tangent-space normal map; donor colour texture not applied',
        'label': 'source scan, not Inez',
    }
    (out/'scan_source_report.json').write_text(json.dumps(report, indent=2)+'\n')
    for obj in list(scene.objects):
        if obj.type in ('FONT', 'LIGHT', 'CAMERA') or obj.name.startswith('ScanLabel'):
            bpy.data.objects.remove(obj)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(args.output).resolve()), compress=True)
    print('SCAN_IMPORT', json.dumps(report['objects']))


if __name__ == '__main__':
    main()
