"""Bounded Phase-2 regional transport audit.

This audit deliberately realizes only a small region window. It verifies the
strategic graph is sparse, region transitions have exact adjacent portals,
mutable route infrastructure exists, settlement gateways bind selected routes
and local road materialization reaches the active region.
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
            world.settlement_plan_version=5;world.routegen_version=3
            regions=RegionBlockPlanner(world);state=LivingWorldState()
            state.factions["faction:audit"]=FactionState("faction:audit","Audit League","culture:audit",treasury=5000,prominence=75)
            towns=[]
            for y in range(-radius,radius+1):
                for x in range(-radius,radius+1):
                    plan=regions.plan(x,y,persist=True)
                    if not plan.settlement_present or plan.settlement_anchor is None:continue
                    uid=f"settlement:{x}:{y}"
                    town=SettlementState(uid,f"Audit {len(towns)}",x,y,*plan.settlement_anchor,
                                         80+len(towns)*10,"culture:audit","religion:audit","faction:audit")
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
            return {
                "seed":seed.hex(),"settlements":len(towns),"routes":len(plans),
                "sparse_limit":sparse_limit,"sparse_ok":len(plans)<=sparse_limit,
                "bad_portals":bad_portals,
                "infrastructure_records":len(state.route_infrastructure),
                "materialized_active_segments":materialized,
                "bound_gateway_roads":bound_gateway,
                "hinterland_regions":len(state.factions["faction:audit"].hinterland_regions),
            }
        finally:
            db.close()


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--seed",default="phase2-route-audit")
    parser.add_argument("--radius",type=int,default=4)
    parser.add_argument("--json",action="store_true")
    args=parser.parse_args()
    result=audit(args.seed.encode("utf-8"),max(1,args.radius))
    if args.json:print(json.dumps(result,sort_keys=True))
    else:
        for key,value in result.items():print(f"{key}: {value}")
    ok=result["settlements"]>=2 and result["sparse_ok"] and not result["bad_portals"] and result["infrastructure_records"]==result["routes"]
    return 0 if ok else 1


if __name__=="__main__":
    raise SystemExit(main())
