"""Fixed-camera captures from the Inez Digital Human Lab (viewer/digital-human.html).

    (cd viewer && npx vite --host 127.0.0.1 --port 4173) &
    python3 tools/inez/dh_lab_capture.py --out assets/characters/inez/renders/digital_human/m2_skin \
        --config baseline "materials=glb&normals=glb&calibrated=0&tonemap=aces" \
        --config skin "materials=dh" --views face_front face_34_left --presets studio apartment

Each --config is a name and a URL query; every config is captured for every
view x preset with identical camera, pose, resolution and exposure, so that
one change at a time can be compared. Writes <out>/<config>/<preset>_<view>.png
and <out>/capture_report.json (lab state, attachment report incl. the
normal-correction and region numbers, console errors, timings).

The browser is Chromium with SwiftShader: the default backend here is
WebGL2 (WebGPU is lost on this machine's software adapter); pass
--backend webgpu on hardware with a working WebGPU device.
"""
import argparse
import asyncio
import base64
import json
import os
import time
from pathlib import Path

from playwright.async_api import async_playwright

CHROMIUM = os.environ.get('INEZ_CHROMIUM', '/opt/pw-browsers/chromium-1194/chrome-linux/chrome')


async def run(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report = {'url': args.url, 'backend': args.backend, 'size': [args.width, args.height], 'configs': {}}
    flags = ['--no-sandbox', '--disable-dev-shm-usage', '--enable-unsafe-swiftshader', '--use-angle=swiftshader']
    if args.backend == 'webgpu':
        flags += ['--enable-unsafe-webgpu', '--use-webgpu-adapter=swiftshader']
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=CHROMIUM, headless=True, args=flags)
        for name, query in args.config:
            page = await browser.new_page(viewport={'width': args.width + 340, 'height': args.height + 44}, device_scale_factor=1)
            logs = []
            page.on('console', lambda m: m.type in ('error', 'warning') and logs.append(f'{m.type}: {m.text[:400]}'))
            page.on('pageerror', lambda e: logs.append(f'pageerror: {e}'))
            started = time.time()
            q = f'backend={args.backend}&model={args.model}' + (f'&{query}' if query else '')
            await page.goto(f'{args.url}?{q}', wait_until='domcontentloaded', timeout=600000)
            await page.wait_for_function('window.inezDH?.state.ready === true || window.inezDH?.state.error', timeout=600000)
            ready_s = time.time() - started
            state = await page.evaluate('JSON.parse(JSON.stringify(window.inezDH.state))')
            if state.get('error'):
                report['configs'][name] = {'query': q, 'error': state['error'], 'console': logs}
                await page.close()
                continue
            await page.evaluate('() => window.inezDH.pause(true)')
            shots = []
            for preset in args.presets:
                await page.evaluate('p => window.inezDH.setPreset(p)', preset)
                if args.exposure is not None:
                    await page.evaluate('e => window.inezDH.setExposure(e)', args.exposure)
                for view in args.views:
                    await page.evaluate('v => window.inezDH.setView(v)', view)
                    data = await page.evaluate('() => window.inezDH.capture()')
                    data = await page.evaluate('() => window.inezDH.capture()')  # second frame: shadows and PMREM settled
                    path = out / name / f'{preset}_{view}.png'
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(base64.b64decode(data.split(',', 1)[1]))
                    shots.append(str(path))
            report['configs'][name] = {'query': q, 'ready_s': round(ready_s, 2), 'state': state,
                                       'attachment': await page.evaluate('JSON.parse(JSON.stringify(window.inezDH.attachment))'),
                                       'screenshots': shots, 'console': logs[:40]}
            await page.close()
        await browser.close()
    (out / 'capture_report.json').write_text(json.dumps(report, indent=2) + '\n')
    for name, r in report['configs'].items():
        print(name, r.get('error') or f"ready {r['ready_s']} s, {len(r['screenshots'])} shots, {len(r['console'])} console messages")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:4173/digital-human.html')
    parser.add_argument('--out', required=True)
    parser.add_argument('--config', nargs=2, action='append', metavar=('NAME', 'QUERY'), required=True)
    parser.add_argument('--views', nargs='+', default=['face_front'])
    parser.add_argument('--presets', nargs='+', default=['studio'])
    parser.add_argument('--exposure', type=float)
    parser.add_argument('--backend', default='webgl', choices=['webgl', 'webgpu'])
    parser.add_argument('--model', default='inez_runtime.glb')
    parser.add_argument('--width', type=int, default=900)
    parser.add_argument('--height', type=int, default=900)
    asyncio.run(run(parser.parse_args()))


if __name__ == '__main__':
    main()
