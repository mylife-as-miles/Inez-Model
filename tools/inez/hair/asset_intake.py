"""Read-only inventory of a locally supplied licensed hair package.

No download, authentication workaround, texture synthesis or auto fitting.
An archive inventory is not equivalent to an inspected/extracted FBX package.
"""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path

from PIL import Image

EXTENSIONS={'.fbx','.abc','.mhpkg','.png','.tga','.jpg','.jpeg','.txt','.pdf','.md','.zip'}


def inventory(source):
    files=[source] if source.is_file() else sorted(p for p in source.rglob('*') if p.is_file())
    records=[]
    for p in files:
        if p.suffix.lower() not in EXTENSIONS:continue
        row={'file':p.name if source.is_file() else str(p.relative_to(source)),
             'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'extension':p.suffix.lower()}
        if p.suffix.lower() in {'.png','.tga','.jpg','.jpeg'}:
            with Image.open(p) as im:row['image']={'size':list(im.size),'mode':im.mode}
        if p.suffix.lower()=='.zip':
            with zipfile.ZipFile(p) as z:
                row['archive_members']=[{'name':a.filename,'bytes':a.file_size} for a in z.infolist() if not a.is_dir()]
                row['extracted']=False
        records.append(row)
    return records


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--report',required=True)
    p.add_argument('--license-note',help='Local receipt/license note to record, not assume or accept')
    args=p.parse_args();source=Path(args.source).resolve();output=Path(args.report).resolve()
    if not source.exists():raise SystemExit('Licensed source package is missing: '+str(source))
    if output.exists():raise SystemExit('Choose a new versioned inventory report')
    records=inventory(source)
    report={'source':str(source),'listing':'https://www.fab.com/listings/a3425afb-5801-455e-a6a1-e27632d493db',
        'files':records,'license_note':args.license_note,'entitlement_verified':False,
        'source_unchanged':True,'fitting_performed':False,'hair_accepted':False,
        'ready_for_local_inspection':any(r['extension']=='.fbx' for r in records) and any(r['extension'] in {'.png','.tga'} for r in records)}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'report':str(output),'files':len(records),'ready_for_local_inspection':report['ready_for_local_inspection']}))
    return 0 if report['ready_for_local_inspection'] else 2


if __name__=='__main__':raise SystemExit(main())
