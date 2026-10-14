"""Batching wet-ground alpha blits preserves exact drawn pixels."""
import os
import unittest
from unittest.mock import patch

from worldseed.presentation.weather_fx import WeatherFxRenderer


class WetGroundBatchTests(unittest.TestCase):
    def test_batch_matches_legacy_blit_order_and_reuses_tuple_source(self):
        with patch.dict(os.environ,{'SDL_VIDEODRIVER':'dummy','SDL_AUDIODRIVER':'dummy'}):
            import pygame
            pygame.init()
            try:
                fx=WeatherFxRenderer(pygame)
                cells=tuple((pygame.Rect(x*24,y*24,24,24),terrain)
                    for y in range(8) for x in range(12)
                    for terrain in (('core:grass','core:sand','core:rock')[(x+y)%3],))
                expected=pygame.Surface((320,225),pygame.SRCALPHA)
                actual=pygame.Surface((320,225),pygame.SRCALPHA)
                expected.fill((63,71,54,255))
                actual.fill((63,71,54,255))
                for rect,terrain in cells:
                    sprite=fx._wet_tile(terrain,rect.width,64)
                    if sprite is not None:expected.blit(sprite,rect.topleft)
                fx.draw_wet_ground(actual,cells,64)
                batch=fx._wet_batch
                fx.draw_wet_ground(actual,cells,0)
                self.assertIs(batch,fx._wet_batch)
                # A repeated draw on a fresh surface uses the same cached
                # sprite destinations without copying or reallocating cells.
                repeat=pygame.Surface((320,225),pygame.SRCALPHA)
                repeat.fill((63,71,54,255))
                fx.draw_wet_ground(repeat,cells,64)
                self.assertIs(batch,fx._wet_batch)
                self.assertEqual(pygame.image.tobytes(actual,'RGBA'),
                                 pygame.image.tobytes(expected,'RGBA'))
                self.assertEqual(pygame.image.tobytes(repeat,'RGBA'),
                                 pygame.image.tobytes(expected,'RGBA'))
                # Changes in wetness or source identity invalidate the batch.
                fx.draw_wet_ground(repeat,cells,85)
                self.assertIsNot(fx._wet_batch,batch)
                newer=tuple(cells)
                if newer is cells:newer=tuple(list(cells))
                fx.draw_wet_ground(repeat,newer,85)
                self.assertIs(fx._wet_batch_source,newer)
            finally:
                pygame.quit()


if __name__=='__main__':
    unittest.main()
