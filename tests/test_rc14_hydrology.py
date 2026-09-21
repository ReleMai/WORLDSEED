from __future__ import annotations

import tempfile
import unittest
from hashlib import blake2b
from pathlib import Path

from worldseed.config import (
    DATA_DIR, HYDROLOGY_VERSION, ROUTEGEN_VERSION, SETTLEMENT_PLAN_VERSION, WORLDGEN_VERSION,
)
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.persistence.database import WorldDatabase
from worldseed.world.generator import WorldGenerator
from worldseed.world.hydrology import HydrologyGenerator, audit_domain, audit_window_seams, HYDROLOGY_ALGORITHM
from worldseed.world.regional_plan import stable_plan_uid


class RC14HydrologyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)
        cls.seed = b'rc14-hydrology-tests'

    def _hydro(self):
        return HydrologyGenerator(WorldGenerator(self.seed, self.registry, version=WORLDGEN_VERSION))

    def test_phase3_contract_versions_activate_worldgen_v5(self):
        self.assertEqual(HYDROLOGY_VERSION, 1)
        self.assertEqual(SETTLEMENT_PLAN_VERSION, 1)
        self.assertEqual(ROUTEGEN_VERSION, 1)
        self.assertEqual(WORLDGEN_VERSION, 8)
        self.assertTrue(HYDROLOGY_ALGORITHM.startswith('rc14-phase3'))

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

    def test_legacy_v4_terrain_remains_hydrology_free(self):
        gen = WorldGenerator(self.seed, self.registry, version=4)
        before = [gen.terrain_at(WorldPos(x, y, 0)) for x, y in ((0,0),(64,64),(-37,91),(511,-220))]
        planner = HydrologyGenerator(gen)
        planner.prepare_window(-1, 0, -1, 0, persist=False)
        gen.attach_hydrology(planner)
        after = [gen.terrain_at(WorldPos(x, y, 0)) for x, y in ((0,0),(64,64),(-37,91),(511,-220))]
        self.assertEqual(before, after)

    def test_prepared_multi_domain_window_has_no_interior_seams(self):
        gen = WorldGenerator(self.seed, self.registry, version=5)
        planner = HydrologyGenerator(gen)
        domains = planner.prepare_window(-1, 0, -1, 0, persist=False)
        self.assertEqual(audit_window_seams(domains), [])

    def test_worldgen_v5_projects_physical_hydrology_and_crossing_cost(self):
        gen = WorldGenerator(b'rc14-golden-00', self.registry, version=5)
        planner = HydrologyGenerator(gen)
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
            self.assertEqual(db.load_generated_regional_plan(1,-2,1)['settlements'], ['s1'])
            self.assertEqual(db.load_generated_settlement_plan('s1',1)['anchor'], [5,7])
            self.assertEqual(db.load_generated_route_plan('r1',1)['corridor'][-1], [1,0])
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
            for key in ('hydrology_version','settlement_plan_version','routegen_version'):
                db.connection.execute('DELETE FROM world_meta WHERE key=?', (key,))
            db.connection.commit(); db.close()
            db2 = WorldDatabase.open(path)
            self.assertEqual(db2.get_meta('worldgen_version'), 3)
            self.assertEqual(db2.get_meta('hydrology_version'), 1)
            self.assertEqual(db2.get_meta('settlement_plan_version'), 1)
            self.assertEqual(db2.get_meta('routegen_version'), 1)
            db2.close()


if __name__ == '__main__':
    unittest.main()
