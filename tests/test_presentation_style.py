"""Shared style preserves palette identity and keeps painting observational."""
import unittest
from unittest.mock import Mock
from worldseed.ui.presentation_style import DEFAULT_PALETTE, draw_standard_menu_frame, palette

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

if __name__ == '__main__':
    unittest.main()
