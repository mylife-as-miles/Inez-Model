"""Build the actual dressed skinned game asset after credible clay head review.

Run against an independently reviewed fitted head .blend. Both the initial
front/profile/body gate and actual clay-head gate must explicitly be true.
This script is not image generation and never calls a paid generator.
"""
import argparse
import sys
import json
import math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import bpy
import numpy as np
from mathutils import Vector
from model_source import (CHARACTER,read_obj,shape_vertices,fit_vertices,rig_sources,joint_point)
from model_build import point_camera,studio
from model_materials import skin_pbr
from model_clothing import build_clothing
from model_hair import build_hair
from model_face import build_face


def arguments():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',required=True)
    parser.add_argument('--gate',required=True)
    parser.add_argument('--head-gate',required=True)
    parser.add_argument('--render',action='store_true')
    parser.add_argument('--texture-resolution',type=int,default=2048)
    return parser.parse_args(sys.argv[sys.argv.index('--')+1:])


def fit_body_pose(points,config):
    result=[list(p)for p in points]
    angle=math.radians(config.get('body_arm_a_pose_degrees',18)-43)
    for i,p in enumerate(points):
        x,y,z=p
        if y<.35 and .25<abs(x)<2.65:
            correction=.65*max(0,min(1,(.3-y)/7.8))
            result[i][0]-=math.copysign(correction,x)
        if abs(x)>1.20 and .25<y<4.85:
            amount=max(0,min(1,(abs(x)-1.20)/.44))
            sign=1 if x>0 else -1
            theta=sign*angle
            dx=x-sign*1.50;dy=y-4.55
            rx=dx*math.cos(theta)-dy*math.sin(theta)
            ry=dx*math.sin(theta)+dy*math.cos(theta)
            result[i][0]=x+(sign*1.50+rx-x)*amount
            result[i][1]=y+(4.55+ry-y)*amount
            result[i][2]=z-.65*max(0,min(1,(4.50-y)/3.10))*amount
    return result


def rest_joint_fit(arm,points,rig,transform):
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active=arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    for name,item in rig['bones'].items():
        bone=arm.data.edit_bones[name]
        bone.head=transform(joint_point(points,rig,item['head']))
        bone.tail=transform(joint_point(points,rig,item['tail']))
        if (bone.tail-bone.head).length<1e-5:
            bone.tail+=Vector((0,0,.002))
        plane=rig.get('planes',{}).get(item.get('rotation_plane'))
        if plane and len(plane)==3:
            p=[Vector(transform(joint_point(points,rig,n)))for n in plane]
            normal=(p[1]-p[0]).cross(p[2]-p[0])
            if normal.length>1e-7:
                bone.align_roll(normal)
    bpy.ops.object.mode_set(mode='OBJECT')
    arm.select_set(False)


def render_views(config,transform,scale,renders):
    scene=bpy.context.scene
    scene.render.resolution_x=scene.render.resolution_y=1024
    scene.cycles.samples=config.get('dressed_render_samples',48)
    camera=scene.camera
    target=Vector((0,0,.86))
    camera.data.ortho_scale=1.94
    views={}
    for name,angle in [('front',0),('left_profile',90),('back',180),('right_profile',-90),('three_quarter',35)]:
        r=math.radians(angle)
        camera.location=target+Vector((3*math.sin(r),-3*math.cos(r),0))
        point_camera(camera,target)
        scene.render.filepath=str(renders/(name+'.png'))
        bpy.ops.render.render(write_still=True)
        views[name]=scene.render.filepath
    target=Vector(transform((0,6.82,.45)))
    camera.data.ortho_scale=3.05*scale
    for name,angle in [('portrait_front',0),('portrait_three_quarter',35)]:
        r=math.radians(angle)
        camera.location=target+Vector((2*math.sin(r),-2*math.cos(r),0))
        point_camera(camera,target)
        scene.render.filepath=str(renders/(name+'.png'))
        bpy.ops.render.render(write_still=True)
        views[name]=scene.render.filepath
    target=Vector((0,0,.86))
    camera.data.ortho_scale=1.94
    camera.location=target+Vector((0,-3,0))
    point_camera(camera,target)
    return views


def export_glb(output):
    bpy.ops.object.select_all(action='DESELECT')
    selected=[]
    for obj in bpy.context.scene.objects:
        if obj.type in ('MESH','ARMATURE')and not obj.hide_render:
            obj.select_set(True);selected.append(obj)
    arm=next(o for o in selected if o.type=='ARMATURE')
    bpy.context.view_layer.objects.active=arm
    bpy.ops.export_scene.gltf(filepath=str(output),export_format='GLB',use_selection=True,
        export_yup=True,export_texcoords=True,export_normals=True,export_tangents=True,
        export_skins=True,export_morph=True,export_animations=True,export_cameras=False,
        export_lights=False,export_extras=True,export_apply=False)


