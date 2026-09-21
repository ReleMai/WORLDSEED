from __future__ import annotations

import unittest

from worldseed.config import DATA_DIR, WORLDGEN_PREVIEW_VERSION, WORLDGEN_VERSION
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.world.generator import WorldGenerator


class WorldgenV8Phase2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)
        cls.seed = b"v8-authority-fixture"

    def test_v8_is_explicit_preview_until_promotion_gate(self):
        self.assertEqual(WORLDGEN_VERSION, 7)
        self.assertEqual(WORLDGEN_PREVIEW_VERSION, 8)

    def test_v7_field_contract_is_frozen_at_representative_coordinates(self):
        expected = {
            (-4097, -2049): (32639, 28033, 20425, 36803),
            (-1, -1): (47792, 19303, 24469, 33183),
            (0, 0): (47799, 19235, 24445, 33133),
            (913, -1441): (46888, 39719, 45726, 46155),
            (4096, 2048): (38268, 27122, 37929, 41715),
        }
        gen = WorldGenerator(self.seed, self.registry, version=7)
        for (x, y), row in expected.items():
            fields = gen.sample_fields(WorldPos(x, y, 0))
            self.assertEqual(
                (fields.elevation, fields.moisture, fields.temperature, fields.fertility),
                row,
                (x, y),
            )

    def test_explicit_v8_promotes_geological_elevation_only(self):
        gen7 = WorldGenerator(self.seed, self.registry, version=7)
        gen8 = WorldGenerator(self.seed, self.registry, version=WORLDGEN_PREVIEW_VERSION)
        changed = 0
        for x, y in ((-4097,-2049),(-1,-1),(0,0),(913,-1441),(4096,2048)):
            pos = WorldPos(x, y, 0)
            legacy = gen7.sample_fields(pos)
            fields = gen8.sample_fields(pos)
            geology = gen8.prototype_landform_at(x, y)
            self.assertEqual(fields.elevation, geology.elevation)
            self.assertEqual(fields.moisture, legacy.moisture)
            self.assertEqual(gen8.landform_at(pos), geology)
            changed += fields.elevation != legacy.elevation
        self.assertGreater(changed, 0)

    def test_legacy_worlds_do_not_expose_authoritative_v8_landforms(self):
        gen7 = WorldGenerator(self.seed, self.registry, version=7)
        self.assertIsNone(gen7.landform_at(WorldPos(0, 0, 0)))
        gen8 = WorldGenerator(self.seed, self.registry, version=8)
        self.assertIsNone(gen8.landform_at(WorldPos(0, 0, -1)))


if __name__ == "__main__":
    unittest.main()
