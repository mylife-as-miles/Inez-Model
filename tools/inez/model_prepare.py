"""Inventory only: does not construct, deform, render or export a character."""
import json
from model_source import CHARACTER, read_obj, rig_sources, source_bounds

vertices, texcoords, groups = read_obj()
rig, weights = rig_sources()
body_ids = sorted({i for face in groups['body'] for i, _ in face})
inventory = {
    'stage': 'preparation only; front/profile/body approval required before build',
    'source': 'MakeHuman hm08, CC0 assets, see model/base-source/provenance.json',
    'vertices_including_helpers': len(vertices),
    'body_vertices': len(body_ids),
    'body_polygons': len(groups['body']),
    'body_source_index_range': [min(body_ids), max(body_ids)],
    'uv_entries': len(texcoords),
    'body_bounds_makehuman_units': source_bounds(vertices, body_ids),
    'continuous_body_topology': True,
    'source_coordinate_convention': 'X lateral, Y up, Z toward front',
    'blender_coordinate_convention': 'X lateral, Y rearward, Z up, meters',
    'scale_policy': '1.70 m provisional, must be replaced by game-team height',
    'skeleton_bones': len(rig['bones']),
    'skeleton_license': rig['license'],
    'weight_license': weights['license'],
    'facial_bones_available': [n for n in rig['bones'] if n.startswith(
        ('eye','oculi','orbicularis','oris','levator','risorius','temporalis','jaw'))],
    'object_groups': {name: len(faces) for name, faces in groups.items()},
    'manual_work_expected': [
        'match cranial/nose/lid/lip/jaw form to originals through actual clay renders',
        'true left/right profiles are proposed reconstructions, not source truth',
        'manual sculpt refinement likely necessary for production facial likeness',
        'sweater/jeans/boots construction and hair groom need separate fitted meshes',
        'facial textures withheld until head geometry passes credible-likeness gate',
        'source weights require deformation/clipping review after head/body fitting',
    ],
}
path = CHARACTER/'qa/model/model_source_inventory.json'
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(inventory, indent=2)+'\n')
print(json.dumps({k:inventory[k]for k in ['body_vertices','body_polygons','uv_entries','skeleton_bones','stage']},indent=2))

