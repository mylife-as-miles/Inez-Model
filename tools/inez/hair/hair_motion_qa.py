"""Browser QA for the per-card hair simulation on Inez (actual Three.js, actual clips).

    INEZ_CHROMIUM=... python3 -I tools/inez/hair/hair_motion_qa.py --url http://127.0.0.1:4173/ \
        --model v06/inez_recovery_v06_hair_r02.glb --revision hair_r02_motion

For each embedded clip it resets the simulation to the animated pose, steps
the real mixer in fixed 1/60 s steps through viewer.advance(), and records the
solver diagnostics (offset from the animation, segment stretch, proxy
penetrations, resets/recoveries, CPU time). It saves side and back renders at
fixed clip times with the simulation on and off (same pose, camera and light),
checks teleport handling and records the live-loop cost. Software WebGL
(SwiftShader) timings are CPU evidence only.
"""
import argparse
import asyncio
import base64
import json
import os
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[3]
CHAR = ROOT / 'assets/characters/inez'
CLIPS = [('Idle', 2.0), ('Walk', 2.0), ('Run', 2.0), ('TurnLeft', 1.5), ('CrouchDown', 1.5), ('LookAround', 3.0)]

CAMERA_JS = '''([az, el, ty, sp]) => { const v = window.inezViewer; v.setView('face_front');
  const c = v.camera, t = v.controls.target, root = v.actorPosition;
  t.set(root[0], ty, root[2]); const d = 4, A = az * Math.PI / 180, E = el * Math.PI / 180;
  c.position.set(t.x + Math.sin(A) * Math.cos(E) * d, t.y + Math.sin(E) * d, t.z + Math.cos(A) * Math.cos(E) * d);
  const aspect = (c.right - c.left) / (c.top - c.bottom); c.top = sp / 2; c.bottom = -sp / 2; c.left = -sp / 2 * aspect; c.right = sp / 2 * aspect;
  c.zoom = 1; c.updateProjectionMatrix(); v.controls.update(); c.updateMatrixWorld(); v.renderFrame(); }'''


async def shot(page, path, az, el, ty, sp):
    await page.evaluate(CAMERA_JS, [az, el, ty, sp])
    data = await page.evaluate("() => { window.inezViewer.renderFrame(); return document.getElementById('render').toDataURL('image/png'); }")
    path.write_bytes(base64.b64decode(data.split(',')[1]))


