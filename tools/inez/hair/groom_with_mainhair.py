"""Blender: grow Inez's hair strands from restyled guides with the user's MainHair node group.

    blender -b --factory-startup --disable-autoexec -P tools/inez/hair/groom_with_mainhair.py -- \
        HairNodes.blend GUIDES.npz HEAD.npz OUT_STRANDS.npz OUT.blend REPORT.json [--amount 20]

HairNodes.blend (supplied by the user) holds one Blender 3.4 geometry-nodes
group, "MainHair": Hair Amount -> Spread/Clumping -> Points Count -> Random
Length -> Stick To Mesh -> Noise -> Delete Hair -> Hair Thickness -> Curl ->
Roughness. The source file is only read; a copy, "MainHair_Inez", is changed
in parameters only (its node layout stays the user's), because its values were
authored for a much larger scene (hair 1-2.7 units long, ±5-10 cm noise) and
its curl was effectively off (Curl Scale 0.01, 6 points, curl circle in a
plane containing the strand). Every change is listed in the report:

  Deform Curves on Surface   bypassed: the guides are a static rest groom
  guide_id                   stored per curve before duplication (binding)
  Hair Amount                Duplicate Elements Amount 2 -> --amount
  Spread                     0.8 x 0.02 -> 0.8 x 0.004 (--spread)
  Points Count               8 -> 16 (guides have 16 points)
  Random Length              absolute 1.0-2.7 -> factor 0.75-1.0 of each guide
  Stick To Mesh              object = Inez's rendered head surface
  Noise                      scale 0.1 -> 0.003 (--noise)
  Clumping                   root x5 -> x4, tip x1.5 -> x0.5 (--clump-root/--clump-tip): converging clumps
  Roughness (flyaways)       41 % x 0.2 -> 4 % x 0.006 (--rough-prob, --rough-scale)
  Curl                       resample 6 -> 40 points, Curl Scale 0.01 -> 8 turns (--curl-points, --curl-turns),
                             per-clump factor 0.6-1 (random ID = guide_id), Curl Shape 0.2 -> 0.005 m,
                             curl circle perpendicular to the strand (Z axis) = helix
Positions are glTF metres (+Y up); orientation does not matter to the graph.
"""
import json
import sys
from pathlib import Path

import bpy
import numpy as np

argv = sys.argv[sys.argv.index('--') + 1:]
nodes_blend, guides_npz, head_npz, out_npz, out_blend, report_path = argv[:6]
opts = dict(zip(argv[6::2], argv[7::2]))
amount = int(opts.get('--amount', 20))
curl_turns = float(opts.get('--curl-turns', 8))
curl_points = int(opts.get('--curl-points', 40))
rough_prob = float(opts.get('--rough-prob', .04))
rough_scale = float(opts.get('--rough-scale', .006))
noise_scale = float(opts.get('--noise', .003))
clump_root = float(opts.get('--clump-root', 4.0))
clump_tip = float(opts.get('--clump-tip', .5))
curl_radius = float(opts.get('--curl-radius', .005))
curl_per = opts.get('--curl-per', 'guide')

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

head = np.load(head_npz)
me = bpy.data.meshes.new('InezHeadSurface')
me.from_pydata(head['position'].astype(float).tolist(), [], head['triangles'].astype(int).tolist())
head_obj = bpy.data.objects.new('InezHeadSurface', me); scene.collection.objects.link(head_obj)

g = np.load(guides_npz)
pts = g['points'].astype(float); n_guides, n_pts, _ = pts.shape
cv = bpy.data.hair_curves.new('InezGuides')
cv.add_curves([n_pts] * n_guides)
cv.attributes['position'].data.foreach_set('vector', pts.reshape(-1))
guides_obj = bpy.data.objects.new('InezGuides', cv); scene.collection.objects.link(guides_obj)

with bpy.data.libraries.load(nodes_blend, link=False) as (src, dst):
    if 'MainHair' not in src.node_groups:
        raise SystemExit('MainHair node group not found')
    dst.node_groups = ['MainHair']
original = bpy.data.node_groups['MainHair']
ng = original.copy(); ng.name = 'MainHair_Inez'
N = ng.nodes; L = ng.links
changes = []


def setv(node, idx, value, label):
    sock = N[node].inputs[idx]
    old = sock.default_value
    sock.default_value = value
    changes.append({'node': node, 'input': sock.name, 'from': old if isinstance(old, (int, float, bool, str)) else list(old), 'to': value, 'section': label})