def main():
    args=arguments()
    config=json.loads(Path(args.config).read_text())
    gate=json.loads(Path(args.gate).read_text())
    headgate=json.loads(Path(args.head_gate).read_text())
    if not gate.get('front_profile_body_initial_gate_passed'):
        raise RuntimeError('Initial reference geometry gate has not passed')
    if not headgate.get('credible_head_geometry_passed'):
        raise RuntimeError('Detailed texture/dressed build blocked: actual clay head must receive independent credible-geometry review')
    body=bpy.data.objects.get('Inez_ContinuousHumanMesh_UNAPPROVED')
    arm=bpy.data.objects.get('InezRig_PROTOTYPE')
    if body is None or arm is None:
        raise RuntimeError('Load the actual fitted clay .blend, not an empty scene')
    if body.data.shape_keys is None or len(body.data.shape_keys.key_blocks)<2:
        raise RuntimeError('Separate editable source Basis and actual fitted head must be retained')
    if any(o.name=='Inez_Sweater'for o in bpy.data.objects):
        raise RuntimeError('Dressed geometry already exists: open a fresh reviewed head .blend for an iteration')
    source,uv,groups=read_obj()
    basis=shape_vertices(source,config['source_shape_weights'])
    fitted=fit_vertices(basis,config['fit_controls'])
    ground=min(basis[i][1]for i in range(13380))
    height=max(basis[i][1]for i in range(13380))-ground
    scale=config['provisional_height_m']/height
    def transform(p):
        return (p[0]*scale,-p[2]*scale,(p[1]-ground)*scale)
    fitkey=body.data.shape_keys.key_blocks[-1]
    attr=body.data.attributes.get('makehuman_source_index')
    if attr is None:
        raise RuntimeError('Actual fitted topology lost its licensed source-index correspondence')
    for vi,item in enumerate(attr.data):
        co=fitkey.data[vi].co
        fitted[item.value]=(co.x/scale,co.z/scale+ground,-co.y/scale)
    fitted=fit_body_pose(fitted,config)
    for vi,item in enumerate(attr.data):
        fitkey.data[vi].co=transform(fitted[item.value])
    fitkey.value=1.0
    rig,weights=rig_sources()
    rest_joint_fit(arm,fitted,rig,transform)
    textures=CHARACTER/'model/textures'
    body.data.materials.clear()
    body.data.materials.append(skin_pbr(fitted,uv,groups['body'],textures,args.texture_resolution))
    faceobjects=build_face(body,fitted,uv,groups,rig,weights,transform,arm,textures)
    clothing=build_clothing(fitted,uv,groups,rig,weights,transform,arm,textures)
    hair=build_hair(fitted,uv,groups,transform,arm,textures)
    body['identity_status']='Fitted dressed playable foundation; independent final artistic review pending'
    body['fitting_limitations']='Original/profile-informed continuous head fit; unseen geometry/microdetail extrapolated'
    arm['rig_status']='163 actual bones/normalized source weights; dressed deformation/animation review pending'
    scene=bpy.context.scene
    scene['INEZ_STAGE']='Actual fitted dressed rigged prototype; final identity and animation gates pending'
    scene['geometry_head_gate']=json.dumps(headgate)
    scene['source_basis_preserved']=True
    scene['material_authority']='Original A face; original B costume; generated body guides geometry only'
    revision=config['revision']
    out=CHARACTER/'model'
    out.mkdir(parents=True,exist_ok=True)
    renders=CHARACTER/('renders/dressed_'+revision)
    renders.mkdir(parents=True,exist_ok=True)
    # Deliver the actual editable skinned geometry before the longer studio
    # rendering stage, so the motion artist can work on the delivered source.
    # Rendering afterward never overwrites that source or the animated GLB.
    camera=scene.camera
    target=Vector((0,0,.86))
    camera.data.ortho_scale=1.94
    camera.location=target+Vector((0,-3,0))
    point_camera(camera,target)
    blend=out/'inez.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    backup=out/'work'/('inez_dressed_'+revision+'.blend')
    bpy.ops.wm.save_as_mainfile(filepath=str(backup),copy=True)
    export_glb(out/'inez.glb')
    print('INEZ_DRESSED_ASSETS_READY '+json.dumps({'blend':str(blend),
        'glb':str(out/'inez.glb'),'rest_backup':str(backup)}),flush=True)
    renderfiles=render_views(config,transform,scale,renders)if args.render else {}
    manifest={
        'revision':revision,'stage':scene['INEZ_STAGE'],'blend':str(blend),'glb':str(out/'inez.glb'),
        'initial_geometry_gate':gate,'credible_head_gate':headgate,
        'body_source_vertices':len(body.data.vertices),'source_basis_preserved':True,
        'actual_bone_count':len(arm.data.bones),'actual_authored_meshes':[o.name for o in faceobjects+clothing+hair],
        'actual_textures':sorted({node.image.name for obj in scene.objects if obj.type=='MESH'
            for mat in obj.data.materials if mat and mat.use_nodes
            for node in mat.node_tree.nodes if node.type=='TEX_IMAGE'and node.image}),
        'original_guided_costume':True,'texture_projection_used':False,'placeholder_mannequin_used':False,
        'animation_status':'Separate animation artist must add and verify actual Idle/Walk/Run and face controls',
        'final_artistic_identity_approved':False,'production_complete':False,'actual_renders':renderfiles,
        'units':'meters; glTF Y up, +Z forward','provisional_height_m':config['provisional_height_m'],
    }
    (CHARACTER/'qa/model'/('model_dressed_'+revision+'_manifest.json')).write_text(json.dumps(manifest,indent=2)+'\n')
    print('INEZ_DRESSED_MODEL_MANIFEST '+json.dumps(manifest))


if __name__=='__main__':
    main()
