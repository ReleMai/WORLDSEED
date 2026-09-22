import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from worldseed.config import DATA_DIR, CHUNK_SIZE
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import ChunkKey, WorldPos
from worldseed.persistence.database import WorldDatabase
from worldseed.world.world import World
from worldseed.world.generator import WorldGenerator
from worldseed.world.atlas import read_atlas
from worldseed.systems.state import LivingWorldState, StructureInstance
from worldseed.ui.pygame_terminal import PygameTerminal


def fixture(version=7, seed=b'atlas-test', auto_hydrology=False):
    reg = ContentRegistry.load(DATA_DIR)
    td = tempfile.TemporaryDirectory()
    db = WorldDatabase.create(Path(td.name)/'atlas.db', 'Atlas', seed.hex())
    world = World(WorldGenerator(seed, reg, version=version), reg, db, auto_hydrology=auto_hydrology)
    sim = SimpleNamespace(world=world, player_pos=WorldPos(0,0,0), state=LivingWorldState(),
        discovered_tiles_set={'-1,-1,0','0,0,0','-1,0,0','0,-1,0'},
        known_settlements=lambda: [], known_site_ids=lambda: set())
    return td, db, world, sim


class AtlasTests(unittest.TestCase):
    def setUp(self):
        self.td, self.db, self.world, self.sim = fixture()
    def tearDown(self):
        self.db.close(); self.td.cleanup()
    def seed_chunk(self, key, tid='core:forest'):
        values = [tid]*(CHUNK_SIZE*CHUNK_SIZE)
        self.db.store_generated_chunk(key, self.world.generator.version, values)
        return values

    def test_exact_all_seeds_versions_and_negative_coordinates(self):
        for seed in (b'zero', b'river', b'ocean'):
            for version in range(1,8):
                td, db, world, sim = fixture(version, seed)
                try:
                    key = ChunkKey(-1,-1,0)
                    chunk = world.generator.generate_chunk(key)
                    world.cache.put(key, chunk)
                    sim.discovered_tiles_set.update(
                        f'{x},{y},0' for y in range(-32,0) for x in range(-32,0)
                    )
                    view = read_atlas(sim, (-16,-16),128)
                    for y in range(-32,0):
                        for x in range(-32,0):
                            self.assertEqual(view.terrain_at(x,y), world.tile_at(WorldPos(x,y,0)).terrain_id)
                finally:
                    db.close(); td.cleanup()

    def test_persisted_dirty_and_saved_delta_precedence(self):
        key = ChunkKey(-1,-1,0)
        self.seed_chunk(key)
        self.sim.discovered_tiles_set.add('-2,-2,0')
        self.db.connection.execute('INSERT INTO tile_deltas VALUES(-2,-2,0,?)', ('core:sand',))
        self.assertEqual(read_atlas(self.sim,span=128).terrain_at(-2,-2),'core:sand')
        self.world.set_terrain(WorldPos(-2,-2,0),'core:tilled_soil')
        self.assertEqual(read_atlas(self.sim,span=128).terrain_at(-2,-2),'core:tilled_soil')
        self.assertEqual(self.world.tile_at(WorldPos(-2,-2,0)).terrain_id,'core:tilled_soil')

    def test_read_only_no_generation_no_lru_changes_no_database_writes(self):
        self.seed_chunk(ChunkKey(0,0,0))
        before = self.sim.state.to_dict()
        changes = self.db.connection.total_changes
        cache = list(self.world.cache._chunks)
        with (patch.object(self.world.generator,'generate_chunk',side_effect=AssertionError('generation forbidden')),
              patch.object(self.world.cache,'get',side_effect=AssertionError('cache loading forbidden'))):
            a = read_atlas(self.sim,span=128)
            b = read_atlas(self.sim,span=128)
        self.assertEqual(a,b)
        self.assertEqual(changes,self.db.connection.total_changes)
        self.assertEqual(before,self.sim.state.to_dict())
        self.assertEqual(cache,list(self.world.cache._chunks))

    def test_missing_and_undiscovered_terrain_is_not_invented(self):
        self.seed_chunk(ChunkKey(20,0,0),'core:river')
        view = read_atlas(self.sim,(640,0),128)
        self.assertIsNone(view.terrain_at(640,0))
        self.sim.discovered_tiles_set.add('640,0,0')
        view = read_atlas(self.sim,(640,0),128)
        self.assertEqual(view.terrain_at(640,0),'core:river')
        self.assertIsNone(view.terrain_at(610,0))

    def test_poi_authority_and_discovery(self):
        self.seed_chunk(ChunkKey(0,0,0),'core:grass')
        towns = [SimpleNamespace(uid='v',name='Village',x=2,y=2,population=150),
                 SimpleNamespace(uid='c',name='City',x=40,y=40,population=1200)]
        self.sim.known_settlements = lambda: towns
        self.sim.state.structures['camp'] = StructureInstance('core:campfire',8,8,0)
        self.sim.state.structures['secret'] = StructureInstance('core:brush_lean_to',24,24,0,owner='stranger')
        self.world.set_terrain(WorldPos(0,0,0),'core:cave_mouth')
        markers = read_atlas(self.sim,span=128).markers
        self.assertEqual({m.kind for m in markers},{'village','city','camp','cave'})
        self.assertNotIn('camp:secret',{m.uid for m in markers})
        self.sim.state.structures['camp'].condition=0
        self.assertNotIn('camp',{m.kind for m in read_atlas(self.sim,span=128).markers})

    def test_real_prepared_hydrology_survives_cache_reload(self):
        td, db, world, sim = fixture(7,b'prepared-atlas',True)
        try:
            world.pre_generate(WorldPos(0,0,0),0)
            sim.discovered_tiles_set.update({'0,0,0','15,15,0','31,31,0'})
            expected = read_atlas(sim,span=128)
            world.cache._chunks.clear()
            with patch.object(world.generator,'generate_chunk',side_effect=AssertionError('no regen')):
                actual = read_atlas(sim,span=128)
                self.assertEqual(actual,expected)
                for x,y in ((0,0),(15,15),(31,31)):
                    self.assertEqual(actual.terrain_at(x,y),world.tile_at(WorldPos(x,y,0)).terrain_id)
        finally:
            db.close(); td.cleanup()

    def test_explored_chunks_survive_lru_eviction_and_reopen(self):
        pos = WorldPos(-10,-10,0)
        expected = self.world.tile_at(pos).terrain_id
        self.sim.discovered_tiles_set.add(f'{pos.x},{pos.y},0')
        self.db.commit_generated()
        self.world.cache._chunks.clear()
        self.assertEqual(read_atlas(self.sim,span=128).terrain_at(pos.x,pos.y),expected)

    def test_new_modded_terrain_keeps_identity_and_has_visual_fallback(self):
        from worldseed.ui.atlas_map import AtlasArt
        from worldseed.content.registry import TerrainDef
        import json
        art = object.__new__(AtlasArt)
        art.styles = json.loads((Path(__file__).resolve().parents[1]/'worldseed/assets/atlas_styles.json').read_text())
        self.world.registry.terrains['test:marsh'] = TerrainDef('test:marsh','Marsh',';',';',32,True,tags=('soil',))
        self.seed_chunk(ChunkKey(0,0,0),'test:marsh')
        self.assertEqual(read_atlas(self.sim,span=128).terrain_at(0,0),'test:marsh')
        self.assertEqual(art.color('test:marsh',self.world.registry),tuple(art.styles['tag_fallback']['soil']))


