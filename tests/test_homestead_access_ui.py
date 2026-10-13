"""Cabin access uses existing commands and shared menus in both backends."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tests import test_interior_engine as engine_fixtures
from tests.test_ui_rc2 import _fake_term
from worldseed import app
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Position
from worldseed.systems.homestead_access import ensure_access
from worldseed.systems.homestead_blueprints import doorway, door_uid


class HomesteadAccessUITests(unittest.TestCase):
    prepared_simulation = engine_fixtures.InteriorEngineTests.prepared_simulation

    def setUp(self):
        self.sim, _ = self.prepared_simulation()
        self.sim.interiors._remove_actor('player')
        self.site = {
            'uid': 'homestead:ui', 'home_id': 'log_cabin', 'style_id': 'log_cabin_01',
            'x': 4, 'y': 4, 'z': 0, 'orientation': 0, 'owner_uid': 'player',
            'stage': 4, 'stored': {}, 'revision': 4,
        }
        self.sim.state.homesteads[self.site['uid']] = self.site
        self.door = ensure_access(self.sim, self.site)
        self.sim.entities.get(self.sim.player_id, Position).value = WorldPos(*doorway(self.site)[1])
        self.ctx = SimpleNamespace(sim=self.sim, entities=self.sim.entities,
                                   player_id=self.sim.player_id, registry=self.sim.registry)

    def test_action_hub_enters_from_exact_outside_doorway(self):
        term = _fake_term(['1', '1'])
        result = app._action_palette(self.ctx, term)
        self.assertIn('enter', result.lower())
        self.assertIn('Enter your log cabin', '\n'.join(term.frames))
        plan = self.sim.interiors.current_plan()
        self.assertEqual(plan.building_id, self.site['uid'])
        self.assertEqual(plan.door_uid, door_uid(self.site))
        self.assertEqual(plan.furniture, [])

    def test_action_hub_escape_restores_parent_without_mutating_state(self):
        before = deepcopy(self.sim.state.to_dict())
        term = _fake_term(['1', 'ESC', 'ESC'])
        self.assertEqual(app._action_palette(self.ctx, term), '')
        self.assertIn('Enter your log cabin', '\n'.join(term.frames))
        self.assertEqual(len(term.frames), 3)
        self.assertEqual(self.sim.state.to_dict(), before)

    def test_action_hub_does_not_offer_entry_from_another_side(self):
        self.sim.entities.get(self.sim.player_id, Position).value = WorldPos(3, 6, 0)
        term = _fake_term(['1', 'ESC', 'ESC'])
        app._action_palette(self.ctx, term)
        self.assertNotIn('Enter your log cabin', '\n'.join(term.frames))

    def test_completed_depot_uses_shared_enter_menu_for_both_backends(self):
        for graphical in (False, True):
            with self.subTest(graphical=graphical):
                term = _fake_term(['ESC'])
                if graphical:
                    term.present_homestead_depot = Mock(side_effect=AssertionError('unfinished depot'))
                before = deepcopy(self.sim.state.to_dict())
                self.assertEqual(app._homestead_blueprint_panel(self.ctx, term, self.site['uid']), app.UI_BACK)
                self.assertIn('Enter your log cabin', term.frames[0])
                self.assertIn('4, 7', term.frames[0])
                self.assertEqual(self.sim.state.to_dict(), before)

    def test_completed_depot_enter_dispatches_existing_portal_command(self):
        term = _fake_term(['1'])
        self.assertIn('enter', app._homestead_blueprint_panel(self.ctx, term, self.site['uid']).lower())
        self.assertEqual(self.sim.interiors.current_plan().building_id, self.site['uid'])

    def test_world_door_context_offers_entry_without_preparing_an_interior(self):
        before = deepcopy(self.sim.state.to_dict())
        with patch.object(app, '_select', return_value=None) as menu:
            app._world_context_menu(self.ctx, _fake_term([]), WorldPos(*doorway(self.site)[0]))
        options = dict(menu.call_args.args[2])
        self.assertIn('enter_interior', options)
        self.assertEqual(self.sim.state.to_dict(), before)


if __name__ == '__main__':
    unittest.main()
