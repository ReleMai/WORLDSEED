"""Exposed tabletop goods use the same inventory and art the player can take."""
import copy
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.ui.interior_view import _draw_tabletop_items
from worldseed.ui.pygame_terminal import PygameTerminal


class TabletopGoodsArtTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'SDL_VIDEODRIVER': 'dummy', 'SDL_AUDIODRIVER': 'dummy'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.term = PygameTerminal(960, 640)
        self.term.enter()
        self.addCleanup(self.term.restore)
        self.reg = ContentRegistry.load(DATA_DIR)
        self.canvas = self.term.pg.Rect(80, 80, 150, 120)
        self.container = SimpleNamespace(items={'core:stone': 1, 'core:wood': 2, 'core:bone': 1})

    def test_only_exposed_goods_are_painted_and_rendering_cannot_consume_them(self):
        before = copy.deepcopy(self.container.items)
        self.term.screen.fill((0, 0, 0))
        blank = self.term.pg.image.tobytes(self.term.screen, 'RGBA')
        _draw_tabletop_items(self.term, SimpleNamespace(piece_id='core:household_chest_piece'),
                             self.container, self.canvas)
        self.assertEqual(self.term.pg.image.tobytes(self.term.screen, 'RGBA'), blank)
        _draw_tabletop_items(self.term, SimpleNamespace(piece_id='core:small_table_piece'),
                             self.container, self.canvas)
        self.assertNotEqual(self.term.pg.image.tobytes(self.term.screen, 'RGBA'), blank)
        self.assertEqual(self.container.items, before)

    def test_removing_goods_removes_their_art_at_every_zoom(self):
        furniture = SimpleNamespace(piece_id='core:writing_desk_piece')
        for size in (12, 28, 56):
            self.term._tile_px = size
            self.term.screen.fill((0, 0, 0))
            self.container.items = {'core:stone': 1, 'core:wood': 0}
            _draw_tabletop_items(self.term, furniture, self.container, self.canvas)
            filled = self.term.pg.image.tobytes(self.term.screen, 'RGBA')
            self.term.screen.fill((0, 0, 0))
            self.container.items.clear()
            _draw_tabletop_items(self.term, furniture, self.container, self.canvas)
            self.assertNotEqual(self.term.pg.image.tobytes(self.term.screen, 'RGBA'), filled)


if __name__ == '__main__':
    unittest.main()
