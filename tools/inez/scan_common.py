"""Shared Blender helpers for the scan-reconstruction passes (import, align, wrap, bake).

Every scan-stage render goes through `render_views` so that the untouched
source, each deformation pass and the wrapped Inez head are lit and framed the
same way. A label is rendered into the frame (not added afterwards) so a pass
image cannot be mistaken for another stage.
"""
import math
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
CHARACTER = ROOT/'assets/characters/inez'
SCAN_DIR = CHARACTER/'scans/source/ten24_sample/extracted/OBJ Package'

# name: (yaw degrees, camera side). Yaw 90 looks at the character's left side.
VIEWS = {'front': 0, 'three_quarter': 35, 'left': 90, 'right': -90, 'three_quarter_right': -35}


def look_at(obj, target):
    obj.rotation_euler = (Vector(target)-obj.location).to_track_quat('-Z', 'Y').to_euler()


def import_obj(path, name):
    before = set(bpy.data.objects)
    bpy.ops.wm.obj_import(filepath=str(path), forward_axis='NEGATIVE_Z', up_axis='Y')
    new = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
    if len(new) != 1:
        raise RuntimeError(f'Expected one mesh from {path}, got {[o.name for o in new]}')
    obj = new[0]
    obj.name = obj.data.name = name
    return obj


def keep_faces(obj, predicate):
    """Delete faces whose vertex positions fail `predicate(list_of_world_coords)`; drop loose verts.

    The original vertex order of kept vertices is recorded in the int attribute
    `scan_vertex_index` so every derived value traces back to the source OBJ.
    """
    mesh = obj.data
    if 'scan_vertex_index' not in mesh.attributes:
        attr = mesh.attributes.new('scan_vertex_index', 'INT', 'POINT')
        attr.data.foreach_set('value', list(range(len(mesh.vertices))))
    bm = bmesh.new()
    bm.from_mesh(mesh)
    doomed = [f for f in bm.faces if not predicate([obj.matrix_world @ v.co for v in f.verts])]
    bmesh.ops.delete(bm, geom=doomed, context='FACES_ONLY')
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context='VERTS')
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()


def clay_material(name, normal_image=None, strength=1.0, color=(0.50, 0.48, 0.46), uv_map=None):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Roughness'].default_value = 0.55
    if normal_image is not None:
        tex = nodes.new('ShaderNodeTexImage')
        tex.image = normal_image
        tex.image.colorspace_settings.name = 'Non-Color'
        tex.interpolation = 'Cubic'
        nmap = nodes.new('ShaderNodeNormalMap')
        nmap.inputs['Strength'].default_value = strength
        if uv_map:
            nmap.uv_map = uv_map
            uv = nodes.new('ShaderNodeUVMap')
            uv.uv_map = uv_map
            links.new(uv.outputs['UV'], tex.inputs['Vector'])
        links.new(tex.outputs['Color'], nmap.inputs['Color'])
        links.new(nmap.outputs['Normal'], bsdf.inputs['Normal'])
    return mat


def emission_material(name, color, strength=1.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    out = nodes.new('ShaderNodeOutputMaterial')
    em = nodes.new('ShaderNodeEmission')
    em.inputs['Color'].default_value = (*color, 1)
    em.inputs['Strength'].default_value = strength
    mat.node_tree.links.new(em.outputs['Emission'], out.inputs['Surface'])
    return mat


class Studio:
    """Neutral review rig: grey world, key/fill/rim area lights that follow the view, ortho camera."""

    def __init__(self, scene, samples=32, resolution=900):
        self.scene = scene
        scene.render.engine = 'CYCLES'
        scene.cycles.samples = samples
        scene.cycles.use_denoising = True
        scene.render.resolution_x = scene.render.resolution_y = resolution
        scene.render.resolution_percentage = 100
        scene.render.film_transparent = False
        scene.view_settings.view_transform = 'AgX'
        world = bpy.data.worlds.new('Scan_Review_Neutral')
        world.use_nodes = True
        world.node_tree.nodes['Background'].inputs[0].default_value = (0.42, 0.42, 0.42, 1)
        world.node_tree.nodes['Background'].inputs[1].default_value = 0.55
        scene.world = world
        self.lights = []
        for name, power, size in (('ScanKey', 26, 0.5), ('ScanFill', 9, 0.5), ('ScanRim', 16, 0.35)):
            data = bpy.data.lights.new(name, 'AREA')
            data.energy, data.size = power, size
            light = bpy.data.objects.new(name, data)
            scene.collection.objects.link(light)
            self.lights.append(light)
        camdata = bpy.data.cameras.new('ScanCamera')
        camdata.type = 'ORTHO'
        self.camera = bpy.data.objects.new('ScanCamera', camdata)
        scene.collection.objects.link(self.camera)
        scene.camera = self.camera
        self.label = None

    def set_label(self, text):
        if self.label is None:
            curve = bpy.data.curves.new('ScanLabel', 'FONT')
            self.label = bpy.data.objects.new('ScanLabel', curve)
            self.scene.collection.objects.link(self.label)
            curve.materials.append(emission_material('ScanLabelInk', (1.0, 0.82, 0.25), 1.2))
            curve.align_x = 'LEFT'
            curve.align_y = 'BOTTOM'
            plate = bpy.data.meshes.new('ScanLabelPlate')
            # Unit plate: x spans the text width, y one font size (scaled per render).
            plate.from_pydata([(-0.03, -0.3, -0.001), (1.03, -0.3, -0.001), (1.03, 1.15, -0.001), (-0.03, 1.15, -0.001)], [], [(0, 1, 2, 3)])
            plate.materials.append(emission_material('ScanLabelPlateInk', (0.02, 0.02, 0.02), 1.0))
            backing = bpy.data.objects.new('ScanLabelPlate', plate)
            self.scene.collection.objects.link(backing)
            backing.parent = self.label
        self.label.data.body = text

    def render(self, center, span, yaw_degrees, path, distance=1.5):
        center = Vector(center)
        r = math.radians(yaw_degrees)
        forward = Vector((math.sin(r), -math.cos(r), 0))
        self.camera.location = center+forward*distance
        look_at(self.camera, center)
        self.camera.data.ortho_scale = span
        self.camera.data.clip_end = distance*3
        c, s = math.cos(r), math.sin(r)
        for light, (dx, dy, dz) in zip(self.lights, [(-0.55, -0.75, 0.55), (0.70, -0.55, 0.15), (0.25, 0.75, 0.55)]):
            light.location = center+Vector((dx*c-dy*s, dx*s+dy*c, dz))
            look_at(light, center)
        if self.label is not None:
            right = Vector((math.cos(r), math.sin(r), 0))
            size = span*0.030
            self.label.data.size = size
            self.label.children[0].scale = (len(self.label.data.body)*size*0.56, size, 1)
            self.label.location = center-right*span*0.48-Vector((0, 0, span*0.475))+forward*0.5
            self.label.rotation_euler = (math.pi/2, 0, r)
        self.scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        print('SCAN_RENDER', path, flush=True)
