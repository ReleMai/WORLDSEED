"""The fishing and natural-cache visuals must be usable by both render paths."""

import unittest

from PIL import Image

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.presentation.visuals import VisualRegistry


class FishAndContainerSpriteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = ContentRegistry.load(DATA_DIR)
        cls.visuals = VisualRegistry.load_default()

    def test_every_fish_item_has_a_transparent_sprite(self):
        fish = (
            "brook_trout", "bluegill", "largemouth_bass", "channel_catfish",
            "common_carp", "northern_pike", "striped_bass", "summer_flounder",
            "striped_mullet", "atlantic_mackerel", "atlantic_cod", "red_drum",
        )
        self.assertEqual({f"core:{name}" for name in fish},
                         {cid for cid, item in self.content.items.items()
                          if "raw_fish" in item.tags})
        for name in fish:
            with self.subTest(fish=name):
                path = self.visuals.resolve(self.visuals.ref("items", f"core:{name}"))
                self.assertEqual(f"{name}.png", path.name)
                with Image.open(path) as sprite:
                    # Generated inventory art uses the common native 64px cell.
                    self.assertEqual((64, 64), sprite.size)
                    alpha = sprite.convert("RGBA").getchannel("A")
                    self.assertEqual(0, alpha.getpixel((0, 0)))
                    self.assertIsNotNone(alpha.getbbox())

    def test_natural_containers_share_their_art_and_have_renderable_atlas_rows(self):
        pairs = (
            ("hollow_log_cache", "natural_hollow_log", 0),
            ("rotten_stump_cache", "natural_rotten_stump", 1),
            ("rock_crevice_cache", "natural_rock_cache", 2),
        )
        rows = []
        for resource, structure, row in pairs:
            with self.subTest(resource=resource):
                resource_path = self.visuals.resolve(
                    self.visuals.ref("resources", f"core:{resource}"))
                structure_path = self.visuals.resolve(
                    self.visuals.ref("structures", f"core:{structure}"))
                self.assertEqual(resource_path, structure_path)
                with Image.open(resource_path) as sprite:
                    self.assertEqual((160, 136), sprite.size)
                    self.assertIsNotNone(sprite.convert("RGBA").getchannel("A").getbbox())

                atlas_path = self.visuals.resource_atlas_path(f"core:{resource}")
                style = self.visuals.resource_style(f"core:{resource}")
                self.assertEqual((row, 5, 128),
                                 (style["atlas_row"], style["atlas_columns"],
                                  style["atlas_frame"]))
                with Image.open(atlas_path) as atlas:
                    self.assertEqual((640, 384), atlas.size)
                    frames = [atlas.crop((column * 128, row * 128,
                                          (column + 1) * 128, (row + 1) * 128))
                              for column in range(5)]
                    self.assertTrue(all(frame.getchannel("A").getbbox()
                                        for frame in frames))
                    self.assertGreater(len({frame.tobytes() for frame in frames}), 1)
                    rows.append(frames[0].tobytes())
        self.assertEqual(3, len(set(rows)))


if __name__ == "__main__":
    unittest.main()
