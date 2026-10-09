"""Fitted, skinned real sweater/jeans/platform-boot reconstruction.

Cloth uses continuous licensed surface topology, with loose fitted silhouette,
applied thickness, independent cuffs/neck/hem and sewn seams/pockets. Boots
are connected lofted uppers/soles with real tongues, eyelets and laces.
Importing the module creates nothing; root and head gates are caller-owned.
"""
import math
import bpy
import numpy as np
from mathutils import Vector
from model_source import source_weight_vectors, joint_point
from model_build import mesh_from_group,attach_weights
from model_geometry import (mesh_object,tubes,loft,skin_rigid,skin_source_nearest,
                            actual_thickness,smooth_geometry,boundary_loops,torus_source)
from model_materials import material,fabric_pbr,detail_tile


def body_normals(points,faces):
    points=np.asarray(points,float)
    normals=np.zeros_like(points)
    for face in faces:
        ids=[i for i,t in face]
        a,b,c=points[ids[:3]]
        normal=np.cross(b-a,c-a)
        for i in ids:
            normals[i]+=normal
    lengths=np.linalg.norm(normals,axis=1)
    normals/=np.maximum(lengths,1e-9)[:,None]
    return normals


def clothing_faces(points,groups,normalized,kind):
    selected=[]
    for face in groups['body']:
        ids=[i for i,t in face]
        center=np.mean([points[i]for i in ids],axis=0)
        arm=sum(sum(v for n,v in normalized[i].items()if n.startswith(('upperarm','lowerarm','shoulder')))
                for i in ids)/len(ids)
        hand=sum(sum(v for n,v in normalized[i].items()if n.startswith(('finger','wrist')))
                 for i in ids)/len(ids)
        if kind=='sweater':
            sleeve=arm>.40 and hand<.24
            torso=(abs(center[0])<1.55 and center[1]>1.82)
            if center[1]<5.20 and (torso or sleeve):
                selected.append(face)
        elif -5.54<center[1]<1.48 and abs(center[0])<2.6 and arm<.12 and hand<.12:
            selected.append(face)
    if len(selected)<300:
        raise RuntimeError('Clothing topology selection failed for '+kind)
    return selected


def garment_points(points,normals,kind):
    result=np.asarray(points,float).copy()
    for i,p in enumerate(points[:13380]):
        x,y,z=p
        n=normals[i]
        if kind=='sweater':
            offset=.205
            if abs(x)<1.45:
                # Fill the waist indentation so the crop hangs roomy below the chest.
                offset+=.12*math.exp(-((y-2.65)/.73)**2)
            else:
                offset+=.055
            result[i]+=n*offset
            if z>.55 and 1.85<y<3.5 and abs(x)<.95:
                result[i,2]+=.12*math.exp(-((y-2.55)/.70)**2)
            ripple=.024*math.sin(y*14+x*3)*math.exp(-((y-2.05)/.40)**2)
            result[i]+=n*ripple
        else:
            offset=.13 if y>-.70 else .20
            result[i]+=n*offset
            if y<-.55:
                side=1 if x>0 else -1
                center_x=side*(1.015+.018*math.sin(y*.6))
                center_z=.30+.12*math.exp(-((y+3.6)/1.7)**2)
                dx=x-center_x;dz=z-center_z
                r=math.sqrt(dx*dx+dz*dz)
                target=.64 if y>-3.5 else .55
                # Loose straight legs, preserving separation on the inner seam.
                if r>.10:
                    grow=max(0,target-r)
                    result[i,0]+=dx/r*grow*.88
                    result[i,2]+=dz/r*grow*.88
                gathering=(.047*math.sin(y*27+z*9+x*3)+.029*math.sin(y*43-z*7))*math.exp(-((y+5.1)/.63)**2)
                result[i]+=n*gathering
            # Natural broad denim creases, not ornamental distressing.
            result[i]+=n*(.024*math.sin(y*17+x*6+z*4)*math.exp(-((y+3.0)/1.3)**2))
    return result.tolist()


