from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.persistence.database import WorldDatabase
from worldseed.systems.route_planner import RoutePlanner
from worldseed.systems.state import LivingWorldState, SettlementState
from worldseed.world.generator import WorldGenerator
from worldseed.world.region_blocks import RegionBlockPlanner
from worldseed.world.world import World


class RegionalCivilizationRouteTests(unittest.TestCase):
    def make_world(self, seed=b"regional-civilization-phase1"):
        td=tempfile.TemporaryDirectory();self.addCleanup(td.cleanup)
        reg=ContentRegistry.load(DATA_DIR)
        db=WorldDatabase.create(Path(td.name)/"world.db","regional",seed.hex());self.addCleanup(db.close)
        world=World(WorldGenerator(seed,reg),reg,db)
        world.settlement_plan_version=4;world.routegen_version=2
        return world,db

    def test_civilization_profiles_are_deterministic_and_terrain_scored(self):
        world,_=self.make_world();planner=RegionBlockPlanner(world)
        profiles=[planner.civilization.profile(x,y) for y in range(-2,3) for x in range(-2,3)]
        self.assertTrue(any(p.settlement_present for p in profiles))
        self.assertTrue(any(not p.settlement_present for p in profiles))
        for p in profiles:
            self.assertEqual(p,planner.civilization.profile(p.region_x,p.region_y))
            if p.settlement_present:self.assertGreaterEqual(p.score,40)

    def test_route_planner_builds_sparse_persisted_network(self):
        world,db=self.make_world();regions=RegionBlockPlanner(world);state=LivingWorldState()
        coords=[]
        for y in range(-4,5):
            for x in range(-4,5):
                p=regions.plan(x,y,persist=True)
                if p.settlement_present:coords.append((x,y,p))
                if len(coords)>=5:break
            if len(coords)>=5:break
        self.assertGreaterEqual(len(coords),3)
        for i,(x,y,p) in enumerate(coords):
            uid=f"settlement:{x}:{y}"
            state.settlements[uid]=SettlementState(uid,f"Town {i}",x,y,p.settlement_anchor[0],p.settlement_anchor[1],
                                                   40+i*25,"culture:test","religion:test","faction:test")
        center=(coords[0][0],coords[0][1])
        planner=RoutePlanner(world,state,regions)
        plans=planner.sync(state.settlements.values(),center,radius=10,persist=True)
        self.assertTrue(plans)
        n=len(state.settlements)
        self.assertLessEqual(len(plans),(n-1)+max(1,n//3))
        self.assertTrue(all(p.region_path and p.chunk_corridor for p in plans))
        self.assertGreaterEqual(len(state.trade_routes),len(plans)*2)
        self.assertIsNotNone(db.load_generated_route_plan(plans[0].uid,planner.version))


if __name__=="__main__":
    unittest.main()
