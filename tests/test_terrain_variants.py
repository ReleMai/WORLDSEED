from pathlib import Path
import hashlib
import unittest

from worldseed.presentation.visuals import VisualRegistry


class TerrainVariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vis = VisualRegistry.load_default()
        cls.root = Path('worldseed')
        cls.terrain_ids = [
            'core:grass', 'core:forest', 'core:scrub', 'core:sand', 'core:rock',
            'core:tundra', 'core:wetland', 'core:water', 'core:river',
            'core:river_shallow', 'core:floodplain', 'core:tilled_soil',
            'core:cave_floor', 'core:berry_thicket',
        ]

    def digest(self, relpath: str) -> str:
        return hashlib.sha256((self.root / relpath).read_bytes()).hexdigest()

    def test_common_repeatable_terrains_have_ten_or_more_variants(self):
        for terrain_id in self.terrain_ids:
            with self.subTest(terrain_id=terrain_id):
                ref = self.vis.ref('terrain', terrain_id)
                self.assertGreaterEqual(len(ref.paths), 10)
                for raw in ref.paths:
                    path = self.root / raw
                    self.assertTrue(path.exists(), path)
                    self.assertGreater(path.stat().st_size, 200, path)

    def test_each_variant_set_contains_multiple_unique_images(self):
        for terrain_id in self.terrain_ids:
            with self.subTest(terrain_id=terrain_id):
                ref = self.vis.ref('terrain', terrain_id)
                digests = [self.digest(raw) for raw in ref.paths]
                self.assertGreaterEqual(len(set(digests)), 6)

    def test_visual_registry_resolves_different_variants(self):
        for terrain_id in ('core:grass', 'core:sand', 'core:water'):
            with self.subTest(terrain_id=terrain_id):
                ref = self.vis.ref('terrain', terrain_id)
                self.assertNotEqual(self.vis.resolve(ref, 0), self.vis.resolve(ref, 1))
                self.assertNotEqual(self.vis.resolve(ref, 1), self.vis.resolve(ref, 2))


if __name__ == '__main__':
    unittest.main()
