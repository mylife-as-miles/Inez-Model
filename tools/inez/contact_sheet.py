"""Assemble approved individual reference guides without regenerating panels."""
from pathlib import Path
import json
import math
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[2]/'assets/characters/inez'
VIEWS = [
    '01_face_front_neutral', '02_face_left_profile', '03_face_right_profile', '04_face_three_quarter',
    '05_body_front', '06_body_side', '07_body_back', '08_eyes_closeup',
    '09_lips_closeup', '10_skin_freckles_closeup', '11_necklace_closeup',
    '12_sweater_material_closeup', '13_boots_closeup',
]


def main():
    ledger = json.loads((ROOT/'qa/generation_ledger.json').read_text())
    approved = {}
    for view in VIEWS:
        matches = [row for row in ledger['calls'] if row['view']==view and row['status'] in
                   ('approved_for_reference','approved_geometry_only')]
        if not matches or not (ROOT/'references/approved'/(view+'.png')).is_file():
            raise SystemExit('No reviewed individual guide for '+view+'; refusing fabricated master.')
        approved[view] = matches[-1]
    cell_width, cell_height = 550, 760
    canvas = Image.new('RGB', (4*cell_width, 150+math.ceil(len(VIEWS)/4)*cell_height), '#e8e8e8')
    draw = ImageDraw.Draw(canvas)
    font_path='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    title=ImageFont.truetype(font_path,30); label=ImageFont.truetype(font_path,18)
    small=ImageFont.truetype(font_path,15)
    draw.text((20,18),'INEZ — reviewed individual reference guides',fill='#202020',font=title)
    draw.text((20,64),'Original A/B retain final authority. Profiles infer unseen depth. Scope labels are mandatory.',fill='#303030',font=label)
    draw.text((20,96),'Body materials, generated pendant motif and exact freckle maps are not approved. This is not a real 3D render.',fill='#303030',font=label)
    manifest={}
    for index,view in enumerate(VIEWS):
        x=(index%4)*cell_width; y=150+(index//4)*cell_height
        image=Image.open(ROOT/'references/approved'/(view+'.png')).convert('RGB')
        fitted=ImageOps.contain(image,(cell_width-24,cell_height-88),Image.Resampling.LANCZOS)
        canvas.paste(fitted,(x+(cell_width-fitted.width)//2,y+(cell_height-88-fitted.height)//2))
        row=approved[view]
        scope='Geometry only; material exclusions apply' if row['status']=='approved_geometry_only' else 'Provisional guide; original evidence overrides'
        if view in ('08_eyes_closeup','09_lips_closeup','10_skin_freckles_closeup','11_necklace_closeup','12_sweater_material_closeup','13_boots_closeup'):
            scope='Qualitative detail guide; check scope JSON'
        draw.text((x+12,y+cell_height-68),view.replace('_',' '),fill='#202020',font=label)
        draw.text((x+12,y+cell_height-40),scope,fill='#555555',font=small)
        scope_file=ROOT/'references/approved'/(view+'.scope.json')
        manifest[view]={'source':row['approved_output'],'status':row['status'],'sha256':row['sha256'],
                        'decision':row.get('decision'),'scope_file':str(scope_file.relative_to(ROOT)) if scope_file.exists() else None}
    target=ROOT/'references/approved/INEZ_MASTER_TURNAROUND.png'
    canvas.save(target)
    (ROOT/'qa/master_turnaround_manifest.json').write_text(json.dumps({'assembled_from_existing_approved_guides':True,
        'production_approved':False,'views':manifest},indent=2)+'\n')
    print(target)


if __name__=='__main__':
    main()
