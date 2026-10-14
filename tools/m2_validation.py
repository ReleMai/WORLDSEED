"""Measured M2 engine-performance report; synthetic references, never player saves.

Runs six prepared reference scenes at equal settings, 1k/10k distant actor
movement probes, and legacy/revised detached save-capture comparisons. Record
all outcomes including misses; synthetic 720p throughput isn't a 1080p target.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time


def _run(args: list[str], timeout: int) -> None:
    print('M2_RUN ' + ' '.join(args), flush=True)
    subprocess.run([sys.executable, '-u', *args], check=True,
                   timeout=timeout, env=os.environ.copy())


def _stage(scene: dict, name: str) -> dict:
    row=scene.get('timings',{}).get('stages',{}).get(name,{})
    return {key: row.get(key) for key in
            ('count','p50_ms','p95_ms','p99_ms','worst_ms','over_100ms_count')}


def summarize(scenes: dict, scaling: list[dict], capture: dict) -> dict:
    records=[]
    for row in scenes['scenes']:
        records.append({
            'scene':row['scene'],
            'frame':_stage(row,'render.frame'),
            'frame_count':row['frames_measured'],
            'size':row['size'],
            'save_bytes':row['save_bytes'],
            'state_json_bytes':row['state_json_bytes'],
            'authority_unchanged':row['authority_unchanged'],
            'interrupted':row['interrupted'],
            'hardware':row['hardware'],
            'build_identity':row['build_identity'],
        })
    movement=[]
    for row in scaling:
        movement.append({
            'population':row['state_counts']['npcs'],
            'movement':_stage(row,'simulation.free_movement'),
            'frame':_stage(row,'render.frame'),
            'save_bytes':row['save_bytes'],
            'authority_unchanged':row['authority_unchanged'],
            'hardware':row['hardware'],
        })
    ratio=None
    if len(movement)==2:
        slow=movement[1]['movement'].get('p50_ms')
        fast=movement[0]['movement'].get('p50_ms')
        if fast and slow is not None:
            ratio=slow/fast
    # Targets have different validation semantics. No assertion on synthetic
    # 720p runner measurements for interactive 1080p or long-session latency.
    return {
        'kind':'m2-synthetic-runner-measurement',
        'not_live_1080p_certification':True,
        'reference_scenes':records,
        'movement_probes':movement,
        'movement_p50_ratio_10000_over_1000':ratio,
        'movement_within_proposed_20_percent':ratio is not None and ratio<=1.20,
        'save_capture':capture,
    }


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,default=Path('dist/m2-validation'))
    ap.add_argument('--frames',type=int,default=40)
    ap.add_argument('--warmup',type=int,default=5)
    ap.add_argument('--capture-repeats',type=int,default=3)
    args=ap.parse_args(argv)
    if not 10<=args.frames<=120 or not 0<=args.warmup<=15 or not 1<=args.capture_repeats<=6:
        ap.error('invalid bounded benchmark settings')
    out=args.output
    out.mkdir(parents=True,exist_ok=True)
    started=time.time()
    cmd=['-m','tools.reference_scenes','--headless','--frames',str(args.frames),
         '--warmup',str(args.warmup),'--width','1280','--height','720','--zoom','28']
    all_dir=out/'scenes'
    _run([*cmd,'--scene','all','--output-dir',str(all_dir)],timeout=500)
    scenes=json.loads((all_dir/'summary.json').read_text(encoding='utf-8'))
    scaling=[]
    for npc_count in (1000,10000):
        directory=out/('movement-'+str(npc_count))
        _run([*cmd,'--scene','large_save','--distant-npcs',str(npc_count),
              '--idle-movement-probe','--output-dir',str(directory)],timeout=400)
        probe=json.loads((directory/'summary.json').read_text(encoding='utf-8'))
        scaling.extend(probe['scenes'])
    captured=out/'save-capture.json'
    _run(['-m','tools.save_capture_probe','--npc-count','1000','--npc-count','10000',
          '--repeats',str(args.capture_repeats),'--output',str(captured)],timeout=400)
    capture=json.loads(captured.read_text(encoding='utf-8'))
    report=summarize(scenes,scaling,capture)
    report['measured_seconds']=round(time.time()-started,2)
    report['runner']={'python':sys.version.split()[0],'platform':platform.platform(),
                      'logical_cpus':os.cpu_count()}
    report['save_serializer']='npc-atomic-fastpath-with-generic-asdict-fallback'
    target=out/'m2-summary.json'
    target.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print('M2_SUMMARY_JSON '+json.dumps(report,sort_keys=True),flush=True)
    print('M2_REPORT_PATH '+str(target),flush=True)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
