"""Measure actual exported, skinned boot contact over animation frames.

Uses the same accumulated same-material-point stance displacement definition
as boot_contact_audit.py, in +Y-up glTF metres; includes matching +Z travel.
Loop seam and within-stance sliding are separate reported measurements.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from animation_validate_glb import Scene


def run(path,hz,actions):
    scene=Scene(path);rest,changes=scene.globals()
    boots=[i for i,n in enumerate(scene.nodes) if 'mesh' in n and 'boot' in n.get('name','').lower()]
    masks={s:{} for s in 'LR'}
    for i in boots:
        points=scene.vertices(i,rest,changes)
        for side in 'LR':
            selected=np.flatnonzero(scene.region_mask(i,('foot','toe','lowerleg','upperleg'),side))
            if len(selected):masks[side][i]=selected[points[selected,1]<points[selected,1].min()+.03]
    if any(not m for m in masks.values()):raise ValueError('Both actual boot sides required')
    manifest=json.loads((Path(__file__).resolve().parents[2]/'assets/characters/inez/rig/animation_manifest.json').read_text())
    animations={a['name']:a for a in scene.data['animations']};report={'file':str(path),'sampling_hz':hz,'contact_band_m':.002,'clips':{}}
    for name in actions:
        animation=animations[name];start=min(float(scene.accessor(s['input']).min()) for s in animation['samplers'])
        end=max(float(scene.accessor(s['input']).max()) for s in animation['samplers']);duration=end-start
        speed=manifest['clip_info'][name].get('matching_viewer_speed_m_s',0)
        previous=None;active={s:None for s in 'LR'};phases={s:[] for s in 'LR'};lows={s:[] for s in 'LR'}
        first=None;last=None
        for frame,t in enumerate(np.linspace(start,end,round(duration*hz)+1)):
            matrices,change=scene.globals(animation,float(t));cache={i:scene.vertices(i,matrices,change) for i in boots}
            P={s:np.concatenate([cache[i][indices] for i,indices in masks[s].items()]) for s in 'LR'}
            if first is None:first={s:p.copy() for s,p in P.items()}
            last={s:p.copy() for s,p in P.items()}
            for side,p in P.items():
                p[:,2]+=speed*(t-start);k=int(p[:,1].argmin());low=float(p[k,1]);lows[side].append(low)
                planted=low<.002
                step=float(np.linalg.norm(p[k,[0,2]]-previous[side][k,[0,2]])) if previous is not None else 0
                if planted and active[side] is None:active[side]={'start_s':float(t),'end_s':float(t),'slip_mm':0.}
                elif planted:active[side]['end_s']=float(t);active[side]['slip_mm']+=step*1000
                if not planted and active[side] is not None:phases[side].append(active[side]);active[side]=None
            previous=P
        for side in 'LR':
            if active[side] is not None:phases[side].append(active[side])
        result={'duration_s':duration,'matching_speed_m_s':speed,'samples':round(duration*hz)+1}
        for side in 'LR':
            kept=[p for p in phases[side] if p['end_s']-p['start_s']>=3/hz-1e-6]
            result[side]={'max_stance_slip_mm':max((p['slip_mm'] for p in kept),default=0),
                'lowest_sole_mm':min(lows[side])*1000,'highest_sole_mm':max(lows[side])*1000,
                'local_loop_seam_mm':float(np.linalg.norm(last[side]-first[side],axis=1).max()*1000),
                'planted_phases':kept}
        report['clips'][name]=result
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--report',required=True)
    p.add_argument('--hz',type=int,default=120);p.add_argument('--actions',nargs='+',default=['Walk','Run','CrouchDown','CrouchUp'])
    args=p.parse_args();report=run(args.input,args.hz,args.actions)
    Path(args.report).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({n:{s:round(c[s]['max_stance_slip_mm'],3) for s in 'LR'} for n,c in report['clips'].items()}))
