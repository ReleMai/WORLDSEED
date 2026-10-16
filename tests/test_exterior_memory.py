"""Last-observed exterior knowledge survives saves without hidden live reads."""
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import tempfile
from unittest import TestCase
from unittest.mock import patch

from tools.reference_scene_fixtures import build_fixture
from worldseed.config import DATA_DIR, CHUNK_SIZE
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos, split_world
from worldseed.persistence.validation import validate_sim_state
from worldseed.presentation.live_gpu_scene import capture_live_scene
from worldseed.presentation.gpu_exterior_memory import (
    BASE_MEMORY_CHUNK_LIMIT, _base_chunks, legacy_base_terrain)
from worldseed.presentation.worldspace import WorldCamera, WorldFoot
from worldseed.sim.engine import Simulation
from worldseed.systems.building_shells import BuildingShell
from worldseed.systems.exterior_memory import (ExteriorMemory, MAX_CELL_OBJECTS,
    MAX_OBSERVED_CELLS, RememberedCell, RememberedObject, RememberedShell, observe_exterior)
from worldseed.systems.state import GroundPile, LivingWorldState, RoofState, pos_key
import tests.test_live_gpu_scene as live_tests


def unexpected(*args, **kwargs):
    raise AssertionError('hidden current authority must not be queried')


class ExteriorMemoryTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)

    @contextmanager
    def fixture(self, name='forest'):
        with tempfile.TemporaryDirectory() as directory:
            fixture = build_fixture(name,self.registry,Path(directory),width=640,height=480,zoom=28)
            try:
                yield fixture
            finally:
                fixture.close()

    def camera(self, sim):
        p = sim.player_pos
        return WorldCamera(WorldFoot(p.x+.5,p.y+.5,p.z),640,480,28)

    feature = live_tests.LiveGpuSceneContracts.feature

    def test_optional_save_roundtrip_is_detached_and_old_save_learns_nothing_hidden(self):
        state = LivingWorldState()
        state.exterior_memory.remember((-1,33,0),RememberedCell('core:forest',
            ('core:oak_tree','stump'),(RememberedObject('pile:0:-1:33','pile','core:stone'),)))
        raw = state.to_dict()
        restored = LivingWorldState.from_dict(raw)
        self.assertEqual(restored.exterior_memory.to_dict(),state.exterior_memory.to_dict())
        raw['exterior_memory']['chunks']['-1,1,0'][0][1] = 'changed'
        self.assertEqual(restored.exterior_memory.get((-1,33,0)).terrain_id,'core:forest')
        self.assertIsNone(LivingWorldState.from_dict({'clock_minute':500}).exterior_memory.get((-1,33,0)))
        restored.exterior_memory.remember((-1,33,0),RememberedCell('core:grassland'))
        self.assertEqual(state.exterior_memory.get((-1,33,0)).terrain_id,'core:forest')

    def test_shared_shell_revisions_prune_without_forgetting_still_observed_cells(self):
        shell = BuildingShell('house','village','residence','core:house',((0,0),(1,0)),
            (0,0),'door',0,'rectangular',(0,0,1,0))
        old = RememberedShell(shell)
        new = RememberedShell(replace(shell,content_id='core:ruin'))
        memory = ExteriorMemory()
        memory.remember((0,0,0),RememberedCell(shell_key='old'),old)
        memory.remember((1,0,0),RememberedCell(shell_key='old'),old)
        memory.remember((0,0,0),RememberedCell(shell_key='new'),new)
        self.assertEqual(memory.shell('old'),old)
        self.assertEqual(memory.get((1,0,0)).shell_key,'old')
        memory.remember((1,0,0),RememberedCell())
        self.assertIsNone(memory.shell('old'))
        self.assertEqual(memory.shell('new'),new)
        raw = memory.to_dict()
        self.assertEqual(ExteriorMemory.from_dict(raw).to_dict(),raw)
        self.assertEqual(sum(len(cells) for cells in memory._chunks.values()),2)

    def test_last_seen_state_survives_verified_database_checkpoint(self):
        with self.fixture('camp') as fixture:
            sim = fixture.sim
            observe_exterior(sim,{tuple(map(int,token.split(','))) for token in sim.visible_tiles_set})
            before = sim.state.exterior_memory.to_dict()
            self.assertTrue(before['chunks'])
            fixture.db.save_state(turn=sim.turn,tile_deltas={},player_id=sim.player_id,
                position=sim.player_pos,inventory={},sim_state=sim.state.to_dict())
            self.assertEqual(fixture.db.verify(),[])
            loaded = LivingWorldState.from_dict(fixture.db.load_sim_state())
            self.assertEqual(loaded.exterior_memory.to_dict(),before)

    def test_observation_and_cell_budgets_reject_unbounded_or_corrupt_data(self):
        memory = ExteriorMemory()
        prop = RememberedObject('x','pile','core:stone')
        with self.assertRaisesRegex(ValueError,'bounded exterior'):
            memory.remember((0,0,0),RememberedCell(objects=(prop,)*(MAX_CELL_OBJECTS+1)))
        with self.assertRaisesRegex(ValueError,'bounded sight'):
            observe_exterior(None,[(0,0,0)]*(MAX_OBSERVED_CELLS+1))
        with self.assertRaisesRegex(ValueError,'format'):
            ExteriorMemory.from_dict({'version':99})
        self.assertTrue(any('exterior appearance memory' in issue
            for issue in validate_sim_state({'exterior_memory':{'version':99}})))
        with self.assertRaisesRegex(ValueError,'cell index'):
            ExteriorMemory.from_dict({'version':1,'chunks':{'0,0,0':[[1024,'',None,[],'',None]]}})

    def test_hidden_harvest_and_pile_changes_remain_stale_until_exact_cell_seen_again(self):
        with self.fixture() as fixture:
            sim = fixture.sim
            tree,pile = (256,256,0),(257,256,0)
            self.feature(sim,tree,'core:oak_tree')
            sim.state.ground_piles[pos_key(*pile)] = GroundPile(*pile,{'core:stone':2})
            observe_exterior(sim,{tree,pile})
            sim.state.resource_depletion[pos_key(*tree)] = sim.clock.minute-1
            sim.state.ground_piles[pos_key(*pile)].items.clear()
            sim._visible_tile_set.clear()
            before = fixture.authority_fingerprint()
            with patch.object(sim.world,'prepared_tile_at',unexpected), \
                    patch.object(sim.resources,'prepared_feature_at',unexpected), \
                    patch.object(sim.settlement_physicalization,'shell_at',unexpected), \
                    patch.object(sim.settlement_physicalization,'cell_at',unexpected), \
                    patch.object(sim.building,'roof_at',unexpected):
                snapshot = capture_live_scene(sim,self.camera(sim))
                frame = snapshot.gpu_frame(materials=live_tests.FakeAssets(),registry=self.registry,
                    resource_style=lambda _: {'width':1.3,'height':1.9})
            self.assertEqual(dict(snapshot.remembered_resources)[tree].stage,'mature')
            self.assertEqual([(o.kind,o.content_id) for o in snapshot.remembered_objects],[('pile','core:stone')])
            self.assertEqual((snapshot.actors,snapshot.fires,snapshot.resources,snapshot.objects),((),(),(),()))
            self.assertTrue(any(c.visual_id.startswith('memory:') for c in frame.scenery))
            self.assertEqual(before,fixture.authority_fingerprint())
            observe_exterior(sim,{tree,pile})
            self.assertEqual(sim.state.exterior_memory.get(tree).resource,('core:oak_tree','stump'))
            self.assertEqual(sim.state.exterior_memory.get(pile).objects,())

    def test_production_discovery_is_the_writer_and_render_does_not_warm_old_memory(self):
        with self.fixture() as fixture:
            sim = fixture.sim
            cell = (256,256,0)
            self.feature(sim,cell,'core:oak_tree')
            self.assertIsNone(sim.state.exterior_memory.get(cell))
            capture_live_scene(sim,self.camera(sim))
            self.assertIsNone(sim.state.exterior_memory.get(cell))
            Simulation._discover(sim,sim.player_pos)
            self.assertEqual(sim.state.exterior_memory.get(cell).resource,('core:oak_tree','mature'))
            sim.state.resource_depletion[pos_key(*cell)] = sim.clock.minute-1
            Simulation._discover(sim,sim.player_pos)
            self.assertEqual(sim.state.exterior_memory.get(cell).resource,('core:oak_tree','stump'))

    def test_shell_and_roof_memory_remain_closed_and_never_query_hidden_live_objects(self):
        with self.fixture('village_street') as fixture:
            sim = fixture.sim
            live = capture_live_scene(sim,self.camera(sim))
            building = live.buildings[0]
            observed = set(building.visible_cells)
            self.assertTrue(observed)
            observe_exterior(sim,observed)
            expected = {cell:sim.state.exterior_memory.get(cell) for cell in observed}
            sim._visible_tile_set.clear()
            with patch.object(sim.settlement_physicalization,'shell_at',unexpected), \
                    patch.object(sim.settlement_physicalization,'cell_at',unexpected), \
                    patch.object(sim.world,'prepared_tile_at',unexpected):
                snapshot = capture_live_scene(sim,self.camera(sim))
            self.assertTrue(snapshot.remembered_buildings)
            self.assertEqual(snapshot.remembered_buildings[0].visible_cells,frozenset(observed))
            self.assertFalse(observed & set(dict(snapshot.terrain)))
            self.assertEqual(snapshot.remembered_objects,())
            self.assertEqual(expected,{cell:sim.state.exterior_memory.get(cell) for cell in observed})
        with self.fixture('camp') as fixture:
            sim = fixture.sim
            cell = (256,256,0)
            sim.state.roofs[pos_key(*cell)] = RoofState('core:thatch_roof',*cell)
            sim.state.ground_piles[pos_key(*cell)] = GroundPile(*cell,{'private:treasure':10})
            observe_exterior(sim,{cell})
            sim._visible_tile_set.clear()
            snap = capture_live_scene(sim,self.camera(sim))
            self.assertEqual([o.kind for o in snap.remembered_objects],['roof'])
            self.assertEqual(snap.remembered_resources,())
            self.assertNotIn(cell,dict(snap.terrain))

    def test_distant_memory_is_not_scanned_and_unknown_cells_never_promoted(self):
        with self.fixture() as fixture:
            sim = fixture.sim
            sim.state.exterior_memory.remember((256,256,0),RememberedCell('core:forest'))
            sim.state.exterior_memory.remember((100000,100000,0),RememberedCell('core:forest'))
            sim.state.exterior_memory.remember((257,256,0),RememberedCell('core:forest'))
            sim._visible_tile_set.clear()
            sim._discovered_tile_set = live_tests.MembershipOnly([pos_key(256,256,0)])
            sim.state.exterior_memory._chunks = live_tests.IndexedOnlyDict(sim.state.exterior_memory._chunks)
            before = sim.state.next_uid,sim.clock.minute
            snapshot = capture_live_scene(sim,self.camera(sim))
            self.assertEqual(snapshot.remembered_cells,frozenset({(256,256,0)}))
            self.assertEqual((sim.state.next_uid,sim.clock.minute),before)

    def test_old_discovery_basemap_uses_pinned_base_and_never_hidden_live_deltas_or_objects(self):
        with self.fixture() as fixture:
            sim = fixture.sim
            known,other,unknown = (256,256,0),(257,256,0),(258,256,0)
            key,_,_ = split_world(WorldPos(*known))
            fixture.db.store_generated_chunk(key,sim.world.generator.version,
                ('core:grass',)*(CHUNK_SIZE*CHUNK_SIZE))
            sim.world.set_terrain(WorldPos(*known),'core:rock')
            fixture.db.save_state(turn=sim.turn,tile_deltas={WorldPos(*other):'core:rock'},
                player_id=sim.player_id,position=sim.player_pos,inventory={},sim_state=sim.state.to_dict())
            sim.state.ground_piles[pos_key(*known)] = GroundPile(*known,{'private:unseen':1})
            sim._visible_tile_set.clear()
            sim._discovered_tile_set = live_tests.MembershipOnly([pos_key(*known),pos_key(*other)])
            before = sim.state.to_dict()
            runtime = (sim.world.revision,dict(sim.world.dirty_tiles),
                tuple(sim.world.cache._chunks),fixture.db.connection.total_changes)
            with patch.object(sim.world,'prepared_tile_at',unexpected), \
                    patch.object(sim.world.cache,'peek',unexpected), \
                    patch.object(fixture.db,'load_chunk_deltas',unexpected), \
                    patch.object(sim.resources,'prepared_feature_at',unexpected), \
                    patch.object(sim.settlement_physicalization,'shell_at',unexpected), \
                    patch.object(sim.settlement_physicalization,'cell_at',unexpected), \
                    patch.object(fixture.db,'load_generated_chunk',wraps=fixture.db.load_generated_chunk) as reads:
                snapshot = capture_live_scene(sim,self.camera(sim))
                again = capture_live_scene(sim,self.camera(sim))
            self.assertEqual(dict(snapshot.terrain),{known:'core:grass',other:'core:grass'})
            self.assertNotIn(unknown,snapshot.remembered_cells)
            self.assertEqual((snapshot.resources,snapshot.remembered_resources,snapshot.objects,
                snapshot.remembered_objects,snapshot.remembered_buildings),((),(),(),(),()))
            self.assertEqual(snapshot,again)
            self.assertEqual(reads.call_count,1)  # shared immutable base, not per-cell/per-frame reads
            self.assertEqual(before,sim.state.to_dict())
            self.assertEqual(runtime,(sim.world.revision,dict(sim.world.dirty_tiles),
                tuple(sim.world.cache._chunks),fixture.db.connection.total_changes))
            self.assertIsNone(sim.state.exterior_memory.get(known))

    def test_legacy_basemap_misses_can_fill_later_without_generation(self):
        with self.fixture() as fixture:
            sim = fixture.sim
            cell = (256,256,0)
            key,_,_ = split_world(WorldPos(*cell))
            self.assertIsNone(legacy_base_terrain(sim.world,cell,{}))
            fixture.db.store_generated_chunk(key,sim.world.generator.version,
                ('core:forest',)*(CHUNK_SIZE*CHUNK_SIZE))
            with patch.object(sim.world.cache,'get',unexpected), \
                    patch.object(sim.world.generator,'generate_chunk',unexpected):
                self.assertEqual(legacy_base_terrain(sim.world,cell,{}),'core:forest')

    def test_legacy_basemap_surface_contract_never_falls_back_to_wrong_projection(self):
        with self.fixture() as fixture:
            sim = fixture.sim
            cell = (256,256,0)
            key,_,_ = split_world(WorldPos(*cell))
            contract = (sim.world.generator.version,2,1,2)
            fixture.db.store_generated_chunk(key,sim.world.generator.version,
                ('core:grass',)*(CHUNK_SIZE*CHUNK_SIZE))
            with patch.object(sim.world,'_surface_cache_contract',return_value=contract), \
                    patch.object(fixture.db,'load_generated_chunk',unexpected):
                self.assertIsNone(legacy_base_terrain(sim.world,cell,{}))
                fixture.db.store_generated_surface_chunk(key,*contract,
                    ('core:forest',)*(CHUNK_SIZE*CHUNK_SIZE))
                self.assertEqual(legacy_base_terrain(sim.world,cell,{}),'core:forest')

    def test_legacy_basemap_cache_remains_bounded_while_panning(self):
        with self.fixture() as fixture:
            world = fixture.sim.world
            base = ('core:grass',)*(CHUNK_SIZE*CHUNK_SIZE)
            with patch.object(fixture.db,'load_generated_chunk',return_value=base):
                for x in range(BASE_MEMORY_CHUNK_LIMIT+20):
                    self.assertEqual(legacy_base_terrain(world,(x*CHUNK_SIZE,0,0),{}),'core:grass')
            self.assertEqual(len(_base_chunks[world]),BASE_MEMORY_CHUNK_LIMIT)
