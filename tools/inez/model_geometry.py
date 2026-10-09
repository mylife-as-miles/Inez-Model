"""Editable garment/accessory geometry and actual skinning helpers for Inez.

All input points are MakeHuman coordinates unless explicitly documented.
These are authoring operations. Importing this module creates no geometry.
"""
import math
import bpy
from mathutils import Vector
from mathutils.kdtree import KDTree
from model_source import source_weight_vectors


def mesh_object(name, points, faces, transform, material, uv_faces=None):
    mesh = bpy.data.meshes.new(name+'_Geometry')
    mesh.from_pydata([transform(p) for p in points], [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    uv = mesh.uv_layers.new(name='Inez_Authored_UV')
    for poly in mesh.polygons:
        poly.use_smooth = True
        for corner,li in enumerate(poly.loop_indices):
            if uv_faces is not None:
                uv.data[li].uv=uv_faces[poly.index][corner]
            else:
                co=points[mesh.loops[li].vertex_index]
                uv.data[li].uv=(co[0]*0.25+0.5,co[1]*0.125+1.0)
    obj['geometry_author']='Original-reference-guided editable reconstruction'
    obj['identity_status']='UNAPPROVED prototype until independent actual-render critique'
    return obj


def skin_rigid(obj, arm, bone):
    if bone not in arm.data.bones:
        raise KeyError('Missing real rig bone: '+bone)
    vg=obj.vertex_groups.new(name=bone)
    vg.add(list(range(len(obj.data.vertices))),1.0,'REPLACE')
    mod=obj.modifiers.new('Inez_Rig_Skin','ARMATURE')
    mod.object=arm
    obj.parent=arm
    obj['weight_authoring']='Rigid actual '+bone+' bone; no dummy unweighted rig'


def skin_source_nearest(obj, arm, source_points, weights, transform):
    """Interpolate six actual body weight vectors for seams/accessories."""
    ids=list(range(13380))
    normalized=source_weight_vectors(weights,ids)
    tree=KDTree(len(ids))
    for i in ids:
        tree.insert(Vector(transform(source_points[i])),i)
    tree.balance()
    groups={name:obj.vertex_groups.new(name=name) for name in weights['weights']}
    for vertex in obj.data.vertices:
        samples=tree.find_n(vertex.co,6)
        raw=[1/max(distance,0.00015)**2 for _,_,distance in samples]
        divisor=sum(raw)
        accum={}
        for (_,index,_),value in zip(samples,raw):
            for bone,weight in normalized[index].items():
                accum[bone]=accum.get(bone,0)+value*weight/divisor
        total=sum(accum.values())
        for bone,value in accum.items():
            groups[bone].add([vertex.index],value/total,'REPLACE')
    mod=obj.modifiers.new('Inez_Interpolated_Licensed_Weights','ARMATURE')
    mod.object=arm
    obj.parent=arm
    obj['weight_authoring']='Normalized interpolation of six nearest licensed body weight vectors'


def loft(name, rings, transform, material, capped=True):
    """Real connected quad surface through equal-sized garment/boot rings."""
    n=len(rings[0])
    if any(len(r)!=n for r in rings):
        raise ValueError('Loft rings must have equal resolution')
    points=[p for ring in rings for p in ring]
    faces=[]
    uv=[]
    for row in range(len(rings)-1):
        for i in range(n):
            j=(i+1)%n
            faces.append((row*n+i,row*n+j,(row+1)*n+j,(row+1)*n+i))
            uv.append([(i/n,row/(len(rings)-1)),((i+1)/n,row/(len(rings)-1)),
                       ((i+1)/n,(row+1)/(len(rings)-1)),(i/n,(row+1)/(len(rings)-1))])
    if capped:
        # Explicit UV triangle fans keep platform caps planar and exportable
        # with tangent-space normal maps; large cap n-gons lack valid tangents.
        for row,reverse in [(0,True),(len(rings)-1,False)]:
            center=len(points)
            points.append(tuple(sum(p[a]for p in rings[row])/n for a in range(3)))
            for i in range(n):
                j=(i+1)%n
                indices=(center,row*n+j,row*n+i)if reverse else(center,row*n+i,row*n+j)
                corners=[(.5,.5),(.5+.48*math.cos(2*math.pi*i/n),.5+.48*math.sin(2*math.pi*i/n)),
                         (.5+.48*math.cos(2*math.pi*j/n),.5+.48*math.sin(2*math.pi*j/n))]
                faces.append(indices)
                uv.append([corners[0],corners[2],corners[1]]if reverse else corners)
    obj=mesh_object(name,points,faces,transform,material,uv)
    if capped:
        for poly in obj.data.polygons[(len(rings)-1)*n:]:
            poly.use_smooth=False
    return obj


def tubes(name, paths, radii, transform, material, sides=5):
    """Game-exportable continuous mesh strands/laces, with cylindrical UVs."""
    points=[]
    faces=[]
    uv=[]
    for path_index,path in enumerate(paths):
        if len(path)<2:
            continue
        start=len(points)
        previous_axis=Vector((1,0,0))
        radius=radii[path_index] if isinstance(radii,list) else radii
        for k,p in enumerate(path):
            p=Vector(p)
            tangent=Vector(path[min(k+1,len(path)-1)])-Vector(path[max(0,k-1)])
            tangent.normalize()
            axis=previous_axis-tangent*previous_axis.dot(tangent)
            if axis.length<1e-8:
                axis=tangent.cross(Vector((0,0,1)))
            axis.normalize()
            other=tangent.cross(axis).normalized()
            previous_axis=axis
            taper=max(0.16,min(1.0,4*(1-k/(len(path)-1))))
            for s in range(sides):
                theta=2*math.pi*s/sides
                points.append(tuple(p+radius*taper*(math.cos(theta)*axis+math.sin(theta)*other)))
        for k in range(len(path)-1):
            for s in range(sides):
                s1=(s+1)%sides
                faces.append((start+k*sides+s,start+k*sides+s1,
                              start+(k+1)*sides+s1,start+(k+1)*sides+s))
                uv.append([(s/sides,k/(len(path)-1)),((s+1)/sides,k/(len(path)-1)),
                           ((s+1)/sides,(k+1)/(len(path)-1)),(s/sides,(k+1)/(len(path)-1))])
    return mesh_object(name,points,faces,transform,material,uv)


def boundary_loops(obj):
    counts={}
    for poly in obj.data.polygons:
        for edge in poly.edge_keys:
            edge=tuple(sorted(edge))
            counts[edge]=counts.get(edge,0)+1
    adjacency={}
    for (a,b),count in counts.items():
        if count==1:
            adjacency.setdefault(a,[]).append(b)
            adjacency.setdefault(b,[]).append(a)
    loops=[]
    visited=set()
    for start in adjacency:
        if start in visited:
            continue
        loop=[start]
        previous=None
        current=start
        for _ in range(len(adjacency)+1):
            visited.add(current)
            nexts=[i for i in adjacency[current]if i!=previous]
            if not nexts:
                break
            nxt=nexts[0]
            if nxt==start:
                break
            loop.append(nxt)
            previous,current=current,nxt
        loops.append(loop)
    return loops


def apply_static_modifier(obj, modifier):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active=obj
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    obj.select_set(False)


def actual_thickness(obj, thickness_m=0.0022):
    """Applied thickness survives GLB rather than depending on render modifiers."""
    modifier=obj.modifiers.new('Authored_real_cloth_thickness','SOLIDIFY')
    modifier.thickness=thickness_m
    modifier.offset=-1.0
    modifier.use_even_offset=True
    apply_static_modifier(obj,modifier)
    obj['cloth_thickness_m']=thickness_m


def smooth_geometry(obj, levels=1):
    modifier=obj.modifiers.new('Authored_surface_refinement','SUBSURF')
    modifier.levels=levels
    modifier.render_levels=levels
    apply_static_modifier(obj,modifier)


def torus_source(name, center, major_radius, minor_radius, transform, material,
                 orientation='front',major_segments=16,minor_segments=6):
    points=[]
    for i in range(major_segments):
        a=2*math.pi*i/major_segments
        for j in range(minor_segments):
            b=2*math.pi*j/minor_segments
            x=(major_radius+minor_radius*math.cos(b))*math.cos(a)
            y=(major_radius+minor_radius*math.cos(b))*math.sin(a)
            z=minor_radius*math.sin(b)
            if orientation=='front':
                delta=(x,y,z)
            elif orientation=='top':
                delta=(x,z,y)
            else:
                delta=(z,x,y)
            points.append(tuple(center[k]+delta[k]for k in range(3)))
    faces=[]
    for i in range(major_segments):
        for j in range(minor_segments):
            faces.append((i*minor_segments+j,((i+1)%major_segments)*minor_segments+j,
                          ((i+1)%major_segments)*minor_segments+(j+1)%minor_segments,
                          i*minor_segments+(j+1)%minor_segments))
    return mesh_object(name,points,faces,transform,material)
