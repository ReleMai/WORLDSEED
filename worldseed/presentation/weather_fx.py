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
        self, width: int, height: int, seed: bytes, cloud_cover: int,
        wind_dx: int, wind_dy: int, world_left: int, world_top: int,
        tile_px: int, elapsed_ms: int,
    ):
        """World-anchored moving cloud-shadow field."""
        cover=max(0,min(100,int(cloud_cover)))
        if cover<12:return None
        pg=self.pg;tile_px=max(1,int(tile_px));phase=max(0,int(elapsed_ms))//180
        key=(int(width),int(height),int(world_left),int(world_top),tile_px,phase,cover//10,int(wind_dx)//256,int(wind_dy)//256,bytes(seed))
        cached=self._cloud_cache.get(key)
        if cached is not None:return cached
        surf=pg.Surface((width,height),pg.SRCALPHA)
        cell_w,cell_h=36,28
        drift_tiles_x=(int(wind_dx)*phase)//26000;drift_tiles_y=(int(wind_dy)*phase)//26000
        min_x=world_left-drift_tiles_x-48;max_x=world_left+width//tile_px-drift_tiles_x+48
        min_y=world_top-drift_tiles_y-36;max_y=world_top+height//tile_px-drift_tiles_y+36
        gx0,gx1=min_x//cell_w,max_x//cell_w;gy0,gy1=min_y//cell_h,max_y//cell_h
        alpha=10+cover//6
        for gy in range(gy0,gy1+1):
            for gx in range(gx0,gx1+1):
                token=hash_u64(seed,'weather-art:cloud-field',gx,gy)
                if int(token%100)>=cover:continue
                wx=gx*cell_w+6+int((token>>9)%max(1,cell_w-12))+drift_tiles_x
                wy=gy*cell_h+5+int((token>>21)%max(1,cell_h-10))+drift_tiles_y
                cx=(wx-world_left)*tile_px;cy=(wy-world_top)*tile_px
                base_w=(18+int((token>>33)%20))*tile_px;base_h=(8+int((token>>45)%11))*tile_px
                lobes=4+int((token>>55)%4)
                body=pg.Rect(cx-base_w//2,cy-base_h//2,base_w,base_h)
                pg.draw.ellipse(surf,(7,11,16,max(3,alpha//3)),body.inflate(tile_px*3,tile_px*2))
                for i in range(lobes):
                    lt=hash_u64(seed,'weather-art:cloud-lobe',gx,gy,i)
                    ox=(int(lt%1000)-500)*base_w//1800;oy=(int((lt>>12)%1000)-500)*base_h//2200
                    rw=max(tile_px*5,base_w*(34+int((lt>>24)%36))//100)
                    rh=max(tile_px*3,base_h*(42+int((lt>>36)%34))//100)
                    rect=pg.Rect(cx+ox-rw//2,cy+oy-rh//2,rw,rh)
                    for grow,a_div in ((tile_px*2,4),(tile_px,3),(0,1)):
                        rr=rect.inflate(grow,grow);pg.draw.ellipse(surf,(6,10,15,max(2,alpha//a_div)),rr)
        if len(self._cloud_cache)>64:self._cloud_cache.clear()
        self._cloud_cache[key]=surf;return surf

    def draw_cloud_shadows(self, screen, rect, seed: bytes, weather: dict, *, world_left: int, world_top: int, tile_px: int, elapsed_ms: int) -> None:
        surf=self.cloud_shadow_surface(rect.width,rect.height,seed,int(weather.get('cloud_cover',0)),int(weather.get('wind_dx',0)),int(weather.get('wind_dy',0)),world_left,world_top,tile_px,elapsed_ms)
        if surf is not None:screen.blit(surf,rect.topleft)
    def draw_fog(self, screen, rect, weather: dict) -> None:
        fog = max(0, min(100, int(weather.get("fog", 0))))
        if fog <= 4:
            return
        overlay = self.pg.Surface((rect.width, rect.height), self.pg.SRCALPHA)
        overlay.fill((172, 184, 184, min(82, 8 + fog // 2)))
        screen.blit(overlay, rect.topleft)

    def draw_lighting(self, screen, rect, lighting) -> None:
        alpha=max(0,min(230,int(getattr(lighting,'darkness_alpha',0))))
        if alpha<=0:return
        phase=str(getattr(lighting,'phase','day'))
        tr=int(getattr(lighting,'tint_r',255));tg=int(getattr(lighting,'tint_g',255));tb=int(getattr(lighting,'tint_b',255))
        if phase in ('dawn','dusk'):
            warm=self.pg.Surface((rect.width,rect.height),self.pg.SRCALPHA)
            warm.fill((tr,tg,tb,min(62,max(12,alpha//2))))
            screen.blit(warm,rect.topleft);dark=(18,17,20,alpha)
        elif phase=='night':dark=(5,12,28,alpha)
        else:dark=(15,20,26,alpha)
        overlay=self.pg.Surface((rect.width,rect.height),self.pg.SRCALPHA)
        overlay.fill(dark);screen.blit(overlay,rect.topleft)

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
