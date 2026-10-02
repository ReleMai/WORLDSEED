"""Interior materials are varied presentation data, not world authority."""
import copy
from pathlib import Path
import unittest

from worldseed.presentation.visuals import VisualRegistry
from worldseed.ui.pygame_terminal import PygameTerminal


FLOORS = {
    'oak': 'core:interior_floor_oak',
    'flagstone': 'core:interior_floor_flagstone',
    'terracotta': 'core:interior_floor_terracotta',
}
WALLS = {
    'plaster': 'core:interior_wall_plaster',
    'timber': 'core:interior_wall_timber',
    'stone': 'core:interior_wall_stone',
}
WORKSHOPS = ('smithy', 'workshop', 'mill', 'fishery', 'bakery', 'butcher',
             'weavery', 'tannery', 'pottery', 'brewery', 'mason_yard', 'clinic')
STATIONS = ('core:forge_piece', 'core:carpenter_bench_piece', 'core:millstone_piece',
            'core:bakery_oven_piece', 'core:loom_piece', 'core:brewery_vat_piece')


class InteriorMaterialCatalogTests(unittest.TestCase):
    def setUp(self):
        self.visuals = VisualRegistry.load_default()

    def test_building_functions_choose_their_own_material_profile(self):
        expected = {
            'residence': (FLOORS['oak'], WALLS['plaster']),
            'smithy': (FLOORS['flagstone'], WALLS['stone']),
            'bakery': (FLOORS['terracotta'], WALLS['plaster']),
            'workshop': (FLOORS['oak'], WALLS['timber']),
        }
        for function, materials in expected.items():
            with self.subTest(function=function):
                self.assertEqual(self.visuals.interior_materials(function), materials)

    def test_kitchen_uses_washable_floor_without_changing_building_walls(self):
        self.assertEqual(self.visuals.interior_materials('residence', 'Kitchen'),
                         (FLOORS['terracotta'], WALLS['plaster']))
        self.assertEqual(self.visuals.interior_materials('workshop', 'kitchen'),
                         (FLOORS['terracotta'], WALLS['timber']))

    def test_unknown_building_uses_safe_default(self):
        self.assertEqual(self.visuals.interior_materials('mod:unconfigured_hall'),
                         (FLOORS['oak'], WALLS['plaster']))

    def test_room_keyword_does_not_match_another_words_substring(self):
        self.assertEqual(self.visuals.interior_materials('inn', 'Private guest room'),
                         (FLOORS['oak'], WALLS['timber']))
        self.assertEqual(self.visuals.interior_materials('brewery', 'Vat room'),
                         (FLOORS['flagstone'], WALLS['timber']))

    def test_all_workshops_have_valid_varied_materials(self):
        pairs = []
        for function in WORKSHOPS:
            pair = self.visuals.interior_materials(function)
            with self.subTest(function=function):
                self.assertEqual(len(pair), 2)
                self.assertIn(pair[0], FLOORS.values())
                self.assertIn(pair[1], WALLS.values())
                for visual_id in pair:
                    self.assertIsNotNone(self.visuals.resolve(self.visuals.ref('interior_textures', visual_id)))
            pairs.append(pair)
        self.assertGreaterEqual(len(set(pairs)), 3,
                                'Workshops must not all share one generic interior style')

    def test_material_queries_do_not_mutate_the_visual_manifest(self):
        before = copy.deepcopy(self.visuals.manifest)
        for function in (*WORKSHOPS, 'residence', 'mod:unconfigured_hall'):
            self.visuals.interior_materials(function)
            self.visuals.interior_materials(function, 'Kitchen')
        self.assertEqual(self.visuals.manifest, before)


@unittest.skipUnless(PygameTerminal.available(), 'pygame optional')
class InteriorMaterialAssetTests(unittest.TestCase):
    def test_six_material_textures_are_distinct_complete_opaque_assets(self):
        import pygame as pg
        visuals = VisualRegistry.load_default()
        paths = []
        for visual_id in (*FLOORS.values(), *WALLS.values()):
            with self.subTest(visual_id=visual_id):
                path = visuals.resolve(visuals.ref('interior_textures', visual_id))
                self.assertIsNotNone(path)
                self.assertTrue(path.is_file(), str(path))
                surface = pg.image.load(str(path))
                self.assertGreater(surface.get_width(), 32)
                self.assertGreater(surface.get_height(), 32)
                # RGB assets and fully opaque RGBA assets are both valid.
                self.assertEqual(pg.mask.from_surface(surface, 254).count(),
                                 surface.get_width() * surface.get_height())
                paths.append(path)
        self.assertEqual(len(set(paths)), 6)

    def test_six_workstations_have_separate_genuine_transparent_cutouts(self):
        import pygame as pg
        visuals = VisualRegistry.load_default()
        paths = []
        for piece_id in STATIONS:
            with self.subTest(piece_id=piece_id):
                path = visuals.resolve(visuals.ref('interiors', piece_id))
                self.assertIsNotNone(path)
                self.assertTrue(path.is_file(), str(path))
                surface = pg.image.load(str(path))
                self.assertTrue(surface.get_flags() & pg.SRCALPHA)
                count = pg.mask.from_surface(surface, 0).count()
                self.assertGreater(count, 0)
                self.assertLess(count, surface.get_width() * surface.get_height(),
                                'A painted checkerboard or opaque background is not transparency')
                paths.append(path)
        self.assertEqual(len(set(paths)), 6)


