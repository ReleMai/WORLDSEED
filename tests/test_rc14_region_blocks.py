from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.persistence.database import WorldDatabase
from worldseed.systems.generation import ProceduralSocietyGenerator
from worldseed.world.generator import WorldGenerator
from worldseed.world.region_blocks import REGION_SIZE, RegionBlockPlanner, entry_side
from worldseed.world.world import World


class RegionBlockTests(unittest.TestCase):
    def make_world(self, seed=b'region-block-dev5'):
        td=tempfile.TemporaryDirectory();self.addCleanup(td.cleanup)
        reg=ContentRegistry.load(DATA_DIR)
        db=WorldDatabase.create(Path(td.name)/'world.db','test',seed.hex());self.addCleanup(db.close)
        world=World(WorldGenerator(seed,reg),reg,db)
        return world,db

    def test_plan_is_deterministic_persisted_and_anchor_has_rural_margin(self):
        world,db=self.make_world();planner=RegionBlockPlanner(world)
        # Find a deterministic region that contains a settlement.
        coords=next(( (x,y) for y in range(-4,5) for x in range(-4,5) if planner._presence(x,y) ))
        plan=planner.plan(*coords,persist=True)
        self.assertTrue(plan.settlement_present);self.assertIsNotNone(plan.settlement_anchor)
        x,y=plan.settlement_anchor;x0,y0=coords[0]*REGION_SIZE,coords[1]*REGION_SIZE
        self.assertGreaterEqual(x,x0+64);self.assertLess(x,x0+REGION_SIZE-64)
        self.assertGreaterEqual(y,y0+64);self.assertLess(y,y0+REGION_SIZE-64)
        raw=db.load_generated_regional_plan(*coords,planner.version);self.assertIsNotNone(raw)
        planner2=RegionBlockPlanner(world);again=planner2.plan(*coords,persist=False)
        self.assertEqual(plan,again)

    def test_settlement_presence_and_anchor_match_society_generator(self):
        world,_=self.make_world();planner=RegionBlockPlanner(world)
        society=ProceduralSocietyGenerator(planner.seed,world.registry,planner)
        for ry in range(-3,4):
            for rx in range(-3,4):
                plan=planner.plan(rx,ry,persist=False)
                generated=society.settlement_for_cell(rx,ry)
                self.assertEqual(plan.settlement_present, generated is not None)
                if generated is not None:
                    settlement=generated[0]
                    self.assertEqual((settlement.x,settlement.y),plan.settlement_anchor)

    def test_road_edge_contract_is_symmetric(self):
        world,_=self.make_world();planner=RegionBlockPlanner(world)
        opposites={'north':'south','south':'north','east':'west','west':'east'}
        deltas={'north':(0,-1),'south':(0,1),'east':(1,0),'west':(-1,0)}
        found=0
        for ry in range(-4,5):
            for rx in range(-4,5):
                a=planner.plan(rx,ry,persist=False)
                for road in a.roads:
                    dx,dy=deltas[road.direction];b=planner.plan(rx+dx,ry+dy,persist=False)
                    mate=next((r for r in b.roads if r.direction==opposites[road.direction]),None)
                    self.assertIsNotNone(mate)
                    self.assertEqual(road.offset,mate.offset)
                    self.assertEqual(road.road_class,mate.road_class);found+=1
        self.assertGreater(found,0)

    def test_entry_side_matches_direction_of_travel(self):
        n=REGION_SIZE
        self.assertEqual(entry_side(10,n-1,10,n),'north')
        self.assertEqual(entry_side(10,0,10,-1),'south')
        self.assertEqual(entry_side(n-1,10,n,10),'west')
        self.assertEqual(entry_side(0,10,-1,10),'east')
        self.assertIsNone(entry_side(10,10,11,10))

    def test_prepared_lookup_never_generates_writes_or_populates_cache(self):
        world, db = self.make_world()
        plan = RegionBlockPlanner(world).plan(-1, 0)
        reader = RegionBlockPlanner(world)
        before = db.connection.total_changes
        with patch.object(reader, '_generate', side_effect=AssertionError('generation')):
            self.assertEqual(reader.read_prepared(-1, 0), plan)
            self.assertIsNone(reader.read_prepared(100, 100))
            self.assertEqual(reader._cache, {})
            self.assertEqual(db.connection.total_changes, before)
            corrupt = plan.to_dict()
            corrupt['dominant_biome'] = 'water'
            db.store_generated_regional_plan(-1, 0, reader.version, corrupt)
            self.assertIsNone(reader.read_prepared(-1, 0))
            self.assertEqual(reader._cache, {})


if __name__=='__main__':unittest.main()
