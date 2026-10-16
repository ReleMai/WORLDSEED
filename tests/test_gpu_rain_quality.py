"""Actual post-shader rain/visibility checks; EGL is optional, never hardware proof."""
from __future__ import annotations

from dataclasses import replace
import unittest

from worldseed.presentation.gl_atmosphere import (
    AtmosphereFrame, GLAtmospherePass, WorldLight,
)


class _ScreenContext:
    def __init__(self, context, screen):
        self.context, self.screen = context, screen

    def __getattr__(self, key):
        return getattr(self.context, key)

    def __setattr__(self, key, value):
        if key in ('context', 'screen'):
            object.__setattr__(self, key, value)
        else:
            setattr(self.context, key, value)


class GPURainQuality(unittest.TestCase):
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
        self.post.scene_color.write(bytes((62, 79, 71, 255)) * self.width * self.height)
        self.frame = AtmosphereFrame(720, sun=1., elapsed_seconds=2.125)

    def render(self, **changes):
        self.post.present(replace(self.frame, **changes))
        return self.target.read(components=3, alignment=1)

    def rain_field(self, **changes):
        dry = self.render(rain=0., **changes)
        wet = self.render(rain=1., **changes)
        return [sum(wet[index + c] - dry[index + c] for c in range(3)) / 3
                for index in range(0, len(wet), 3)]

    def test_unknown_and_discovery_memory_ignore_live_weather_and_light(self):
        # Fractional alpha is discovery memory from the scene's straight-alpha
        # blending; RGB has already been dimmed before the atmosphere pass.
        row = (bytes((0, 0, 0, 0)) * 128 + bytes((26, 33, 30, 45)) * 128
               + bytes((62, 79, 71, 255)) * 256)
        self.post.scene_color.write(row * self.height)
        dry = self.render()
        wet = self.render(rain=1., fog=1., cloud=1., sun=.18,
                          lights=(WorldLight(192, 192, 900, 2.),))
        later = self.render(snow=1., fog=1., cloud=1., elapsed_seconds=400., sun=1.)
        for y in range(self.height):
            start = y * self.width * 3
            self.assertEqual(wet[start:start + 128*3], bytes(128*3))
            self.assertEqual(wet[start + 128*3:start + 256*3], bytes((26, 33, 30))*128)
            self.assertEqual(wet[start:start + 256*3], dry[start:start + 256*3])
            self.assertEqual(wet[start:start + 256*3], later[start:start + 256*3])
        self.assertNotEqual(dry, wet)

    def test_rain_is_reproducible_and_uses_visual_clock(self):
        first = self.render(rain=.8)
        self.assertEqual(first, self.render(rain=.8))
        self.assertNotEqual(first, self.render(rain=.8, elapsed_seconds=2.25))

    def test_stacked_remembered_props_keep_weather_classification_and_unknown_black(self):
        from worldseed.presentation.gl_worldspace import GLWorldspaceRenderer, SpriteCommand
        renderer = GLWorldspaceRenderer(self.context,self.width,self.height)
        self.addCleanup(renderer.close)
        clip = ((0.,0.,float(self.width),float(self.height)),)
        def command(uid,bounds,remembered,color):
            return SpriteCommand(uid,uid,0,bytes((*color,255)),1,1,bounds,clip,
                                 opacity=.62 if remembered else 1.,remembered=remembered)
        rows=[command('memory-floor',(128.,0.,256.,384.),True,(80,90,60))]
        rows += [command('memory-prop'+str(i),(140.,30.,244.,354.),True,(100,65,40))
                 for i in range(12)]
        rows += [command('current',(256.,0.,512.,384.),False,(62,79,71))]
        renderer.draw(rows,target=self.post.scene_target,clear=(0.,0.,0.,0.))
        source = self.post.scene_target.read(components=4,alignment=1)
        self.assertEqual(source[:128*4],bytes(128*4))
        self.assertEqual(source[(192*self.width+192)*4+3],0)
        dry=self.render()
        wet=self.render(rain=1.,fog=1.,cloud=1.,sun=.18,
                        lights=(WorldLight(192,192,900,2.),))
        self.assertGreater(sum(dry[128*3:256*3]),0)
        for y in range(self.height):
            start=y*self.width*3
            self.assertEqual(dry[start:start+256*3],wet[start:start+256*3])
            self.assertEqual(wet[start:start+128*3],bytes(128*3))
        self.assertNotEqual(dry,wet)

    def test_translucent_current_foliage_still_receives_live_weather_and_grade(self):
        # Standard sprite alpha blending can lower alpha even over opaque
        # current ground. It must not be confused with memory's .42 squared.
        for alpha in (122, 191):
            with self.subTest(alpha=alpha):
                self.post.scene_color.write(bytes((62, 79, 71, alpha)) *
                                            self.width * self.height)
                daylight = self.render()
                night = self.render(sun=.18)
                wet = self.render(rain=1.)
                self.assertNotEqual(daylight, night)
                self.assertNotEqual(daylight, wet)

    def test_sparse_subdued_rain_and_monotonic_storm_intensity(self):
        dry = self.render()
        mild = self.render(rain=.3)
        storm = self.render(rain=1.)
        mild_delta = [wet-base for wet, base in zip(mild, dry)]
        storm_delta = [wet-base for wet, base in zip(storm, dry)]
        self.assertGreater(sum(mild_delta), 0)
        self.assertGreater(sum(storm_delta), sum(mild_delta) * 2)
        self.assertTrue(all(high >= low for low, high in zip(mild_delta, storm_delta)))
        coverage = sum(value > 2 for value in storm_delta) / len(storm_delta)
        self.assertGreater(coverage, .005)
        self.assertLess(coverage, .15)
        self.assertLess(max(storm_delta), 80)
        self.assertLess(sum(storm_delta) / len(storm_delta), 4.)

    def test_rain_falls_down_continuously_in_top_origin_world(self):
        before = self.rain_field(elapsed_seconds=2.)
        after = self.rain_field(elapsed_seconds=2.01)
        # RGB readback is bottom-first, so DOWN in world coordinates is a
        # negative readback-row shift. Independent bands fall 2.6/3.5/4.7 px.
        def correlation(dy):
            return sum(before[y*self.width+x] * after[(y+dy)*self.width+x]
                       for y in range(8, self.height-8)
                       for x in range(self.width))
        downward = max(correlation(dy) for dy in (-3, -4, -5))
        upward = max(correlation(dy) for dy in (3, 4, 5))
        self.assertGreater(downward, upward * 2)
        almost = self.rain_field(elapsed_seconds=2.0001)
        self.assertLess(sum(abs(a-b) for a, b in zip(before, almost)) / len(before), .1)

    def test_camera_translation_preserves_world_aligned_particle_positions(self):
        baseline = self.render(rain=1.)
        shifted = self.render(rain=1., camera_pixel_x=17., camera_pixel_y=11.)
        errors = []
        for y in range(11, self.height):
            for x in range(self.width-17):
                old = ((y-11)*self.width + x+17)*3
                new = (y*self.width+x)*3
                errors.extend(abs(baseline[old+c]-shifted[new+c]) for c in range(3))
        self.assertLess(sum(errors)/len(errors), .02)

    def test_wind_moves_drops_in_the_authoritative_wind_direction(self):
        before = self.rain_field(elapsed_seconds=2., wind_x=4.)
        after = self.rain_field(elapsed_seconds=2.03, wind_x=4.)
        def correlation(dx, dy):
            return sum(before[y*self.width+x] * after[(y+dy)*self.width+x+dx]
                       for y in range(18, self.height-18)
                       for x in range(8, self.width-8))
        down = (-8, -10, -14)
        with_wind = max(correlation(dx, dy) for dx in (3, 4) for dy in down)
        against = max(correlation(dx, dy) for dx in (-3, -4) for dy in down)
        self.assertGreater(with_wind, against * 2.)

    def test_night_rain_is_subdued_and_authorized_lights_pick_it_up(self):
        day = self.rain_field(sun=1.)
        night = self.rain_field(sun=.18)
        self.assertLess(sum(night), sum(day) * .65)
        light = WorldLight(128, 192, 160, 1.5, (1., .65, .35))
        lit = self.rain_field(sun=.18, lights=(light,))
        def total(field, start, stop):
            return sum(field[y*self.width+x] for y in range(self.height)
                       for x in range(start, stop))
        self.assertGreater(total(lit, 50, 206), total(night, 50, 206) * 1.2)
        self.assertEqual(total(lit, 360, 512), total(night, 360, 512))


if __name__ == '__main__':
    unittest.main()
