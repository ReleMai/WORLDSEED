"""M2 GPU probe input validation is display-independent."""
import unittest
from tools.gpu_compositing_probe import estimate_texture_bytes, percentile, validate

class GPUCompositingProbeTests(unittest.TestCase):
    def test_interpolated_percentiles(self):
        self.assertIsNone(percentile([], 95))
        self.assertEqual(percentile([5, 1, 3], 50), 3)
        self.assertEqual(percentile([1, 2, 3, 4, 5], 95), 4.8)

    def test_working_set_is_bounded_through_native_4k(self):
        self.assertEqual(estimate_texture_bytes(3840, 2160), 165888000)
        validate(3840, 2160, 120)
        for values in ((500, 720, 30), (1920, 1080, 0), (3841, 2160, 120)):
            with self.assertRaises(ValueError):
                validate(*values)

if __name__ == '__main__':
    unittest.main()
