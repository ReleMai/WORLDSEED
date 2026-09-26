from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.persistence.database import WorldDatabase
from worldseed.systems.route_planner import RoutePlanner
from worldseed.systems.state import FactionState, LivingWorldState, SettlementState
from worldseed.world.generator import WorldGenerator
from worldseed.world.region_blocks import RegionBlockPlanner
from worldseed.world.world import World


class RegionalTransportPhase3Tests(unittest.TestCase):
    def make_world(self, seed=b"regional-transport-phase3"):
        td=tempfile.TemporaryDirectory();self.addCleanup(td.cleanup)
        reg=ContentRegistry.load(DATA_DIR)
        db=WorldDatabase.create(Path(td.name)/"world.db","phase3",seed.hex());self.addCleanup(db.close)
        world=World(WorldGenerator(seed,reg),reg,db)
        world.settlement_plan_version=5
        world.routegen_version=4
        return world,reg,db

    def town(self,uid,rx,ry,faction,pop=120):
        return SettlementState(
            uid=uid,name=uid,region_x=rx,region_y=ry,
            x=rx*512+256,y=ry*512+256,population=pop,
            culture_id=f"culture:{faction}",religion_id="religion:test",
            faction_id=faction,wealth=800,
        )

    def test_hard_route_damage_creates_detour_and_repair_restores_base(self):
        world,_,_=self.make_world()
        state=LivingWorldState()
        state.factions["faction:a"]=FactionState("faction:a","A","culture:a",treasury=2000,power=70,prominence=70)
        a=self.town("a",0,0,"faction:a")
        b=self.town("b",4,0,"faction:a")
        state.settlements={a.uid:a,b.uid:b}
        planner=RoutePlanner(world,state,RegionBlockPlanner(world))
        plans=planner.sync_network(state.settlements.values(),persist=False)
        self.assertEqual(len(plans),1)
        plan=plans[0]
        self.assertGreaterEqual(len(plan.region_path),4)
        base=list(plan.region_path)
        changed=planner.damage_route(plan.uid,95,minute=120,reason="flood")
        self.assertTrue(changed)
        infra=state.route_infrastructure[plan.uid]
        self.assertTrue(infra.detour_regions)
        detour=[tuple(map(int,row.split(","))) for row in infra.detour_regions]
        self.assertNotEqual(base,detour)
        self.assertGreater(infra.reroute_count,0)
        planner.repair_route(plan.uid,100,180)
        self.assertFalse(infra.detour_regions)
        self.assertFalse(infra.hazard_regions)
        self.assertGreater(infra.condition,25)

    def test_faction_influence_creates_frontier_posts_tolls_and_patrols(self):
        world,_,_=self.make_world(b"phase3-frontier")
        state=LivingWorldState()
        state.factions["faction:a"]=FactionState(
            "faction:a","River League","culture:a",treasury=3000,power=85,prominence=80,toll_policy=70
        )
        state.factions["faction:b"]=FactionState(
            "faction:b","Iron March","culture:b",treasury=3000,power=90,prominence=78,toll_policy=65
        )
        a=self.town("a",0,0,"faction:a",150)
        b=self.town("b",5,0,"faction:b",160)
        state.settlements={a.uid:a,b.uid:b}
        planner=RoutePlanner(world,state,RegionBlockPlanner(world))
        plans=planner.sync_network(state.settlements.values(),persist=False)
        self.assertEqual(len(plans),1)
        plan=plans[0]
        posts=planner.border_posts_for_route(plan.uid)
        self.assertTrue(posts)
        self.assertTrue(any(p.toll_copper>0 for p in posts))
        self.assertTrue(any(p.patrol_strength>0 for p in posts))
        infra=state.route_infrastructure[plan.uid]
        self.assertGreaterEqual(infra.toll_copper,1)
        self.assertGreater(infra.patrol_strength,0)
        before=sum(f.treasury for f in state.factions.values())
        paid=planner.collect_toll(plan.uid,planner.route_toll(plan.uid))
        self.assertGreaterEqual(paid,1)
        self.assertEqual(sum(f.treasury for f in state.factions.values()),before+paid)
        self.assertIn(a.frontier_status,{"core","frontier","contested"})
        self.assertIn(b.frontier_status,{"core","frontier","contested"})

    def test_war_damage_uses_same_route_and_state_round_trips(self):
        world,_,_=self.make_world(b"phase3-war")
        state=LivingWorldState()
        fa=FactionState("faction:a","A","culture:a",treasury=1500,power=80,prominence=75,at_war=["faction:b"])
        fb=FactionState("faction:b","B","culture:b",treasury=1500,power=80,prominence=75,at_war=["faction:a"])
        state.factions={fa.uid:fa,fb.uid:fb}
        a=self.town("a",0,0,fa.uid)
        b=self.town("b",4,0,fb.uid)
        state.settlements={a.uid:a,b.uid:b}
        planner=RoutePlanner(world,state,RegionBlockPlanner(world))
        plan=planner.sync_network(state.settlements.values(),persist=False)[0]
        before=state.route_infrastructure[plan.uid].condition
        affected=planner.apply_war_damage(fa.uid,fb.uid,30*1440,severity=45)
        self.assertEqual(affected,(plan.uid,))
        infra=state.route_infrastructure[plan.uid]
        crossing_damage=any(v<100 for v in infra.crossing_conditions.values())
        self.assertTrue(infra.condition<before or crossing_damage)
        restored=LivingWorldState.from_dict(state.to_dict())
        copy=restored.route_infrastructure[plan.uid]
        self.assertEqual(copy.condition,infra.condition)
        self.assertEqual(copy.detour_regions,infra.detour_regions)
        self.assertEqual(copy.reroute_count,infra.reroute_count)
        self.assertEqual(
            {uid:p.toll_copper for uid,p in restored.border_posts.items()},
            {uid:p.toll_copper for uid,p in state.border_posts.items()},
        )


if __name__=="__main__":
    unittest.main()
