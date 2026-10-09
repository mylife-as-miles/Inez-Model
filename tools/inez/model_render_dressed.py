"""Render the stable actual dressed rest snapshot without editing final source."""
import sys,json,math,argparse
from pathlib import Path
import bpy
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parent))
from model_build import point_camera
p=argparse.ArgumentParser();p.add_argument('--output-dir',required=True);p.add_argument('--samples',type=int,default=32);p.add_argument('--views',nargs='+',default=['front','portrait_front','portrait_three_quarter','back']);a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=True)
s=bpy.context.scene;s.render.resolution_x=s.render.resolution_y=1024;s.render.resolution_percentage=100;s.cycles.samples=a.samples;s.cycles.use_denoising=False;s.render.image_settings.file_format='PNG';cam=s.camera
body=bpy.data.objects['Inez_ContinuousHumanMesh_UNAPPROVED'];keys=body.data.shape_keys.key_blocks;fit=keys['Inez_HeadFit_v03'];attr=body.data.attributes['makehuman_source_index'];lookup={d.value:i for i,d in enumerate(attr.data)};eyes=[Vector(fit.data[lookup[i]].co)for i in [6785,6784]];headtarget=Vector((0,-.05,sum(v.z for v in eyes)/len(eyes)+.005))
views={};angles={'front':0,'left_profile':90,'right_profile':-90,'back':180,'three_quarter':35,'portrait_front':0,'portrait_three_quarter':35}
for name in a.views:
 target=headtarget if name.startswith('portrait')else Vector((0,0,.86));cam.data.ortho_scale=.338 if name.startswith('portrait')else 1.94;r=math.radians(angles[name]);cam.location=target+Vector((3*math.sin(r),-3*math.cos(r),0));point_camera(cam,target);s.render.filepath=str(out/(name+'.png'));bpy.ops.render.render(write_still=True);views[name]=s.render.filepath;print('ACTUAL_DRESSED_RENDER_READY '+name,flush=True)
manifest={'source':bpy.data.filepath,'renderer':'Blender 4.3.2 Cycles actual rest mesh; browser fidelity remains separate','views':views,'final_source_modified':False,'identity_approved':False};(out/'render_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
