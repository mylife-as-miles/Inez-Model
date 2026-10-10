"""Check the externally loaded animation clips on the real Inez in Chromium.

    (cd viewer && npx vite --host 127.0.0.1 --port 4173) &
    python3 tools/inez/browser_lab_qa.py --revision lab_v01

For every clip listed in animation/runtime/clips.json this:

- confirms the clip loaded and bound to Inez's bones (no unbound tracks);
- confirms the viewer labels its source from the manifest, and never as
  TERRA unless the manifest says so;
- steps the clip in fixed 1/60 s steps with the lab's travel on (the in-place
  clip moves at its matching speed), and records the toe-ball and ankle world
  positions of both feet each 1/30 s;
- measures world-space slip per planted phase from those samples, independently
  of the lab's own counter, and also reports the lab's counter;
- captures frames with the contact markers, trail and source stick figure.

Frames are read from the canvas after an explicit render (SwiftShader).
"""
import argparse
import asyncio
import base64
import json
import math
import os
import time
from pathlib import Path

from playwright.async_api import async_playwright

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO/'assets/characters/inez'
CHROMIUM = os.environ.get('INEZ_CHROMIUM', '/opt/pw-browsers/chromium-1194/chrome-linux/chrome')


async def capture(page, path):
    data = await page.evaluate('''() => { window.inezViewer.renderFrame();
        return document.getElementById('render').toDataURL('image/png'); }''')
    path.write_bytes(base64.b64decode(data.split(',', 1)[1]))


def planted_phases(samples, side, lift_limit=0.02, speed_limit=0.3, dt=1/30):
    """Planted = the toe ball within lift_limit of this foot's lowest point and
    moving slower than speed_limit horizontally. Slip = largest horizontal
    distance from the ball's position at the start of the phase."""
    balls = [s[side]['ball'] for s in samples]
    floor = min(b[1] for b in balls)
    phases, current = [], None
    for i, b in enumerate(balls):
        speed = math.hypot(b[0]-balls[i-1][0], b[2]-balls[i-1][2])/dt if i else 0.0
        planted = b[1]-floor < lift_limit and speed < speed_limit
        if planted and current is None:
            current = {'start': i, 'anchor': b, 'slip_m': 0.0}
        if planted and current is not None:
            current['slip_m'] = max(current['slip_m'], math.hypot(b[0]-current['anchor'][0], b[2]-current['anchor'][2]))
            current['end'] = i
        if not planted and current is not None:
            phases.append(current)
            current = None
    if current is not None:
        phases.append(current)
    return [{'frames': [p['start'], p['end']], 'slip_mm': round(p['slip_m']*1000, 2)}
            for p in phases if p['end']-p['start'] >= 3]


def sole_contact(samples, floor_band=0.002):
    """The retargeter's own slip measure, on the skinned boot mesh in the
    browser: a foot is planted while its lowest sole vertex is within
    floor_band of the floor (y = 0); 2 mm is below the retargeter's 3 mm
    swing clearance, as in tools/inez/boot_contact_audit.py. Per planted phase, slip is the summed
    horizontal travel of the vertex in contact at each later frame, between
    that frame and the one before (the same material point), so heel-to-toe
    rolling is not counted as slip."""
    result = {'phases': {}, 'lowest_sole_mm': round(min(s['sole'][f]['lowest_y'] for s in samples for f in 'LR')*1000, 2)}
    for foot in 'LR':
        phases, current = [], None
        for i, s in enumerate(samples):
            planted = s['sole'][foot]['lowest_y'] < floor_band
            if planted and current is None:
                current = {'start': i, 'slip_m': 0.0}
            elif planted:
                current['slip_m'] += s['sole'][foot]['contact_step']
                current['end'] = i
            if not planted and current is not None:
                phases.append(current)
                current = None
        if current is not None:
            phases.append(current)
        result['phases'][foot] = [{'frames': [p['start'], p.get('end', p['start'])], 'slip_mm': round(p['slip_m']*1000, 2)}
                                  for p in phases if p.get('end', p['start'])-p['start'] >= 3]
    return result


