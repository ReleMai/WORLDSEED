import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from worldseed.presentation.regional_terrain import RegionalTerrainAssets
from worldseed.ui.pygame_terminal import PygameTerminal


def terrain_plan(**changes):
    fields = dict(region_x=-1, region_y=0, dominant_biome='grassland',
                  mean_moisture=32768, mean_temperature=32768,
                  mean_elevation=32768, relief=9000, biome_mix={'grassland': 25})
    fields.update(changes)
    return SimpleNamespace(**fields)


@unittest.skipUnless(PygameTerminal.available(), 'pygame optional')
class RegionalTerrainAssetTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'SDL_VIDEODRIVER': 'dummy', 'SDL_AUDIODRIVER': 'dummy'})
        self.env.start()
        self.term = PygameTerminal()
        self.term.enter()
        self.pg = self.term.pg
        self.assets = RegionalTerrainAssets(self.pg, capacity=8)

    def tearDown(self):
        self.pg.quit()
        self.env.stop()

    def pixels(self, surface):
        return self.pg.image.tobytes(surface, 'RGB')

    def test_repeat_order_independence_and_hidden_state_isolation(self):
        a, b = terrain_plan(), terrain_plan(region_x=2)
        before = dict(vars(a))
        with patch('random.random', side_effect=AssertionError('global RNG')):
            first = self.pixels(self.assets.surface(a, 96))
            second = self.pixels(self.assets.surface(b, 96))
            other = RegionalTerrainAssets(self.pg)
            self.assertEqual(second, self.pixels(other.surface(b, 96)))
            self.assertEqual(first, self.pixels(other.surface(a, 96)))
            self.assertNotEqual(first, second)
            self.assertEqual(vars(a), before)
            a.control_potential = 'bandit_frontier'
            a.site_potential = True
            a.fingerprint = 'hidden-fields-changed'
            self.assertEqual(first, self.pixels(other.surface(a, 96)))

    def test_public_terrain_fields_drive_assets(self):
        base = self.pixels(self.assets.surface(terrain_plan(), 128))
        for change in ({'mean_moisture': 0}, {'mean_temperature': 1000},
                       {'mean_elevation': 60000}, {'relief': 60000},
                       {'biome_mix': {'grassland': 5, 'forest': 20}},
                       {'dominant_biome': 'forest'}):
            with self.subTest(change=change):
                self.assertNotEqual(base, self.pixels(self.assets.surface(terrain_plan(**change), 128)))

    def test_asset_cache_reuse_eviction_and_size_bounds(self):
        plan = terrain_plan()
        surface = self.assets.surface(plan, 96)
        with patch.object(self.assets, '_generate', side_effect=AssertionError('cache miss')):
            self.assertIs(self.assets.surface(plan, 96), surface)
            self.assets.surface(plan, 50)  # Scale the existing fixed-resolution asset.
        original = self.pixels(surface)
        for x in range(20):
            self.assets.surface(terrain_plan(region_x=x), 96)
            self.assertLessEqual(len(self.assets._cache), 8)
        self.assertEqual(original, self.pixels(self.assets.surface(plan, 96)))
        self.assertEqual(self.assets.surface(plan, 10000).get_size(), (256, 256))
        # Keep both base and scaled assets for an entire 13 x 9 viewport.
        viewport = RegionalTerrainAssets(self.pg)
        plans = [terrain_plan(region_x=x, region_y=y) for y in range(9) for x in range(13)]
        for item in plans:
            viewport.surface(item, 95)
        with patch.object(viewport, '_generate', side_effect=AssertionError('viewport cache thrash')):
            for item in plans:
                viewport.surface(item, 95)

    def test_neighboring_biomes_blend_directionally_without_replacing_center(self):
        base_plan = terrain_plan(dominant_biome='grassland', region_x=0, region_y=0)
        forest_north = terrain_plan(dominant_biome='forest', region_x=0, region_y=-1)
        sand_west = terrain_plan(dominant_biome='coast', region_x=-1, region_y=0)
        no_neighbors = self.assets.surface(base_plan, 128)
        blended = self.assets.surface(base_plan, 128, neighbors={'north': forest_north, 'west': sand_west})
        self.assertNotEqual(self.pixels(no_neighbors), self.pixels(blended))
        center_plain = tuple(no_neighbors.get_at((64, 64)))[:3]
        center_blended = tuple(blended.get_at((64, 64)))[:3]
        self.assertLess(sum(abs(a - b) for a, b in zip(center_plain, center_blended)), 40)
        north_plain = tuple(no_neighbors.get_at((64, 5)))[:3]
        north_blended = tuple(blended.get_at((64, 5)))[:3]
        west_plain = tuple(no_neighbors.get_at((5, 64)))[:3]
        west_blended = tuple(blended.get_at((5, 64)))[:3]
        self.assertNotEqual(north_plain, north_blended)
        self.assertNotEqual(west_plain, west_blended)
        repeated = self.assets.surface(base_plan, 128, neighbors={'north': forest_north, 'west': sand_west})
        self.assertEqual(self.pixels(blended), self.pixels(repeated))

    def test_every_regional_biome_has_distinct_textured_coverage(self):
        biomes = {'grassland', 'forest', 'highland', 'tundra', 'scrub', 'coast', 'water'}
        self.assertEqual(set(self.assets.styles), {'core:' + b for b in biomes})
        images = set()
        for biome in sorted(biomes):
            surface = self.assets.surface(terrain_plan(dominant_biome=biome), 128)
            colors = {tuple(surface.get_at((x, y))) for x in range(128) for y in range(128)}
            self.assertGreater(len(colors), 30)
            images.add(self.pixels(surface))
        self.assertEqual(len(images), len(biomes))
        fallback = self.assets.surface(terrain_plan(dominant_biome='mod:unknown'), 96)
        self.assertEqual(tuple(fallback.get_at((50, 50)))[:3], (45, 47, 48))
