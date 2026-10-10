"""Export an existing V06 source without resaving or modifying it on disk."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parent))
from v06_prepare import export_runtime
from animation_build import reset_pose
from animation_validate_glb import Scene
from glb_expression_clips import read_glb, write_glb, add_accessor


def normalize_clip_starts(output,durations):
    # The exporter writes frame 1 at t=1/fps. Three's AnimationClip uses the
    # last time as duration, so this padding would alter matching gait speed.
    # Remove the common start offset while preserving every sampled pose.
    scene=Scene(output);data,binary=read_glb(output);inputs={};emitted={};offsets={}
    for animation in data['animations']:
        start=min(float(scene.accessor(s['input']).min()) for s in animation['samplers'])
        for sampler in animation['samplers']:
            key=(sampler['input'],start)
            if key not in inputs:
                times=scene.accessor(sampler['input']).ravel().astype(np.float64)-start
                times=np.maximum(times,0).astype(np.float32)
                inputs[key]=add_accessor(data,binary,times,'SCALAR')
            sampler['input']=inputs[key]
        duration=max(data['accessors'][s['input']]['max'][0] for s in animation['samplers'])
        emitted[animation['name']]=duration;offsets[animation['name']]=start
        assert abs(duration-durations[animation['name']])<2e-6,(animation['name'],'endpoint lost')
    data['buffers'][0]['byteLength']=len(binary)+(-len(binary)%4)
    write_glb(output,data,binary)
    return emitted,offsets


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--report',required=True)
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    source=Path(bpy.data.filepath);output=Path(args.output).resolve()
    if output==source.resolve():raise RuntimeError('Export must use a different file')
    original_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    arm=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
    arm.animation_data.action=None;reset_pose(arm)
    meshes=[o for o in bpy.context.scene.objects if o.type=='MESH' and not o.hide_render]
    fps=bpy.context.scene.render.fps/bpy.context.scene.render.fps_base
    durations={a.name:(a.frame_range[1]-a.frame_range[0])/fps for a in bpy.data.actions if a.get('inez_generated_animation')}
    export_runtime(arm,meshes,output,output.parent/(output.stem+'_work'))
    emitted,offsets=normalize_clip_starts(output,durations)
    assert hashlib.sha256(source.read_bytes()).hexdigest()==original_hash
    Path(args.report).write_text(json.dumps({'source':str(source),'output':str(output),'source_sha256':original_hash,
        'source_unchanged':True,'source_fps':fps,'authored_duration_s':durations,
        'emitted_duration_s':emitted,'start_padding_removed_s':offsets,
        'export_timing':'integer common lattice of 24 Hz authored endpoints and 60 Hz contact samples (120 Hz)'},indent=2)+'\n')


if __name__=='__main__':main()
