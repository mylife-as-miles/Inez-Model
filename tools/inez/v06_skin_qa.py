"""Actual Inez WebGL2 diffusion integration, screenshots and timed full frames.

Software Chromium is explicit by default. --hardware removes SwiftShader
flags; diagnostics still record the real renderer and do not infer GPU use.
Run target-hardware benchmarks separately from concurrent capture jobs.
"""
import argparse
import asyncio
import base64
import io
import json
import os
import time
from pathlib import Path

import numpy as np
from PIL import Image
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[2]
CHAR=ROOT/'assets/characters/inez'


def compare(a,b,mask=None):
    d=np.abs(a[:,:,:3].astype(float)-b[:,:,:3].astype(float))
    if mask is not None:d=d[mask]
    return {'mean_abs_rgb_8bit':float(d.mean()),'max_abs_rgb_8bit':float(d.max()),
            'fraction_pixels_changed':float((d.max(axis=-1)>0).mean())}


async def run(args):
    destination=CHAR/'renders'/args.revision;destination.mkdir(parents=True,exist_ok=True)
    report={'model':args.model,'backend_requested':args.backend,'hardware_flags_requested':args.hardware,
        'artistic_approval':False,'target_gpu_validation':False,'errors':[],'checks':{},'screenshots':[],
        'performance_note':'Full character frames; timings on the recorded renderer only. No laptop/VR guarantee.'}
    async with async_playwright() as p:
        flags=['--no-sandbox','--disable-dev-shm-usage','--enable-precise-memory-info']
        if not args.hardware:flags+=['--enable-unsafe-swiftshader','--use-angle=swiftshader']
        browser=await p.chromium.launch(executable_path=os.environ.get('INEZ_CHROMIUM','/usr/bin/chromium'),args=flags)
        page=await browser.new_page(viewport={'width':args.width,'height':args.height},device_scale_factor=1)
        page.set_default_timeout(180000)
        page.on('pageerror',lambda e:report['errors'].append(str(e)))
        page.on('console',lambda e:report['errors'].append(e.text) if e.type=='error' else None)
        start=time.monotonic()
        await page.goto(args.url+'?model='+args.model+('&renderer=webgpu' if args.backend=='webgpu' else ''),timeout=180000)
        await page.wait_for_function('window.inezViewer?.state.ready || window.inezViewer?.state.error',timeout=300000)
        report['load_to_ready_s']=time.monotonic()-start
        if not await page.evaluate('window.inezViewer.state.ready'):raise RuntimeError(await page.evaluate('window.inezViewer.state.error'))
        await page.evaluate('''() => {const v=window.inezViewer;v.renderer.setAnimationLoop(null);
            v.captureMode(true);v.pause(true);v.resetPosition();v.setAnimation('rest',{transition:0});v.resetFace();v.setView('face_front');}''')
        report['asset_info']=await page.evaluate('window.inezViewer.assetInfo')
        report['identity_before']=await page.evaluate('window.inezViewer.getMorphInfluences()')
        report['actual_backend']=await page.evaluate('window.inezViewer.state.backend')
        report['diagnostics']=await page.evaluate('window.inezViewer.digitalHuman.diagnostics')

        async def settings(values):
            return await page.evaluate('values=>window.inezViewer.setSkin(values)',values)

        async def capture(name):
            data=await page.evaluate('''() => {window.inezViewer.renderFrame();return document.getElementById('render').toDataURL('image/png');}''')
            raw=base64.b64decode(data.split(',',1)[1]);(destination/(name+'.png')).write_bytes(raw)
            report['screenshots'].append(name+'.png')
            return np.array(Image.open(io.BytesIO(raw)).convert('RGBA'))

        if not report['diagnostics']['skinDiffusionSupported']:
            await settings({'mode':'enhanced'})
            report['checks']['unsupported_backend_keeps_original_pbr']=await page.evaluate('''() => {
                const r=window.inezViewer.digitalHuman;return [...r.originals].every(([mesh,material])=>mesh.material===material);}''')
            await page.evaluate("window.inezViewer.setLighting('neutral')")
            await capture('backend_fallback')
        else:
            report['checks']['actual_named_skin_meshes_used']=len(report['diagnostics']['activeSkinMeshes'])>=2
            report['checks']['thickness_attributes_loaded']=all(x['available'] for x in report['diagnostics']['thickness'])
            comparisons={}
            if not args.performance_only:
                for lighting in ['neutral','apartment']:
                    await page.evaluate('preset=>window.inezViewer.setLighting(preset)',lighting)
                    await settings({'mode':'existing','debug':'off'})
                    pbr=await capture(lighting+'_existing')
                    await settings({'mode':'enhanced','sss':False,'strength':.55,'radius':1,
                        'microNormal':0,'roughnessVariation':1,'thinTransmission':False,'quality':'gameplay'})
                    off=await capture(lighting+'_sss_off')
                    await settings({'sss':True})
                    on=await capture(lighting+'_sss_on')
                    comparisons[lighting]={'existing_vs_enhanced_off':compare(pbr,off),'sss_on_vs_off':compare(off,on),
                        'camera':await page.evaluate('({position:window.inezViewer.camera.position.toArray(),projection:window.inezViewer.camera.projectionMatrix.toArray()})')}
                    report['checks'][lighting+'_diffusion_changes_pixels']=compare(off,on)['max_abs_rgb_8bit']>0
                    # Read the actual normal-pass alpha to isolate non-skin.
                    alpha=await page.evaluate('''() => {const v=window.inezViewer,r=v.digitalHuman.pipeline;
                        const pixels=new Uint8Array(r.size.x*r.size.y*4);v.renderer.readRenderTargetPixels(r.normal,0,0,r.size.x,r.size.y,pixels);
                        return {width:r.size.x,height:r.size.y,alpha:Array.from(pixels.filter((_,i)=>i%4===3))};}''')
                    skin=np.array(alpha['alpha'],dtype=np.uint8).reshape(alpha['height'],alpha['width'])[::-1]>0
                    # Exclude a 3px boundary band (MSAA/diffuse edge filtering).
                    from scipy.ndimage import binary_dilation
                    outside=~binary_dilation(skin,iterations=3)
                    comparisons[lighting]['non_skin_on_vs_off']=compare(off,on,outside)
                    report['checks'][lighting+'_non_skin_unchanged']=compare(off,on,outside)['max_abs_rgb_8bit']<=1
                await page.evaluate("window.inezViewer.setLighting('neutral')")
                await settings({'mode':'enhanced','sss':True,'strength':0})
                zero=await capture('strength_zero')
                await settings({'sss':False})
                disabled=await capture('disabled')
                report['checks']['zero_strength_equals_disabled']=compare(zero,disabled)['max_abs_rgb_8bit']==0
                await settings({'sss':True,'strength':1,'radius':3})
                strong=await capture('wide_diffusion')
                await settings({'radius':.25})
                narrow=await capture('narrow_diffusion')
                report['checks']['radius_changes_pixels']=compare(strong,narrow)['max_abs_rgb_8bit']>0
                await settings({'strength':.55,'radius':1,'roughnessVariation':0,'microNormal':0})
                uniform_roughness=await capture('uniform_roughness')
                await settings({'roughnessVariation':1,'microNormal':0})
                plain=await capture('mapped_roughness_no_micro')
                await settings({'microNormal':1})
                micro=await capture('micro_normal_full')
                report['checks']['roughness_control_changes_pixels']=compare(uniform_roughness,plain)['max_abs_rgb_8bit']>0
                report['checks']['micro_normal_control_changes_pixels']=compare(micro,plain)['max_abs_rgb_8bit']>0
                await settings({'microNormal':0})
                for debug in ['diffuse','scattered','normals','thickness']:
                    await settings({'debug':debug});await capture('debug_'+debug)
                await settings({'debug':'off','thinTransmission':False})
                await page.evaluate("window.inezViewer.setLighting('backlight');window.inezViewer.setView('face_three_quarter')")
                thin_off=await capture('thin_transmission_off')
                await settings({'thinTransmission':True})
                thin_on=await capture('thin_transmission_on')
                report['checks']['thin_transmission_changes_pixels']=compare(thin_off,thin_on)['max_abs_rgb_8bit']>0
                report['thin_comparison']=compare(thin_off,thin_on)
                await settings({'thinTransmission':False})
                report['checks']['thin_toggle_updates_uniforms']=await page.evaluate('''() => [...window.inezViewer.digitalHuman.records.values()].every(r=>r.uniforms.dhThinEnabled.value===0)''')
                await page.evaluate("window.inezViewer.setView('face_front');window.inezViewer.setLighting('neutral');window.inezViewer.setFaceControls({blinkLeft:1,blinkRight:1})")
                await capture('enhanced_blink')
                await page.evaluate("window.inezViewer.resetFace();window.inezViewer.setExpression('SubtleFear',.7)")
                await capture('enhanced_subtle_fear')
                await page.evaluate('window.inezViewer.resetFace();window.inezViewer.setWireframe(true)')
                report['checks']['wireframe_preserved']=await page.evaluate('''() => [...window.inezViewer.digitalHuman.records.values()].every(r=>r.material.wireframe)''')
                await page.evaluate('window.inezViewer.setWireframe(false)')
                await settings({'mode':'existing'})
                report['checks']['original_material_references_restored']=await page.evaluate('''() => [...window.inezViewer.digitalHuman.originals].every(([m,a])=>m.material===a)''')
                report['comparisons']=comparisons

            if not args.skip_performance:
                await page.evaluate("window.inezViewer.setView('face_front');window.inezViewer.setLighting('neutral')")
                benchmarks={}
                for name,values in [('existing',{'mode':'existing'}),('enhanced_off',{'mode':'enhanced','sss':False}),
                                    ('enhanced_on',{'mode':'enhanced','sss':True}),('cinematic',{'mode':'enhanced','sss':True,'quality':'cinematic'})]:
                    await settings({'quality':'gameplay','debug':'off','microNormal':.15,'roughnessVariation':1,'radius':1,'strength':.55,**values})
                    benchmarks[name]=await page.evaluate('''async frames => {
                        const v=window.inezViewer,gl=v.renderer.getContext(),draw=()=>{v.renderFrame();gl.finish();};
                        let start=performance.now();draw();const warm=performance.now()-start;
                        const times=[];for(let i=0;i<frames;i++){await new Promise(requestAnimationFrame);start=performance.now();draw();times.push(performance.now()-start);}
                        const ordered=[...times].sort((a,b)=>a-b),median=ordered[Math.floor(ordered.length/2)];
                        return {frames,frame_times_ms:times,median_frame_ms:median,median_frame_fps:1000/median,
                            warm_frame_ms: warm,first_frame_note:'includes lazy shader compilation/target allocation; not isolated compilation time',
                            frame_note:'wall-clock full render + gl.finish; not GPU pass timing',
                            render:{...v.renderer.info.render},renderer_memory:{...v.renderer.info.memory},
                            js_heap:performance.memory?{used:performance.memory.usedJSHeapSize,total:performance.memory.totalJSHeapSize}:null,
                            pipeline:v.digitalHuman.diagnostics.pipeline};}''',args.frames)
                report['benchmarks']=benchmarks
        report['identity_after']=await page.evaluate('window.inezViewer.getMorphInfluences()')
        report['checks']['identity_and_morph_defaults_preserved']=report['identity_before']==report['identity_after']
        report['diagnostics']=await page.evaluate('window.inezViewer.digitalHuman.diagnostics')
        report['checks']['no_shader_failures']=not report['diagnostics']['shaderFailures']
        report['checks']['no_browser_errors']=not report['errors'] and not await page.evaluate('window.inezViewer.errors')
        report['resolution']=await page.evaluate('({width:document.getElementById("render").width,height:document.getElementById("render").height})')
        await browser.close()
    report['technical_passed']=all(report['checks'].values())
    output=CHAR/'qa'/'v06'/(args.revision+'.json');output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'report':str(output),'passed':report['technical_passed'],'checks':report['checks'],'errors':report['errors']}))
    return int(not report['technical_passed'])


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:4173/')
    p.add_argument('--model',default='v06/inez_recovery_v06.glb');p.add_argument('--revision',required=True)
    p.add_argument('--backend',choices=['webgl','webgpu'],default='webgl');p.add_argument('--hardware',action='store_true')
    p.add_argument('--width',type=int,default=900);p.add_argument('--height',type=int,default=680)
    p.add_argument('--frames',type=int,default=5);p.add_argument('--skip-performance',action='store_true')
    p.add_argument('--performance-only',action='store_true')
    raise SystemExit(asyncio.run(run(p.parse_args())))