async def run(args):
    destination = ROOT/'renders'/args.revision
    destination.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT/'animation/runtime/clips.json').read_text())
    url = args.url+('?model='+args.model if args.model else '')
    report = {'url': url, 'revision': args.revision, 'browser': CHROMIUM, 'renderer_note':
              'SwiftShader software WebGL; timings are not GPU performance', 'checks': {}, 'clips': {},
              'screenshots': [], 'page_errors': [], 'console_errors': [], 'warnings': []}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(executable_path=CHROMIUM, headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage', '--enable-unsafe-swiftshader', '--use-angle=swiftshader',
                  '--ignore-gpu-blocklist'])
        page = await browser.new_page(viewport={'width': args.width, 'height': args.height}, device_scale_factor=1)
        page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
        page.on('console', lambda message: message.type == 'error' and report['console_errors'].append(message.text))
        started = time.time()
        await page.goto(url, wait_until='domcontentloaded', timeout=300000)
        await page.wait_for_function('window.inezViewer?.state.ready === true || window.inezViewer?.state.error',
                                     timeout=300000)
        report['load_to_ready_s'] = time.time()-started
        state = await page.evaluate('JSON.parse(JSON.stringify(window.inezViewer.state))')
        if not state.get('ready'):
            raise RuntimeError('viewer not ready: '+str(state.get('error')))
        report['model_path'] = state.get('modelPath')
        report['external_clips_loaded'] = state.get('externalClips', [])
        report['warnings'] = await page.evaluate('[...window.inezViewer.warnings]')
        options = await page.evaluate('''() => [...document.getElementById('animation').options]
            .map(o => ({value: o.value, text: o.textContent}))''')
        report['animation_options'] = options
        expected = [c['name'] for c in manifest['clips']]
        report['checks']['all_manifest_clips_loaded'] = sorted(report['external_clips_loaded']) == sorted(expected)
        report['checks']['no_unbound_tracks'] = not any('tracks target bones' in w or 'failed to load' in w
                                                        for w in report['warnings'])
        await page.evaluate('''() => { const v = window.inezViewer; v.pause(true); v.setFaceControls({autoBlink:false}); }''')
        labels_ok = True
        for entry in manifest['clips']:
            name = entry['name']
            option = next((o for o in options if o['value'] == name), None)
            want = 'TERRA' if entry.get('terra') else {'cmu_mocap': 'CMU mocap', 'synthetic': 'synthetic test'}.get(entry['kind'], 'procedural')
            label_ok = bool(option) and want in option['text'] and (entry.get('terra') or 'TERRA' not in option['text'])
            labels_ok &= label_ok
            await page.evaluate('''name => { const v = window.inezViewer; v.resetPosition();
                v.setLab('travel', true); v.setLab('contacts', true); v.setLab('trail', true); v.setLab('comparison', true);
                v.setAnimation(name, {transition: 0, restart: true}); }''', name)
            # Reset the lab's per-phase counters for this clip.
            await page.evaluate('''() => { const s = window.inezViewer.lab.stats;
                s.maxPhaseSlipMm = [0, 0]; s.lastPhaseSlipMm = [null, null]; }''')
            await page.evaluate('() => window.inezViewer.advance(0, {render: false})')
            duration = await page.evaluate('window.inezViewer.state.clipDuration')
            # Stop one frame before the loop wraps (the lab resets travel there).
            steps = int(round(duration*30))-2
            samples = await page.evaluate('''steps => { const v = window.inezViewer, out = [];
                const pos = name => { const b = v.getBone(name); return b.getWorldPosition(new b.position.constructor()).toArray(); };
                // The skinned boot mesh, split per foot by the nearer ankle at
                // the first frame: the same surface the retargeter planted.
                let boots; v.getAvatar().traverse(o => { if (!boots && o.isMesh && o.name.startsWith('Inez_Boots')) boots = o; });
                const n = boots.geometry.attributes.position.count, P = new Float32Array(n * 3), Q = new Float32Array(n * 3);
                const tmp = boots.position.clone();
                const fill = target => { boots.updateMatrixWorld(true); boots.skeleton.update();
                    for (let k = 0; k < n; k++) { boots.getVertexPosition(k, tmp); tmp.applyMatrix4(boots.matrixWorld); target.set([tmp.x, tmp.y, tmp.z], 3 * k); } };
                let side = null;
                const sole = (target, previous) => {
                    const r = {};
                    for (const s of ['L', 'R']) {
                        let best = -1, y = Infinity;
                        for (let k = 0; k < n; k++) if (side[k] === s && target[3 * k + 1] < y) { y = target[3 * k + 1]; best = k; }
                        const step = previous ? Math.hypot(target[3 * best] - previous[3 * best], target[3 * best + 2] - previous[3 * best + 2]) : 0;
                        r[s] = {lowest_y: y, vertex: best, contact_step: step};
                    }
                    return r; };
                for (let i = 0; i <= steps; i++) {
                    v.advance(1 / 30, {render: false});
                    const previous = i ? P.slice() : null;
                    fill(P);
                    if (!side) { const a = pos('foot.L'), b = pos('foot.R'); side = [];
                        for (let k = 0; k < n; k++) { const dl = Math.hypot(P[3*k]-a[0], P[3*k+2]-a[2]), dr = Math.hypot(P[3*k]-b[0], P[3*k+2]-b[2]); side.push(dl < dr ? 'L' : 'R'); } }
                    out.push({t: v.state.clipTime, root: v.state.characterPosition,
                        L: {ball: pos('toe1-1.L'), ankle: pos('foot.L')}, R: {ball: pos('toe1-1.R'), ankle: pos('foot.R')},
                        sole: sole(P, previous), lab: JSON.parse(JSON.stringify(v.state.lab ?? {}))});
                }
                return out; }''', steps)
            travel = math.dist(samples[0]['root'], samples[-1]['root'])
            # Feet relative to the character: a clip that does not drive the
            # skeleton leaves these constant while the character travels.
            def local(sample, side, key):
                return [sample[side][key][i]-sample['root'][i] for i in range(3)]
            foot_motion = max(math.dist(local(a, side, 'ball'), local(samples[0], side, 'ball'))
                              for a in samples for side in ('L', 'R'))
            # Loop seam: last sampled pose against the first, character space.
            seam = max(math.dist(local(samples[-1], side, key), local(samples[0], side, key))
                       for side in ('L', 'R') for key in ('ball', 'ankle'))
            sole = sole_contact(samples)
            phases = {side: planted_phases(samples, side) for side in ('L', 'R')}
            last_lab = samples[-1]['lab']
            penetration = [min(s['lab'].get('penetrationMm', [0, 0])[k] for s in samples) for k in (0, 1)]
            result = {
                'source_label': option['text'] if option else None, 'expected_tag': want, 'label_ok': label_ok,
                'manifest_entry': entry, 'duration_s': duration, 'samples': len(samples),
                'character_travel_m': round(travel, 4),
                'max_foot_motion_relative_to_character_m': round(foot_motion, 4),
                'loop_seam_foot_jump_mm': round(seam*1000, 1),
                'travel_speed_m_s': round(travel/max(samples[-1]['t']-samples[0]['t'], 1e-6), 4),
                'sole_contact': sole,
                'max_sole_contact_slip_mm': max((p['slip_mm'] for v in sole['phases'].values() for p in v), default=None),
                'lowest_sole_mm': sole['lowest_sole_mm'],
                'toe_ball_planted_drift': phases,
                'max_toe_ball_drift_mm': max((p['slip_mm'] for v in phases.values() for p in v), default=None),
                'lab_max_phase_slip_mm': last_lab.get('maxPhaseSlipMm'),
                'lab_min_below_floor_mm': penetration,
                'source_stick_figure_loaded': await page.evaluate('n => Boolean(window.inezViewer.lab.trajectories[n])', name),
                'cpu_timing_ms': last_lab.get('timing'),
            }
            report['clips'][name] = result
            # Frames from the side, the camera following the travelling character.
            await page.evaluate('''name => { const v = window.inezViewer; v.resetPosition(); v.setView('body_left');
                v.setAnimation(name, {transition: 0, restart: true}); }''', name)
            for i, step in enumerate((0.5, 0.45, 0.45)):
                await page.evaluate('s => window.inezViewer.advance(s, {render: false})', step)
                path = destination/f"{name.lower()}_{i+1}.png"
                await capture(page, path)
                report['screenshots'].append(str(path.relative_to(REPO)))
        report['checks']['source_labels_match_manifest'] = labels_ok
        report['checks']['clips_drive_the_skeleton'] = all(
            r['max_foot_motion_relative_to_character_m'] > 0.2 for r in report['clips'].values())
        corrected = [r for n, r in report['clips'].items() if not n.endswith('_Raw')]
        report['checks']['corrected_clips_sole_slip_under_10mm'] = all(
            r['max_sole_contact_slip_mm'] is not None and r['max_sole_contact_slip_mm'] < 10 for r in corrected)
        report['checks']['corrected_clips_no_floor_penetration_over_5mm'] = all(r['lowest_sole_mm'] > -5 for r in corrected)
        report['checks']['in_place_clips_travel_at_matching_speed'] = all(
            abs(r['travel_speed_m_s']-r['manifest_entry']['matching_speed_m_s']) < 0.05 for r in report['clips'].values()
            if r['manifest_entry'].get('in_place'))
        report['checks']['no_page_errors'] = not report['page_errors']
        report['passed'] = all(report['checks'].values())
        await browser.close()
    out = ROOT/'animation/qa'/f'browser_{args.revision}.json'
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps({'checks': report['checks'], 'clips': {n: {k: r[k] for k in (
        'source_label', 'max_sole_contact_slip_mm', 'lowest_sole_mm', 'max_toe_ball_drift_mm', 'lab_max_phase_slip_mm', 'lab_min_below_floor_mm', 'travel_speed_m_s',
        'max_foot_motion_relative_to_character_m', 'loop_seam_foot_jump_mm', 'duration_s')}
        for n, r in report['clips'].items()}}, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:4173/')
    parser.add_argument('--model')
    parser.add_argument('--revision', default='lab_v01')
    parser.add_argument('--width', type=int, default=960)
    parser.add_argument('--height', type=int, default=720)
    asyncio.run(run(parser.parse_args()))


if __name__ == '__main__':
    main()
