"""Neutral Cycles review renders of an actual Inez .blend (runtime geometry).

blender -b SOURCE.blend --python tools/inez/review_render.py -- \
    --output DIR [--views front,left,back,three_quarter,portrait_front,...]
    [--samples 24] [--resolution 900] [--frame N] [--action Idle]

Subdivision modifiers are disabled so the images show the same base mesh the
GLB exports. Lighting is a fixed neutral studio rig. This writes only into
--output and never saves the .blend.
"""
import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--views', default='front,left,back,three_quarter,portrait_front,portrait_three_quarter,portrait_left')
    parser.add_argument('--samples', type=int, default=24)
    parser.add_argument('--resolution', type=int, default=900)
    parser.add_argument('--action', default='')
    parser.add_argument('--frame', type=int, default=1)
    parser.add_argument('--shape', action='append', default=[], help='NAME=VALUE shape key override on every mesh that has it')
    parser.add_argument('--hide', default='', help='comma-separated name substrings to hide (debug)')
    parser.add_argument('--only', default='', help='comma-separated name substrings to keep (debug)')
    return parser.parse_args(sys.argv[sys.argv.index('--')+1:])


def look_at(obj, target):
    obj.rotation_euler = (Vector(target)-obj.location).to_track_quat('-Z', 'Y').to_euler()


def main():
    args = arguments()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    hide = [h for h in args.hide.split(',') if h]
    only = [h for h in args.only.split(',') if h]
    for obj in scene.objects:
        if obj.type == 'MESH' and (any(h in obj.name for h in hide) or (only and not any(h in obj.name for h in only))):
            obj.hide_render = True
        if obj.type == 'MESH':
            for mod in obj.modifiers:
                if mod.type == 'SUBSURF':
                    mod.show_render = False
                    mod.show_viewport = False
            for item in args.shape:
                name, value = item.split('=')
                keys = obj.data.shape_keys
                if keys and name in keys.key_blocks:
                    keys.key_blocks[name].value = float(value)
        if obj.type == 'LIGHT':
            obj.hide_render = True
    arm = next((o for o in scene.objects if o.type == 'ARMATURE'), None)
    if arm and args.action:
        arm.animation_data_create()
        arm.animation_data.action = bpy.data.actions[args.action]
    scene.frame_set(args.frame)
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = False
    scene.render.resolution_x = scene.render.resolution_y = args.resolution
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.view_settings.view_transform = 'AgX'
    world = bpy.data.worlds.new('Review_Neutral')
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs[0].default_value = (0.42, 0.42, 0.42, 1)
    world.node_tree.nodes['Background'].inputs[1].default_value = 0.55
    scene.world = world
    lights = []
    for name, location, power, size in [('Review_Key', (-1.6, -2.2, 2.4), 420, 1.6),
                                        ('Review_Fill', (2.0, -1.6, 1.4), 170, 1.6),
                                        ('Review_Rim', (0.6, 2.2, 2.2), 260, 1.2)]:
        data = bpy.data.lights.new(name, 'AREA')
        data.energy, data.size = power, size
        light = bpy.data.objects.new(name, data)
        scene.collection.objects.link(light)
        light.location = location
        look_at(light, (0, 0, 1.0))
        lights.append(light)
    camdata = bpy.data.cameras.new('Review_Camera')
    camdata.type = 'ORTHO'
    camera = bpy.data.objects.new('Review_Camera', camdata)
    scene.collection.objects.link(camera)
    scene.camera = camera
    views = {
        'front': (0, 0.90, 1.95), 'left': (90, 0.90, 1.95), 'back': (180, 0.90, 1.95),
        'right': (-90, 0.90, 1.95), 'three_quarter': (35, 0.90, 1.95),
        'portrait_front': (0, 1.585, 0.42), 'portrait_three_quarter': (35, 1.585, 0.42),
        'portrait_left': (90, 1.585, 0.42), 'portrait_right': (-90, 1.585, 0.42),
        'portrait_back': (180, 1.585, 0.42), 'portrait_a1_yaw25': (25, 1.585, 0.42),
        'portrait_a2_yaw13': (13, 1.585, 0.42),
        'torso_front': (0, 1.18, 0.75), 'torso_left': (90, 1.18, 0.75), 'torso_back': (180, 1.18, 0.75),
        'legs_front': (0, 0.42, 0.95), 'legs_left': (90, 0.42, 0.95), 'feet_three_quarter': (35, 0.20, 0.55),
    }
    for name in args.views.split(','):
        angle, height, span = views[name]
        r = math.radians(angle)
        target = Vector((0, 0, height))
        camera.location = target+Vector((4*math.sin(r), -4*math.cos(r), 0))
        look_at(camera, target)
        camdata.ortho_scale = span
        # Light rig follows the camera so every view is lit from the front-left.
        for light, (dx, dy, dz) in zip(lights, [(-1.6, -2.2, 2.4), (2.0, -1.6, 1.4), (0.6, 2.2, 2.2)]):
            c, s = math.cos(r), math.sin(r)
            light.location = (dx*c-dy*s, dx*s+dy*c, dz)
            look_at(light, (0, 0, height))
        scene.render.filepath = str(out/(name+'.png'))
        bpy.ops.render.render(write_still=True)
        print('REVIEW_RENDER', scene.render.filepath, flush=True)


if __name__ == '__main__':
    main()
