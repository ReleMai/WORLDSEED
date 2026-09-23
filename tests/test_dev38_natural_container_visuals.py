import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import unittest

from worldseed.presentation.visuals import VisualRegistry
from worldseed.ui.pygame_terminal import PygameTerminal


NATURAL_CONTAINERS = (
    ("core:hollow_log_cache", 0),
    ("core:rotten_stump_cache", 1),
    ("core:rock_crevice_cache", 2),
)


class Dev38NaturalContainerManifestTests(unittest.TestCase):
    def test_each_natural_container_has_five_atlas_variants(self):
        visuals = VisualRegistry.load_default()
        atlas_paths = set()
        for content_id, row in NATURAL_CONTAINERS:
            style = visuals.resource_style(content_id)
            self.assertEqual(style.get("variants"), 5)
            self.assertEqual(style.get("atlas_columns"), 5)
            self.assertEqual(style.get("atlas_frame"), 128)
            self.assertEqual(style.get("atlas_row"), row)
            self.assertTrue(style.get("smooth"))
            atlas = visuals.resource_atlas_path(content_id)
            self.assertIsNotNone(atlas)
            self.assertTrue(atlas.exists(), atlas)
            atlas_paths.add(atlas)
        self.assertEqual(len(atlas_paths), 1)

    def test_world_cell_variant_choice_is_deterministic_and_varied(self):
        term = PygameTerminal()
        for content_id, row in NATURAL_CONTAINERS:
            first = term._resource_visual(content_id, 123, -77, 0)
            second = term._resource_visual(content_id, 123, -77, 0)
            self.assertEqual(first, second)
            self.assertEqual(first[0], "atlas")
            self.assertEqual(first[3], row)
            self.assertEqual(first[4], 128)

            columns = {
                term._resource_visual(content_id, x, y, 0)[2]
                for y in range(-8, 9)
                for x in range(-8, 9)
            }
            self.assertEqual(columns, {0, 1, 2, 3, 4})


@unittest.skipUnless(PygameTerminal.available(), "requires pygame-ce")
class Dev38NaturalContainerAtlasTests(unittest.TestCase):
    def test_all_fifteen_frames_load_with_alpha(self):
        term = PygameTerminal(640, 480)
        term.enter()
        try:
            atlas = term._visuals.resource_atlas_path("core:hollow_log_cache")
            source = term.pg.image.load(str(atlas)).convert_alpha()
            self.assertEqual(source.get_size(), (640, 384))
            for _, row in NATURAL_CONTAINERS:
                for column in range(5):
                    frame = term._load_atlas_frame(
                        atlas, column, row, 128, 112, 112, smooth=True
                    )
                    self.assertIsNotNone(frame, (row, column))
                    self.assertLessEqual(frame.get_width(), 112)
                    self.assertLessEqual(frame.get_height(), 112)
        finally:
            term.restore()


if __name__ == "__main__":
    unittest.main()
