"""SDL dummy regressions for the inventory browser's visible input contract."""
from __future__ import annotations

import copy
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

from tools.preview_item_browsers import inventory_fixture
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.ui.pygame_terminal import PygameTerminal


@unittest.skipUnless(PygameTerminal.available(), 'requires pygame-ce')
class InventoryBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)

    def setUp(self):
        self.term = PygameTerminal(1280, 800)
        self.term.enter()
        self.pg = self.term.pg
        self.pg.event.clear()
        self.rows, self.data = inventory_fixture(self.registry)

    def tearDown(self):
        self.term.restore()

    def configure_panel(self, size):
        width, height = size
        if width > self.term.screen.get_width() - 32 or height > self.term.screen.get_height() - 32:
            self.term.screen = self.pg.display.set_mode((width + 32, height + 32))
        self.term._floating_panels['inventory_unified'] = {'x': 16, 'y': 16, 'w': width, 'h': height}

    def render(self, *, start=0, selected=0):
        capacity = self.term.menu_page_size('inventory_unified')
        self.term.present_feature_menu('inventory_unified', 'INVENTORY', self.rows[start:start + capacity],
                                       selected, page_start=start, total=len(self.rows), data=self.data)
        return capacity

    def target(self, token):
        return next(rect for rect, value in self.term._pointer_targets if value == token)

    def emit(self, event, **kwargs):
        self.pg.event.clear()
        self.pg.event.post(self.pg.event.Event(event, **kwargs))
        # A sentinel means a regression reports a failed assertion instead of
        # hanging inside SDL's input wait when an event is accidentally ignored.
        self.pg.event.post(self.pg.event.Event(self.pg.KEYDOWN, key=self.pg.K_ESCAPE, unicode=''))
        return self.term.read_key()

    def test_visible_capacity_and_controls_fit_minimum_standard_and_maximized(self):
        for size in ((640, 440), (900, 620), (1888, 1048)):
            with self.subTest(size=size):
                self.configure_panel(size)
                capacity = self.render()
                state = self.term._floating_panels['inventory_unified']
                panel = self.pg.Rect(state['x'], state['y'], state['w'], state['h'])
                cards = [(rect, token) for rect, token in self.term._pointer_targets if token.startswith('UI_SELECT:')]
                self.assertEqual(len(cards), capacity, 'Every menu row must have a visible click target')
                for rect, token in self.term._pointer_targets:
                    self.assertTrue(panel.contains(rect), f'{token} extends outside panel: {rect}')
                for rect, token in cards:
                    self.assertEqual(self.term._hit_token(rect.center), token)
                self.assertGreaterEqual(self.term.menu_grid_columns('inventory_unified'), 2)

    def test_long_item_names_receive_two_lines_below_icons(self):
        self.configure_panel((640, 440))
        with patch.object(self.term, '_panel_text', wraps=self.term._panel_text) as render_text:
            self.render()
        first_name = self.data['items'][self.rows[0].key]['name']
        calls = [call for call in render_text.call_args_list if call.args[0] == first_name]
        self.assertTrue(calls)
        text_rect = self.pg.Rect(calls[0].args[1])
        self.assertEqual(calls[0].kwargs.get('max_lines'), 2)
        self.assertGreaterEqual(text_rect.height, 2 * self.term.small_font.get_linesize())
        self.assertGreaterEqual(len(self.term._wrap_pixel_text(first_name, self.term.small_font, text_rect.width)), 2)
        card = self.target('UI_SELECT:0')
        self.assertTrue(card.contains(text_rect))
        self.assertGreater(text_rect.y, card.y + 58)

    def test_real_sprite_alpha_is_cropped_and_scaled_without_stretching(self):
        self.configure_panel((900, 620))
        # The fixture is real registry content; choose an elongated item sprite
        # to catch stretching that a square icon would conceal.
        chosen = None
        for row in self.rows:
            path = self.term._visuals.resolve(self.term._visuals.ref('items', row.key))
            source = self.pg.image.load(str(path)).convert_alpha()
            bounds = source.get_bounding_rect(min_alpha=8)
            if bounds.width and bounds.height and abs(bounds.width - bounds.height) > 5:
                chosen = row.key, path, bounds
                break
        self.assertIsNotNone(chosen)
        item_id, path, bounds = chosen
        rect = self.pg.Rect(50, 50, 72, 72)
        self.term._panel_item_icon(item_id, rect)
        sprite = self.term._panel_icon_cache[(str(path), rect.width, rect.height)]
        scale = min((rect.width - 8) / bounds.width, (rect.height - 8) / bounds.height)
        self.assertLessEqual(abs(sprite.get_width() - bounds.width * scale), 1)
        self.assertLessEqual(abs(sprite.get_height() - bounds.height * scale), 1)
        self.assertGreaterEqual(max(sprite.get_size()), rect.width - 9)

    def test_hover_redraw_keeps_selected_item_and_action_target_stable(self):
        self.configure_panel((900, 620))
        before = copy.deepcopy(self.data)
        self.render()
        second = self.target('UI_SELECT:1')
        self.assertEqual(self.emit(self.pg.MOUSEMOTION, pos=second.center, rel=(1, 0), buttons=(0, 0, 0)), 'UI_REDRAW')
        self.render()
        self.assertEqual(self.term._panel_detail_view[0], 'inventory:' + self.rows[0].key)
        self.assertEqual(self.term._hit_token(self.target('UI_ACTION:drop').center), 'UI_ACTION:drop')
        self.assertEqual(self.data, before)
        first = self.target('UI_SELECT:0')
        self.assertEqual(self.term.screen.get_at((first.centerx, first.y))[:3], self.term._theme['accent'])
        self.assertNotEqual(self.term.screen.get_at((second.centerx, second.y))[:3], self.term._theme['accent'])

    def test_wheel_scrolls_details_independently_from_grid(self):
        self.configure_panel((640, 440))
        key = self.rows[0].key
        self.data['items'][key]['description'] = 'Long retained detail with all material properties. ' * 45
        self.render()
        detail_key, detail, maximum = self.term._panel_detail_view
        self.assertGreater(maximum, 0)
        self.term._last_mouse = detail.center
        self.assertEqual(self.emit(self.pg.MOUSEWHEEL, y=-1, x=0), 'UI_REDRAW')
        self.assertGreater(self.term._panel_detail_states[detail_key], 0)
        previous = self.term._panel_detail_states[detail_key]
        self.term._last_mouse = self.target('UI_SELECT:0').center
        self.assertEqual(self.emit(self.pg.MOUSEWHEEL, y=-1, x=0),
                         'UI_WHEEL:' + str(self.term.menu_grid_columns('inventory_unified')))
        self.assertEqual(self.term._panel_detail_states[detail_key], previous)

    def test_scrollbar_click_and_drag_emit_absolute_offsets(self):
        self.configure_panel((640, 440))
        capacity = self.render()
        track = self.target('UI_SCROLL_TRACK')
        expected = len(self.rows) - capacity
        self.assertEqual(self.emit(self.pg.MOUSEBUTTONDOWN, button=1, pos=(track.centerx, track.bottom - 1)),
                         'UI_SCROLL:' + str(expected))
        self.assertEqual(self.emit(self.pg.MOUSEMOTION, pos=(track.centerx, track.top), rel=(0, -20), buttons=(1, 0, 0)),
                         'UI_SCROLL:0')
        self.assertEqual(self.emit(self.pg.MOUSEMOTION, pos=(track.centerx, track.bottom - 1), rel=(0, 20), buttons=(1, 0, 0)),
                         'UI_SCROLL:' + str(expected))
        self.assertEqual(self.emit(self.pg.MOUSEBUTTONUP, button=1, pos=track.center), 'UI_REDRAW')
        self.assertIsNone(self.term._panel_scroll_drag)

    def test_offscreen_selection_retains_details_and_no_visible_highlight(self):
        self.configure_panel((900, 620))
        selected_key = self.rows[-1].key
        self.data['selected_key'] = selected_key
        self.render(selected=-1)
        self.assertEqual(self.term._panel_detail_view[0], 'inventory:' + selected_key)
        for rect, token in self.term._pointer_targets:
            if token.startswith('UI_SELECT:'):
                self.assertNotEqual(self.term.screen.get_at((rect.centerx, rect.y))[:3], self.term._theme['accent'])
        self.assertIn('UI_ACTION:drop', {token for _, token in self.term._pointer_targets})

    def test_input_data_is_observational_and_presentation_caches_are_bounded(self):
        self.configure_panel((900, 620))
        before = copy.deepcopy(self.data)
        self.render()
        self.assertEqual(self.data, before)
        item_id = self.rows[0].key
        for width in range(24, 224):
            self.term._panel_item_icon(item_id, self.pg.Rect(0, 0, width, 40))
        self.assertLessEqual(len(self.term._panel_icon_cache), 192)
        for index in range(40):
            self.term._panel_detail('bounded:' + str(index), self.pg.Rect(0, 0, 100, 40),
                                    [('text', 'Details', self.term._theme['text'])])
        self.assertLessEqual(len(self.term._panel_detail_states), 32)
        self.assertEqual(self.data, before)


if __name__ == '__main__':
    unittest.main()
