#!/usr/bin/env python3
"""Find deterministic Dev31 playtest locations for hard-to-find geography."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from worldseed.config import DATA_DIR, WORLDGEN_VERSION
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.world.generator import WorldGenerator


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--seed",default="dev31-mountain-test")
    ap.add_argument("--radius",type=int,default=8192)
    ap.add_argument("--spacing",type=int,default=128)
    ap.add_argument("--out",type=Path,default=Path("DEV31_TEST_LOCATIONS.json"))
    args=ap.parse_args()

    reg=ContentRegistry.load(DATA_DIR)
    gen=WorldGenerator(args.seed.encode("utf-8"),reg,version=WORLDGEN_VERSION)
    candidates=[]
    radius=max(2048,int(args.radius));spacing=max(32,int(args.spacing))
    for y in range(-radius,radius+1,spacing):
        for x in range(-radius,radius+1,spacing):
            pos=WorldPos(x,y,0)
            fields=gen.sample_fields(pos)
            topo=gen.topography_at(pos)
            land=gen.landform_at(pos)
            if topo is None or land is None:continue
            score=0
            if fields.elevation>=43000:score+=(fields.elevation-43000)*4
            score+=int(topo.relief)*2+int(topo.ruggedness)*2
            score+=int(land.mountain_chain)*2
            if fields.elevation<30000:score-=80000
            candidates.append((
                score,x,y,int(fields.elevation),int(topo.relief),int(topo.ruggedness),
                int(land.mountain_chain),str(land.province),
            ))
    candidates.sort(reverse=True)
    chosen=[]
    for row in candidates:
        _,x,y,*_=row
        if any((x-c["x"])**2+(y-c["y"])**2 < 900**2 for c in chosen):continue
        chosen.append({
            "x":x,"y":y,"elevation":row[3],"relief":row[4],
            "ruggedness":row[5],"mountain_chain":row[6],"province":row[7],
        })
        if len(chosen)>=8:break
    payload={
        "seed":args.seed,
        "worldgen_version":WORLDGEN_VERSION,
        "purpose":"Mountain/ridge locations for Dev31 manual geography and visibility testing.",
        "mountain_candidates":chosen,
    }
    args.out.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(payload,indent=2,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
