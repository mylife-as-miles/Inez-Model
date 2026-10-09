"""v04 eye materials, brows and lashes on the actual fitted head.

v03's brow tubes sat ~0.4 IPD above the pupils (higher than original B's
~0.2-0.34 IPD band) and were too sparse to read; the transmissive cornea
rendered white in WebGL. v04 paints the brow mass into the skin (see
model_materials_v04.brow_field) and adds matching 3D brow hairs inside that
band, uses a clear alpha-blended cornea and a muted green-hazel iris.
"""
import math

import bpy
import numpy as np
from mathutils import Vector

from model_face import face_front_surface
from model_geometry import mesh_object, tubes, skin_rigid, skin_source_nearest
from model_materials import material
from model_materials_v04 import iris_pbr_v04, clear_cornea_v04, sclera_v04
from model_source import joint_point

IRIS_RADIUS = 0.054


def _replace_mesh(obj, points, faces, uvs, transform, material_):
    mesh = bpy.data.meshes.new(obj.name+'_v04')
    mesh.from_pydata([transform(tuple(p)) for p in points], [], faces)
    mesh.update()
    layer = mesh.uv_layers.new(name='Eye_UV')
    for poly in mesh.polygons:
        poly.use_smooth = True
        for corner, li in enumerate(poly.loop_indices):
            layer.data[li].uv = uvs[mesh.loops[li].vertex_index]
    mesh.materials.append(material_)
    old = obj.data
    obj.data = mesh
    bpy.data.meshes.remove(old)
    for mod in list(obj.modifiers):
        if mod.type == 'SUBSURF':
            obj.modifiers.remove(mod)


def rebuild_eye(eye, iris, center, radius, transform, sclera, irismat, bone, rings=20, segments=40):
    """Sclera sphere open over the iris, a slightly concave recessed iris disk
    (pupil in its texture) and vertex groups kept on the real eye bone."""
    theta0 = math.asin(min(0.95, IRIS_RADIUS/radius))
    points, faces, uvs = [], [], []
    for r in range(rings+1):
        theta = theta0+(math.pi-theta0)*r/rings
        for k in range(segments):
            a = 2*math.pi*k/segments
            d = np.array([math.sin(theta)*math.cos(a), math.sin(theta)*math.sin(a), math.cos(theta)])
            points.append(center+d*radius)
            uvs.append((k/segments, r/rings))
    for r in range(rings):
        for k in range(segments):
            k2 = (k+1) % segments
            faces.append((r*segments+k, r*segments+k2, (r+1)*segments+k2, (r+1)*segments+k))
    _replace_mesh(eye, points, faces, uvs, transform, sclera)
    plane = radius*math.cos(theta0)
    ipoints, ifaces, iuvs = [], [], []
    iris_rings = 6
    for r in range(iris_rings+1):
        rr = IRIS_RADIUS*r/iris_rings
        depth = plane-0.004+0.003*(rr/IRIS_RADIUS)**2
        for k in range(segments):
            a = 2*math.pi*k/segments
            ipoints.append(center+np.array([rr*math.cos(a), rr*math.sin(a), depth]))
            iuvs.append((0.5+0.5*(rr/IRIS_RADIUS)*math.cos(a), 0.5+0.5*(rr/IRIS_RADIUS)*math.sin(a)))
    for r in range(iris_rings):
        for k in range(segments):
            k2 = (k+1) % segments
            ifaces.append((r*segments+k, (r+1)*segments+k, (r+1)*segments+k2, r*segments+k2))
    _replace_mesh(iris, ipoints, ifaces, iuvs, transform, irismat)
    for obj in (eye, iris):
        # Mesh weights live in the replaced mesh data: rebind every vertex.
        group = obj.vertex_groups.get(bone) or obj.vertex_groups.new(name=bone)
        group.add(list(range(len(obj.data.vertices))), 1.0, 'REPLACE')
        obj['eye_status'] = 'v04 open-front sclera / recessed iris; rigid to the real eye bone'



def make_cornea_v04(side, center, radius, transform, arm):
    mat = clear_cornea_v04(side)
    points, faces = [], []
    rings, segments = 9, 40
    for row in range(rings):
        angle = .002+.678*row/(rings-1)
        for k in range(segments):
            a = 2*math.pi*k/segments
            rr = radius*math.sin(angle)
            points.append((center[0]+rr*math.cos(a), center[1]+rr*math.sin(a),
                           center[2]+radius*math.cos(angle)+.0035*math.exp(-(angle/.34)**2)))
    for row in range(rings-1):
        for k in range(segments):
            nxt = (k+1) % segments
            faces.append((row*segments+k, row*segments+nxt, (row+1)*segments+nxt, (row+1)*segments+k))
    obj = mesh_object('Inez_Cornea_'+side, points, faces, transform, mat)
    skin_rigid(obj, arm, 'eye.'+side)
    obj['eye_status'] = 'Clear alpha-blended corneal dome over separate iris/pupil and sclera'
    return obj


