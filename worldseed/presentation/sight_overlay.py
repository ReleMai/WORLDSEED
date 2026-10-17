"""Wall-clock-only Alt radius fade; never advances simulation or discovery."""
from dataclasses import dataclass
from functools import lru_cache
from .gl_worldspace import SpriteCommand


@dataclass
class SightOverlayFade:
    level: float = 0.
    last_time: float | None = None

    def advance(self, held, now):
        dt=0. if self.last_time is None else max(0.,now-self.last_time)
        self.last_time=now
        self.level=max(0.,min(1.,self.level+dt*(1/.18 if held else -1/.25)))
        return self.level*self.level*(3.-2.*self.level)


@lru_cache(maxsize=1)
def _ring():
    import pygame as pg
    surface=pg.Surface((1024,1024),pg.SRCALPHA)
    pg.draw.circle(surface,(194,205,184,175),(512,512),500,4)
    pg.draw.circle(surface,(45,51,42,65),(512,512),506,2)
    surface=pg.transform.smoothscale(surface,(512,512))
    return ('alt-sight-ring',1,pg.image.tobytes(surface,'RGBA'),512,512)


def radius_command(center,radius,viewport,opacity):
    if radius<2 or opacity<=0:return None
    x,y=center
    size=radius*256/250
    return SpriteCommand('alt-sight-radius',*_ring(),
                         (x-size,y-size,x+size,y+size),(viewport,),opacity=opacity)