# Deform Curves on Surface -> bypass; store guide_id before duplication
gi, dcos, dup = N['Group Input'], N['Deform Curves on Surface'], N['Duplicate Elements']
store = N.new('GeometryNodeStoreNamedAttribute'); store.data_type = 'INT'; store.domain = 'CURVE'
store.inputs['Name'].default_value = 'guide_id'
index = N.new('GeometryNodeInputIndex')
L.new(gi.outputs['Geometry'], store.inputs['Geometry']); L.new(index.outputs['Index'], store.inputs['Value'])
L.new(store.outputs['Geometry'], dup.inputs['Geometry'])
N.remove(dcos)
changes.append({'node': 'Deform Curves on Surface', 'change': 'removed (static rest groom)', 'section': 'Hair Amount'})
changes.append({'node': 'Store Named Attribute (added)', 'change': 'guide_id = curve index before duplication', 'section': 'Hair Amount'})

setv('Duplicate Elements', 'Amount', amount, 'Hair Amount')
setv('Math.001', 1, float(opts.get('--spread', .004)), 'Spread')
setv('Resample Curve', 'Count', 16, 'Points Count')
N['Trim Curve'].mode = 'FACTOR'; changes.append({'node': 'Trim Curve', 'change': 'mode LENGTH -> FACTOR', 'section': 'Random Length'})
setv('Random Value.001', 2, .75, 'Random Length'); setv('Random Value.001', 3, 1.0, 'Random Length')
N['Object Info.001'].inputs['Object'].default_value = head_obj
changes.append({'node': 'Object Info.001', 'change': 'object = InezHeadSurface', 'section': 'Stick To Mesh'})
setv('Vector Math.005', 3, noise_scale, 'Noise')
setv('Vector Math.007', 3, rough_scale, 'Roughness'); setv('Random Value.003', 6, rough_prob, 'Roughness')
setv('Resample Curve.001', 'Count', curl_points, 'Curl')
for name, value in (('Value', curl_turns), ('Size', curl_radius)):
    old = N[name].outputs[0].default_value; N[name].outputs[0].default_value = value
    changes.append({'node': name, 'label': N[name].label, 'from': old, 'to': value, 'section': 'Curl'})
setv('Random Value.004', 2, .6, 'Curl')
N['Align Euler to Vector'].axis = 'Z'; changes.append({'node': 'Align Euler to Vector', 'change': 'axis X -> Z (helix around the strand)', 'section': 'Curl'})
setv('Map Range.001', 3, clump_root, 'Clumping'); setv('Map Range.001', 4, clump_tip, 'Clumping')
if curl_per == 'guide':
    # Curl frequency random per guide (clump) instead of per strand, so the
    # strands of a clump spiral together into ringlets instead of frizz.
    named = N.new('GeometryNodeInputNamedAttribute'); named.data_type = 'INT'; named.inputs['Name'].default_value = 'guide_id'
    L.new(named.outputs['Attribute'], N['Random Value.004'].inputs['ID'])
    changes.append({'node': 'Random Value.004', 'change': 'ID = guide_id (was strand index): curls shared per clump', 'section': 'Curl'})

mod = guides_obj.modifiers.new('MainHair', 'NODES'); mod.node_group = ng
deps = bpy.context.evaluated_depsgraph_get()
ev = guides_obj.evaluated_get(deps).data
n_points, n_curves = len(ev.points), len(ev.curves)
pos = np.empty(n_points * 3); ev.attributes['position'].data.foreach_get('vector', pos)
offsets = np.array([c.first_point_index for c in ev.curves] + [n_points], np.int64)
radius = np.empty(n_points); ev.attributes['radius'].data.foreach_get('value', radius)
gid = np.empty(n_curves, np.int64); ev.attributes['guide_id'].data.foreach_get('value', gid)
np.savez_compressed(out_npz, position=pos.reshape(-1, 3).astype(np.float32), offsets=offsets, radius=radius.astype(np.float32), guide_id=gid.astype(np.int32))
bpy.ops.wm.save_as_mainfile(filepath=out_blend)
Path(report_path).write_text(json.dumps({'tool': 'tools/inez/hair/groom_with_mainhair.py', 'node_group_source': nodes_blend,
    'guides': int(n_guides), 'strands': int(n_curves), 'points': int(n_points), 'points_per_strand': sorted(set(np.diff(offsets).tolist()))[:5],
    'changes': changes}, indent=1, default=str) + '\n')
print(json.dumps({'strands': n_curves, 'points': n_points}))
