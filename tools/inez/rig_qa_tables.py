"""Markdown tables for INEZ_RIG_QA.md, read straight from the rig manifest.

    python3 -I tools/inez/rig_qa_tables.py assets/characters/inez/rig/animation_manifest.json

Prints the clip, audit, identity and skin tables so the report quotes the
measured values verbatim instead of transcribing them by hand.
"""
import json
import sys


def mm(value):
    return '—' if value is None else f'{value*1000:.1f}'


def main():
    m = json.load(open(sys.argv[1]))
    clips, audits = m['clip_info'], m['deformation_samples']
    print('| Clip | Duration (s) | Loop | Matching speed (m/s) | Pelvis drop range (cm) | IK reach error (mm) | Boot-ground error (mm) | Loop ankle error (mm) |')
    print('|---|---|---|---|---|---|---|---|')
    for name, c in clips.items():
        a = audits.get(name, {})
        drop = c.get('pelvis_drop_range_m')
        drop = '—' if not drop else f'{drop[0]*100:.1f} … {drop[1]*100:.1f}'
        ground = a.get('maximum_stance_boot_ground_error_m')
        if ground is None and a.get('lowest_boot_z_range_m'):
            lo, hi = a['lowest_boot_z_range_m']
            ground = max(abs(lo), abs(hi))
        loop = 'one-shot' if c.get('one_shot') else ('yes' if c.get('loop', True) else 'no')
        speed = c.get('matching_viewer_speed_m_s')
        print(f"| {name} | {c['duration_s']:.2f} | {loop} | {'—' if not speed else f'{speed:.2f}'} | {drop} | "
              f"{mm(c.get('maximum_ik_reach_error_m'))} | {mm(ground)} | {mm(a.get('loop_ankle_error_m'))} |")
    print()
    print('| Identity layer | Default after the bake |')
    print('|---|---|')
    for k, v in m['identity_morph_source_defaults'].items():
        print(f'| `{k}` | {v:g} |')
    print()
    print('| Mesh | Vertices >4 influences (pruned) | Max discarded weight | Unweighted |')
    print('|---|---|---|---|')
    for k, v in m['runtime_weight_adaptation'].items():
        print(f"| {k} | {v['vertices_with_source_influences_above_four']} | {v['maximum_discarded_normalized_weight']:.3f} | {v['unweighted_vertices']} |")
    print()
    print('| Mesh with facial controls | Targets | Max displacement (mm) |')
    print('|---|---|---|')
    for k, v in m['face_shape_deformation'].items():
        if isinstance(v, dict):
            disp = max((t['maximum_displacement_m'] for t in v.values() if isinstance(t, dict) and 'maximum_displacement_m' in t), default=0)
            n = sum(1 for t in v.values() if isinstance(t, dict) and 'maximum_displacement_m' in t)
            print(f'| {k} | {n} | {disp*1000:.1f} |')
    pt = m.get('ponytail', {})
    print()
    print(f"Ponytail: {pt.get('status')}; bones {pt.get('bones')}; {pt.get('ponytail_vertices')} shell vertices; span {pt.get('span_m', 0):.3f} m")
    print(f"Bones: {m['bone_count']}; weight failures: {m['weight_failures']}")


if __name__ == '__main__':
    main()
