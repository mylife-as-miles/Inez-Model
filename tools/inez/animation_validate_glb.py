"""Sample actual glTF skinning, clips and facial morph deformation.

This checks exported bytes rather than inferring readiness from bone counts.
It does not replace the artist/critic browser review of likeness and clipping.
"""
import argparse
import json
import math
from pathlib import Path
import struct

import numpy as np

from animation_motion import foot_cycle, gait_specs


COMPONENTS = {5120: np.int8, 5121: np.uint8, 5122: np.int16,
              5123: np.uint16, 5125: np.uint32, 5126: np.float32}
WIDTHS = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}


class Scene:
    def __init__(self, path):
        raw = Path(path).read_bytes()
        magic, version, size = struct.unpack_from('<4sII', raw)
        if magic != b'glTF' or version != 2 or size != len(raw):
            raise ValueError('Invalid GLB header')
        offset = 12
        self.binary = b''
        while offset < len(raw):
            length, kind = struct.unpack_from('<II', raw, offset)
            data = raw[offset+8:offset+8+length]
            if kind == 0x4e4f534a:
                self.data = json.loads(data.rstrip(b' \0'))
            elif kind == 0x004e4942:
                self.binary = data
            offset += length+8
        self.nodes = self.data.get('nodes', [])
        self.parents = {}
        for index, node in enumerate(self.nodes):
            for child in node.get('children', []):
                self.parents[child] = index
        self.cache = {}
        self.skin_cache = {}

    def accessor(self, index):
        if index in self.cache:
            return self.cache[index]
        spec = self.data['accessors'][index]
        dtype = np.dtype(COMPONENTS[spec['componentType']]).newbyteorder('<')
        width = WIDTHS[spec['type']]
        values = np.zeros((spec['count'], width), dtype=dtype)
        if 'bufferView' in spec:
            view = self.data['bufferViews'][spec['bufferView']]
            offset = view.get('byteOffset', 0)+spec.get('byteOffset', 0)
            stride = view.get('byteStride', dtype.itemsize*width)
            values = np.ndarray((spec['count'], width), dtype=dtype, buffer=self.binary,
                                offset=offset, strides=(stride, dtype.itemsize)).copy()
        if 'sparse' in spec:
            sparse = spec['sparse']
            index_spec, value_spec = sparse['indices'], sparse['values']
            index_view = self.data['bufferViews'][index_spec['bufferView']]
            index_dtype = np.dtype(COMPONENTS[index_spec['componentType']]).newbyteorder('<')
            indices = np.frombuffer(self.binary, dtype=index_dtype, count=sparse['count'],
                                    offset=index_view.get('byteOffset', 0)+index_spec.get('byteOffset', 0))
            value_view = self.data['bufferViews'][value_spec['bufferView']]
            replacement = np.frombuffer(self.binary, dtype=dtype, count=sparse['count']*width,
                                        offset=value_view.get('byteOffset', 0)+value_spec.get('byteOffset', 0)).reshape(-1, width)
            values[indices] = replacement
        if spec.get('normalized') and spec['componentType'] != 5126:
            info = np.iinfo(dtype)
            values = values.astype(float)/info.max
            if info.min < 0:
                values = np.maximum(-1.0, values)
        self.cache[index] = values
        return values

    @staticmethod
    def rotation(q):
        x, y, z, w = q/np.linalg.norm(q)
        return np.array(((1-2*y*y-2*z*z, 2*x*y-2*z*w, 2*x*z+2*y*w),
                         (2*x*y+2*z*w, 1-2*x*x-2*z*z, 2*y*z-2*x*w),
                         (2*x*z-2*y*w, 2*y*z+2*x*w, 1-2*x*x-2*y*y)))

    @staticmethod
    def interpolate(a, b, amount, rotation=False):
        a, b = np.array(a, dtype=float), np.array(b, dtype=float)
        if not rotation:
            return a+(b-a)*amount
        dot = float(a @ b)
        if dot < 0:
            b, dot = -b, -dot
        if dot > 0.9995:
            result = a+(b-a)*amount
            return result/np.linalg.norm(result)
        angle = math.acos(max(-1.0, min(1.0, dot)))
        return (a*math.sin((1-amount)*angle)+b*math.sin(amount*angle))/math.sin(angle)

    def animation_overrides(self, animation, time):
        result = {}
        if animation is None:
            return result
        for channel in animation['channels']:
            sampler = animation['samplers'][channel['sampler']]
            times = self.accessor(sampler['input']).ravel()
            values = self.accessor(sampler['output'])
            target = channel['target']
            path = target['path']
            if path == 'weights':
                width = len(values)//len(times)
                values = values.reshape(len(times), width)
            if sampler.get('interpolation', 'LINEAR') == 'CUBICSPLINE':
                raise ValueError('Cubic-spline sampling is not implemented; production bake should be linear')
            right = min(len(times)-1, int(np.searchsorted(times, time, side='right')))
            left = max(0, right-1)
            amount = 0 if right == left or times[right] == times[left] else max(0, min(1, (time-times[left])/(times[right]-times[left])))
            value = values[left] if sampler.get('interpolation') == 'STEP' else self.interpolate(values[left], values[right], amount, path == 'rotation')
            result.setdefault(target['node'], {})[path] = value
        return result

    def globals(self, animation=None, time=0):
        overrides = self.animation_overrides(animation, time)
        local, global_matrices = {}, {}
        for index, node in enumerate(self.nodes):
            change = overrides.get(index, {})
            if 'matrix' in node and not change:
                matrix = np.array(node['matrix']).reshape(4, 4).T
            else:
                matrix = np.eye(4)
                matrix[:3, 3] = change.get('translation', node.get('translation', (0, 0, 0)))
                rotation = change.get('rotation', node.get('rotation', (0, 0, 0, 1)))
                scale = change.get('scale', node.get('scale', (1, 1, 1)))
                matrix[:3, :3] = self.rotation(np.asarray(rotation))*np.asarray(scale)[None, :]
            local[index] = matrix

        def visit(index):
            if index not in global_matrices:
                parent = self.parents.get(index)
                global_matrices[index] = local[index] if parent is None else visit(parent) @ local[index]
            return global_matrices[index]
        for index in range(len(self.nodes)):
            visit(index)
        return global_matrices, overrides

    def vertices(self, node_index, globals_, changes=None, morph_override=None):
        node = self.nodes[node_index]
        mesh = self.data['meshes'][node['mesh']]
        names = mesh.get('extras', {}).get('targetNames', [])
        default_weights = node.get('weights', mesh.get('weights', []))
        default_weights = (changes or {}).get(node_index, {}).get('weights', default_weights)
        chunks = []
        skin = self.data.get('skins', [])[node['skin']] if 'skin' in node else None
        if skin:
            if node['skin'] not in self.skin_cache:
                if 'inverseBindMatrices' in skin:
                    matrices = self.accessor(skin['inverseBindMatrices']).reshape(-1, 4, 4).transpose(0, 2, 1)
                else:
                    matrices = np.repeat(np.eye(4)[None], len(skin['joints']), axis=0)
                self.skin_cache[node['skin']] = matrices
            matrices = np.array([globals_[index] for index in skin['joints']]) @ self.skin_cache[node['skin']]
        for primitive in mesh['primitives']:
            attributes = primitive['attributes']
            points = self.accessor(attributes['POSITION']).astype(float).copy()
            for index, target in enumerate(primitive.get('targets', [])):
                weight = float(default_weights[index]) if index < len(default_weights) else 0.0
                if morph_override and index < len(names) and names[index] in morph_override:
                    weight = morph_override[names[index]]
                if weight and 'POSITION' in target:
                    points += self.accessor(target['POSITION'])*weight
            homogeneous = np.column_stack((points, np.ones(len(points))))
            if skin and 'JOINTS_0' in attributes:
                positions = np.zeros((len(points), 4))
                for group in range(2):
                    joint_name, weight_name = 'JOINTS_'+str(group), 'WEIGHTS_'+str(group)
                    if joint_name not in attributes:
                        continue
                    joints = self.accessor(attributes[joint_name]).astype(int)
                    weights = self.accessor(attributes[weight_name]).astype(float)
                    influenced = np.einsum('nkij,nj->nki', matrices[joints], homogeneous)
                    positions += np.einsum('nk,nki->ni', weights, influenced)
                points = positions[:, :3]
            else:
                points = (globals_[node_index] @ homogeneous.T).T[:, :3]
            chunks.append(points)
        return np.concatenate(chunks) if chunks else np.empty((0, 3))

    def region_mask(self, node_index, prefixes, side):
        """Find actual exported vertices substantially weighted to a limb."""
        node = self.nodes[node_index]
        mesh = self.data['meshes'][node['mesh']]
        if 'skin' not in node:
            return np.zeros(sum(self.data['accessors'][p['attributes']['POSITION']]['count']
                                for p in mesh['primitives']), dtype=bool)
        skin = self.data['skins'][node['skin']]
        selected = np.array([self.nodes[index].get('name', '').startswith(prefixes)
                             and self.nodes[index].get('name', '').endswith('.'+side)
                             for index in skin['joints']])
        chunks = []
        for primitive in mesh['primitives']:
            attributes = primitive['attributes']
            values = np.zeros(len(self.accessor(attributes['POSITION'])))
            for group in range(2):
                j, w = 'JOINTS_'+str(group), 'WEIGHTS_'+str(group)
                if j in attributes and w in attributes:
                    values += (selected[self.accessor(attributes[j]).astype(int)]
                               * self.accessor(attributes[w])).sum(axis=1)
            chunks.append(values > 0.2)
        return np.concatenate(chunks)


