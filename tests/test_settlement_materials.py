"""Building materials and connected topology must resolve to visible art."""

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import unittest

from PIL import Image

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.presentation.visuals import VisualRegistry
from worldseed.ui.pygame_terminal import PygameTerminal


class SettlementMaterialAssetsTests(unittest.TestCase):
    def test_every_building_shell_piece_resolves_an_authored_material(self):
        registry = ContentRegistry.load(DATA_DIR)
        visuals = VisualRegistry.load_default()
        paths = set()
        for piece in registry.settlement_pieces.values():
            if piece.category not in {'wall', 'opening', 'floor', 'road', 'roof'}:
                continue
            with self.subTest(piece=piece.id):
                path = visuals.settlement_material_path(piece.category, piece.material, piece.tags, piece.id)
                self.assertIsNotNone(path)
                self.assertTrue(path.is_file(), path)
                paths.add(path)
                with Image.open(path) as image:
                    self.assertEqual((128, 128), image.size)
        self.assertEqual(24, len(paths))
        self.assertEqual(24, len({path.read_bytes() for path in paths}))
        for name in ('wood_wall', 'stone_wall', 'reed_screen', 'door',
                     'wood_floor', 'wood_roof', 'stone_roof'):
            with self.subTest(icon=name):
                path = visuals.resolve(visuals.ref('structures', f'core:{name}'))
                with Image.open(path) as icon:
                    self.assertEqual((48, 48), icon.size)
                    self.assertIsNotNone(icon.convert('RGBA').getchannel('A').getbbox())


@unittest.skipUnless(PygameTerminal.available(), "requires pygame-ce")
class SettlementConnectionRenderTests(unittest.TestCase):
    def setUp(self):
        self.terminal = PygameTerminal(480, 320)
        self.terminal.enter()
        self.pieces = ContentRegistry.load(DATA_DIR).settlement_pieces

    def tearDown(self):
        self.terminal.restore()

    def test_all_wall_and_path_connections_keep_open_ends(self):
        wall = self.pieces['core:timber_straight_wall_piece']
        path = self.pieces['core:footpath_piece']
        for piece, draw in ((wall, self.terminal._settlement_wall_surface),
                            (path, self.terminal._settlement_ground_surface)):
            with self.subTest(piece=piece.id):
                for bits in range(16):
                    surface = draw(piece, 48, bits)
                    self.assertEqual((48, 48), surface.get_size())
                    self.assertGreater(surface.get_bounding_rect().width, 0)
                    if bits & 1:
                        self.assertGreater(surface.get_at((24, 0)).a, 0)
                    if bits & 2:
                        self.assertGreater(surface.get_at((47, 24)).a, 0)
                    if bits & 4:
                        self.assertGreater(surface.get_at((24, 47)).a, 0)
                    if bits & 8:
                        self.assertGreater(surface.get_at((0, 24)).a, 0)

    def test_doors_roofs_and_floor_edges_follow_their_neighbors(self):
        door = self.pieces['core:wood_door_piece']
        roof = self.pieces['core:slate_roof_piece']
        floor = self.pieces['core:stone_plain_floor_piece']
        horizontal = self.terminal._settlement_wall_surface(door, 48, 10, 'entrance')
        vertical = self.terminal._settlement_wall_surface(door, 48, 5, 'entrance')
        self.assertNotEqual(horizontal.get_at((0, 24)).a, vertical.get_at((0, 24)).a)
        self.assertNotEqual(
            self.terminal._settlement_roof_surface(roof, 48, 0).get_at((24, 1)),
            self.terminal._settlement_roof_surface(roof, 48, 15).get_at((24, 1)))
        self.assertNotEqual(
            self.terminal._settlement_ground_surface(floor, 48, 0).get_at((1, 24)),
            self.terminal._settlement_ground_surface(floor, 48, 15).get_at((1, 24)))

    def test_player_built_shell_uses_the_connected_materials(self):
        from types import SimpleNamespace
        structures = {
            (0, 0, 0): SimpleNamespace(structure_id='core:wood_wall'),
            (1, 0, 0): SimpleNamespace(structure_id='core:door'),
            (2, 0, 0): SimpleNamespace(structure_id='core:stone_wall'),
        }
        wall = self.terminal._placed_building_piece('core:wood_wall')
        door = self.terminal._placed_building_piece('core:door')
        self.assertEqual(2, self.terminal._placed_building_bits((0, 0, 0), structures, wall))
        self.assertEqual(10, self.terminal._placed_building_bits((1, 0, 0), structures, door))
        for structure in ('core:wood_floor', 'core:wood_roof', 'core:stone_roof'):
            self.assertIsNotNone(self.terminal._placed_building_piece(structure))


if __name__ == '__main__':
    unittest.main()
