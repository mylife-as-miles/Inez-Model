"""UV-space PBR authoring for the actual Inez mesh, without photo projection.

Skin/fabric maps use barycentric source-UV rasterization of fitted geometry.
Freckles and unseen microdetail are disclosed reconstruction/extrapolation.
Importing does not author maps: callers must enforce the credible-head gate.
"""
from pathlib import Path
import json
import math
import bpy
import numpy as np


def material(name,color,roughness=0.6,metallic=0.0):
    mat=bpy.data.materials.new(name)
    mat.use_nodes=True
    bsdf=mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value=(*color,1)
    bsdf.inputs['Roughness'].default_value=roughness
    bsdf.inputs['Metallic'].default_value=metallic
    return mat


def save_image(name,array,directory,noncolor=False):
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    height,width=array.shape[:2]
    if array.ndim==2:
        array=np.repeat(array[:,:,None],3,axis=2)
    rgba=np.ones((height,width,4),dtype=np.float32)
    rgba[:,:,:3]=np.clip(array,0,1)
    img=bpy.data.images.new(name,width=width,height=height,alpha=True)
    img.colorspace_settings.name='Non-Color' if noncolor else 'sRGB'
    # Source UV origin is lower left, matching Blender pixels and glTF UVs.
    img.pixels.foreach_set(rgba.reshape(-1))
    img.filepath_raw=str(directory/(name+'.png'))
    img.file_format='PNG'
    img.save()
    img.pack()
    return img


def connect_pbr(mat,albedo,roughness,normal,normal_strength=0.24):
    nodes=mat.node_tree.nodes
    links=mat.node_tree.links
    bsdf=nodes.get('Principled BSDF')
    for img,slot in [(albedo,'Base Color'),(roughness,'Roughness')]:
        node=nodes.new('ShaderNodeTexImage')
        node.image=img
        node.label=slot+' — actual authored UV map'
        links.new(node.outputs['Color'],bsdf.inputs[slot])
    normaltex=nodes.new('ShaderNodeTexImage')
    normaltex.image=normal
    normaltex.label='Separate tangent normal microdetail'
    normalnode=nodes.new('ShaderNodeNormalMap')
    normalnode.inputs['Strength'].default_value=normal_strength
    links.new(normaltex.outputs['Color'],normalnode.inputs['Color'])
    links.new(normalnode.outputs['Normal'],bsdf.inputs['Normal'])
    mat['pbr_map_status']='Separate authored UV albedo, roughness, normal maps embedded in GLB'


def uv_point_raster(points,texcoords,faces,resolution):
    """Rasterize 3D surface positions into each actual indexed UV triangle."""
    points=np.asarray(points,dtype=np.float32)
    texcoords=np.asarray(texcoords,dtype=np.float32)
    raster=np.zeros((resolution,resolution,3),np.float32)
    mask=np.zeros((resolution,resolution),bool)
    for face in faces:
        for j in range(1,len(face)-1):
            tri=[face[0],face[j],face[j+1]]
            xyz=points[[v for v,t in tri]]
            uv=texcoords[[t for v,t in tri]]*(resolution-1)
            lo=np.maximum(0,np.floor(uv.min(axis=0)).astype(int))
            hi=np.minimum(resolution-1,np.ceil(uv.max(axis=0)).astype(int))
            if (hi<lo).any():
                continue
            xx,yy=np.meshgrid(np.arange(lo[0],hi[0]+1),np.arange(lo[1],hi[1]+1))
            den=((uv[1,1]-uv[2,1])*(uv[0,0]-uv[2,0])+
                 (uv[2,0]-uv[1,0])*(uv[0,1]-uv[2,1]))
            if abs(den)<1e-9:
                continue
            a=((uv[1,1]-uv[2,1])*(xx-uv[2,0])+(uv[2,0]-uv[1,0])*(yy-uv[2,1]))/den
            b=((uv[2,1]-uv[0,1])*(xx-uv[2,0])+(uv[0,0]-uv[2,0])*(yy-uv[2,1]))/den
            c=1-a-b
            inside=(a>=-0.008)&(b>=-0.008)&(c>=-0.008)
            coordinates=a[:,:,None]*xyz[0]+b[:,:,None]*xyz[1]+c[:,:,None]*xyz[2]
            region=raster[lo[1]:hi[1]+1,lo[0]:hi[0]+1]
            region[inside]=coordinates[inside]
            mask[lo[1]:hi[1]+1,lo[0]:hi[0]+1]|=inside
    return raster,mask


