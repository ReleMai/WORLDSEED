"""Small presentation-only foundation for layered atmospheric effects.

Frames contain copied scalar samples, never simulation objects. Emitters create
bounded, deterministic visual particles from world-space cells; they retain no
history and do not advance game time. Effect registration controls composition.
"""
from dataclasses import dataclass
from math import floor
from typing import Callable

from worldseed.core.rng import hash_u64


@dataclass(frozen=True)
class WeatherSample:
    cloud_cover: int = 0
    rain: int = 0
    fog: int = 0
    storm_intensity: int = 0
    wind_dx: int = 0
    wind_dy: int = 0
    daylight: int = 65535
    sunrise: int = 360
    sunset: int = 1080
    night: bool = False

    @classmethod
    def capture(cls, weather, lighting=None):
        bounded = lambda name, upper: max(0, min(upper, int(weather.get(name, 0))))
        return cls(bounded('cloud_cover',100), bounded('rain',10), bounded('fog',100),
                   bounded('storm_intensity',100), int(weather.get('wind_dx',0)),
                   int(weather.get('wind_dy',0)), int(getattr(lighting,'daylight',65535)),
                   int(getattr(lighting,'sunrise_minute',360)), int(getattr(lighting,'sunset_minute',1080)),
                   bool(getattr(lighting,'phase','day')=='night'))


@dataclass(frozen=True)
class EffectFrame:
    seed: bytes
    width: int
    height: int
    left: int
    top: int
    tile_px: int
    elapsed_ms: int
    game_minute: int
    weather: WeatherSample


@dataclass(frozen=True)
class VisualParticle:
    identity: int
    x: float
    y: float
    age: float
    opacity: float


@dataclass(frozen=True)
class FieldEmitter:
    namespace: str
    spacing: int
    reach: int = 55
    drift_scale: float = 1.0
    lifetime_ms: int = 360000
    max_particles: int = 256

    def particles(self, frame):
        spacing = max(1, self.spacing)
        time = max(0, frame.elapsed_ms)
        dx = frame.weather.wind_dx * time / 4680000 * self.drift_scale
        dy = frame.weather.wind_dy * time / 4680000 * self.drift_scale
        xmin = floor((frame.left-dx-self.reach)/spacing)
        xmax = floor((frame.left+frame.width/max(1,frame.tile_px)-dx+self.reach)/spacing)
        ymin = floor((frame.top-dy-self.reach)/spacing)
        ymax = floor((frame.top+frame.height/max(1,frame.tile_px)-dy+self.reach)/spacing)
        # An absurd viewport must not turn presentation into an unbounded scan.
        # Normal supported zoom/window sizes are well below this 32x32 window.
        if xmax-xmin > 31:
            middle=(xmin+xmax)//2; xmin,xmax=middle-15,middle+16
        if ymax-ymin > 31:
            middle=(ymin+ymax)//2; ymin,ymax=middle-15,middle+16
        count = 0
        for y in range(ymin,ymax+1):
            for x in range(xmin,xmax+1):
                cell = hash_u64(frame.seed,self.namespace,x,y)
                life = max(1,self.lifetime_ms) + cell % max(1,self.lifetime_ms//2)
                cycle, age = divmod(time + (cell>>12)%life, life)
                token = hash_u64(frame.seed,self.namespace,'life',x,y,cycle)
                px = x*spacing + ((cell>>24)%1000)*spacing/1000 + dx
                py = y*spacing + ((cell>>36)%1000)*spacing/1000 + dy
                # Cull to the actual view plus sprite reach before the budget.
                if not (frame.left-self.reach <= px <= frame.left+frame.width/max(1,frame.tile_px)+self.reach and
                        frame.top-self.reach <= py <= frame.top+frame.height/max(1,frame.tile_px)+self.reach):
                    continue
                t = age/life
                fade = min(1.0,t/0.12,(1-t)/0.16)
                opacity = fade*fade*(3-2*fade)
                yield VisualParticle(token,px,py,t,opacity)
                count += 1
                if count >= max(1,self.max_particles):
                    return


class EffectStack:
    """Ordered render passes; new effects receive the same immutable frame."""
    def __init__(self):
        self._passes = {}

    def register(self, name: str, order: int, render: Callable, animated: Callable):
        if name in self._passes:
            raise ValueError('Duplicate atmosphere effect: '+name)
        if len(self._passes) >= 32:
            raise ValueError('Atmosphere effect registration budget exceeded')
        self._passes[name] = (order,render,animated)

    def animated(self, weather):
        return any(row[2](weather) for row in self._passes.values())

    def draw(self, screen, rect, frame):
        clip = screen.get_clip()
        screen.set_clip(clip.clip(rect))
        try:
            for name, (_,render,_) in sorted(self._passes.items(),key=lambda row:(row[1][0],row[0])):
                for surface in render(frame):
                    if surface is not None:
                        screen.blit(surface,rect.topleft)
        finally:
            screen.set_clip(clip)
