"""One-time actual boot cap geometry correction before motion ownership handoff."""
import sys,bpy,bmesh
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from model_dress import export_glb
root=Path('/workspace/assets/characters/inez/model')
for side in ['L','R']:
 o=bpy.data.objects['Inez_Boot_Sole_'+side];bm=bmesh.new();bm.from_mesh(o.data)
 caps=[f for f in bm.faces if len(f.verts)>4]
 for f in caps:f.smooth=False
 bmesh.ops.triangulate(bm,faces=caps,quad_method='BEAUTY',ngon_method='BEAUTY');bm.to_mesh(o.data);bm.free();o.data.update()
 o['cap_tangent_correction']='Actual cap n-gons triangulated, UVs/weights retained'
bpy.ops.wm.save_as_mainfile(filepath=str(root/'inez.blend'))
bpy.ops.wm.save_as_mainfile(filepath=str(root/'work/inez_dressed_v03.blend'),copy=True)
export_glb(root/'inez.glb')
print('STABLE_DRESSED_SOURCE_READY',flush=True)
