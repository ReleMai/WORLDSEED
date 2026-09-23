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
            with self.subTest(content_id=content_id, expected_row=row):
                style = visuals.resource_style(content_id)
                self.assertEqual(style.get("variants"), 5)
                self.assertEqual(style.get("atlas_columns"), 5)
                self.assertEqual(style.get("atlas_frame"), 64)
                self.assertEqual(style.get("atlas_row"), row)
                self.assertTrue(style.get("smooth"))
                atlas = visuals.resource_atlas_path(content_id)
                self.assertIsNotNone(atlas, f"{content_id}: missing atlas path")
                self.assertTrue(atlas.exists(), f"{content_id}: missing atlas file {atlas}")
                atlas_paths.add(atlas)
        self.assertEqual(
            len(atlas_paths),
            1,
            f"natural-container resources must share one atlas, got: {sorted(map(str, atlas_paths))}",
        )

    def test_world_cell_variant_choice_is_deterministic_and_varied(self):
        term = PygameTerminal()
        for content_id, row in NATURAL_CONTAINERS:
            with self.subTest(content_id=content_id, atlas_row=row):
                first = term._resource_visual(content_id, 123, -77, 0)
                second = term._resource_visual(content_id, 123, -77, 0)
                self.assertEqual(first, second)
                self.assertEqual(first[0], "atlas")
                self.assertEqual(first[3], row)
                self.assertEqual(first[4], 64)

                columns = {
                    term._resource_visual(content_id, x, y, 0)[2]
                    for y in range(-8, 9)
                    for x in range(-8, 9)
                }
                self.assertEqual(
                    columns,
                    {0, 1, 2, 3, 4},
                    f"{content_id}: atlas variant selection did not cover all five columns",
                )


@unittest.skipUnless(PygameTerminal.available(), "requires pygame-ce")
class Dev38NaturalContainerAtlasTests(unittest.TestCase):
    def test_all_fifteen_frames_load_with_alpha(self):
        term = PygameTerminal(640, 480)
        term.enter()
        try:
            atlas = term._visuals.resource_atlas_path("core:hollow_log_cache")
            affected_ids = tuple(content_id for content_id, _ in NATURAL_CONTAINERS)
            self.assertIsNotNone(
                atlas,
                f"missing shared natural-container atlas for {', '.join(affected_ids)}",
            )
            try:
                source = term.pg.image.load(str(atlas)).convert_alpha()
            except Exception as exc:
                self.fail(
                    "Failed to decode natural-container atlas "
                    f"{atlas} used by {', '.join(affected_ids)}: "
                    f"{type(exc).__name__}: {exc}"
                )

            self.assertEqual(
                source.get_size(),
                (320, 192),
                f"{atlas}: expected 320x192 natural-container atlas",
            )
            for content_id, row in NATURAL_CONTAINERS:
                for column in range(5):
                    with self.subTest(
                        content_id=content_id,
                        atlas=str(atlas),
                        row=row,
                        column=column,
                    ):
                        frame = term._load_atlas_frame(
                            atlas, column, row, 64, 112, 112, smooth=True
                        )
                        self.assertIsNotNone(
                            frame,
                            f"{content_id}: failed to load atlas frame row={row} column={column} from {atlas}",
                        )
                        self.assertLessEqual(
                            frame.get_width(),
                            112,
                            f"{content_id}: frame row={row} column={column} width={frame.get_width()}",
                        )
                        self.assertLessEqual(
                            frame.get_height(),
                            112,
                            f"{content_id}: frame row={row} column={column} height={frame.get_height()}",
                        )
        finally:
            term.restore()


if __name__ == "__main__":
    unittest.main(verbosity=2)
