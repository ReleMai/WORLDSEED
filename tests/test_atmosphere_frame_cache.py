"""Atmospheric caches retain exact visual frames but never freeze animation."""
import os
import unittest
from unittest.mock import Mock,patch

from worldseed.presentation.atmosphere import EffectFrame,WeatherSample
from worldseed.presentation.clouds import CloudRenderer
from worldseed.presentation.weather_fx import WeatherFxRenderer


class AtmosphereFrameCacheTests(unittest.TestCase):
    def test_composited_cloud_cache_tracks_phase_weather_and_camera(self):
        with patch.dict(os.environ,{'SDL_VIDEODRIVER':'dummy','SDL_AUDIODRIVER':'dummy'}):
            import pygame
            pygame.init()
            try:
                clouds=CloudRenderer(pygame)
                def layers(w,h,*args,**kwargs):
                    shadow=pygame.Surface((w,h),pygame.SRCALPHA)
                    cloud=pygame.Surface((w,h),pygame.SRCALPHA)
                    shadow.fill((20,30,40,35));cloud.fill((80,90,100,40))
                    return shadow,cloud
                mock=Mock(side_effect=layers)
                kwargs=dict(storm=20,minute=720,daylight=45000,sunrise=360,sunset=1080)
                with patch.object(clouds,'layers',mock):
                    a=clouds.composited_layers(480,280,b'cloud-test',60,3,4,8,9,28,1590,**kwargs)[0]
                    b=clouds.composited_layers(480,280,b'cloud-test',60,3,4,8,9,28,1594,**kwargs)[0]
                    self.assertIs(a,b)
                    self.assertEqual(mock.call_count,1)
                    changed=clouds.composited_layers(480,280,b'cloud-test',60,3,4,8,9,28,1623,**kwargs)[0]
                    self.assertIsNot(changed,b)
                    self.assertEqual(pygame.image.tobytes(changed,'RGBA'),pygame.image.tobytes(b,'RGBA'))
                    move=clouds.composited_layers(480,280,b'cloud-test',60,3,4,9,9,28,1623,**kwargs)[0]
                    self.assertIsNot(move,changed)
                    sun=clouds.composited_layers(480,280,b'cloud-test',60,3,4,9,9,28,1623,**dict(kwargs,daylight=44000))[0]
                    self.assertIsNot(sun,move)
                    self.assertLessEqual(len(clouds._composited_frames),2)
                    self.assertLessEqual(clouds._composited_bytes,64*1024*1024)
            finally:
                pygame.quit()

    def test_fog_cache_reuses_only_matching_alpha_and_dimensions(self):
        with patch.dict(os.environ,{'SDL_VIDEODRIVER':'dummy','SDL_AUDIODRIVER':'dummy'}):
            import pygame
            pygame.init()
            try:
                fx=WeatherFxRenderer(pygame)
                def frame(w,h,fog):
                    return EffectFrame(b'seed',w,h,0,0,28,1200,720,WeatherSample(fog=fog))
                first=fx._fog_layers(frame(320,240,55))[0]
                second=fx._fog_layers(frame(320,240,55))[0]
                self.assertIs(first,second)
                self.assertIsNot(fx._fog_layers(frame(320,240,60))[0],second)
                self.assertIsNot(fx._fog_layers(frame(640,240,60))[0],second)
                self.assertEqual(fx._fog_layers(frame(640,240,0)),())
            finally:
                pygame.quit()


if __name__=='__main__':
    unittest.main()
