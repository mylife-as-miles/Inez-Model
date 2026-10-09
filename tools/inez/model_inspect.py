"""Read-only object/UV/material/weight manifest for a real Blender source."""
import argparse,json,sys
from pathlib import Path
import bpy
p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
arm=next(o for o in bpy.data.objects if o.type=='ARMATURE')
meshes=[];issues=[]
for o in bpy.data.objects:
 if o.type!='MESH' or o.hide_render:continue
 sums=[sum(g.weight for g in v.groups)for v in o.data.vertices]
 mod=next((m for m in o.modifiers if m.type=='ARMATURE'),None)
 if mod is None:issues.append(o.name+' missing real skinning')
 if not o.data.uv_layers:issues.append(o.name+' missing UV')
 if any(abs(n-1)>1e-4 for n in sums):issues.append(o.name+' weights not normalized')
 meshes.append({'name':o.name,'vertices':len(o.data.vertices),'polygons':len(o.data.polygons),'uv_layers':[u.name for u in o.data.uv_layers],'skin_armature':mod.object.name if mod else None,'vertex_groups':len(o.vertex_groups),'weight_range':[min(sums),max(sums)],'materials':[m.name for m in o.data.materials if m],'shape_defaults':{k.name:k.value for k in o.data.shape_keys.key_blocks}if o.data.shape_keys else {}})
materials=[]
for m in bpy.data.materials:
 if not m.use_nodes:continue
 imgs=[n.image for n in m.node_tree.nodes if n.type=='TEX_IMAGE'and n.image]
 materials.append({'name':m.name,'uv_images':[i.name for i in imgs],'pbr_status':m.get('pbr_map_status'),'vermilion_topology':m.get('actual_vermilion_topology')})
report={'source':bpy.data.filepath,'stage':bpy.context.scene.get('INEZ_STAGE'),'bone_count':len(arm.data.bones),'bone_names':[b.name for b in arm.data.bones],'armature':arm.name,'meshes':meshes,'materials':materials,'packed_authored_maps':[{'name':i.name,'size':list(i.size),'packed':bool(i.packed_file),'path':i.filepath}for i in bpy.data.images if i.source=='GENERATED' or(i.filepath and '/textures/'in i.filepath)],'mesh_count':len(meshes),'source_technical_issues':issues,'production_approved':False}
Path(a.output).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'source':report['source'],'bone_count':report['bone_count'],'mesh_count':len(meshes),'issues':issues}))
