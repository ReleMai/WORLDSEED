"""Resident-only terrain/resource reads used by live GPU scene capture."""
from __future__ import annotations

from collections import OrderedDict
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from worldseed.config import CHUNK_SIZE, DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos, split_world
from worldseed.systems.resources import ResourceSystem
from worldseed.systems.state import pos_key
from worldseed.world.chunk import Chunk
from worldseed.world.world import World


class PreparedGpuReadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=ContentRegistry.load(DATA_DIR)

    def setUp(self):
        self.state=SimpleNamespace(clock_minute=0,structures={},containers={},
                                  crops={},soils={},resource_depletion={})
        self.world=World(SimpleNamespace(version=1),self.registry,object(),
                         cache_chunks=4,auto_hydrology=False)
        self.world.cache.loader=lambda _:self.fail('observational read loaded terrain')
        self.resources=ResourceSystem(self.state,self.registry,b'prepared-gpu',
                                      self.world,version=5)
        self.pos=WorldPos(-2,3,0)
        self.prepare(self.pos,'core:oak_tree')

    def prepare(self,pos,fid,terrain='core:forest',season=None):
        key,lx,ly=split_world(pos)
        chunk=self.world.cache.peek(key)
        if chunk is None:chunk=Chunk.empty(key)
        chunk.set(lx,ly,self.registry.terrain_index(terrain))
        self.world.cache.put(key,chunk)
        season=season or self.resources._season()
        cache_key=(key.x,key.y,season)
        values=list(self.resources._feature_chunk_cache.get(cache_key,
                    (None,)*(CHUNK_SIZE*CHUNK_SIZE)))
        values[ly*CHUNK_SIZE+lx]=fid
        self.resources._cache_feature_chunk(cache_key,tuple(values))

    def test_resident_terrain_read_preserves_order_and_live_delta(self):
        other=WorldPos(65,4,0)
        self.prepare(other,'core:pine_tree')
        keys=tuple(self.world.cache._chunks)
        tile=self.world.prepared_tile_at(self.pos)
        self.assertEqual((tile.position,tile.terrain_id),(self.pos,'core:forest'))
        self.assertEqual(tuple(self.world.cache._chunks),keys)
        self.world.set_terrain(self.pos,'core:grass')
        self.assertEqual(self.world.prepared_tile_at(self.pos).terrain_id,'core:grass')
        self.assertIsNone(self.world.prepared_tile_at(WorldPos(500,500,0)))

    def test_prepared_resource_reads_never_load_generate_or_reorder(self):
        self.prepare(WorldPos(65,4,0),'core:pine_tree')
        terrain_before=tuple(self.world.cache._chunks)
        resources_before=OrderedDict(self.resources._feature_chunk_cache)
        misses_before=set(self.resources._feature_chunk_misses)
        with (
            patch.object(self.world,'tile_at',side_effect=AssertionError('tile_at')),
            patch.object(self.resources,'_load_prepared_feature_chunk',side_effect=AssertionError('resource load')),
            patch.object(self.resources,'_raw_feature',side_effect=AssertionError('raw placement')),
            patch.object(self.resources,'_shoreline_reed',side_effect=AssertionError('shore reeds')),
        ):
            view=self.resources.prepared_feature_at(self.pos)
            self.assertEqual((view.feature_id,view.stage),('core:oak_tree','mature'))
            self.assertIsNone(self.resources.prepared_feature_at(WorldPos(1000,1000,0)))
        self.assertEqual(tuple(self.world.cache._chunks),terrain_before)
        self.assertEqual(self.resources._feature_chunk_cache,resources_before)
        self.assertEqual(self.resources._feature_chunk_misses,misses_before)
        self.assertEqual((self.resources._raw_cache,self.resources._structural_cache),({},{}))
        self.assertEqual(self.state.resource_depletion,{})

    def test_missing_season_or_terrain_and_empty_cells_stay_unknown(self):
        self.resources._feature_chunk_cache.clear()
        self.assertIsNone(self.resources.prepared_feature_at(self.pos))
        self.prepare(self.pos,'core:oak_tree',season='winter')
        self.assertIsNone(self.resources.prepared_feature_at(self.pos))
        self.prepare(self.pos,None)
        self.assertIsNone(self.resources.prepared_feature_at(self.pos))
        self.prepare(self.pos,'core:oak_tree')
        key,_,_=split_world(self.pos)
        self.world.cache._chunks.pop(key)
        self.assertIsNone(self.resources.prepared_feature_at(self.pos))
        self.assertIsNone(self.resources.prepared_feature_at(WorldPos(-2,3,-1)))

    def test_depletion_and_regrowth_match_gameplay_queries(self):
        self.state.resource_depletion[pos_key(self.pos.x,self.pos.y,self.pos.z)]=0
        self.resources._base_feature=lambda pos,minute=None:'core:oak_tree'
        for minute,stage in ((0,'stump'),(45*1440,'sapling'),(240*1440,'mature')):
            with self.subTest(minute=minute):
                season=self.resources._season(minute)
                self.prepare(self.pos,'core:oak_tree',season=season)
                prepared=self.resources.prepared_feature_at(self.pos,minute)
                self.assertEqual(prepared.stage,stage)
                self.assertEqual(prepared,self.resources.feature_at(self.pos,minute))

    def test_non_tree_depletion_matches_gameplay_without_reed_generation(self):
        self.prepare(self.pos,'core:reed_bed',terrain='core:riverbank')
        self.state.resource_depletion[pos_key(self.pos.x,self.pos.y,self.pos.z)]=0
        self.resources._base_feature=lambda pos,minute=None:'core:reed_bed'
        for minute,stage in ((0,'depleted'),(9*1440,'mature')):
            self.assertEqual(self.resources.prepared_feature_at(self.pos,minute).stage,stage)
            self.assertEqual(self.resources.prepared_feature_at(self.pos,minute),
                             self.resources.feature_at(self.pos,minute))

    def test_authoritative_occupancy_clearance_and_terrain_suppress_resources(self):
        pk=pos_key(self.pos.x,self.pos.y,self.pos.z)
        for mapping in ('structures','containers','crops','soils'):
            with self.subTest(mapping=mapping):
                getattr(self.state,mapping)[pk]=object()
                self.assertIsNone(self.resources.prepared_feature_at(self.pos))
                getattr(self.state,mapping).clear()
        self.resources.attach_settlement_physicalization(
            SimpleNamespace(clears_natural_feature=lambda _:True))
        self.assertIsNone(self.resources.prepared_feature_at(self.pos))
        self.resources.attach_settlement_physicalization(None)
        self.world.set_terrain(self.pos,'core:water')
        self.assertIsNone(self.resources.prepared_feature_at(self.pos))


if __name__=='__main__':unittest.main()
