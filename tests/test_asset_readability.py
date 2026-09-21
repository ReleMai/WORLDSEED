from pathlib import Path
import hashlib
import unittest
from PIL import Image

ROOT = Path('worldseed/assets/sprites')


class AssetReadabilityTests(unittest.TestCase):
    def digest(self, rel):
        return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()

    def test_common_ground_resources_have_unique_authored_images(self):
        paths = [
            'resources/oak_tree.png', 'resources/pine_tree.png', 'resources/birch_tree.png',
            'resources/willow_tree.png', 'resources/fallen_branches.png',
            'resources/blueberry_bush.png', 'resources/raspberry_cane.png',
            'resources/strawberry_patch.png', 'resources/yarrow_patch.png',
            'resources/plantain_patch.png', 'resources/nettle_patch.png',
            'resources/dandelion_patch.png', 'resources/wild_carrot_patch.png',
            'resources/wild_onion_patch.png', 'resources/wild_grain_patch.png',
            'resources/bolete_patch.png', 'resources/morel_patch.png',
        ]
        digests = [self.digest(path) for path in paths]
        self.assertEqual(len(digests), len(set(digests)))

    def test_transparent_resource_art_does_not_gain_colored_rectangles(self):
        for rel in ('resources/blueberry_bush.png', 'resources/willow_tree.png',
                    'items/blueberries.png', 'items/morel.png'):
            with self.subTest(rel=rel):
                img = Image.open(ROOT / rel).convert('RGBA')
                corners = [img.getpixel((0, 0))[3], img.getpixel((img.width - 1, 0))[3],
                           img.getpixel((0, img.height - 1))[3], img.getpixel((img.width - 1, img.height - 1))[3]]
                self.assertEqual(corners, [0, 0, 0, 0])

    def test_hd_surface_terrain_textures_are_distinct(self):
        paths = [
            'terrain/grass_hd.png', 'terrain/forest_hd.png', 'terrain/scrub_hd.png',
            'terrain/rock_hd.png', 'terrain/sand_hd.png', 'terrain/tundra_hd.png',
            'terrain/wetland_hd.png', 'terrain/water_hd.png', 'terrain/river_hd.png',
            'terrain/river_shallow_hd.png', 'terrain/tilled_soil_hd.png',
        ]
        digests = [self.digest(path) for path in paths]
        self.assertEqual(len(digests), len(set(digests)))
        for path in paths:
            self.assertEqual(Image.open(ROOT / path).size, (128, 128))


if __name__ == '__main__':
    unittest.main()
