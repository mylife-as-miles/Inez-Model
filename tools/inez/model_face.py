"""Actual eye/cornea, restrained brows/lashes and tearline mesh authoring."""
import math
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from model_source import joint_point
from model_geometry import mesh_object,tubes,skin_rigid,skin_source_nearest
from model_materials import material,iris_pbr,detail_tile


def face_front_surface(body,transform):
    depsgraph=bpy.context.evaluated_depsgraph_get()
    evaluated=body.evaluated_get(depsgraph)
    mesh=evaluated.to_mesh()
    vertices=[body.matrix_world@v.co for v in mesh.vertices]
    faces=[tuple(p.vertices)for p in mesh.polygons]
    bvh=BVHTree.FromPolygons(vertices,faces)
    evaluated.to_mesh_clear()
    scale=transform((1,0,0))[0]
    ground=-transform((0,0,0))[2]/scale
    def project(x,y,offset=.004):
        origin=Vector(transform((x,y,4.0)))
        location,normal,index,distance=bvh.ray_cast(origin,Vector((0,1,0)),1.0)
        if location is None:
            raise RuntimeError('Actual head surface not found for face overlay')
        source=(location.x/scale,location.z/scale+ground,-location.y/scale+offset)
        return source
    return project


def make_cornea(side,center,radius,transform,arm,directory):
    mat=detail_tile('ClearCornea_'+side,directory,(.96,.97,.96),.035,'cornea',resolution=256)
    bsdf=mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Transmission Weight'].default_value=1.0
    bsdf.inputs['IOR'].default_value=1.376
    bsdf.inputs['Specular IOR Level'].default_value=.5
    points=[];faces=[];uv=[]
    rings=9;segments=40
    # Small natural corneal dome, separated from the iris and white sclera.
    for row in range(rings):
        angle=.002+.678*row/(rings-1)
        for k in range(segments):
            a=2*math.pi*k/segments
            rr=radius*math.sin(angle)
            points.append((center[0]+rr*math.cos(a),center[1]+rr*math.sin(a),
                           center[2]+radius*math.cos(angle)+.0035*math.exp(-(angle/.34)**2)))
    for row in range(rings-1):
        for k in range(segments):
            nxt=(k+1)%segments
            faces.append((row*segments+k,row*segments+nxt,(row+1)*segments+nxt,(row+1)*segments+k))
            uv.append([(k/segments,row/(rings-1)),((k+1)/segments,row/(rings-1)),
                       ((k+1)/segments,(row+1)/(rings-1)),(k/segments,(row+1)/(rings-1))])
    obj=mesh_object('Inez_Cornea_'+side,points,faces,transform,mat,uv)
    skin_rigid(obj,arm,'eye.'+side)
    obj['eye_status']='Actual refractive cornea over separate iris/pupil and sclera, restrained reflection'
    return obj


def build_face(body,points,uv,groups,rig,weights,transform,arm,directory):
    irismat=iris_pbr(directory)
    sclera=detail_tile('ScleraOffWhite',directory,(.72,.735,.69),.28,'sclera')
    sclera.node_tree.nodes.get('Principled BSDF').inputs['Subsurface Weight'].default_value=.025
    pupilmat=material('Inez_NaturalPupil',(.004,.005,.004),.17)
    browmat=material('Inez_DenseNaturalBrownBrows',(.053,.035,.024),.71)
    lashmat=material('Inez_NaturalBrownLashes',(.039,.026,.021),.69)
    tearmat=material('Inez_SubtlePinkTearline',(.47,.24,.21),.23)
    objects=[]
    for side in ('L','R'):
        eye=bpy.data.objects.get('EyeGeometry_'+side)
        if eye is None:
            raise RuntimeError('Fitted source eyeball missing')
        eye.data.materials.clear();eye.data.materials.append(sclera)
        eye.name='Inez_Eyeball_'+side
        iris=bpy.data.objects.get('IrisQA_'+side)
        pupil=bpy.data.objects.get('PupilQA_'+side)
        if iris is None or pupil is None:
            raise RuntimeError('Real clay eye landmark geometry missing')
        iris.data.materials.clear();iris.data.materials.append(irismat);iris.name='Inez_Iris_'+side
        pupil.data.materials.clear();pupil.data.materials.append(pupilmat);pupil.name='Inez_Pupil_'+side
        ids={i for face in groups['helper-'+side.lower()+'-eye']for i,t in face}
        center=joint_point(points,rig,rig['bones']['eye.'+side]['head'])
        radius=max(points[i][2]for i in ids)-center[2]
        objects.append(make_cornea(side,center,radius+.0045,transform,arm,directory))
    project=face_front_surface(body,transform)
    rng=np.random.default_rng(2451)
    for side,sign in [('L',1),('R',-1)]:
        paths=[];radii=[]
        for k in range(205):
            x=rng.uniform(.125,.485)
            t=(x-.125)/.36
            band_y=6.994+.028*math.exp(-((t-.65)/.29)**2)-.016*t
            y=band_y+rng.uniform(-.019,.019)*(1-.66*t)
            length=rng.uniform(.017,.035)*(1-.35*t)
            slope=.55-.80*t
            path=[]
            for s in np.linspace(0,1,6):
                xx=sign*(x+length*s*.59)
                yy=y+length*s*slope-.006*s*s
                path.append(project(xx,yy,.008+.003*math.sin(math.pi*s)))
            paths.append(path);radii.append(rng.uniform(.0010,.00175))
        brow=tubes('Inez_Brows_'+side,paths,radii,transform,browmat,sides=3)
        skin_source_nearest(brow,arm,points,weights,transform)
        objects.append(brow)
        upperids=[6847,6844,6841,6838,6785,6784,6790,6793,6796,6799,6802]
        lowerids=[6847,6837,6834,6831,6828,6825,6822,6819,6816,6814,6802]
        if sign<0:
            # Exact original topology mirror, never an unrelated symmetric head.
            source=np.asarray(points[:13380])
            def mirror(i):
                target=np.asarray(points[i])*np.array([-1,1,1])
                return int(np.argmin(np.sum((source-target)**2,axis=1)))
            upperids=[mirror(i)for i in upperids]
            lowerids=[mirror(i)for i in lowerids]
        for kind,ids,bone in [('Upper',upperids,'orbicularis03.'+side),('Lower',lowerids,'orbicularis04.'+side)]:
            line=[Vector(points[i])for i in ids]
            paths=[];radii=[]
            count=51 if kind=='Upper' else 26
            for value in np.linspace(.10,len(line)-1-.15,count):
                index=int(value);t=value-index
                p=line[index].lerp(line[min(index+1,len(line)-1)],t)
                length=(.036 if kind=='Upper'else .021)*rng.uniform(.72,1.10)
                direction=Vector((sign*(.06+value/len(line)*.27),.68 if kind=='Upper'else -.49,.75)).normalized()
                paths.append([tuple(p+direction*length*s+Vector((0,-.006*s*s,.007*math.sin(math.pi*s))))for s in np.linspace(0,1,6)])
                radii.append(.00095 if kind=='Upper'else .00072)
            lash=tubes('Inez_Lashes'+kind+'_'+side,paths,radii,transform,lashmat,sides=3)
            skin_rigid(lash,arm,bone)
            lash['face_overlay_status']='Real eyelid-bone attachment; requires animation morph-following review'
            objects.append(lash)
        tear=tubes('Inez_Tearline_'+side,[[tuple(Vector(points[i])+Vector((0,.002,.005)))for i in lowerids]],.0032,transform,tearmat,sides=4)
        skin_rigid(tear,arm,'orbicularis04.'+side)
        objects.append(tear)
    return objects
