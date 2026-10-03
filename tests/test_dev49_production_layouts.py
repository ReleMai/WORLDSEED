"""Resource-driven v11 layout contracts and frozen legacy plan geography."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.audit_settlement_layouts import (ARCHETYPES, POPULATIONS, MemoryCache,
                                           inspect_skeleton, synthetic_fixture)
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.persistence.database import WorldDatabase
from worldseed.systems.settlement_planner import SettlementSkeleton, SettlementSkeletonPlanner
from worldseed.systems.state import LivingWorldState


class ProductionLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)

    def fixture(self, archetype='agrarian', population=45, cache=None, version=11):
        return synthetic_fixture(self.registry, archetype, population, version, cache)

    def test_all_resource_profiles_and_ranks_have_legal_connected_geometry(self):
        morphologies = set()
        for archetype in ARCHETYPES:
            for population in POPULATIONS:
                with self.subTest(archetype=archetype, population=population):
                    world, region, uid = self.fixture(archetype, population)
                    skeleton = SettlementSkeletonPlanner(world).plan(region, uid, population, persist=False)
                    self.assertEqual(11, skeleton.plan.version)
                    self.assertFalse(inspect_skeleton(world, self.registry, skeleton))
                    # Flat, suitable audit land must actually support its two
                    # advertised industries, not merely list their names.
                    self.assertEqual(set(skeleton.plan.resource_specializations),
                                     {p.resource_deposit for p in skeleton.parcels if p.resource_deposit})
                    morphologies.add(skeleton.plan.morphology)
        self.assertGreaterEqual(len(morphologies), 5)

    def test_generation_order_and_unrelated_world_state_do_not_change_layout(self):
        world, region, uid = self.fixture('mining', 110)
        first = SettlementSkeletonPlanner(world).plan(region, uid, 110, persist=False)
        other = SettlementSkeletonPlanner(world)
        other.plan(region, 'settlement:unrelated', 45, persist=False)
        world.unrelated = {'inventory': 999, 'ui_order': ['z', 'a']}
        rebuilt = other.plan(region, uid, 110, persist=False)
        self.assertEqual(first.fingerprint, rebuilt.fingerprint)
        self.assertEqual(first.to_dict(), rebuilt.to_dict())

    def test_cache_reload_skips_generation_and_deletion_rebuilds_same_plan(self):
        cache = MemoryCache()
        world, region, uid = self.fixture(cache=cache)
        first = SettlementSkeletonPlanner(world).plan(region, uid, 45)
        reloaded = SettlementSkeletonPlanner(world)
        with patch.object(reloaded, '_generate', side_effect=AssertionError('cache hit generated')), \
             patch.object(world, 'environment_at', side_effect=AssertionError('cache hit queried environment')):
            self.assertEqual(first.fingerprint, reloaded.plan(region, uid, 45).fingerprint)
        cache.rows.clear()
        rebuilt = SettlementSkeletonPlanner(world).plan(region, uid, 45, persist=False)
        self.assertEqual(first.fingerprint, rebuilt.fingerprint)
        self.assertEqual(first.to_dict(), SettlementSkeleton.from_dict(first.to_dict()).to_dict())

    def test_resources_not_archetype_name_drive_the_selected_recipe(self):
        world, region, uid = self.fixture('mining', 45)
        ore_plan = SettlementSkeletonPlanner(world).plan(region, uid, 45, persist=False)
        fertile_world, _, _ = self.fixture('agrarian', 45)
        # Keep the seed, settlement identity, archetype, and geometry unchanged;
        # changing the authoritative physical fields must change production.
        world.environment_at = fertile_world.environment_at
        field_plan = SettlementSkeletonPlanner(world).plan(region, uid, 45, persist=False)
        self.assertNotEqual(ore_plan.plan.resource_specializations, field_plan.plan.resource_specializations)
        self.assertNotEqual(ore_plan.plan.morphology, field_plan.plan.morphology)
        self.assertEqual(2, len(field_plan.plan.resource_specializations))

    def test_real_mine_mouth_preference_still_requires_a_legal_reserved_footprint(self):
        world, _, _ = self.fixture('mining', 45)
        planner = SettlementSkeletonPlanner(world)
        mouth = (292,256)
        args = ((256,256),(180,180,332,332),'mining')
        self.assertEqual(mouth, planner._production_site(*args,set(),(1,0),preferred_sites=[mouth]))
        # A real connector cannot justify overlapping another district.
        other = planner._production_site(*args,planner._rect(mouth,13,11),(1,0),preferred_sites=[mouth])
        self.assertNotEqual(mouth,other)
        if other is not None:
            self.assertFalse(planner._rect(mouth,13,11) & planner._rect(other,13,11))

    def test_v10_geometry_matches_pre_dev49_committed_golden(self):
        from tests.test_dev45_farm_compounds import FarmCompoundTests
        fixture = FarmCompoundTests()
        fixture.registry = self.registry
        self.assertEqual('fa414cc16fd96b867bdd60f3916bbc11c23549c5',
                         fixture.skeleton(version=10, population=45).fingerprint)

    def test_v11_cache_rebuild_preserves_authoritative_damage_and_save_integrity(self):
        with tempfile.TemporaryDirectory(prefix='worldseed-layout-v11-') as directory:
            path = Path(directory) / 'layout.db'
            db = WorldDatabase.create(path, 'Production layout regression', b'layout-audit'.hex())
            try:
                world, region, uid = self.fixture(cache=db)
                first = SettlementSkeletonPlanner(world).plan(region, uid, 45)
                structure = next(row for row in first.structures if row.enclosed)
                db.store_physical_plan_delta(structure.uid, 'structure', 1, {'destroyed': True})
                db.connection.execute('DELETE FROM generated_settlement_plans WHERE settlement_uid=?', (uid,))
                db.commit_generated()
                rebuilt = SettlementSkeletonPlanner(world).plan(region, uid, 45)
                self.assertEqual(first.fingerprint, rebuilt.fingerprint)
                self.assertEqual({'destroyed': True}, db.load_physical_plan_delta(structure.uid)['payload'])
                db.save_state(turn=1, tile_deltas={}, player_id=1,
                              position=WorldPos(256, 256, 0), inventory={},
                              sim_state=LivingWorldState().to_dict())
                self.assertEqual([], db.verify())
            finally:
                db.close()

    def test_real_prepared_hydrology_produces_a_legal_complete_v11_skeleton(self):
        from worldseed.app import _village_targets
        from worldseed.world.generator import WorldGenerator
        from worldseed.world.hydrology import HydrologyGenerator
        from worldseed.world.region_blocks import RegionBlockPlanner
        from worldseed.world.world import World
        seed = b'village-start-real-hydrology'
        with tempfile.TemporaryDirectory(prefix='worldseed-layout-real-') as directory:
            db = WorldDatabase.create(Path(directory)/'real.db', 'Real layout smoke', seed.hex())
            try:
                generator = WorldGenerator(seed, self.registry)
                world = World(generator, self.registry, db, auto_hydrology=False)
                world.settlement_plan_version = 11
                hydrology = HydrologyGenerator(generator, db)
                targets = _village_targets(world, seed, self.registry, limit=8)
                self.assertTrue(targets)
                inspected = None
                for target in targets:
                    x0, y0 = target.region_x*512, target.region_y*512
                    bounds = (x0, y0, x0+511, y0+511)
                    hydrology.prepare_world_bounds(*bounds, persist=True)
                    generator.attach_hydrology(hydrology)
                    world.prepare_coastal_mouths(bounds)
                    region = RegionBlockPlanner(world).plan(target.region_x, target.region_y,
                                                           persist=True, refresh=True)
                    if not region.settlement_present or region.settlement_anchor is None:
                        continue
                    uid = f'settlement:{target.region_x}:{target.region_y}'
                    try:
                        skeleton = SettlementSkeletonPlanner(world).plan(region, uid, target.population)
                    except ValueError:
                        # Prepared water may invalidate a provisional candidate;
                        # geometric failures on a generated skeleton must fail.
                        continue
                    self.assertEqual(11, skeleton.plan.version)
                    self.assertTrue(any(row.enclosed for row in skeleton.structures))
                    self.assertFalse(inspect_skeleton(world, self.registry, skeleton))
                    inspected = skeleton
                    break
                self.assertIsNotNone(inspected, 'eight bounded candidates must include a viable physical settlement')
                self.assertEqual([], db.verify())
            finally:
                db.close()


if __name__ == '__main__':
    unittest.main()
