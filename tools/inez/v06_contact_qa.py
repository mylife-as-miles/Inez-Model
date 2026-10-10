"""Matched actual viewer renders and an independent Three.js contact audit.

No generated imagery. Both models use the same camera, neutral lighting and
original PBR. Contact sampling uses the loaded AnimationMixer and skinned boot
vertices without drawing each sample; matching travel is added analytically.
"""
import argparse
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path

import numpy as np
from playwright.async_api import async_playwright

from animation_validate_glb import Scene
from v06_contact_glb import run as exported_contact

ROOT = Path(__file__).resolve().parents[2]
CHAR = ROOT / 'assets/characters/inez'
CLIPS = ('Walk', 'Run', 'CrouchDown', 'CrouchUp')


def specs(path, hz):
    scene = Scene(path)
    matrices, changes = scene.globals()
    boots = []
    for i, node in enumerate(scene.nodes):
        if 'mesh' not in node or 'boot' not in node.get('name', '').lower():
            continue
        points = scene.vertices(i, matrices, changes)
        sides = {}
        for side in 'LR':
            selected = np.flatnonzero(scene.region_mask(i, ('foot', 'toe', 'lowerleg', 'upperleg'), side))
            if len(selected):
                sides[side] = selected[points[selected, 1] < points[selected, 1].min() + .03].tolist()
        boots.append({'name': node['name'], 'vertices': len(points), 'sides': sides})
    manifest = json.loads((CHAR / 'rig/animation_manifest.json').read_text())
    clips = {}
    for animation in scene.data['animations']:
        name = animation['name']
        if name not in CLIPS:
            continue
        duration = max(float(scene.accessor(s['input']).max()) for s in animation['samplers'])
        clips[name] = {'duration': duration, 'count': round(duration * hz),
            'speed': manifest['clip_info'][name].get('matching_viewer_speed_m_s', 0)}
    return {'boots': boots, 'clips': clips, 'hz': hz}


AUDIT_JS = """async spec => {
    const T = await import('/node_modules/three/build/three.module.js');
    const v = window.inezViewer, avatar = v.getAvatar();
    const meshes = spec.boots.map(b => {
        const mesh = avatar.getObjectByName(b.name);
        if (!mesh?.isSkinnedMesh || mesh.geometry.attributes.position.count !== b.vertices)
            throw new Error('Actual boot topology mismatch: ' + b.name);
        return {mesh, sides:b.sides};
    });
    const result = {};
    for (const [name, clip] of Object.entries(spec.clips)) {
        v.mixer.stopAllAction();
        const action = v.mixer._actions.find(a => a.getClip().name === name);
        if (!action) throw new Error('Missing actual clip: ' + name);
        action.reset().setEffectiveWeight(1).setLoop(T.LoopOnce,1).play();
        action.clampWhenFinished = true;
        const phases={L:[],R:[]}, active={L:null,R:null}, lows={L:[],R:[]};
        let previous=null;
        for (let frame=0;frame<=clip.count;frame++) {
            const t=clip.duration*frame/clip.count;
            action.paused=false; action.time=t; v.mixer.update(0);
            avatar.updateMatrixWorld(true); meshes.forEach(({mesh})=>mesh.skeleton.update());
            const points={L:[],R:[]};
            for (const {mesh,sides} of meshes) for (const side of ['L','R'])
                for (const index of sides[side]??[]) {
                    const p=mesh.getVertexPosition(index,new T.Vector3()).applyMatrix4(mesh.matrixWorld);
                    p.sub(avatar.position); p.z+=clip.speed*t; points[side].push(p.toArray());
                }
            for (const side of ['L','R']) {
                const p=points[side];
                if (!p.length) throw new Error('Missing actual sole: '+side);
                let k=0;for(let i=1;i<p.length;i++)if(p[i][1]<p[k][1])k=i;
                const low=p[k][1];lows[side].push(low);
                const step=previous?Math.hypot(p[k][0]-previous[side][k][0],p[k][2]-previous[side][k][2]):0;
                if(low<.002) {
                    if(!active[side])active[side]={start_s:t,end_s:t,slip_mm:0};
                    else {active[side].end_s=t;active[side].slip_mm+=step*1000;}
                } else if(active[side]) {phases[side].push(active[side]);active[side]=null;}
            }
            previous=points;
        }
        result[name]={duration_s:clip.duration,matching_speed_m_s:clip.speed,samples:clip.count+1};
        for (const side of ['L','R']) {
            if(active[side])phases[side].push(active[side]);
            const kept=phases[side].filter(p=>p.end_s-p.start_s>=3/spec.hz-1e-6);
            result[name][side]={max_stance_slip_mm:Math.max(0,...kept.map(p=>p.slip_mm)),
                lowest_sole_mm:Math.min(...lows[side])*1000,planted_phases:kept};
        }
    }
    v.mixer.stopAllAction();return result;
}"""


