"""Presentation continuity and frozen-input regressions (SDL dummy display)."""
import copy
import os
import unittest
from unittest.mock import Mock

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.world.lighting import LightingSystem


@unittest.skipUnless(PygameTerminal.available(), 'pygame optional')
class WeatherAnimationTests(unittest.TestCase):
    def setUp(self):
        self.term = PygameTerminal()
        self.term.enter()
        self.pg = self.term.pg
        self.fx = self.term._weather_fx

    def tearDown(self):
        self.term.restore()

    def test_lighting_fades_and_retargets_without_jump(self):
        lights = LightingSystem()
        day, night = lights.at(720), lights.at(0)
        self.fx.set_lighting(day, 0)
        start = self.fx.lighting_sample(0)
        self.fx.set_lighting(night, 100)
        self.assertEqual(start, self.fx.lighting_sample(100))
        middle = self.fx.lighting_sample(425)
        self.assertLess(start[-1], middle[-1])
        self.assertLess(middle[-1], night.darkness_alpha)
        self.fx.set_lighting(day, 425)
        self.assertEqual(middle, self.fx.lighting_sample(425))
        self.assertEqual(start, self.fx.lighting_sample(1075))
        self.assertFalse(self.fx.lighting_transition_active(1075))
        self.fx.set_lighting(night, 1100, reset=True)
        self.assertEqual(night.darkness_alpha, self.fx.lighting_sample(1100)[-1])

    def test_clouds_move_less_than_a_tile_and_remain_world_anchored(self):
        def cloud(left, elapsed):
            return self.fx.cloud_shadow_surface(640,360,b'cloud-anchor',100,1024,0,left,0,20,elapsed)
        a, b = cloud(0,0), cloud(0,330)
        self.assertNotEqual(self.pg.image.tobytes(a,'RGBA'), self.pg.image.tobytes(b,'RGBA'))
        a = b
        shifted = cloud(1,330)
        self.assertEqual(self.pg.image.tobytes(a.subsurface((20,0,620,360)),'RGBA'),
                         self.pg.image.tobytes(shifted.subsurface((0,0,620,360)),'RGBA'))
        self.assertLessEqual(len(self.fx._cloud_cache),2)

    def test_rain_no_longer_repeats_after_sixteen_frames(self):
        def rain(phase):
            return self.fx.rain_surface(640,360,b'rain',phase,8,650,0)
        first = self.pg.image.tobytes(rain(0),'RGBA')
        self.assertNotEqual(first,self.pg.image.tobytes(rain(16),'RGBA'))
        for phase in range(20):
            rain(phase)
        self.assertEqual(first,self.pg.image.tobytes(rain(0),'RGBA'))
        self.assertLessEqual(len(self.fx._rain_cache),2)

    def test_idle_lighting_animates_clear_weather_without_world_queries(self):
        term=self.term
        used=self.pg.Rect(10,10,320,200)
        term.screen.fill((120,140,100))
        day,night=LightingSystem().at(720),LightingSystem().at(0)
        self.fx.set_lighting(day,0)
        self.fx.set_lighting(night,100)
        ctx=dict(seed=b'test',rain=0,cloud_cover=0,wetness=0,wind_dx=0,wind_dy=0,
                 fog=0,night=True,lighting=night,fire_rects=[],left=0,top=0,tile_px=20)
        original=copy.deepcopy(ctx)
        term._weather_animation_context=ctx
        term._weather_static_snapshot=term.screen.subsurface(used).copy()
        term._hover_map_snapshot=term._weather_static_snapshot.copy()
        term._hover_context={'used':used}
        term._restore_hover_damage=Mock()
        term._refresh_hover_only=Mock()
        term._animate_idle_effects(100)
        first=self.pg.image.tobytes(term.screen.subsurface(used),'RGB')
        term._animate_idle_effects(750)
        second=self.pg.image.tobytes(term.screen.subsurface(used),'RGB')
        self.assertNotEqual(first,second)
        self.assertEqual(ctx,original)
        self.assertEqual(term.screen.get_at((0,0))[:3],(120,140,100))
        term._animate_idle_effects(1000)
        self.assertEqual(second,self.pg.image.tobytes(term.screen.subsurface(used),'RGB'))
