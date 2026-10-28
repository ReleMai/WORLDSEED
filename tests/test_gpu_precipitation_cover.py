"""Real EGL pixels for precipitation interception; no hardware acceptance claim."""
from __future__ import annotations

from dataclasses import replace
import unittest

from tests.test_gpu_rain_quality import _ScreenContext
from worldseed.presentation.gl_atmosphere import (
    AtmosphereFrame, GLAtmospherePass, MAX_FRAMEBUFFER_BYTES, WorldLight,
)
from worldseed.presentation.gl_worldspace import (
    GLWorldspaceRenderer, GPUBackendUnavailable, SpriteCommand,
)


class GPUPrecipitationCoverTests(unittest.TestCase):
    width, height = 512, 384

    @classmethod
    def setUpClass(cls):
        try:
            import moderngl
        except ImportError:
            raise unittest.SkipTest('optional ModernGL unavailable')
        try:
            cls.context = moderngl.create_standalone_context(backend='egl', require=330)
        except Exception as exc:
            raise unittest.SkipTest(f'optional EGL context unavailable: {exc}')

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'context'):
            cls.context.release()

    def setUp(self):
        self.output = self.context.texture((self.width, self.height), 4)
        self.addCleanup(self.output.release)
        self.target = self.context.framebuffer(color_attachments=[self.output])
        self.addCleanup(self.target.release)
        self.post = GLAtmospherePass(_ScreenContext(self.context, self.target),
                                     self.width, self.height)
        self.addCleanup(self.post.close)
        self.renderer = GLWorldspaceRenderer(self.context, self.width, self.height)
        self.addCleanup(self.renderer.close)
        self.post.scene_color.write(bytes((62, 79, 71, 255)) * self.width * self.height)
        self.frame = AtmosphereFrame(720, sun=1., elapsed_seconds=2.125)

    def command(self, uid='roof', *, alpha=255, **changes):
        return SpriteCommand(uid, uid, 0, bytes((255, 255, 255, alpha)), 1, 1,
                             (0., 0., float(self.width), float(self.height)),
                             ((0., 0., float(self.width), float(self.height)),),
                             precipitation_cover=True, **changes)

    def cover(self, *commands):
        self.renderer.draw(commands, target=self.post.cover_target,
                           coverage_only=True, clear=(0., 0., 0., 0.))
        return self.post.cover_target.read(components=1, alignment=1)

    def render(self, *, cover_enabled=True, **changes):
        self.post.present(replace(self.frame, **changes), cover_enabled=cover_enabled)
        return self.target.read(components=3, alignment=1)

    def delta(self, *, kind='rain', cover_enabled=True):
        dry = self.render(cover_enabled=cover_enabled)
        wet = self.render(cover_enabled=cover_enabled, **{kind: 1.})
        return tuple(a-b for a, b in zip(wet, dry))

    def rectangle_sum(self, raw, rect, *, channels=3):
        x0, y0, x1, y1 = rect
        return sum(sum(raw[((self.height-1-y)*self.width+x0)*channels:
                           ((self.height-1-y)*self.width+x1)*channels])
                   for y in range(y0, y1))

    def assert_rectangle_equal(self, first, second, rect):
        x0, y0, x1, y1 = rect
        for y in range(y0, y1):
            start = ((self.height-1-y)*self.width+x0)*3
            stop = start+(x1-x0)*3
            self.assertEqual(first[start:stop], second[start:stop])

    def test_opaque_roof_blocks_rain_and_snow_without_changing_other_atmosphere(self):
        raw = self.cover(self.command())
        self.assertEqual(set(raw), {255})
        for kind in ('rain', 'snow'):
            with self.subTest(kind=kind):
                self.assertGreater(sum(self.delta(kind=kind, cover_enabled=False)), 0)
                self.assertEqual(sum(self.delta(kind=kind)), 0)
                self.assertEqual(self.render(), self.render(**{kind: 1.}))
        grade = dict(sun=.25, fog=.7, cloud=.8,
                     lights=(WorldLight(150, 190, 180, 1.4),))
        self.assertEqual(self.render(**grade), self.render(cover_enabled=False, **grade))

    def test_alpha_courtyard_hole_remains_open_to_precipitation(self):
        # A wide transparent plateau avoids conflating texture edge filtering
        # with the open courtyard. The renderer uses the actual source alpha.
        rgba = bytes(channel for y in range(16) for x in range(16)
                     for channel in (255, 255, 255, 0 if 4 <= x < 12 and 4 <= y < 12 else 255))
        roof = replace(self.command(), rgba=rgba, image_w=16, image_h=16)
        raw = self.cover(roof)
        ring = (24, 24, 88, 360)
        courtyard = (168, 130, 344, 254)
        self.assertEqual(self.rectangle_sum(raw, ring, channels=1), 255 * 64 * 336)
        self.assertEqual(self.rectangle_sum(raw, courtyard, channels=1), 0)
        for kind in ('rain', 'snow'):
            field = self.delta(kind=kind)
            self.assertEqual(self.rectangle_sum(field, ring), 0)
            self.assertGreater(self.rectangle_sum(field, courtyard), 0)
            self.assert_rectangle_equal(self.render(), self.render(**{kind: 1.}), ring)

    def test_partial_canopies_attenuate_and_overlapping_cover_uses_alpha_union(self):
        for kind in ('rain', 'snow'):
            with self.subTest(kind=kind):
                self.post.clear_cover()
                open_field = sum(self.delta(kind=kind))
                raw = self.cover(self.command('canopy', alpha=128))
                self.assertTrue(all(127 <= value <= 129 for value in raw))
                half_field = sum(self.delta(kind=kind))
                self.assertGreater(half_field, open_field * .3)
                self.assertLess(half_field, open_field * .7)
                raw = self.cover(self.command('canopy-a', alpha=128), self.command('canopy-b', alpha=128))
                self.assertTrue(all(190 <= value <= 194 for value in raw))
                layered_field = sum(self.delta(kind=kind))
                self.assertGreater(layered_field, 0)
                self.assertLess(layered_field, half_field * .7)

    def test_cosmetic_player_reveal_does_not_open_a_hole_in_physical_cover(self):
        roof = self.command(opacity=.05, fade_center=(256., 192.),
                            fade_radius=600., local_alpha=.08)
        raw = self.cover(roof)
        self.assertEqual(set(raw), {255})
        self.assertEqual(sum(self.delta()), 0)
        self.assertEqual(self.render(), self.render(rain=1.))

    def test_cover_respects_asymmetric_exact_clips_and_memory_unknown_stay_frozen(self):
        row = (bytes((0, 0, 0, 0)) * 128 + bytes((26, 33, 30, 45)) * 128
               + bytes((62, 79, 71, 255)) * 256)
        self.post.scene_color.write(row * self.height)
        clip = (320., 24., 416., 172.)
        roof = replace(self.command(), clip_rects=(clip,))
        raw = self.cover(roof)
        for y in range(self.height):
            for x in range(self.width):
                expected = 255 if 320 <= x < 416 and 24 <= y < 172 else 0
                self.assertEqual(raw[(self.height-1-y)*self.width+x], expected)
        dry = self.render()
        wet = self.render(rain=1.)
        self.assertEqual(self.rectangle_sum(self.delta(), (320, 24, 416, 172)), 0)
        self.assert_rectangle_equal(dry, wet, (320, 24, 416, 172))
        self.assertGreater(self.rectangle_sum(self.delta(), (420, 24, 510, 370)), 0)
        severe = self.render(rain=1., fog=1., cloud=1., sun=.18,
                             lights=(WorldLight(192, 192, 900, 2.),))
        snow = self.render(snow=1., fog=1., elapsed_seconds=300.)
        for y in range(self.height):
            start = y*self.width*3
            for rendered in (wet, severe, snow):
                self.assertEqual(rendered[start:start+128*3], bytes(128*3))
                self.assertEqual(rendered[start:start+256*3], dry[start:start+256*3])

    def test_untagged_and_remembered_sprites_cannot_intercept_current_weather(self):
        raw = self.cover(replace(self.command('memory-roof'), remembered=True),
                         replace(self.command('ordinary-sprite'), precipitation_cover=False))
        self.assertEqual(set(raw), {0})
        self.assertEqual(self.render(rain=1.), self.render(rain=1., cover_enabled=False))
        with self.assertRaises(ValueError):
            replace(self.command(), precipitation_cover=1)

    def test_default_color_draw_and_post_api_ignore_cover_opt_in(self):
        command = self.command()
        self.renderer.draw((command,), target=self.post.scene_target, clear=(0., 0., 0., 0.))
        tagged = self.post.scene_target.read(components=4, alignment=1)
        self.renderer.draw((replace(command, precipitation_cover=False),),
                           target=self.post.scene_target, clear=(0., 0., 0., 0.))
        self.assertEqual(tagged, self.post.scene_target.read(components=4, alignment=1))
        self.cover(command)
        self.post.present(replace(self.frame, rain=1.))
        default = self.target.read(components=3, alignment=1)
        self.assertEqual(default, self.render(rain=1., cover_enabled=False))
        self.assertNotEqual(default, self.render(rain=1.))

    def test_cover_clear_reuses_resources_and_resize_replaces_and_bounds_targets(self):
        self.assertEqual(set(self.post.cover_target.read(components=1, alignment=1)), {0})
        self.cover(self.command())
        cover, target = self.post.cover_color, self.post.cover_target
        self.post.clear_cover()
        self.assertIs(self.post.cover_color, cover)
        self.assertIs(self.post.cover_target, target)
        self.assertEqual(set(target.read(components=1, alignment=1)), {0})
        self.cover(self.command())
        self.assertIs(self.post.cover_color, cover)
        self.post.resize(self.width, self.height)
        self.assertIs(self.post.cover_color, cover)
        self.post.resize(320, 240)
        self.assertIsNot(self.post.cover_color, cover)
        self.assertIsNot(self.post.cover_target, target)
        self.assertEqual(self.post.cover_color.size, (320, 240))
        self.assertEqual(self.post.cover_color.components, 1)
        self.assertLessEqual(320*240*5, MAX_FRAMEBUFFER_BYTES)
        self.assertEqual(set(self.post.cover_target.read(components=1, alignment=1)), {0})
        self.post.clear_cover()
        self.assertEqual(set(self.post.cover_target.read(components=1, alignment=1)), {0})
        current = self.post.cover_color
        with self.assertRaises(ValueError):
            self.post.resize(4000, 3000)
        self.assertIs(self.post.cover_color, current)
        self.post.close()
        self.assertIsNone(self.post.cover_color)
        self.assertIsNone(self.post.cover_target)
        with self.assertRaises(GPUBackendUnavailable):
            self.post.clear_cover()


if __name__ == '__main__':
    unittest.main()
