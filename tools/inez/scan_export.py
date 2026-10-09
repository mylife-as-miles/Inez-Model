"""Export an object's evaluated mesh (world space) to .npz for the scan-fit math.

    blender -b FILE.blend --python tools/inez/scan_export.py -- --object NAME --output OUT.npz \
        [--subdivide 2] [--attribute makehuman_source_index]

Writes vertices, triangles (fan-split polygons with their polygon index),
per-vertex UV (first loop), vertex normals and the optional integer point attribute. With --subdivide N a
Catmull-Clark copy is exported as well (`sub_vertices`, `sub_triangles`,
`sub_normals`), used as the smooth target surface so mesh faceting does not
leak into the fitted residual. Shape keys/modifiers are evaluated as they are
set in the file; nothing is saved back.
"""
import argparse
import sys

import bpy
import numpy as np


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('--object', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--subdivide', type=int, default=0)
    parser.add_argument('--attribute', default='')
    return parser.parse_args(sys.argv[sys.argv.index('--')+1:])


def mesh_arrays(obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    n = len(mesh.vertices)
    co = np.empty(n*3, np.float32)
    mesh.vertices.foreach_get('co', co)
    co = co.reshape(-1, 3)
    normals = np.empty(n*3, np.float32)
    mesh.vertex_normals.foreach_get('vector', normals)
    normals = normals.reshape(-1, 3)
    M = np.array(obj.matrix_world)
    co = co@M[:3, :3].T+M[:3, 3]
    normals = normals@np.linalg.inv(M[:3, :3])
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
    uv = None
    if mesh.uv_layers:
        loop_uv = np.empty(len(mesh.loops)*2, np.float32)
        mesh.uv_layers.active.data.foreach_get('uv', loop_uv)
        loop_vertex = np.empty(len(mesh.loops), np.int64)
        mesh.loops.foreach_get('vertex_index', loop_vertex)
        uv = np.zeros((n, 2), np.float32)
        # First loop of each vertex wins (assignment order is reversed).
        uv[loop_vertex[::-1]] = loop_uv.reshape(-1, 2)[::-1]
    tris, owner = [], []
    for poly in mesh.polygons:
        ids = list(poly.vertices)
        for k in range(1, len(ids)-1):
            tris.append((ids[0], ids[k], ids[k+1]))
            owner.append(poly.index)
    evaluated.to_mesh_clear()
    return co, np.array(tris, np.int32), normals, np.array(owner, np.int32), uv


def main():
    args = arguments()
    obj = bpy.data.objects[args.object]
    for mod in obj.modifiers:
        if mod.type == 'SUBSURF':
            mod.show_viewport = False
    out = {}
    out['vertices'], out['triangles'], out['normals'], out['triangle_polygon'], uv = mesh_arrays(obj)
    if uv is not None:
        out['uv'] = uv
    if args.attribute:
        attr = obj.data.attributes[args.attribute]
        values = np.empty(len(attr.data), np.int64)
        attr.data.foreach_get('value', values)
        out[args.attribute] = values
    if args.subdivide:
        mod = obj.modifiers.new('ExportSubdivision', 'SUBSURF')
        mod.levels = mod.render_levels = args.subdivide
        mod.show_viewport = True
        out['sub_vertices'], out['sub_triangles'], out['sub_normals'], _, _ = mesh_arrays(obj)
        obj.modifiers.remove(mod)
    out['matrix_world'] = np.array(obj.matrix_world, np.float64)
    np.savez_compressed(args.output, **out)
    print('SCAN_EXPORT', args.object, {k: v.shape for k, v in out.items()})


if __name__ == '__main__':
    main()
