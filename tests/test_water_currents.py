from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.persistence.database import WorldDatabase
from worldseed.world.generator import WorldGenerator
from worldseed.world.hydrology import HydrologyGenerator
from worldseed.world.region_blocks import RegionBlockPlanner
from worldseed.world.world import World


class WaterCurrentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)
        cls.gen = WorldGenerator(b'rc14-current-dev12', cls.registry, version=5)
        cls.hydro = HydrologyGenerator(cls.gen)
        cls.hydro.prepare_window(-1, 0, -1, 0, persist=False)
        cls.gen.attach_hydrology(cls.hydro)

    def test_river_and_ocean_current_samples_exist_and_are_directional(self):
        river = next(
            WorldPos(x, y, 0)
            for y in range(-256, 257, 4)
            for x in range(-256, 257, 4)
            if (surface := self.hydro.surface_at(WorldPos(x, y, 0), prepared_only=True)) is not None
            and int(surface.river_class) > 0
        )
        ocean = next(
            WorldPos(x, y, 0)
            for y in range(-768, 769, 16)
            for x in range(-768, 769, 16)
            if self.gen.sample_fields(WorldPos(x, y, 0)).elevation < 23800
            and ((surface := self.hydro.surface_at(WorldPos(x, y, 0), prepared_only=True)) is None or int(surface.river_class) == 0)
        )
        river_current = self.gen.current_at(river, prepared_only=True)
        ocean_current = self.gen.current_at(ocean, prepared_only=True)
        self.assertIsNotNone(river_current)
        self.assertTrue(river_current.flowing)
        self.assertEqual(river_current.kind, 'river')
        self.assertIn(river_current.heading, {'north', 'northeast', 'east', 'southeast', 'south', 'southwest', 'west', 'northwest'})
        self.assertGreater(river_current.speed, 0)
        self.assertIsNotNone(ocean_current)
        self.assertTrue(ocean_current.flowing)
        self.assertIn(ocean_current.kind, {'ocean', 'ocean_shore'})
        self.assertIn(ocean_current.heading, {'north', 'northeast', 'east', 'southeast', 'south', 'southwest', 'west', 'northwest'})

    def test_region_plans_encode_water_current_metadata(self):
        td = tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup)
        db = WorldDatabase.create(Path(td.name) / 'currents.db', 'currents', self.gen.world_seed.hex())
        self.addCleanup(db.close)
        world = World(self.gen, self.registry, db)
        planner = RegionBlockPlanner(world)
        target = None
        for ry in range(-3, 4):
            for rx in range(-3, 4):
                plan = planner.plan(rx, ry, persist=False)
                if plan.waters:
                    target = plan
                    break
            if target is not None:
                break
        self.assertIsNotNone(target)
        self.assertTrue(any(w.current_heading != 'still' and w.current_strength > 0 for w in target.waters))
        self.assertTrue(all(w.water_kind in {'river', 'ocean'} for w in target.waters))


if __name__ == '__main__':
    unittest.main()
