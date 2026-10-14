"""Compare legacy and checkpoint snapshot captures without opening player saves.

Run: python -m tools.save_capture_probe --npc-count 1000 --npc-count 10000
Synthetic, deterministic populated state. Numbers are hardware-specific and
do not imply a release performance threshold or database transaction timing.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import platform
from statistics import median
import time

from worldseed.systems.state import LivingWorldState, NPCState


def prepared_state(npc_count: int) -> LivingWorldState:
    if not 0 <= npc_count <= 20000:
        raise ValueError("npc_count must be between 0 and 20000")
    state=LivingWorldState(player_name='Save capture benchmark')
    for number in range(npc_count):
        uid=f'probe:npc:{number:05d}'
        actor=NPCState(uid,uid,30,'farmer',['patient'],10000+number,10000,0,'distant','none')
        actor.inventory={'core:stone':number%7}
        actor.memories=[{'kind':'worked','minute':number,'note':'distant actor'}]
        state.npcs[uid]=actor
    return state


def measure(npc_count: int, repeats: int=3) -> dict:
    if not 1 <= repeats <= 8:
        raise ValueError("repeats must be between 1 and 8")
    state=prepared_state(npc_count)
    legacy_times=[]
    revised_times=[]
    for repetition in range(repeats):
        # Alternate order to reduce systematic warm-cache/order bias.
        if repetition % 2 == 0:
            methods=('legacy','revised')
        else:
            methods=('revised','legacy')
        snapshots={}
        for method in methods:
            before=time.perf_counter_ns()
            snapshot=(deepcopy(state.to_dict()) if method=='legacy'
                      else state.checkpoint_snapshot())
            elapsed=(time.perf_counter_ns()-before)/1_000_000
            (legacy_times if method=='legacy' else revised_times).append(elapsed)
            snapshots[method]=snapshot
        if snapshots['legacy'] != snapshots['revised']:
            raise AssertionError('checkpoint snapshot payload changed')
        if len(snapshots['revised']['npcs']) != npc_count:
            raise AssertionError('actor count changed in capture')
    payload=json.dumps(snapshots['revised'],separators=(',',':'),sort_keys=True)
    return {
        'npc_count':npc_count,'repeats':repeats,
        'legacy_median_capture_ms':round(median(legacy_times),3),
        'revised_median_capture_ms':round(median(revised_times),3),
        'json_payload_bytes':len(payload.encode('utf-8')),
        'identity_verified':True,
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--npc-count',action='append',type=int,default=None,
                        help='Repeatable distant NPC population, 0..20000')
    parser.add_argument('--repeats',type=int,default=3)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args(argv)
    populations=args.npc_count or [1000,10000]
    if not 1 <= len(populations) <= 4:
        parser.error('provide one to four --npc-count arguments')
    if not 1 <= args.repeats <= 8 or any(not 0<=n<=20000 for n in populations):
        parser.error('invalid benchmark bounds')
    report={
        'python':platform.python_version(),
        'platform':platform.platform(),
        'scenario':'synthetic-detached-state-only-no-database',
        'results':[measure(n,args.repeats) for n in populations],
    }
    text=json.dumps(report,indent=2)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(text,encoding='utf-8')
    print(text,end='')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
