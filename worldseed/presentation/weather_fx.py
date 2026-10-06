"""Procedural weather/night art for the pygame local renderer.

These are presentation assets generated from deterministic WORLDSEED state:
wet-ground texture, soft projected cloud shadows, animated rain streak/splash
frames, fog haze, night/dawn/dusk grading, and local fire glow. No simulation
state is created or mutated here.
"""
from __future__ import annotations

from worldseed.core.rng import hash_u64
from worldseed.presentation.clouds import CloudRenderer
from worldseed.presentation.atmosphere import EffectFrame, WeatherSample, EffectStack
from worldseed.systems.illumination import LightSource, MAX_FIRE_RADIUS, Q, source_strength


class WeatherFxRenderer:
    def __init__(self, pygame_module) -> None:
        self.pg = pygame_module
        self._wet_cache = {}
        self._clouds = CloudRenderer(pygame_module)
        self._cloud_cache = self._clouds.frames
        self._rain_cache = {}
        self._rain_particles = {}
        self._glow_cache = {}
        self._lighting_target = None
        self._lighting_from = None
        self._lighting_started = 0
        self.effects = EffectStack()
        self.effects.register('fog',10,self._fog_layers,lambda w: False)
        self.effects.register('clouds',20,self._cloud_layers,lambda w: w.cloud_cover >= 12)
        self.effects.register('rain',30,self._rain_layers,lambda w: w.rain > 0)

    def has_animated_effects(self, weather):
        return self.effects.animated(WeatherSample.capture(weather))

    def draw_atmosphere(self, screen, rect, seed, weather, *, world_left,
                        world_top, tile_px, elapsed_ms, game_minute=720, lighting=None):
        frame = EffectFrame(bytes(seed),rect.width,rect.height,world_left,world_top,
                            tile_px,elapsed_ms,game_minute,WeatherSample.capture(weather,lighting))
        self.effects.draw(screen,rect,frame)

    def _fog_layers(self, frame):
        fog = frame.weather.fog
        if fog <= 4:
            return ()
        overlay = self.pg.Surface((frame.width,frame.height),self.pg.SRCALPHA)
        overlay.fill((172,184,184,min(82,8+fog//2)))
        return (overlay,)

    def _cloud_layers(self, frame):
        w = frame.weather
        return self._clouds.composited_layers(frame.width,frame.height,frame.seed,w.cloud_cover,
                                   w.wind_dx,w.wind_dy,frame.left,frame.top,frame.tile_px,
                                   frame.elapsed_ms,storm=w.storm_intensity,minute=frame.game_minute,
                                   daylight=w.daylight,sunrise=w.sunrise,sunset=w.sunset)

    def _rain_layers(self, frame):
        w = frame.weather
        return (self.rain_surface(frame.width,frame.height,frame.seed,frame.elapsed_ms//33,
                                  w.rain,w.wind_dx,w.wind_dy,w.night),)

    @staticmethod
    def _terrain_group(terrain_id: str) -> str:
        tid = str(terrain_id)
        if any(token in tid for token in ("ocean", "river", "water", "estuary", "lake")):
            return "water"
        if any(token in tid for token in ("sand", "shore", "floodplain")):
            return "sand"
        if any(token in tid for token in ("rock", "cave", "ore", "shaft")):
            return "rock"
        if any(token in tid for token in ("forest", "grass", "tundra", "scrub", "wetland")):
            return "vegetation"
        return "soil"

    def _wet_tile(self, terrain_id: str, tile_px: int, wetness: int):
        group = self._terrain_group(terrain_id)
        if group == "water" or wetness <= 2:
            return None
        band = max(1, min(5, int(wetness) // 20 + 1))
        key = ("wet", group, int(tile_px), band)
        cached = self._wet_cache.get(key)
        if cached is not None:
            return cached

        pg = self.pg
        surf = pg.Surface((tile_px, tile_px), pg.SRCALPHA)
        strength = 8 + band * 7
        if group == "vegetation":
            surf.fill((16, 30, 27, strength))
        elif group == "sand":
            surf.fill((47, 38, 28, strength + 5))
        elif group == "rock":
            surf.fill((18, 29, 40, strength + 7))
            # Sparse cool sheen reads as damp stone without looking metallic.
            step = max(5, tile_px // 5)
            for i in range(step // 2, tile_px, step):
                pg.draw.line(surf, (165, 184, 191, 10 + band * 3), (i, 1), (max(0, i - step // 2), tile_px - 2), 1)
        else:
            surf.fill((26, 31, 29, strength + 4))
        self._wet_cache[key] = surf
        return surf

    def draw_wet_ground(self, screen, cells, wetness: int) -> None:
        if wetness <= 2:
            return
        for rect, terrain_id in cells:
            overlay = self._wet_tile(terrain_id, rect.width, wetness)
            if overlay is not None:
                screen.blit(overlay, rect.topleft)

    def cloud_shadow_surface(
        self, width: int, height: int, seed: bytes, cloud_cover: int,
        wind_dx: int, wind_dy: int, world_left: int, world_top: int,
        tile_px: int, elapsed_ms: int,
    ):
        shadows, _ = self._clouds.layers(width, height, seed, cloud_cover,
                                        wind_dx, wind_dy, world_left, world_top,
                                        tile_px, elapsed_ms)
        return shadows

    def draw_cloud_shadows(self, screen, rect, seed: bytes, weather: dict, *,
                           world_left: int, world_top: int, tile_px: int,
                           elapsed_ms: int, game_minute=720, lighting=None) -> None:
        layers = self._clouds.layers(
            rect.width, rect.height, seed, int(weather.get('cloud_cover', 0)),
            int(weather.get('wind_dx', 0)), int(weather.get('wind_dy', 0)),
            world_left, world_top, tile_px, elapsed_ms,
            storm=int(weather.get('storm_intensity', 0)), minute=game_minute,
            daylight=getattr(lighting, 'daylight', 65535),
            sunrise=getattr(lighting, 'sunrise_minute', 360),
            sunset=getattr(lighting, 'sunset_minute', 1080))
        for layer in layers:
            if layer is not None:
                screen.blit(layer, rect.topleft)

    def draw_fog(self, screen, rect, weather: dict) -> None:
        frame = EffectFrame(b'',rect.width,rect.height,0,0,1,0,0,WeatherSample.capture(weather))
        for layer in self._fog_layers(frame):
            screen.blit(layer,rect.topleft)

    def lighting_colors(self, lighting):
        alpha = max(0, min(230, int(getattr(lighting, 'darkness_alpha', 0))))
        phase = str(getattr(lighting, 'phase', 'day'))
        warm = (0, 0, 0, 0)
        if phase in ('dawn', 'dusk'):
            warm = (lighting.tint_r, lighting.tint_g, lighting.tint_b,
                    min(62, max(12, alpha // 2)))
            dark = (18, 17, 20, alpha)
        else:
            dark = (*((5, 12, 28) if phase == 'night' else (15, 20, 26)), alpha)
        return warm + dark

    def lighting_sample(self, now):
        if self._lighting_target is None:
            return (0,) * 8
        t = max(0.0, min(1.0, (now - self._lighting_started) / 650.0))
        t = t * t * (3 - 2 * t)
        return tuple(round(a + (b - a) * t)
                     for a, b in zip(self._lighting_from, self._lighting_target))

    def set_lighting(self, lighting, now, *, reset=False):
        target = self.lighting_colors(lighting)
        if reset or self._lighting_target is None:
            self._lighting_from = self._lighting_target = target
            self._lighting_started = now - 650
        elif target != self._lighting_target:
            self._lighting_from = self.lighting_sample(now)
            self._lighting_target = target
            self._lighting_started = now

    def lighting_transition_active(self, now):
        return self._lighting_target is not None and now < self._lighting_started + 650

    def draw_lighting(self, screen, rect, lighting, *, elapsed_ms=None) -> None:
        colors = (self.lighting_colors(lighting) if elapsed_ms is None
                  else self.lighting_sample(elapsed_ms))
        overlay = self.pg.Surface((rect.width, rect.height), self.pg.SRCALPHA)
        for offset in (0, 4):
            color = colors[offset:offset + 4]
            if color[3]:
                overlay.fill(color)
                screen.blit(overlay, rect.topleft)

    def _glow_surface(self, radius: int, strength: int):
        radius = max(8, int(radius))
        strength = max(0, min(100, int(strength)))
        key = (radius, strength)
        cached = self._glow_cache.get(key)
        if cached is not None:
            return cached
        pg = self.pg
        size = radius * 2
        surf = pg.Surface((size, size), pg.SRCALPHA)
        source = LightSource(radius, radius, radius, strength * Q // 100)
        for r in range(radius, 2, -3):
            alpha = source_strength(source, radius + r, radius) * 95 // Q
            # Additive blits ignore source alpha for RGB: encode strength in
            # the color channels too, so a zero-strength edge stays black.
            pg.draw.circle(surf, (alpha, 181 * alpha // 255, 100 * alpha // 255, 0), (radius, radius), r)
        # Intensity uses the same finite falloff and radius as recognition.
        # This warm tint is presentation only, not a second visibility field.
        if len(self._glow_cache) >= 64:
            self._glow_cache.clear()
        self._glow_cache[key] = surf
        return surf

    def draw_fire_glows(self, screen, map_rect, fire_rects, lighting) -> None:
        if str(getattr(lighting, "phase", "day")) == "day" and int(getattr(lighting, "darkness_alpha", 0)) < 35:
            return
        for rect, intensity in fire_rects:
            radius = rect.width * MAX_FIRE_RADIUS
            glow = self._glow_surface(radius, intensity)
            x = rect.centerx - glow.get_width() // 2
            y = rect.centery - glow.get_height() // 2
            saved = screen.get_clip()
            screen.set_clip(map_rect)
            screen.blit(glow, (x, y), special_flags=self.pg.BLEND_RGBA_ADD)
            screen.set_clip(saved)

    def rain_surface(
        self,
        width: int,
        height: int,
        seed: bytes,
        phase: int,
        rain: int,
        wind_dx: int,
        wind_dy: int,
        night: bool = False,
    ):
        rain = max(0, min(10, int(rain)))
        if rain <= 0:
            return None
        # Phase is an unwrapped 33 ms presentation tick. Particle identities do
        # not depend on phase: each drop travels to a fixed impact point.
        key = (width, height, int(phase), rain, wind_dx, wind_dy, bool(night), bytes(seed))
        cached = self._rain_cache.get(key)
        if cached is not None:
            return cached
        pg = self.pg
        surf = pg.Surface((width, height), pg.SRCALPHA)
        count = max(12, min(900, round((18 + rain * 18) * width * height / (960 * 600))))
        slant = max(-0.65, min(0.65, wind_dx / 1600.0))
        particle_key=(bytes(seed),width,height,count)
        particles=self._rain_particles.get(particle_key)
        if particles is None:
            particles=[]
            for i in range(count):
                token=hash_u64(seed,"weather-art:rain",i)
                fall_ticks=18+int((token>>44)%17)
                particles.append((int(token%max(1,width)),int((token>>17)%max(1,height)),
                                  0.55+((token>>34)%100)/150.0,fall_ticks,
                                  int((token>>50)%(fall_ticks+9))))
            if len(self._rain_particles)>=4:self._rain_particles.clear()
            self._rain_particles[particle_key]=tuple(particles)
        for x,y,depth,fall_ticks,offset in particles:
            cycle = fall_ticks + 9
            age = (int(phase) + offset) % cycle
            if age < fall_ticks:
                distance = (fall_ticks - age) * (7 + rain * 0.45) * depth
                length = (5 + rain * 0.8) * depth
                head = (x - slant * distance, y - distance)
                tail = (head[0] - slant * length, head[1] - length)
                alpha = round((100 if night else 82) * depth)
                pg.draw.aaline(surf, (154, 180, 205, alpha), tail, head)
            else:
                # A short expanding ring fades at the same point the drop hit.
                age -= fall_ticks
                radius = 1 + age * 0.55 * depth
                alpha = round(100 * (1 - age / 9) * depth)
                pg.draw.ellipse(surf, (184, 204, 216, alpha),
                                (x-radius, y-radius/3, radius*2+1, radius*2/3+1), 1)
        # Keep only two full-size frames instead of retaining dozens of screens.
        if len(self._rain_cache) >= 2:
            self._rain_cache.pop(next(iter(self._rain_cache)))
        self._rain_cache[key] = surf
        return surf
