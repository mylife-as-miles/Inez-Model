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
    glb=CHARACTER/'model/inez.glb'
    if not glb.is_file():
        raise SystemExit('Actual inez.glb missing; no substitute character will be packaged.')
    raw=glb.read_bytes()
    if struct.unpack_from('<4sI',raw)!=(b'glTF',2):
        raise SystemExit('Not a glTF2 binary asset.')
    dist=WORKSPACE/'viewer/dist'
    if not (dist/'index.html').exists():
        raise SystemExit('Run the viewer production build after final assets/status updates.')
    status=json.loads((CHARACTER/'qa/production_status.json').read_text())
    if not status.get('model_available'):
        raise SystemExit('Runtime availability must truthfully record the actual GLB.')
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    files={}
    for root in [dist/'assets']:
        for path in root.rglob('*'):
            if path.is_file():files[path.relative_to(dist).as_posix()]=path
    files['index.html']=dist/'index.html'
    if (dist/'favicon.svg').exists():files['favicon.svg']=dist/'favicon.svg'
    files['characters/inez/model/inez.glb']=glb
    files['characters/inez/qa/production_status.json']=CHARACTER/'qa/production_status.json'
    files['characters/inez/qa/browser_validation.json']=report_path
    for root in [CHARACTER/'references/original',CHARACTER/'references/approved']:
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
Generated reference guides have explicit restricted scopes; original portraits/costume retain authority.
Base graphical mesh/rig assets: MakeHuman CC0 (credits/). No MakeHuman AGPL program code copied.
The fitted geometry, authored clothing/hair/maps, animations and viewer source are in the full review package.
'''
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for name,path in files.items():archive.write(path,name)
        archive.writestr('serve.py',server)
        archive.writestr('README.txt',readme)
        archive.writestr('manifest.json',json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'output':str(output),'size_bytes':output.stat().st_size,'runtime_files':len(files),
                      'production_approved':status.get('production_approved',False)},indent=2))


if __name__=='__main__':main()
