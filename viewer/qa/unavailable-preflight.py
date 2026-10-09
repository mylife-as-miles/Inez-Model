"""Local viewer foundation preflight. This never validates a character asset."""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from playwright.async_api import async_playwright

QA = Path(__file__).parent


async def main():
    report = {'scope': 'Viewer foundation only. Authored GLB unavailable; no character or deformation approval.',
              'timestamp': datetime.now(timezone.utc).isoformat(), 'browser': 'Chromium / SwiftShader WebGL2',
              'checks': {}, 'pageErrors': [], 'consoleErrors': [], 'consoleWarnings': [], 'glbRequests': [], 'screenshots': []}
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path='/usr/bin/chromium', headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage', '--enable-unsafe-swiftshader', '--use-angle=swiftshader'])
        page = await browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.on('pageerror', lambda error: report['pageErrors'].append(str(error)))
        page.on('console', lambda entry: report['consoleErrors' if entry.type == 'error' else 'consoleWarnings'].append(entry.text)
                if entry.type in ['error', 'warning'] else None)
        page.on('request', lambda request: report['glbRequests'].append(request.url) if '.glb' in request.url else None)
        try:
            await page.goto('http://127.0.0.1:4173/', wait_until='networkidle')
            await page.wait_for_function('window.inezViewer && !window.inezViewer.state.loading')
            report['initial'] = await page.evaluate('''() => {
                const v=window.inezViewer;return {state:v.state,errors:v.errors,warnings:v.warnings,api:Object.keys(v),
                disabled:['animation','expression','viseme','jaw','eye-yaw','head-yaw','pause','timeline','movement-speed','material'].map(id=>({id,disabled:document.getElementById(id).disabled}))};
            }''')
            checks = report['checks']
            checks['truthful_unavailable_state'] = report['initial']['state']['ready'] is False and report['initial']['state']['assetInfo'] is None
            checks['asset_controls_disabled'] = all(x['disabled'] for x in report['initial']['disabled'])
            report['views'] = await page.evaluate('''()=>[...document.getElementById('view').options].map(o=>({name:o.value,ok:window.inezViewer.setView(o.value)}))''')
            checks['all_camera_presets_work'] = all(v['ok'] for v in report['views'])
            report['lightControls'] = await page.evaluate('''()=>{const v=window.inezViewer;v.setLighting('apartment');return v.setLightControls({exposure:1.2,key:1.4,fill:.7,ambient:.4})}''')
            checks['lighting_controls_work'] = report['lightControls'] == {'exposure': 1.2, 'key': 1.4, 'fill': .7, 'ambient': .4}
            checks['no_fake_asset_api_results'] = await page.evaluate('''()=>{const v=window.inezViewer;return !v.getAvatar() && v.sampleDeformedVertices('fake',[0])===null && v.advance(.2)===false && v.setAnimation('Walk')===false && v.setExpression('Anger')===false && v.getMorphInfluences().length===0}''')
            await page.evaluate("window.inezViewer.setView('body_front');window.inezViewer.setLighting('studio');window.inezViewer.setReference('original/inez_portraits.jpg')")
            await page.wait_for_function("document.getElementById('reference-image').complete && document.getElementById('reference-image').naturalWidth > 0")
            checks['original_reference_loaded'] = True
            await page.screenshot(path=str(QA/'unavailable_reference_comparison.png')); report['screenshots'].append('unavailable_reference_comparison.png')
            await page.evaluate('window.inezViewer.captureMode(true,{freeze:true})')
            checks['capture_freezes_and_hides_ui'] = await page.evaluate("window.inezViewer.state.paused && getComputedStyle(document.querySelector('aside')).display==='none'")
            await page.screenshot(path=str(QA/'unavailable_capture_mode.png')); report['screenshots'].append('unavailable_capture_mode.png')
            await page.evaluate('window.inezViewer.captureMode(false)')
            checks['capture_restores_playback'] = await page.evaluate('window.inezViewer.state.capture===false && window.inezViewer.state.paused===false')
            report['materialModuleFixtures'] = await page.evaluate("async()=>{const {runMaterialRegression}=await import('/qa/material-regression.js');return runMaterialRegression()}")
            checks['material_module_fixtures_pass'] = all(report['materialModuleFixtures']['checks'].values())
            report['viewerErrors'] = await page.evaluate('window.inezViewer.errors')
            checks['no_glb_requested'] = not report['glbRequests']
            checks['no_runtime_errors'] = not report['pageErrors'] and not report['consoleErrors'] and not report['viewerErrors']
        except Exception as error:
            report['failure'] = str(error)
        finally:
            report['foundation_passed'] = bool(report['checks']) and all(report['checks'].values()) and 'failure' not in report
            report['actual_character_validated'] = False
            (QA/'unavailable_preflight.json').write_text(json.dumps(report, indent=2)+'\n')
            await browser.close()
    print(json.dumps({k: report.get(k) for k in ['foundation_passed','actual_character_validated','checks','failure','pageErrors','consoleErrors','consoleWarnings']}, indent=2))
    return 0 if report['foundation_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
