"""Render the actual head, detect face landmarks and map them to mesh vertices.

    blender -b DRESSED.blend --python tools/inez/head_landmark_map.py -- \
        --output qa/model/head_landmarks_v04.json --image render.png [--yaw 0] [--hide-hair]

Orthographic neutral render of the real body mesh (subdivision disabled, as in
the GLB). Each MediaPipe landmark pixel is cast back onto the body surface to
find the licensed MakeHuman source vertex under it. This is a measurement aid
for frontal proportion fitting, not a biometric identity score.
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


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--image', required=True)
    parser.add_argument('--yaw', type=float, default=0.0)
    parser.add_argument('--hide-hair', action='store_true')
    parser.add_argument('--resolution', type=int, default=1024)
    parser.add_argument('--span', type=float, default=0.30)
    parser.add_argument('--detector', default=str(Path(__file__).resolve().parent/'face_landmarks.py'))
    parser.add_argument('--python', default='python3')
    return parser.parse_args(sys.argv[sys.argv.index('--')+1:])


def look_at(obj, target):
    obj.rotation_euler = (Vector(target)-obj.location).to_track_quat('-Z', 'Y').to_euler()


def main():
    args = arguments()
    scene = bpy.context.scene
    body = bpy.data.objects['Inez_ContinuousHumanMesh_UNAPPROVED']
    arm = bpy.data.objects['InezRig_PROTOTYPE']
    for obj in scene.objects:
        if obj.type == 'MESH':
            for mod in obj.modifiers:
                if mod.type == 'SUBSURF':
                    mod.show_render = mod.show_viewport = False
            hair = any(t in obj.name for t in ('Hair', 'Curl', 'Ponytail', 'Crown', 'Flyaway', 'Framing'))
            if args.hide_hair and hair:
                obj.hide_render = True
        if obj.type == 'LIGHT':
            obj.hide_render = True
    eyes = [arm.matrix_world @ arm.data.bones['eye.'+s].head_local for s in ('L', 'R')]
    center = (eyes[0]+eyes[1])/2+Vector((0, 0, -0.035))
    yaw = math.radians(args.yaw)
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 24
    scene.cycles.use_denoising = False
    scene.render.resolution_x = scene.render.resolution_y = args.resolution
    scene.view_settings.view_transform = 'AgX'
    world = bpy.data.worlds.new('Landmark_Neutral')
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs[0].default_value = (0.35, 0.35, 0.35, 1)
    world.node_tree.nodes['Background'].inputs[1].default_value = 0.7
    scene.world = world
    for name, offset, power in (('LM_Key', (-0.8, -1.6, 0.9), 160), ('LM_Fill', (1.0, -1.4, 0.3), 90)):
        data = bpy.data.lights.new(name, 'AREA')
        data.energy, data.size = power, 1.2
        light = bpy.data.objects.new(name, data)
        scene.collection.objects.link(light)
        light.location = center+Vector(offset)
        look_at(light, center)
    camdata = bpy.data.cameras.new('LM_Camera')
    camdata.type = 'ORTHO'
    camdata.ortho_scale = args.span
    camera = bpy.data.objects.new('LM_Camera', camdata)
    scene.collection.objects.link(camera)
    scene.camera = camera
    forward = Vector((math.sin(yaw), -math.cos(yaw), 0))
    camera.location = center+forward*2.0
    look_at(camera, center)
    scene.render.filepath = args.image
    bpy.ops.render.render(write_still=True)
    detection = subprocess.run([args.python, args.detector, args.image], capture_output=True, text=True)
    if detection.returncode != 0:
        raise RuntimeError('Landmark detection failed: '+detection.stderr[-800:])
    landmarks = json.loads(detection.stdout.strip().splitlines()[-1])['landmarks']
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = body.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    verts = [body.matrix_world @ v.co for v in mesh.vertices]
    polys = [list(p.vertices) for p in mesh.polygons]
    bvh = BVHTree.FromPolygons(verts, polys)
    source_index = [d.value for d in body.data.attributes['makehuman_source_index'].data]
    right = Vector((math.cos(yaw), math.sin(yaw), 0))
    up = Vector((0, 0, 1))
    mapped = {}
    for k, (u, v, *_rest) in enumerate(landmarks):
        world = center+right*((u/args.resolution-0.5)*args.span)+up*((0.5-v/args.resolution)*args.span)
        hit, normal, face, distance = bvh.ray_cast(world+forward*1.0, -forward, 3.0)
        if hit is None:
            continue
        nearest = min(polys[face], key=lambda i: (verts[i]-hit).length)
        mapped[k] = {'pixel': [u, v], 'vertex': nearest, 'source_index': source_index[nearest],
                     'hit_world': list(hit), 'vertex_world': list(verts[nearest])}
    evaluated.to_mesh_clear()
    report = {'image': args.image, 'yaw_degrees': args.yaw, 'span_m': args.span, 'resolution': args.resolution,
              'center_world': list(center), 'eye_centers_world': [list(e) for e in eyes],
              'landmark_count': len(landmarks), 'mapped_count': len(mapped), 'landmarks_px': landmarks,
              'mapping': mapped, 'note': 'Detector measurement aid; not a biometric similarity score'}
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report)+'\n')
    print('LANDMARK_MAP', json.dumps({'mapped': len(mapped), 'output': args.output}))


if __name__ == '__main__':
    main()
