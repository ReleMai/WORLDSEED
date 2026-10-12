"""Material previews, instance details and quantity quotes reflect command authority."""
from copy import copy, deepcopy
from types import SimpleNamespace
import os
import unittest

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

from worldseed.app import _inventory_ui_data, _recipe_ui_data
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry, RecipeDef
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory
from worldseed.systems.artifacts import ArtifactSystem
from worldseed.systems.crafting import CraftingSystem
from worldseed.systems.state import LivingWorldState
from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.ui.trade_quotes import max_affordable_trade, trade_total
from worldseed.ui.widgets import MenuRow


class MaterialQualityReadModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)

    def simulation(self, recipe=None, *, discovery=False):
        registry = copy(self.registry)
        registry.recipes = dict(registry.recipes)
        if recipe:
            registry.recipes[recipe.id] = recipe
        state = LivingWorldState(player_crafting_discovery_enabled=discovery)
        artifacts = ArtifactSystem(state, registry, b'quality-ui')
        sim = SimpleNamespace(state=state, player_pos=WorldPos(0, 0), artifacts=artifacts,
                              building=SimpleNamespace(nearby_station_ids=lambda pos: set(),
                                  nearby_container=lambda pos: None,
                                  environmental_bonuses=lambda pos: {'work_bonus': 2}),
                              player_skill=lambda skill: 3)
        sim.crafting = CraftingSystem(state, registry, artifacts)
        return registry, sim

    def test_exact_preview_matches_crafted_quality_and_is_observational(self):
        registry, sim = self.simulation()
        recipe = registry.recipes['core:stone_knife']
        inv = Inventory({'core:stone_flake': 1, 'core:tool_handles': 1,
                         'core:hardwood_blank': 1, 'core:plant_cordage': 1})
        before = deepcopy(sim.state.to_dict()), dict(inv.items)
        row = _recipe_ui_data(registry, sim, inv, [recipe], material_preference='refined')['recipes'][recipe.id]
        self.assertEqual((sim.state.to_dict(), inv.items), before)
        self.assertTrue(row['ready'], row['missing'])
        self.assertEqual(row['material_preference'], 'refined')
        self.assertEqual(row['consumed']['core:hardwood_blank'], 1)
        self.assertNotIn('core:tool_handles', row['consumed'])
        self.assertEqual(sum(item['qty'] for item in row['consumed_items']), sum(row['consumed'].values()))
        output = row['outputs'][0]
        self.assertTrue(any('Durability' in benefit for benefit in output['benefits']))
        ok, message, _ = sim.crafting.craft(recipe.id, inv, set(), skill_level=3, work_bonus=2, preference='refined')
        self.assertTrue(ok, message)
        crafted = next(artifact for artifact in sim.state.artifacts.values() if artifact.base_item == output['id'])
        self.assertEqual(crafted.quality, output['quality'])
        self.assertEqual(crafted.material, output['material'])
        self.assertEqual(crafted.components['crafting']['ingredients'], row['consumed_items'])

    def test_indoor_preview_uses_the_command_station_bonus_rule(self):
        registry, sim = self.simulation()
        recipe = registry.recipes['core:stone_knife']
        inv = Inventory({'core:stone_flake': 1, 'core:tool_handles': 1, 'core:plant_cordage': 1})
        sim.interiors = SimpleNamespace(player_presence=lambda: {}, station_ids_near_player=lambda: set())
        row = _recipe_ui_data(registry, sim, inv, [recipe])['recipes'][recipe.id]
        expected = sim.crafting.preview(recipe, inv, skill_level=3, work_bonus=0)
        self.assertEqual(row['outputs'][0]['quality'], expected['outputs'][0]['quality'])

    def test_equivalent_units_are_not_displayed_as_physical_consumption(self):
        recipe = RecipeDef('test:units', 'Useful recovered handle', {}, {'core:stone_knife': 1}, 5,
                           input_tags={'short_haft': 4}, input_units={'core:tool_handles': 2}, material_quality=True)
        registry, sim = self.simulation(recipe)
        inv = Inventory({'core:tool_handles': 2})
        row = _recipe_ui_data(registry, sim, inv, [recipe])['recipes'][recipe.id]
        self.assertEqual(row['inputs'][0]['allocated'], {'core:tool_handles': 4})
        self.assertEqual(row['inputs'][0]['unit_label'], 'material units')
        self.assertEqual(row['consumed'], {'core:tool_handles': 2})
        self.assertEqual(sum(item['qty'] for item in row['consumed_items']), 2)

    def test_alternatives_do_not_reveal_unseen_material_names(self):
        recipe = self.registry.recipes['core:stone_knife']
        registry, sim = self.simulation(discovery=True)
        sim.state.player_discovered_recipes.append(recipe.id)
        inv = Inventory({'core:tool_handles': 1})
        before = deepcopy(sim.state.to_dict())
        row = _recipe_ui_data(registry, sim, inv, [recipe])['recipes'][recipe.id]
        options = {option['id'] for ingredient in row['inputs'] for option in ingredient.get('options', ())}
        self.assertEqual(options, {'core:tool_handles'})
        self.assertEqual(sim.state.to_dict(), before)

    def test_inventory_preserves_every_instance_and_actual_effects(self):
        registry, sim = self.simulation()
        iid = 'core:stone_knife'
        for index in range(4):
            grade = 40 + 10 * index
            artifact = sim.artifacts.create(iid, 'player', index, quality_hint=grade,
                components_override={'body': {'material': 'core:stone', 'quality': grade, 'condition': 100},
                    'crafting': {'quality_version': 1, 'source': 'recovered',
                        'ingredients': [{'id': 'core:tool_handles', 'qty': 1, 'quality': 45, 'source': 'recovered'}]}})
            artifact.name = f'Individual knife {index}'
        inv = Inventory({iid: 4})
        before = deepcopy(sim.state.to_dict())
        details = _inventory_ui_data(registry, inv, sim)['items'][iid]['detail_lines']
        for index in range(4):
            self.assertTrue(any(line.startswith(f'Individual knife {index}:') for line in details))
        self.assertEqual(sum(line.startswith('Effective quality ') for line in details), 4)
        self.assertEqual(sum(line.startswith('Input: ') for line in details), 4)
        self.assertTrue(any('Trade value ×1.20' in line for line in details))
        self.assertEqual(sim.state.to_dict(), before)


