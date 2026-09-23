"""Audit coast-v2 river mouths against real prepared multi-domain drainage."""
import argparse,json,sys,time
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from worldseed.core.coords import WorldPos
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.world.generator import WorldGenerator
from worldseed.world.hydrology import HydrologyGenerator
from worldseed.world.landforms import SEA_LEVEL_REFERENCE as SEA


def audit(seed):
    gen=WorldGenerator(seed.encode(),ContentRegistry.load(DATA_DIR),version=8)
    hydro=HydrologyGenerator(gen,version=2,morphology_version=2);gen.attach_hydrology(hydro)
    coast=None
    for y in range(-3072,3073,128):
        for x in range(-3072,3073,128):
            a=gen.landforms_v8.sample(x,y).elevation
            b=gen.landforms_v8.sample(x+128,y).elevation
            if (a<SEA)!=(b<SEA):coast=(x,y);break
        if coast:break
    if coast is None:return {'seed':seed,'mouths':0,'delta_mouths':0,'seam_comparisons':0}
    x,y=coast;dx,dy=hydro.domain_for_world(x,y)
    domains=hydro.prepare_world_bounds(dx*1024,dy*1024,(dx+2)*1024-1,(dy+1)*1024-1,persist=False)
    plans={};copies={};comparisons=0
    for domain in domains:
        for plan in gen.coastal_mouths.plans(domain)[0]:
            if plan.source in copies:
                assert plan==copies[plan.source],('mouth seam mismatch',plan.source)
                comparisons+=1
            copies[plan.source]=plan
            # Count only source nodes belonging to a prepared core.
            if hydro.domain_for_world(*plan.source)==(domain.domain_x,domain.domain_y):plans[plan.source]=plan
    for plan in plans.values():
        assert sum(plan.branch_discharge)==plan.discharge
        for path in plan.branches:
            assert path[0] in plan.primary
            assert gen.landforms_v8.sample(*path[-1]).elevation<SEA
    seam_cells=0
    by_key={(d.domain_x,d.domain_y):d for d in domains}
    for domain in domains:
        neighbor=by_key.get((domain.domain_x+1,domain.domain_y))
        if neighbor is None:continue
        edge=(domain.domain_x+1)*1024
        for y in range(domain.domain_y*1024,(domain.domain_y+1)*1024,4):
            for x in range(edge-2,edge+3):
                p=WorldPos(x,y,0)
                assert gen.coastal_mouths.at(p,domain)==gen.coastal_mouths.at(p,neighbor),('projection seam',x,y)
                seam_cells+=1
    rebuilt={}
    gen.coastal_mouths._indexes.clear()
    for domain in reversed(domains):
        for plan in gen.coastal_mouths.plans(domain)[0]:rebuilt[plan.source]=plan
    assert all(rebuilt[k]==v for k,v in copies.items())
    return {'seed':seed,'mouths':len(plans),'delta_mouths':sum(bool(p.branches) for p in plans.values()),
            'barriers':sum(bool(p.barrier) for p in plans.values()),'seam_cells':seam_cells,'seam_comparisons':comparisons,'max_mixing_width':max((p.mixing_width for p in plans.values()),default=0),
            'example':asdict(next((p for p in plans.values() if p.branches),next(iter(plans.values()),None))) if plans else None}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--seeds',type=int,default=3);args=parser.parse_args()
    start=time.perf_counter();rows=[audit('v8-phase5-mouth-'+str(i)) for i in range(args.seeds)]
    print(json.dumps({'reports':rows,'seconds':round(time.perf_counter()-start,3)},indent=2))
    return 0 if sum(r['mouths'] for r in rows)>0 and sum(r['delta_mouths'] for r in rows)>0 else 1

if __name__=='__main__':raise SystemExit(main())
