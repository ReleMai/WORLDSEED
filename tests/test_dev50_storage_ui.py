"""Indoor storage menus respect physical reach, locks and theft commands."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from tests import test_dev50_interior_storage as fixtures
from worldseed import app
from worldseed.entities.components import Inventory
from worldseed.sim.commands import StealContainerCommand, UseInteriorFurnitureCommand
from worldseed.systems.interior_state import InteriorActor


class IndoorStorageMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.InteriorStorageTests.setUpClass()

    def setUp(self):
        self.sim, town, storage = fixtures.InteriorStorageTests().fixture()
        house = next(s for s in self.sim.settlement_physicalization.skeleton_for(town.uid).structures
                     if s.function == 'residence')
        self.plan = self.sim.interiors.prepare_workplace(house.uid)
        self.container = next(c for c in storage.for_property(house.uid) if c.uid == 'property-storage:'+house.uid)
        self.furniture = next(f for f in self.plan.furniture if f.uid == self.container.interior_furniture_uid)
        self.actor = InteriorActor(self.plan.uid, *self.sim.interiors.fixture_use_position(self.plan, self.furniture))
        self.sim.interiors._put_actor('player', self.actor)
        self.sim.known_npc_ids = lambda: set()
        self.sim.player_pos = NS(x=0, y=0, z=0)
        self.sim.log = []
        self.commands = []
        self.sim.execute = self.commands.append
        self.ctx = NS(sim=self.sim, player_id=1, registry=self.sim.registry,
                      entities=NS(get=lambda *_: Inventory()))
        self.term = NS(size=lambda: (100, 35))

    def menu_rows(self):
        rows = []
        def select(term, title, values, **kwargs):
            rows.extend(values)
            return None
        with patch.object(app, '_select', select):
            app._interior_context_menu(self.ctx, self.term,
                                       self.furniture.x + self.furniture.w // 2,
                                       self.furniture.y + self.furniture.h // 2)
        return dict(rows)

    def test_locked_storage_has_no_open_or_pick_action_in_normal_stance(self):
        self.container.locked = True
        self.sim.state.player_hunting_stance = 'normal'
        before = self.sim.state.to_dict()
        rows = self.menu_rows()
        self.assertIn('inspect_storage', rows)
        self.assertNotIn('open_storage', rows)
        self.assertNotIn('pick_storage', rows)
        self.assertEqual(before, self.sim.state.to_dict())
        self.sim.state.player_hunting_stance = 'aggressive'
        self.assertIn('pick_storage', self.menu_rows())

    def test_far_or_wrong_space_container_cannot_be_opened(self):
        self.container.locked = False
        self.actor.space_id = 'interior:other'
        self.assertNotIn('open_storage', self.menu_rows())
        self.assertIn('Move closer', app._container_reach_error(self.sim, self.container))

    def test_user_selected_open_observes_real_furniture_then_opens_bound_inventory(self):
        self.container.locked = False
        with patch.object(app, '_select', return_value='open_storage'), \
             patch.object(app, '_storage_menu', return_value='opened') as opened:
            result = app._interior_context_menu(self.ctx, self.term,
                                               self.furniture.x + 10, self.furniture.y + 10)
        self.assertEqual(result, 'opened')
        self.assertEqual(self.commands, [UseInteriorFurnitureCommand(1, self.furniture.uid)])
        opened.assert_called_once_with(self.ctx, self.term, self.container.uid)

    def test_private_terminal_take_dispatches_theft_not_authorized_transfer(self):
        self.container.locked = False
        self.sim.state.player_hunting_stance = 'stalk'
        self.container.items = {'core:wheat': 2}
        with patch.object(app, '_stack_menu', side_effect=['take', 'core:wheat']):
            app._storage_menu_terminal(self.ctx, self.term, self.container.uid)
        self.assertEqual(self.commands, [StealContainerCommand(1, self.container.uid, 'core:wheat', 1)])


if __name__ == '__main__':
    unittest.main()