class QuantityQuoteTests(unittest.TestCase):
    def test_affordable_max_uses_cumulative_mixed_quality_prices(self):
        calls = []
        def quote(sid, iid, buy, amount):
            calls.append(amount)
            return 0 if not amount else 15 + 5 * (amount - 1)
        sim = SimpleNamespace(player_trade_total=quote)
        self.assertEqual(max_affordable_trade(sim, 'town', 'knife', 1000, 30), 4)
        self.assertLessEqual(len(calls), 5)
        self.assertEqual(trade_total(sim, 'town', 'knife', True, 4), 30)
        self.assertEqual(max_affordable_trade(sim, 'town', 'knife', 1000, 14), 0)
        self.assertEqual(max_affordable_trade(sim, 'town', 'knife', 2, 30), 2)

    def test_legacy_fixture_quotes_remain_supported(self):
        sim = SimpleNamespace(player_trade_price=lambda sid, iid, buy: 7)
        self.assertEqual(trade_total(sim, 'town', 'knife', False, 3), 21)
        self.assertEqual(max_affordable_trade(sim, 'town', 'knife', 100, 24), 3)


@unittest.skipUnless(PygameTerminal.available(), 'requires pygame-ce')
class MaterialPreferenceLayoutTests(unittest.TestCase):
    def setUp(self):
        self.term = PygameTerminal(1280, 800)
        self.term.enter()
        self.term.pg.event.clear()
        self.term.clock = type('Clock', (), {'tick': lambda self, rate: None})()

    def tearDown(self):
        self.term.restore()

    def target(self, token):
        return next(rect for rect, value in self.term._pointer_targets if value == token)

    def test_preference_and_action_stay_outside_scrolling_details(self):
        recipe = {'name': 'Shaped crafting tool', 'ready': True, 'minutes': 20,
                  'material_preference_enabled': True, 'material_preference': 'refined',
                  'material_quality_enabled': True, 'material_quality': 72, 'material_source': 'Mixed materials',
                  'outputs': [{'id': 'core:stone_knife', 'name': 'Stone knife', 'qty': 1, 'quality': 80,
                               'benefits': ['Damage ×1.60', 'Durability ×1.30', 'Trade value ×1.30']}],
                  'inputs': [{'id': 'core:tool_handles', 'name': 'Recovered handles', 'have': 8, 'need': 4,
                              'unit_label': 'material units'}],
                  'consumed': {'core:tool_handles': 2},
                  'consumed_items': [{'id': 'core:tool_handles', 'name': 'Recovered handles', 'qty': 2,
                                      'quality': 45, 'source': 'recovered'}],
                  'description': 'A full manufacturing explanation. ' * 80}
        data = {'recipes': {'recipe': recipe}, 'known_count': 1, 'station_id': 'station',
                'stations': [{'station_id': 'station', 'title': 'Physical workshop'}]}
        rows = [MenuRow('recipe', recipe['name'])]
        before = deepcopy(data)
        for width, height in ((740, 500), (1080, 680)):
            self.term._floating_panels['crafting'] = {'x': 12, 'y': 12, 'w': width, 'h': height}
            for feature, token in (('crafting_unified', 'UI_ACTION:craft'), ('workshop_station', 'UI_ACTION:workshop_craft')):
                with self.subTest(size=(width, height), feature=feature):
                    self.term.present_feature_menu(feature, 'Crafting', rows, 0, data=data, total=1)
                    preference = self.target('UI_ACTION:material_preference')
                    action = self.target(token)
                    key, viewport, maximum = self.term._panel_detail_view
                    self.assertLessEqual(viewport.bottom, preference.top)
                    self.assertLessEqual(preference.bottom, action.top)
                    self.assertFalse(preference.colliderect(action))
                    self.assertGreater(maximum, 0)
                    self.term._panel_detail_states[key] = maximum
                    self.term.present_feature_menu(feature, 'Crafting', rows, 0, data=data, total=1)
                    self.assertEqual(self.term._panel_detail_view[2], maximum)
                    labels = [str(line[2] if line[0] == 'item' else line[1])
                              for line in self.term._crafting_detail_lines(recipe)]
                    self.assertTrue(any('Quality 80/100' in label for label in labels))
                    self.assertTrue(any('Recovered handles ×2' in label for label in labels))
                    self.assertEqual(data, before)


if __name__ == '__main__':
    unittest.main()
