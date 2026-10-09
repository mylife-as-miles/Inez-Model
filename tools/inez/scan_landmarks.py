"""Detect face landmarks on a mesh from several views and lift them to 3D surface points.

    blender -b FILE.blend --python tools/inez/scan_landmarks.py -- \
        --object NAME --output LANDMARKS.json --image-dir DIR \
        [--views front,three_quarter,three_quarter_right] [--span 0.30] \
        [--scan-colour] [--hide Hair,Curl,...]

Used identically on the Ten24 scan crop and on Inez's body mesh so both
landmark sets come from the same cameras, framing and detector. Each view is
an orthographic render centred on the eye midpoint (found by a first wide
pass); every MediaPipe landmark pixel is cast onto the object along the view
axis. Per landmark the 3D point is taken from the view that sees that part of
the surface most frontally
(fixed rule from the frontal image so every mesh uses the same view per landmark). `--scan-colour` applies the publisher colour map to
the scan for detection only (that render is a measurement input, never an Inez
texture). Landmarks are a measurement aid, not a biometric identity score.
"""
import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scan_common import SCAN_DIR, Studio, VIEWS

DETECTOR = Path(__file__).resolve().parent/'face_landmarks.py'


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('--object', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--image-dir', required=True)
    parser.add_argument('--views', default='front,three_quarter,three_quarter_right')
    parser.add_argument('--span', type=float, default=0.30)
    parser.add_argument('--resolution', type=int, default=1024)
    parser.add_argument('--samples', type=int, default=32)
    parser.add_argument('--scan-colour', action='store_true')
    parser.add_argument('--hide', default='')
    parser.add_argument('--extra-bvh', default='', help='name substrings of extra meshes rays may hit (e.g. Eyeball,Cornea)')
    parser.add_argument('--python', default='python3')
    parser.add_argument('--probe-span', type=float, default=0.42, help='first wide frontal render span (m)')
    parser.add_argument('--probe-drop', type=float, default=0.14, help='probe centre below the top of the object (m)')
    return parser.parse_args(sys.argv[sys.argv.index('--')+1:])


def scan_colour_material():
    mat = bpy.data.materials.new('ScanColour_DetectionOnly')
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    tex = nodes.new('ShaderNodeTexImage')
    tex.image = bpy.data.images.load(str(SCAN_DIR/'Colour Maps/JPG/Colour_8k.jpg'))
    bsdf = nodes['Principled BSDF']
    bsdf.inputs['Roughness'].default_value = 0.5
    mat.node_tree.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    return mat


def detect(image, python):
    run = subprocess.run([python, str(DETECTOR), str(image)], capture_output=True, text=True)
    lines = run.stdout.strip().splitlines()
    data = json.loads(lines[-1]) if lines else {'face': False}
    return data if data.get('face') else None


def main():
    args = arguments()
    scene = bpy.context.scene
    target = bpy.data.objects[args.object]
    hide = [h for h in args.hide.split(',') if h]
    for obj in scene.objects:
        if obj.type == 'MESH':
            for mod in obj.modifiers:
                if mod.type == 'SUBSURF':
                    mod.show_render = mod.show_viewport = False
            if any(h in obj.name for h in hide):
                obj.hide_render = True
        if obj.type == 'LIGHT':
            obj.hide_render = True
    if args.scan_colour:
        target.data.materials.clear()
        target.data.materials.append(scan_colour_material())
    depsgraph = bpy.context.evaluated_depsgraph_get()
    verts, polys, owners = [], [], []
    extra = [h for h in args.extra_bvh.split(',') if h]
    sources = [target]+[o for o in scene.objects if o.type == 'MESH' and o is not target
                        and any(h in o.name for h in extra) and not o.hide_render]
    for obj in sources:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        base = len(verts)
        verts += [obj.matrix_world @ v.co for v in mesh.vertices]
        for p in mesh.polygons:
            polys.append([base+i for i in p.vertices])
            owners.append(obj.name)
        evaluated.to_mesh_clear()
        if obj is target:
            target_verts = list(verts)
    bvh = BVHTree.FromPolygons(verts, polys)
    top = max(v.z for v in target_verts)
    upper = [v for v in target_verts if v.z > top-max(0.30, args.probe_drop*2)]
    xs, ys = [v.x for v in upper], [v.y for v in upper]
    center = Vector(((min(xs)+max(xs))/2, (min(ys)+max(ys))/2, top-args.probe_drop))
    studio = Studio(scene, args.samples, args.resolution)
    images = Path(args.image_dir)
    images.mkdir(parents=True, exist_ok=True)

    def cast(view, pixels, center, span):
        yaw = math.radians(VIEWS[view])
        forward = Vector((math.sin(yaw), -math.cos(yaw), 0))
        right = Vector((math.cos(yaw), math.sin(yaw), 0))
        hits = {}
        for k, (u, v, *_rest) in enumerate(pixels):
            origin = center+right*((u/args.resolution-0.5)*span)+Vector((0, 0, (0.5-v/args.resolution)*span))
            start = origin+forward*1.0
            hit, normal, face, distance = bvh.ray_cast(start, -forward, 3.0)
            # First contact of a 1.5 mm thick ray: silhouette landmarks (jaw,
            # chin, face outline) graze the surface, and a thin ray would pass
            # them and land on the neck or shoulders behind.
            far = distance if hit is not None else 2.0
            step = 0.0005
            t = max(0.0, far-0.15)
            while t <= far:
                near, nnormal, nface, ndist = bvh.find_nearest(start-forward*t)
                if near is not None and ndist < 0.0015:
                    if hit is None or t < distance-0.002:
                        hit, normal, face, distance = near, nnormal, nface, t
                    break
                t += step
            if hit is not None:
                hits[k] = {'world': list(hit), 'normal': list(normal), 'face': face, 'object': owners[face],
                           'facing': float(normal.dot(forward)), 'pixel': [u, v], 'depth': float(distance)}
        return hits
    # Pass 1: wide frontal render to find the eyes, then centre every view on them.
    probe = images/'probe_front.png'
    studio.render(center, args.probe_span, 0, probe)
    data = detect(probe, args.python)
    if data is None:
        raise SystemExit('No face detected in the probe render '+str(probe))
    corners = cast('front', [data['landmarks'][i] for i in (33, 133, 362, 263)], center, args.probe_span)
    if len(corners) < 4:
        raise SystemExit('Eye corners not on the surface in the probe render')
    eye_mid = sum((Vector(c['world']) for c in corners.values()), Vector())/4
    center = eye_mid+Vector((0, 0, -0.035))
    report = {'object': args.object, 'span_m': args.span, 'resolution': args.resolution,
              'center_world': list(center), 'eye_corner_mid_world': list(eye_mid), 'views': {}}
    per_view = {}
    for view in args.views.split(','):
        image = images/f'{view}.png'
        studio.render(center, args.span, VIEWS[view], image)
        data = detect(image, args.python)
        if data is None:
            report['views'][view] = {'image': str(image), 'face': False}
            continue
        hits = cast(view, data['landmarks'], center, args.span)
        per_view[view] = hits
        report['views'][view] = {'image': str(image), 'face': True, 'pose': data.get('pose'),
                                 'landmarks_px': data['landmarks'], 'cast': len(hits)}
    combined = {}
    # Fixed view rule shared by every mesh so the same landmark always comes
    # from the same camera: lateral position in the frontal image, in units of
    # half the eye-corner distance, picks front or the 3/4 view facing that side.
    front_px = report['views'].get('front', {}).get('landmarks_px')
    if front_px is None:
        raise SystemExit('Frontal detection failed; the fixed view rule needs it')
    mid_x = (front_px[133][0]+front_px[362][0])/2
    half = abs(front_px[263][0]-front_px[33][0])/2
    for k in range(478):
        side = (front_px[k][0]-mid_x)/half
        order = ['front'] if abs(side) < 1.25 else (['three_quarter', 'front'] if side > 0 else ['three_quarter_right', 'front'])
        for view in order:
            hit = per_view.get(view, {}).get(k)
            if hit is not None:
                combined[k] = {'world': hit['world'], 'normal': hit['normal'], 'face': hit['face'],
                               'object': hit['object'], 'view': view, 'facing': hit['facing'],
                               'depth': hit['depth'], 'side': side}
                break
    report['landmarks'] = combined
    report['note'] = 'MediaPipe measurement aid lifted to the surface; not a biometric similarity score'
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report)+'\n')
    print('SCAN_LANDMARKS', json.dumps({'object': args.object, 'views': {v: r.get('cast', 0) for v, r in report['views'].items()},
                                        'combined': len(combined)}))


if __name__ == '__main__':
    main()
