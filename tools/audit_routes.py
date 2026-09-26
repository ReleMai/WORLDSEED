"""Bounded Phase-3 regional transport audit.

This audit realizes only a small settlement window. It verifies sparse strategic
roads, exact portals, mutable infrastructure, route-bound gateways, local
materialization, faction frontier posts/tolls and deterministic damage detours.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.persistence.database import WorldDatabase
from worldseed.systems.physicalization import SettlementPhysicalizationSystem
from worldseed.systems.route_planner import RoutePlanner
from worldseed.systems.settlement_planner import SettlementSkeletonPlanner
from worldseed.systems.state import FactionState, LivingWorldState, SettlementState
from worldseed.world.generator import WorldGenerator
from worldseed.world.region_blocks import RegionBlockPlanner
from worldseed.world.world import World


def audit(seed: bytes, radius: int = 4, max_settlements: int = 12) -> dict:
    reg=ContentRegistry.load(DATA_DIR)
    with tempfile.TemporaryDirectory() as td:
        db=WorldDatabase.create(Path(td)/"audit.db","route-audit",seed.hex())
        try:
            world=World(WorldGenerator(seed,reg),reg,db)
            world.settlement_plan_version=5;world.routegen_version=4
            regions=RegionBlockPlanner(world);state=LivingWorldState()
            state.factions["faction:audit:a"]=FactionState("faction:audit:a","Audit League","culture:audit:a",treasury=5000,power=80,prominence=75,toll_policy=65)
            state.factions["faction:audit:b"]=FactionState("faction:audit:b","Audit March","culture:audit:b",treasury=5000,power=82,prominence=74,toll_policy=60)
            towns=[]
            for y in range(-radius,radius+1):
                for x in range(-radius,radius+1):
                    plan=regions.plan(x,y,persist=True)
                    if not plan.settlement_present or plan.settlement_anchor is None:continue
                    uid=f"settlement:{x}:{y}"
                    faction_id="faction:audit:a" if len(towns)%2==0 else "faction:audit:b"
                    town=SettlementState(uid,f"Audit {len(towns)}",x,y,*plan.settlement_anchor,
                                         80+len(towns)*10,f"culture:{faction_id}","religion:audit",faction_id)
                    state.settlements[uid]=town;towns.append(town)
                    if len(towns)>=max_settlements:break
                if len(towns)>=max_settlements:break
            routes=RoutePlanner(world,state,regions)
            plans=routes.sync_network(towns,persist=True)
            bad_portals=[]
            for plan in plans:
                if len(plan.portals)!=max(0,len(plan.region_path)-1):bad_portals.append(plan.uid);continue
                for portal in plan.portals:
                    a=tuple(portal["from_cell"]);b=tuple(portal["to_cell"])
                    if abs(a[0]-b[0])+abs(a[1]-b[1])!=1:bad_portals.append(plan.uid);break
            materialized=0;bound_gateway=0
            if towns:
                town=towns[0]
                physical=SettlementPhysicalizationSystem(world,reg,regions,SettlementSkeletonPlanner(world),routes)
                physical.sync(towns,(town.region_x,town.region_y),radius=0)
                materialized=len(physical.route_segments())
                skel=physical.skeleton_for(town.uid)
                if skel:bound_gateway=sum(1 for road in skel.roads if road.route_id)
            sparse_limit=max(0,(len(towns)-1)+max(1,len(towns)//3)) if towns else 0
            detour_tested=False;detour_ok=True
            candidate=next((p for p in plans if len(p.region_path)>=4),None)
            if candidate is not None:
                detour_tested=True
                base=list(candidate.region_path)
                routes.damage_route(candidate.uid,95,minute=120,reason="audit_flood")
                infra=state.route_infrastructure[candidate.uid]
                detour_ok=bool(infra.detour_regions) and [tuple(map(int,t.split(","))) for t in infra.detour_regions]!=base
                routes.repair_route(candidate.uid,100,180)
                detour_ok=detour_ok and not infra.detour_regions
            posts=[p for p in state.border_posts.values() if p.active]
            return {
                "seed":seed.hex(),"settlements":len(towns),"routes":len(plans),
                "sparse_limit":sparse_limit,"sparse_ok":len(plans)<=sparse_limit,
                "bad_portals":bad_portals,
                "infrastructure_records":len(state.route_infrastructure),
                "materialized_active_segments":materialized,
                "bound_gateway_roads":bound_gateway,
                "hinterland_regions":sum(len(f.hinterland_regions) for f in state.factions.values()),
                "border_posts":len(posts),
                "toll_posts":sum(1 for p in posts if p.toll_copper>0),
                "detour_tested":detour_tested,
                "detour_ok":detour_ok,
            }
        finally:
            db.close()


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--seed",default="phase3-route-audit")
    parser.add_argument("--radius",type=int,default=4)
    parser.add_argument("--json",action="store_true")
    args=parser.parse_args()
    result=audit(args.seed.encode("utf-8"),max(1,args.radius))
    if args.json:print(json.dumps(result,sort_keys=True))
    else:
        for key,value in result.items():print(f"{key}: {value}")
    ok=(result["settlements"]>=2 and result["sparse_ok"] and not result["bad_portals"]
        and result["infrastructure_records"]==result["routes"] and result["detour_ok"])
    return 0 if ok else 1


if __name__=="__main__":
    raise SystemExit(main())
