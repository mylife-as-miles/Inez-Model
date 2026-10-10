"""Controlled real Three.js captures; never uses generated reference imagery.

Run against the existing Vite viewer. --restore-preview is diagnostic only:
it reverses the documented pass-3 albedo gains without editing an asset.
"""
import argparse
import asyncio
import base64
import json
import os
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
CHAR = ROOT / 'assets/characters/inez'


async def run(args):
    out = CHAR / 'renders' / args.revision
    out.mkdir(parents=True, exist_ok=True)
    report = {'model': args.model, 'artistic_approval': False, 'views': {}, 'errors': [], 'diagnostic_no_skin_normal_map': args.no_skin_normal_map,
              'diagnostic_no_avatar_shadow_receive': args.no_shadows, 'diagnostic_shadow_normal_bias': args.shadow_normal_bias}
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=os.environ.get('INEZ_CHROMIUM', '/usr/bin/chromium'),
            args=['--no-sandbox', '--disable-dev-shm-usage', '--enable-unsafe-swiftshader', '--use-angle=swiftshader'])
        page = await browser.new_page(viewport={'width': 1000, 'height': 760}, device_scale_factor=1)
        page.on('pageerror', lambda e: report['errors'].append(str(e)))
        page.on('console', lambda e: report['errors'].append(e.text) if e.type == 'error' else None)
        await page.goto(args.url + '?model=' + args.model, timeout=120000)
        await page.wait_for_function('window.inezViewer?.state.ready || window.inezViewer?.state.error', timeout=180000)
        await page.evaluate('''() => { const v=window.inezViewer; v.captureMode(true); v.pause(true);
            v.resetPosition(); v.setAnimation('rest',{transition:0}); v.resetFace(); }''')
        await page.evaluate('preset => window.inezViewer.setLighting(preset)', args.lighting)
        if args.restore_preview:
            await page.evaluate('''() => window.inezViewer.getAvatar().traverse(m => {
                if(!m.isMesh) return;
                for(const a of [m.material].flat()) {
                    if(['Inez_Head_Skin_PBR','Inez_Skin_Freckles_Pores_Lips_PBR'].includes(a.name)) a.color.multiplyScalar(1/.42);
                    if(a.name==='Inez_Hair_FromAssetB') {a.color.r*=.042/.024;a.color.g*=.021/.0135;a.color.b*=.0088/.0068;}
                }
            })''')
        if args.no_skin_normal_map:
            # Diagnostic only: drop the two skin materials' tangent-space normal
            # maps in the browser (no asset is edited) to test whether contour
            # bands come from the normal map rather than albedo or geometry.
            await page.evaluate('''() => window.inezViewer.getAvatar().traverse(m => {
                if(!m.isMesh) return;
                for(const a of [m.material].flat())
                    if(['Inez_Head_Skin_PBR','Inez_Skin_Freckles_Pores_Lips_PBR'].includes(a.name)) {a.normalMap=null;a.needsUpdate=true;}
            })''')
        if args.no_shadows:
            # Diagnostic only: stop the avatar receiving shadow-map shadows
            # (browser only) to test for self-shadowing acne on the face.
            await page.evaluate('''() => window.inezViewer.getAvatar().traverse(m => { if(m.isMesh) { m.receiveShadow=false; for(const a of [m.material].flat()) a.needsUpdate=true; } })''')
        if args.shadow_normal_bias is not None:
            # Diagnostic only: offset the shadow lookup along the normal for every
            # shadow-casting light in the scene (no viewer source is edited).
            await page.evaluate('''b => { let s=window.inezViewer.getAvatar(); while(s.parent) s=s.parent;
                s.traverse(o => { if(o.isLight && o.castShadow) { o.shadow.normalBias=b; o.shadow.needsUpdate=true; } }); }''', args.shadow_normal_bias)
        if args.normal_preview:
            await page.evaluate('''async () => {
                const T=await import('/node_modules/three/build/three.module.js');
                window.inezViewer.getAvatar().traverse(m=>{
                    if(!m.isMesh || !m.name.includes('ContinuousHumanMesh')) return;
                    const g=m.geometry, base=g.attributes.position, p=base.clone();
                    for(let i=0;i<base.count;i++) {
                        const v=new T.Vector3().fromBufferAttribute(base,i);
                        (g.morphAttributes.position||[]).forEach((a,k)=>{
                            const d=new T.Vector3().fromBufferAttribute(a,i);
                            if(!g.morphTargetsRelative) d.sub(new T.Vector3().fromBufferAttribute(base,i));
                            v.addScaledVector(d,m.morphTargetInfluences[k]);
                        }); p.setXYZ(i,v.x,v.y,v.z);
                    }
                    const tmp=new T.BufferGeometry();tmp.setAttribute('position',p);tmp.setIndex(g.index);tmp.computeVertexNormals();
                    g.setAttribute('normal',tmp.attributes.normal.clone());
                    for(const [name,k] of Object.entries(m.morphTargetDictionary||{}))
                        if(name.startsWith('Inez_') && g.morphAttributes.normal?.[k]) g.morphAttributes.normal[k].array.fill(0);
                    g.morphAttributes.normal?.forEach(a=>a.needsUpdate=true);
                });
            }''')
        for view in args.views.split(','):
            await page.evaluate('view => window.inezViewer.setView(view)', view)
            if view == 'face_front' and args.match_reference:
                await page.evaluate('''() => {const v=window.inezViewer,c=v.camera,t=v.controls.target;
                    const d=c.position.distanceTo(t),yaw=4*Math.PI/180,pitch=-5*Math.PI/180;
                    c.position.set(t.x+Math.sin(yaw)*Math.cos(pitch)*d,t.y+Math.sin(pitch)*d,t.z+Math.cos(yaw)*Math.cos(pitch)*d);
                    v.controls.update();c.updateMatrixWorld();v.renderFrame();}''')
            data = await page.evaluate('''() => {window.inezViewer.renderFrame();return document.getElementById('render').toDataURL('image/png');}''')
            (out / (view + '.png')).write_bytes(base64.b64decode(data.split(',')[1]))
            report['views'][view] = await page.evaluate('''() => {const v=window.inezViewer,c=v.camera;
                const a=v.getAvatar();return {camera:{position:c.position.toArray(),target:v.controls.target.toArray(),
                    matrixWorld:c.matrixWorld.toArray(),projection:c.projectionMatrix.toArray(),left:c.left,right:c.right,top:c.top,bottom:c.bottom},
                    avatarOffset:a.position.toArray(),lighting:v.state.lighting,lightControls:v.state.lightControls,width:1000,height:760};}''')
        report['backend'] = await page.evaluate('window.inezViewer.state.backend')
        report['viewer_errors'] = await page.evaluate('window.inezViewer.errors')
        report['restore_preview'] = args.restore_preview
        report['normal_preview'] = args.normal_preview
        (out / 'capture.json').write_text(json.dumps(report, indent=2) + '\n')
        await browser.close()
    print(json.dumps({'output':str(out),'errors':report['errors'],'backend':report['backend']}))
    return int(bool(report['errors'] or report['viewer_errors']))


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--url',default='http://127.0.0.1:4173/')
    parser.add_argument('--model',default='inez_runtime.glb')
    parser.add_argument('--revision',required=True)
    parser.add_argument('--views',default='face_front,face_left,face_right,face_three_quarter,body_front,body_back')
    parser.add_argument('--match-reference',action='store_true')
    parser.add_argument('--no-skin-normal-map',action='store_true',help='diagnostic: render the skin without its normal maps (browser only)')
    parser.add_argument('--no-shadows',action='store_true',help='diagnostic: avatar does not receive shadow-map shadows (browser only)')
    parser.add_argument('--shadow-normal-bias',type=float,default=None,help='diagnostic: set normalBias on shadow-casting lights (browser only)')
    parser.add_argument('--lighting',default='studio',choices=['studio','neutral','apartment','daylight','flashlight'])
    parser.add_argument('--restore-preview',action='store_true')
    parser.add_argument('--normal-preview',action='store_true')
    raise SystemExit(asyncio.run(run(parser.parse_args())))