@unittest.skipUnless(PygameTerminal.available(), 'pygame optional')
class InteriorMaterialRenderingTests(unittest.TestCase):
    def setUp(self):
        # Compose the existing headless fixture rather than inherit its tests,
        # which would silently double the regression suite in this module.
        from tests import test_interior_presentation as fixtures
        self.fixture = fixtures.InteriorPresentationTests(
            'test_render_is_observational_and_uses_no_outdoor_entities')
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)

    def test_furniture_alpha_silhouette_is_portrait_fitted_without_collision_mutation(self):
        from unittest.mock import patch
        from worldseed.ui.interior_view import _furniture_sprite
        term = self.fixture.term
        source = term.pg.Surface((100, 100), term.pg.SRCALPHA)
        term.pg.draw.rect(source, (80, 120, 160), (40, 20, 20, 60))
        rect = term.pg.Rect(5, 7, 80, 80)
        before = rect.copy()
        path = Path('synthetic-portrait-furniture.png')
        with patch.object(term.pg.image, 'load', return_value=source) as load:
            sprite = _furniture_sprite(term, path, rect)
            repeated = _furniture_sprite(term, path, rect)
        self.assertEqual(load.call_count, 1)
        self.assertEqual(sprite.get_height(), 80)
        self.assertLessEqual(abs(sprite.get_width() * 3 - sprite.get_height()), 1)
        self.assertEqual(repeated.get_size(), sprite.get_size())
        self.assertEqual(rect, before)
        self.assertEqual(source.get_size(), (100, 100))

    def test_furniture_source_cache_stays_bounded_and_recent_entries_do_not_reload(self):
        from unittest.mock import patch
        from worldseed.ui.interior_view import _furniture_sprite
        term = self.fixture.term
        source = term.pg.Surface((20, 40), term.pg.SRCALPHA)
        source.fill((80, 120, 160))
        rect = term.pg.Rect(0, 0, 40, 40)
        with patch.object(term.pg.image, 'load', return_value=source):
            for index in range(110):
                self.assertIsNotNone(_furniture_sprite(term, Path(f'synthetic-furniture-{index}.png'), rect))
        self.assertLessEqual(len(term._interior_art_sources), 96)
        with patch.object(term.pg.image, 'load', side_effect=AssertionError('recent source was reloaded')):
            self.assertIsNotNone(_furniture_sprite(term, Path('synthetic-furniture-109.png'), rect))

    def test_renderer_reads_building_and_room_styles_without_outdoor_access(self):
        from unittest.mock import patch
        from worldseed.ui import interior_view
        fixture = self.fixture
        fixture.plan.function = 'smithy'
        before = copy.deepcopy((vars(fixture.plan), vars(fixture.player), vars(fixture.sim.state)))
        with patch.object(interior_view, '_texture', wraps=interior_view._texture) as textures:
            fixture.render()
        ids = [call.args[2] for call in textures.call_args_list]
        self.assertIn(FLOORS['flagstone'], ids)
        self.assertIn(WALLS['stone'], ids)
        self.assertNotIn('core:interior_floor', ids)
        self.assertNotIn('core:interior_wall', ids)
        self.assertEqual(before, (vars(fixture.plan), vars(fixture.player), vars(fixture.sim.state)))

    def test_kitchen_room_override_is_rendered_without_changing_saved_geometry(self):
        from unittest.mock import patch
        from worldseed.ui import interior_view
        fixture = self.fixture
        fixture.plan.function = 'residence'
        fixture.plan.rooms[0].name = 'Kitchen'
        before = copy.deepcopy(vars(fixture.plan))
        with patch.object(interior_view, '_texture', wraps=interior_view._texture) as textures:
            fixture.render()
        ids = [call.args[2] for call in textures.call_args_list]
        self.assertIn(FLOORS['oak'], ids)
        self.assertIn(FLOORS['terracotta'], ids)
        self.assertIn(WALLS['plaster'], ids)
        self.assertEqual(vars(fixture.plan), before)


if __name__ == '__main__':
    unittest.main()
