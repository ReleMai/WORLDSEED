import unittest
from unittest.mock import patch

from tests import test_ui_rc2
from tests.test_interiors import sample_plan
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory, Vitals
from worldseed.sim.commands import MoveCommand, GatherCommand, DropCommand, PickupCommand
from worldseed.systems.interior_state import InteriorActor
from worldseed.systems.state import LivingWorldState
from worldseed.ui.renderer import Renderer


class InteriorEngineTests(unittest.TestCase):
    def setUp(self):
        fixture=test_ui_rc2.UIRC2Tests('test_environment_look_is_observational_and_does_not_plan')
        fixture.setUp();self.addCleanup(fixture.tearDown)
        self.sim=fixture.sim;self.fixture=fixture
        self.plan=sample_plan()
        self.sim.state.interiors[self.plan.uid]=self.plan
        self.sim.interiors._put_actor('player',InteriorActor(self.plan.uid,self.plan.entry_x,self.plan.entry_y))

    def test_move_is_fractional_without_discovering_outside(self):
        sim=self.sim;pos=sim.player_pos;discovered=list(sim.state.discovered_tiles);minute=sim.clock.minute
        sim.execute(MoveCommand(sim.player_id,1,-1))
        actor=sim.interiors.player_presence()
        self.assertEqual(actor.x,self.plan.entry_x+127)
        self.assertEqual(sim.player_pos,pos)
        self.assertEqual(sim.clock.minute,minute)
        self.assertEqual(sim.state.discovered_tiles,discovered)

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