async def run(args):
    out = CHAR / 'renders' / args.revision
    if out.exists():
        raise ValueError('Choose a new capture revision')
    out.mkdir(parents=True)
    report = {'revision': args.revision, 'sampling_hz': args.hz,
        'lighting': 'neutral', 'skin_mode': 'existing', 'artistic_approval': False,
        'models': {}, 'errors': []}
    cameras = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=os.environ.get('INEZ_CHROMIUM', '/usr/bin/chromium'),
            args=['--no-sandbox', '--disable-dev-shm-usage', '--enable-unsafe-swiftshader', '--use-angle=swiftshader'])
        for label, model in [('before', args.before), ('after', args.after)]:
            page = await browser.new_page(viewport={'width': 1000, 'height': 760}, device_scale_factor=1)
            page.set_default_timeout(180000)
            page.on('pageerror', lambda e: report['errors'].append(str(e)))
            page.on('console', lambda e: report['errors'].append(e.text) if e.type == 'error' else None)
            path = CHAR / 'model' / model
            sample_spec = specs(path, args.hz)
            await page.goto(args.url + '?model=' + model, timeout=180000)
            await page.wait_for_function('window.inezViewer?.state.ready || window.inezViewer?.state.error', timeout=300000)
            if not await page.evaluate('window.inezViewer.state.ready'):
                raise RuntimeError(await page.evaluate('window.inezViewer.state.error'))
            await page.evaluate("""() => {const v=window.inezViewer;v.renderer.setAnimationLoop(null);
                v.captureMode(true);v.pause(true);v.resetPosition();v.setAnimation('rest',{transition:0});
                v.resetFace();v.setLighting('neutral');v.setSkin({mode:'existing'});} """)
            record = {'model': model, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'backend': await page.evaluate('window.inezViewer.state.backend'),
                'diagnostics': await page.evaluate('window.inezViewer.digitalHuman.diagnostics'),
                'clips': await page.evaluate(AUDIT_JS, sample_spec), 'captures': []}
            folder = out / label
            folder.mkdir()
            for view in ('face_front', 'body_left', 'boots'):
                await page.evaluate("""view => {const v=window.inezViewer;v.setAnimation('rest',{transition:0});
                    v.setView(view==='boots'?'body_left':view);
                    if(view==='boots') {v.camera.zoom=2;v.camera.position.y=.23;
                        v.controls.target.y=.23;v.controls.update();v.camera.updateProjectionMatrix();}
                }""", view)
                camera = await page.evaluate("""() => {const v=window.inezViewer;return {position:v.camera.position.toArray(),
                    target:v.controls.target.toArray(),projection:v.camera.projectionMatrix.toArray()};}""")
                if label == 'before':
                    cameras[view] = camera
                elif camera != cameras[view]:
                    raise ValueError('Matched camera changed: ' + view)
                poses = [('rest', 0)] if view == 'face_front' else [
                    (name, fraction * clip['duration'])
                    for name, clip in sample_spec['clips'].items()
                    for fraction in ([.125, .375, .625, .875] if view == 'boots' else [.25, .5, .75])]
                for index, (name, t) in enumerate(poses):
                    await page.evaluate("""({name,t}) => {const v=window.inezViewer;
                        v.setAnimation(name,{transition:0,restart:true});v.seek(t);v.renderFrame();}
                    """, {'name': name, 't': t})
                    raw = await page.evaluate("document.getElementById('render').toDataURL('image/png')")
                    filename = f'{view}_{name}_{index:02d}.png'
                    (folder / filename).write_bytes(base64.b64decode(raw.split(',')[1]))
                    record['captures'].append({'file': label + '/' + filename, 'view': view, 'clip': name, 'time_s': t})
            report['models'][label] = record
            print('CAPTURED', label, len(record['captures']), 'actual PNGs', flush=True)
            await page.close()
        await browser.close()
    report['matched_cameras'] = cameras
    parity = {}
    for label, model in [('before', args.before), ('after', args.after)]:
        exported = exported_contact(CHAR / 'model' / model, args.hz, CLIPS)
        actual = report['models'][label]['clips']
        parity[label] = {name: {side: {key: abs(actual[name][side][key] - exported['clips'][name][side][key])
            for key in ('max_stance_slip_mm', 'lowest_sole_mm')} for side in 'LR'} for name in CLIPS}
    after = report['models']['after']['clips']
    portrait = 'face_front_rest_00.png'
    report['checks'] = {
        'no_browser_errors': not report['errors'],
        'matched_cameras': True,
        'original_pbr_rest_portrait_identical': (out / 'before' / portrait).read_bytes() == (out / 'after' / portrait).read_bytes(),
        'runtime_contact_below_half_mm': all(after[n][s]['max_stance_slip_mm'] < .5 for n in CLIPS for s in 'LR'),
        'runtime_no_sampled_penetration': all(after[n][s]['lowest_sole_mm'] >= 0 for n in CLIPS for s in 'LR'),
        'independent_evaluators_agree_within_tenth_mm': all(delta < .1 for model in parity.values()
            for clip in model.values() for side in clip.values() for delta in side.values())}
    report['evaluator_absolute_difference_mm'] = parity
    report['technical_passed'] = all(report['checks'].values())
    output = CHAR / 'qa/v06' / (args.revision + '.json')
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'report': str(output), 'passed': report['technical_passed'], 'errors': report['errors']}))
    return int(not report['technical_passed'])


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url', default='http://127.0.0.1:4174/')
    p.add_argument('--before', default='v06/inez_recovery_v06_paused.glb')
    p.add_argument('--after', default='v06/inez_recovery_v06_contact_r01.glb')
    p.add_argument('--revision', required=True)
    p.add_argument('--hz', type=int, default=120)
    args = p.parse_args()
    if args.hz <= 0:
        p.error('--hz must be positive')
    raise SystemExit(asyncio.run(run(args)))
