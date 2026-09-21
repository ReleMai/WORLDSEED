import json
import tempfile
import unittest
from pathlib import Path

from worldseed.config import DATA_DIR, ENGINE_VERSION, WORLDGEN_VERSION
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.core.rng import hash_u64
from worldseed.entities.components import Inventory, Position, Vitals
from worldseed.entities.store import EntityStore
from worldseed.persistence.database import WorldDatabase
from worldseed.sim.commands import GatherCommand, MoveCommand, TalkCommand, VerticalMoveCommand, ExcavateShaftCommand
from worldseed.sim.engine import Simulation
from worldseed.systems.resources import ResourceSystem
from worldseed.systems.state import LivingWorldState, pos_key
from worldseed.ui.router import classify_key
from worldseed.ui.startup import inspect_save
from worldseed.world.generator import WorldGenerator
from worldseed.world.world import World


class RC5GameplayTests(unittest.TestCase):
    def make_sim(self, seed=b'rc5-gameplay', z=0, items=None, gen_version=None):
        td=tempfile.TemporaryDirectory();reg=ContentRegistry.load(DATA_DIR)
        db=WorldDatabase.create(Path(td.name)/'w.db','RC5',seed.hex())
        if gen_version is not None:db.set_meta('worldgen_version',gen_version);db.connection.commit()
        gen=WorldGenerator(seed,reg,version=gen_version)
        world=World(gen,reg,db);e=EntityStore();pid=e.spawn(preferred_id=1)
        e.add(pid,Position(WorldPos(0,0,z)));e.add(pid,Inventory(items or {'core:stone_axe':1,'core:iron_pick':1}));e.add(pid,Vitals())
        sim=Simulation(world,e,reg,0,LivingWorldState(),seed)
        return td,db,reg,world,e,pid,sim

    def test_surface_tree_is_feature_not_ground_and_has_life_cycle(self):
        td,db,reg,world,e,pid,sim=self.make_sim()
        try:
            target=None
            for y in range(-80,81):
                for x in range(-80,81):
                    p=WorldPos(x,y,0);fv=sim.resources.feature_at(p)
                    if fv and 'tree' in reg.resources[fv.feature_id].tags:
                        target=p;break
                if target:break
            self.assertIsNotNone(target)
            e.get(pid,Position).value=target
            ground=world.tile_at(target).terrain_id
            sim.execute(GatherCommand(pid))
            self.assertEqual(world.tile_at(target).terrain_id,ground)
            self.assertEqual(sim.resources.feature_at(target).stage,'stump')
            harvested=sim.state.resource_depletion[pos_key(target.x,target.y,target.z)]
            self.assertEqual(sim.resources.feature_at(target,harvested+46*1440).stage,'sapling')
            feature=sim.resources._base_feature(target);days=reg.resources[feature].regrow_days
            self.assertEqual(sim.resources.feature_at(target,harvested+(days+1)*1440).stage,'mature')
        finally:db.close();td.cleanup()

    def test_tree_blocks_movement_until_felled(self):
        td,db,reg,world,e,pid,sim=self.make_sim()
        try:
            target=None;origin=None
            for y in range(-60,61):
                for x in range(-60,61):
                    p=WorldPos(x,y,0);fv=sim.resources.feature_at(p)
                    if fv and reg.resources[fv.feature_id].blocks_movement:
                        for dx,dy in ((-1,0),(1,0),(0,-1),(0,1)):
                            q=p.moved(dx,dy)
                            if world.is_passable(q) and not sim.resources.blocks_movement(q):origin=q;target=p;break
                    if target:break
                if target:break
            self.assertIsNotNone(target);e.get(pid,Position).value=origin
            dx,dy=target.x-origin.x,target.y-origin.y
            sim.execute(MoveCommand(pid,dx,dy));self.assertEqual(sim.player_pos,origin)
            sim.execute(GatherCommand(pid,dx,dy));self.assertFalse(sim.resources.blocks_movement(target))
            sim.execute(MoveCommand(pid,dx,dy));self.assertEqual(sim.player_pos,target)
        finally:db.close();td.cleanup()

    def test_adjacent_wall_mining_opens_passage(self):
        td,db,reg,world,e,pid,sim=self.make_sim(z=-1)
        try:
            origin=WorldPos(0,0,-1);target=WorldPos(1,0,-1)
            e.get(pid,Position).value=origin;world.set_terrain(origin,'core:cave_floor');world.set_terrain(target,'core:cave_wall')
            before=e.get(pid,Inventory).count('core:stone')
            sim.execute(GatherCommand(pid,1,0))
            self.assertEqual(world.tile_at(target).terrain_id,'core:cave_floor')
            self.assertGreater(e.get(pid,Inventory).count('core:stone'),before)
        finally:db.close();td.cleanup()

    def test_v3_surface_cave_is_reciprocal_vertical_column(self):
        reg=ContentRegistry.load(DATA_DIR);g=WorldGenerator(b'connector-test',reg,version=3)
        mouth=None
        for y in range(-120,121):
            for x in range(-120,121):
                p=WorldPos(x,y,0)
                if g.terrain_at(p)=='core:cave_mouth':mouth=p;break
            if mouth:break
        self.assertIsNotNone(mouth)
        self.assertEqual(g.terrain_at(WorldPos(mouth.x,mouth.y,-1)),'core:shaft')
        span=g._connector_span(mouth.x,mouth.y);self.assertGreaterEqual(span,1)
        for z in range(-1,-span-1,-1):self.assertEqual(g.terrain_at(WorldPos(mouth.x,mouth.y,z)),'core:shaft')

    def test_v2_generator_preserves_legacy_cave_rules(self):
        reg=ContentRegistry.load(DATA_DIR);seed=b'legacy-geography';g=WorldGenerator(seed,reg,version=2)
        mouth=None
        for y in range(-150,151):
            for x in range(-150,151):
                p=WorldPos(x,y,0);f=g.sample_fields(p)
                if f.elevation>=26500 and hash_u64(seed,'cave-mouth',x//3,y//3)%997==0:
                    mouth=p;break
            if mouth:break
        self.assertIsNotNone(mouth);self.assertEqual(g.terrain_at(mouth),'core:cave_mouth')
        # save checkpoints must not rewrite immutable generator metadata
        with tempfile.TemporaryDirectory() as td:
            db=WorldDatabase.create(Path(td)/'legacy.db','Legacy',seed.hex());db.set_meta('worldgen_version',2);db.connection.commit()
            db.save_state(turn=1,tile_deltas={},player_id=1,position=WorldPos(0,0,0),inventory={},sim_state=LivingWorldState().to_dict())
            self.assertEqual(db.get_meta('worldgen_version'),2);db.close()

    def test_line_of_sight_does_not_discover_through_wall(self):
        td,db,reg,world,e,pid,sim=self.make_sim(z=-1)
        try:
            origin=WorldPos(0,0,-1);wall=WorldPos(1,0,-1);hidden=WorldPos(2,0,-1)
            e.get(pid,Position).value=origin;world.set_terrain(origin,'core:cave_floor');world.set_terrain(wall,'core:cave_wall');world.set_terrain(hidden,'core:cave_floor')
            sim.state.discovered_tiles=[];sim._discover(origin)
            self.assertIn(pos_key(wall.x,wall.y,wall.z),sim.state.discovered_tiles)
            self.assertNotIn(pos_key(hidden.x,hidden.y,hidden.z),sim.state.discovered_tiles)
        finally:db.close();td.cleanup()

    def test_npc_identity_requires_talking(self):
        td,db,reg,world,e,pid,sim=self.make_sim()
        try:
            if not sim.state.npcs:self.skipTest('seed realized no named NPCs')
            npc=next(iter(sim.state.npcs.values()));npc.x,npc.y,npc.z=1,0,0;e.get(pid,Position).value=WorldPos(0,0,0)
            sim.state.discovered_npcs=[];sim._discover(sim.player_pos)
            self.assertNotIn(npc.uid,sim.known_npc_ids())
            sim.execute(TalkCommand(pid,1,0));self.assertIn(npc.uid,sim.known_npc_ids())
        finally:db.close();td.cleanup()

    def test_mouse_and_paste_tokens_are_never_gameplay_commands(self):
        self.assertEqual(classify_key('MOUSE').kind,'none')
        self.assertEqual(classify_key('PASTE').kind,'none')

    def test_save_summary_exposes_continue_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'a.db';db=WorldDatabase.create(path,'Aldervale',b'seed'.hex())
            st=LivingWorldState(clock_minute=4320,player_name='Mara',player_origin='prospector')
            db.set_meta('player_name','Mara');db.set_meta('player_origin','prospector');db.set_meta('last_saved_at',12345.0)
            db.save_state(turn=9,tile_deltas={},player_id=1,position=WorldPos(0,0,0),inventory={},sim_state=st.to_dict());db.close()
            row=inspect_save(path);self.assertTrue(row.valid);self.assertEqual(row.world_name,'Aldervale');self.assertEqual(row.player_name,'Mara');self.assertEqual(row.origin,'prospector');self.assertEqual(row.day,4)

    def test_spawn_avoids_blocking_resource(self):
        from worldseed.app import _find_spawn
        td,db,reg,world,e,pid,sim=self.make_sim(seed=b'spawn-scoring')
        try:
            p=_find_spawn(world,'wanderer',sim.resources);self.assertFalse(sim.resources.blocks_movement(p));self.assertTrue(world.is_passable(p))
        finally:db.close();td.cleanup()

    def test_main_menu_continue_selects_latest_valid_save(self):
        import worldseed.ui.startup as startup
        class FakeTerm:
            def __init__(self,keys):self.keys=list(keys)
            def size(self):return (100,30)
            def present(self,text):self.last=text
            def read_key(self):return self.keys.pop(0)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);old=startup.DEFAULT_SAVE_DIR;startup.DEFAULT_SAVE_DIR=root
            try:
                for name,stamp in [('Old',1000.0),('Recent',2000.0)]:
                    path=root/f'{name}.db';db=WorldDatabase.create(path,name,b'seed'.hex());db.set_meta('last_saved_at',stamp);db.set_meta('player_name',name+' Hero');db.connection.commit();db.close()
                sel=startup.main_menu(FakeTerm(['\r']))
                self.assertIsNotNone(sel);self.assertEqual(sel.path.name,'Recent.db');self.assertFalse(sel.is_new)
            finally:startup.DEFAULT_SAVE_DIR=old

    def test_undiscovered_records_do_not_leak_through_ledger(self):
        from worldseed.app import _ledger_rows
        td,db,reg,world,e,pid,sim=self.make_sim(seed=b'discovery-ledger')
        try:
            sim.state.discovered_npcs=[];sim.state.discovered_settlements=[];sim.state.discovered_factions=[];sim.state.discovered_events=[]
            self.assertEqual(_ledger_rows(sim,'people'),[]);self.assertEqual(_ledger_rows(sim,'factions'),[]);self.assertEqual(_ledger_rows(sim,'events'),[])
        finally:db.close();td.cleanup()

    def test_look_does_not_spoil_undiscovered_historical_site(self):
        from worldseed.core.coords import ChunkKey, chunk_origin
        from worldseed.ui.screens import look_screen
        td,db,reg,world,e,pid,sim=self.make_sim(seed=b'site-secrecy',z=-1)
        try:
            key=next(ChunkKey(x,y,-1) for x in range(-30,31) for y in range(-30,31) if world.generator.sites.has_site(ChunkKey(x,y,-1)))
            info=world.generator.sites.info(key);origin=chunk_origin(key);p=WorldPos(origin.x+16,origin.y+16,-1)
            sim.state.discovered_tiles=[pos_key(p.x,p.y,p.z)];sim.state.discovered_sites=[]
            text=look_screen(sim,100,p);self.assertNotIn(info.name,text);self.assertNotIn(info.builder,text)
        finally:db.close();td.cleanup()

    def test_site_overlay_cannot_sever_v3_connector(self):
        from worldseed.core.coords import ChunkKey, chunk_origin
        reg=ContentRegistry.load(DATA_DIR);g=WorldGenerator(b'overlay-connector',reg,version=3);found=None
        for cy in range(-40,41):
            for cx in range(-40,41):
                key=ChunkKey(cx,cy,-1)
                if not g.sites.has_site(key):continue
                origin=chunk_origin(key)
                for ly in range(32):
                    for lx in range(32):
                        p=WorldPos(origin.x+lx,origin.y+ly,-1)
                        if g.has_connector(p):found=(key,lx,ly,p);break
                    if found:break
                if found:break
            if found:break
        self.assertIsNotNone(found)
        key,lx,ly,p=found;chunk=g.generate_chunk(key)
        self.assertEqual(reg.terrain_id(chunk.get(lx,ly)),'core:shaft')

    def test_player_can_excavate_persistent_supported_shaft(self):
        td,db,reg,world,e,pid,sim=self.make_sim(seed=b'player-shaft',items={'core:iron_pick':1,'core:wood':4})
        try:
            # Find a passable clear surface tile.
            pos=None
            for y in range(-40,41):
                for x in range(-40,41):
                    q=WorldPos(x,y,0)
                    if world.is_passable(q) and not sim.resources.blocks_movement(q) and 'water' not in world.tile_at(q).terrain.tags:
                        pos=q;break
                if pos:break
            self.assertIsNotNone(pos);e.get(pid,Position).value=pos
            sim.execute(ExcavateShaftCommand(pid))
            self.assertEqual(world.tile_at(pos).terrain_id,'core:cave_mouth')
            self.assertEqual(world.tile_at(pos.moved(0,0,-1)).terrain_id,'core:shaft')
            self.assertEqual(e.get(pid,Inventory).count('core:wood'),2)
            sim.execute(VerticalMoveCommand(pid,-1));self.assertEqual(sim.player_pos.z,-1)
            sim.execute(VerticalMoveCommand(pid,1));self.assertEqual(sim.player_pos.z,0)
        finally:db.close();td.cleanup()

    def test_new_character_starts_without_guiding_leads(self):
        from worldseed.app import _load_context
        from worldseed.ui.startup import StartSelection
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'new.db';ctx=_load_context(StartSelection(path,True,'New',b'rumor-seed'.hex(),'Ilya','scholar'),prepare_world=False)
            try:
                self.assertEqual(ctx.sim.state.player_rumors,[])
                self.assertEqual(ctx.sim.known_settlement_ids(),set())
                self.assertEqual(ctx.sim.known_npc_ids(),set())
            finally:ctx.db.close()

    def test_rc4_save_cannot_load_trapped_inside_new_resource_feature(self):
        from worldseed.app import _load_context
        from worldseed.ui.startup import StartSelection
        seed=b'legacy-resource-upgrade'
        reg=ContentRegistry.load(DATA_DIR)
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'legacy.db';db=WorldDatabase.create(path,'Legacy Resource',seed.hex());db.set_meta('worldgen_version',2);db.connection.commit()
            world=World(WorldGenerator(seed,reg,version=2),reg,db);state=LivingWorldState();resources=ResourceSystem(state,reg,seed,world)
            target=None
            for y in range(-100,101):
                for x in range(-100,101):
                    q=WorldPos(x,y,0)
                    if resources.blocks_movement(q):target=q;break
                if target:break
            self.assertIsNotNone(target)
            db.save_state(turn=3,tile_deltas={},player_id=1,position=target,inventory={'core:stone_axe':1},sim_state=state.to_dict());db.close()
            ctx=_load_context(StartSelection(path,False),prepare_world=False)
            try:
                self.assertEqual(ctx.sim.player_pos,target)
                self.assertFalse(ctx.sim.resources.blocks_movement(target))
            finally:ctx.db.close()


if __name__=='__main__':unittest.main()
