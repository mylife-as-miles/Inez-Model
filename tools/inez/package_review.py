"""Package actual review work; exclude caches, dependencies and duplicate dist assets."""
from pathlib import Path
import hashlib,json,zipfile

root=Path('/workspace')
dest=root/'artifacts/inez-initial-reference-review.zip'
dest.parent.mkdir(exist_ok=True)
folders=['docs','reports','assets/characters/inez','tools/inez','viewer','references']
paths=[]
for folder in folders:
 for path in (root/folder).rglob('*'):
  if not path.is_file():continue
  rel=path.relative_to(root)
  if any(p in {'node_modules','dist','__pycache__','.vite'} for p in rel.parts):continue
  paths.append(path)
paths.sort()
inventory=[dict(path=str(p.relative_to(root)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())for p in paths]
with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=6)as z:
 for path in paths:z.write(path,str(path.relative_to(root)))
 z.writestr('REVIEW_PACKAGE_MANIFEST.json',json.dumps(dict(status='Paused at canonical body costume gate; no reconstructed 3D model',files=inventory),indent=2)+'\n')
print(json.dumps(dict(package=str(dest),bytes=dest.stat().st_size,files=len(paths)),indent=2))
