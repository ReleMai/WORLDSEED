"""Painted buildings fit immutable physical shells, including padded exports."""
import json
import os
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from worldseed.config import DATA_DIR
from worldseed.systems.building_shells import BuildingShell
from worldseed.systems.state import pos_key
from worldseed.ui.exterior_view import _facade_door_rect, _fit_geometry, _surface_key, _whole_surface, draw_shells, shell_at_pointer
from worldseed.ui.pygame_terminal import PygameTerminal


@unittest.skipUnless(PygameTerminal.available(), 'pygame optional')
class Dev54ExteriorFitTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'SDL_VIDEODRIVER': 'dummy', 'SDL_AUDIODRIVER': 'dummy'})
        self.env.start()
        self.term = PygameTerminal(1280, 832)
        self.term.enter()
        self.used = self.term.pg.Rect(100, 100, 1100, 650)

    def tearDown(self):
        self.term.restore()
        self.env.stop()

    @staticmethod
    def shell(width=6, height=5, entrance_x=2):
        cells = tuple((x, y) for y in range(height) for x in range(width))
        return BuildingShell('house:fit', 'town:fit', 'residence', 'core:house', cells,
                             (entrance_x, height - 1), 'door:stable', 0, 'rectangular',
                             (0, 0, width - 1, height - 1))

    def paint_asset(self, shell, asset, path, size):
        self.term.screen.fill((31, 44, 34))
        known = {pos_key(x, y, 0) for x, y in shell.footprint}
        hits = []
        with patch('worldseed.ui.exterior_view._art_ref', return_value=(asset, path)):
            draw_shells(self.term, (shell,), self.used, 0, 0, size, known, known, hit_regions=hits)
        return hits, known

    def test_all_authored_assets_fit_the_plan_without_export_padding_or_translation(self):
        root = Path(DATA_DIR).parent
        visuals = json.loads((root / 'assets/visuals.json').read_text(encoding='utf-8'))['building_shells']
        for name, relative in visuals.items():
            path = root / relative
            shell = self.shell()
            before = shell.footprint
            for size in (16, 28, 40, 56):
                with self.subTest(asset=name, zoom=size):
                    hits, known = self.paint_asset(shell, path.stem, path, size)
                    body = next(row for row in hits if row['kind'] == 'body')
                    door = next(row for row in hits if row['kind'] == 'door')
                    self.assertEqual(body['rect'], self.term.pg.Rect(100, 100, 6 * size, 5 * size))
                    # A padded source can no longer create a complete blank
                    # blocked column/row at any of the physical shell edges.
                    bounds = body['mask'].get_bounding_rects()
                    united = bounds[0].unionall(bounds[1:])
                    self.assertLessEqual(united.left, 2)
                    self.assertLessEqual(united.top, 2)
                    self.assertGreaterEqual(united.right, body['rect'].width - 2)
                    # A few legacy anchors intentionally end a fraction below
                    # the painted foundation. Only the existing doorstep
                    # apron may be blank, never an entire blocked tile row.
                    self.assertGreaterEqual(united.bottom, body['rect'].height - max(2, size // 10))
                    self.assertEqual(door['target'], shell.entrance)
                    self.assertEqual(door['rect'].midbottom,
                                     (100 + 2 * size + size // 2, 100 + 5 * size - max(1, size // 10)))
                    ctx = {'used': self.used, 'shell_hit_regions': hits}
                    self.assertEqual(shell_at_pointer(ctx, door['rect'].center), (shell, 'door'))
                    self.assertEqual(known, {pos_key(x, y, 0) for x, y in before})
            self.assertEqual(shell.footprint, before)

    def test_even_width_portals_do_not_shift_art_half_a_tile_left_or_right(self):
        root = Path(DATA_DIR).parent
        path = root / 'assets/sprites/buildings/dev47/residence_3.png'
        for entrance_x in (2, 3):
            shell = self.shell(entrance_x=entrance_x)
            for size in (16, 28, 56):
                with self.subTest(entrance_x=entrance_x, zoom=size):
                    hits, _ = self.paint_asset(shell, 'residence_3', path, size)
                    body = next(row for row in hits if row['kind'] == 'body')
                    door = next(row for row in hits if row['kind'] == 'door')
                    self.assertEqual(body['rect'].topleft, self.used.topleft)
                    self.assertEqual(body['rect'].size, (6 * size, 5 * size))
                    self.assertEqual(door['rect'].centerx, 100 + entrance_x * size + size // 2)

    def test_source_pixels_are_not_modified_and_fit_axes_are_monotone(self):
        source = self.term.pg.Surface((100, 100), self.term.pg.SRCALPHA)
        self.term.pg.draw.rect(source, (110, 90, 70, 255), (25, 10, 50, 80))
        before = self.term.pg.image.tobytes(source, 'RGBA')
        axes, door = _fit_geometry(self.shell(), 168, 140, source, (300, 650, 120, 200))
        sx, sy, tx, ty = axes
        self.assertEqual((sx[0], sx[-1], sy[0], sy[-1]), (25, 75, 10, 90))
        self.assertTrue(all(b > a for values in axes for a, b in zip(values, values[1:])))
        self.assertEqual((tx[0], tx[-1], ty[0], ty[-1]), (0, 168, 0, 140))
        self.assertEqual(self.term.pg.Rect(door).midbottom, (70, 138))
        self.assertEqual((tx[1] + tx[2]) // 2, 70)
        self.assertEqual((door[0], door[0] + door[2]), (tx[1], tx[2]))
        self.assertEqual(self.term.pg.image.tobytes(source, 'RGBA'), before)

    def test_painted_recess_and_leaf_share_center_after_source_cache_eviction(self):
        source = self.term.pg.Surface((100, 100), self.term.pg.SRCALPHA)
        source.fill((90, 120, 70))
        self.term.pg.draw.rect(source, (20, 30, 220), (20, 60, 10, 30))
        path = Path('synthetic_offcentre_recess.png')
        self.term._building_source_cache = {str(path): source}
        shell = self.shell()
        body = self.term.pg.Rect(100, 100, 168, 140)
        with patch('worldseed.ui.exterior_view._art_ref', return_value=('synthetic', path)), \
                patch('worldseed.ui.exterior_view._door_anchor', return_value=(200, 600, 100, 300)):
            fitted = _whole_surface(self.term, shell, body.width, body.height)
            door = _facade_door_rect(self.term, shell, body)
            local_y = door.centery - body.y
            recess_pixels = [x for x in range(fitted.get_width()) if fitted.get_at((x, local_y)).b > 180]
            self.assertTrue(recess_pixels)
            self.assertLessEqual(abs((min(recess_pixels) + max(recess_pixels) + 1) // 2 - (door.centerx - body.x)), 1)
            self.term._building_source_cache.clear()
            with patch('worldseed.ui.exterior_view._fit_geometry', side_effect=AssertionError('cached facade rescanned PNG')), \
                    patch.object(self.term.pg.image, 'load', side_effect=AssertionError('cached building reloaded')):
                self.assertIs(_whole_surface(self.term, shell, body.width, body.height), fitted)
                self.assertEqual(_facade_door_rect(self.term, shell, body), door)

    def test_fit_cache_keys_distinguish_grid_scale_and_missing_art_family(self):
        shell = replace(self.shell(), entrance=None)
        key = _surface_key('residence', None, shell, 168, 140)
        different_grid = replace(shell, bounds=(0, 0, 2, 4))
        different_family = replace(shell, function='archive')
        self.assertNotEqual(key, _surface_key('residence', None, different_grid, 168, 140))
        self.assertNotEqual(key, _surface_key('archive', None, different_family, 168, 140))
        self.assertNotEqual(key, _surface_key('residence_3', None, shell, 168, 140))


if __name__ == '__main__':
    unittest.main()
