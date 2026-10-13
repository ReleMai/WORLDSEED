import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from worldseed.core.coords import WorldPos, ChunkKey
from worldseed.persistence.database import WorldDatabase
from worldseed.persistence.validation import validate_sim_state
from worldseed.sim.engine import Simulation
from worldseed.systems.discovery import DiscoveryTiles, DiscoverySet, ChunkCells
from worldseed.systems.state import LivingWorldState
from worldseed.world.atlas import AtlasSnapshot, _discovered_cells_in_view


class CompactDiscoveryTests(unittest.TestCase):
    def test_preserves_more_than_old_cap_across_database_round_trip(self):
        tokens = [f'{x},{y},0' for y in range(350) for x in range(400)]
        state = LivingWorldState(discovered_tiles=tokens)
        raw = state.to_dict()
        self.assertEqual(raw['discovered_tiles'], [])
        self.assertLess(len(json.dumps(raw['discovered_chunks'])), len(json.dumps(tokens)) // 10)
        with tempfile.TemporaryDirectory() as folder:
            db = WorldDatabase.create(Path(folder) / 'memory.db', 'Discovery', b'compact'.hex())
            try:
                db.save_state(turn=0, tile_deltas={}, player_id=1, position=WorldPos(0,0,0), inventory={}, sim_state=raw)
                self.assertEqual(db.verify(), [])
                restored = LivingWorldState.from_dict(db.load_sim_state())
                self.assertEqual(len(restored.discovered_tiles), 140000)
                self.assertIn(tokens[0], restored.discovered_tiles)
                self.assertIn(tokens[-1], restored.discovered_tiles)
                self.assertEqual(set(restored.discovered_tiles), set(tokens))
            finally:
                db.close()

    def test_negative_and_multilevel_cells_are_exact(self):
        tokens = ['-33,-33,0', '-32,-32,0', '-1,-1,0', '0,0,0', '31,31,0', '32,32,0', '-1,32,-2', '1,2,3']
        cells = DiscoveryTiles(tokens)
        rebuilt = DiscoveryTiles.from_chunks(cells.to_chunks())
        self.assertEqual(set(rebuilt), set(tokens))
        self.assertNotIn('-2,-1,0', rebuilt)
        self.assertNotIn('-1,-1,-1', rebuilt)
        self.assertEqual(rebuilt.surface_chunks, {(-2,-2), (-1,-1), (0,0), (1,1)})
        self.assertEqual(set(rebuilt.surface_cells[(-1,-1)]), {0, 1023})

    def test_legacy_import_and_uncapped_export(self):
        original = {'discovered_tiles': [f'{x},-1,-1' for x in range(120002)]}
        before = deepcopy(original)
        state = LivingWorldState.from_dict(original)
        self.assertEqual(original, before)
        self.assertEqual(len(state.discovered_tiles.export_legacy()), 120002)
        self.assertEqual(set(LivingWorldState.from_dict(state.to_dict()).discovered_tiles), set(original['discovered_tiles']))

    def test_mixed_legacy_and_current_fields_are_unioned_without_aliasing(self):
        raw = {'discovered_format_version': 1, 'discovered_chunks': {'-1,-1,0': '1'}, 'discovered_tiles': ['0,0,0']}
        before = deepcopy(raw)
        state = LivingWorldState.from_dict(raw)
        self.assertEqual(set(state.discovered_tiles), {'-32,-32,0','0,0,0'})
        state.discovered_tiles.append('1,0,0')
        self.assertEqual(raw, before)
        self.assertEqual(LivingWorldState.from_dict(None).discovered_tiles, [])

    def test_corrupt_or_unknown_compact_memory_is_rejected_and_verified(self):
        for chunks, version in (({},2), ({},True), ({},None), ([],1), ({'bad':'1'},1), ({'01,0,0':'1'},1), ({'0,0,0':'z'},1), ({'0,0,0':'0'},1), ({'0,0,0':'1'*257},1), ({'0,0,0':4},1)):
            with self.subTest(chunks=chunks, version=version):
                raw = {'discovered_chunks': chunks, 'discovered_format_version': version}
                with self.assertRaises(ValueError):
                    LivingWorldState.from_dict(raw)
                self.assertTrue(validate_sim_state(raw))

    def test_additions_are_incremental_without_history_iteration_or_index_rebuild(self):
        cells = DiscoveryTiles(f'{x},0,0' for x in range(120005))
        sim = Simulation.__new__(Simulation)
        sim.state = LivingWorldState(discovered_tiles=cells)
        sim._discovered_tile_set = DiscoverySet(cells)
        sim._discovered_surface_chunks = cells.surface_chunks
        sim._discovered_surface_cells_by_chunk = cells.surface_cells
        first = cells.surface_cells[(0,0)]
        chunks_identity = cells._chunks
        with patch.object(DiscoveryTiles, '__iter__', side_effect=AssertionError('history scan')):
            sim._record_discovered_tiles({'120005,0,0','120005,0,0','-1,-1,0','1,1,-3'})
            self.assertEqual(len(sim.discovered_tiles_set), 120008)
            self.assertIn('0,0,0', sim.discovered_tiles_set)
            self.assertIn('120005,0,0', sim.discovered_tiles_set)
        self.assertIs(cells._chunks, chunks_identity)
        self.assertIs(cells.surface_cells[(0,0)], first)
        self.assertIs(sim.discovered_surface_cells_by_chunk, cells.surface_cells)
        self.assertIsInstance(cells.surface_cells[(0,0)], ChunkCells)

    def test_set_compatibility_and_clear_keep_surface_indexes_consistent(self):
        cells = DiscoveryTiles(['-1,-1,0', '0,0,0'])
        view = DiscoverySet(cells)
        view.update(['1,0,0', '1,0,0'])
        self.assertEqual(len(view), 3)
        self.assertEqual(set({'1,0,0','9,9,0'} - view), {'9,9,0'})
        view.discard('0,0,0')
        self.assertNotIn(0, cells.surface_cells[(0,0)])
        view.clear()
        self.assertEqual(cells, [])
        self.assertEqual(cells.surface_cells, {})
        self.assertEqual(cells.surface_chunks, set())

    def test_compact_set_algebra_returns_repeatable_independent_values(self):
        indices = ChunkCells(5)
        for result, expected in ((indices & {0}, {0}), (indices - {2}, {0}), (indices | {1}, {0,1,2})):
            self.assertEqual(set(result), expected)
            self.assertEqual(set(result), expected)
            self.assertEqual(len(result), len(expected))
        cells = DiscoveryTiles(['0,0,0', '1,0,0'])
        view = DiscoverySet(cells)
        for result, expected in ((view & {'0,0,0'}, {'0,0,0'}), (view - {'0,0,0'}, {'1,0,0'}), (view | {'2,0,0'}, {'0,0,0','1,0,0','2,0,0'})):
            self.assertEqual(set(result), expected)
            self.assertEqual(set(result), expected)
            result.add('3,0,0')
            self.assertNotIn('3,0,0', cells)
        self.assertEqual(view.difference({'0,0,0'}), {'1,0,0'})
        self.assertTrue(view.issuperset({'0,0,0'}))

    def test_snapshot_deepcopy_is_independent_and_compact(self):
        cells = DiscoveryTiles(['0,0,0','1,0,0'])
        snapshot = deepcopy(LivingWorldState(discovered_tiles=cells).to_dict())
        cells.append('2,0,0')
        self.assertEqual(set(LivingWorldState.from_dict(snapshot).discovered_tiles), {'0,0,0','1,0,0'})
        copy = deepcopy(cells)
        copy.append('3,0,0')
        self.assertNotIn('3,0,0', cells)

    def test_membership_cache_is_bounded_and_tracks_newly_known_and_removed_cells(self):
        from worldseed.systems.discovery import MEMBERSHIP_CACHE_LIMIT
        cells = DiscoveryTiles(['0,0,0'])
        self.assertNotIn('1,0,0', cells)
        cells.append('1,0,0')
        self.assertIn('1,0,0', cells)
        cells.discard('1,0,0')
        self.assertNotIn('1,0,0', cells)
        for x in range(MEMBERSHIP_CACHE_LIMIT+10):
            self.assertNotIn(f'{x},4,0', cells)
        self.assertEqual(len(cells._membership_cache), MEMBERSHIP_CACHE_LIMIT)
        self.assertIn('0,0,0', cells)
        with patch('worldseed.systems.discovery._coordinates', side_effect=AssertionError('reparsed cached cell')):
            self.assertIn('0,0,0', cells)
        cells.clear()
        self.assertNotIn('0,0,0', cells)

    def test_atlas_queries_only_view_chunks_and_remain_observational(self):
        class BoundedIndex(dict):
            def items(self):
                raise AssertionError('atlas scanned lifetime discovery chunks')
        cells = DiscoveryTiles(['-1,-1,0','0,0,0','120000,0,0','0,0,-1'])
        sim = SimpleNamespace(discovered_surface_cells_by_chunk=BoundedIndex(cells.surface_cells), player_pos=WorldPos(0,0,0))
        before = cells.to_chunks()
        found = _discovered_cells_in_view(sim, AtlasSnapshot(-64,-64,128))
        self.assertEqual(set(found), {ChunkKey(-1,-1,0),ChunkKey(0,0,0)})
        self.assertEqual(found[ChunkKey(-1,-1,0)], {1023})
        self.assertEqual(found[ChunkKey(0,0,0)], {0})
        self.assertEqual(cells.to_chunks(), before)


if __name__ == '__main__':
    unittest.main()
