"""Exercise the actual exported character in Chromium and capture real frames.

    (cd viewer && npx vite --host 127.0.0.1 --port 4173) &
    python3 tools/inez/browser_qa.py --revision browser_v02 [--model inez_runtime.glb]

Requires the Vite viewer running. Missing geometry, clips or deformation are
failures, never evidence of artistic acceptance. Frames are read from the
WebGL canvas (preserveDrawingBuffer) after an explicit render, because full
page screenshots under SwiftShader timed out on the dressed model. This is an
integration check, not a replacement for likeness and clipping reviews.
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

ROOT = Path(__file__).resolve().parents[2]/'assets/characters/inez'
CHROMIUM = os.environ.get('INEZ_CHROMIUM', '/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
IDENTITY = ('Inez_HeadFit_', 'Inez_HeadRefine_', 'Inez_SourceBodyFit_', 'Inez_SourceHeadWrap_', 'Inez_FaceCorrect_')


def maximum_change(first, second):
    return max((math.dist(a['world'], b['world']) for a, b in zip(first, second)), default=0.0)


async def capture(page, path):
    data = await page.evaluate('''() => { window.inezViewer.renderFrame();
        return document.getElementById('render').toDataURL('image/png'); }''')
    path.write_bytes(base64.b64decode(data.split(',', 1)[1]))


async def run(args):
    destination = ROOT/'renders'/args.revision
    destination.mkdir(parents=True, exist_ok=True)
    url = args.url+('?model='+args.model if args.model else '')
    report = {'url': url, 'revision': args.revision, 'browser': CHROMIUM, 'actual_model_required': True,
              'artistic_approval': False, 'checks': {}, 'screenshots': [], 'page_errors': [], 'console_errors': [],
              'timings_s': {}}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(executable_path=CHROMIUM, headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage', '--enable-unsafe-swiftshader', '--use-angle=swiftshader',
                  '--ignore-gpu-blocklist'])
        page = await browser.new_page(viewport={'width': args.width, 'height': args.height}, device_scale_factor=1)
        page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
        page.on('console', lambda entry: report['console_errors'].append(entry.text) if entry.type == 'error' else None)
        try:
            started = time.time()
            await page.goto(url, wait_until='load', timeout=120000)
            await page.wait_for_function('window.inezViewer?.state.ready === true || window.inezViewer?.state.error',
                                         timeout=300000)
            report['timings_s']['load_to_ready'] = time.time()-started
            state = await page.evaluate('JSON.parse(JSON.stringify(window.inezViewer.state))')
            if not state.get('ready'):
                raise RuntimeError('viewer not ready: '+str(state.get('error')))
            report['backend'] = state['backend']
            report['model_path'] = state.get('modelPath')
            report['asset_info'] = await page.evaluate('window.inezViewer.assetInfo')
            inventory = await page.evaluate('''() => {
                const meshes=[], bones=[]; window.inezViewer.getAvatar().traverse(o=>{
                    if(o.isBone) bones.push(o.name);
                    if(o.isMesh) meshes.push({name:o.name,vertices:o.geometry.attributes.position.count,
                        skinned:!!o.isSkinnedMesh,uv:!!o.geometry.attributes.uv,morphNames:Object.keys(o.morphTargetDictionary||{}),
                        textured:[o.material].flat().some(m=>m&&(m.map||m.normalMap||m.roughnessMap||m.metalnessMap||m.aoMap))});
                }); return {meshes,bones};}''')
            report['inventory'] = inventory
            body = next(m for m in inventory['meshes'] if 'ContinuousHumanMesh' in m['name'])
            report['checks']['actual_skinned_geometry_loaded'] = body['vertices'] > 1000 and len(inventory['bones']) > 100
            # Every textured mesh needs UVs; untextured ones (vertex-coloured
            # teeth/tongue, plain silver necklace) are listed, not failed.
            report['untextured_meshes_without_uv'] = [m['name'] for m in inventory['meshes'] if not m['uv'] and not m['textured']]
            report['checks']['uvs_present'] = all(m['uv'] for m in inventory['meshes'] if m['vertices'] > 0 and m['textured'])
            names = set(report['asset_info']['animations'])
            required = {'Idle', 'Walk', 'Run', 'LookAround', 'TurnLeft', 'TurnRight', 'CrouchDown', 'Crouch', 'CrouchUp',
                        'Expr_SubtleFear', 'Expr_Confusion', 'Expr_Anger', 'Expr_Exhaustion'}
            report['missing_clips'] = sorted(required-names)
            report['checks']['required_clips_present'] = not report['missing_clips']
            indices = list(range(0, body['vertices'], max(1, body['vertices']//96)))[:97]
            # The body exports one primitive per material and Three.js loads
            # each as its own mesh; expressions live on the one holding the head.
            body_parts = [m['name'] for m in inventory['meshes'] if 'ContinuousHumanMesh' in m['name']]
            head_part = await page.evaluate('''names => {
                const avatar=window.inezViewer.getAvatar();avatar.updateMatrixWorld(true);
                const top=n=>{const m=avatar.getObjectByName(n);m.geometry.computeBoundingBox();
                    return m.geometry.boundingBox.clone().applyMatrix4(m.matrixWorld).max.y;};
                return names.reduce((a,b)=>top(b)>top(a)?b:a);
            }''', body_parts)
            report['head_mesh'] = head_part
            head_indices = await page.evaluate('''name => {
                const mesh=window.inezViewer.getAvatar().getObjectByName(name),p=mesh.geometry.attributes.position;
                const rows=[];for(let i=0;i<p.count;i++)rows.push([i,p.getY(i)]);
                // The head part holds only the head and neck: sample every
                // vertex, so brows, lids and mouth are all measured.
                rows.sort((a,b)=>b[1]-a[1]);
                return rows.map(r=>r[0]).slice(0,8000);
            }''', head_part)

            async def sample(chosen, name=None):
                result = await page.evaluate('({name,indices})=>window.inezViewer.sampleDeformedVertices(name,indices)',
                                             {'name': name or body['name'], 'indices': chosen})
                return result['samples']

            async def sample_head(chosen):
                return await sample(chosen, head_part)

            await page.evaluate('''()=>{const v=window.inezViewer;v.pause(true);v.setAnimation('rest',{transition:0});
                v.setExpression('Neutral');v.setViseme('none');v.setFaceControls({autoBlink:false,blinkLeft:0,blinkRight:0,jaw:0});v.resetPosition();}''')
            report['initial_morphs'] = await page.evaluate('window.inezViewer.getMorphInfluences()')
            clip_report = {}
            for clip in ['Idle', 'Walk', 'Run', 'LookAround', 'Crouch']:
                await page.evaluate('clip=>{const v=window.inezViewer;v.setAnimation(clip,{transition:0,restart:true});v.seek(.07);}', clip)
                first = await sample(indices)
                await page.evaluate('window.inezViewer.seek(.41)')
                second = await sample(indices)
                change = maximum_change(first, second)
                clip_report[clip] = {'maximum_sampled_vertex_displacement_m': change, 'deformation_verified': change > 1e-5}
            report['clip_deformation'] = clip_report
            report['checks']['body_clips_deform_actual_mesh'] = all(r['deformation_verified'] for r in clip_report.values())
            # One-shot turn: the viewer moves the clip's final yaw onto the character.
            await page.evaluate('''()=>{const v=window.inezViewer;v.resetPosition();v.setAnimation('Idle',{transition:0});v.pause(false);v.turn('Left');}''')
            await page.evaluate('window.inezViewer.advance(1.6)')
            yaw = await page.evaluate('window.inezViewer.state.characterYaw')
            report['turn_left_character_yaw_rad'] = yaw
            report['checks']['turn_applies_root_yaw'] = abs(yaw-math.pi/2) < 0.05
            await page.evaluate('''()=>{const v=window.inezViewer;v.resetPosition();v.crouch(true);}''')
            await page.evaluate('window.inezViewer.advance(1.2)')
            crouch_state = await page.evaluate('window.inezViewer.state.currentAnimation')
            await page.evaluate('''()=>{const v=window.inezViewer;v.crouch(false);}''')
            await page.evaluate('window.inezViewer.advance(1.2)')
            stand_state = await page.evaluate('window.inezViewer.state.currentAnimation')
            report['crouch_sequence'] = [crouch_state, stand_state]
            report['checks']['crouch_chain_works'] = crouch_state == 'Crouch' and stand_state in ('automatic', 'Idle')
            # Cross-fade.
            await page.evaluate('''()=>{const v=window.inezViewer;v.resetPosition();v.pause(false);v.setAnimation('Idle',{transition:0});v.setAnimation('Walk',{transition:.6});}''')
            await page.evaluate('window.inezViewer.advance(0.25)')
            blend = await page.evaluate('window.inezViewer.state.actionWeights')
            report['crossfade_midpoint_weights'] = blend
            report['checks']['animation_crossfade_has_multiple_active_clips'] = sum(float(w) > 0.01 for w in blend.values()) >= 2
            # Static expressions and the facial performance clips.
            await page.evaluate('''()=>{const v=window.inezViewer;v.pause(true);v.setAnimation('rest',{transition:0});v.setExpression('Neutral');}''')
            neutral = await sample_head(head_indices)
            expression_report = {}
            for expression in ['Confused', 'Suspicious', 'SubtleFear', 'IntenseFear', 'Anger', 'Exhaustion']:
                await page.evaluate('name=>window.inezViewer.setExpression(name,1)', expression)
                posed = await sample_head(head_indices)
                change = maximum_change(neutral, posed)
                expression_report[expression] = {'maximum_sampled_head_displacement_m': change, 'deformation_verified': change > 1e-6}
            report['expression_deformation'] = expression_report
            report['checks']['facial_expressions_deform_real_geometry'] = all(r['deformation_verified'] for r in expression_report.values())
            await page.evaluate("window.inezViewer.setExpression('Neutral')")
            performance = {}
            for clip in ['Expr_SubtleFear', 'Expr_Confusion', 'Expr_Anger', 'Expr_Exhaustion']:
                await page.evaluate('''name=>{const v=window.inezViewer;v.pause(false);v.playPerformance(name);}''', clip)
                await page.evaluate('window.inezViewer.advance(1.0)')
                posed = await sample_head(head_indices)
                performance[clip] = {'maximum_sampled_head_displacement_m': maximum_change(neutral, posed)}
                morphs = await page.evaluate('window.inezViewer.getMorphInfluences()')
                performance[clip]['identity_targets_at_default'] = all(
                    abs(t['value']-t['initial']) < 1e-6 for m in morphs for t in m['targets'] if t['name'].startswith(IDENTITY))
                await page.evaluate('window.inezViewer.stopPerformance()')
            report['performance_clips'] = performance
            report['checks']['facial_clips_deform_and_keep_identity'] = all(
                p['maximum_sampled_head_displacement_m'] > 1e-6 and p['identity_targets_at_default'] for p in performance.values())
            before_controls = await sample_head(head_indices)
            await page.evaluate('window.inezViewer.setFaceControls({blinkLeft:1,blinkRight:1,jaw:.3,eyeYaw:.1,headYaw:.1})')
            after_controls = await sample_head(head_indices)
            report['face_control_displacement_m'] = maximum_change(before_controls, after_controls)
            report['checks']['blink_jaw_head_controls_deform_geometry'] = report['face_control_displacement_m'] > 1e-6
            await page.evaluate('window.inezViewer.setFaceControls({blinkLeft:0,blinkRight:0,jaw:0,eyeYaw:0,headYaw:0})')
            report['final_morphs'] = await page.evaluate('window.inezViewer.getMorphInfluences()')
            identity_targets = [t for m in report['final_morphs'] for t in m['targets'] if t['name'].startswith(IDENTITY)]
            report['identity_targets'] = sorted({t['name']: t['value'] for t in identity_targets}.items())
            report['checks']['identity_fit_defaults_preserved'] = bool(identity_targets) and all(
                not t['controlled'] and abs(t['value']-t['initial']) < 1e-6 for t in identity_targets)
            # Keyboard locomotion.
            await page.evaluate('''()=>{const v=window.inezViewer;v.resetPosition();v.setAnimation('automatic',{transition:0});v.pause(false);}''')
            await page.click('#render')
            start_position = await page.evaluate('window.inezViewer.state.characterPosition')
            await page.keyboard.down('w')
            await page.evaluate('window.inezViewer.advance(0.6)')
            walking_state = await page.evaluate('JSON.parse(JSON.stringify(window.inezViewer.state))')
            await page.keyboard.down('Shift')
            await page.evaluate('window.inezViewer.advance(0.6)')
            running_state = await page.evaluate('JSON.parse(JSON.stringify(window.inezViewer.state))')
            await page.keyboard.up('Shift')
            await page.keyboard.up('w')
            report['keyboard'] = {'start': start_position, 'walk_speed': walking_state['locomotionSpeed'],
                                  'run_speed': running_state['locomotionSpeed'], 'walk_position': walking_state['characterPosition']}
            report['checks']['keyboard_moves_character'] = math.dist(start_position, walking_state['characterPosition']) > .01
            report['checks']['shift_increases_running_speed'] = running_state['locomotionSpeed'] > walking_state['locomotionSpeed']+.1
            # Frame rate as measured by the viewer while idling (software renderer).
            await page.evaluate('''()=>{const v=window.inezViewer;v.resetPosition();v.setLocomotionSpeed(0,{immediate:true});v.setAnimation('Idle',{transition:0});v.pause(false);}''')
            await page.wait_for_timeout(4000)
            report['measured_fps_swiftshader'] = await page.evaluate('window.inezViewer.state.fps')
            report['render_stats'] = await page.evaluate('window.inezViewer.state.renderStats')
            await page.evaluate('''()=>{const v=window.inezViewer;v.pause(true);v.setAnimation('rest',{transition:0});
                v.setExpression('Neutral');v.setLighting('studio');v.captureMode(true,{freeze:true});}''')
            shots = [
                ('01_front_portrait', 'face_front', 'Neutral', 'studio', 'rest', 0, None),
                ('02_left_profile', 'face_left', 'Neutral', 'studio', 'rest', 0, None),
                ('03_right_profile', 'face_right', 'Neutral', 'studio', 'rest', 0, None),
                ('04_three_quarter_face', 'face_three_quarter', 'Neutral', 'studio', 'rest', 0, None),
                ('05_body_front', 'body_front', 'Neutral', 'studio', 'rest', 0, None),
                ('06_body_side', 'body_left', 'Neutral', 'studio', 'rest', 0, None),
                ('07_body_back', 'body_back', 'Neutral', 'studio', 'rest', 0, None),
                ('08_body_three_quarter', 'body_three_quarter', 'Neutral', 'studio', 'Idle', .3, None),
                ('09_subtle_fear', 'face_front', 'SubtleFear', 'studio', 'rest', 0, None),
                ('10_confusion', 'face_front', 'Confused', 'studio', 'rest', 0, None),
                ('11_anger', 'face_front', 'Anger', 'studio', 'rest', 0, None),
                ('12_exhaustion', 'face_front', 'Exhaustion', 'studio', 'rest', 0, None),
                ('13_apartment_lighting', 'body_front', 'Neutral', 'apartment', 'Idle', .3, None),
                ('14_walk_pose', 'body_left', 'Neutral', 'studio', 'Walk', .23, None),
                ('15_run_pose', 'body_left', 'Neutral', 'studio', 'Run', .19, None),
                ('16_crouch', 'body_left', 'Neutral', 'studio', 'Crouch', .5, None),
                ('17_look_around', 'body_front', 'Neutral', 'studio', 'LookAround', 1.4, None),
                ('18_wireframe_face', 'face_three_quarter', 'Neutral', 'studio', 'rest', 0, 'wire'),
            ]
            for name, view, expression, lighting, animation, at, mode in shots:
                await page.evaluate('''({view,expression,lighting,animation,at,mode})=>{
                    const v=window.inezViewer;v.setWireframe(mode==='wire');v.setView(view);v.setLighting(lighting);
                    v.setExpression(expression);v.setAnimation(animation,{transition:0,restart:true});v.seek(at);}''',
                                    dict(view=view, expression=expression, lighting=lighting, animation=animation, at=at, mode=mode))
                image = destination/(name+'.png')
                await capture(page, image)
                report['screenshots'].append(str(image.relative_to(ROOT)))
            await page.evaluate('window.inezViewer.setWireframe(false)')
            # The reference comparison panel is HTML beside the canvas, so it
            # needs a real page screenshot. These have timed out under
            # SwiftShader before; a failure is recorded, never replaced.
            await page.evaluate('''()=>{const v=window.inezViewer;v.captureMode(false);v.pause(true);v.controls.autoRotate=false;
                v.setView('face_front');v.setLighting('studio');v.setExpression('Neutral');v.setAnimation('rest',{transition:0});
                v.setReference('original/inez_portraits.jpg');}''')
            await page.wait_for_function("document.getElementById('reference-image').complete", timeout=60000)
            await page.wait_for_timeout(2500)
            await page.evaluate('window.inezViewer.renderFrame()')
            image = destination/'19_reference_comparison_page.png'
            try:
                await page.screenshot(path=str(image), timeout=180000, animations='disabled')
                report['screenshots'].append(str(image.relative_to(ROOT)))
                report['reference_comparison_screenshot'] = 'captured (full page, original A beside the live canvas)'
            except Exception as error:
                report['reference_comparison_screenshot'] = f'failed: {type(error).__name__}: {error}'
            await page.evaluate("window.inezViewer.setReference('none')")
            report['viewer_errors'] = await page.evaluate('window.inezViewer.errors')
            report['viewer_warnings'] = await page.evaluate('window.inezViewer.warnings')
            report['checks']['browser_has_no_runtime_errors'] = not report['page_errors'] and not report['viewer_errors']
        except Exception as error:
            report['failure'] = f'{type(error).__name__}: {error}'
            try:
                await capture(page, destination/'browser_failure.png')
            except Exception:
                pass
        finally:
            report['technical_passed'] = bool(report['checks']) and all(report['checks'].values()) and 'failure' not in report
            target = ROOT/'qa'/('browser_'+args.revision+'.json')
            target.write_text(json.dumps(report, indent=2)+'\n')
            print(json.dumps({'report': str(target), 'technical_passed': report['technical_passed'],
                              'checks': report['checks'], 'failure': report.get('failure')}, indent=2))
            await browser.close()
    return 0 if report['technical_passed'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:4173/')
    parser.add_argument('--model', default='')
    parser.add_argument('--revision', default='browser_v02')
    parser.add_argument('--width', type=int, default=1280)
    parser.add_argument('--height', type=int, default=900)
    raise SystemExit(asyncio.run(run(parser.parse_args())))