async def run(args):
    out = CHAR / 'renders' / args.revision; out.mkdir(parents=True, exist_ok=True)
    report = {'model': args.model, 'artistic_approval': False, 'backend_note': 'SwiftShader WebGL2: CPU evidence only', 'clips': {}, 'errors': []}
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=os.environ.get('INEZ_CHROMIUM', '/usr/bin/chromium'),
            args=['--no-sandbox', '--disable-dev-shm-usage', '--enable-unsafe-swiftshader', '--use-angle=swiftshader'])
        page = await browser.new_page(viewport={'width': 1000, 'height': 760})
        page.on('pageerror', lambda e: report['errors'].append(str(e)))
        page.on('console', lambda m: report['errors'].append(m.text) if m.type == 'error' else None)
        await page.goto(args.url + '?model=' + args.model, timeout=120000)
        await page.wait_for_function('window.inezViewer?.state.ready || window.inezViewer?.state.error', timeout=240000)
        await page.evaluate("() => { const v = window.inezViewer; v.captureMode(true); v.setLighting('neutral'); }")
        report['hair_setup'] = await page.evaluate('window.inezViewer.hairDiagnostics')
        if not report['hair_setup']:
            report['errors'].append('model has no simulated hair cards'); report['viewer_warnings'] = await page.evaluate('window.inezViewer.warnings')
        for clip, seconds in CLIPS if report['hair_setup'] else []:
            samples = await page.evaluate('''([clip, seconds]) => { const v = window.inezViewer;
                v.resetPosition(); v.setAnimation(clip, { transition: 0 }); v.setHairPhysics(true);
                const out = []; const steps = Math.round(seconds * 60);
                for (let i = 1; i <= steps; i++) { v.advance(1 / 60, { render: false });
                  if (i % 5 === 0) { const d = v.hairDiagnostics; out.push({ t: i / 60, offset: d.maxOffsetFromAnimation, stretch: d.maxRelativeStretch,
                    penetrations: d.penetrations, resets: d.resets, recoveries: d.recoveries, solve_ms: d.lastSolveMs }); } }
                return out; }''', [clip, seconds])
            report['clips'][clip] = {
                'seconds': seconds, 'samples': samples,
                'max_offset_from_animation_m': max(s['offset'] for s in samples),
                'mean_offset_from_animation_m': sum(s['offset'] for s in samples) / len(samples),
                'max_relative_stretch': max(s['stretch'] for s in samples),
                'max_penetrations': max(s['penetrations'] for s in samples),
                'recoveries': samples[-1]['recoveries']}
            # same pose with and without the simulation, side and back
            for view, az, el, ty, sp in (('side', 90, 0, 1.55, .62), ('back', 180, 10, 1.55, .62)):
                await shot(page, out / f'{clip}_{view}_physics.png', az, el, ty, sp)
            await page.evaluate("() => window.inezViewer.setHairPhysics(false)")
            for view, az, el, ty, sp in (('side', 90, 0, 1.55, .62), ('back', 180, 10, 1.55, .62)):
                await shot(page, out / f'{clip}_{view}_animation_only.png', az, el, ty, sp)
            await page.evaluate("() => window.inezViewer.setHairPhysics(true)")
        if report['hair_setup']:
            # teleport: walk away, then reset position in one frame
            report['teleport'] = await page.evaluate('''() => { const v = window.inezViewer;
                v.resetPosition(); v.setAnimation('automatic', { transition: 0 }); v.setLocomotionSpeed(2.4, { move: true }); v.setHairPhysics(true);
                for (let i = 0; i < 90; i++) v.advance(1 / 60, { render: false });
                const before = v.hairDiagnostics, travelled = v.actorPosition.slice();
                v.resetPosition(); v.advance(1 / 60, { render: false });
                const after = v.hairDiagnostics;
                return { travelled_m: Math.hypot(travelled[0], travelled[2]), resets_before: before.resets, resets_after: after.resets,
                  offset_after_m: after.maxOffsetFromAnimation, recoveries: after.recoveries }; }''')
            # live loop cost (real requestAnimationFrame timing, unpaused)
            await page.evaluate("() => { const v = window.inezViewer; v.captureMode(false); v.pause(false); v.setAnimation('Run', { transition: 0 }); }")
            await page.wait_for_timeout(6000)
            report['live_loop'] = await page.evaluate("() => ({ fps: window.inezViewer.state.fps, hair: window.inezViewer.hairDiagnostics })")
        report['viewer_errors'] = await page.evaluate('window.inezViewer.errors')
        report['backend'] = await page.evaluate('window.inezViewer.state.backend')
        await browser.close()
    clips = report['clips']
    report['checks'] = {
        'hair_simulation_loaded': bool(report.get('hair_setup')),
        'no_browser_errors': not report['errors'] and not report.get('viewer_errors'),
        'stretch_below_2_percent': bool(clips) and all(c['max_relative_stretch'] < .02 for c in clips.values()),
        'no_proxy_penetration': bool(clips) and all(c['max_penetrations'] == 0 for c in clips.values()),
        'no_recoveries': bool(clips) and all(c['recoveries'] == 0 for c in clips.values()),
        'secondary_motion_present_in_run': bool(clips) and clips.get('Run', {}).get('max_offset_from_animation_m', 0) > .01,
        'teleport_resets_without_recovery': bool(report.get('teleport')) and report['teleport']['resets_after'] > report['teleport']['resets_before'] and report['teleport']['recoveries'] == 0,
    }
    report['passed'] = all(report['checks'].values())
    path = CHAR / 'hair/qa' / f'{args.revision}.json'
    path.write_text(json.dumps(report, indent=1) + '\n')
    print(json.dumps({'report': str(path), 'passed': report['passed'], 'checks': report['checks'],
                      'clips': {k: {m: round(v[m], 4) for m in ('max_offset_from_animation_m', 'max_relative_stretch')} for k, v in clips.items()},
                      'teleport': report.get('teleport'), 'live_loop_fps': report.get('live_loop', {}).get('fps'),
                      'hair_ms': report.get('live_loop', {}).get('hair', {}).get('timing_ms') if report.get('live_loop') else None}, indent=1))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--url', default='http://127.0.0.1:4173/')
    ap.add_argument('--model', required=True)
    ap.add_argument('--revision', required=True)
    raise SystemExit(asyncio.run(run(ap.parse_args())))
