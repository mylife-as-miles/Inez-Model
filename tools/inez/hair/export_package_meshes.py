"""Blender: read the licensed hair package FBX files and save their meshes as NPZ
arrays in glTF space (metres, +Y up, +Z forward). Source files are only read.

blender -b --factory-startup -P export_package_meshes.py -- PACKAGE_DIR OUT_DIR
"""
import sys
from pathlib import Path
import bpy
import numpy as np

argv = sys.argv[sys.argv.index('--') + 1:]
pkg, out = Path(argv[0]), Path(argv[1])
out.mkdir(parents=True, exist_ok=True)
# Blender Z-up (-Y forward) -> glTF Y-up (+Z forward): (x, y, z) -> (x, z, -y)
TO_GLTF = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], float)


def mesh_arrays(obj):
    deps = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(deps)
    me = ev.to_mesh()
    me.calc_loop_triangles()
    mw = np.array(obj.matrix_world)
    n = len(me.vertices)
    co = np.empty(n * 3); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
    co = co @ mw[:3, :3].T + mw[:3, 3]
    nor = np.empty(n * 3); me.vertices.foreach_get('normal', nor); nor = nor.reshape(-1, 3)
    nor = nor @ np.linalg.inv(mw[:3, :3]).T
    nor /= np.maximum(np.linalg.norm(nor, axis=1, keepdims=True), 1e-12)
    tris = np.empty(len(me.loop_triangles) * 3, np.int64); me.loop_triangles.foreach_get('vertices', tris)
    tri_loops = np.empty(len(me.loop_triangles) * 3, np.int64); me.loop_triangles.foreach_get('loops', tri_loops)
    # per-vertex UV (cards have no UV seams inside a card; take the loop UV of each vertex)
    uv = np.zeros((n, 2))
    if me.uv_layers:
        luv = np.empty(len(me.loops) * 2); me.uv_layers[0].data.foreach_get('uv', luv); luv = luv.reshape(-1, 2)
        lv = np.empty(len(me.loops), np.int64); me.loops.foreach_get('vertex_index', lv)
        uv[lv] = luv
    # loose part ids (cards)
    parent = np.arange(n)
    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]; a = parent[a]
        return a
    ed = np.empty(len(me.edges) * 2, np.int64); me.edges.foreach_get('vertices', ed)
    for a, b in ed.reshape(-1, 2):
        ra, rb = find(a), find(b)
        if ra != rb: parent[ra] = rb
    roots = np.array([find(i) for i in range(n)])
    _, part = np.unique(roots, return_inverse=True)
    ev.to_mesh_clear()
    return dict(position=co @ TO_GLTF.T, normal=nor @ TO_GLTF.T, uv=uv, triangles=tris.reshape(-1, 3), part=part)


jobs = {'head': ('Female_Herad_Mesh.fbx', 'Female_Base_Head_geo'),
        'scalp': ('Female_Scalp_Mesh.fbx', 'Female_Xgen_Scalp_geo')}
for i in range(5):
    jobs[f'cards_lod{i}'] = (f'LODs/Female_Adult_001_HairCard_LOD{i}.fbx', f'Female_Adult_001_HarCards_LOD{i}')
for key, (fname, objname) in jobs.items():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(pkg / fname))
    obj = bpy.data.objects.get(objname) or next(o for o in bpy.context.scene.objects
        if o.type == 'MESH' and o.name.startswith(objname))
    arrays = mesh_arrays(obj)
    np.savez_compressed(out / f'{key}.npz', **arrays)
    print(key, obj.name, len(arrays['position']), 'verts', len(arrays['triangles']), 'tris', arrays['part'].max() + 1, 'parts',
          'y', arrays['position'][:, 1].min().round(3), arrays['position'][:, 1].max().round(3))
