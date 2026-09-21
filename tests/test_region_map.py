import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from worldseed.core.coords import WorldPos
from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.ui.region_map import UNKNOWN_COLOR, ROAD_COLOR, WATER_COLOR, edge_point, regional_view
from worldseed.world.region_blocks import RegionRoadExit, RegionWaterExit


def map_fixture():
    plans = {}
    for rx, direction, biome in ((-1, 'east', 'grassland'), (0, 'west', 'forest')):
        plans[(rx, 0)] = SimpleNamespace(
            region_x=rx, region_y=0, mean_moisture=32768, mean_temperature=32768,
            mean_elevation=32768, biome_mix={biome: 25},
            dominant_biome=biome, relief=0, wilderness_tags=('wooded',),
            roads=(RegionRoadExit(direction, 400, 'road'),),
            waters=(RegionWaterExit(direction, 96, 2),), settlement_anchor=None,
            control_potential='SECRET_BANDITS', site_potential=True,
        )
    town = SimpleNamespace(uid='known', name='Known village', region_x=-1, region_y=0, x=-200, y=200)
    unseen = SimpleNamespace(uid='hidden_region', name='Hidden town', region_x=1, region_y=0, x=600, y=200)
    return SimpleNamespace(
        player_pos=WorldPos(-128, 128, 0),
        discovered_tiles_set={'-128,128,0', '1,1,0', '600,1,-1', '8000,0,0', 'bad'},
        region_planner=SimpleNamespace(read_prepared=Mock(side_effect=lambda x, y: plans.get((x, y)))),
        known_settlements=lambda: [town, unseen], visited_settlement_ids=lambda: {'known'},
        world=Mock(),
    )


class RegionalViewTests(unittest.TestCase):
    def test_one_surface_tile_reveals_whole_region_but_not_underground_or_distant_regions(self):
        sim = map_fixture()
        view = regional_view(sim, 9, 7)
        self.assertEqual(view.center, (-1, 0))
        self.assertEqual(view.discovered, {(-1, 0), (0, 0)})
        self.assertEqual([t.uid for t in view.towns], ['known'])
        self.assertEqual(sim.region_planner.read_prepared.call_count, 2)
        sim.world.assert_not_called()
        self.assertEqual(sim.world.mock_calls, [])


@unittest.skipUnless(PygameTerminal.available(), 'pygame optional')
class RegionalMapRenderingTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'SDL_VIDEODRIVER': 'dummy', 'SDL_AUDIODRIVER': 'dummy'})
        self.env.start()
        self.term = PygameTerminal()
        self.term.enter()

    def tearDown(self):
        self.term.pg.quit()
        self.env.stop()

    def test_shared_exit_offsets_join_exactly(self):
        pg = self.term.pg
        for size in (41, 100, 147):
            rect = pg.Rect(10, 20, size, size)
            for offset in (0, 96, 400, 511):
                self.assertEqual(edge_point(rect, 'east', offset), edge_point(rect.move(size, 0), 'west', offset))
                self.assertEqual(edge_point(rect, 'south', offset), edge_point(rect.move(0, size), 'north', offset))
                self.assertNotEqual(edge_point(rect, 'east', 96), edge_point(rect, 'east', 400))

    def test_map_is_regional_and_mouse_motion_cannot_restore_local_pixels(self):
        term, sim = self.term, map_fixture()
        pg = term.pg
        for width, height in ((800, 520), (1280, 800), (2560, 1392)):
            term._resize(width, height)
            term._hover_context = {'stale': True}
            term._hover_map_snapshot = pg.Surface((width, height))
            font = term.small_font
            term.small_font = Mock(wraps=font)
            try:
                # Legacy schematic renderer remains an explicit compatibility
                # helper. Production now uses the exact atlas, tested in
                # test_dev22_atlas.py (including hover regression).
                from worldseed.ui.region_map import draw_region_map
                draw_region_map(term, sim)
                labels = '\n'.join(call.args[0] for call in term.small_font.render.call_args_list)
                self.assertIn('Known village', labels)
                self.assertNotIn('Hidden town', labels)
                self.assertNotIn('SECRET_BANDITS', labels)
            finally:
                term.small_font = font
            pixels = pg.image.tobytes(term.screen, 'RGB')
            # Both discovered regional plans received their own terrain asset.
            appearances = {key[1].biome for key in term._regional_terrain_assets._cache}
            self.assertEqual(appearances, {'grassland', 'forest'})
            self.assertGreater(pixels.count(bytes(UNKNOWN_COLOR)), 1000)
            self.assertGreater(pixels.count(bytes(ROAD_COLOR)), 10)
            self.assertGreater(pixels.count(bytes(WATER_COLOR)), 10)
            self.assertIsNone(term._hover_context)
            for pos in ((200, 200), (500, 350), (700, 400)):
                pg.event.post(pg.event.Event(pg.MOUSEMOTION, pos=pos, rel=(1, 1), buttons=(0, 0, 0)))
                pg.event.post(pg.event.Event(pg.KEYDOWN, key=pg.K_ESCAPE, unicode='\x1b'))
                self.assertEqual(term.read_key(), 'ESC')
                self.assertEqual(pg.image.tobytes(term.screen, 'RGB'), pixels)
            self.assertEqual(sim.world.mock_calls, [])