@unittest.skipUnless(PygameTerminal.available(),'pygame optional')
class AtlasRenderTests(unittest.TestCase):
    setUp = AtlasTests.setUp
    tearDown = AtlasTests.tearDown
    seed_chunk = AtlasTests.seed_chunk
    def test_render_controls_resize_hover_and_assets(self):
        from worldseed.ui.atlas_map import begin_atlas, atlas_input
        term = PygameTerminal(); term.enter()
        try:
            for ky in range(-2,2):
                for kx in range(-2,2):
                    self.seed_chunk(ChunkKey(kx,ky,0),'core:forest' if kx<0 else 'core:sand')
            self.sim.known_settlements=lambda: [SimpleNamespace(uid=str(i),name=f'Village {i}',x=i,y=i,population=100) for i in range(30)]
            begin_atlas(term,self.sim)
            for size in ((800,520),(1280,800),(2560,1392)):
                term._resize(*size);term.present_region_map(self.sim)
                for rect, token in term._pointer_targets:
                    self.assertTrue(term.screen.get_rect().contains(rect),(size,token,rect))
                self.assertEqual(set(term._atlas_art.icons),{'village','city','camp','cave','fortress','temple','mine','archive','crypt'})
                self.assertIsNone(term._hover_context)
                pixels=term.pg.image.tobytes(term.screen,'RGB')
                term.pg.event.clear()
                term.pg.event.post(term.pg.event.Event(term.pg.MOUSEMOTION,pos=(200,200),rel=(1,1),buttons=(0,0,0)))
                term.pg.event.post(term.pg.event.Event(term.pg.KEYDOWN,key=term.pg.K_ESCAPE,unicode='\x1b'))
                self.assertEqual(term.read_key(),'ESC')
                self.assertEqual(pixels,term.pg.image.tobytes(term.screen,'RGB'))
            for token in ('ATLAS:in','ATLAS:out','ATLAS:home','ATLAS:next','ATLAS:prev'):
                self.assertTrue(atlas_input(term,self.sim,token));term.present_region_map(self.sim)
            self.assertTrue(any(k=='ATLAS_DRAG_ZONE' for _,k in term._pointer_targets))
            term.pg.event.clear()
            rect=term._atlas_rect
            poi_rects=[r for r,k in term._pointer_targets if k.startswith('ATLAS_POI:')]
            start=None
            for gy in range(rect.top+20,rect.bottom-20,24):
                for gx in range(rect.left+20,rect.right-20,24):
                    if not any(r.collidepoint(gx,gy) for r in poi_rects):
                        start=(gx,gy);break
                if start is not None:break
            self.assertIsNotNone(start)
            end=(start[0]+40,start[1]+25)
            term.pg.event.post(term.pg.event.Event(term.pg.MOUSEBUTTONDOWN,button=1,pos=start))
            self.assertEqual(term.read_key(),'ATLAS:drag_start')
            self.assertTrue(atlas_input(term,self.sim,'ATLAS:drag_start'))
            term.pg.event.post(term.pg.event.Event(term.pg.MOUSEMOTION,pos=end,rel=(40,25),buttons=(1,0,0)))
            drag=term.read_key();self.assertTrue(drag.startswith('ATLAS:drag:'))
            old_center=term._atlas_controls.center
            self.assertTrue(atlas_input(term,self.sim,drag))
            self.assertNotEqual(old_center,term._atlas_controls.center)
            term.pg.event.post(term.pg.event.Event(term.pg.MOUSEBUTTONUP,button=1,pos=end))
            self.assertEqual(term.read_key(),'ATLAS:drag_end')
            self.assertTrue(atlas_input(term,self.sim,'ATLAS:drag_end'))
            # The real app redraws after panning before the next pointer action;
            # refresh the invalidated snapshot before testing inspection.
            term.present_region_map(self.sim)
            self.assertFalse(atlas_input(term,self.sim,'w'))
            term._last_mouse = term._atlas_rect.center
            self.assertTrue(atlas_input(term,self.sim,'ATLAS_INSPECT'))
            # Odd raster dimensions put the center pixel just west/north of
            # the exact origin; floor mapping is intentional.
            self.assertTrue(all(abs(v)<=1 for v in term._atlas_controls.inspected))
            term.present_region_map(self.sim)
        finally:
            term.restore()
