"""Blender head-first character fitting from continuous licensed topology.

Usage only AFTER explicit root approval:
  blender -b -t 4 --python tools/inez/model_build.py -- --config ... --gate ...

This first implementation creates a clay fitting prototype, not final Inez.
The original reference images remain packed into a non-rendering collection.
It deliberately does not author detailed face textures or a dressed body yet.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import argparse
import json
import math
import bpy
from mathutils import Vector
from model_source import (CHARACTER, SOURCE, read_obj, rig_sources,
                          shape_vertices, fit_vertices, joint_point)


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    parser.add_argument('--gate', required=True)
    parser.add_argument('--render', action='store_true')
    return parser.parse_args(sys.argv[sys.argv.index('--')+1:])


def material(name, color, roughness=0.62):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Roughness'].default_value = roughness
    return mat


def mesh_from_group(name, faces, points, texcoords, transform, mat):
    ids = sorted({i for face in faces for i, _ in face})
    source_to_mesh = {src:mesh for mesh,src in enumerate(ids)}
    mesh = bpy.data.meshes.new(name+'_Geometry')
    mesh.from_pydata([transform(points[i]) for i in ids], [],
                     [[source_to_mesh[i] for i, _ in face] for face in faces])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    uv = mesh.uv_layers.new(name='MakeHuman_CC0_UV')
    for poly, face in zip(mesh.polygons, faces):
        poly.use_smooth = True
        for loop, (_, texidx) in zip(poly.loop_indices, face):
            uv.data[loop].uv = texcoords[texidx]
    attr = mesh.attributes.new('makehuman_source_index', 'INT', 'POINT')
    for i, src in enumerate(ids):
        attr.data[i].value = src
    obj.data.materials.append(mat)
    obj['source_license'] = 'CC0-1.0'
    obj['source_provenance'] = 'model/base-source/provenance.json'
    obj['identity_status'] = 'UNAPPROVED geometry fitting prototype'
    return obj, ids


def add_armature(points, rig, transform):
    arm = bpy.data.armatures.new('Inez_CC0_Humanoid_FacialSkeleton')
    obj = bpy.data.objects.new('InezRig_PROTOTYPE', arm)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    for name, item in rig['bones'].items():
        bone = arm.edit_bones.new(name)
        bone.head = transform(joint_point(points, rig, item['head']))
        bone.tail = transform(joint_point(points, rig, item['tail']))
        if (bone.tail-bone.head).length < 1e-5:
            bone.tail += Vector((0,0,0.002))
        # Planes record anatomically meaningful axes in the licensed source.
        plane = rig.get('planes', {}).get(item.get('rotation_plane'))
        if plane and len(plane) == 3:
            p = [Vector(transform(joint_point(points, rig, n))) for n in plane]
            normal = (p[1]-p[0]).cross(p[2]-p[0])
            if normal.length > 1e-6:
                bone.align_roll(normal)
    for name, item in rig['bones'].items():
        if item.get('parent'):
            arm.edit_bones[name].parent = arm.edit_bones[item['parent']]
    bpy.ops.object.mode_set(mode='OBJECT')
    obj.show_in_front = True
    obj['source_license'] = rig['license']
    obj['rig_status'] = 'Prototype source weights; expression/skinning tests pending'
    obj.select_set(False)
    return obj


def attach_weights(obj, source_ids, weights, arm):
    mapping = {src:i for i,src in enumerate(source_ids)}
    totals = {src:0 for src in source_ids}
    for bone, values in weights['weights'].items():
        for src, value in values:
            if src in totals:
                totals[src] += value
    for bone, values in weights['weights'].items():
        vg = obj.vertex_groups.new(name=bone)
        for src, value in values:
            if src in mapping and totals[src]>1e-8:
                vg.add([mapping[src]], value/totals[src], 'REPLACE')
    mod = obj.modifiers.new('MakeHuman_Licensed_Weights', 'ARMATURE')
    mod.object = arm
    obj.parent = arm


def subdivision(obj, level=2):
    mod = obj.modifiers.new('Editable_Quad_Subdivision', 'SUBSURF')
    mod.subdivision_type = 'CATMULL_CLARK'
    mod.levels = 1
    mod.render_levels = level


def add_eye_landmark_disks(points, rig, transform, arm, groups=None):
    """Untextured iris/pupil geometry provides gaze landmarks for clay QA."""
    iris_mat=material('CLAY_IRIS_landmark_only',(0.18,0.18,0.17),0.5)
    pupil_mat=material('CLAY_PUPIL_landmark_only',(0.025,0.025,0.025),0.35)
    for side in ('L','R'):
        center=Vector(joint_point(points,rig,rig['bones']['eye.'+side]['head']))
        # The helper sphere is not a fixed-size primitive. Derive its forward
        # extent so QA irises sit on the actual preserved fitted eye surface.
        if groups:
            ids={i for face in groups['helper-'+side.lower()+'-eye'] for i,t in face}
            radius=max(points[i][2]for i in ids)-center.z
        else:
            radius=0.157
        for kind,diskradius,mat,offset in [('Iris',0.052,iris_mat,0.002),('Pupil',0.019,pupil_mat,0.003)]:
            pts=[transform((center.x,center.y,center.z+radius+offset))]
            segments=48
            for i in range(segments):
                angle=2*math.pi*i/segments
                x=center.x+diskradius*math.cos(angle)
                y=center.y+diskradius*math.sin(angle)
                z=center.z+math.sqrt(radius*radius-diskradius*diskradius)+offset
                pts.append(transform((x,y,z)))
            mesh=bpy.data.meshes.new(kind+'QA_'+side+'_Mesh')
            mesh.from_pydata(pts,[],[(0,1+i,1+(i+1)%segments)for i in range(segments)])
            mesh.update()
            uv=mesh.uv_layers.new(name='Iris_radial_UV')
            for poly in mesh.polygons:
                for loop_index in poly.loop_indices:
                    vertex_index=mesh.loops[loop_index].vertex_index
                    if vertex_index==0:
                        uv.data[loop_index].uv=(0.5,0.5)
                    else:
                        angle=2*math.pi*(vertex_index-1)/segments
                        uv.data[loop_index].uv=(0.5+0.5*math.cos(angle),0.5+0.5*math.sin(angle))
            obj=bpy.data.objects.new(kind+'QA_'+side,mesh)
            bpy.context.collection.objects.link(obj)
            obj.data.materials.append(mat)
            for poly in mesh.polygons:poly.use_smooth=True
            vg=obj.vertex_groups.new(name='eye.'+side)
            vg.add(list(range(len(pts))),1,'REPLACE')
            mod=obj.modifiers.new('Eye_rotation','ARMATURE')
            mod.object=arm
            obj.parent=arm
            obj['material_status']='Clay landmark; no production eye appearance claim'


def reference_setup():
    collection = bpy.data.collections.new('ORIGINALS_AND_APPROVED_REFERENCE_PLANES')
    bpy.context.scene.collection.children.link(collection)
    collection.hide_render = True
    entries = [('A_ORIGINAL_FINAL_FACE_AUTHORITY', 'references/original/inez_portraits.jpg'),
               ('B_ORIGINAL_FINAL_BODY_AUTHORITY', 'references/original/inez_turnaround.jpg'),
               ('Front_approved_2D_hypothesis', 'references/approved/01_face_front_neutral.png'),
               ('Left_profile_approved_2D_hypothesis', 'references/approved/02_face_left_profile.png'),
               ('Body_front_approved_2D_hypothesis', 'references/approved/05_body_front.png')]
    for index,(name,relative) in enumerate(entries):
        path = CHARACTER/relative
        if not path.exists():
            continue
        img = bpy.data.images.load(str(path), check_existing=True)
        img.pack()
        empty = bpy.data.objects.new(name,None)
        empty.empty_display_type = 'IMAGE'
        empty.data = img
        empty.empty_display_size = 1.0
        empty.location = (index*1.2-2.4,0.8,1.4)
        empty.rotation_euler = (math.pi/2,0,0)
        empty['reference_authority'] = 'Originals outrank generated hypotheses'
        scope_path=path.with_suffix('.scope.json')
        if scope_path.exists():
            empty['MANDATORY_reference_scope']=scope_path.read_text()
        collection.objects.link(empty)
    collection.hide_viewport = True


def point_camera(camera, target):
    camera.rotation_euler=(Vector(target)-camera.location).to_track_quat('-Z','Y').to_euler()


def light(name, location, target, power, size):
    data = bpy.data.lights.new(name,'AREA')
    data.energy, data.shape, data.size = power,'DISK',size
    obj=bpy.data.objects.new(name,data)
    bpy.context.collection.objects.link(obj)
    obj.location=location
    point_camera(obj,target)
    return obj


def studio(config, transform, scale):
    scene=bpy.context.scene
    scene.render.engine='CYCLES'
    scene.cycles.samples=config.get('render_samples',48)
    # This executor's Cycles build lacks OpenImageDenoise. Real path-traced
    # samples are retained rather than failing all actual renders at save.
    scene.cycles.use_denoising=False
    scene.render.resolution_x=scene.render.resolution_y=config.get('render_resolution',768)
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG'
    scene.view_settings.view_transform='AgX'
    world=bpy.data.worlds.new('Neutral_Studio_Gray')
    world.use_nodes=True
    world.node_tree.nodes['Background'].inputs[0].default_value=(0.45,0.45,0.45,1)
    world.node_tree.nodes['Background'].inputs[1].default_value=0.5
    scene.world=world
    target=Vector(transform(config['camera_head_target_source']))
    light('Soft_Key',target+Vector((-1,-1.2,1.0)),target,90,1.0)
    light('Soft_Fill',target+Vector((1.0,-0.6,0.4)),target,55,1.0)
    light('Top_Back',target+Vector((0,0.8,0.9)),target,65,0.9)
    camdata=bpy.data.cameras.new('Head_Orthographic_Camera')
    camdata.type='ORTHO'
    camdata.ortho_scale=config['camera_head_ortho_source']*scale
    camera=bpy.data.objects.new('Head_Orthographic_Camera',camdata)
    bpy.context.collection.objects.link(camera)
    scene.camera=camera
    return camera,target


def main():
    args=arguments()
    config=json.loads(Path(args.config).read_text())
    gate=json.loads(Path(args.gate).read_text())
    if not gate.get('front_profile_body_initial_gate_passed'):
        raise RuntimeError('Actual geometry creation is blocked: explicit initial reference gate required')
    if not config.get('fit_controls'):
        raise RuntimeError('The macro source is unfitted: calibrate original-based head fitting controls before model creation')
    for reference in ('01_face_front_neutral.png','02_face_left_profile.png','05_body_front.png'):
        if not (CHARACTER/'references/approved'/reference).exists():
            raise RuntimeError('Missing initial approved modeling reference: '+reference)
    for reference in ('02_face_left_profile.scope.json','05_body_front.scope.json'):
        if not (CHARACTER/'references/approved'/reference).exists():
            raise RuntimeError('Mandatory scoped hypothesis evidence missing: '+reference)
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    source,uv,groups=read_obj()
    basis=shape_vertices(source,config['source_shape_weights'])
    fitted=fit_vertices(basis,config.get('fit_controls',[]))
    body_ids=sorted({i for f in groups['body'] for i,_ in f})
    ground=min(basis[i][1]for i in body_ids)
    height=max(basis[i][1]for i in body_ids)-ground
    scale=config['provisional_height_m']/height
    def transform(p):
        return (p[0]*scale,-p[2]*scale,(p[1]-ground)*scale)
    clay=material('CLAY_GEOMETRY_QA_no_identity_texture',(0.42,0.35,0.29))
    eyeclay=material('CLAY_EYEBALL_geometry_only',(0.68,0.65,0.60),0.42)
    body,ids=mesh_from_group('Inez_ContinuousHumanMesh_UNAPPROVED',groups['body'],basis,uv,transform,clay)
    body.shape_key_add(name='Basis_FemaleYoung_Source')
    previous_versions=config.get('previous_fit_versions',[])
    if not previous_versions and config.get('previous_fit_controls'):
        previous_versions=[{'revision':config['previous_fit_revision'],
                            'fit_controls':config['previous_fit_controls']}]
    for version in previous_versions:
        previous=fit_vertices(basis,version['fit_controls'])
        previous_key=body.shape_key_add(name='Inez_HeadFit_'+version['revision'])
        for index,src in enumerate(ids):
            previous_key.data[index].co=transform(previous[src])
        previous_key.value=0.0
    fit=body.shape_key_add(name='Inez_HeadFit_'+config['revision'])
    for index,src in enumerate(ids):
        fit.data[index].co=transform(fitted[src])
    fit.value=1.0
    rig,weights=rig_sources()
    arm=add_armature(fitted,rig,transform)
    attach_weights(body,ids,weights,arm)
    subdivision(body)
    for side in ('l','r'):
        eye,eyeids=mesh_from_group('EyeGeometry_'+side.upper(),groups['helper-'+side+'-eye'],fitted,uv,transform,eyeclay)
        vg=eye.vertex_groups.new(name='eye.'+side.upper())
        vg.add(list(range(len(eyeids))),1.0,'REPLACE')
        mod=eye.modifiers.new('Rigid_eye_bone_attachment','ARMATURE')
        mod.object=arm
        eye.parent=arm
        subdivision(eye)
    add_eye_landmark_disks(fitted,rig,transform,arm,groups)
    reference_setup()
    camera,target=studio(config,transform,scale)
    body['fit_config']=str(Path(args.config))
    body['fitting_limitations']='No claim of likeness approval; no detailed facial texture; no clothing/hair yet'
    bpy.context.scene['INEZ_STAGE']=config['stage']
    bpy.context.scene['original_authority']='Original A face, Original B dressed body'
    bpy.context.scene['provisional_height_m']=config['provisional_height_m']
    revision=config['revision']
    work=CHARACTER/'model/work'
    work.mkdir(parents=True,exist_ok=True)
    renders=CHARACTER/('renders/head_'+revision)
    renders.mkdir(parents=True,exist_ok=True)
    blend=work/('inez_head_'+revision+'.blend')
    camera.location=target+Vector((0,-2,0))
    point_camera(camera,target)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    # MakeHuman's .L joint is positive X: a left-side camera is +X.
    views={'front':0,'left_profile':90,'right_profile':-90,'three_quarter':45}
    for name,angle in views.items():
        radians=math.radians(angle)
        camera.location=target+Vector((2*math.sin(radians),-2*math.cos(radians),0))
        point_camera(camera,target)
        if args.render:
            bpy.context.scene.render.filepath=str(renders/(name+'.png'))
            bpy.ops.render.render(write_still=True)
    camera.location=target+Vector((0,-2,0))
    point_camera(camera,target)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    snapshot={
        'revision':revision,'stage':config['stage'],'blend':str(blend),
        'gate_evidence':gate,'basis_body_vertices':len(ids),'basis_body_quads':len(groups['body']),
        'uv_layer':'MakeHuman_CC0_UV','rig_bones':len(rig['bones']),
        'provisional_height_m':config['provisional_height_m'],
        'has_body_shape_key':True,'has_licensed_weights':True,
        'textures_authored':False,'dressed_body_authored':False,'identity_approved':False,
        'render_names':list(views)if args.render else [],
        'manual_sculpting_expected':'Clay renders must be critiqued; continuous mesh is only a fitting prototype',
    }
    (CHARACTER/'qa/model'/('model_head_'+revision+'_manifest.json')).write_text(json.dumps(snapshot,indent=2)+'\n')
    print('INEZ_MODEL_MANIFEST '+json.dumps(snapshot))


if __name__=='__main__':
    main()
