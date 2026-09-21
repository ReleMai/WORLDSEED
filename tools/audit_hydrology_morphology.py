#!/usr/bin/env python3
"""Audit Hydrology v2 local river morphology/materialization."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from worldseed.config import (
    DATA_DIR, HYDROLOGY_MORPHOLOGY_VERSION, HYDROLOGY_VERSION, WORLDGEN_VERSION,
)
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.world.generator import WorldGenerator
from worldseed.world.hydrology import HydrologyGenerator, audit_domain


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--seed",default="v8-hydrology-morphology-audit")
    ap.add_argument("--domain-x",type=int,default=0)
    ap.add_argument("--domain-y",type=int,default=0)
    ap.add_argument("--step",type=int,default=4)
    ap.add_argument("--out",type=Path,default=Path("v8_hydrology_morphology_audit.json"))
    args=ap.parse_args()

    registry=ContentRegistry.load(DATA_DIR)
    seed=args.seed.encode("utf-8")
    gen=WorldGenerator(seed,registry,version=WORLDGEN_VERSION)
    hydro=HydrologyGenerator(
        gen,version=HYDROLOGY_VERSION,
        morphology_version=HYDROLOGY_MORPHOLOGY_VERSION,
    )
    domain=hydro.generate(args.domain_x,args.domain_y)
    hydro._remember(domain)
    gen.attach_hydrology(hydro)

    span=domain.core_nodes*domain.lattice_spacing
    x0=args.domain_x*span
    y0=args.domain_y*span
    step=max(1,int(args.step))
    styles=Counter()
    terrain=Counter()
    flags=Counter()
    river_cells=0
    water_cells=0
    crossings=[]
    for y in range(y0,y0+span,step):
        for x in range(x0,x0+span,step):
            surface=hydro.surface_at(WorldPos(x,y,0),prepared_only=True)
            if surface is None:
                continue
            terrain[str(surface.terrain_override or "base")]+=1
            styles[str(surface.channel_style)]+=1
            if surface.river_class>0:
                river_cells+=1
            if surface.river_class>0 or surface.lake:
                water_cells+=1
            for name in ("ford","rapid","gorge","braided","delta","oxbow_lake"):
                if bool(getattr(surface,name,False)):
                    flags[name]+=1
            if surface.crossing_cost>0 and surface.river_class>0:
                crossings.append(int(surface.crossing_cost))

    report={
        "seed":args.seed,
        "worldgen_version":WORLDGEN_VERSION,
        "hydrology_version":HYDROLOGY_VERSION,
        "morphology_version":HYDROLOGY_MORPHOLOGY_VERSION,
        "domain":[args.domain_x,args.domain_y],
        "domain_fingerprint":domain.fingerprint,
        "domain_issues":audit_domain(domain),
        "sample_step":step,
        "river_samples":river_cells,
        "water_samples":water_cells,
        "channel_styles":dict(sorted(styles.items())),
        "terrain_overrides":dict(sorted(terrain.items())),
        "morphology_flags":dict(sorted(flags.items())),
        "crossing_cost":{
            "count":len(crossings),
            "min":min(crossings,default=0),
            "max":max(crossings,default=0),
            "mean":sum(crossings)//max(1,len(crossings)),
        },
    }
    args.out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2,sort_keys=True))
    return 1 if report["domain_issues"] else 0


if __name__=="__main__":
    raise SystemExit(main())
