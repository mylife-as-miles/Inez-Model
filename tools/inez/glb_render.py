"""Inspection renders of a source GLB exactly as delivered (never modified or saved).

    blender -b --python tools/inez/glb_render.py -- --glb FILE.glb --output DIR --label "ASSET A" \
        [--views overview|face|all] [--samples 32] [--resolution 1000]

The GLB is imported with Blender's glTF importer (+Y up -> +Z up) and left in
place; cameras and lights are scaled to its bounding box so normalized
generator units (about 1 unit tall) frame like real metres. Views:
  overview  body front/back/left/right/three-quarter + top
  face      face front/left/right/three-quarter (head located from the
            mesh's upper silhouette, framed by its width)
  wire      face and torso wireframe (Cycles wireframe shader over clay)
  material  unlit base colour, roughness channel, clay+normal map, clay only
Every image carries an in-frame label naming the asset and the view.
"""
import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scan_common import emission_material, look_at


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('--glb', default='')
    parser.add_argument('--output', required=True)
    parser.add_argument('--label', required=True)
    parser.add_argument('--views', default='all')
    parser.add_argument('--samples', type=int, default=32)
    parser.add_argument('--resolution', type=int, default=1000)
    parser.add_argument('--yaw-offset', type=float, default=0.0,
                        help='degrees added to every view so yaw 0 looks at the character\'s face')
    parser.add_argument('--blend-objects', default='', help='render these objects of an opened .blend instead of importing --glb')
    parser.add_argument('--body-frame', default='', help='cx,cy,cz,span: fixed full-body framing for comparisons')
    parser.add_argument('--face-probe-fraction', type=float, default=0.25,
                        help='upper fraction of the height rendered to find the face with landmarks')
    return parser.parse_args(sys.argv[sys.argv.index('--')+1:])


class Rig:
    def __init__(self, scene, samples, resolution, size):
        self.scene, self.size = scene, size
        scene.render.engine = 'CYCLES'
        scene.cycles.samples = samples
        scene.cycles.use_denoising = True
        scene.render.resolution_x = scene.render.resolution_y = resolution
        scene.view_settings.view_transform = 'AgX'
        world = bpy.data.worlds.new('Audit_World')
        world.use_nodes = True
        world.node_tree.nodes['Background'].inputs[0].default_value = (0.42, 0.42, 0.42, 1)
        world.node_tree.nodes['Background'].inputs[1].default_value = 0.6
        scene.world = world
        self.lights = []
        for name, power in (('AuditKey', 1.0), ('AuditFill', 0.35), ('AuditRim', 0.6)):
            data = bpy.data.lights.new(name, 'AREA')
            data.energy = power*120*size**2
            data.size = 0.6*size
            light = bpy.data.objects.new(name, data)
            scene.collection.objects.link(light)
            self.lights.append(light)
        cam = bpy.data.cameras.new('AuditCam')
        cam.type = 'ORTHO'
        self.camera = bpy.data.objects.new('AuditCam', cam)
        scene.collection.objects.link(self.camera)
        scene.camera = self.camera
        curve = bpy.data.curves.new('AuditLabel', 'FONT')
        self.label = bpy.data.objects.new('AuditLabel', curve)
        scene.collection.objects.link(self.label)
        curve.materials.append(emission_material('AuditLabelInk', (1.0, 0.82, 0.25), 1.2))

    def render(self, center, span, yaw, path, text, pitch=0.0):
        center = Vector(center)
        r, p = math.radians(yaw), math.radians(pitch)
        forward = Vector((math.sin(r)*math.cos(p), -math.cos(r)*math.cos(p), math.sin(p)))
        d = 3*self.size
        self.camera.location = center+forward*d
        look_at(self.camera, center)
        self.camera.data.ortho_scale = span
        self.camera.data.clip_end = 8*self.size
        c, s = math.cos(r), math.sin(r)
        for light, (dx, dy, dz) in zip(self.lights, [(-1.1, -1.5, 1.1), (1.4, -1.1, 0.3), (0.5, 1.5, 1.1)]):
            light.location = center+Vector((dx*c-dy*s, dx*s+dy*c, dz))*self.size
            look_at(light, center)
        right = Vector((math.cos(r), math.sin(r), 0))
        up = forward.cross(right).normalized()*-1 if pitch else Vector((0, 0, 1))
        self.label.data.body = text
        self.label.data.size = span*0.028
        self.label.location = center-right*span*0.48-up*span*0.48+forward*d*0.5
        self.label.rotation_euler = self.camera.rotation_euler
        self.scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        print('AUDIT_RENDER', path, flush=True)


