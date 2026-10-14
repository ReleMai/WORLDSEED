"""Shared style preserves palette identity and keeps painting observational."""
import unittest
from unittest.mock import Mock
from worldseed.ui.presentation_style import (DEFAULT_PALETTE, FONT_SIZES, PANEL_METRICS, PANEL_HELP,
    draw_standard_menu_frame, draw_floating_panel_frame, draw_panel_focus_outline,
    button_style, draw_button_background, panel_help_text, palette)

class PresentationStyleTests(unittest.TestCase):
    def test_palette_is_immutable_by_default_and_copies_are_independent(self):
        with self.assertRaises(TypeError):
            DEFAULT_PALETTE['accent'] = (0, 0, 0)
        changed = palette()
        changed['accent'] = (0, 0, 0)
        self.assertEqual(palette()['accent'], (195, 154, 77))

    def test_frame_does_not_flip_display_or_dispatch_input(self):
        pg = Mock()
        pg.SRCALPHA = 65536
        rect = Mock(x=50, y=70, w=400, h=300, right=450)
        screen = Mock()
        draw_standard_menu_frame(pg, screen, rect, palette())
        pg.Surface.assert_called_once_with((416, 316), 65536)
        screen.blit.assert_called_once()
        self.assertEqual(pg.draw.rect.call_count, 4)
        pg.draw.line.assert_called_once()
        pg.display.flip.assert_not_called()


    def test_floating_shell_is_observational(self):
        pg=Mock()
        rect=Mock(x=10,y=20,w=600,h=450,right=610)
        screen=Mock()
        draw_floating_panel_frame(pg,screen,rect,palette())
        self.assertEqual(pg.draw.rect.call_count,5)
        self.assertEqual(pg.draw.line.call_count,2)
        pg.display.flip.assert_not_called()
        screen.blit.assert_not_called()

    def test_button_styles_expose_disabled_and_destructive_roles(self):
        colors=palette()
        self.assertEqual(button_style(colors),(colors['panel2'],colors['edge_hi'],colors['text'],1))
        self.assertEqual(button_style(colors,hovered=True)[1],colors['accent'])
        self.assertEqual(button_style(colors,hovered=True,enabled=False)[2],colors['muted'])
        self.assertEqual(button_style(colors,destructive=True,context='homestead')[1],colors['danger'])
        self.assertEqual(button_style(colors,prominent=True,context='homestead')[1],colors['accent'])
        with self.assertRaises(ValueError):
            button_style(colors,context='invalid')

    def test_button_painter_leaves_pointer_and_simulation_untouched(self):
        pg=Mock()
        screen=Mock()
        self.assertEqual(draw_button_background(pg,screen,Mock(),palette(),enabled=False),palette()['muted'])
        self.assertEqual(pg.draw.rect.call_count,2)
        pg.display.flip.assert_not_called()
        screen.blit.assert_not_called()

    def test_typography_metrics_and_context_help(self):
        self.assertEqual(dict(FONT_SIZES), {'body': 17, 'small': 14, 'title': 21})
        self.assertEqual(PANEL_METRICS['content_top'], 52)
        self.assertIn('Shift-click', panel_help_text('inventory_unified'))
        self.assertIn('recipe', panel_help_text('crafting'))
        self.assertEqual(panel_help_text('unknown', 'Custom text'), 'Custom text')
        self.assertIn('Resize', panel_help_text('unknown'))
        with self.assertRaises(TypeError):
            PANEL_HELP['crafting'] = 'changed'

    def test_focus_outline_is_observational(self):
        pg = Mock()
        rect = Mock()
        screen = Mock()
        draw_panel_focus_outline(pg, screen, rect, palette())
        rect.inflate.assert_called_once_with(-6, -6)
        pg.draw.rect.assert_called_once()
        pg.display.flip.assert_not_called()
        screen.blit.assert_not_called()


if __name__ == '__main__':
    unittest.main()
