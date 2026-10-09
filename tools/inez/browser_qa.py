"""Exercise the actual exported character in Chromium and capture real geometry.

Requires the Vite viewer running. Missing geometry, clips or deformation are
failures, never evidence of artistic acceptance. This is an integration check,
not a replacement for independent likeness and clipping reviews.
"""
import argparse
import asyncio
import json
import math
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path('/workspace/assets/characters/inez')


def maximum_change(first, second):
    return max((math.dist(a['world'], b['world']) for a, b in zip(first, second)), default=0.0)


async def run(args):
    destination = ROOT / 'renders' / args.revision
    destination.mkdir(parents=True, exist_ok=True)
    report = {'url': args.url, 'revision': args.revision, 'actual_model_required': True,
              'artistic_approval': False, 'checks': {}, 'screenshots': [],
              'page_errors': [], 'console_errors': []}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(executable_path='/usr/bin/chromium', headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage', '--enable-unsafe-swiftshader', '--use-angle=swiftshader'])
        page = await browser.new_page(viewport={'width': 1440, 'height': 1000}, device_scale_factor=1)
        page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
        page.on('console', lambda entry: report['console_errors'].append(entry.text) if entry.type == 'error' else None)
        try:
            await page.goto(args.url, wait_until='networkidle', timeout=60000)
            await page.wait_for_function('window.inezViewer?.state.ready === true', timeout=45000)
            report['asset_info'] = await page.evaluate('window.inezViewer.assetInfo || window.inezViewer.state.assetInfo')
            report['viewer_errors'] = await page.evaluate('window.inezViewer.errors')
            inventory = await page.evaluate('''() => {
                const v=window.inezViewer, avatar=v.getAvatar();
                const meshes=[], bones=[];
                avatar.traverse(o=>{
                    if(o.isBone) bones.push(o.name);
                    if(o.isMesh) meshes.push({name:o.name,vertices:o.geometry.attributes.position.count,
                        skinned:!!o.isSkinnedMesh,uv:!!o.geometry.attributes.uv,
                        morphNames:Object.keys(o.morphTargetDictionary||{})});
                }); return {meshes,bones};
            }''')
            report['inventory'] = inventory
            body = next((m for m in inventory['meshes'] if 'ContinuousHumanMesh' in m['name']),
                        next(m for m in inventory['meshes'] if m['skinned']))
            report['checks']['actual_skinned_geometry_loaded'] = body['vertices'] > 1000 and bool(inventory['bones'])
            report['checks']['uvs_present'] = all(m['uv'] for m in inventory['meshes'] if m['vertices'] > 0)
            indices = list(range(0, body['vertices'], max(1, body['vertices']//96)))[:97]
            head_indices = await page.evaluate('''name => {
                const mesh=window.inezViewer.getAvatar().getObjectByName(name),p=mesh.geometry.attributes.position;
                const rows=[];for(let i=0;i<p.count;i++)rows.push([i,p.getY(i)]);
                rows.sort((a,b)=>b[1]-a[1]);const head=rows.slice(0,Math.max(300,Math.floor(rows.length*.13)));
                return head.filter((_,i)=>i%Math.max(1,Math.floor(head.length/160))===0).map(r=>r[0]).slice(0,180);
            }''', body['name'])

            async def sample(chosen):
                result = await page.evaluate('''({name,indices})=>window.inezViewer.sampleDeformedVertices(name,indices)''',
                                             {'name': body['name'], 'indices': chosen})
                return result['samples']

            await page.evaluate('''() => {const v=window.inezViewer;v.pause(true);v.setAnimation('rest',{transition:0});
                v.setExpression('Neutral');v.setViseme('Neutral');v.setFaceControls({autoBlink:false,blinkLeft:0,blinkRight:0,jaw:0});v.resetPosition();}''')
            initial_fit = await page.evaluate('window.inezViewer.getMorphInfluences()')
            report['initial_morphs'] = initial_fit
            clip_report = {}
            for clip in ['Idle', 'Walk', 'Run']:
                await page.evaluate('''clip=>{const v=window.inezViewer;v.setAnimation(clip,{transition:0,restart:true});v.seek(.07);}''', clip)
                first = await sample(indices)
                await page.evaluate('window.inezViewer.seek(.41)')
                second = await sample(indices)
                change = maximum_change(first, second)
                clip_report[clip] = {'maximum_sampled_vertex_displacement_m': change, 'deformation_verified': change > 0.00001}
            report['clip_deformation'] = clip_report
            report['checks']['idle_walk_run_deform_actual_mesh'] = all(row['deformation_verified'] for row in clip_report.values())

            await page.evaluate('''()=>{const v=window.inezViewer;v.pause(false);v.setAnimation('Idle',{transition:0});v.setAnimation('Walk',{transition:.6});}''')
            await page.wait_for_timeout(220)
            blend = await page.evaluate('window.inezViewer.state.actionWeights')
            report['crossfade_midpoint_weights'] = blend
            report['checks']['animation_crossfade_has_multiple_active_clips'] = sum(float(w)>0.01 for w in blend.values()) >= 2
            await page.wait_for_timeout(700)

            await page.evaluate('''()=>{const v=window.inezViewer;v.pause(true);v.setAnimation('rest',{transition:0});v.setExpression('Neutral');}''')
            neutral = await sample(head_indices)
            expression_report = {}
            for expression in ['Confused','Suspicious','SubtleFear','IntenseFear','Anger','Exhaustion']:
                await page.evaluate('name=>window.inezViewer.setExpression(name,1)', expression)
                posed = await sample(head_indices)
                change = maximum_change(neutral, posed)
                expression_report[expression] = {'maximum_sampled_head_displacement_m': change, 'deformation_verified': change>0.000001}
            report['expression_deformation'] = expression_report
            report['checks']['facial_expressions_deform_real_geometry'] = all(row['deformation_verified'] for row in expression_report.values())
            await page.evaluate("window.inezViewer.setExpression('Neutral')")
            before_controls = await sample(head_indices)
            await page.evaluate('window.inezViewer.setFaceControls({blinkLeft:1,blinkRight:1,jaw:.3,eyeYaw:.1,headYaw:.1})')
            after_controls = await sample(head_indices)
            report['face_control_displacement_m'] = maximum_change(before_controls, after_controls)
            report['checks']['blink_jaw_head_controls_deform_geometry'] = report['face_control_displacement_m']>0.000001
            await page.evaluate('window.inezViewer.setFaceControls({blinkLeft:0,blinkRight:0,jaw:0,eyeYaw:0,headYaw:0})')
            report['final_morphs'] = await page.evaluate('window.inezViewer.getMorphInfluences()')
            fit_targets = [target for mesh in report['final_morphs'] for target in mesh['targets']
                           if target['name'].startswith('Inez_HeadFit_')]
            report['checks']['identity_fit_defaults_preserved'] = bool(fit_targets) and all(
                not target['controlled'] and abs(target['value']-target['initial'])<0.000001
                for target in fit_targets)

            await page.evaluate('''()=>{const v=window.inezViewer;v.resetPosition();v.setAnimation('automatic',{transition:0});v.pause(false);}''')
            start_position = await page.evaluate('window.inezViewer.state.characterPosition')
            await page.keyboard.down('w')
            await page.wait_for_timeout(450)
            walking_state = await page.evaluate('JSON.parse(JSON.stringify(window.inezViewer.state))')
            await page.keyboard.down('Shift')
            await page.wait_for_timeout(450)
            running_state = await page.evaluate('JSON.parse(JSON.stringify(window.inezViewer.state))')
            await page.keyboard.up('Shift')
            await page.keyboard.up('w')
            report['keyboard_start_position'] = start_position
            report['keyboard_walking_state'] = walking_state
            report['keyboard_running_state'] = running_state
            report['checks']['keyboard_moves_character'] = math.dist(start_position, walking_state['characterPosition']) > .01
            report['checks']['shift_increases_running_speed'] = running_state['locomotionSpeed'] > walking_state['locomotionSpeed'] + .1
            await page.evaluate('''()=>{const v=window.inezViewer;v.resetPosition();v.setLocomotionSpeed(0,{immediate:true});v.pause(true);v.setAnimation('rest',{transition:0});
                v.setExpression('Neutral');v.setLighting('studio');v.captureMode(true,{freeze:true});}''')

            for name, view, expression, lighting, animation, time in [
                ('01_front_portrait','face_front','Neutral','studio','rest',0),
                ('02_left_profile','face_left','Neutral','studio','rest',0),
                ('03_right_profile','face_right','Neutral','studio','rest',0),
                ('04_three_quarter_face','face_three_quarter','Neutral','studio','rest',0),
                ('05_body_front','body_front','Neutral','studio','rest',0),
                ('06_body_side','body_left','Neutral','studio','rest',0),
                ('07_body_back','body_back','Neutral','studio','rest',0),
                ('08_neutral_expression','face_front','Neutral','studio','Idle',.3),
                ('09_fear_expression','face_front','IntenseFear','studio','rest',0),
                ('10_apartment_lighting','body_front','Neutral','apartment','Idle',.3),
                ('11_walk_pose','body_front','Neutral','studio','Walk',.23),
                ('12_run_pose','body_left','Neutral','studio','Run',.19)]:
                await page.evaluate('''({view,expression,lighting,animation,time})=>{
                    const v=window.inezViewer;v.setView(view);v.setLighting(lighting);v.setExpression(expression);
                    v.setAnimation(animation,{transition:0,restart:true});v.seek(time);
                }''', dict(view=view,expression=expression,lighting=lighting,animation=animation,time=time))
                await page.wait_for_timeout(100)
                image = destination / (name+'.png')
                await page.screenshot(path=str(image))
                report['screenshots'].append(str(image.relative_to(ROOT)))
            report['viewer_errors'] = await page.evaluate('window.inezViewer.errors')
            report['checks']['browser_has_no_runtime_errors'] = not report['page_errors'] and not report['viewer_errors']
        except Exception as error:
            report['failure'] = str(error)
            await page.screenshot(path=str(destination/'browser_failure.png'))
        finally:
            report['technical_passed'] = bool(report['checks']) and all(report['checks'].values()) and 'failure' not in report
            target = ROOT/'qa'/('browser_'+args.revision+'.json')
            target.write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps({'report':str(target),'technical_passed':report['technical_passed'],'checks':report['checks'],'failure':report.get('failure')},indent=2))
            await browser.close()
    return 0 if report['technical_passed'] else 1


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:4173/')
    parser.add_argument('--revision',default='browser_v01');arguments=parser.parse_args()
    raise SystemExit(asyncio.run(run(arguments)))