def add_sweater_trims(obj,source_points,transform,arm,weights,mat):
    inverse_scale=1/transform((1,0,0))[0]
    objects=[]
    for index,loop in enumerate(boundary_loops(obj)):
        if len(loop)<6:
            continue
        # Boundary vertices are still source coordinates before refinement/thickness.
        ids=[obj.data.attributes['makehuman_source_index'].data[i].value for i in loop]
        path=[Vector(source_points[i])for i in ids]
        center=sum(path,Vector())/len(path)
        width=.16 if center.y<2.2 else .15
        if abs(center.x)>2.5:
            kind='Cuff'
            toward=Vector((-math.copysign(.14,center.x),.16,-.08)).normalized()
            width=.18
        elif center.y>4.8:
            kind='CrewNeck'
            toward=Vector((0,-1,0))
            width=.14
        else:
            kind='RibbedHem'
            toward=Vector((0,1,0))
            width=.18
        rings=[]
        for k in range(4):
            t=k/3
            ring=[]
            for j,p in enumerate(path):
                radial=p-center
                radial.y=0 if kind!='Cuff' else radial.y
                if radial.length>1e-8:
                    radial.normalize()
                rib=.009*math.cos(2*math.pi*j/len(path)*max(16,len(path)//2))
                ring.append(tuple(p+toward*width*t+radial*(.019+rib)))
            rings.append(ring)
        trim=loft('Inez_Sweater_'+kind+'_'+str(index),rings,transform,mat,capped=False)
        skin_source_nearest(trim,arm,source_points,weights,transform)
        actual_thickness(trim,.0024)
        objects.append(trim)
    return objects


def surface_point(points,ids,x,y,front=True):
    best=None;cost=1e30
    for i in ids:
        p=points[i]
        c=(p[0]-x)**2+(p[1]-y)**2
        if front and p[2]<.24:
            c+=4
        if not front and p[2]>-.03:
            c+=4
        if c<cost:
            cost,best=c,p
    return (x,y,best[2]+(.020 if front else -.020))


def add_jean_details(obj,points,source,transform,arm,weights,denim,thread):
    ids=[d.value for d in obj.data.attributes['makehuman_source_index'].data]
    objects=[]
    seam_paths=[]
    for side in (-1,1):
        # Front pocket openings, central fly, side and inseam construction.
        seam_paths.append([surface_point(points,ids,side*(.58+.40*t),1.17-.53*t,True)for t in np.linspace(0,1,20)])
        seam_paths.append([surface_point(points,ids,side*1.49,y,False)for y in np.linspace(.70,-5.39,70)])
        seam_paths.append([surface_point(points,ids,side*.43,y,True)for y in np.linspace(-.80,-5.35,60)])
        outline=[(side*.30,.98),(side*.96,.91),(side*.92,.06),(side*.64,-.20),(side*.30,.02)]
        pocketpoints=[surface_point(points,ids,x,y,False)for x,y in outline]
        center=sum((Vector(p)for p in pocketpoints),Vector())/len(pocketpoints)
        pocketpoints.append(tuple(center+Vector((0,0,-.018))))
        faces=[(i,(i+1)%5,5)for i in range(5)]
        pocket=mesh_object('Inez_Jeans_RearPatchPocket_'+('L'if side>0 else'R'),pocketpoints,faces,transform,denim)
        skin_source_nearest(pocket,arm,source,weights,transform)
        actual_thickness(pocket,.0009)
        objects.append(pocket)
        seam_paths.append(pocketpoints[:5]+[pocketpoints[0]])
    seam_paths.append([surface_point(points,ids,.025,y,True)for y in np.linspace(1.29,-.39,35)])
    seam_paths.append([surface_point(points,ids,-.055,y,True)for y in np.linspace(1.26,-.28,35)])
    for front in (True,False):
        seam_paths.append([surface_point(points,ids,x,1.38,front)for x in np.linspace(-1.12,1.12,44)])
    seams=tubes('Inez_Jeans_SewnSeams',seam_paths,.006,transform,thread,sides=4)
    skin_source_nearest(seams,arm,source,weights,transform)
    objects.append(seams)
    for index,(x,front)in enumerate([(-.86,True),(.86,True),(-.79,False),(.79,False),(0,False)]):
        p=surface_point(points,ids,x,1.28,front)
        dz=.025 if front else -.025
        vertices=[(p[0]-.07,p[1]-.19,p[2]+dz),(p[0]+.07,p[1]-.19,p[2]+dz),
                  (p[0]+.065,p[1]+.12,p[2]+dz),(p[0]-.065,p[1]+.12,p[2]+dz)]
        loop=mesh_object('Inez_Jeans_BeltLoop_'+str(index),vertices,[(0,1,2,3)],transform,denim)
        skin_source_nearest(loop,arm,source,weights,transform)
        actual_thickness(loop,.0013)
        objects.append(loop)
    metal=material('Inez_Jeans_RestrainedDarkHardware',(.16,.15,.135),.42,.72)
    for index,(x,y)in enumerate([(0,1.28),(-.59,1.16),(.59,1.16),(-.99,.65),(.99,.65)]):
        center=surface_point(points,ids,x,y,True)
        rivet=torus_source('Inez_Jeans_ButtonOrRivet_'+str(index),center,.024 if index==0 else .012,.006,transform,metal)
        skin_source_nearest(rivet,arm,source,weights,transform)
        objects.append(rivet)
    return objects


def boots(points,rig,transform,arm,directory):
    leather=detail_tile('BootBlackLeather',directory,(.028,.029,.030),.48,'leather')
    rubber=detail_tile('BootBlackRubberSole',directory,(.017,.018,.019),.87,'rubber')
    lace_mat=material('Inez_Boot_Black_WovenLaces',(.020,.022,.023),.89)
    stitching=material('Inez_Boot_Subtle_BlackStitching',(.057,.058,.058),.80)
    eyeletmat=material('Inez_Boot_BlackenedMetalEyelets',(.049,.050,.052),.39,.73)
    objects=[]
    for side in ('L','R'):
        foot=joint_point(points,rig,rig['bones']['foot.'+side]['head'])
        cx=foot[0]
        n=40
        # Outlines are round-toed, with broad uniform platform soles and no heel.
        def ring(y,width,depth,center_z):
            result=[]
            for i in range(n):
                a=2*math.pi*i/n
                x=width*math.cos(a)
                z=center_z+depth*math.sin(a)
                result.append((cx+x,y,z))
            return result
        sole_rings=[ring(y,.515+bulge,1.19+bulge,.84)for y,bulge in
                    [(-8.12,0),(-8.07,.012),(-7.76,.012),(-7.65,.010),(-7.61,-.018)]]
        sole=loft('Inez_Boot_Sole_'+side,sole_rings,transform,rubber)
        skin_rigid(sole,arm,'foot.'+side)
        objects.append(sole)
        dims=[(-7.63,.49,1.14,.83),(-7.57,.49,1.13,.82),(-7.44,.48,1.07,.77),
              (-7.28,.45,.85,.62),(-7.10,.414,.60,.39),(-6.95,.389,.46,.28),
              (-6.74,.382,.442,.24),(-6.48,.376,.438,.21),(-6.22,.370,.429,.20),
              (-5.96,.360,.419,.20),(-5.70,.351,.410,.20),(-5.65,.351,.410,.20)]
        def front_z(y,xoffset=0):
            heights=[d[0]for d in dims]
            width=float(np.interp(y,heights,[d[1]for d in dims]))
            depth=float(np.interp(y,heights,[d[2]for d in dims]))
            center=float(np.interp(y,heights,[d[3]for d in dims]))
            return center+depth*math.sqrt(max(0,1-(xoffset/width)**2))
        upper=loft('Inez_Boot_'+side,[ring(*d)for d in dims],transform,leather,capped=False)
        actual_thickness(upper,.0028)
        skin_rigid(upper,arm,'foot.'+side)
        objects.append(upper)
        tonguepoints=[(cx+xo,y,front_z(y,xo)+.029)for y in [-7.15,-6.90,-6.60,-6.30,-6.0,-5.67]for xo in [-.205,0,.205]]
        tongue=mesh_object('Inez_Boot_Tongue_'+side,tonguepoints,
                          [(i*3+j,i*3+j+1,(i+1)*3+j+1,(i+1)*3+j)for i in range(5)for j in range(2)],transform,leather)
        actual_thickness(tongue,.0022)
        skin_rigid(tongue,arm,'foot.'+side)
        objects.append(tongue)
        laces=[]
        for row in range(7):
            y=-7.02+row*.187
            for sign in (-1,1):
                center=(cx+sign*.244,y,front_z(y,.244)+.017)
                eyelet=torus_source('Inez_Boot_Eyelet_'+side+'_'+str(row)+'_'+str(sign),center,.024,.007,transform,eyeletmat)
                skin_rigid(eyelet,arm,'foot.'+side)
                objects.append(eyelet)
            if row<6:
                for sign in (-1,1):
                    laces.append([(cx+sign*.244*(1-2*t),y+.187*t,front_z(y+.187*t,sign*.244*(1-2*t))+.044)
                                  for t in np.linspace(0,1,9)])
        lace=tubes('Inez_Boot_Laces_'+side,laces,.012,transform,lace_mat,sides=5)
        skin_rigid(lace,arm,'foot.'+side)
        objects.append(lace)
        # Toe-cap stitch is a real curved seam on the round upper.
        stitchpaths=[[(cx+.477*math.cos(a),-7.385,.748+1.046*math.sin(a)+.013)for a in np.linspace(0,math.pi,28)],
                     [(cx-.291,y,front_z(y,-.291)+.015)for y in np.linspace(-7.10,-5.77,28)],
                     [(cx+.291,y,front_z(y,.291)+.015)for y in np.linspace(-7.10,-5.77,28)],
                     ring(-7.63,.506,1.17,.84)+[ring(-7.63,.506,1.17,.84)[0]]]
        stitches=tubes('Inez_Boot_StitchedPanels_'+side,stitchpaths,.0052,transform,stitching,sides=4)
        skin_rigid(stitches,arm,'foot.'+side)
        objects.append(stitches)
        tread=[]
        for q in range(9):
            z=-.15+q*.245
            tread.append([(cx-.48+t*.96,-8.115,z)for t in np.linspace(0,1,8)])
        treadobj=tubes('Inez_Boot_SoleTread_'+side,tread,.018,transform,rubber,sides=4)
        skin_rigid(treadobj,arm,'foot.'+side)
        treadobj['hidden_detail_status']='Unseen sole tread is provisional extrapolation'
        objects.append(treadobj)
    return objects


def necklace(source_points,sweater_points,sweater_ids,transform,arm,weights,directory):
    silver=detail_tile('FineSilverChainAndTinyPendant',directory,(.61,.65,.69),.23,'silver',resolution=256)
    silver.node_tree.nodes.get('Principled BSDF').inputs['Metallic'].default_value=.95
    paths=[]
    for side in (-1,1):
        paths.append([surface_point(sweater_points,sweater_ids,side*.50*(1-t),5.22-.90*t,True)
                      for t in np.linspace(0,1,42)])
    chain=tubes('Inez_FineSilverNecklace',paths,.0062,transform,silver,sides=5)
    skin_source_nearest(chain,arm,source_points,weights,transform)
    c=surface_point(sweater_points,sweater_ids,0,4.315,True)
    # Tiny ambiguous branched silhouette: no cross/star/bird motif claimed.
    pendantpaths=[[(c[0]-.018,c[1]+.014,c[2]+.007),(c[0],c[1]-.036,c[2]+.012),
                   (c[0]+.018,c[1]+.016,c[2]+.007)],
                  [(c[0],c[1]-.020,c[2]+.01),(c[0]+.024,c[1]+.002,c[2]+.009)]]
    pendant=tubes('Inez_TinyUnknownMotifPendant',pendantpaths,.008,transform,silver,sides=5)
    skin_source_nearest(pendant,arm,source_points,weights,transform)
    pendant['motif_status']='Original tiny silhouette uncertain; no exact motif inference'
    return [chain,pendant]


def build_clothing(points,uv,groups,rig,weights,transform,arm,directory):
    normalized=source_weight_vectors(weights,range(13380))
    normals=body_normals(points,groups['body'])
    sweaterfaces=clothing_faces(points,groups,normalized,'sweater')
    jeanfaces=clothing_faces(points,groups,normalized,'jeans')
    sweaterpoints=garment_points(points,normals,'sweater')
    jeanpoints=garment_points(points,normals,'jeans')
    sweatermat=fabric_pbr('Sweater_ThreeDarkBands',sweaterpoints,uv,sweaterfaces,directory,'knit')
    jeanmat=fabric_pbr('WashedBlackDenim',jeanpoints,uv,jeanfaces,directory,'denim')
    sweater,sweaterids=mesh_from_group('Inez_Sweater',sweaterfaces,sweaterpoints,uv,transform,sweatermat)
    jeans,jeanids=mesh_from_group('Inez_Jeans',jeanfaces,jeanpoints,uv,transform,jeanmat)
    attach_weights(sweater,sweaterids,weights,arm)
    attach_weights(jeans,jeanids,weights,arm)
    ribbed=detail_tile('CharcoalRibbedKnitTrims',directory,(.22,.23,.235),.90,'ribbed')
    trims=add_sweater_trims(sweater,sweaterpoints,transform,arm,weights,ribbed)
    thread=material('Inez_Jeans_SubtleSeamThread',(.071,.076,.074),.88)
    details=add_jean_details(jeans,jeanpoints,points,transform,arm,weights,jeanmat,thread)
    # Applying surface and thickness makes the exported game asset self-contained.
    for garment in (sweater,jeans):
        smooth_geometry(garment,1)
        actual_thickness(garment,.0021 if garment==sweater else .0016)
        garment['costume_status']='Original B guided authored loose skinned garment; pending actual-render review'
    bootobjects=boots(points,rig,transform,arm,directory)
    jewelry=necklace(points,sweaterpoints,sweaterids,transform,arm,weights,directory)
    return [sweater,jeans]+trims+details+bootobjects+jewelry
