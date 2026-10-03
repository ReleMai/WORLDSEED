import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from tests.test_interiors import sample_plan
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import ChunkKey, WorldPos
from worldseed.entities.components import Inventory, Position, Vitals
from worldseed.entities.store import EntityStore
from worldseed.persistence.database import WorldDatabase
from worldseed.sim.commands import MoveCommand, GatherCommand, DropCommand, PickupCommand, CraftCommand, StartProcessingCommand
from worldseed.sim.engine import Simulation
from worldseed.systems.interior_state import InteriorActor, InteriorRect
from worldseed.systems.interiors import build_interior
from worldseed.systems.state import LivingWorldState
from worldseed.ui.renderer import Renderer
from worldseed.world.chunk import Chunk
from worldseed.world.generator import WorldGenerator
from worldseed.world.world import World


class InteriorEngineTests(unittest.TestCase):
    def setUp(self):
        self.sim,self.plan=self.prepared_simulation()

    def prepared_simulation(self):
        """Fresh real engine, without regenerating unrelated surface regions.

        These assertions cover continuous interiors and Simulation.execute,
        not world startup (covered by the world/UI and portal integrations).
        Only constructor regional preparation is suppressed. Command handlers,
        time advancement, consequences and every authoritative system remain
        real and unpatched when each test starts.
        """
        registry=ContentRegistry.load(DATA_DIR)
        folder=tempfile.TemporaryDirectory(prefix='worldseed-interior-engine-')
        self.addCleanup(folder.cleanup)
        seed=b'interior-engine'
        database=WorldDatabase.create(Path(folder.name)/'interior.db','Interior engine fixture',seed.hex())
        self.addCleanup(database.close)
        world=World(WorldGenerator(seed,registry),registry,database)
        # One prepared dry anchor chunk makes unexpected incidental terrain
        # reads bounded, without hydrology, society or route generation.
        key=ChunkKey(0,0,0);chunk=Chunk.empty(key)
        ground=registry.terrain_index('core:grass')
        for index in range(len(chunk.terrain)):chunk.terrain[index]=ground
        world.cache.put(key,chunk)
        entities=EntityStore();player_id=entities.spawn(preferred_id=1)
        entities.add(player_id,Position(WorldPos(0,0,0)))
        entities.add(player_id,Inventory({'core:copper_coin':30,'core:wood':4}))
        entities.add(player_id,Vitals())
        plan=sample_plan()
        state=LivingWorldState(discovered_tiles=['0,0,0','1,0,0'])
        state.interiors[plan.uid]=plan
        state.interior_actors['player']=InteriorActor(plan.uid,plan.entry_x,plan.entry_y)
        with patch.object(Simulation,'_ensure_nearby_world') as prepare:
            sim=Simulation(world,entities,registry,0,state,seed)
        prepare.assert_called_once_with(WorldPos(0,0,0),force=True)
        return sim,plan

    def test_prepared_fixture_has_isolated_mutable_engine_and_world_state(self):
        other,other_plan=self.prepared_simulation()
        self.assertIsNot(self.sim.state,other.state)
        self.assertIsNot(self.sim.entities,other.entities)
        self.assertIsNot(self.sim.registry,other.registry)
        self.assertIsNot(self.sim.world,other.world)
        self.sim.entities.get(self.sim.player_id,Inventory).remove('core:wood',2)
        self.sim.interiors.player_presence().x+=127
        self.plan.furniture[0].x+=143
        self.sim.state.discovered_tiles.append('2,0,0')
        self.assertEqual(other.entities.get(other.player_id,Inventory).count('core:wood'),4)
        self.assertEqual(other.interiors.player_presence().x,other_plan.entry_x)
        self.assertNotEqual(self.plan.furniture[0].x,other_plan.furniture[0].x)
        self.assertEqual(other.state.discovered_tiles,['0,0,0','1,0,0'])

    def test_move_is_fractional_without_discovering_outside(self):
        sim=self.sim;pos=sim.player_pos;discovered=list(sim.state.discovered_tiles);minute=sim.clock.minute
        sim.execute(MoveCommand(sim.player_id,1,-1))
        actor=sim.interiors.player_presence()
        self.assertEqual(actor.x,self.plan.entry_x+127)
        self.assertEqual(sim.player_pos,pos)
        self.assertEqual(sim.clock.minute,minute)
        self.assertEqual(sim.state.discovered_tiles,discovered)

    def generated_mill(self):
        from tests import test_phase4_workshop_expansion as workshop_fixtures
        source=workshop_fixtures.WorkshopExpansionTests();source.registry=self.sim.registry
        _,_,_,skeleton=source._city()
        mill=next(s for s in skeleton.structures if s.function=='mill')
        pieces=[p for p in skeleton.pieces if p.structure_plan_id==mill.uid]
        entrance=next(p for p in pieces if p.role=='entrance')
        door=SimpleNamespace(uid=entrance.uid,x=entrance.x,y=entrance.y,z=0,owner_uid='')
        plan=build_interior(mill,door,[r for r in skeleton.rooms if r.structure_plan_id==mill.uid],pieces)
        self.sim.state.interiors[plan.uid]=plan
        station=next(f for f in plan.furniture if f.piece_id=='core:millstone_piece')
        use=self.sim.interiors.fixture_use_position(plan,station)
        self.sim.interiors._put_actor('player',InteriorActor(plan.uid,*use))
        return plan,station

    def test_execute_crafts_at_real_indoor_mill_without_outdoor_station_query(self):
        sim=self.sim;plan,station=self.generated_mill()
        sim.state.player_crafting_discovery_enabled=False
        inv=sim.entities.get(sim.player_id,Inventory);inv.add('core:wheat',2)
        before=inv.count('core:flour');minute=sim.clock.minute
        with patch.object(sim.building,'nearby_station_ids',side_effect=AssertionError('outdoor station query')), patch.object(sim.building,'environmental_bonuses',side_effect=AssertionError('outdoor work bonus')):
            sim.execute(CraftCommand(sim.player_id,'core:mill_flour'))
        self.assertEqual(inv.count('core:flour'),before+2)
        self.assertEqual(inv.count('core:wheat'),0)
        self.assertGreater(sim.clock.minute,minute)
        self.assertIn('complete',sim.log[-1].message)

    def test_station_use_context_checks_actual_reach_and_wall_before_opening_craft_ui(self):
        from worldseed import app
        sim=self.sim;plan,station=self.generated_mill()
        ctx=SimpleNamespace(sim=sim,player_id=sim.player_id)
        before=sim.state.to_dict()
        with patch.object(app,'_select',return_value='use'),patch.object(app,'_crafting_menu',return_value=app.UI_BACK) as opened:
            result=app._interior_context_menu(ctx,SimpleNamespace(),station.x+10,station.y+10)
        opened.assert_called_once_with(ctx,unittest.mock.ANY,'workshops','core:millstone')
        self.assertEqual(result,app.UI_BACK)
        self.assertEqual(sim.state.to_dict(),before)
        actor=sim.interiors.player_presence()
        nearest_x=max(station.x,min(actor.x,station.x+station.w));nearest_y=max(station.y,min(actor.y,station.y+station.h))
        if abs(actor.x-nearest_x)>=abs(actor.y-nearest_y):
            plan.walls.append(InteriorRect((actor.x+nearest_x)//2,0,25,plan.height))
        else:plan.walls.append(InteriorRect(0,(actor.y+nearest_y)//2,plan.width,25))
        with patch.object(app,'_select',return_value='use'),patch.object(app,'_crafting_menu',side_effect=AssertionError('through-wall craft menu')):
            self.assertIn('walls block',app._interior_context_menu(ctx,SimpleNamespace(),station.x+10,station.y+10))
        with patch.object(sim.world,'tile_at',side_effect=AssertionError('outside water query')):
            self.assertFalse(app._nearby_water(sim))
        sim.execute(StartProcessingCommand(sim.player_id,'core:smoke_fish'))
        self.assertIn('unavailable inside',sim.log[-1].message)

    def test_outside_commands_cannot_use_anchor(self):
        with patch.object(self.sim,'_gather',side_effect=AssertionError('outside gather')):
            self.sim.execute(GatherCommand(self.sim.player_id))
        self.assertIn('unavailable inside',self.sim.log[-1].message)

    def test_drop_pickup_conserves_goods_in_correct_space(self):
        inv=self.sim.entities.get(self.sim.player_id,Inventory);before=inv.count('core:wood')
        self.sim.execute(DropCommand(self.sim.player_id,'core:wood',2))
        self.assertEqual(inv.count('core:wood'),before-2)
        self.assertEqual(self.plan.piles[0].items,{'core:wood':2})
        self.assertFalse(self.sim.state.ground_piles)
        self.sim.execute(PickupCommand(self.sim.player_id))
        self.assertEqual(inv.count('core:wood'),before)
        self.assertFalse(self.plan.piles)

    def test_post_action_does_not_attack_or_reveal_outside(self):
        before=list(self.sim.state.discovered_tiles)
        with patch.object(self.sim.hunting,'update_local_ai',side_effect=AssertionError('outside attack')), patch.object(self.sim,'_discover',side_effect=AssertionError('outside discovery')):
            self.sim._post_action()
        self.assertEqual(self.sim.state.discovered_tiles,before)

    def test_death_keeps_cargo_inside_and_clears_presence(self):
        inv=self.sim.entities.get(self.sim.player_id,Inventory);cargo=dict(inv.items)
        with patch('worldseed.systems.respawn.nearby_land_spawn',return_value=WorldPos(12,12,0)):
            self.sim._handle_death('test interior death')
        self.assertEqual(self.plan.piles[0].items,cargo)
        self.assertFalse(inv.items)
        self.assertIsNone(self.sim.interiors.player_presence())
        self.assertFalse(self.sim.state.ground_piles)

    def test_save_defaults_round_trip_and_terminal_observation(self):
        state=self.sim.state;before=state.to_dict()
        for width,height in ((1,1),(60,18),(100,40)):
            text=Renderer(self.sim.registry).render(self.sim.world,self.sim.entities,self.sim,self.sim.player_id,width,height)
            self.assertLessEqual(len(text.splitlines()),height)
            self.assertTrue(all(len(line)<=width for line in text.splitlines()))
        self.assertEqual(state.to_dict(),before)
        self.assertEqual(LivingWorldState.from_dict(before).to_dict(),before)
        self.assertEqual(LivingWorldState.from_dict({'clock_minute':42}).interior_actors,{})


if __name__=='__main__':unittest.main()
