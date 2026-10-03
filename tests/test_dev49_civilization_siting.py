from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

from worldseed.config import LEGACY_SETTLEMENT_PLAN_VERSION, SETTLEMENT_PLAN_VERSION
from worldseed.core.rng import hash_u64
from worldseed.persistence.database import WorldDatabase
from worldseed.world.regional_civilization import RegionalCivilizationPlanner


class PhysicalWorld:
    """Cheap authoritative field fixture: no terrain generation or simulation."""

    def __init__(self, env=None, fields=None):
        self.calls = 0
        self.field_calls = 0
        self.env = env or self.environment
        self.fields = fields or self.base_fields
        self.generator = NS(world_seed=b"dev49-siting-contract", sample_fields=self.sample_fields)

    @staticmethod
    def base_fields(pos):
        return NS(fertility=40000 + (pos.x * 17 + pos.y * 23) % 13000,
                  moisture=42000, temperature=36000, elevation=34000)

    @staticmethod
    def environment(pos):
        return NS(open_water=False, soil_fertility=55 + (pos.x // 31 + pos.y // 29) % 28,
                  farmland=48 + (pos.x // 29 - pos.y // 37) % 29,
                  slope=12 + (pos.x // 83 + pos.y // 79) % 17,
                  relief=25, flood_risk=8,
                  resources=NS(freshwater=50, timber=55, stone=35), resource_opportunity=47)

    def sample_fields(self, pos):
        self.field_calls += 1
        return self.fields(pos)

    def environment_at(self, pos):
        self.calls += 1
        return self.env(pos)

    def tile_at(self, *args, **kwargs):
        raise AssertionError("Civilization siting must not materialize tiles")


class CivilizationSitingTests(unittest.TestCase):
    def test_versions_1_through_10_keep_pre_v11_fingerprints(self):
        # Captured from 79f21b5 before adding any v11 siting code.
        expected = (
            "9463e5b73567741beb0c8c03b797656e7341af94",
            "7ba64497b8322be0c54ba2c91d68792d182f93cf",
            "085b3bd075bba415ba5c9976103179d98f308d3c",
            "23cbdcd6cee1f234a40f05e12faa6287d0cffb58",
            "5a662470d5e00ff8a8dcb0881555c46c511bd916",
            "8a8c18de7943f2f88cf41e01430ff39eb35b2f45",
            "89137e65d31eed501e4e957fb692688022c6e881",
            "c4aad24485887349b4592c05b33e68d949489fa4",
            "6ff8d3e86c7cb6b0727e9a7f952f7c382c57e712",
            "c5cf1b51a22c2332fa8a7040ffafed0786a13785",
        )
        for version, fingerprint in enumerate(expected, 1):
            with self.subTest(version=version):
                profile = RegionalCivilizationPlanner(PhysicalWorld(), version).profile(-1, 2)
                self.assertEqual(profile.fingerprint, fingerprint)
                self.assertEqual(profile.anchor, (-341, 1126))

    def test_v11_rejects_high_value_tiny_island_for_broad_dry_land(self):
        seed = b"dev49-siting-contract"
        gx = gy = 3
        ix = 54 + gx * 58 + int(hash_u64(seed, "civil-site-x", 0, 0, gx, gy) % 37) - 18
        iy = 54 + gy * 58 + int(hash_u64(seed, "civil-site-y", 0, 0, gx, gy) % 37) - 18

        def env(pos):
            distance = (pos.x - ix) ** 2 + (pos.y - iy) ** 2
            result = PhysicalWorld.environment(pos)
            result.slope = 8
            result.farmland = 62
            result.soil_fertility = 65
            if distance <= 8 ** 2:
                result.farmland = result.soil_fertility = 100
                result.resources = NS(freshwater=100, timber=100, stone=100)
                result.resource_opportunity = 100
                result.slope = result.flood_risk = 0
            elif distance <= 35 ** 2:
                result.open_water = True
            return result

        world = PhysicalWorld(env=env)
        self.assertEqual(RegionalCivilizationPlanner(world, 10)._raw(0, 0)["anchor"], (ix, iy))
        current = RegionalCivilizationPlanner(world, 11)._raw(0, 0)
        x, y = current["anchor"]
        self.assertGreater((x - ix) ** 2 + (y - iy) ** 2, 35 ** 2)
        self.assertGreaterEqual(current["score"], 35)

    def test_v11_rejects_unprepared_base_sea_without_fabricating_fields(self):
        fields = lambda pos: NS(elevation=22000, moisture=42000, fertility=55000, temperature=36000)
        world = PhysicalWorld(env=lambda pos: None, fields=fields)
        planner = RegionalCivilizationPlanner(world, 11)
        self.assertEqual(planner._raw(0, 0)["score"], 0)
        self.assertFalse(planner.profile(0, 0).settlement_present)

    def test_unprepared_base_land_gets_no_prepared_flatness_bonus(self):
        world = PhysicalWorld(env=lambda pos: None)
        planner = RegionalCivilizationPlanner(world, 11)
        cache = {}
        self.assertEqual(planner._site_fitness(100, 100, cache), 0)
        self.assertEqual(len(cache), 9)
        self.assertEqual(world.field_calls, 9)

    def test_flooded_or_steep_cores_and_mixed_preparation_are_not_buildable(self):
        for hazard in ("flood", "slope", "partial"):
            def env(pos):
                result = PhysicalWorld.environment(pos)
                if hazard == "flood":
                    result.flood_risk = 95
                elif hazard == "slope":
                    result.slope = 90
                elif pos.x < 100:
                    return None
                return result

            with self.subTest(hazard=hazard):
                planner = RegionalCivilizationPlanner(PhysicalWorld(env=env), 11)
                self.assertIsNone(planner._site_fitness(100, 100, {}))

    def test_v11_resource_specialization_rewards_real_non_farm_opportunity(self):
        def env(pos):
            result = PhysicalWorld.environment(pos)
            result.farmland = 20
            result.resources = NS(freshwater=45, timber=90, stone=35)
            result.resource_opportunity = 65
            return result

        world = PhysicalWorld(env=env)
        legacy = RegionalCivilizationPlanner(world, 10)._site_score(100, 100)
        current = RegionalCivilizationPlanner(world, 11)._site_score(100, 100)
        self.assertEqual(current[1], "forest")
        self.assertEqual(current[0] - legacy[0], 14)

    def test_v11_raw_environment_queries_are_bounded_and_cached(self):
        world = PhysicalWorld()
        planner = RegionalCivilizationPlanner(world, 11)
        first = planner._raw(-2, 3)
        self.assertLessEqual(world.calls, 126)
        calls = world.calls
        self.assertIs(planner._raw(-2, 3), first)
        self.assertEqual(world.calls, calls)
        self.assertGreaterEqual(first["anchor"][0], -2 * 512 + 64)
        self.assertLess(first["anchor"][0], -2 * 512 + 448)

    def test_v11_profiles_are_generation_order_independent(self):
        coords = [(-1, 1), (0, 1), (-1, 2), (0, 2)]
        forward = RegionalCivilizationPlanner(PhysicalWorld(), 11)
        reverse = RegionalCivilizationPlanner(PhysicalWorld(), 11)
        expected = {coord: forward.profile(*coord) for coord in coords}
        actual = {coord: reverse.profile(*coord) for coord in reversed(coords)}
        self.assertEqual(expected, actual)

    def test_v11_competes_only_with_physically_nearby_stronger_sites(self):
        class FixedSites(RegionalCivilizationPlanner):
            def __init__(self, version, near):
                super().__init__(PhysicalWorld(), version)
                self.near = near

            def _raw(self, rx, ry):
                center = rx == 0 and ry == 0
                x = 100 if center else (450 if self.near and (rx, ry) == (1, 0) else rx * 512 + 100)
                y = ry * 512 + 100
                return dict(score=55 if center else 65, route=55, crossing=30,
                            defense=30, anchor=(x, y), archetype="agrarian", carrying=60)

        self.assertFalse(FixedSites(10, False).profile(0, 0).settlement_present)
        self.assertTrue(FixedSites(11, False).profile(0, 0).settlement_present)
        self.assertFalse(FixedSites(11, True).profile(0, 0).settlement_present)


class CivilizationVersionMetadataTests(unittest.TestCase):
    def test_missing_contract_stays_v10_but_new_save_records_v11(self):
        self.assertEqual(SETTLEMENT_PLAN_VERSION, 11)
        self.assertEqual(LEGACY_SETTLEMENT_PLAN_VERSION, 10)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "world.db"
            db = WorldDatabase.create(path, "contract", "00")
            self.assertEqual(db.get_meta("settlement_plan_version"), 11)
            db.connection.execute("DELETE FROM world_meta WHERE key='settlement_plan_version'")
            db.connection.commit()
            db.close()
            db = WorldDatabase.open(path)
            try:
                self.assertEqual(db.get_meta("settlement_plan_version"), 10)
            finally:
                db.close()

    def test_existing_explicit_contracts_1_through_11_remain_pinned(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "world.db"
            db = WorldDatabase.create(path, "contract", "00")
            db.close()
            for version in range(1, 12):
                with self.subTest(version=version):
                    db = WorldDatabase.open(path)
                    db.set_meta("settlement_plan_version", version)
                    db.connection.commit()
                    db.close()
                    db = WorldDatabase.open(path)
                    try:
                        self.assertEqual(db.get_meta("settlement_plan_version"), version)
                    finally:
                        db.close()


if __name__ == "__main__":
    unittest.main()