def locate_face(rig, meshes, co, lo, hi, size, args, out):
    """Find the face with MediaPipe on a probe render and lift eye corners/chin to 3D."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    verts, polys = [], []
    for obj in meshes:
        mesh = obj.evaluated_get(depsgraph).to_mesh()
        base = len(verts)
        verts += [obj.matrix_world @ v.co for v in mesh.vertices]
        polys += [[base+i for i in p.vertices] for p in mesh.polygons]
        obj.evaluated_get(depsgraph).to_mesh_clear()
    bvh = BVHTree.FromPolygons(verts, polys)
    frac = args.face_probe_fraction
    upper = co[co[:, 2] > hi[2]-size*frac]
    center = Vector((float(np.median(upper[:, 0])), float(np.median(upper[:, 1])), float(hi[2]-size*frac/2)))
    span = size*frac*1.05
    probe = out/'_face_probe.png'
    yaw = math.radians(args.yaw_offset)
    rig.label.data.body = ''
    rig.render(center, span, args.yaw_offset, probe, '')
    run = subprocess.run(['python3', str(Path(__file__).resolve().parent/'face_landmarks.py'), str(probe)],
                         capture_output=True, text=True)
    data = json.loads(run.stdout.strip().splitlines()[-1]) if run.stdout.strip() else {'face': False}
    probe.unlink(missing_ok=True)
    if not data.get('face'):
        raise SystemExit('No face found in the probe render; pass a different --yaw-offset')
    forward = Vector((math.sin(yaw), -math.cos(yaw), 0))
    right = Vector((math.cos(yaw), math.sin(yaw), 0))
    res = args.resolution

    def lift(k):
        u, v = data['landmarks'][k][:2]
        origin = center+right*((u/res-0.5)*span)+Vector((0, 0, (0.5-v/res)*span))
        hit = bvh.ray_cast(origin+forward*3*size, -forward, 6*size)[0]
        return hit if hit is not None else origin
    outer = (lift(33)-lift(263)).length
    eyes = (lift(33)+lift(263))/2
    chin = lift(152)
    face_center = (eyes+chin)/2+Vector((0, 0, (eyes-chin).length*0.25))
    return tuple(face_center), outer*3.6


def main():
    args = arguments()
    if args.blend_objects:
        keep = [n for n in args.blend_objects.split(',') if n]
        for obj in bpy.context.scene.objects:
            if obj.type in ('LIGHT', 'CAMERA') or obj.type == 'FONT':
                obj.hide_render = True
            if obj.type == 'MESH':
                obj.hide_render = not any(obj.name.startswith(k) for k in keep)
                for mod in obj.modifiers:
                    if mod.type == 'SUBSURF':
                        mod.show_render = False
        meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH' and not o.hide_render]
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=str(Path(args.glb).resolve()))
        meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    co = np.concatenate([np.array([o.matrix_world @ v.co for v in o.data.vertices]) for o in meshes])
    co = co[np.isfinite(co).all(1)]
    lo, hi = co.min(0), co.max(0)
    size = float(hi[2]-lo[2])
    scene = bpy.context.scene
    rig = Rig(scene, args.samples, args.resolution, size)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    views = args.views
    body_center = ((lo[0]+hi[0])/2, (lo[1]+hi[1])/2, (lo[2]+hi[2])/2)
    body_span = max(hi[2]-lo[2], hi[0]-lo[0], hi[1]-lo[1])*1.04
    if args.body_frame:
        cx, cy, cz, sp = (float(v) for v in args.body_frame.split(','))
        body_center, body_span = (cx, cy, cz), sp
    tag = args.label
    head_center, head_span = (body_center, body_span*0.2)
    if views != 'overview':
        head_center, head_span = locate_face(rig, meshes, co, lo, hi, size, args, out)
    if views in ('overview', 'all'):
        for name, yaw in (('body_front', 0), ('body_three_quarter', 35), ('body_left', 90), ('body_back', 180), ('body_right', -90)):
            rig.render(body_center, body_span, yaw+args.yaw_offset, out/f'{name}.png', f'{tag} - {name} (source GLB as delivered)')
    if views in ('face', 'all'):
        for name, yaw in (('face_front', 0), ('face_three_quarter', 35), ('face_left', 90), ('face_right', -90)):
            rig.render(head_center, head_span, yaw+args.yaw_offset, out/f'{name}.png', f'{tag} - {name} (source GLB as delivered)')
    if views in ('wire', 'all', 'material'):
        materials = {o.name: list(o.data.materials) for o in meshes}
        node_sets = []
        for mat in {m for ms in materials.values() for m in ms if m}:
            nodes = mat.node_tree.nodes
            bsdf = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')
            out_node = next(n for n in nodes if n.type == 'OUTPUT_MATERIAL')
            node_sets.append((mat, bsdf, out_node))
        if views in ('wire', 'all'):
            for mat, bsdf, out_node in node_sets:
                links = mat.node_tree.links
                wire = mat.node_tree.nodes.new('ShaderNodeWireframe')
                wire.use_pixel_size = True
                wire.inputs['Size'].default_value = 0.6
                clay = mat.node_tree.nodes.new('ShaderNodeBsdfDiffuse')
                clay.inputs['Color'].default_value = (0.55, 0.55, 0.55, 1)
                dark = mat.node_tree.nodes.new('ShaderNodeEmission')
                dark.inputs['Color'].default_value = (0.02, 0.05, 0.12, 1)
                mix = mat.node_tree.nodes.new('ShaderNodeMixShader')
                links.new(wire.outputs['Fac'], mix.inputs['Fac'])
                links.new(clay.outputs['BSDF'], mix.inputs[1])
                links.new(dark.outputs['Emission'], mix.inputs[2])
                links.new(mix.outputs['Shader'], out_node.inputs['Surface'])
            rig.render(head_center, head_span*0.6, args.yaw_offset, out/'wire_face_front.png', f'{tag} - wireframe face (triangles as delivered)')
            rig.render(body_center, body_span*0.35, args.yaw_offset, out/'wire_torso_front.png', f'{tag} - wireframe torso')
            for mat, bsdf, out_node in node_sets:
                mat.node_tree.links.new(bsdf.outputs['BSDF'], out_node.inputs['Surface'])
        if views in ('material', 'all'):
            for mat, bsdf, out_node in node_sets:
                nodes, links = mat.node_tree.nodes, mat.node_tree.links
                base = bsdf.inputs['Base Color'].links[0].from_node if bsdf.inputs['Base Color'].links else None
                emit = nodes.new('ShaderNodeEmission')
                if base:
                    links.new(base.outputs['Color'], emit.inputs['Color'])
                links.new(emit.outputs['Emission'], out_node.inputs['Surface'])
            scene.view_settings.view_transform = 'Standard'
            rig.render(head_center, head_span, args.yaw_offset, out/'material_basecolor_face.png', f'{tag} - unlit base colour (face)')
            rig.render(body_center, body_span, args.yaw_offset, out/'material_basecolor_body.png', f'{tag} - unlit base colour (body)')
            scene.view_settings.view_transform = 'AgX'
            for mat, bsdf, out_node in node_sets:
                nodes, links = mat.node_tree.nodes, mat.node_tree.links
                # The importer splits metallic-roughness with a Separate Color
                # node; follow the actual socket (green = roughness).
                rough = bsdf.inputs['Roughness'].links[0].from_socket if bsdf.inputs['Roughness'].links else None
                emit = nodes.new('ShaderNodeEmission')
                if rough:
                    links.new(rough, emit.inputs['Color'])
                links.new(emit.outputs['Emission'], out_node.inputs['Surface'])
            scene.view_settings.view_transform = 'Standard'
            rig.render(head_center, head_span, args.yaw_offset, out/'material_roughness_face.png', f'{tag} - roughness channel (face)')
            scene.view_settings.view_transform = 'AgX'
            for mat, bsdf, out_node in node_sets:
                nodes, links = mat.node_tree.nodes, mat.node_tree.links
                bsdf.inputs['Base Color'].default_value = (0.55, 0.55, 0.55, 1)
                for link in list(bsdf.inputs['Base Color'].links):
                    links.remove(link)
                links.new(bsdf.outputs['BSDF'], out_node.inputs['Surface'])
            rig.render(head_center, head_span, 35+args.yaw_offset, out/'material_clay_normalmap_face.png', f'{tag} - clay + source normal map')
            for mat, bsdf, out_node in node_sets:
                for link in list(bsdf.inputs['Normal'].links):
                    mat.node_tree.links.remove(link)
            rig.render(head_center, head_span, 35+args.yaw_offset, out/'material_clay_geometry_face.png', f'{tag} - clay geometry only (no normal map)')
            rig.render(body_center, body_span, 35+args.yaw_offset, out/'material_clay_geometry_body.png', f'{tag} - clay geometry only')
    (out/'bounds.txt').write_text(f'min {lo.tolist()}\nmax {hi.tolist()}\nhead_center {head_center}\n')


if __name__ == '__main__':
    main()