def dilate_maps(arrays,mask,passes=5):
    mask=mask.copy()
    arrays=[a.copy()for a in arrays]
    for _ in range(passes):
        counts=np.zeros(mask.shape,np.float32)
        accum=[np.zeros_like(a)for a in arrays]
        for dy,dx in [(1,0),(-1,0),(0,1),(0,-1)]:
            shifted=np.roll(mask,(dy,dx),(0,1))
            counts+=shifted
            for out,arr in zip(accum,arrays):
                values=np.roll(arr,(dy,dx),(0,1))
                out+=values*shifted[:,:,None] if arr.ndim==3 else values*shifted
        added=(~mask)&(counts>0)
        for arr,out in zip(arrays,accum):
            arr[added]=out[added]/counts[added,None] if arr.ndim==3 else out[added]/counts[added]
        mask|=added
    return arrays


def normal_from_height(height,strength=0.08):
    dy,dx=np.gradient(height)
    normal=np.stack((-dx*strength,-dy*strength,np.ones_like(height)),axis=2)
    normal/=np.linalg.norm(normal,axis=2)[:,:,None]
    return normal*0.5+0.5


def actual_lip_color_field(raster,points):
    """Follow fitted exterior vermilion rows in the preserved actual UV layout.

    These indexed anatomical borders follow every real head fit. The source
    seam and Cupid's bow remain geometry; this authors only muted surface color.
    """
    upper_ids=[362,357,356,355,409,410,375,363,407,402]
    lower_ids=[492,486,480,406,405,404,403,402]
    points=np.asarray(points,dtype=np.float32)
    def contour(ids):
        rows=points[ids]
        order=np.argsort(abs(rows[:,0]))
        return abs(rows[order,0]),rows[order,1],rows[order,2]
    ux,uy,uz=contour(upper_ids)
    lx,ly,lz=contour(lower_ids)
    x,y,z=raster[:,:,0],raster[:,:,1],raster[:,:,2]
    xx=abs(x)
    top=np.interp(xx,ux,uy)
    bottom=np.interp(xx,lx,ly)
    front=np.minimum(np.interp(xx,ux,uz),np.interp(xx,lx,lz))-.033
    # Soft natural border, retaining the fitted topological Cupid's bow and
    # fuller lower lip. No hard-coded seam height or invented color ellipse.
    weight=np.clip((top-y)/.007,0,1)*np.clip((y-bottom)/.007,0,1)
    weight*=np.clip((min(ux[-1],lx[-1])-xx)/.006,0,1)
    weight*=np.clip((z-front)/.012,0,1)
    return weight.astype(np.float32),{'upper_source_vertices':upper_ids,
        'lower_source_vertices':lower_ids,'actual_half_width_source':float(min(ux[-1],lx[-1])),
        'upper_center_height_source':float(uy[0]),'lower_center_height_source':float(ly[0])}


