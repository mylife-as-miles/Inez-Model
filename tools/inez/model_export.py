"""Export an existing editable Blender fit; never promote it to production.

Run Blender with the fitted .blend then --python this file -- --output FILE.
This script records technical glTF readiness separately from artistic approval.
"""
import argparse
from pathlib import Path
import sys
import json
import bpy

parser=argparse.ArgumentParser()
parser.add_argument('--output',required=True)
parser.add_argument('--manifest',required=True)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
output=Path(args.output)
output.parent.mkdir(parents=True,exist_ok=True)
bpy.ops.object.select_all(action='DESELECT')
objects=[]
for obj in bpy.context.scene.objects:
    if obj.type in ('MESH','ARMATURE') and not obj.hide_render:
        obj.select_set(True)
        objects.append(obj)
        if obj.type=='MESH':
            obj['artistic_approval']='UNAPPROVED editable geometry fitting prototype'
bpy.context.view_layer.objects.active=next((o for o in objects if o.type=='ARMATURE'),objects[0])
bpy.ops.export_scene.gltf(filepath=str(output),export_format='GLB',
    use_selection=True,export_yup=True,export_texcoords=True,export_normals=True,
    export_tangents=True,export_skins=True,export_morph=True,
    export_animations=True,export_cameras=False,export_lights=False,
    export_extras=True,export_apply=False)
manifest={
    'file':str(output),
    'blend_source':bpy.data.filepath,
    'stage':bpy.context.scene.get('INEZ_STAGE','Unapproved fitting prototype'),
    'production_approved':False,
    'object_names':[o.name for o in objects],
    'skinned_objects':[o.name for o in objects if o.type=='MESH' and any(m.type=='ARMATURE'for m in o.modifiers)],
    'uv_layers':{o.name:[u.name for u in o.data.uv_layers]for o in objects if o.type=='MESH'},
    'animation_test_status':'pending; exported data is not a passed deformation test',
    'source_license':'CC0-1.0 for MakeHuman source assets; see model/base-source',
}
Path(args.manifest).write_text(json.dumps(manifest,indent=2)+'\n')
print('INEZ_EXPORT_MANIFEST '+json.dumps(manifest))

