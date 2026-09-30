from __future__ import annotations

import hashlib
from pathlib import Path
import unittest

from PIL import Image

from worldseed.presentation.visuals import VisualRegistry


ALPHA_THRESHOLD = 8
EXPECTED_SIZE = (160, 256)
EXPECTED_TOP = 16
EXPECTED_BASELINE = 248
EXPECTED_CENTER_X = 80.0


class CharacterSpriteNormalizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.visuals = VisualRegistry.load_default()

    def _groups(self) -> dict[str, tuple[Path, ...]]:
        return {
            "player male": self.visuals.player_paths("male"),
            "player female": self.visuals.player_paths("female"),
            "npc male": self.visuals.npc_paths("male"),
            "npc female": self.visuals.npc_paths("female"),
        }

    def test_each_player_and_npc_group_has_ten_unique_paths(self) -> None:
        groups = self._groups()
        for label, paths in groups.items():
            self.assertEqual(len(paths), 10, label)
            self.assertEqual(len(set(paths)), 10, label)

        player_paths = set(groups["player male"] + groups["player female"])
        npc_paths = set(groups["npc male"] + groups["npc female"])
        self.assertTrue(player_paths.isdisjoint(npc_paths))

    def test_active_actor_sprites_share_canvas_center_height_and_baseline(self) -> None:
        for label, paths in self._groups().items():
            for path in paths:
                with self.subTest(group=label, sprite=path.name):
                    with Image.open(path) as image:
                        rgba = image.convert("RGBA")
                        self.assertEqual(rgba.size, EXPECTED_SIZE)
                        alpha = rgba.getchannel("A").point(
                            lambda value: 255 if value >= ALPHA_THRESHOLD else 0
                        )
                        bounds = alpha.getbbox()
                        self.assertIsNotNone(bounds)
                        assert bounds is not None
                        left, top, right, bottom = bounds
                        self.assertEqual(top, EXPECTED_TOP)
                        self.assertEqual(bottom, EXPECTED_BASELINE)
                        self.assertEqual(bottom - top, 232)
                        self.assertLessEqual(
                            abs(((left + right) / 2.0) - EXPECTED_CENTER_X), 0.5
                        )

    def test_all_forty_active_actor_images_have_distinct_pixels(self) -> None:
        digests: dict[str, Path] = {}
        for paths in self._groups().values():
            for path in paths:
                with Image.open(path) as image:
                    digest = hashlib.sha256(image.convert("RGBA").tobytes()).hexdigest()
                self.assertNotIn(digest, digests, f"{path} duplicates {digests.get(digest)}")
                digests[digest] = path
        self.assertEqual(len(digests), 40)


if __name__ == "__main__":
    unittest.main()