def skin_pbr(points,texcoords,faces,directory,resolution=2048):
    raster,mask=uv_point_raster(points,texcoords,faces,resolution)
    x,y,z=raster[:,:,0],raster[:,:,1],raster[:,:,2]
    noise=(np.sin(127*x+151*y+117*z)+0.43*np.sin(509*x-419*y+277*z)+
           0.21*np.sin(1497*x+1359*y-2197*z))/1.64
    albedo=np.empty((*mask.shape,3),np.float32)
    albedo[:]=[0.57,0.384,0.287]
    albedo+=noise[:,:,None]*np.array([.010,.007,.005])
    front=np.clip((z-.8)*4,0,1)
    cheeks=np.exp(-((abs(x)-.36)/.27)**2-((y-6.47)/.23)**2)*front
    nose=np.exp(-(x/.18)**2-((y-6.53)/.22)**2)*front
    albedo+=cheeks[:,:,None]*np.array([.035,-.008,-.004])
    albedo+=nose[:,:,None]*np.array([.028,-.006,-.008])
    under=np.exp(-((abs(x)-.29)/.20)**2-((y-6.66)/.066)**2)*front
    albedo-=under[:,:,None]*np.array([.041,.035,.023])
    rng=np.random.default_rng(1299)
    freckle=np.zeros(mask.shape,np.float32)
    headmask=mask&(y>6.27)&(y<7.55)&(z>.80)
    hx,hy=x[headmask],y[headmask]
    headfreckle=np.zeros(hx.shape,np.float32)
    # Concentration follows original nose/upper cheek pattern; exact hidden marks unknown.
    for _ in range(240):
        fx=rng.uniform(-.53,.53)
        fy=rng.normal(6.58,.125)
        if abs(fx)<.10 and fy>6.78:
            continue
        radius=rng.uniform(.004,.013)
        spot=np.exp(-(((hx-fx)/radius)**2+((hy-fy)/(radius*rng.uniform(.65,1.35)))**2)*1.5)
        headfreckle+=spot*rng.uniform(.11,.29)
    for _ in range(35):
        fx=rng.uniform(-.48,.48);fy=rng.uniform(6.97,7.38);radius=rng.uniform(.004,.010)
        headfreckle+=np.exp(-(((hx-fx)/radius)**2+((hy-fy)/radius)**2))*rng.uniform(.08,.15)
    freckle[headmask]=headfreckle*front[headmask]
    albedo-=np.minimum(freckle,.39)[:,:,None]*np.array([.28,.21,.15])
    lipweight,lip_topology=actual_lip_color_field(raster,points)
    lipmask=lipweight>.001
    lipgrain=(np.sin(x*1730+y*41)+.3*np.sin(x*2871-y*107))*.007
    lipcolor=np.array([.44,.247,.213])+lipgrain[:,:,None]
    albedo=albedo*(1-lipweight[:,:,None])+lipcolor*lipweight[:,:,None]
    rough=np.full(mask.shape,.59,np.float32)
    rough-=nose*.13
    rough-=np.exp(-(x/.5)**2-((y-7.14)/.29)**2)*front*.055
    rough+=noise*.016
    rough=rough*(1-lipweight)+(.43+lipgrain*1.6)*lipweight
    pore=(np.sin(x*3481+y*2279+z*1447)+.47*np.sin(x*5963-y*4311+z*3757))
    height=pore*.19+noise*.05
    height=height*(1-lipweight)+np.sin(x*1730+y*41)*.27*lipweight
    normal=normal_from_height(height,.26)
    albedo,rough,normal=dilate_maps([albedo,rough,normal],mask)
    images=[save_image('inez_skin_albedo',albedo,directory),
            save_image('inez_skin_roughness',rough,directory,True),
            save_image('inez_skin_normal',normal,directory,True)]
    mat=material('Inez_Skin_Freckles_Pores_Lips_PBR',(0.57,.384,.287),.59)
    connect_pbr(mat,*images,normal_strength=.24)
    bsdf=mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Subsurface Weight'].default_value=.045
    bsdf.inputs['Subsurface Radius'].default_value=(1.0,.42,.24)
    bsdf.inputs['IOR'].default_value=1.42
    mat['texture_evidence']='Original A qualitative freckle clusters/tonal variation; procedural UV reconstruction, not photo projection'
    mat['hidden_surface_status']='Unseen marks and pores are extrapolated; not calibrated source albedo'
    mat['actual_vermilion_topology']=json.dumps(lip_topology)
    return mat


