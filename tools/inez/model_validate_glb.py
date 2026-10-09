"""Inspect actual GLB data and buffer structure. No visual approval is inferred."""
import argparse
from pathlib import Path
import struct
import json

parser=argparse.ArgumentParser()
parser.add_argument('glb')
parser.add_argument('--output',required=True)
args=parser.parse_args()
data=Path(args.glb).read_bytes()
magic,version,length=struct.unpack_from('<4sII',data,0)
assert magic==b'glTF'and version==2 and length==len(data),'Invalid GLB header/length'
offset=12
chunks=[]
while offset<len(data):
    size,kind=struct.unpack_from('<II',data,offset)
    chunks.append((kind,data[offset+8:offset+8+size]))
    offset+=8+size
assert offset==len(data),'Invalid chunk boundary'
document=json.loads(next(value for kind,value in chunks if kind==0x4E4F534A).decode())
binary=next((value for kind,value in chunks if kind==0x004E4942),b'')
issues=[]
for index,view in enumerate(document.get('bufferViews',[])):
    if view.get('buffer',0)!=0:issues.append(f'BufferView {index} external buffer unsupported by validator')
    if view.get('byteOffset',0)+view['byteLength']>len(binary):issues.append(f'BufferView {index} overruns GLB binary')
for mi,mesh in enumerate(document.get('meshes',[])):
    for pi,primitive in enumerate(mesh['primitives']):
        attrs=primitive.get('attributes',{})
        if 'POSITION'not in attrs:issues.append(f'Mesh {mi} primitive {pi} has no positions')
        if 'TEXCOORD_0'not in attrs:issues.append(f'Mesh {mi} primitive {pi} lacks UV coordinates')
        if 'NORMAL'not in attrs:issues.append(f'Mesh {mi} primitive {pi} lacks normals')
for si,skin in enumerate(document.get('skins',[])):
    if not skin.get('joints'):issues.append(f'Skin {si} has no joints')
    if 'inverseBindMatrices'not in skin:issues.append(f'Skin {si} has no inverse binds')
    if any(n>=len(document['nodes'])for n in skin['joints']):issues.append(f'Skin {si} references missing nodes')
external_resources=[img['uri']for img in document.get('images',[])if 'uri'in img and not img['uri'].startswith('data:')]
report={
    'file':args.glb,'bytes':len(data),'header_version':version,
    'meshes':len(document.get('meshes',[])),
    'nodes':len(document.get('nodes',[])),
    'materials':len(document.get('materials',[])),
    'skins':len(document.get('skins',[])),
    'joints_per_skin':[len(s['joints'])for s in document.get('skins',[])],
    'animations':[a.get('name',str(i))for i,a in enumerate(document.get('animations',[]))],
    'morph_meshes':sum(any(p.get('targets')for p in m['primitives'])for m in document.get('meshes',[])),
    'external_image_resources':external_resources,
    'structural_issues':issues,
    'structural_validation_passed':not issues and not external_resources,
    'browser_render_validation':'requires real viewer screenshots; this validator does not assess rendering',
    'artistic_identity_approval':False,
}
Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
raise SystemExit(0 if report['structural_validation_passed']else 1)
