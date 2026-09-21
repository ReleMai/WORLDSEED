"""Procedural weather/night art for the pygame local renderer.

These are presentation assets generated from deterministic WORLDSEED state:
wet-ground texture, soft projected cloud shadows, animated rain streak/splash
frames, fog haze, night/dawn/dusk grading, and local fire glow. No simulation
state is created or mutated here.
"""
from __future__ import annotations

from worldseed.core.rng import hash_u64


class WeatherFxRenderer:
    def __init__(self, pygame_module) -> None:
        self.pg = pygame_module
        self._wet_cache = {}
        self._cloud_cache = {}
        self._rain_cache = {}
        self._glow_cache = {}

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
        self,
        width: int,
        height: int,
        seed: bytes,
        minute: int,
        cloud_cover: int,
        wind_dx: int,
        wind_dy: int,
    ):
        cover = max(0, min(100, int(cloud_cover)))
        if cover < 12:
            return None
        # Game-time phase makes projected shadows advance when simulation time
        # advances. The low-resolution mask is smoothed on upscale.
        phase = max(0, int(minute)) // 12
        key = (int(width), int(height), phase, cover // 10, int(wind_dx) // 256, int(wind_dy) // 256, bytes(seed))
        cached = self._cloud_cache.get(key)
        if cached is not None:
            return cached

        pg = self.pg
        scale = 4
        lw, lh = max(8, width // scale), max(8, height // scale)
        low = pg.Surface((lw, lh), pg.SRCALPHA)
        count = 3 + cover // 12
        drift_x = (wind_dx * (phase % 64)) // 1536
        drift_y = (wind_dy * (phase % 64)) // 1536
        alpha = 9 + cover // 5
        for i in range(count):
            token = hash_u64(seed, "weather-art:cloud", phase // 8, i)
            cx = int(token % max(1, lw + 60)) - 30 + drift_x // scale
            cy = int((token >> 13) % max(1, lh + 50)) - 25 + drift_y // scale
            rw = 16 + int((token >> 27) % 34)
            rh = 9 + int((token >> 39) % 22)
            # Layered ellipses create feathered, irregular cloud footprints.
            for ring in range(4, 0, -1):
                grow = ring * 3
                a = max(2, alpha // (ring + 1))
                rect = pg.Rect(cx - rw // 2 - grow, cy - rh // 2 - grow, rw + grow * 2, rh + grow * 2)
                pg.draw.ellipse(low, (8, 13, 18, a), rect)
            lobe = pg.Rect(cx - rw // 3, cy - rh // 2, rw, rh)
            pg.draw.ellipse(low, (7, 11, 16, alpha), lobe)

        surface = pg.transform.smoothscale(low, (width, height))
        if len(self._cloud_cache) > 48:
            self._cloud_cache.clear()
        self._cloud_cache[key] = surface
        return surface

    def draw_cloud_shadows(self, screen, rect, seed: bytes, minute: int, weather: dict) -> None:
        surf = self.cloud_shadow_surface(
            rect.width, rect.height, seed, minute,
            int(weather.get("cloud_cover", 0)),
            int(weather.get("wind_dx", 0)),
            int(weather.get("wind_dy", 0)),
        )
        if surf is not None:
            screen.blit(surf, rect.topleft)

    def draw_fog(self, screen, rect, weather: dict) -> None:
        fog = max(0, min(100, int(weather.get("fog", 0))))
        if fog <= 4:
            return
        overlay = self.pg.Surface((rect.width, rect.height), self.pg.SRCALPHA)
        overlay.fill((172, 184, 184, min(82, 8 + fog // 2)))
        screen.blit(overlay, rect.topleft)

    def draw_lighting(self, screen, rect, lighting) -> None:
        alpha = max(0, min(230, int(getattr(lighting, "darkness_alpha", 0))))
        if alpha <= 0:
            return
        phase = str(getattr(lighting, "phase", "day"))
        if phase == "dawn":
            color = (41, 25, 42, alpha)
        elif phase == "dusk":
            color = (43, 23, 48, alpha)
        elif phase == "night":
            color = (5, 12, 28, alpha)
        else:
            color = (15, 20, 26, alpha)
        overlay = self.pg.Surface((rect.width, rect.height), self.pg.SRCALPHA)
        overlay.fill(color)
        screen.blit(overlay, rect.topleft)

    def _glow_surface(self, radius: int, strength: int):
        radius = max(8, int(radius))
        band = max(1, min(5, int(strength) // 20 + 1))
        key = (radius, band)
        cached = self._glow_cache.get(key)
        if cached is not None:
            return cached
        pg = self.pg
        size = radius * 2
        surf = pg.Surface((size, size), pg.SRCALPHA)
        for r in range(radius, 2, -3):
            t = 1.0 - r / max(1, radius)
            alpha = int((4 + band * 4) * (t + 0.15))
            pg.draw.circle(surf, (255, 143, 52, max(0, min(36, alpha))), (radius, radius), r)
        self._glow_cache[key] = surf
        return surf

    def draw_fire_glows(self, screen, map_rect, fire_rects, lighting) -> None:
        if str(getattr(lighting, "phase", "day")) == "day" and int(getattr(lighting, "darkness_alpha", 0)) < 35:
            return
        for rect, intensity in fire_rects:
            radius = max(rect.width * 2, int(rect.width * (2.0 + max(0, intensity) / 85.0)))
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
        key = (int(width), int(height), int(phase) & 15, rain, int(wind_dx) // 256, int(wind_dy) // 256, bool(night), bytes(seed))
        cached = self._rain_cache.get(key)
        if cached is not None:
            return cached

        pg = self.pg
        surf = pg.Surface((width, height), pg.SRCALPHA)
        count = 18 + rain * 18
        slant = max(-8, min(8, int(wind_dx) // 128))
        drop_len = 4 + rain
        bright = (154, 180, 205, 125 if night else 105)
        for i in range(count):
            token = hash_u64(seed, "weather-art:rain", int(phase), i)
            x = int(token % max(1, width + 24)) - 12
            y = int((token >> 17) % max(1, height + 32)) - 16
            speed_offset = ((phase * (5 + rain)) + i * 3) % max(1, height + 32)
            y = (y + speed_offset) % max(1, height + 16) - 8
            pg.draw.aaline(surf, bright, (x, y), (x + slant, y + drop_len))

        # Animated ground splashes make rain contact the terrain instead of
        # reading as a screen-only post-process.
        splash_count = 2 + rain * 2
        for i in range(splash_count):
            token = hash_u64(seed, "weather-art:splash", int(phase), i)
            x = int(token % max(1, width))
            y = int((token >> 21) % max(1, height))
            rw = 2 + int((token >> 37) % 4)
            pg.draw.arc(surf, (184, 204, 216, 90), (x-rw, y-1, rw*2, 4), 0.2, 2.95, 1)

        if len(self._rain_cache) > 96:
            self._rain_cache.clear()
        self._rain_cache[key] = surf
        return surf
