"""M2 real-scene GPU bridge: bounded inputs, observable source, safe fallback."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.gpu_reference_scene_probe import (
    MAX_TEXTURE_BYTES, benchmark, capture_real_frames, texture_budget, validate,
)


class GPUReferenceProbePureTests(unittest.TestCase):
    def test_two_captured_gpu_frames_fit_4k_budget(self):
        self.assertEqual(texture_budget(3840, 2160), 66355200)
        self.assertLess(texture_budget(3840, 2160), MAX_TEXTURE_BYTES)
        validate('forest', 3840, 2160, 48, 120, 4, -4)

    def test_rejects_bad_dimensions_camera_or_unbounded_frames(self):
        valid = ('forest', 1280, 720, 28, 120, 1, 0)
        for key, bad in (
            (0, 'missing'), (1, 639), (2, 2161), (3, 30),
            (4, 0), (4, 601), (5, 5), (6, -5),
            (1, True), (4, True),
        ):
            values = list(valid)
            values[key] = bad
            with self.subTest(key=key, bad=bad), self.assertRaises(ValueError):
                validate(*values)

    def test_dummy_display_cannot_masquerade_as_accelerated_gpu(self):
        with self.assertRaisesRegex(ValueError, 'dummy'):
            benchmark(10, 640, 480, software_only=False, headless=True)


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'requires pygame-ce')
class GPUReferenceSourceTests(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
        os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

    def test_real_software_frames_include_camera_delta_without_state_changes(self):
        frames, metadata = capture_real_frames('forest', 640, 480, 28, 1, 0,
                                               headless=True)
        import pygame as pg
        self.assertEqual(len(frames), 2)
        self.assertTrue(metadata['authority_unchanged'])
        self.assertEqual(metadata['camera_step_cells'], [1, 0])
        self.assertEqual(metadata['phase_step_ms'], 231)
        self.assertTrue(all(surface.get_size() == (640, 480) for surface in frames))
        self.assertNotEqual(metadata['pixel_sha256'][0], metadata['pixel_sha256'][1])
        self.assertEqual(metadata['pixel_sha256'], [
            __import__('hashlib').sha256(pg.image.tobytes(frame, 'RGB')).hexdigest()
            for frame in frames
        ])

    def test_fallback_is_explicit_and_reports_real_source(self):
        result = benchmark(10, 640, 480, zoom=28, scene='camp',
                           software_only=True, headless=True)
        self.assertFalse(result['hardware_confirmed'])
        self.assertTrue(result['production_renderer_unchanged'])
        self.assertFalse(result['gpu_compositing_of_individual_alpha_layers'])
        self.assertIsNone(result['gpu_present'])
        self.assertEqual(result['software_copy']['samples'], 10)
        self.assertTrue(result['source_frames']['authority_unchanged'])


if __name__ == '__main__':
    unittest.main()
