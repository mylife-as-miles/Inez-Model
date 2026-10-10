"""Bake geometric thickness on the actual fitted glTF skin (Blender BVH).

blender -b --python tools/inez/v06_thickness.py -- --input FILE.glb \
  --output VERSIONED.glb --report REPORT.json

Adds two custom vertex attributes only. Positions, UVs, skin weights, morphs,
clips and embedded maps retain their original accessors and bytes.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0,str(Path(__file__).resolve().parent))
from animation_validate_glb import Scene
from glb_expression_clips import read_glb,write_glb,add_accessor


def main():
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True);p.add_argument('--report',required=True)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    if Path(a.input).resolve()==Path(a.output).resolve():raise RuntimeError('Use a separate output')
    scene=Scene(a.input);gltf,binary=read_glb(a.input);report={'source':a.input,'output':a.output,'meshes':[],
        'method':'inward ray from fitted rest surface to opposing geometry; custom vertex attributes',
        'limitations':'open boundaries and rays without an opposing face are unknown (40 mm sentinel); not measured dermis thickness'}
    for mesh in gltf['meshes']:
        if 'ContinuousHumanMesh' not in mesh.get('name',''):continue
        defaults=mesh.get('weights',[])
        for primitive in mesh['primitives']:
            xyz=scene.accessor(primitive['attributes']['POSITION']).astype(np.float64)
            for weight,target in zip(defaults,primitive.get('targets',[])):
                if weight and 'POSITION' in target:xyz+=weight*scene.accessor(target['POSITION'])
            triangles=scene.accessor(primitive['indices']).ravel().astype(int).reshape(-1,3)
            normals=np.zeros_like(xyz)
            face=np.cross(xyz[triangles[:,1]]-xyz[triangles[:,0]],xyz[triangles[:,2]]-xyz[triangles[:,0]])
            for k in range(3):np.add.at(normals,triangles[:,k],face)
            normals/=np.maximum(np.linalg.norm(normals,axis=1,keepdims=True),1e-12)
            tree=BVHTree.FromPolygons([tuple(v) for v in xyz],[tuple(v) for v in triangles],all_triangles=True)
            thickness=np.full(len(xyz),.04,np.float32);valid=np.zeros(len(xyz),bool)
            for i,(v,n) in enumerate(zip(xyz,normals)):
                hit,normal,_,distance=tree.ray_cast(Vector(v-n*.0002),Vector(-n),.12)
                if hit is not None and normal.dot(Vector(n))<-.2 and distance>.0001:
                    thickness[i]=min(.12,distance+.0002);valid[i]=True
            # Anatomical lateral head band, refined by measured opposing
            # surface <8 mm. Only this mask receives the optional ear term.
            lateral=(np.abs(xyz[:,0])>.065)&(xyz[:,1]>1.44)&(xyz[:,1]<1.67)
            thin=(lateral&valid&(thickness<.008)).astype(np.float32)
            primitive['attributes']['_INEZ_THICKNESS']=add_accessor(gltf,binary,thickness,'SCALAR')
            primitive['attributes']['_INEZ_THIN_REGION']=add_accessor(gltf,binary,thin,'SCALAR')
            report['meshes'].append({'mesh':mesh['name'],'vertices':len(xyz),'bounds':[xyz.min(0).tolist(),xyz.max(0).tolist()],
                'valid_ray_count':int(valid.sum()),'thin_region_vertices':int(thin.sum()),
                'valid_thickness_mm_percentiles':(np.percentile(thickness[valid],[0,25,50,75,100])*1000).tolist() if valid.any() else []})
    gltf['buffers'][0]['byteLength']=len(binary)
    write_glb(a.output,gltf,binary);Path(a.report).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report['meshes']))


if __name__=='__main__':main()
