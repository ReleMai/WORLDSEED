"""Every recipe output must resolve to a distinct inventory sprite."""
import hashlib
import json
from pathlib import Path
import struct
import unittest

from worldseed.presentation.visuals import VisualRegistry


class CraftableSpriteCoverageTests(unittest.TestCase):
    def test_every_recipe_output_has_a_distinct_rgba_sprite(self):
        root = Path(__file__).resolve().parents[1] / 'worldseed'
        recipes = json.loads((root / 'data' / 'recipes.json').read_text())
        crafted = {item for recipe in recipes for item in recipe['outputs']}
        visual = VisualRegistry.load_default()
        hashes = set()
        for item in crafted:
            ref = visual.ref('items', item)
            self.assertEqual(1, len(ref.paths), item)
            sprite = visual.base_dir / ref.paths[0]
            data = sprite.read_bytes()
            self.assertEqual(b'\x89PNG\r\n\x1a\n', data[:8], item)
            self.assertEqual((64, 64), struct.unpack('>II', data[16:24]), item)
            self.assertEqual(6, data[25], item)  # RGBA, with transparency.
            hashes.add(hashlib.sha256(data).digest())
        self.assertEqual(len(crafted), len(hashes))


if __name__ == '__main__':
    unittest.main()