def bounds(points):
    return np.column_stack((points.min(axis=0), points.max(axis=0))).tolist() if len(points) else None


def run(path, manifest=None):
    scene = Scene(path)
    data = scene.data
    mesh_nodes = [i for i, node in enumerate(scene.nodes) if 'mesh' in node]
    if not mesh_nodes:
        raise ValueError('Actual exported asset contains no mesh nodes')
    body = next((i for i in mesh_nodes if 'ContinuousHumanMesh' in scene.nodes[i].get('name', '')), mesh_nodes[0])
    # Production uses a single Inez_Boots mesh, not legacy Boot_L/Boot_R
    # objects. Partition its vertices by the actual side's skin influences.
    rest_matrices, rest_changes = scene.globals()
    boots = {side: {} for side in ('L', 'R')}
    for index in mesh_nodes:
        if 'boot' not in scene.nodes[index].get('name','').lower(): continue
        for side in ('L','R'):
            mask=scene.region_mask(index,('foot','toe','lowerleg','upperleg'),side)
            if mask.any(): boots[side][index]=np.flatnonzero(mask)
    editable_report = json.loads(Path(manifest).read_text()) if manifest else {}
    specs = gait_specs(editable_report.get('provisional_height_m', 1.68))
    audit = {'file': str(path), 'status': 'actual exported deformation sampling; visual critique still required',
             'axes': {'up': '+Y', 'forward': '+Z'}, 'clip_checks': {}, 'morph_checks': {},
             'overlay_morph_checks': {}, 'skin_checks': [], 'mesh_checks': []}
    failures = []
    joint_names = {scene.nodes[index].get('name', '') for skin in data.get('skins', [])
                   for index in skin['joints']}
    required_joints = {'root', 'head', 'jaw', 'eye.L', 'eye.R', 'hair.01', 'hair.02', 'hair.03'}
    if required_joints-joint_names:
        failures.append('Missing exported deform controls: '+str(sorted(required_joints-joint_names)))
    if 'skin' not in scene.nodes[body]:
        failures.append('Actual continuous human body has no exported skin')
    if any(not boots[side] for side in ('L', 'R')):
        failures.append('Named left/right boot support geometry is missing')
    for index in mesh_nodes:
        node, checks = scene.nodes[index], []
        for primitive in data['meshes'][node['mesh']]['primitives']:
            attributes = primitive['attributes']
            material_index = primitive.get('material')
            material = data['materials'][material_index] if material_index is not None else {}
            pbr = material.get('pbrMetallicRoughness', {})
            textured = any(k.endswith('Texture') for k in material) or any(k.endswith('Texture') for k in pbr)
            checks.append({'uv': 'TEXCOORD_0' in attributes, 'normals': 'NORMAL' in attributes,
                           'material': primitive.get('material'), 'skinned': 'skin' in node
                           and 'JOINTS_0' in attributes and 'WEIGHTS_0' in attributes})
            if (textured and 'TEXCOORD_0' not in attributes) or 'NORMAL' not in attributes:
                failures.append(node.get('name', str(index))+' lost exported UVs/normals')
            if material_index is None or 'pbrMetallicRoughness' not in data['materials'][material_index]:
                failures.append(node.get('name', str(index))+' lacks exported PBR material')
            if not checks[-1]['skinned']:
                failures.append(node.get('name', str(index))+' lacks exported skin/joint weights')
            if 'JOINTS_1' in attributes:
                failures.append(node.get('name', str(index))+' has extra skin influences unsupported by standard Three.js skinning')
        audit['mesh_checks'].append({'node': node.get('name'), 'primitives': checks})
    for mesh in data.get('meshes', []):
        for primitive in mesh['primitives']:
            attributes = primitive['attributes']
            if 'WEIGHTS_0' in attributes:
                total = scene.accessor(attributes['WEIGHTS_0']).sum(axis=1)
                if 'WEIGHTS_1' in attributes:
                    total += scene.accessor(attributes['WEIGHTS_1']).sum(axis=1)
                audit['skin_checks'].append({'mesh': mesh.get('name'), 'weight_sum_min': float(total.min()),
                                             'weight_sum_max': float(total.max()), 'bad_vertices': int((np.abs(total-1)>0.002).sum())})
    animations = {a.get('name', str(i)): a for i, a in enumerate(data.get('animations', []))}
    regions = {region+'_'+side: scene.region_mask(body, prefixes, side)
               for side in ('L', 'R') for region, prefixes in
               (('arm', ('upperarm', 'lowerarm', 'wrist')), ('leg', ('upperleg', 'lowerleg')))}
    for name, animation in animations.items():
        duration = max(float(scene.accessor(s['input']).max()) for s in animation['samplers'])
        start = min(float(scene.accessor(s['input']).min()) for s in animation['samplers'])
        endpoint_points = []
        records = []
        contact_errors = []
        limb_motion = {region: 0.0 for region in regions}
        maximum_body_motion = 0.0
        baked_samples = editable_report.get('clip_info', {}).get(name, {}).get('sample_count', 33)
        sample_count = max(65, int(baked_samples)*4+1) if name in specs else 17
        selected_records = set(np.linspace(0, sample_count-1, 17).round().astype(int))
        for sample_index, time in enumerate(np.linspace(start, duration, sample_count)):
            matrices, changes = scene.globals(animation, float(time))
            points = scene.vertices(body, matrices, changes)
            if len(endpoint_points) == 0 or time == duration:
                endpoint_points.append(points)
            distances = np.linalg.norm(points-endpoint_points[0], axis=1)
            maximum_body_motion = max(maximum_body_motion, float(distances.max()))
            for region, mask in regions.items():
                if mask.any():
                    limb_motion[region] = max(limb_motion[region], float(distances[mask].max()))
            record = {'time_s': float(time), 'body_bounds': bounds(points), 'feet': {}}
            for side in ('L', 'R'):
                chunks = [scene.vertices(index, matrices, changes)[indices] for index,indices in boots[side].items()]
                boot_points = np.concatenate(chunks) if chunks else np.empty((0, 3))
                record['feet'][side] = {'bounds': bounds(boot_points), 'minimum_y_m': float(boot_points[:, 1].min()) if len(boot_points) else None}
                if name in specs and len(boot_points):
                    phase = (float(time)-start)/max(1e-8, duration-start)
                    expected = foot_cycle(specs[name], phase+(0 if side == 'L' else 0.5))
                    record['feet'][side]['stance_contact'] = expected['contact']
                    record['feet'][side]['expected_sole_lift_m'] = expected['lift']
                    if expected['contact']:
                        contact_errors.append(abs(float(boot_points[:, 1].min())))
            if sample_index in selected_records:
                records.append(record)
        dynamic = []
        rotation_channels = 0
        for channel in animation['channels']:
            path_ = channel['target']['path']
            sampler = animation['samplers'][channel['sampler']]
            values = scene.accessor(sampler['output'])
            amplitude = float(np.ptp(values, axis=0).max())
            if path_ == 'rotation':
                rotation_channels += 1
            if amplitude > 0.0001:
                dynamic.append({'node': scene.nodes[channel['target']['node']].get('name'), 'path': path_, 'component_range': amplitude})
        loop_error = float(np.linalg.norm(endpoint_points[0]-endpoint_points[-1], axis=1).max())
        start_matrices, start_changes = scene.globals(animation, start)
        end_matrices, end_changes = scene.globals(animation, duration)
        all_mesh_loop_errors = {scene.nodes[index].get('name', str(index)):
                               float(np.linalg.norm(scene.vertices(index, start_matrices, start_changes)
                                     - scene.vertices(index, end_matrices, end_changes), axis=1).max())
                               for index in mesh_nodes}
        root_translation = [c for c in dynamic if c['path'] == 'translation' and c['node'] in ('root', 'Root')]
        audit['clip_checks'][name] = {'duration_s': duration-start, 'rotation_channel_count': rotation_channels,
                                     'dynamic_channel_count': len(dynamic), 'maximum_loop_body_vertex_error_m': loop_error,
                                     'maximum_stance_boot_ground_error_m': max(contact_errors, default=None),
                                     'actual_deformation_sample_count': sample_count,
                                     'maximum_actual_body_vertex_motion_m': maximum_body_motion,
                                     'maximum_actual_limb_vertex_motion_m': limb_motion,
                                     'maximum_loop_mesh_vertex_errors_m': all_mesh_loop_errors,
                                     'dynamic_channels': dynamic, 'sample_frames': records,
                                     'root_translation_channels': root_translation}
    matrices, changes = scene.globals()
    mesh = data['meshes'][scene.nodes[body]['mesh']]
    names = mesh.get('extras', {}).get('targetNames', [])
    identity_weights = scene.nodes[body].get('weights', mesh.get('weights', []))
    audit['identity_morph_weights'] = {name: float(identity_weights[index])
                                      for index, name in enumerate(names)
                                      if name.startswith('Inez_') and index < len(identity_weights)}
    expected_identity = editable_report.get('identity_morph_source_defaults', {})
    audit['identity_morph_source_defaults'] = expected_identity
    if not audit['identity_morph_weights'] or not any(abs(weight) > 1e-6
                                                      for weight in audit['identity_morph_weights'].values()):
        failures.append('Fitted identity morphs are absent or all exported defaults are inactive')
    if manifest and not expected_identity:
        failures.append('Source manifest does not record each original identity morph default')
    if expected_identity:
        if not set(expected_identity).issubset(audit['identity_morph_weights']):
            failures.append('Export changed the individual source identity morph names')
        elif any(abs(weight-audit['identity_morph_weights'][name]) > 1e-6
                 for name, weight in expected_identity.items()):
            failures.append('Export changed an individual source identity morph default')
    neutral = scene.vertices(body, matrices, changes)
    for name in names:
        if name.startswith('Inez_HeadFit'):
            continue
        altered = scene.vertices(body, matrices, changes, {name: 1.0})
        distances = np.linalg.norm(altered-neutral, axis=1)
        audit['morph_checks'][name] = {'affected_exported_vertices': int((distances > 1e-7).sum()),
                                      'maximum_world_displacement_m': float(distances.max())}
    for index in mesh_nodes:
        node_name = scene.nodes[index].get('name', '')
        if not any(token in node_name.lower() for token in ('brow', 'lash', 'tearline')):
            continue
        neutral_overlay = scene.vertices(index, matrices, changes)
        overlay_names = data['meshes'][scene.nodes[index]['mesh']].get('extras', {}).get('targetNames', [])
        relevant = ('Confused', 'Anger') if 'brow' in node_name.lower() else ('Blink_L', 'Blink_R')
        checks = {}
        for name in relevant:
            altered = scene.vertices(index, matrices, changes, {name: 1.0})
            distances = np.linalg.norm(altered-neutral_overlay, axis=1)
            checks[name] = {'target_exported': name in overlay_names,
                            'affected_exported_vertices': int((distances > 1e-7).sum()),
                            'maximum_world_displacement_m': float(distances.max())}
        if not any(check['affected_exported_vertices'] for check in checks.values()):
            failures.append(node_name+' does not follow exported face expression/blink morphs')
        audit['overlay_morph_checks'][node_name] = checks
    required_clips = {'Idle', 'Walk', 'Run'}
    required_morphs = {'Neutral', 'Confused', 'Suspicious', 'SubtleFear', 'IntenseFear', 'Anger', 'Exhaustion',
                       'Blink_L', 'Blink_R', 'Viseme_AA', 'Viseme_EE', 'Viseme_OH', 'Viseme_MM', 'Viseme_FV'}
    if required_clips-animations.keys():
        failures.append('Missing locomotion clips: '+str(sorted(required_clips-animations.keys())))
    if required_morphs-set(names):
        failures.append('Missing facial controls: '+str(sorted(required_morphs-set(names))))
    for name in required_clips & animations.keys():
        check = audit['clip_checks'][name]
        if check['maximum_loop_body_vertex_error_m'] > 0.003:
            failures.append(name+' loop discontinuity exceeds 3 mm')
        if max(check['maximum_loop_mesh_vertex_errors_m'].values(), default=0) > 0.003:
            failures.append(name+' has a clothing/hair/face mesh loop discontinuity above 3 mm')
        if check['maximum_actual_body_vertex_motion_m'] < (0.001 if name == 'Idle' else 0.03):
            failures.append(name+' does not actually deform exported body vertices')
        if check['dynamic_channel_count'] < (4 if name == 'Idle' else 16):
            failures.append(name+' lacks sufficient changing joint tracks')
        contact_error = check['maximum_stance_boot_ground_error_m']
        if contact_error is not None and contact_error > 0.010:
            failures.append(name+' exported stance boot contact exceeds 10 mm')
        if name in ('Walk', 'Run'):
            for region, displacement in check['maximum_actual_limb_vertex_motion_m'].items():
                if displacement < 0.03:
                    failures.append(name+' '+region+' lacks actual exported skin movement')
            moving_legs = [c for c in check['dynamic_channels'] if c['path'] == 'rotation'
                           and c['node'].startswith(('upperleg01', 'lowerleg01')) and c['component_range'] > 0.04]
            if len(moving_legs) < 4:
                failures.append(name+' does not have substantial thigh/shin motion on both legs')
    for name in required_morphs-{'Neutral'}:
        if name in audit['morph_checks'] and audit['morph_checks'][name]['affected_exported_vertices'] < 4:
            failures.append(name+' has no meaningful exported mesh deformation')
    if any(check['bad_vertices'] for check in audit['skin_checks']):
        failures.append('Exported skin weights are not normalized')
    if manifest:
        audit['editable_source_manifest'] = str(manifest)
    audit['failures'] = failures
    audit['technical_sampling_passed'] = not failures
    return audit


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--glb', required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--manifest')
    args = parser.parse_args()
    result = run(args.glb, args.manifest)
    Path(args.report).write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'technical_sampling_passed': result['technical_sampling_passed'],
                      'failures': result['failures'], 'clips': list(result['clip_checks']),
                      'morphs': list(result['morph_checks'])}, indent=2))
    if result['failures']:
        raise SystemExit(2)
