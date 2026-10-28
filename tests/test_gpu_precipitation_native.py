"""Optional actual main-window cover reuse, animation and authority contracts."""
from __future__ import annotations

from dataclasses import replace
import unittest
from unittest.mock import patch

from tests import test_gpu_main_game as native


class GPUPrecipitationNativeTests(unittest.TestCase):
    setUpClass = classmethod(native.GPUMainGameTests.setUpClass.__func__)
    setUp = native.GPUMainGameTests.setUp

    def present(self):
        native.GPUMainGameTests.present(self)

    def test_wet_idle_reuses_capture_and_static_cover_while_canopies_track_sway(self):
        before = self.fixture.authority_fingerprint()
        self.present()
        term = self.term
        self.assertTrue(term._precipitation_commands)
        self.assertTrue(any(row.sway_px for row in term._precipitation_commands))
        wet = replace(term._snapshot.atmosphere(2.125), rain=1., snow=0.)
        uploads = term._ui_gpu.uploads
        with patch.object(type(term._snapshot), 'atmosphere', return_value=wet), \
                patch('worldseed.ui.gpu_terminal.capture_live_scene',
                      side_effect=AssertionError('idle precipitation recaptured world')), \
                patch.object(term._post, 'present', wraps=term._post.present) as post, \
                patch.object(term._world_renderer, 'draw', wraps=term._world_renderer.draw) as draw:
            term._precipitation_dirty = True
            count = term._gpu_cover_frames
            term._composite()
            self.assertEqual(term._gpu_cover_frames, count+1)
            self.assertTrue(post.call_args.kwargs['cover_enabled'])
            coverage, scene = draw.call_args_list[-2:]
            self.assertTrue(coverage.kwargs['coverage_only'])
            self.assertFalse(scene.kwargs.get('coverage_only', False))
            self.assertEqual(coverage.kwargs['frame_time_seconds'],
                             scene.kwargs['frame_time_seconds'])
            self.assertGreater(max(term._post.cover_target.read(components=1, alignment=1)), 0)
            term._composite()
            self.assertEqual(term._gpu_cover_frames, count+2)

            # Freeze only the detached visual sway to exercise static-roof cache
            # ownership using the same admitted source art and exact clips.
            term._world_commands = tuple(replace(row, sway_px=0.) for row in term._world_commands)
            term._precipitation_commands = tuple(replace(row, sway_px=0.)
                                                  for row in term._precipitation_commands)
            term._precipitation_dirty = True
            term._composite()
            count = term._gpu_cover_frames
            texture = term._post.cover_color
            term._composite()
            self.assertEqual(term._gpu_cover_frames, count)
            self.assertIs(term._post.cover_color, texture)
            self.assertEqual(term._ui_gpu.uploads, uploads)

            with patch.object(type(term._snapshot), 'atmosphere', return_value=replace(wet, rain=0.)):
                term._composite()
                self.assertFalse(post.call_args.kwargs['cover_enabled'])
                self.assertEqual(term._gpu_cover_frames, count)

            term._precipitation_commands = ()
            term._precipitation_dirty = True
            term._composite()
            self.assertFalse(post.call_args.kwargs['cover_enabled'])
            self.assertIsNone(term._precipitation_report)
            self.assertEqual(set(term._post.cover_target.read(components=1, alignment=1)), {0})
        self.assertEqual(self.fixture.authority_fingerprint(), before)

        old_texture = term._post.cover_color
        term._resize(640, 480)
        self.assertEqual(term._precipitation_commands, ())
        self.assertTrue(term._precipitation_dirty)
        self.assertEqual(term._post.cover_color.size, (640, 480))
        self.assertIsNot(term._post.cover_color, old_texture)
        self.present()
        self.assertEqual(self.fixture.authority_fingerprint(), before)
        self.assertEqual(self.set_mode.call_count, 1)


if __name__ == '__main__':
    unittest.main()
