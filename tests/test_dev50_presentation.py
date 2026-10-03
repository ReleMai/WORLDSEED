"""Entrances, connected fences and custom storage art remain observational."""
import os
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from PIL import Image

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.presentation.visuals import VisualRegistry
from worldseed.systems.building_shells import BuildingShell
from worldseed.systems.state import pos_key
from worldseed.ui.exterior_view import draw_shells
from worldseed.ui.fence_view import connection_bits, fence_surface
from worldseed.ui.pygame_terminal import PygameTerminal


class StorageArtTests(unittest.TestCase):
    def test_ten_containers_have_distinct_genuine_alpha_art(self):
        visuals = VisualRegistry.load_default()
        names = ('household_chest', 'wardrobe', 'pantry_cabinet', 'inn_barrel', 'armory_locker',
                 'tool_chest', 'supply_crate', 'grain_bin', 'medicine_cabinet', 'archive_bookcase')
        paths = [visuals.resolve(visuals.ref('containers', 'core:' + name)) for name in names]
        self.assertEqual(len(set(paths)), 10)
        self.assertEqual(len({path.read_bytes() for path in paths}), 10)
        for path in paths:
            with self.subTest(path=path), Image.open(path) as im:
                self.assertIn('A', im.getbands())
                self.assertEqual(im.getchannel('A').getextrema()[0], 0)
                self.assertIsNotNone(im.getchannel('A').getbbox())

    def test_corrected_chicken_exports_do_not_include_left_cow_fragments(self):
        visuals = VisualRegistry.load_default()
        ref = visuals.ref('species', 'core:chicken')
        self.assertEqual(len(ref.paths), 2)
        for path in ref.paths:
            self.assertIn('/dev50/', path)
            with Image.open(visuals.base_dir / path) as im:
                alpha = im.getchannel('A')
                self.assertEqual(im.size, (320, 256))
                # The old exports had a detached cow strip touching x=30/46.
                # The corrected single-animal cutouts have clear canvas edges.
                self.assertIsNone(alpha.crop((0, 0, 12, 256)).getbbox())
                self.assertIsNone(alpha.crop((308, 0, 320, 256)).getbbox())


@unittest.skipUnless(PygameTerminal.available(), 'pygame optional')
class Dev50PresentationTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'SDL_VIDEODRIVER': 'dummy', 'SDL_AUDIODRIVER': 'dummy'})
        self.env.start()
        self.term = PygameTerminal(1000, 720)
        self.term.enter()
        self.pg = self.term.pg
        self.registry = ContentRegistry.load(DATA_DIR)

    def tearDown(self):
        self.term.restore()
        self.env.stop()

    def test_all_authored_building_thresholds_align_with_stable_physical_portal(self):
        visuals = self.term._visuals
        functions = ('residence', 'residence_2', 'residence_3', 'residence_4', 'residence_5', 'residence_6',
                     'archive', 'bakery', 'barn', 'barracks', 'brewery', 'butcher', 'clinic', 'fishery',
                     'inn', 'market', 'mason_yard', 'mill', 'outskirt_camp', 'pottery', 'school', 'shrine',
                     'smithy', 'tannery', 'watchhouse', 'weavery', 'workshop')
        used = self.pg.Rect(150, 130, 700, 500)
        footprint = tuple((x, y) for y in range(6) for x in range(6))
        known = {pos_key(x, y, 0) for x, y in footprint}
        for function in functions:
            for size in (16, 28, 56):
                with self.subTest(function=function, size=size):
                    shell = BuildingShell('shell:' + function, 'town', function, 'core:house', footprint,
                                          (3, 5), 'door:stable', 0, 'rectangle', (0, 0, 5, 5))
                    hits = []
                    draw_shells(self.term, (shell,), used, 0, 0, size, known, known, hit_regions=hits)
                    doors = [row for row in hits if row['kind'] == 'door']
                    self.assertEqual(len(doors), 1)
                    self.assertEqual(doors[0]['target'], (3, 5))
                    self.assertEqual(doors[0]['rect'].midbottom,
                                     (used.x + 3 * size + size // 2,
                                      used.y + 6 * size - max(1, size // 10)))
                    self.assertEqual(doors[0]['role'], 'facade')
        self.assertEqual(known, {pos_key(x, y, 0) for x, y in footprint})

    def test_fence_rails_join_across_edges_and_gates_without_structure_id_restriction(self):
        fence_id, gate_id = 'core:dev43_field_fence_piece', 'core:animal_pen_gate_piece'
        cells = {(0, 0, 0): NS(structure_piece_id=fence_id),
                 (1, 0, 0): NS(structure_piece_id=gate_id),
                 (2, 0, 0): NS(structure_piece_id=fence_id)}
        before = {key: row.structure_piece_id for key, row in cells.items()}
        self.assertEqual(connection_bits((0, 0, 0), cells, self.registry), 2)
        self.assertEqual(connection_bits((1, 0, 0), cells, self.registry), 10)
        self.assertEqual(connection_bits((2, 0, 0), cells, self.registry), 8)
        piece = self.registry.settlement_pieces[fence_id]
        for size in (16, 28, 56):
            a = fence_surface(self.term, piece, size, 2)
            b = fence_surface(self.term, piece, size, 8)
            ys = [y for y in range(size) if a.get_at((size - 1, y)).a]
            self.assertTrue(ys)
            self.assertTrue(any(b.get_at((0, y)).a for y in ys))
            for bits in (0, 3, 5, 6, 9, 10, 12, 15):
                self.assertTrue(fence_surface(self.term, piece, size, bits).get_bounding_rect().width)
        self.assertEqual(before, {key: row.structure_piece_id for key, row in cells.items()})

    def test_indoor_containers_never_enter_exterior_spatial_buckets(self):
        state = NS(containers={'inside': NS(x=0, y=0, z=0, interior_space_id='home'),
                               'outside': NS(x=0, y=0, z=0, interior_space_id='')})
        for name in ('creatures', 'npcs', 'structures', 'crops', 'fires', 'fluids', 'ground_piles',
                     'carcasses', 'animal_signs', 'animal_homes'):
            setattr(state, name, {})
        sim = NS(state=state, clock=NS(minute=0))
        view = self.term._spatial_state_views(sim, -1, -1, 1, 1, 0)
        self.assertEqual(view['containers'], [state.containers['outside']])
