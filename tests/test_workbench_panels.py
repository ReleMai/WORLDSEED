"""Discovery/workshop rendering stays bounded, readable and observational."""
import copy
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.ui.widgets import MenuRow


@unittest.skipUnless(PygameTerminal.available(), 'requires pygame-ce')
class WorkbenchPanelTests(unittest.TestCase):
    def setUp(self):
        self.term = PygameTerminal(1280, 800)
        self.term.enter()
        self.pg = self.term.pg
        self.pg.event.clear()
        self.term.clock = type('Clock', (), {'tick': lambda self, rate: None})()

    def tearDown(self):
        self.term.restore()

    def panel(self, width=740, height=500):
        self.term._floating_panels['crafting'] = {'x': 12, 'y': 12, 'w': width, 'h': height}

    def target(self, token):
        return next(rect for rect, value in self.term._pointer_targets if value == token)

    def discovery_data(self, count=40):
        entries = {f'material:{index}': {'name': 'A useful carried crafting material', 'count': 8,
                   'pool_count': 8, 'known_recipes': ['Known technique']} for index in range(count)}
        rows = [MenuRow(key, item['name']) for key, item in entries.items()]
        data = {'items': entries, 'selected_items': (rows[0].key,) * 5 if rows else (),
                'mix_state': 'green' if rows else 'red', 'known_exact': [],
                'latest_result': {'id': 'recipe:last', 'name': 'Plant cordage from recovered wild fibers',
                                  'outputs': [{'id': 'core:brush', 'name': 'Plant fiber', 'qty': 2}]},
                'learned_history': [{'id': f'recipe:{index}', 'name': f'Learned crafting technique {index}',
                                     'outputs': [{'id': 'core:brush', 'name': 'Plant fiber', 'qty': 2}]}
                                    for index in range(30)], 'learned_count': 30}
        return rows, data

    def workshop_data(self, count=12):
        recipe = {'name': 'A useful workshop crafting technique', 'minutes': 30, 'skill': 'woodcraft',
                  'ready': True, 'inputs': [{'id': 'core:wood', 'name': f'Timber component {index}',
                  'have': 5, 'need': 2} for index in range(12)],
                  'outputs': [{'id': 'core:wood', 'name': 'Shaped timber', 'qty': 2}], 'description': 'Process details. ' * 40}
        recipes = {f'recipe:{index}': copy.deepcopy(recipe) for index in range(count)}
        rows = [MenuRow(key, value['name']) for key, value in recipes.items()]
        data = {'recipes': recipes, 'known_count': count, 'locked_count': 5,
                'profile': {'title': "CARPENTER'S WORKBENCH", 'purpose': 'Shape timber using real carried materials.', 'action_label': 'BUILD'},
                'stations': [{'station_id': f'station:{index}', 'title': f'Physical workshop {index}'} for index in range(9)],
                'station_id': 'station:0', 'station_page': 0}
        return rows, data

    def test_discovery_grid_capacity_and_five_slots_fit_both_windows(self):
        rows, data = self.discovery_data()
        for width, height in ((740, 500), (900, 620)):
            self.panel(width, height)
            geometry = self.term._discovery_browser_geometry()
            capacity = self.term.menu_page_size('discovery_pot')
            self.assertEqual(capacity, geometry['capacity'])
            self.assertEqual(self.term.menu_grid_columns('discovery_pot'), geometry['columns'])
            self.term.present_feature_menu('discovery_pot', 'Discovery', rows[:capacity], 0, data=data, total=len(rows))
            for index in range(capacity):
                rect = self.target(f'UI_SELECT:{index}')
                self.assertTrue(geometry['grid'].contains(rect))
                self.assertLessEqual(rect.bottom, geometry['grid'].bottom - 26)
            for index in range(5):
                self.assertTrue(geometry['experiment'].contains(self.target(f'UI_ACTION:remove_slot:{index}')))
            self.assertTrue(geometry['experiment'].contains(self.target('UI_ACTION:mix')))
            self.assertFalse(self.target('UI_ACTION:mix').colliderect(geometry['journal']))

    def test_latest_result_stays_visible_while_history_scrolls(self):
        self.panel()
        rows, data = self.discovery_data()
        before = copy.deepcopy(data)
        self.term.present_feature_menu('discovery_pot', 'Discovery', rows[:4], 0, data=data, total=len(rows))
        key, viewport, maximum = self.term._panel_detail_view
        self.assertEqual(key, 'discovery:learned-history')
        self.assertGreater(maximum, 0)
        journal = self.term._discovery_browser_geometry()['journal']
        pinned = self.pg.Rect(journal.x, journal.y, journal.width, 80)
        pixels = self.pg.image.tobytes(self.term.screen.subsurface(pinned), 'RGB')
        self.term._panel_detail_states[key] = maximum
        self.term.present_feature_menu('discovery_pot', 'Discovery', rows[:4], 0, data=data, total=len(rows))
        self.assertEqual(pixels, self.pg.image.tobytes(self.term.screen.subsurface(pinned), 'RGB'))
        self.assertIsNotNone(self.target('UI_ACTION:dismiss_result'))
        self.assertGreaterEqual(viewport.y, pinned.bottom)
        self.assertEqual(data, before)

    def test_selected_material_retains_tags_and_all_learned_uses(self):
        self.panel()
        rows, data = self.discovery_data()
        item = data['items'][rows[0].key]
        item['tags'] = ['plant_scraps', 'fiber']
        item['known_recipes'] = ['Plant cordage', 'Woven cloth', 'Braided sling']
        item['possible_recipes'] = ['Hidden technique']
        with patch.object(self.term, '_panel_detail', wraps=self.term._panel_detail) as detail:
            self.term.present_feature_menu('discovery_pot', 'Discovery', rows[:4], 0, data=data, total=len(rows))
        lines = detail.call_args.args[2]
        texts = [entry[1] for entry in lines if entry[0] == 'text']
        self.assertIn('Tags: Plant Scraps · Fiber', texts)
        self.assertTrue(all(name in texts for name in item['known_recipes']))
        self.assertNotIn('Hidden technique', texts)

    def test_empty_discovery_and_workshops_have_no_phantom_item_targets(self):
        self.panel()
        self.term.present_feature_menu('discovery_pot', 'Discovery', [MenuRow('__none__', 'None')], 0, data={'items': {}})
        self.assertFalse(any(value.startswith('UI_SELECT:') for _, value in self.term._pointer_targets))
        self.assertNotIn('UI_ACTION:mix', [value for _, value in self.term._pointer_targets])
        self.term.present_feature_menu('workshop_station', 'Workshops', [MenuRow('__none__', 'None')], 0, data={})
        self.assertFalse(any(value.startswith('UI_SELECT:') for _, value in self.term._pointer_targets))
        self.assertNotIn('UI_ACTION:workshop_craft', [value for _, value in self.term._pointer_targets])

    def test_workshop_true_counts_capacity_and_scrollable_details(self):
        rows, data = self.workshop_data()
        before = copy.deepcopy(data)
        for width, height in ((740, 500), (900, 620)):
            self.panel(width, height)
            capacity = self.term.menu_page_size('workshop_station')
            with patch.object(self.term, '_panel_text', wraps=self.term._panel_text) as write:
                self.term.present_feature_menu('workshop_station', 'Workshops', rows[:capacity], 0, data=data, total=len(rows))
            self.assertIn('12 KNOWN · 5 UNDISCOVERED', [call.args[0] for call in write.call_args_list])
            geometry = self.term._workshop_browser_geometry()
            for index in range(capacity):
                rect = self.target(f'UI_SELECT:{index}')
                self.assertTrue(geometry['list'].contains(rect))
                self.assertLessEqual(rect.bottom, geometry['list'].bottom - 24)
            _, viewport, maximum = self.term._panel_detail_view
            self.assertGreater(maximum, 0)
            self.assertFalse(viewport.colliderect(self.target('UI_ACTION:workshop_craft')))
            self.assertIsNotNone(self.target('UI_SCROLL_TRACK'))
        self.assertEqual(data, before)

    def test_station_pages_show_four_then_final_station_with_stable_body(self):
        self.panel()
        rows, data = self.workshop_data()
        self.term.present_feature_menu('workshop_station', 'Workshops', rows[:3], 0, data=data, total=len(rows))
        geometry = self.term._workshop_browser_geometry()
        tokens = [value for _, value in self.term._pointer_targets if value.startswith('UI_ACTION:workshop:')]
        self.assertEqual(len(tokens), 4)
        data['station_page'] = 2
        self.term.present_feature_menu('workshop_station', 'Workshops', rows[:3], 0, data=data, total=len(rows))
        tokens = [value for _, value in self.term._pointer_targets if value.startswith('UI_ACTION:workshop:')]
        self.assertEqual(tokens, ['UI_ACTION:workshop:station:8'])
        self.assertEqual(geometry, self.term._workshop_browser_geometry())


if __name__ == '__main__':
    unittest.main()

