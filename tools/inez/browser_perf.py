"""Frame-rate and CPU-time measurement of the Inez viewer, per LOD.

    (cd viewer && npx vite --host 127.0.0.1 --port 4173) &
    python3 tools/inez/browser_perf.py --label this_machine            # software WebGL (SwiftShader)
    python3 tools/inez/browser_perf.py --label my_laptop --gpu          # the machine's real GPU

Run with --gpu on the hardware being judged. Without it Chromium is forced onto
SwiftShader, the CPU rasteriser this container has, and the numbers say
nothing about a GPU. For each model it loads the viewer, plays Idle and
then Walk in place for --seconds each, and records the viewer's own counters:

- frames per second;
- rolling CPU time for animation, lab and render submission;
- triangles, draw calls and textures;
- load-to-ready time.

The browser's WebGL renderer string is recorded so the report names the
hardware actually measured.
"""
import argparse
import asyncio
import json
import os
import platform
import time
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]/'assets/characters/inez'
CHROMIUM = os.environ.get('INEZ_CHROMIUM', '/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
MODELS = ('inez_runtime.glb', 'inez_runtime_lod1.glb', 'inez_runtime_lod2.glb')


async def measure(browser, url, model, seconds, size):
    page = await browser.new_page(viewport={'width': size[0], 'height': size[1]}, device_scale_factor=1)
    started = time.time()
    await page.goto(f'{url}?model={model}', wait_until='domcontentloaded', timeout=600000)
    await page.wait_for_function('window.inezViewer?.state.ready === true || window.inezViewer?.state.error', timeout=600000)
    ready = time.time()-started
    gl = await page.evaluate('''() => { const c = document.createElement('canvas').getContext('webgl2');
        const ext = c && c.getExtension('WEBGL_debug_renderer_info');
        return c ? {vendor: c.getParameter(ext ? ext.UNMASKED_VENDOR_WEBGL : c.VENDOR),
                    renderer: c.getParameter(ext ? ext.UNMASKED_RENDERER_WEBGL : c.RENDERER)} : null; }''')
    result = {'model': model, 'load_to_ready_s': round(ready, 2), 'webgl': gl, 'phases': {}}
    for clip in ('Idle', 'Walk'):
        await page.evaluate('''clip => { const v = window.inezViewer; v.resetPosition(); v.pause(false);
            v.setLab('travel', false); v.setAnimation(clip, {transition: 0, restart: true}); }''', clip)
        await page.wait_for_timeout(1500)  # settle the rolling averages
        samples = []
        end = time.time()+seconds
        while time.time() < end:
            await page.wait_for_timeout(1000)
            samples.append(await page.evaluate('''() => { const s = window.inezViewer.state;
                return {fps: s.fps, cpu_ms: s.lab?.timing ?? null, stats: s.renderStats}; }'''))
        fps = [s['fps'] for s in samples if s['fps']]
        result['phases'][clip] = {
            'fps_mean': round(sum(fps)/len(fps), 3) if fps else None,
            'fps_min': round(min(fps), 3) if fps else None,
            'cpu_ms_last': samples[-1]['cpu_ms'] if samples else None,
            'render_stats': samples[-1]['stats'] if samples else None,
        }
    await page.close()
    return result


async def run(args):
    flags = ['--no-sandbox', '--disable-dev-shm-usage', '--ignore-gpu-blocklist']
    if not args.gpu:
        flags += ['--enable-unsafe-swiftshader', '--use-angle=swiftshader']
    report = {'label': args.label, 'gpu_requested': args.gpu, 'viewport': [args.width, args.height],
              'host': {'platform': platform.platform(), 'cpus': os.cpu_count()}, 'models': []}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(executable_path=CHROMIUM, headless=not args.headed, args=flags)
        for model in args.models:
            report['models'].append(await measure(browser, args.url, model, args.seconds, (args.width, args.height)))
        await browser.close()
    out = ROOT/'qa/technical'/f'performance_{args.label}.json'
    out.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:4173/')
    parser.add_argument('--label', required=True, help='names the output file, e.g. the machine')
    parser.add_argument('--gpu', action='store_true', help='use the real GPU instead of SwiftShader')
    parser.add_argument('--headed', action='store_true', help='visible window (some GPUs need it)')
    parser.add_argument('--models', nargs='+', default=list(MODELS))
    parser.add_argument('--seconds', type=float, default=8)
    parser.add_argument('--width', type=int, default=1280)
    parser.add_argument('--height', type=int, default=720)
    asyncio.run(run(parser.parse_args()))


if __name__ == '__main__':
    main()
