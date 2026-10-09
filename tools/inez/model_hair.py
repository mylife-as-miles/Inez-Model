"""Actual exportable curly high ponytail, scalp and uneven framing geometry.

No particle-system-only or screen-facing photo hair is used. The game meshes
are editable tube/card-compatible strands with retained UVs and real weights.
Hidden scalp/back arrangement is a disclosed original-consistent proposal.
"""
import math
import bpy
import numpy as np
from mathutils import Vector
from model_build import mesh_from_group
from model_geometry import tubes,skin_rigid,smooth_geometry
from model_materials import detail_tile


def bezier(a,b,c,d,t):
    return ((1-t)**3*np.asarray(a)+3*(1-t)**2*t*np.asarray(b)+
            3*(1-t)*t*t*np.asarray(c)+t**3*np.asarray(d))


def build_hair(points,uv,groups,transform,arm,directory):
    rng=np.random.default_rng(72269)
    hairmat=detail_tile('MediumBrownHair',directory,(.115,.076,.049),.57,'hair')
    warmmat=detail_tile('RestrainedWarmHairHighlights',directory,(.157,.108,.068),.55,'hair')
    fine_mat=detail_tile('FineBrownFlyawayHair',directory,(.105,.073,.048),.58,'hair')
    scalpfaces=[]
    scalppoints=[list(p)for p in points]
    for face in groups['body']:
        p=np.mean([points[i]for i,t in face],axis=0)
        # High irregular hairline; original face/forehead remains unobscured.
        threshold=6.69+max(0,min(1,(p[2]+.05)/1.30))*.79
        threshold+=.035*math.sin(p[0]*7)
        if p[1]>threshold and p[1]>6.65:
            scalpfaces.append(face)
    scalpids=sorted({i for f in scalpfaces for i,t in f})
    for i in scalpids:
        p=Vector(points[i]);center=Vector((0,7.24,.37));delta=p-center
        if delta.length>0:
            delta.normalize()
        volume=.14+.036*math.sin(p.x*13+p.z*9)+.023*math.sin(p.y*19+p.z*13)
        scalppoints[i]=tuple(p+delta*volume)
    scalp,_=mesh_from_group('Inez_ScalpHair',scalpfaces,scalppoints,uv,transform,hairmat)
    skin_rigid(scalp,arm,'head')
    smooth_geometry(scalp,1)
    scalp['hairline_status']='Partly occluded original hairline reconstructed; not historical full scalp'
    objects=[scalp]
    crownpaths=[];crownradii=[];warmcrown=[];warmradii=[]
    # Loose pulled-back crown, varying uneven waves and a modest irregular part.
    for k in range(135):
        x=rng.uniform(-.67,.67)
        frontal=k<98
        if frontal:
            root=(x,7.50+.09*(1-abs(x)/.67),1.16+.14*(1-(x/.75)**2))
            control1=(x*.92,8.05+rng.uniform(-.03,.07),1.02)
            control2=(x*.52,8.04+rng.uniform(-.02,.04),-.25)
        else:
            sign=1 if x>0 else -1
            root=(sign*rng.uniform(.55,.77),rng.uniform(6.95,7.49),rng.uniform(-.30,.73))
            control1=(sign*.81,7.83,rng.uniform(-.2,.3))
            control2=(sign*.42,7.87,-.61)
        end=(rng.uniform(-.15,.15),7.57+rng.uniform(-.07,.07),-.63+rng.uniform(-.05,.04))
        phase=rng.uniform(0,2*math.pi);frequency=rng.uniform(8,13)
        path=[]
        for t in np.linspace(0,1,54):
            p=bezier(root,control1,control2,end,t)
            envelope=math.sin(math.pi*t)
            p+=np.array([.035*math.sin(frequency*math.pi*t+phase),
                         .022*math.sin(frequency*math.pi*t+phase+.7),
                         .031*math.cos(frequency*math.pi*t+phase)])*envelope
            path.append(tuple(p))
        radius=rng.uniform(.011,.023)
        if k%9==0:
            warmcrown.append(path);warmradii.append(radius*.84)
        else:
            crownpaths.append(path);crownradii.append(radius)
    crown=tubes('Inez_Crown_PulledCurlyLocks',crownpaths,crownradii,transform,hairmat,sides=5)
    skin_rigid(crown,arm,'head');objects.append(crown)
    warm=tubes('Inez_Crown_WarmAccentLocks',warmcrown,warmradii,transform,warmmat,sides=5)
    skin_rigid(warm,arm,'head');objects.append(warm)
    ponypaths=[];ponyradii=[];ponywarmpaths=[];ponywarmradii=[]
    for k in range(104):
        angle=rng.uniform(0,2*math.pi)
        radius=math.sqrt(rng.uniform(0,1))*.49
        x=radius*math.cos(angle);z=radius*.70*math.sin(angle)
        length=rng.uniform(2.60,3.03)
        root=(x*.14,7.61+rng.uniform(-.04,.04),-.64+z*.15)
        c1=(x*.8,7.13,-1.14+z)
        c2=(x,6.20,-1.29+z)
        end=(x*.67,7.56-length,-1.02+z*.63)
        turns=rng.uniform(4.7,7.2);phase=rng.uniform(0,2*math.pi)
        curl=rng.uniform(.075,.143)
        path=[]
        for t in np.linspace(0,1,83):
            p=bezier(root,c1,c2,end,t)
            theta=phase+t*turns*2*math.pi
            strength=min(1,t*7)*(1-.35*t)
            p+=np.array([curl*math.sin(theta),.028*math.cos(theta*.7),curl*.68*math.cos(theta)])*strength
            p[0]+=.028*math.sin(theta*2.31)
            path.append(tuple(p))
        strand_radius=rng.uniform(.012,.023)
        if k%10==0:
            ponywarmpaths.append(path);ponywarmradii.append(strand_radius*.86)
        else:
            ponypaths.append(path);ponyradii.append(strand_radius)
    pony=tubes('Inez_Ponytail_Curls',ponypaths,ponyradii,transform,hairmat,sides=5)
    skin_rigid(pony,arm,'head')
    pony['hair_animation_preparation']='Replace initial head weights by added hair.01/.02/.03 chain after source validation'
    objects.append(pony)
    ponywarm=tubes('Inez_Ponytail_WarmAccentCurls',ponywarmpaths,ponywarmradii,transform,warmmat,sides=5)
    skin_rigid(ponywarm,arm,'head')
    ponywarm['hair_animation_preparation']=pony['hair_animation_preparation']
    objects.append(ponywarm)
    framepaths=[];frameradii=[]
    for side in (-1,1):
        for k in range(20):
            x=side*rng.uniform(.39,.66)
            start_y=rng.uniform(7.42,7.68)
            end_y=rng.uniform(5.64,6.75)
            root=(x,start_y,1.27+rng.uniform(-.02,.05))
            c1=(side*rng.uniform(.54,.72),7.15,1.39)
            c2=(side*rng.uniform(.57,.73),6.4,1.22)
            end=(side*rng.uniform(.51,.71),end_y,rng.uniform(.75,1.17))
            turns=rng.uniform(3.5,5.5);phase=rng.uniform(0,6.28)
            curl=rng.uniform(.025,.059)
            path=[]
            for t in np.linspace(0,1,75):
                p=bezier(root,c1,c2,end,t)
                theta=phase+t*turns*2*math.pi
                p+=np.array([curl*math.sin(theta),.017*math.sin(theta*.7),curl*.76*math.cos(theta)])*math.sin(math.pi*t*.92)
                path.append(tuple(p))
            framepaths.append(path);frameradii.append(rng.uniform(.008,.015))
    for k in range(5):
        x=rng.uniform(-.31,.30)
        root=(x,7.64,1.25)
        end=(x+rng.uniform(-.05,.12),rng.uniform(6.99,7.22),1.43)
        path=[]
        for t in np.linspace(0,1,48):
            p=bezier(root,(x-.04,7.57,1.45),(x+.10,7.30,1.44),end,t)
            p[0]+=.038*math.sin(t*math.pi*6+k)
            p[2]+=.023*math.sin(t*math.pi*5+.4)
            path.append(tuple(p))
        framepaths.append(path);frameradii.append(.0075)
    frame=tubes('Inez_FramingCurls',framepaths,frameradii,transform,hairmat,sides=5)
    skin_rigid(frame,arm,'head');objects.append(frame)
    flyaways=[];flyradii=[]
    allpaths=crownpaths+ponypaths+framepaths
    for k in range(78):
        parent=allpaths[rng.integers(0,len(allpaths))]
        start=rng.integers(0,max(1,len(parent)//2))
        segment=parent[start:]
        path=[]
        direction=np.array([rng.uniform(-.16,.16),rng.uniform(-.05,.12),rng.uniform(-.11,.12)])
        for j,p in enumerate(segment):
            t=j/max(1,len(segment)-1)
            path.append(tuple(np.asarray(p)+direction*math.sin(math.pi*t)+.014*np.sin(t*37+k)))
        flyaways.append(path);flyradii.append(rng.uniform(.0018,.0038))
    fly=tubes('Inez_UnevenFineFlyaways',flyaways,flyradii,transform,fine_mat,sides=3)
    skin_rigid(fly,arm,'head');objects.append(fly)
    for obj in objects:
        obj['hair_geometry_status']='Actual UV-mapped skinned game mesh; curly original-guided groom prototype'
        obj['source_authority']='Original A framing/crown; original B high curly ponytail rear volume'
    return objects
