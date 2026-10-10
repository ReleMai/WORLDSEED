from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory
from worldseed.systems.fishing import FishingSystem
from worldseed.systems.state import LivingWorldState
from worldseed.world.fishing_regions import FishingRegion, FishingRegionSampler

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "worldseed" / "data"


class _FakeTerrain:
    tags = ("surface", "water", "water_source", "shallow")
    name = "Freshwater Lake Shallows"


class _FakeTile:
    terrain = _FakeTerrain()


class _FakeGenerator:
    def __init__(self, region):
        self._region = region

    def fishing_region_at(self, pos):
        return self._region


class _FakeWorld:
    def __init__(self, region):
        self.generator = _FakeGenerator(region)

    def tile_at(self, pos):
        return _FakeTile()


class _RegionGenerator:
    def terrain_at(self, pos):
        return "core:river_shallow"

    def sample_fields(self, pos):
        return SimpleNamespace(fertility=50000, moisture=52000, temperature=22000)

    def current_at(self, pos, prepared_only=True):
        return SimpleNamespace(flowing=True, speed=44)


class FishingSystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA)

    def setUp(self):
        self.state = LivingWorldState()
        self.region = FishingRegion(
            "fishzone:test", "lake_shallow", "weedbed", "fresh", "shallow",
            92, 26000, 0, 0, 0
        )
        self.world = _FakeWorld(self.region)
        self.system = FishingSystem(self.state, self.registry, b"fishing-test", self.world)

    def test_world_region_sampler_is_deterministic_and_structured(self):
        sampler = FishingRegionSampler(b"region-test", _RegionGenerator())
        a = sampler.sample(WorldPos(10, 10, 0))
        b = sampler.sample(WorldPos(10, 10, 0))
        self.assertEqual(a, b)
        self.assertEqual(a.habitat, "river")
        self.assertEqual(a.salinity, "fresh")
        self.assertEqual(a.depth, "shallow")
        self.assertGreaterEqual(a.productivity, 10)
        self.assertGreater(a.current, 0)

    def test_methods_require_depth_range_and_real_gear(self):
        inv = Inventory()
        methods = dict(self.system.available_methods(inv, WorldPos(1, 0, 0), 1))
        self.assertIn("hand", methods)
        self.assertNotIn("rod", methods)
        inv.add("core:reed_rod", 1)
        inv.add("core:fiber_line", 1)
        methods = dict(self.system.available_methods(inv, WorldPos(2, 0, 0), 2))
        self.assertIn("rod", methods)
        self.assertNotIn("hand", methods)

    def test_bait_line_and_rod_participate_in_catch_record(self):
        inv = Inventory({
            "core:wood_rod": 1,
            "core:braided_line": 2,
            "core:earthworms": 20,
            "core:spoon_lure": 1,
        })
        caught = False
        for n in range(1, 18):
            ok, msg, minutes, details = self.system.attempt(
                WorldPos(1, 0, 0), inv, "rod", "core:earthworms",
                480 + n * 31, skill=10, perception=10, survival=8
            )
            if ok:
                caught = True
                self.assertGreater(details["weight_g"], 0)
                self.assertGreaterEqual(details["quality"], 10)
                self.assertIn("rod q3 / line q3", msg)
                break
        self.assertTrue(caught, "high-skill angler should land a deterministic catch within the bounded test attempts")
        self.assertTrue(self.state.player_fishing_log)
        row = self.state.player_fishing_log[-1]
        self.assertEqual(row["method"], "rod")
        self.assertEqual(row["bait_id"], "core:earthworms")
        self.assertGreater(row["weight_g"], 0)
        self.assertGreater(row["quality"], 0)
        self.assertTrue(any(v > 0 for v in self.state.fishing_pressure.values()))

    def test_bait_catalog_includes_natural_and_reusable_options(self):
        inv = Inventory({"core:earthworms":2,"core:berries":1,"core:offal":1,"core:spoon_lure":1})
        options = self.system.bait_options(inv)
        self.assertIn("core:earthworms", options)
        self.assertIn("core:berries", options)
        self.assertIn("core:offal", options)
        self.assertIn("core:spoon_lure", options)

    def test_fishing_pressure_recovers_daily(self):
        self.state.fishing_pressure = {"fishzone:test:core:bluegill": 5, "fishzone:test:core:common_carp": 1}
        self.system.daily_update()
        self.assertEqual(self.state.fishing_pressure, {"fishzone:test:core:bluegill": 3})

    def test_expansion_lures_are_selectable_reusable_and_quality_affects_fishing(self):
        low='core:carved_bone_hook';high='core:articulated_spinner_lure'
        inv=Inventory({'core:spring_tension_fishing_rod':1,'core:waxed_casting_line':1,low:1,high:1})
        before=self.state.to_dict(),dict(inv.items)
        self.assertIn(high,self.system.bait_options(inv))
        self.assertIn(low,self.system.bait_options(inv))
        fish=next(iter(self.registry.fish.values()))
        self.assertGreater(self.system._bait_bonus(fish,high),self.system._bait_bonus(fish,low))
        self.assertGreater(self.system._bait_bonus(fish,low),0)
        self.assertEqual((self.state.to_dict(),inv.items),before)
        self.system.attempt(WorldPos(1,0,0),inv,'rod',high,500,10,10,8)
        self.assertEqual(inv.count(high),1)
        self.assertEqual(inv.count('core:spring_tension_fishing_rod'),1)


if __name__ == "__main__":
    unittest.main()
