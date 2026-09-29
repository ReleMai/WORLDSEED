from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')

from worldseed.config import DATA_DIR, MOVE_MINUTES
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory, Position, Vitals
from worldseed.entities.store import EntityStore
from worldseed.persistence.database import WorldDatabase
from worldseed.sim.commands import MoveCommand
from worldseed.sim.engine import Simulation
from worldseed.systems.state import LivingWorldState, NPCState
from worldseed.world.generator import WorldGenerator
from worldseed.world.lighting import LightingSystem
from worldseed.world.world import World
from worldseed.ui.pygame_terminal import PygameTerminal


def fixture():
    reg=ContentRegistry.load(DATA_DIR)
    td=tempfile.TemporaryDirectory()
    seed=b'dev31-playtest'
    db=WorldDatabase.create(Path(td.name)/'world.db','Dev31',seed.hex())
    world=World(WorldGenerator(seed,reg,version=8),reg,db)
    entities=EntityStore();pid=entities.spawn(preferred_id=1)
    entities.add(pid,Position(WorldPos(0,0,0)));entities.add(pid,Inventory());entities.add(pid,Vitals())
    sim=Simulation(world,entities,reg,0,LivingWorldState(),seed)
    return td,db,sim,pid


class Dev31ExplorationTests(unittest.TestCase):
    def setUp(self):
        self.td,self.db,self.sim,self.pid=fixture()
    def tearDown(self):
        self.db.close();self.td.cleanup()

    def test_movement_uses_continuous_clock_instead_of_advancing_time(self):
        self.assertEqual(MOVE_MINUTES,0)
        before=self.sim.clock.minute
        with patch.object(self.sim,'_move'),patch.object(self.sim,'_post_action'):
            self.sim.execute(MoveCommand(self.pid,1,0))
        self.assertEqual(self.sim.clock.minute,before)

    def test_discovery_is_circular(self):
        pos=self.sim.player_pos
        lighting=SimpleNamespace(ambient_light=65535)
        with patch.object(self.sim.environment,'visual_conditions',return_value=({'visibility':8,'fog':0},lighting)):
            radius=self.sim.visibility_radius(pos)
            with patch.object(self.sim,'_visible_from',return_value=True):
                self.sim._discover(pos)
        visible=self.sim.visible_tiles_set
        self.assertIn(f'{pos.x+radius},{pos.y},0',visible)
        self.assertNotIn(f'{pos.x+radius},{pos.y+radius},0',visible)

    def test_bad_weather_and_night_shrink_sight(self):
        pos=self.sim.player_pos
        clear=SimpleNamespace(ambient_light=62000)
        dark=SimpleNamespace(ambient_light=8000)
        with patch.object(self.sim.environment,'visual_conditions',return_value=({'visibility':8,'fog':0},clear)):
            day=self.sim.visibility_radius(pos)
        with patch.object(self.sim.environment,'visual_conditions',return_value=({'visibility':4,'fog':75},dark)):
            storm_night=self.sim.visibility_radius(pos)
        self.assertLess(storm_night,day)
        self.assertGreaterEqual(storm_night,3)


class Dev31LightingTests(unittest.TestCase):
    # Lighting is pure: do not regenerate a world just to inspect dawn/dusk.
    def test_twilight_uses_warm_orange_tints(self):
        light=LightingSystem()
        # Spring opening sunrise is near 06:00; sample shortly before and after sunset.
        dawn=light.at(330)
        dusk=light.at(1110)
        self.assertEqual(dawn.phase,'dawn')
        self.assertEqual(dusk.phase,'dusk')
        self.assertGreater(dawn.tint_r,dawn.tint_b)
        self.assertGreater(dusk.tint_r,dusk.tint_b)


@unittest.skipUnless(PygameTerminal.available(),'pygame optional')
class Dev31PresentationTests(unittest.TestCase):
    def setUp(self):
        self.term=PygameTerminal();self.term.enter()
    def tearDown(self):
        self.term.restore()

    def test_cloud_field_is_world_anchored_and_moves_independently(self):
        fx=self.term._weather_fx
        seed=b'cloud-anchor'
        a=fx.cloud_shadow_surface(640,360,seed,100,1024,128,0,0,20,0)
        b=fx.cloud_shadow_surface(640,360,seed,100,1024,128,1,0,20,0)
        later=fx.cloud_shadow_surface(640,360,seed,100,1024,128,0,0,20,30000)
        self.assertNotEqual(self.term.pg.image.tobytes(a,'RGBA'),self.term.pg.image.tobytes(b,'RGBA'))
        self.assertNotEqual(self.term.pg.image.tobytes(a,'RGBA'),self.term.pg.image.tobytes(later,'RGBA'))

    def test_spatial_render_index_ignores_far_world_population(self):
        td,db,sim,pid=fixture()
        try:
            for i in range(250):
                sim.state.npcs[str(i)]=NPCState(
                    uid=str(i),name='Far',age=30,occupation='farmer',traits=[],
                    x=5000+i,y=5000,z=0,settlement_id='',faction_id=''
                )
            sim.state.npcs['near']=NPCState(
                uid='near',name='Near',age=30,occupation='farmer',traits=[],
                x=2,y=3,z=0,settlement_id='',faction_id=''
            )
            rows=self.term._spatial_state_views(sim,-20,-20,20,20,0)
            self.assertEqual([n.uid for n in rows['npcs']],['near'])
        finally:
            db.close();td.cleanup()


if __name__=='__main__':
    unittest.main()
