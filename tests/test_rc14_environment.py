import tempfile
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.persistence.database import WorldDatabase
from worldseed.world.environmental_fields import EnvironmentalFieldSampler
from worldseed.world.generator import WorldFields, WorldGenerator
from worldseed.world.hydrology import HydrologyGenerator, HydrologySurface


class EnvironmentalFieldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)
        cls.gen = WorldGenerator(b'rc14-golden-00', cls.registry, version=5)
        cls.hydro = HydrologyGenerator(cls.gen)
        cls.hydro.prepare_window(-1, 0, -1, 0, persist=False)
        cls.gen.attach_hydrology(cls.hydro)

    def test_bounds_and_order_independence_across_negative_chunk_and_domain_edges(self):
        points = [WorldPos(x, y, 0) for x in (-33, -32, -1, 0, 1, 31, 32, 1023)
                  for y in (-33, -1, 0, 32)]
        sampler = EnvironmentalFieldSampler(self.gen, cache_limit=3)
        before = {p: sampler.at(p) for p in points}
        for p in reversed(points):
            self.assertEqual(before[p], sampler.at(p))
            raw = asdict(before[p]); resources = raw.pop('resources'); raw.pop('version'); raw.pop('open_water')
            for value in [*raw.values(), *resources.values(), before[p].resource_opportunity]:
                self.assertGreaterEqual(value, 0)
                self.assertLessEqual(value, 100)
        self.assertEqual(len(sampler._cache), 3)

    def test_warm_read_skips_sampling_and_planning(self):
        p = WorldPos(5, 7, 0)
        sampler = EnvironmentalFieldSampler(self.gen)
        expected = sampler.at(p)
        with patch.object(self.gen, 'sample_fields', side_effect=AssertionError('resampled')), \
             patch.object(self.hydro, 'generate', side_effect=AssertionError('planned')), \
             patch.object(self.hydro, 'prepare_window', side_effect=AssertionError('planned')):
            self.assertIs(expected, sampler.at(p))

    def test_unprepared_read_never_generates_or_caches_fake_values(self):
        gen = WorldGenerator(b'unprepared', self.registry, version=5)
        planner = HydrologyGenerator(gen); gen.attach_hydrology(planner)
        with patch.object(planner, 'generate', side_effect=AssertionError('planned')):
            self.assertIsNone(gen.environment_at(WorldPos(0, 0, 0)))
            self.assertIsNone(planner.surface_at(WorldPos(0, 0, 0), prepared_only=True))
            self.assertEqual(len(gen.environmental_fields._cache), 0)

    def test_legacy_and_underground_do_not_use_new_hydrology(self):
        gen = WorldGenerator(b'legacy', self.registry, version=4)
        planner = HydrologyGenerator(gen); gen.attach_hydrology(planner)
        with patch.object(planner, 'cached_domain', side_effect=AssertionError('legacy hydro')):
            self.assertIsNotNone(gen.environment_at(WorldPos(0, 0, 0)))
            self.assertIsNone(gen.environment_at(WorldPos(0, 0, -1)))

    def test_hydrology_fingerprint_invalidates_derived_cache(self):
        p = WorldPos(11, 9, 0); sampler = EnvironmentalFieldSampler(self.gen)
        before = sampler.at(p)
        domain = self.hydro.cached_domain(0, 0)
        with patch.object(self.hydro, 'cached_domain', return_value=replace(domain, fingerprint='changed')):
            after = sampler.at(p)
        self.assertEqual(before, after)
        self.assertIsNot(before, after)

    def test_terrain_and_broad_climate_are_unchanged_by_reads(self):
        p = WorldPos(-12, 18, 0)
        terrain = self.gen.terrain_at(p)
        v4 = WorldGenerator(self.gen.world_seed, self.registry, version=4)
        self.assertEqual(v4.sample_fields(p), self.gen.sample_fields(p))
        self.gen.environment_at(p)
        self.assertEqual(terrain, self.gen.terrain_at(p))

    def test_causal_drainage_flood_and_slope_responses(self):
        class Flat:
            def sample_fields(self, p):
                return WorldFields(36000, 40000, 36000, 48000)
        pos = WorldPos(0, 0, 0)
        sampler = EnvironmentalFieldSampler(Flat())
        dry = sampler._derive(pos, HydrologySurface())
        wet = sampler._derive(pos, HydrologySurface(wetland_probability=85, floodplain_strength=80, flood_risk=85))
        self.assertGreater(wet.wetness, dry.wetness)
        self.assertLess(wet.drainage, dry.drainage)
        self.assertLess(wet.farmland, dry.farmland)
        class Hills(Flat):
            def sample_fields(self, p):
                return replace(super().sample_fields(p), elevation=36000 + p.x * 300)
        hills = EnvironmentalFieldSampler(Hills())._derive(pos, HydrologySurface())
        self.assertGreater(hills.slope, dry.slope)
        self.assertGreater(hills.relief, dry.relief)
        self.assertLess(hills.farmland, dry.farmland)

    def test_open_water_not_farmland_and_ocean_not_freshwater(self):
        class Flat:
            def sample_fields(self, p):
                return WorldFields(36000, 40000, 36000, 48000)
        p = WorldPos(0, 0, 0)
        lake = EnvironmentalFieldSampler(Flat())._derive(p, HydrologySurface(lake=True, water_access_score=100))
        self.assertTrue(lake.open_water)
        self.assertEqual((lake.farmland, lake.resources.forage, lake.resources.timber), (0, 0, 0))
        self.assertEqual(lake.resources.freshwater, 100)
        class Ocean(Flat):
            def sample_fields(self, p):
                return replace(super().sample_fields(p), elevation=20000)
        ocean = EnvironmentalFieldSampler(Ocean())._derive(p, HydrologySurface(water_access_score=100))
        self.assertEqual(ocean.resources.freshwater, 0)

    def test_save_reload_and_actual_cache_deletion_reproduce_fields_preserve_deltas(self):
        with tempfile.TemporaryDirectory() as td:
            db = WorldDatabase.create(Path(td) / 'world.db', 'test', self.gen.world_seed.hex())
            planner = HydrologyGenerator(self.gen, db)
            planner.prepare_window(0, 0, 0, 0, persist=True)
            gen = WorldGenerator(self.gen.world_seed, self.registry, version=5)
            gen.attach_hydrology(HydrologyGenerator(gen, db))
            p = WorldPos(5, 7, 0)
            with patch.object(gen.hydrology, 'generate', side_effect=AssertionError('must load')):
                expected = gen.environment_at(p)
            self.assertIsNotNone(expected)
            db.store_physical_plan_delta('bridge:test', 'crossing', 1, {'destroyed': True})
            db.commit_generated(); db.close()
            db = WorldDatabase.open(Path(td) / 'world.db')
            loaded = WorldGenerator(self.gen.world_seed, self.registry, version=5)
            loaded.attach_hydrology(HydrologyGenerator(loaded, db))
            with patch.object(loaded.hydrology, 'generate', side_effect=AssertionError('must load')):
                self.assertEqual(expected, loaded.environment_at(p))
            db.connection.execute('DELETE FROM generated_hydrology_domains'); db.connection.commit()
            rebuilt = WorldGenerator(self.gen.world_seed, self.registry, version=5)
            rebuilt.attach_hydrology(HydrologyGenerator(rebuilt, db))
            self.assertIsNone(rebuilt.environment_at(p))
            rebuilt.hydrology.prepare_window(0, 0, 0, 0, persist=True)
            self.assertEqual(expected, rebuilt.environment_at(p))
            self.assertEqual(db.load_physical_plan_delta('bridge:test')['payload'], {'destroyed': True})
            db.close()

    def test_persist_request_writes_previously_memory_only_hydrology(self):
        with tempfile.TemporaryDirectory() as td:
            db = WorldDatabase.create(Path(td) / 'world.db', 'test', self.gen.world_seed.hex())
            planner = HydrologyGenerator(self.gen, db)
            first = planner.load_or_generate(0, 0, persist=False)
            self.assertIsNone(db.load_generated_hydrology_domain(0, 0, planner.version))
            with patch.object(planner, 'generate', side_effect=AssertionError('regenerated')):
                planner.load_or_generate(0, 0, persist=True)
            self.assertEqual(db.load_generated_hydrology_domain(0, 0, planner.version)['fingerprint'], first.fingerprint)
            db.close()
