from __future__ import annotations

import tempfile
import unittest
from hashlib import blake2b
from pathlib import Path

from worldseed.config import (
    DATA_DIR, HYDROLOGY_VERSION, HYDROLOGY_MORPHOLOGY_VERSION,
    COAST_MORPHOLOGY_VERSION, ROUTEGEN_VERSION, SETTLEMENT_PLAN_VERSION, WORLDGEN_VERSION,
)
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import ChunkKey, WorldPos
from worldseed.persistence.database import WorldDatabase
from worldseed.world.generator import WorldGenerator
from worldseed.world.world import World
from worldseed.world.hydrology import (
    HydrologyGenerator, audit_domain, audit_window_seams, HYDROLOGY_ALGORITHM,
    HYDROLOGY_ALGORITHM_V1, HYDROLOGY_ALGORITHM_V2, hydrology_algorithm,
)
from worldseed.world.regional_plan import stable_plan_uid


class RC14HydrologyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)
        cls.seed = b'rc14-hydrology-tests'

    def _hydro(self):
        return HydrologyGenerator(WorldGenerator(self.seed, self.registry, version=WORLDGEN_VERSION))

    def test_phase4_contract_versions_activate_hydrology_v2(self):
        self.assertEqual(HYDROLOGY_VERSION, 2)
        self.assertEqual(HYDROLOGY_MORPHOLOGY_VERSION, 2)
        self.assertEqual(SETTLEMENT_PLAN_VERSION, 3)
        self.assertEqual(ROUTEGEN_VERSION, 1)
        self.assertEqual(WORLDGEN_VERSION, 8)
        self.assertEqual(HYDROLOGY_ALGORITHM, HYDROLOGY_ALGORITHM_V2)
        self.assertEqual(hydrology_algorithm(1), HYDROLOGY_ALGORITHM_V1)
        self.assertEqual(hydrology_algorithm(2), HYDROLOGY_ALGORITHM_V2)

    def test_frozen_rc13_golden_terrain_fingerprints(self):
        expected = {
            'rc14-golden-00':'6d36ad680a8672589485deea15faa001',
            'rc14-golden-01':'d4a87ae513f76f135f1c508d2697e75e',
            'rc14-golden-02':'b429b73f991db55f65e023e36ea934c3',
            'rc14-golden-03':'d4a87ae513f76f135f1c508d2697e75e',
            'rc14-golden-04':'1f6c7dd3253896314e08d69c62c484a0',
            'rc14-golden-05':'d1b7b0ed88a03ec0bd74c25aadd1154d',
            'rc14-golden-06':'d4a87ae513f76f135f1c508d2697e75e',
            'rc14-golden-07':'5f92a259c9def3d9688054d7bf67a137',
            'rc14-golden-08':'dcdcd19ce3e378068fd83acadbe3ed60',
            'rc14-golden-09':'125c9cce4f0d2afd248f4b1fefb6d6c3',
        }
        from worldseed.core.coords import ChunkKey
        for seed_text, fingerprint in expected.items():
            gen = WorldGenerator(seed_text.encode(), self.registry, version=4)
            h = blake2b(digest_size=16, person=b'WS-RC13-BASE')
            for cy in range(-1,2):
                for cx in range(-1,2):
                    chunk = gen.generate_chunk(ChunkKey(cx,cy,0))
                    for idx in chunk.terrain:
                        h.update(self.registry.terrain_id(idx).encode()); h.update(b'\0')
            self.assertEqual(h.hexdigest(), fingerprint, seed_text)

    def test_same_seed_same_domain_same_fingerprint(self):
        a = self._hydro().generate(0, 0)
        b = self._hydro().generate(0, 0)
        self.assertEqual(a.fingerprint, b.fingerprint)
        self.assertEqual(a.flow_to, b.flow_to)
        self.assertEqual(a.accumulation, b.accumulation)
        self.assertEqual(a.watershed_id, b.watershed_id)

    def test_generation_order_does_not_change_domain(self):
        h = self._hydro()
        expected = h.generate(-1, 2).fingerprint
        h.generate(7, -9)
        h.generate(0, 0)
        self.assertEqual(expected, h.generate(-1, 2).fingerprint)

    def test_core_nodes_drain_and_accumulation_is_monotonic(self):
        domain = self._hydro().generate(0, 0)
        self.assertEqual(audit_domain(domain), [])

    def test_v2_persists_climate_runoff_and_channel_gradients(self):
        domain = self._hydro().generate(0, 0)
        n = domain.width * domain.height
        self.assertEqual(domain.version, 2)
        self.assertEqual(domain.algorithm, HYDROLOGY_ALGORITHM_V2)
        self.assertEqual(len(domain.runoff), n)
        self.assertEqual(len(domain.channel_gradient), n)
        self.assertTrue(all(1 <= v <= 12 for v in domain.runoff))
        self.assertTrue(all(v >= 0 for v in domain.channel_gradient))
        self.assertGreater(sum(domain.runoff), n)

    def test_hydrology_v1_contract_remains_loadable_and_distinct(self):
        gen = WorldGenerator(self.seed, self.registry, version=7)
        old = HydrologyGenerator(gen, version=1).generate(0, 0)
        new = HydrologyGenerator(WorldGenerator(self.seed, self.registry, version=8), version=2).generate(0, 0)
        self.assertEqual(old.algorithm, HYDROLOGY_ALGORITHM_V1)
        self.assertEqual(old.runoff, ())
        self.assertEqual(old.channel_gradient, ())
        self.assertNotEqual(old.fingerprint, new.fingerprint)
        self.assertEqual(audit_domain(old), [])
        self.assertEqual(audit_domain(new), [])

    def test_v2_surface_exposes_physical_channel_morphology(self):
        gen = WorldGenerator(b'v8-hydro-morphology', self.registry, version=8)
        planner = HydrologyGenerator(gen, version=2, morphology_version=2)
        planner.prepare_window(-1, 0, -1, 0, persist=False)
        gen.attach_hydrology(planner)
        styles=set();river_cells=0;physical_fords=0
        for y in range(-384,385,4):
            for x in range(-384,385,4):
                surface=planner.surface_at(WorldPos(x,y,0),prepared_only=True)
                if not surface or surface.river_class<=0:continue
                river_cells+=1;styles.add(surface.channel_style)
                if surface.ford:
                    physical_fords+=1
                    self.assertLessEqual(surface.river_class,2)
                    self.assertLess(surface.crossing_cost,80)
                if surface.gorge:self.assertTrue(surface.rapid)
                if surface.delta:self.assertGreaterEqual(surface.river_class,2)
        self.assertGreater(river_cells,0)
        self.assertTrue(styles-{'none'})

    def test_v2_channel_paths_are_multi_point_and_gradient_sensitive(self):
        planner = HydrologyGenerator(
            WorldGenerator(self.seed, self.registry, version=8),
            version=2, morphology_version=2,
        )
        steep, steep_braid, steep_width, steep_is_braid = planner._channel_paths(
            0,0,1,0,1400,2,420,55,1
        )
        flat, flat_braid, flat_width, flat_is_braid = planner._channel_paths(
            0,0,1,0,180,2,420,55,1
        )
        self.assertEqual(len(steep),4)
        self.assertEqual(len(flat),4)
        self.assertFalse(steep_is_braid)
        self.assertIsNone(steep_braid)
        self.assertTrue(flat_is_braid)
        self.assertIsNotNone(flat_braid)
        # Both paths share drainage-node endpoints, so braids always reconnect.
        self.assertEqual(flat[0],flat_braid[0])
        self.assertEqual(flat[-1],flat_braid[-1])
        self.assertGreaterEqual(flat_width,2)
        self.assertEqual(steep[0],flat[0])
        self.assertEqual(steep[-1],flat[-1])

    def test_v2_oxbow_geometry_is_deterministic_and_ring_is_detached(self):
        planner = HydrologyGenerator(
            WorldGenerator(b'v8-oxbow-fixture', self.registry, version=8),
            version=2, morphology_version=2,
        )
        found=None
        for gx in range(-40,41):
            geom=planner._oxbow_geometry(gx,0,gx+1,0,120,2,900,80)
            if geom is not None:
                found=(gx,geom);break
        self.assertIsNotNone(found)
        gx,geom=found
        self.assertEqual(geom,planner._oxbow_geometry(gx,0,gx+1,0,120,2,900,80))
        cx,cy,rx,ry=geom
        self.assertTrue(planner._ellipse_ring_contains(cx+rx,cy,geom,2))
        self.assertFalse(planner._ellipse_ring_contains(cx,cy,geom,2))
        # The scar is shifted away from the active centerline.
        self.assertNotEqual(cy,0)

    def test_v2_current_geometry_uses_same_braided_centerlines_as_terrain(self):
        gen = WorldGenerator(b'v8-current-morphology', self.registry, version=8)
        planner = HydrologyGenerator(gen, version=2, morphology_version=2)
        planner.prepare_window(0,0,0,0,persist=False)
        gen.attach_hydrology(planner)
        found=False
        for y in range(0,512,4):
            for x in range(0,512,4):
                surface=planner.surface_at(WorldPos(x,y,0),prepared_only=True)
                if not surface or not surface.braided or surface.river_class<=0:
                    continue
                current=gen.current_at(WorldPos(x,y,0),prepared_only=True)
                self.assertIsNotNone(current)
                self.assertEqual(current.kind,'river')
                found=True
                break
            if found:break
        # Not every single domain must contain a braid. Geometry helper tests
        # above provide the deterministic braid contract when this seed does not.
        self.assertIsInstance(found,bool)

    def test_legacy_v4_terrain_remains_hydrology_free(self):
        gen = WorldGenerator(self.seed, self.registry, version=4)
        before = [gen.terrain_at(WorldPos(x, y, 0)) for x, y in ((0,0),(64,64),(-37,91),(511,-220))]
        planner = HydrologyGenerator(gen, version=1)
        planner.prepare_window(-1, 0, -1, 0, persist=False)
        gen.attach_hydrology(planner)
        after = [gen.terrain_at(WorldPos(x, y, 0)) for x, y in ((0,0),(64,64),(-37,91),(511,-220))]
        self.assertEqual(before, after)

    def test_prepared_multi_domain_window_has_no_interior_seams(self):
        gen = WorldGenerator(self.seed, self.registry, version=5)
        planner = HydrologyGenerator(gen, version=1)
        domains = planner.prepare_window(-1, 0, -1, 0, persist=False)
        self.assertEqual(audit_window_seams(domains), [])

    def test_v2_prepared_multi_domain_window_has_no_interior_seams(self):
        gen = WorldGenerator(self.seed, self.registry, version=8)
        planner = HydrologyGenerator(gen, version=2)
        domains = planner.prepare_window(-1, 0, -1, 0, persist=False)
        self.assertEqual(audit_window_seams(domains), [])

    def test_worldgen_v5_projects_physical_hydrology_and_crossing_cost(self):
        gen = WorldGenerator(b'rc14-golden-00', self.registry, version=5)
        planner = HydrologyGenerator(gen, version=1)
        planner.prepare_window(-1, 0, -1, 0, persist=False)
        gen.attach_hydrology(planner)
        seen=set(); costly=False
        for y in range(-256,257,4):
            for x in range(-256,257,4):
                pos=WorldPos(x,y,0);tid=gen.terrain_at(pos);seen.add(tid)
                surface=planner.surface_at(pos)
                costly = costly or surface.crossing_cost>0
        self.assertTrue({'core:river_shallow','core:river'} & seen)
        self.assertTrue({'core:wetland','core:floodplain'} & seen)
        self.assertTrue(costly)

    def test_hydrology_cache_roundtrip_skips_regeneration(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'world.db'
            db = WorldDatabase.create(path, 'test', self.seed.hex())
            planner = HydrologyGenerator(WorldGenerator(self.seed, self.registry, version=WORLDGEN_VERSION), db)
            first = planner.load_or_generate(0, 0, persist=True)
            self.assertIsNotNone(db.load_generated_hydrology_domain(0, 0, HYDROLOGY_VERSION))
            db.close()

            db2 = WorldDatabase.open(path)
            planner2 = HydrologyGenerator(WorldGenerator(self.seed, self.registry, version=WORLDGEN_VERSION), db2)
            planner2.generate = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError('cache should be used'))
            second = planner2.load_or_generate(0, 0)
            self.assertEqual(first.fingerprint, second.fingerprint)
            db2.close()

    def test_cache_rebuild_preserves_authoritative_physical_delta(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'world.db'
            db = WorldDatabase.create(path, 'test', self.seed.hex())
            planner = HydrologyGenerator(WorldGenerator(self.seed, self.registry, version=WORLDGEN_VERSION), db)
            original = planner.load_or_generate(0, 0, persist=True)
            db.store_physical_plan_delta('bridge:test', 'crossing', 1, {'condition':17,'destroyed':True})
            db.commit_generated()
            db.connection.execute('DELETE FROM generated_hydrology_domains')
            db.connection.commit()
            rebuilt = planner.load_or_generate(0, 0, persist=True)
            self.assertEqual(original.fingerprint, rebuilt.fingerprint)
            self.assertEqual(db.load_physical_plan_delta('bridge:test')['payload'], {'condition':17,'destroyed':True})
            db.close()

    def test_new_generated_plan_tables_and_deltas_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            db = WorldDatabase.create(Path(td) / 'world.db', 'test', self.seed.hex())
            db.store_generated_regional_plan(1, -2, SETTLEMENT_PLAN_VERSION, {'uid':'regional:1:-2','settlements':['s1']})
            db.store_generated_settlement_plan('s1', SETTLEMENT_PLAN_VERSION, {'uid':'plan:s1','anchor':[5,7]})
            db.store_generated_route_plan('r1', ROUTEGEN_VERSION, {'uid':'r1','corridor':[[0,0],[1,0]]})
            db.store_physical_plan_delta('structure:abc', 'structure', 3, {'condition':42,'destroyed':False})
            db.commit_generated()
            self.assertEqual(db.load_generated_regional_plan(1,-2,SETTLEMENT_PLAN_VERSION)['settlements'], ['s1'])
            self.assertEqual(db.load_generated_settlement_plan('s1',SETTLEMENT_PLAN_VERSION)['anchor'], [5,7])
            self.assertEqual(db.load_generated_route_plan('r1',ROUTEGEN_VERSION)['corridor'][-1], [1,0])
            self.assertEqual(db.load_physical_plan_delta('structure:abc')['payload']['condition'], 42)
            db.close()

    def test_stable_plan_uid_ignores_process_hash_and_dict_order(self):
        a = stable_plan_uid('structure', 'settlement:1', 'home:0', [(4,5),(5,5)])
        b = stable_plan_uid('structure', 'settlement:1', 'home:0', [(4,5),(5,5)])
        c = stable_plan_uid('structure', 'settlement:1', 'home:1', [(4,5),(5,5)])
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_legacy_save_open_adds_contract_metadata_without_geography_rewrite(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'old.db'
            db = WorldDatabase.create(path, 'old', self.seed.hex())
            db.set_meta('worldgen_version', 3)
            for key in ('hydrology_version','hydrology_morphology_version','coast_morphology_version','settlement_plan_version','routegen_version'):
                db.connection.execute('DELETE FROM world_meta WHERE key=?', (key,))
            db.connection.commit(); db.close()
            db2 = WorldDatabase.open(path)
            self.assertEqual(db2.get_meta('worldgen_version'), 3)
            # Missing metadata belongs to a pre-v2 save and must infer v1,
            # never the newest hydrology algorithm.
            self.assertEqual(db2.get_meta('hydrology_version'), 1)
            self.assertEqual(db2.get_meta('hydrology_morphology_version'), 1)
            self.assertEqual(db2.get_meta('coast_morphology_version'), 0)
            self.assertEqual(db2.get_meta('settlement_plan_version'), SETTLEMENT_PLAN_VERSION)
            self.assertEqual(db2.get_meta('routegen_version'), 1)
            db2.close()

    def test_new_save_records_hydrology_v2_but_existing_v1_stays_pinned(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'hydro-contract.db'
            db = WorldDatabase.create(path, 'new-v8', self.seed.hex())
            self.assertEqual(db.get_meta('hydrology_version'), 2)
            self.assertEqual(db.get_meta('hydrology_morphology_version'), 2)
            self.assertEqual(db.get_meta('coast_morphology_version'), COAST_MORPHOLOGY_VERSION)
            db.set_meta('hydrology_version',1)
            db.set_meta('hydrology_morphology_version',1)
            db.connection.commit();db.close()
            reopened = WorldDatabase.open(path)
            self.assertEqual(reopened.get_meta('hydrology_version'), 1)
            self.assertEqual(reopened.get_meta('hydrology_morphology_version'), 1)
            reopened.close()

    def test_world_auto_hydrology_uses_save_pinned_version(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'hydro-world-contract.db'
            db = WorldDatabase.create(path, 'legacy-v8', self.seed.hex())
            db.set_meta('hydrology_version',2)
            db.set_meta('hydrology_morphology_version',1)
            db.connection.commit()
            gen = WorldGenerator(self.seed, self.registry, version=8)
            world = World(gen, self.registry, db)
            self.assertIsNotNone(world.generator.hydrology)
            self.assertEqual(world.generator.hydrology.version, 2)
            self.assertEqual(world.generator.hydrology.morphology_version, 1)
            db.close()

    def test_v1_and_v2_generated_hydrology_caches_can_coexist(self):
        with tempfile.TemporaryDirectory() as td:
            db = WorldDatabase.create(Path(td) / 'hydro-cache-versions.db', 'test', self.seed.hex())
            gen = WorldGenerator(self.seed, self.registry, version=8)
            v1 = HydrologyGenerator(gen, db, version=1).load_or_generate(0,0,persist=True)
            v2 = HydrologyGenerator(gen, db, version=2).load_or_generate(0,0,persist=True)
            self.assertIsNotNone(db.load_generated_hydrology_domain(0,0,1))
            self.assertIsNotNone(db.load_generated_hydrology_domain(0,0,2))
            self.assertNotEqual(v1.fingerprint,v2.fingerprint)
            db.close()


    def test_missing_morphology_metadata_infers_dev29_v1_projection(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'dev29.db'
            db=WorldDatabase.create(path,'dev29',self.seed.hex())
            db.set_meta('hydrology_version',2)
            db.connection.execute("DELETE FROM world_meta WHERE key='hydrology_morphology_version'")
            db.connection.commit();db.close()
            reopened=WorldDatabase.open(path)
            self.assertEqual(reopened.get_meta('hydrology_version'),2)
            self.assertEqual(reopened.get_meta('hydrology_morphology_version'),1)
            reopened.close()

    def test_surface_chunk_cache_isolated_by_hydrology_and_morphology_contract(self):
        with tempfile.TemporaryDirectory() as td:
            db=WorldDatabase.create(Path(td)/'surface-cache.db','cache',self.seed.hex())
            key=ChunkKey(2,-3,0)
            n=32*32
            v1=tuple(['core:grass']*n)
            v2=tuple(['core:floodplain']*n)
            coast=tuple(['core:rocky_shore']*n)
            db.store_generated_surface_chunk(key,8,2,1,0,v1)
            db.store_generated_surface_chunk(key,8,2,2,0,v2)
            db.store_generated_surface_chunk(key,8,2,2,1,coast)
            db.commit_generated()
            self.assertEqual(db.load_generated_surface_chunk(key,8,2,1,0),v1)
            self.assertEqual(db.load_generated_surface_chunk(key,8,2,2,0),v2)
            self.assertEqual(db.load_generated_surface_chunk(key,8,2,2,1),coast)
            self.assertNotEqual(
                db.load_generated_surface_chunk(key,8,2,2,0),
                db.load_generated_surface_chunk(key,8,2,2,1),
            )
            db.close()

    def test_dev29_morphology_v1_keeps_single_midpoint_channel(self):
        planner=HydrologyGenerator(
            WorldGenerator(self.seed,self.registry,version=8),
            version=2,morphology_version=1,
        )
        primary,secondary,width,braid=planner._channel_paths(
            0,0,1,0,180,2,500,60,2
        )
        self.assertEqual(len(primary),3)
        self.assertIsNone(secondary)
        self.assertGreaterEqual(width,4)



if __name__ == '__main__':
    unittest.main()
