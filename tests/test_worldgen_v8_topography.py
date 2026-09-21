from __future__ import annotations

import unittest

from worldseed.config import DATA_DIR, WORLDGEN_PREVIEW_VERSION
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.world.caves import CaveGeneratorV7, CaveGeneratorV8
from worldseed.world.generator import WorldGenerator


class WorldgenV8TopographyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)
        cls.seed = b"v8-topography-tests"

    def test_topography_is_deterministic_and_matches_authoritative_elevation(self):
        a = WorldGenerator(self.seed, self.registry, version=WORLDGEN_PREVIEW_VERSION)
        b = WorldGenerator(self.seed, self.registry, version=WORLDGEN_PREVIEW_VERSION)
        coords = (
            WorldPos(-2049, -1025, 0),
            WorldPos(-33, 31, 0),
            WorldPos(0, 0, 0),
            WorldPos(31, 32, 0),
            WorldPos(2048, -4096, 0),
        )
        for pos in coords:
            ta = a.topography_at(pos)
            tb = b.topography_at(pos)
            self.assertEqual(ta, tb)
            self.assertEqual(ta.elevation, a.sample_fields(pos).elevation)
            self.assertGreaterEqual(ta.slope, 0)
            self.assertLessEqual(ta.slope, 65535)
            self.assertGreaterEqual(ta.relief, 0)
            self.assertLessEqual(ta.relief, 65535)
            self.assertGreaterEqual(ta.ruggedness, 0)
            self.assertLessEqual(ta.ruggedness, 65535)

    def test_legacy_world_has_no_authoritative_v8_topography(self):
        legacy = WorldGenerator(self.seed, self.registry, version=7)
        self.assertIsNone(legacy.topography_at(WorldPos(0, 0, 0)))

    def test_v8_uses_geological_cave_entrance_planner_only(self):
        legacy = WorldGenerator(self.seed, self.registry, version=7)
        preview = WorldGenerator(self.seed, self.registry, version=8)
        self.assertIsInstance(legacy.caves, CaveGeneratorV7)
        self.assertNotIsInstance(legacy.caves, CaveGeneratorV8)
        self.assertIsInstance(preview.caves, CaveGeneratorV8)

    def test_v8_cave_mouths_are_tied_to_exposed_topography(self):
        gen = WorldGenerator(b"v8-cave-siting", self.registry, version=8)
        entrance = None
        for cy in range(-8, 9):
            for cx in range(-8, 9):
                entrance = gen.caves._entrance_for_cell(cx, cy)
                if entrance is not None:
                    break
            if entrance is not None:
                break
        self.assertIsNotNone(entrance)
        pos = WorldPos(entrance.x, entrance.y, 0)
        topo = gen.topography_at(pos)
        geology = gen.landform_at(pos)
        self.assertEqual(entrance.elevation, topo.elevation)
        self.assertTrue(
            topo.relief_raw >= 360
            or topo.slope >= 10500
            or geology.mountain_chain >= 18000
            or geology.plateau >= 25000
        )
        self.assertEqual(gen.terrain_at(pos), "core:cave_mouth")
        for depth in range(1, entrance.depth + 1):
            self.assertEqual(
                gen.terrain_at(WorldPos(entrance.x, entrance.y, -depth)),
                "core:shaft",
            )


if __name__ == "__main__":
    unittest.main()
