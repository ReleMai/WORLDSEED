import unittest
from worldseed.core.rng import PCG32, derive_seed


class RngTests(unittest.TestCase):
    def test_seed_stability(self):
        seed = b"abc"
        self.assertEqual(derive_seed(seed, "terrain", 1, -2), derive_seed(seed, "terrain", 1, -2))
        self.assertNotEqual(derive_seed(seed, "terrain", 1, -2), derive_seed(seed, "creatures", 1, -2))

    def test_pcg_repeatability(self):
        a = PCG32(123456)
        b = PCG32(123456)
        self.assertEqual([a.u32() for _ in range(100)], [b.u32() for _ in range(100)])
