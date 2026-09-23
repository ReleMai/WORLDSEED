import os
os.environ.setdefault("SDL_VIDEODRIVER","dummy")
os.environ.setdefault("SDL_AUDIODRIVER","dummy")
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from worldseed.app import _gather_action
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory, Position
from worldseed.entities.store import EntityStore
from worldseed.sim.commands import GatherCommand, PickupCommand
from worldseed.sim.engine import Simulation
from worldseed.systems.state import GroundPile, pos_key
from worldseed.ui.pygame_terminal import PygameTerminal


class GatherInteractionTests(unittest.TestCase):
    def _ctx(self, harvestable):
        sim=Mock()
        sim.player_pos=WorldPos(0,0,0)
        sim.log=[]
        sim.resources=Mock()
        sim.resources.is_harvestable.side_effect=lambda p:(p.x,p.y,p.z) in harvestable
        sim.resources.description.return_value="Wild Resource"
        def execute(cmd):
            self.assertIsInstance(cmd,GatherCommand)
            sim.log.append(SimpleNamespace(message=f"gathered {cmd.dx},{cmd.dy}"))
        sim.execute.side_effect=execute
        return SimpleNamespace(sim=sim,player_id=1,registry=Mock())

    def test_g_auto_gathers_when_only_one_target_is_in_reach(self):
        ctx=self._ctx({(1,0,0)})
        result=_gather_action(ctx,SimpleNamespace())
        self.assertEqual(result,"gathered 1,0")
        ctx.sim.execute.assert_called_once()

    def test_g_multi_select_gathers_every_selected_target(self):
        ctx=self._ctx({(1,0,0),(0,-1,0)})
        class Term:
            def __init__(self):self.keys=iter(["UI_WORLD:1:0","UI_WORLD:0:-1","\r"])
            def read_key(self):return next(self.keys)
        with patch("worldseed.app._present_game_frame"):
            result=_gather_action(ctx,Term())
        self.assertEqual(ctx.sim.execute.call_count,2)
        self.assertIn("Gathered 2 nearby targets",result)


class AdjacentPickupTests(unittest.TestCase):
    def test_pickup_command_collects_from_adjacent_ground_tile(self):
        entities=EntityStore();pid=entities.spawn(preferred_id=1)
        entities.add(pid,Position(WorldPos(0,0,0)));entities.add(pid,Inventory({"core:wood":1}))
        target=WorldPos(1,0,0);state=SimpleNamespace(ground_piles={
            pos_key(target.x,target.y,target.z):GroundPile(target.x,target.y,target.z,{"core:wood":2})
        })
        messages=[]
        fake=SimpleNamespace(entities=entities,state=state,_message=messages.append)
        Simulation._pickup(fake,PickupCommand(pid,1,0))
        self.assertEqual(entities.get(pid,Inventory).count("core:wood"),3)
        self.assertFalse(state.ground_piles)
        self.assertIn("pick up everything",messages[-1].lower())


@unittest.skipUnless(PygameTerminal.available(),"requires pygame-ce")
class WorldRightClickTests(unittest.TestCase):
    def test_world_right_click_emits_context_menu_token(self):
        term=PygameTerminal();term.enter();pg=term.pg
        try:
            pg.event.clear();term._set_input_mode("world")
            term._hover_context={"used":pg.Rect(10,10,100,100),"left":5,"top":7,"tile_px":10}
            pg.event.post(pg.event.Event(pg.MOUSEBUTTONDOWN,button=3,pos=(25,35)))
            self.assertEqual(term.read_key(),"UI_WORLD_MENU:6:9")
        finally:
            term.restore()


if __name__=="__main__":
    unittest.main()
