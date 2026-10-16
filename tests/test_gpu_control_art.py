"""Complete authored HUD art must survive source and frozen asset loading."""
from __future__ import annotations

import hashlib
import json
import struct
import unittest
from unittest.mock import patch

from worldseed.ui.gpu_control_art import ICON_PATHS, load_icon
from worldseed.ui.router import HUD_BUTTONS


class GpuControlArtTests(unittest.TestCase):
    def test_toolbar_and_movement_have_distinct_transparent_authored_art(self):
        required = {name.lower() for name, _ in HUD_BUTTONS}
        required.update(('normal', 'stalk', 'crouch', 'aggressive', 'confirm', 'cancel'))
        self.assertEqual(required, set(ICON_PATHS))
        manifest = json.loads(next(iter(ICON_PATHS.values())).with_name('manifest.json').read_text())
        self.assertEqual(required, set(manifest['icons']))
        hashes = set()
        for key, path in ICON_PATHS.items():
            with self.subTest(key=key):
                data = path.read_bytes()
                self.assertEqual(b'\x89PNG\r\n\x1a\n', data[:8])
                self.assertEqual((128, 128), struct.unpack('>II', data[16:24]))
                self.assertEqual(6, data[25], 'Art must preserve RGBA transparency')
                hashes.add(hashlib.sha256(data).hexdigest())
        self.assertEqual(len(ICON_PATHS), len(hashes))

    def test_art_loads_at_toolbar_size_without_opening_a_display(self):
        try:
            import pygame as pg
        except ImportError:
            self.skipTest('Optional pygame dependency unavailable')
        with patch.object(pg.display, 'set_mode', side_effect=AssertionError('UI art opened a window')):
            for key in ICON_PATHS:
                with self.subTest(key=key):
                    icon = load_icon(pg, key, 32)
                    self.assertEqual((32, 32), icon.get_size())
                    self.assertEqual(0, icon.get_at((0, 0)).a)
                    colors = {tuple(icon.get_at((x, y))) for y in range(32) for x in range(32)
                              if icon.get_at((x, y)).a > 64}
                    self.assertGreater(len(colors), 80, 'Expected painted art rather than a line glyph')

    def test_invalid_sizes_and_unknown_keys_are_rejected(self):
        for size in (0, -1, 257, True, 32.0):
            with self.subTest(size=size), self.assertRaises(ValueError):
                load_icon(None, 'help', size)
        with self.assertRaises(KeyError):
            load_icon(None, 'missing-control', 32)


if __name__ == '__main__':
    unittest.main()
