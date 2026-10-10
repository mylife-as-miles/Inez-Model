"""Versioned recovery of the existing master, never a character rebuild.

blender -b MASTER.blend --python tools/inez/v06_prepare.py -- \
  --stage color --output model/v06/inez_color_restored.blend --report REPORT.json

Stages can be applied sequentially to separate files. The identity stage uses
reproduced browser landmarks and the two original photographs, not percentage
scaling of the head. Contact repair is a separate module.
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from animation_build import reset_pose
from runtime_export import export, decimate_copy, scaled_images, swap_images, LEVELS

IDENTITY = {'Inez_HeadFit_v01':0, 'Inez_HeadFit_v02':0, 'Inez_HeadFit_v03':1,
            'Inez_HeadRefine_v05':1, 'Inez_SourceBodyFit_v05':1,
            'Inez_SourceHeadWrap_v05':1, 'Inez_FaceCorrect_v05':1}


def fingerprint(obj):
    keys={}
    if obj.data.shape_keys:
        for k in obj.data.shape_keys.key_blocks:
            a=np.empty(len(k.data)*3, np.float32);k.data.foreach_get('co',a)
            keys[k.name]={'value':k.value,'sha256':hashlib.sha256(a.tobytes()).hexdigest()}
    uv={}
    for u in obj.data.uv_layers:
        a=np.empty(len(u.data)*2,np.float32);u.data.foreach_get('uv',a)
        uv[u.name]=hashlib.sha256(a.tobytes()).hexdigest()
    return {'shape_keys':keys,'uv':uv,'vertices':len(obj.data.vertices)}


def restore_color(directory):
    # Explicitly decode and re-encode FILE image pixel buffers. The source
    # images and generated sRGB PNG buffers both contain encoded values here.
    gains={'Inez_Head_Skin_PBR':(1/.42,)*3,
           'Inez_Skin_Freckles_Pores_Lips_PBR':(1/.42,)*3,
           'Inez_Hair_FromAssetB':(.042/.024,.021/.0135,.0088/.0068)}
    directory.mkdir(parents=True,exist_ok=True)
    report={}
    for name,gain in gains.items():
        mat=bpy.data.materials[name]
        bsdf=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
        tex=bsdf.inputs['Base Color'].links[0].from_node
        original=tex.image
        w,h=original.size
        pixels=np.empty(w*h*4,np.float32);original.pixels.foreach_get(pixels)
        px=pixels.reshape(h,w,4).copy()
        # FILE image pixel buffers here contain encoded sRGB (confirmed
        # against the JPEG bytes). Decode once before applying a linear gain.
        rgb=px[:,:,:3]
        px[:,:,:3]=np.where(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)**2.4)
        before=px[:,:,:3].copy()
        px[:,:,:3]*=np.array(gain,np.float32)
        clipped=int((px[:,:,:3]>1).any(-1).sum())
        px[:,:,:3]=np.clip(px[:,:,:3],0,1)
        after=px[:,:,:3].copy()
        rgb=px[:,:,:3]
        px[:,:,:3]=np.where(rgb<=.0031308,rgb*12.92,1.055*rgb**(1/2.4)-.055)
        image=bpy.data.images.new(original.name+'_restored_v06',width=w,height=h,alpha=True)
        image.colorspace_settings.name='sRGB'
        image.pixels.foreach_set(px.ravel());image.update()
        target=directory/(original.name.replace('.','_')+'_restored_v06.png')
        image.file_format='PNG';image.filepath_raw=str(target);image.save()
        bpy.data.images.remove(image)
        tex.image=bpy.data.images.load(str(target),check_existing=False)
        tex.image.colorspace_settings.name='sRGB'
        report[name]={'source':original.filepath,'source_color_space':original.colorspace_settings.name,
                     'output':str(target),'linear_gain':list(gain),'clipped_texels':clipped,
                     'before_median_linear':np.median(before.reshape(-1,3),axis=0).tolist(),
                     'after_median_linear':np.median(after.reshape(-1,3),axis=0).tolist()}
    return report


def likeness(body, capture_path, render_path, reference_path):
    capture=json.loads(Path(capture_path).read_text())['views']['face_front']
    current=np.array(json.loads(Path(render_path).read_text())['landmarks'])[:,:2]
    ref=np.array(json.loads(Path(reference_path).read_text())['landmarks'])[:,:2]
    # Residual pitch/expressions make vertical fitting uncertain. This
    # candidate uses horizontal mouth/jaw corrections only.
    from face_correct import align
    target=align(ref,current)
    p=np.array(capture['camera']['projection']).reshape(4,4,order='F')
    cam=np.array(capture['camera']['matrixWorld']).reshape(4,4,order='F')
    inv=cam@np.linalg.inv(p)
    offset=np.array(capture['avatarOffset'])
    dg=bpy.context.evaluated_depsgraph_get();ev=body.evaluated_get(dg);mesh=ev.to_mesh()
    xyz=np.array([body.matrix_world@v.co for v in mesh.vertices])
    bvh=BVHTree.FromPolygons([tuple(v) for v in xyz],[tuple(f.vertices) for f in mesh.polygons])
    ev.to_mesh_clear()
    def point(i,contour=False):
        ndc=np.array([2*current[i,0]/capture['width']-1,1-2*current[i,1]/capture['height'],-1,1])
        a=inv@ndc;a=a[:3]/a[3]-offset
        ndc[2]=1;b=inv@ndc;b=b[:3]/b[3]-offset
        a=np.array([a[0],-a[2],a[1]]);b=np.array([b[0],-b[2],b[1]])
        ray=(b-a)/np.linalg.norm(b-a)
        hit=bvh.ray_cast(Vector(a),Vector(ray),100)[0]
        if hit is not None and not contour:return np.array(hit)
        # Silhouette points are prone to a ray miss. Find the fitted vertex
        # closest to this actual camera ray; exclude neck and scalp.
        dist=np.linalg.norm(np.cross(xyz-a,ray),axis=1)
        dist[xyz[:,2]<1.40]=np.inf
        return xyz[int(np.argmin(dist))]
    # Orthographic image delta -> world delta; restrict to image x and world z.
    sx=(capture['camera']['right']-capture['camera']['left'])/capture['width']
    sy=(capture['camera']['top']-capture['camera']['bottom'])/capture['height']
    # Conservative stable targets: lip corners, alae, jaw, chin. No aperture
    # expansion: the reference is worried, and blinks must still close fully.
    groups=[([61,291],.75,0,False),([172,397],.65,0,True),
            ([136,365],.5,0,True),([150,379],.5,0,True)]
    centres=[];values=[];moves={}
    for ids,wx,wz,contour in groups:
        delta=(target[ids]-current[ids])*np.array([sx,-sy])
        if len(ids)==2:
            dx=(delta[0,0]-delta[1,0])/2;dz=delta[:,1].mean()
            delta=np.array([[dx,dz],[-dx,dz]])
        for i,d in zip(ids,delta):
            d=np.clip(d*np.array([wx,wz]),[-.0025,-.0007],[.0025,.0007])
            centres.append(point(i,contour));values.append([d[0],0,d[1]])
            moves[str(i)]=(d*1000).tolist()
    for i in [33,133,362,263,159,145,386,374,168,6,105,334,151,9,234,454,13,17,0,129,358,152,2]:
        centres.append(point(i));values.append([0,0,0])
    centres=np.array(centres);values=np.array(values);sigma=.014
    K=np.exp(-((centres[:,None]-centres[None])**2).sum(-1)/(2*sigma*sigma))
    weights=np.linalg.solve(K+np.eye(len(K))*.015,values)
    delta=np.exp(-((xyz[:,None]-centres[None])**2).sum(-1)/(2*sigma*sigma))@weights
    delta[xyz[:,2]<1.40]=0
    to_local=np.array(body.matrix_world.inverted().to_3x3())
    delta=delta@to_local.T
    key=body.shape_key_add(name='Inez_LikenessCorrect_v06',from_mix=False)
    base=np.array([v.co for v in body.data.shape_keys.key_blocks[0].data])
    key.data.foreach_set('co',(base+delta).astype(np.float32).ravel());key.value=1
    return {'key':key.name,'candidate_only':True,'sigma_m':sigma,'landmark_moves_mm':moves,
            'max_displacement_mm':float(np.linalg.norm(delta,axis=1).max()*1000),
            'affected_vertices':int((np.linalg.norm(delta,axis=1)>.00001).sum()),
            'eyelid_aperture_changed':False,'depth_changed':False}


def export_runtime(arm,meshes,output,work):
    work.mkdir(parents=True,exist_ok=True)
    copies=[];originals=[]
    for obj in meshes:
        for mod in obj.modifiers:
            if mod.type=='SUBSURF':mod.show_viewport=mod.show_render=False
        if obj.name in LEVELS['lod0']:
            copy,_,_=decimate_copy(obj,LEVELS['lod0'][obj.name]);copies.append(copy);originals.append(obj)
    mapping=scaled_images(2048,work);swap_images(mapping,True)
    # Blender samples integer frames. A 24 Hz authored endpoint can land on
    # a half frame at 60 Hz. Export on their common 120 Hz lattice so Blink,
    # crouch transitions and turns retain their exact authored endpoints.
    scene=bpy.context.scene;fps=scene.render.fps;frame_base=scene.render.fps_base
    export_fps=math.lcm(24,fps);scale=export_fps/fps
    saved=[]
    for action in bpy.data.actions:
        for curve in action.fcurves:
            for point in curve.keyframe_points:
                for co in [point.co,point.handle_left,point.handle_right]:
                    saved.append((co,float(co.x)));co.x=1+(co.x-1)*scale
    scene.render.fps=export_fps
    try:
        export(output,[o for o in meshes if o not in originals]+copies,arm,image_format='JPEG',quality=95)
    finally:
        for co,x in saved:co.x=x
        scene.render.fps=fps;scene.render.fps_base=frame_base
    swap_images(mapping,False)
    for o in copies:bpy.data.objects.remove(o,do_unlink=True)
    for i in mapping.values():bpy.data.images.remove(i)


def main():
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['color','likeness','contacts'],required=True)
    p.add_argument('--output',required=True);p.add_argument('--report',required=True);p.add_argument('--raw-glb')
    p.add_argument('--capture');p.add_argument('--render-landmarks');p.add_argument('--reference-landmarks')
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    output=Path(args.output).resolve();source=Path(bpy.data.filepath).resolve()
    if output==source or 'v06' not in str(output):raise RuntimeError('Write a separate versioned V06 source')
    output.parent.mkdir(parents=True,exist_ok=True)
    arm=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
    arm.animation_data.action=None;reset_pose(arm)
    meshes=[o for o in bpy.context.scene.objects if o.type=='MESH' and not o.hide_render]
    body=bpy.data.objects['Inez_ContinuousHumanMesh_UNAPPROVED']
    for obj in meshes:
        for mod in obj.modifiers:
            if mod.type=='SUBSURF':mod.show_viewport=mod.show_render=False
    before={o.name:fingerprint(o) for o in meshes}
    for name,value in IDENTITY.items():
        assert abs(body.data.shape_keys.key_blocks[name].value-value)<1e-7,(name,'source default changed')
    report={'source':str(source),'output':str(output),'stage':args.stage,'production_approved':False,
            'bone_count':len(arm.data.bones),'before':before}
    if args.stage=='color':report['color_restoration']=restore_color(output.parent/'textures')
    elif args.stage=='likeness':report['likeness']=likeness(body,args.capture,args.render_landmarks,args.reference_landmarks)
    else:
        from v06_contacts import repair
        report['contacts']=repair(arm,meshes,body)
    after={o.name:fingerprint(o) for o in meshes}
    for name,old in before.items():
        assert old['uv']==after[name]['uv'],(name,'UV regression')
        for key,record in old['shape_keys'].items():assert record==after[name]['shape_keys'][key],(name,key,'morph regression')
    report['existing_morphs_and_uv_unchanged']=True
    report['after']=after
    report['actions']=[a.name for a in bpy.data.actions if a.get('inez_generated_animation')]
    bpy.ops.wm.save_as_mainfile(filepath=str(output),compress=True,relative_remap=True)
    if args.raw_glb:export_runtime(arm,meshes,Path(args.raw_glb).resolve(),output.parent/'export_work')
    Path(args.report).write_text(json.dumps(report,indent=2)+'\n')
    print('V06',args.stage,output,report['existing_morphs_and_uv_unchanged'])


if __name__=='__main__':main()
