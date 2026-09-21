import unittest
from worldseed.core.coords import WorldPos, split_world


class CoordTests(unittest.TestCase):
    def test_boundaries(self):
        cases = [
            ((0, 0), ((0, 0), (0, 0))),
            ((31, 31), ((0, 0), (31, 31))),
            ((32, 32), ((1, 1), (0, 0))),
            ((-1, -1), ((-1, -1), (31, 31))),
            ((-32, -32), ((-1, -1), (0, 0))),
            ((-33, -33), ((-2, -2), (31, 31))),
        ]
        for (x, y), ((cx, cy), (lx, ly)) in cases:
            key, got_lx, got_ly = split_world(WorldPos(x, y))
            self.assertEqual((key.x, key.y), (cx, cy))
            self.assertEqual((got_lx, got_ly), (lx, ly))
