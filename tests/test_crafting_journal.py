"""Discovery results survive redraws and saves without leaking unknown recipes."""
import copy
from types import SimpleNamespace
import unittest

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.entities.components import Inventory
from worldseed.persistence.validation import validate_sim_state
from worldseed.systems.crafting import CraftingSystem
from worldseed.systems.state import LivingWorldState
from worldseed.ui.crafting_journal import crafting_journal_data


class CraftingJournalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)

    def fixture(self):
        state = LivingWorldState(player_crafting_discovery_enabled=True)
        inv = Inventory({'core:stone': 6})
        crafting = CraftingSystem(state, self.registry)
        ok, message, _ = crafting.combine_in_pot(('core:stone',), inv, b'journal-fixture', minute=500)
        self.assertTrue(ok, message)
        return state, inv, crafting

    def test_success_records_bounded_chronology_and_roundtrips_without_aliasing(self):
        state, inv, crafting = self.fixture()
        self.assertEqual(len(state.player_crafting_log), 1)
        entry = state.player_crafting_log[-1]
        self.assertEqual(entry['minute'], 500)
        self.assertEqual(entry['ingredients'], ['core:stone'])
        self.assertIn(entry['recipe_id'], state.player_discovered_recipes)
        raw = state.to_dict()
        restored = LivingWorldState.from_dict(raw)
        raw['player_crafting_log'][0]['ingredients'].clear()
        self.assertEqual(restored.player_crafting_log, state.player_crafting_log)
        state.player_crafting_log *= 100
        self.assertEqual(len(state.to_dict()['player_crafting_log']), 80)
        self.assertEqual(validate_sim_state(restored.to_dict()), [])
        self.assertEqual(LivingWorldState.from_dict({}).player_crafting_log, [])

    def test_failed_experiment_does_not_replace_latest_result(self):
        state, inv, crafting = self.fixture()
        before = copy.deepcopy(state.player_crafting_log)
        self.assertFalse(crafting.combine_in_pot(('core:missing',), inv, b'journal-fixture')[0])
        self.assertEqual(state.player_crafting_log, before)

    def test_projection_is_read_only_and_filters_unknown_history(self):
        state, inv, crafting = self.fixture()
        known = state.player_discovered_recipes[0]
        state.player_crafting_log.append({'recipe_id': 'core:iron_axe', 'minute': 600, 'ingredients': ['core:stone']})
        before = state.to_dict()
        data = crafting_journal_data(self.registry, state)
        self.assertEqual(data['latest_result']['id'], known)
        self.assertEqual([row['id'] for row in data['learned_history']], [known])
        self.assertEqual(before, state.to_dict())
        state.player_crafting_log.clear()
        self.assertIsNone(crafting_journal_data(self.registry, state)['latest_result'])
        self.assertEqual(crafting_journal_data(self.registry, state)['learned_count'], 1)

    def test_controller_keeps_latest_across_grid_edits_and_dismisses_explicitly(self):
        from worldseed.app import _crafting_menu_graphical
        state = LivingWorldState(player_crafting_discovery_enabled=True)
        inv = Inventory({'core:stone': 6})
        crafting = CraftingSystem(state, self.registry)
        frames = []
        class Term:
            mouse_ui = True
            def __init__(self):
                self.keys = iter(('UI_SELECT:0', 'UI_ACTION:mix', 'UI_SELECT:0', 'UI_ACTION:clear',
                                  'UI_ACTION:dismiss_result', 'ESC'))
            def size(self):return 100, 30
            def menu_page_size(self, presentation):return 5
            def present_feature_menu(self, presentation, *args, **kwargs):
                frames.append(copy.deepcopy(kwargs['data']))
            def read_key(self):return next(self.keys)
        sim = SimpleNamespace(state=state, crafting=crafting, player_pos=None,
                              building=SimpleNamespace(nearby_station_ids=lambda pos: set()), log=[])
        def execute(command):
            ok, message, _ = crafting.combine_in_pot(command.items, inv, b'journal-fixture', minute=500)
            sim.log.append(SimpleNamespace(message=message))
        sim.execute = execute
        ctx = SimpleNamespace(sim=sim, registry=self.registry, player_id=1,
                              entities=SimpleNamespace(get=lambda actor, component: inv))
        _crafting_menu_graphical(ctx, Term(), initial_tab='discovery')
        self.assertIsNone(frames[0]['latest_result'])
        self.assertTrue(frames[2]['latest_result'])
        self.assertEqual(frames[2]['latest_result'], frames[3]['latest_result'])
        self.assertEqual(frames[2]['latest_result'], frames[4]['latest_result'])
        self.assertIsNone(frames[5]['latest_result'])
        self.assertEqual(len(frames[5]['learned_history']), 1)

    def test_verifier_rejects_unknown_or_malformed_discovery_records(self):
        state, inv, crafting = self.fixture()
        raw = state.to_dict()
        for bad in (None, {}, [{}], [{'recipe_id': 'unknown:item', 'minute': -1, 'ingredients': []}]):
            with self.subTest(value=bad):
                raw['player_crafting_log'] = bad
                self.assertTrue(any('crafting discovery history' in issue for issue in validate_sim_state(raw)))


if __name__ == '__main__':
    unittest.main()
