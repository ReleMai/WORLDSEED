"""Static shells are coherent objects; collision/discovery remain cell exact."""
import json
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
        roof = self.pg.Surface((60, 60), self.pg.SRCALPHA)
        roof.fill((50, 180, 90))
        self.pg.draw.rect(roof, (210, 40, 50), (0, 0, 60, 30))
        door = self.pg.Surface((24, 40), self.pg.SRCALPHA)
        door.fill((70, 110, 220))
        self.pg.draw.rect(door, (230, 190, 30), (0, 30, 24, 10))
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
        hits = []
        by = draw_shells(self.term, (self.shell,), used, 0, 0, size, known, visible,
                        hit_regions=hits)
        return {'used': used, 'tile_px': size, 'left': 0, 'top': 0, 'z': 0,
                'known': known, 'shell_by': by, 'shell_hit_regions': hits}

    @staticmethod
    def opaque_point(region, near=(0.5, 0.5)):
        rect, mask = region['rect'], region['mask']
        center = (int((rect.width - 1) * near[0]), int((rect.height - 1) * near[1]))
        candidates = [(x, y) for y in range(rect.height) for x in range(rect.width)
                      if mask is None or mask.get_at((x, y))]
        x, y = min(candidates, key=lambda p: abs(p[0]-center[0]) + abs(p[1]-center[1]))
        return rect.x + x, rect.y + y

    @staticmethod
    def main_regions(ctx):
        return {'body': next(row for row in ctx['shell_hit_regions'] if row['kind'] == 'body'),
                'door': next(row for row in ctx['shell_hit_regions']
                             if row['kind'] == 'door')}

    def test_whole_building_and_independent_door_at_all_zoom_limits(self):
        for size in (16, 28, 56):
            ctx = self.paint(size)
            regions = self.main_regions(ctx)
            body = self.opaque_point(regions['body'], (0.1, 0.1))
            door = self.opaque_point(regions['door'], (0.5, 0.25))
            self.assertEqual(shell_at_pointer(ctx, body), (self.shell, 'body'))
            self.assertEqual(shell_at_pointer(ctx, door), (self.shell, 'door'))
            # SDL smoothscale rounds premultiplied RGBA by a few units at
            # small zooms; selection/geometry must remain pixel exact.
            self.assertLessEqual(max(abs(a-b) for a,b in zip(self.term.screen.get_at(body)[:3], (210,40,50))), 5)
            self.assertLessEqual(max(abs(a-b) for a,b in zip(self.term.screen.get_at(door)[:3], (70,110,220))), 5)
            self.assertIsNone(shell_at_pointer(ctx, (0, 0)))

    def test_one_visible_frontage_cell_reveals_coherent_static_shell_only(self):
        known = {pos_key(1, 1, 0)}
        visible = set(known)
        ctx = self.paint(28, known, visible)
        regions = self.main_regions(ctx)
        roof = self.opaque_point(regions['body'], (0.1, 0.1))
        self.assertNotEqual(self.term.screen.get_at(roof)[:3], (0, 0, 0))
        self.assertEqual(shell_at_pointer(ctx, roof), (self.shell, 'body'))
        self.assertEqual(ctx['known'], {pos_key(1, 1, 0)})
        self.assertEqual(visible, {pos_key(1, 1, 0)})

    def test_irregular_physical_footprint_does_not_cut_rectangular_holes_in_art(self):
        self.shell = BuildingShell('house:l', 'town:one', 'residence', 'core:house',
                                   ((0, 0), (1, 0), (2, 0), (0, 1)),
                                   (0, 1), 'door:l', 0, 'L-shaped', (0, 0, 2, 1))
        ctx = self.paint(28)
        body = self.main_regions(ctx)['body']
        point = self.opaque_point(body, (0.8, 0.8))
        self.assertNotEqual(self.term.screen.get_at(point)[:3], (0, 0, 0))
        self.assertEqual(shell_at_pointer(ctx, point), (self.shell, 'body'))
        # Artwork does not grow the authoritative collision footprint.
        self.assertNotIn((1, 1, 0), shell_cells((self.shell,)))

    def test_visible_roof_does_not_reveal_unknown_entrance_or_change_discovery(self):
        known = {pos_key(0, 0, 0)}
        ctx = self.paint(28, known, set(known))
        self.assertEqual([row['kind'] for row in ctx['shell_hit_regions']], ['body'])
        self.assertEqual(known, {pos_key(0, 0, 0)})
        self.assertNotIn(pos_key(*self.shell.entrance, 0), known)

    def test_renderer_is_observational_and_cached(self):
        before = self.shell
        self.paint(28)
        with patch.object(self.pg.image, 'load', side_effect=AssertionError('cached sprite was reloaded')):
            self.paint(28)
        self.assertEqual(self.shell, before)
        self.assertEqual(self.term.screen.get_clip(), self.term.screen.get_rect())

    def test_unexplored_shell_does_not_load_hidden_assets(self):
        with patch.object(self.pg.image, 'load', side_effect=AssertionError('unknown shell loaded')):
            ctx = self.paint(28, set())
        self.assertFalse(ctx['shell_hit_regions'])
        self.assertIsNone(shell_at_pointer(ctx, (44, 64)))

    def test_memory_keeps_static_building_but_does_not_promote_visibility(self):
        known = {pos_key(x, y, 0) for x, y in self.shell.footprint}
        ctx = self.paint(28, known, set())
        body = self.main_regions(ctx)['body']
        pixel = self.term.screen.get_at(self.opaque_point(body, (0.1, 0.1)))[:3]
        self.assertTrue(0 < pixel[0] < 210)
        self.assertEqual(ctx['known'], known)

    def test_north_east_west_entrances_never_rotate_roofs_or_door_leaves(self):
        footprint = tuple((x, y) for y in range(5) for x in range(5))
        for entrance in ((2, 0), (4, 2), (0, 2), (2, 4)):
            with self.subTest(entrance=entrance):
                self.shell = BuildingShell('house:side', 'town:one', 'residence', 'core:house',
                                           footprint, entrance, 'door:side', 0,
                                           'rectangular', (0, 0, 4, 4))
                ctx = self.paint(28)
                regions = self.main_regions(ctx)
                roof = regions['body']
                self.assertGreater(self.term.screen.get_at(self.opaque_point(roof, (0.1, 0.1))).r, 150)
                self.assertGreater(self.term.screen.get_at(self.opaque_point(roof, (0.1, 0.9))).g, 150)
                door = regions['door']
                upper = self.term.screen.get_at(self.opaque_point(door, (0.5, 0.2)))
                lower = self.term.screen.get_at(self.opaque_point(door, (0.5, 0.9)))
                self.assertGreater(upper.b, 170)
                self.assertGreater(lower.r, 180)
                self.assertGreater(door['rect'].height, door['rect'].width)
                self.assertEqual(shell_at_pointer(ctx, self.opaque_point(door)), (self.shell, 'door'))
                self.assertEqual(tuple(door['target']), tuple(entrance))

    def test_scale_and_source_caches_remain_bounded(self):
        for size in range(16, 130):
            self.paint(size)
        self.assertLessEqual(len(self.term._building_surface_cache), 96)
        self.assertLessEqual(len(self.term._building_source_cache), 64)
        self.assertLessEqual(len(self.term._building_door_cache), 96)
        self.assertLessEqual(len(self.term._building_hit_mask_cache), 96)

    def test_genuine_alpha_silhouette_controls_hits_not_rectangle_or_floor(self):
        roof = self.pg.Surface((60, 60), self.pg.SRCALPHA)
        self.pg.draw.polygon(roof, (50, 180, 90),
                             ((0, 0), (60, 0), (60, 30), (30, 30), (30, 60), (0, 60)))
        self.pg.image.save(roof, str(Path(self.temp.name) / 'roof.png'))
        ctx = self.paint(56)
        body = self.main_regions(ctx)['body']
        gap = (body['rect'].x + int(body['rect'].width * .9),
               body['rect'].y + int(body['rect'].height * .7))
        self.assertEqual(self.term.screen.get_at(gap)[:3], (0, 0, 0))
        # This pixel is still inside a known authoritative floor cell. It must
        # not acquire a body hit merely from legacy tile fallback.
        self.assertIsNone(shell_at_pointer(ctx, gap))
        self.assertEqual(shell_at_pointer(ctx, self.opaque_point(body, (.2, .2))),
                         (self.shell, 'body'))

    def test_unrepairable_legacy_side_door_is_shown_at_actual_threshold(self):
        self.shell = BuildingShell('house:north', 'town:one', 'residence', 'core:house',
                                   tuple((x, y) for y in range(5) for x in range(5)),
                                   (2, 0), 'door:north', 0, 'rectangular', (0, 0, 4, 4))
        ctx = self.paint(28)
        facade = self.main_regions(ctx)['door']
        point = self.opaque_point(facade)
        self.assertEqual(facade['role'], 'physical-side')
        self.assertEqual(facade['rect'].midbottom,
                         (ctx['used'].x + 2 * 28 + 14, ctx['used'].y + 28 - 2))
        self.assertEqual(shell_at_pointer(ctx, point), (self.shell, 'door'))
        for door in (row for row in ctx['shell_hit_regions'] if row['kind'] == 'door'):
            self.assertEqual(tuple(door['target']), self.shell.entrance)

    def test_transparent_export_padding_does_not_shrink_portrait_doorway(self):
        # Exports may have a square canvas around a narrow upright door. The
        # PNG remains unmodified while rendering fits its visible alpha bounds.
        door = self.pg.Surface((60, 60), self.pg.SRCALPHA)
        self.pg.draw.rect(door, (70, 110, 220), (20, 0, 20, 60))
        self.pg.image.save(door, str(Path(self.temp.name) / 'door.png'))
        ctx = self.paint(56)
        facade = self.main_regions(ctx)['door']
        self.assertGreater(facade['rect'].height, facade['rect'].width * 2)
        point = self.opaque_point(facade)
        self.assertEqual(shell_at_pointer(ctx, point), (self.shell, 'door'))

    def test_art_anchor_metadata_calibrates_l_shaped_house_facade(self):
        from worldseed.config import DATA_DIR
        path = Path(DATA_DIR).parent / 'assets' / 'building_shell_anchors.json'
        anchors = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(anchors['units'], 1000)
        rect = anchors['assets']['residence_3']['door_rect']
        self.assertEqual(len(rect), 4)
        self.assertGreater(rect[2], 0)
        self.assertGreater(rect[3], 0)
        # The L-shaped house's opening is in its left wing, not at the centre
        # of the overall roof bounds. A generic centre anchor causes drift.
        self.assertLess(rect[0] + rect[2]/2, 400)

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