def build_face_v04(body, points, uv, groups, rig, weights, transform, arm, directory):
    irismat = iris_pbr_v04(directory)
    sclera = sclera_v04(directory)
    # material() colors are Blender linear values (textures are sRGB):
    # brows sRGB ~(0.20,0.14,0.10), lashes sRGB ~(0.10,0.07,0.06).
    browmat = material('Inez_DenseNaturalBrownBrows', (.033, .017, .010), .72)
    lashmat = material('Inez_NaturalBrownLashes', (.010, .006, .005), .70)
    tearmat = material('Inez_SubtlePinkTearline', (.62, .40, .37), .25)
    objects = []
    eye_l = joint_point(points, rig, rig['bones']['eye.L']['head'])
    eye_r = joint_point(points, rig, rig['bones']['eye.R']['head'])
    ipd = abs(eye_l[0]-eye_r[0])
    eye_report = {}
    for side in ('L', 'R'):
        eye = bpy.data.objects.get('EyeGeometry_'+side) or bpy.data.objects.get('Inez_Eyeball_'+side)
        iris = bpy.data.objects.get('IrisQA_'+side) or bpy.data.objects.get('Inez_Iris_'+side)
        pupil = bpy.data.objects.get('PupilQA_'+side) or bpy.data.objects.get('Inez_Pupil_'+side)
        if eye is None or iris is None:
            raise RuntimeError('Fitted source eye geometry missing')
        ids = {i for face in groups['helper-'+side.lower()+'-eye'] for i, t in face}
        center = np.asarray(joint_point(points, rig, rig['bones']['eye.'+side]['head']))
        radius = float(np.median([np.linalg.norm(np.asarray(points[i])-center) for i in ids]))
        # Replace the low-poly helper (its unsubdivided front faces covered the
        # iris in the GLB) with an open-front sclera, recessed iris and cornea.
        rebuild_eye(eye, iris, center, radius, transform, sclera, irismat, 'eye.'+side)
        eye.name = 'Inez_Eyeball_'+side
        iris.name = 'Inez_Iris_'+side
        if pupil is not None:
            bpy.data.objects.remove(pupil, do_unlink=True)
        objects.append(make_cornea_v04(side, center, radius+.0045, transform, arm))
        eye_report[side] = {'eyeball_radius_source_units': radius, 'iris_radius_source_units': IRIS_RADIUS}
    project = face_front_surface(body, transform)
    rng = np.random.default_rng(2451)
    ey = eye_l[1]
    for side, sign in (('L', 1), ('R', -1)):
        paths, radii = [], []
        for k in range(330):
            u = rng.uniform(-0.02, 1.0)
            ax = 0.17*ipd+u*0.82*ipd
            middle = ey+ipd*(0.255+0.045*math.exp(-((u-0.62)/0.30)**2)-0.05*max(0.0, u-0.80))
            half = ipd*(0.060-0.032*max(0.0, u)**1.4)
            y = middle+rng.uniform(-1, 1)*half*0.95
            length = ipd*rng.uniform(0.045, 0.075)*(1-0.3*u)
            # Inner hairs rise, outer hairs lie along the brow toward the tail.
            angle = math.radians(70-55*u+rng.normal(0, 8))
            path = []
            for s in np.linspace(0, 1, 5):
                xx = sign*(ax+length*s*math.cos(angle))
                yy = y+length*s*math.sin(angle)-0.004*s*s
                path.append(project(xx, yy, .006+.004*math.sin(math.pi*s)))
            paths.append(path)
            radii.append(rng.uniform(.0018, .0028))
        brow = tubes('Inez_Brows_'+side, paths, radii, transform, browmat, sides=3)
        skin_source_nearest(brow, arm, points, weights, transform)
        objects.append(brow)
        upperids = [6847, 6844, 6841, 6838, 6785, 6784, 6790, 6793, 6796, 6799, 6802]
        lowerids = [6847, 6837, 6834, 6831, 6828, 6825, 6822, 6819, 6816, 6814, 6802]
        if sign < 0:
            source = np.asarray(points[:13380])

            def mirror(i):
                target = np.asarray(points[i])*np.array([-1, 1, 1])
                return int(np.argmin(np.sum((source-target)**2, axis=1)))
            upperids = [mirror(i) for i in upperids]
            lowerids = [mirror(i) for i in lowerids]
        for kind, ids, bone in (('Upper', upperids, 'orbicularis03.'+side), ('Lower', lowerids, 'orbicularis04.'+side)):
            line = [Vector(points[i]) for i in ids]
            paths, radii = [], []
            count = 60 if kind == 'Upper' else 30
            for value in np.linspace(.10, len(line)-1-.15, count):
                index = int(value)
                t = value-index
                p = line[index].lerp(line[min(index+1, len(line)-1)], t)
                length = (.040 if kind == 'Upper' else .022)*rng.uniform(.72, 1.10)
                direction = Vector((sign*(.06+value/len(line)*.27), .68 if kind == 'Upper' else -.49, .75)).normalized()
                paths.append([tuple(p+direction*length*s+Vector((0, -.006*s*s, .007*math.sin(math.pi*s))))
                              for s in np.linspace(0, 1, 6)])
                radii.append(.0024 if kind == 'Upper' else .0012)
            lash = tubes('Inez_Lashes'+kind+'_'+side, paths, radii, transform, lashmat, sides=3)
            skin_rigid(lash, arm, bone)
            objects.append(lash)
        tear = tubes('Inez_Tearline_'+side, [[tuple(Vector(points[i])+Vector((0, .002, .005))) for i in lowerids]],
                     .0032, transform, tearmat, sides=4)
        skin_rigid(tear, arm, 'orbicularis04.'+side)
        objects.append(tear)
    return objects, {'ipd_source_units': ipd, 'brow_band_ipd_above_pupil': [0.19, 0.34], 'eyes': eye_report}
