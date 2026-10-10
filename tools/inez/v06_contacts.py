"""Repair rigid platform soles and authored contact curves, keeping the rig.

The original actions are copied, sampled at 60 Hz and only six leg-bone
rotations are changed. Upper body, hands, face, and ponytail remain authored.
Rolling contacts anchor the same material point between adjacent samples;
matching-speed travel is included. A closed ankle loop is not a slip test.
"""
import json
import math
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector, Quaternion

from animation_build import vertex_side, boot_vectors, rig_lengths, leg_ik, update


def repair(arm,meshes,body):
    scene=bpy.context.scene
    original_fps=scene.render.fps/scene.render.fps_base
    boots=next(o for o in meshes if o.name=='Inez_Boots')
    before=[];changed={'L':0,'R':0};shaft_weights={}
    bones={g.index:g.name for g in boots.vertex_groups if g.name in arm.data.bones}
    floors={s:min((boots.matrix_world@v.co).z for v in boots.data.vertices if vertex_side(boots,v)==s) for s in 'LR'}
    # The platform and foot below 7 cm are rigid; blend only above that into
    # the existing shaft weighting. Ground-audit sole band is the bottom 3 cm.
    for v in boots.data.vertices:
        side=vertex_side(boots,v)
        if side not in ('L','R'):continue
        z=(boots.matrix_world@v.co).z-floors[side]
        old={bones[g.group]:g.weight for g in v.groups if g.group in bones}
        if z>=.11:shaft_weights[v.index]=old;continue
        t=np.clip((z-.07)/.04,0,1);t=float(t*t*(3-2*t))
        new={n:w*t for n,w in old.items()}
        foot='foot.'+side;new[foot]=new.get(foot,0)+(1-t)
        if z<.03 and old.get(foot,0)<.9999:
            before.append({'vertex':v.index,'side':side,'height_m':z,'weights':old});changed[side]+=1
        for g in list(v.groups):boots.vertex_groups[g.group].remove([v.index])
        for name,w in new.items():
            if w>1e-8:boots.vertex_groups[name].add([v.index],w,'REPLACE')
    for i,weights in shaft_weights.items():
        now={bones[g.group]:g.weight for g in boots.data.vertices[i].groups if g.group in bones}
        assert now==weights,'shoe shaft weight regression'
    supports=boot_vectors(arm,meshes,body);lengths=rig_lengths(arm)
    # Restrict rigid support candidates to the actual platform sole. The
    # freely deforming shaft is never a ground support point.
    for s in 'LR':
        low=min(v.z for v in supports[s]['vectors'])
        supports[s]['vectors']=[v for v in supports[s]['vectors'] if v.z<low+.03]
    original_actions={name:bpy.data.actions[name] for name in ['Walk','Run','CrouchDown','CrouchUp','Crouch']}
    manifest=json.loads((Path(__file__).resolve().parents[2]/'assets/characters/inez/rig/animation_manifest.json').read_text())
    plans={};original_ranges={}
    for name,action in original_actions.items():
        arm.animation_data.action=action
        first,last=map(float,action.frame_range);duration=(last-first)/original_fps
        count=round(duration*60);original_ranges[name]=[first,last]
        speed=manifest['clip_info'][name].get('matching_viewer_speed_m_s',0)
        fraction=manifest['clip_info'][name].get('stance_fraction',1)
        free={s:[] for s in 'LR'};flags={s:[] for s in 'LR'}
        # Three cycles handle a right stance that crosses the loop boundary.
        total=3*count+1 if name in ['Walk','Run'] else count+1
        for i in range(total):
            phase=(i%count)/count if name in ['Walk','Run'] else min(i/(duration*60),1)
            frame=first+phase*(last-first)
            scene.frame_set(int(frame),subframe=frame-int(frame));update()
            for s in 'LR':
                foot=arm.pose.bones['foot.'+s]
                rotation=foot.matrix.to_quaternion()@arm.data.bones['foot.'+s].matrix_local.to_quaternion().inverted()
                ankle=foot.matrix.translation.copy();ankle.y-=speed*i/60
                vs=supports[s]['vectors'];idx=min(range(len(vs)),key=lambda k:(rotation@vs[k]).z)
                free[s].append({'rotation':rotation.copy(),'ankle':ankle,'index':idx})
                flags[s].append(((phase+(0 if s=='L' else .5))%1)<fraction)
        planned={s:[f['ankle'].copy() for f in free[s]] for s in 'LR'}
        if name in ['Walk','Run']:
            for s in 'LR':
                i=0;vs=supports[s]['vectors'];f=free[s];column=flags[s]
                while i<total:
                    if not column[i]:i+=1;continue
                    start=i
                    while i<total and column[i]:i+=1
                    end=i-1;mid=(start+end)//2
                    sole=f[mid]['ankle']+f[mid]['rotation']@vs[f[mid]['index']]
                    planned[s][mid]=Vector((sole.x,sole.y,0))-f[mid]['rotation']@vs[f[mid]['index']]
                    for order in [range(mid+1,end+1),range(mid-1,start-1,-1)]:
                        for k in order:
                            g=k-1 if k>mid else k+1;later=k if k>mid else g;idx=f[later]['index']
                            contact=planned[s][g]+f[g]['rotation']@vs[idx]
                            planned[s][k]=contact-f[k]['rotation']@vs[idx]
                            planned[s][k].z=-min((f[k]['rotation']@v).z for v in vs)
                # Blend the displacement through swing, retaining authored
                # lift/pitch. Never freeze the swinging foot at its anchor.
                for k in range(total):
                    if column[k]:continue
                    a=k-1
                    while a>=0 and not column[a]:a-=1
                    b=k+1
                    while b<total and not column[b]:b+=1
                    da=planned[s][a]-f[a]['ankle'] if a>=0 else Vector()
                    db=planned[s][b]-f[b]['ankle'] if b<total else Vector()
                    u=(k-a)/max(1,b-a);u=u*u*(3-2*u)
                    planned[s][k]=f[k]['ankle']+da*(1-u)+db*u
                    planned[s][k].z=max(planned[s][k].z,-min((f[k]['rotation']@v).z for v in vs)+.003)
        else:
            # All crouch states share the Idle contact pose, avoiding the old
            # outward slide and 8-degree foot turn during the transitions.
            arm.animation_data.action=bpy.data.actions['Idle'];scene.frame_set(1);update()
            for s in 'LR':
                foot=arm.pose.bones['foot.'+s]
                rot=foot.matrix.to_quaternion()@arm.data.bones['foot.'+s].matrix_local.to_quaternion().inverted()
                target=foot.matrix.translation.copy();target.z=-min((rot@v).z for v in supports[s]['vectors'])
                for k in range(total):planned[s][k]=target.copy();free[s][k]['rotation']=rot.copy()
        begin=count if name in ['Walk','Run'] else 0
        rows=[];arm.animation_data.action=action
        reach=0
        for i in range(count+1):
            u=i/count if name in ['Walk','Run'] else min(i/(duration*60),1)
            frame=first+u*(last-first)
            scene.frame_set(int(frame),subframe=frame-int(frame));update()
            for s in 'LR':
                target=planned[s][begin+i].copy();target.y+=speed*(begin+i)/60
                _,error=leg_ik(arm,s,target,free[s][begin+i]['rotation'],lengths)
                reach=max(reach,error)
            rows.append({p+s:tuple(arm.pose.bones[p+s].rotation_quaternion) for s in ['L','R']
                         for p in ['upperleg01.','lowerleg01.','foot.']})
        plans[name]={'rows':rows,'count':count,'duration_s':duration,'speed_m_s':speed,'max_reach_error_mm':reach*1000}
    # Rescale every original action's timeline to retain all clip durations
    # when the scene switches from 24 to 60 fps, including Blink/LookAround.
    scale=60/original_fps
    for action in bpy.data.actions:
        for curve in action.fcurves:
            for point in curve.keyframe_points:
                for co in [point.co,point.handle_left,point.handle_right]:co.x=1+(co.x-1)*scale
    scene.render.fps=60;scene.render.fps_base=1
    for name,plan in plans.items():
        action=original_actions[name];arm.animation_data.action=action
        corrected=set(plan['rows'][0])
        for curve in list(action.fcurves):
            if any(curve.data_path==f'pose.bones["{n}"].rotation_quaternion' for n in corrected):action.fcurves.remove(curve)
        for i,row in enumerate(plan['rows']):
            for bone,q in row.items():
                arm.pose.bones[bone].rotation_quaternion=q
                frame=1+min(i,plan['duration_s']*60)
                arm.pose.bones[bone].keyframe_insert(data_path='rotation_quaternion',frame=frame,group=bone)
        for curve in action.fcurves:
            if any(curve.data_path==f'pose.bones["{n}"].rotation_quaternion' for n in corrected):
                for point in curve.keyframe_points:point.interpolation='LINEAR'
    arm.animation_data.action=None
    return {'incorrect_lowest_3cm_vertices':before,'corrected_sole_vertices':changed,
            'rigid_below_m':.07,'shaft_blend_band_m':[.07,.11],'shaft_above_11cm_unchanged':True,
            'fps':60,'actions':{n:{k:v for k,v in p.items() if k!='rows'} for n,p in plans.items()},
            'original_frame_ranges':original_ranges,'original_fps':original_fps,
            'method':'rolling same-material-point contact in matching-speed world space; only leg rotations replaced'}
