"""Whole-shell painting is bounded, observational, and discovery exact."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from worldseed.presentation.visuals import VisualRegistry
from worldseed.systems.building_shells import BuildingShell
from worldseed.systems.state import pos_key
from worldseed.ui.exterior_view import draw_shells, shell_at_pointer, shell_cells
from worldseed.ui.pygame_terminal import PygameTerminal


@unittest.skipUnless(PygameTerminal.available(), 'pygame optional')
class BuildingPresentationTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'SDL_VIDEODRIVER': 'dummy', 'SDL_AUDIODRIVER': 'dummy'})
        self.env.start()
        self.term = PygameTerminal(800, 520)
        self.term.enter()
        self.pg = self.term.pg
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        roof = self.pg.Surface((60, 40), self.pg.SRCALPHA)
        roof.fill((50, 180, 90))
        door = self.pg.Surface((32, 32), self.pg.SRCALPHA)
        door.fill((70, 110, 220))
        self.pg.image.save(roof, str(base / 'roof.png'))
        self.pg.image.save(door, str(base / 'door.png'))
        self.term._visuals = VisualRegistry({'building_shells': {'residence': 'roof.png'},
                                            'building_doors': {'wood': 'door.png'}}, base)
        self.shell = BuildingShell('house:one', 'town:one', 'residence', 'core:house',
                                   ((0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1)),
                                   (1, 1), 'door:one', 0, 'rectangular', (0, 0, 2, 1))

    def tearDown(self):
        self.term.restore()
        self.temp.cleanup()
        self.env.stop()

    def paint(self, size, known=None, visible=None):
        known = {pos_key(x, y, 0) for x, y in self.shell.footprint} if known is None else known
        visible = known if visible is None else visible
        self.term.screen.fill((0, 0, 0))
        used = self.pg.Rect(30, 50, 400, 250)
        by = draw_shells(self.term, (self.shell,), used, 0, 0, size, known, visible)
        return {'used': used, 'tile_px': size, 'left': 0, 'top': 0, 'z': 0,
                'known': known, 'shell_by': by}

    def test_whole_building_and_independent_door_at_all_zoom_limits(self):
        for size in (16, 28, 56):
            ctx = self.paint(size)
            body = (30 + size // 2, 50 + size // 2)
            door = (30 + size + size // 2, 50 + size + size // 2)
            self.assertEqual(shell_at_pointer(ctx, body), (self.shell, 'body'))
            self.assertEqual(shell_at_pointer(ctx, door), (self.shell, 'door'))
            # SDL smoothscale rounds premultiplied RGBA by a few units at
            # small zooms; selection/geometry must remain pixel exact.
            self.assertLessEqual(max(abs(a-b) for a,b in zip(self.term.screen.get_at(body)[:3], (50,180,90))), 5)
            self.assertLessEqual(max(abs(a-b) for a,b in zip(self.term.screen.get_at(door)[:3], (70,110,220))), 5)
            self.assertIsNone(shell_at_pointer(ctx, (0, 0)))

    def test_one_discovered_tile_does_not_reveal_the_building_or_entrance(self):
        ctx = self.paint(28, {pos_key(0, 0, 0)})
        self.assertEqual(self.term.screen.get_at((44, 64))[:3], (50, 180, 90))
        self.assertEqual(self.term.screen.get_at((72, 64))[:3], (0, 0, 0))
        self.assertEqual(self.term.screen.get_at((72, 92))[:3], (0, 0, 0))
        self.assertIsNone(shell_at_pointer(ctx, (72, 64)))
        self.assertIsNone(shell_at_pointer(ctx, (72, 92)))

    def test_footprint_not_bounding_box_owns_paint_and_selection(self):
        self.shell = BuildingShell('house:l', 'town:one', 'residence', 'core:house',
                                   ((0, 0), (1, 0), (2, 0), (0, 1)),
                                   (0, 1), 'door:l', 0, 'L-shaped', (0, 0, 2, 1))
        ctx = self.paint(28)
        self.assertEqual(self.term.screen.get_at((72, 92))[:3], (0, 0, 0))
        self.assertIsNone(shell_at_pointer(ctx, (72, 92)))

    def test_renderer_is_observational_and_cached(self):
        before = self.shell
        self.paint(28)
        with patch.object(self.pg.image, 'load', side_effect=AssertionError('cached sprite was reloaded')):
            self.paint(28)
        self.assertEqual(self.shell, before)
        self.assertEqual(self.term.screen.get_clip(), self.term.screen.get_rect())

    def test_unexplored_shell_does_not_load_hidden_assets(self):
        with patch.object(self.pg.image, 'load', side_effect=AssertionError('unknown shell loaded')):
            self.paint(28, set())

    def test_memory_keeps_static_building_but_does_not_promote_visibility(self):
        known = {pos_key(x, y, 0) for x, y in self.shell.footprint}
        ctx = self.paint(28, known, set())
        pixel = self.term.screen.get_at((44, 64))[:3]
        self.assertTrue(0 < pixel[1] < 180)
        self.assertEqual(ctx['known'], known)

    def test_default_catalog_has_six_houses_and_unique_core_furniture(self):
        from worldseed.config import DATA_DIR
        from worldseed.content.registry import ContentRegistry
        registry = ContentRegistry.load(DATA_DIR)
        visuals = VisualRegistry.load_default()
        from worldseed.systems.interior_templates import interior_profiles
        functions = {function for profile in interior_profiles() for function in profile['functions'] if function != '*'}
        self.assertGreaterEqual(len(functions),22)
        for function in sorted(functions):
            path = visuals.resolve(visuals.ref('building_shells',function))
            self.assertIsNotNone(path,function)
            self.assertTrue(path.is_file(),str(path))
        house_paths = []
        for function in ('residence', 'residence_2', 'residence_3', 'residence_4', 'residence_5', 'residence_6'):
            path = visuals.resolve(visuals.ref('building_shells', function))
            self.assertIsNotNone(path, function)
            self.assertTrue(path.is_file(), str(path))
            house_paths.append(path)
        self.assertEqual(len(set(house_paths)), 6)
        furniture_paths = []
        for piece in registry.settlement_pieces.values():
            if piece.category != 'furniture' or not piece.id.startswith('core:'):
                continue
            path = visuals.resolve(visuals.ref('interiors', piece.id))
            self.assertIsNotNone(path, piece.id)
            self.assertTrue(path.is_file(), str(path))
            furniture_paths.append(path)
        self.assertEqual(len(furniture_paths), len(set(furniture_paths)))
        for material in ('wood', 'iron'):
            path = visuals.resolve(visuals.ref('building_doors', material))
            self.assertIsNotNone(path, material)
            self.assertTrue(path.is_file(), str(path))


if __name__ == '__main__':
    unittest.main()
