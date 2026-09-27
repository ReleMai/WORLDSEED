"""Verify that every authored animal has a usable illustrated sprite set."""

import unittest

from PIL import Image

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.presentation.visuals import VisualRegistry


class AnimalSpriteTests(unittest.TestCase):
    def test_authored_animals_have_four_distinct_transparent_variants(self):
        content = ContentRegistry.load(DATA_DIR)
        visuals = VisualRegistry.load_default()
        monsters = {"core:cave_crawler", "core:cave_stalker"}
        animals = set(content.species) - monsters
        self.assertEqual(21, len(animals))

        for species_id in sorted(animals):
            with self.subTest(species=species_id):
                ref = visuals.ref("species", species_id)
                self.assertEqual(4, len(ref.paths))
                self.assertTrue(all("/illustrated/" in path for path in ref.paths))
                files = [visuals.base_dir / path for path in ref.paths]
                self.assertEqual(4, len({path.read_bytes() for path in files}))
                for path in files:
                    with Image.open(path) as sprite:
                        self.assertEqual((160, 136), sprite.size)
                        alpha = sprite.convert("RGBA").getchannel("A")
                        self.assertLessEqual(alpha.getpixel((0, 0)), 4)
                        self.assertIsNotNone(alpha.getbbox())


if __name__ == "__main__":
    unittest.main()
