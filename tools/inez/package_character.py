"""Produce the Inez deliverables from an animated master .blend.

    python3 -I tools/inez/package_character.py --animated ANIMATED.blend \
        --animation-manifest animation_manifest.json --work-dir SCRATCH/package

Steps:
1. Blender `runtime_export.py`.
   - Unpacks the master textures to `textures/master/`.
   - Saves `model/inez_master.blend` (compressed, textures linked).
   - Exports the raw master GLB and the LOD0–2 runtime GLBs.
2. `glb_expression_clips.py` on every GLB.
   - Adds the facial clips.
   - Repairs zero-length tangents.
3. Master: written as `model/inez_master.glb`, with JPEG/PNG textures and no
   extensions a basic glTF loader would lack.
4. Runtime levels: glTF-Transform 4.1.1 with KTX-Software `toktx`.
   - KTX2 UASTC for normal and data maps.
   - KTX2 ETC1S for colour.
   - Then `EXT_meshopt_compression`.
   - Output: `model/inez_runtime.glb`, `model/inez_runtime_lod1.glb`,
     `model/inez_runtime_lod2.glb`.
5. Every output passes through the Khronos glTF validator (errors fail the
   run).
6. The rig manifest and expression-clip report are copied to `rig/`.

Environment: `KTX_PREFIX` (default `/opt/ktx/usr`) must hold the extracted
KTX-Software 4.3.2 release (`bin/toktx`, `lib/libktx.so`).
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHAR = ROOT/'assets/characters/inez'
BLENDER = os.environ.get('BLENDER', '/opt/blender-4.3.2/blender')
NPX = ['npx', '--prefix', str(ROOT/'viewer'), 'gltf-transform']


def sanitize(value, prefixes):
    """Replace machine-specific scratch paths in reports with placeholders."""
    if isinstance(value, dict):
        return {k: sanitize(v, prefixes) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(v, prefixes) for v in value]
    if isinstance(value, str):
        for prefix, label in prefixes:
            value = value.replace(prefix, label)
    return value


def run(cmd, env=None, cwd=None):
    print('+', ' '.join(str(c) for c in cmd), flush=True)
    result = subprocess.run([str(c) for c in cmd], env=env, cwd=cwd, capture_output=True, text=True)
    if result.returncode:
        sys.stdout.write(result.stdout[-4000:])
        sys.stderr.write(result.stderr[-4000:])
        raise SystemExit(f'failed: {cmd[0]}')
    return result.stdout


def validate(path, report):
    out = run(['node', ROOT/'tools/inez/validate_glb.mjs', path, report])
    data = json.loads(out[out.index('{'):])
    if data['errors']:
        raise SystemExit(f'glTF validation errors in {path}')
    return {'errors': data['errors'], 'warnings': data['warnings'], 'infos': data['infos']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--animated', required=True)
    parser.add_argument('--animation-manifest', required=True)
    parser.add_argument('--work-dir', required=True)
    parser.add_argument('--skip-blender', action='store_true')
    args = parser.parse_args()
    work = Path(args.work_dir)
    work.mkdir(parents=True, exist_ok=True)
    ktx = Path(os.environ.get('KTX_PREFIX', '/opt/ktx/usr'))
    env = dict(os.environ, PATH=f"{ktx/'bin'}:{os.environ['PATH']}",
               LD_LIBRARY_PATH=f"{ktx/'lib'}:{os.environ.get('LD_LIBRARY_PATH', '')}")
    report = {'animated_source': args.animated, 'outputs': {}}
    if not args.skip_blender:
        run([BLENDER, '-b', '-t', '4', args.animated, '--python', ROOT/'tools/inez/runtime_export.py', '--',
             '--character-dir', CHAR, '--work-dir', work, '--report', work/'runtime_export.json'])
    report['runtime_export'] = json.loads((work/'runtime_export.json').read_text())
    (CHAR/'rig').mkdir(exist_ok=True)
    (CHAR/'qa'/'technical').mkdir(parents=True, exist_ok=True)
    # Master: facial clips + tangent repair, plain textures.
    master = CHAR/'model'/'inez_master.glb'
    run([sys.executable, '-I', ROOT/'tools/inez/glb_expression_clips.py', '--input', work/'inez_master_raw.glb',
         '--output', master, '--report', CHAR/'rig'/'expression_clips.json'])
    report['outputs']['inez_master.glb'] = {'bytes': master.stat().st_size,
                                            'validation': validate(master, CHAR/'qa/technical/inez_master_validation.json')}
    names = {'lod0': 'inez_runtime.glb', 'lod1': 'inez_runtime_lod1.glb', 'lod2': 'inez_runtime_lod2.glb'}
    for level, name in names.items():
        raw = work/f'inez_runtime_{level}.glb'
        if not raw.exists():
            continue
        clips = work/f'{level}_clips.glb'
        run([sys.executable, '-I', ROOT/'tools/inez/glb_expression_clips.py', '--input', raw, '--output', clips])
        uastc = work/f'{level}_uastc.glb'
        run(NPX+['uastc', clips, uastc, '--slots', '{normalTexture,occlusionTexture,metallicRoughnessTexture}',
                 '--level', '2', '--rdo', '--zstd', '18'], env=env)
        etc1s = work/f'{level}_etc1s.glb'
        run(NPX+['etc1s', uastc, etc1s, '--slots', '{baseColorTexture,emissiveTexture}', '--quality', '192'], env=env)
        # The validator cannot decode meshopt buffers, so the accessor data is
        # checked on the last uncompressed step and the structure on the output.
        before_meshopt = validate(etc1s, work/f'{level}_etc1s_validation.json')
        out = CHAR/'model'/name
        run(NPX+['meshopt', etc1s, out, '--level', 'medium'], env=env)
        report['outputs'][name] = {'bytes': out.stat().st_size, 'level': level,
                                   'validation_before_meshopt': before_meshopt,
                                   'validation': validate(out, CHAR/f'qa/technical/{Path(name).stem}_validation.json')}
    prefixes = [(str(work.resolve()), '<work>'), (str(Path(args.animated).resolve().parent), '<build>'),
                (str(ROOT)+'/', '')]
    manifest = sanitize(json.loads(Path(args.animation_manifest).read_text()), prefixes)
    (CHAR/'rig'/'animation_manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    report = sanitize(report, prefixes)
    (CHAR/'qa/technical/package_report.json').write_text(json.dumps(report, indent=2)+'\n')
    print('PACKAGE '+json.dumps(report['outputs']))


if __name__ == '__main__':
    main()
