"""Package the actual browser-tested GLB and compiled standalone viewer."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zipfile

WORKSPACE=Path(__file__).resolve().parents[2]
CHARACTER=WORKSPACE/'assets/characters/inez'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--browser-report',required=True)
    parser.add_argument('--output',default=str(Path(__file__).resolve().parents[2]/'artifacts/inez-playable-viewer.zip'))
    args=parser.parse_args()
    report_path=Path(args.browser_report)
    report=json.loads(report_path.read_text())
    if not report.get('technical_passed'):
        raise SystemExit('Refusing playable package: actual browser integration check has not passed.')
    status=json.loads((CHARACTER/'qa/production_status.json').read_text())
    tested=report.get('model_path') or 'model/'+status.get('default_model','inez_runtime.glb')
    glb=CHARACTER/tested
    if not glb.is_file() or glb.parent!=CHARACTER/'model':
        raise SystemExit(f'Browser-tested model {tested} missing; no substitute character will be packaged.')
    raw=glb.read_bytes()
    if struct.unpack_from('<4sI',raw)!=(b'glTF',2):
        raise SystemExit('Not a glTF2 binary asset.')
    dist=WORKSPACE/'viewer/dist'
    if not (dist/'index.html').exists():
        raise SystemExit('Run the viewer production build after final assets/status updates.')
    if not status.get('model_available'):
        raise SystemExit('Runtime availability must truthfully record the actual GLB.')
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    files={}
    for root in [dist/'assets',dist/'basis']:
        for path in root.rglob('*'):
            if path.is_file():files[path.relative_to(dist).as_posix()]=path
    files['index.html']=dist/'index.html'
    if (dist/'favicon.svg').exists():files['favicon.svg']=dist/'favicon.svg'
    if not any(name.startswith('basis/') for name in files):
        raise SystemExit('The build lacks the Basis transcoder (basis/); KTX2 textures would not load.')
    # The viewer requests the default model named in the status file.
    status=dict(status,default_model=glb.name)
    files['characters/inez/'+glb.relative_to(CHARACTER).as_posix()]=glb
    files['characters/inez/rig/animation_manifest.json']=CHARACTER/'rig/animation_manifest.json'
    files['characters/inez/qa/browser_validation.json']=report_path
    for root in [CHARACTER/'references/original']:
        for path in root.rglob('*'):
            if path.is_file():files['characters/inez/'+path.relative_to(CHARACTER).as_posix()]=path
    for name in ['LICENSE.ASSETS.md','provenance.json']:
        files['credits/'+name]=CHARACTER/'model/base-source'/name
    manifest={name:{'size_bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
              for name,path in files.items()}
    server='''from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from functools import partial
import argparse
if __name__ == "__main__":
    p=argparse.ArgumentParser();p.add_argument("--port",type=int,default=8012);a=p.parse_args()
    root=Path(__file__).resolve().parent
    server=ThreadingHTTPServer(("127.0.0.1",a.port),partial(SimpleHTTPRequestHandler,directory=str(root)))
    print(f"Open http://127.0.0.1:{a.port}/ — Ctrl+C to stop",flush=True)
    server.serve_forever()
'''
    readme='''INEZ Three.js character viewer

Extract this archive and run: python3 serve.py
Open http://127.0.0.1:8012/ in a current browser. Do not open index.html through file://.

Orbit: drag. Zoom: wheel. Move: WASD/arrows. Run: Shift.
Use the panel for camera/lighting/material/reference, facial controls, Idle/Walk/Run and blending.
The GLB contains actual skinned geometry, materials, morph targets and animation clips.

Production likeness approval: '''+str(status.get('production_approved',False))+'''
''' +str(status.get('blocker',''))+'''
Browser technical evidence is included. Technical motion success does not imply exact identity.
The two original images (characters/inez/references/original/) are the likeness authority.
Base mesh/rig: MakeHuman CC0 (credits/). No MakeHuman AGPL program code copied.
Geometry and colour of hair, clothing and face come from the owner's two Inez GLBs.
Editable master, textures, tools and reports are in the repository, not in this archive.
'''
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for name,path in files.items():archive.write(path,name)
        archive.writestr('characters/inez/qa/production_status.json',json.dumps(status,indent=2)+'\n')
        archive.writestr('serve.py',server)
        archive.writestr('README.txt',readme)
        archive.writestr('manifest.json',json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'output':str(output),'size_bytes':output.stat().st_size,'runtime_files':len(files),
                      'production_approved':status.get('production_approved',False)},indent=2))


if __name__=='__main__':main()
