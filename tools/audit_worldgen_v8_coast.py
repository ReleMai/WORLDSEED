#!/usr/bin/env python3
"""Audit WORLDGEN v8 Phase-5 coast morphology without changing terrain."""
from __future__ import annotations

import argparse
import json
from collections import Counter

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.world.generator import WorldGenerator


def audit_seed(seed: str, radius: int, step: int) -> dict:
    registry=ContentRegistry.load(DATA_DIR)
    gen=WorldGenerator(seed.encode('utf-8'),registry,version=8)
    kinds=Counter();materials=Counter();shelves=Counter()
    values=[]
    for y in range(-radius,radius+1,step):
        for x in range(-radius,radius+1,step):
            coast=gen.coast_at(WorldPos(x,y,0))
            if coast is None:continue
            kinds[coast.coast_kind]+=1
            shelves[coast.shelf_class]+=1
            if coast.shore_material!='none':materials[coast.shore_material]+=1
            if coast.near_coast:
                values.append(coast)
    return {
        'seed':seed,
        'samples':sum(kinds.values()),
        'near_coast_samples':len(values),
        'coast_kinds':dict(sorted(kinds.items())),
        'shore_materials':dict(sorted(materials.items())),
        'shelf_classes':dict(sorted(shelves.items())),
        'mean_wave_exposure':sum(v.wave_exposure for v in values)//max(1,len(values)),
        'mean_shelter':sum(v.shelter for v in values)//max(1,len(values)),
        'max_tidal_flat':max((v.tidal_flat_potential for v in values),default=0),
        'max_marsh':max((v.marsh_potential for v in values),default=0),
        'max_lagoon':max((v.lagoon_potential for v in values),default=0),
        'algorithm':values[0].algorithm if values else '',
    }


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--seeds',type=int,default=6)
    ap.add_argument('--radius',type=int,default=3072)
    ap.add_argument('--step',type=int,default=128)
    args=ap.parse_args()
    reports=[
        audit_seed(f'v8-phase5-coast-{i:02d}',max(512,args.radius),max(32,args.step))
        for i in range(max(1,args.seeds))
    ]
    print(json.dumps({'reports':reports},indent=2,sort_keys=True))
    # Audit fails only on structural absence; calibration remains a human/data
    # review rather than encoding one preferred coastline distribution.
    if any(r['near_coast_samples']==0 for r in reports):
        return 1
    if any(len(r['shelf_classes'])<2 for r in reports):
        return 2
    return 0


if __name__=='__main__':
    raise SystemExit(main())