def fabric_pbr(name,points,texcoords,faces,directory,kind='knit',resolution=2048):
    raster,mask=uv_point_raster(points,texcoords,faces,resolution)
    x,y,z=raster[:,:,0],raster[:,:,1],raster[:,:,2]
    albedo=np.empty((*mask.shape,3),np.float32)
    noise=np.sin(139*x+271*y+143*z)*.5+np.sin(729*x-617*y+383*z)*.25
    if kind=='knit':
        # Exactly three broad torso bands; gray neck and ribbed hem are preserved.
        virtual_y=y.copy()
        arms=abs(x)>1.28
        shoulder_y=4.57
        distance=np.sqrt((abs(x)-1.54)**2+(y-shoulder_y)**2+(z-.25)**2)
        virtual_y[arms]=shoulder_y-distance[arms]
        dark=((virtual_y>3.75)&(virtual_y<4.28))|((virtual_y>2.82)&(virtual_y<3.31))|((virtual_y>1.91)&(virtual_y<2.39))
        # Additional sleeve bands below the torso hem; cuffs remain gray.
        dark|=arms&(virtual_y>.35)&(virtual_y<.82)
        albedo[:]=[.22,.23,.235]
        albedo[dark]=[.055,.062,.075]
        weave=np.maximum(0,np.cos(x*145+np.sin(y*219)*.65))**5*np.sin(y*219)
        albedo+=weave[:,:,None]*.013+noise[:,:,None]*.008
        rough=np.full(mask.shape,.89,np.float32)+noise*.025
        height=weave*.80+np.sin(x*737+y*519)*.10
        normalstrength=.6
    else:
        albedo[:]=[.051,.055,.054]
        diagonal=np.sin((x+y)*745)*np.sin((x-y)*429)
        wash=np.sin(x*6.7+y*4.1+z*3.2)*.005+noise*.0028
        albedo+=wash[:,:,None]+diagonal[:,:,None]*.003
        rough=np.full(mask.shape,.87,np.float32)+noise*.025
        height=diagonal*.26+np.sin(x*2399-y*971)*.035
        normalstrength=.40
    normal=normal_from_height(height,.22)
    albedo,rough,normal=dilate_maps([albedo,rough,normal],mask)
    images=[save_image(name+'_albedo',albedo,directory),save_image(name+'_roughness',rough,directory,True),
            save_image(name+'_normal',normal,directory,True)]
    mat=material('Inez_'+name+'_PBR',(.15,.15,.15),.86)
    connect_pbr(mat,*images,normal_strength=normalstrength)
    mat['original_evidence']='Original B costume construction/phase/near-black material; UV-space authored reconstruction'
    return mat


def iris_pbr(directory,resolution=512):
    q=np.linspace(-1,1,resolution,dtype=np.float32)
    x,y=np.meshgrid(q,q)
    r=np.sqrt(x*x+y*y);a=np.arctan2(y,x)
    fibers=(np.sin(a*127+r*27)+.5*np.sin(a*239-r*71)+.3*np.sin(a*411+r*113))/1.8
    albedo=np.empty((resolution,resolution,3),np.float32)
    albedo[:]=[.24,.285,.19]
    center=np.exp(-((r-.31)/.23)**2)
    albedo+=center[:,:,None]*np.array([.070,.026,-.028])
    albedo+=fibers[:,:,None]*np.array([.025,.028,.015])
    limbal=np.clip((r-.79)/.21,0,1)
    albedo*=1-limbal[:,:,None]*.55
    rough=np.full((resolution,resolution),.51,np.float32)
    normal=normal_from_height(fibers*.16,.18)
    images=[save_image('inez_iris_olive_hazel_albedo',albedo,directory),
            save_image('inez_iris_roughness',rough,directory,True),save_image('inez_iris_normal',normal,directory,True)]
    mat=material('Inez_Muted_GreenHazel_Iris_PBR',(.24,.285,.19),.51)
    connect_pbr(mat,*images,normal_strength=.09)
    return mat


def detail_tile(name,directory,color,roughness,kind,resolution=512):
    q=np.arange(resolution,dtype=np.float32)/resolution
    u,v=np.meshgrid(q,q)
    if kind=='hair':
        grain=np.sin(u*math.pi*2*43+np.sin(v*math.pi*4)*.9)*.48+np.sin(u*math.pi*2*107)*.25
        normalstrength=.32
    elif kind=='leather':
        grain=np.sin(u*2*math.pi*157+np.sin(v*2*math.pi*127))*np.sin(v*2*math.pi*173)
        normalstrength=.22
    elif kind=='cornea':
        grain=np.zeros_like(u)
        normalstrength=.02
    elif kind=='ribbed':
        grain=np.cos(u*2*math.pi*64)*.82+np.sin(v*2*math.pi*113)*.13
        normalstrength=.67
    else:
        grain=np.sin(u*2*math.pi*79)*np.sin(v*2*math.pi*89)
        normalstrength=.10
    albedo=np.zeros((resolution,resolution,3),np.float32)+np.asarray(color)
    albedo+=grain[:,:,None]*.004
    rough=np.full((resolution,resolution),roughness,np.float32)+grain*.022
    normal=normal_from_height(grain*.35,.18)
    images=[save_image(name+'_albedo',albedo,directory),save_image(name+'_roughness',rough,directory,True),
            save_image(name+'_normal',normal,directory,True)]
    mat=material('Inez_'+name+'_PBR',color,roughness)
    connect_pbr(mat,*images,normal_strength=normalstrength)
    return mat
