"""Crafting browser layout and read-only scrolling regressions on a real SDL surface."""
import copy
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.ui.widgets import MenuRow


@unittest.skipUnless(PygameTerminal.available(), 'requires pygame-ce')
class CraftingBrowserTests(unittest.TestCase):
    def setUp(self):
        self.term = PygameTerminal(1280, 800)
        self.term.enter()
        self.pg = self.term.pg
        self.pg.event.clear()
        self.term.clock = type('Clock', (), {'tick': lambda self, rate: None})()

    def tearDown(self):
        self.term.restore()

    def recipe(self, name='A carefully shaped stone crafting implement'):
        return {'name': name, 'ready': True, 'minutes': 20, 'skill': 'stone_work',
                'difficulty': 2, 'station': 'Stone workshop', 'description': 'Full recipe explanation. ' * 40,
                'missing': [], 'outputs': [{'id': 'core:stone_flake', 'name': 'Stone flake', 'qty': 2}],
                'inputs': [{'id': 'core:stone', 'name': f'Required stone material {index}', 'need': 2, 'have': 4}
                           for index in range(15)]}

    def data(self, count=20):
        rows = [MenuRow(f'recipe:{index}', f'Recipe {index}') for index in range(count)]
        data = {'recipes': {row.key: self.recipe() for row in rows},
                'categories': [f'profession_category_{index}' for index in range(14)],
                'category': 'profession_category_0', 'category_page': 0}
        return rows, data

    def render(self, rows, data, selected=0, page_start=0, total=None):
        self.term._present_crafting_unified('CRAFTING', rows, selected, data=data,
                                            page_start=page_start, total=total)

    def target(self, token):
        return next(rect for rect, value in self.term._pointer_targets if value == token)

    def test_minimum_and_standard_windows_have_exact_clickable_capacity(self):
        rows, data = self.data()
        for width, height in ((740, 500), (1080, 680)):
            with self.subTest(width=width, height=height):
                self.term._floating_panels['crafting'] = {'x': 12, 'y': 12, 'w': width, 'h': height}
                geometry = self.term._crafting_browser_geometry()
                capacity = geometry['capacity']
                self.render(rows[:capacity], data, total=len(rows))
                tokens = [value for _, value in self.term._pointer_targets if value.startswith('UI_SELECT:')]
                self.assertEqual(tokens, [f'UI_SELECT:{index}' for index in range(capacity)])
                for index in range(capacity):
                    rect = self.target(f'UI_SELECT:{index}')
                    self.assertTrue(geometry['list'].contains(rect))
                    self.assertLessEqual(rect.bottom, geometry['list'].bottom - 26)
                    self.assertEqual(self.term._hit_token(rect.center), f'UI_SELECT:{index}')
                self.assertIsNotNone(self.target('UI_SCROLL_TRACK'))
                data['categories'] = ['primitive']
                self.render(rows[:capacity], data, total=len(rows))
                self.assertEqual(self.term._crafting_browser_geometry()['capacity'], capacity)
                data['categories'] = [f'profession_category_{index}' for index in range(14)]

    def test_labelled_tabs_categories_and_search_never_overlap(self):
        self.term._floating_panels['crafting'] = {'x': 12, 'y': 12, 'w': 740, 'h': 500}
        rows, data = self.data()
        self.render(rows[:3], data, total=len(rows))
        tabs = [rect for rect, token in self.term._pointer_targets if token.startswith('UI_ACTION:tab:')]
        categories = [rect for rect, token in self.term._pointer_targets if token.startswith('UI_ACTION:category:')]
        search = self.target('UI_ACTION:search')
        self.assertEqual(len(tabs), 5)
        self.assertEqual(len(categories), 6)
        for index, rect in enumerate(tabs):
            self.assertGreater(rect.width, 40)
            self.assertFalse(rect.colliderect(search))
            self.assertTrue(all(not rect.colliderect(other) for other in tabs[index + 1:] + categories))
        for index, rect in enumerate(categories):
            self.assertTrue(all(not rect.colliderect(other) for other in categories[index + 1:]))
            self.assertLess(rect.bottom, self.term._crafting_browser_geometry()['body'].top)

    def test_long_category_hover_preserves_full_name(self):
        self.term._floating_panels['crafting'] = {'x': 12, 'y': 12, 'w': 740, 'h': 500}
        rows, data = self.data(1)
        self.render(rows, data)
        self.term._last_mouse = self.target('UI_ACTION:category:profession_category_0').center
        self.render(rows, data)
        self.assertEqual(self.term._crafting_tab_tooltip[0], 'Profession Category 0')

    def test_full_detail_scrolls_without_covering_pinned_craft_button(self):
        self.term._floating_panels['crafting'] = {'x': 12, 'y': 12, 'w': 740, 'h': 500}
        rows, data = self.data(1)
        before = copy.deepcopy(data)
        self.render(rows, data)
        key, viewport, maximum = self.term._panel_detail_view
        button = self.target('UI_ACTION:craft')
        self.assertGreater(maximum, 0)
        self.assertFalse(viewport.colliderect(button))
        self.assertEqual(self.term.screen.get_clip(), self.term.screen.get_rect())
        captured = self.pg.image.tobytes(self.term.screen.subsurface(button), 'RGB')
        self.term._panel_detail_states[key] = maximum
        self.render(rows, data)
        self.assertEqual(self.term._panel_detail_states[key], maximum)
        self.assertEqual(self.pg.image.tobytes(self.term.screen.subsurface(button), 'RGB'), captured)
        self.assertEqual(data, before)
        detail_lines = self.term._crafting_detail_lines(data['recipes'][rows[0].key])
        self.assertEqual(sum(line[0] == 'item' for line in detail_lines), 16)
        self.assertIn(data['recipes'][rows[0].key]['description'], [line[1] for line in detail_lines if line[0] == 'text'])

    def test_offscreen_selection_remains_the_detail_recipe(self):
        rows, data = self.data(8)
        data['selected_key'] = rows[-1].key
        with patch.object(self.term, '_panel_detail', wraps=self.term._panel_detail) as details:
            self.render(rows[:3], data, selected=-1, total=8)
        self.assertEqual(details.call_args.args[0], 'crafting:' + rows[-1].key)
        self.assertIsNotNone(self.target('UI_ACTION:craft'))

    def test_missing_recipe_has_full_requirements_and_no_craft_target(self):
        rows, data = self.data(1)
        recipe = data['recipes'][rows[0].key]
        recipe['ready'] = False
        recipe['missing'] = ['Stone 0/2', 'Requires a Stone workshop']
        self.render(rows, data)
        self.assertNotIn('UI_ACTION:craft', [value for _, value in self.term._pointer_targets])
        content = self.term._crafting_detail_lines(recipe)
        self.assertTrue(all(('text', missing, self.term._theme['danger']) in content for missing in recipe['missing']))


if __name__ == '__main__':
    unittest.main()
