"""Textured cloud canopy and its projected shadow, with no world access.

Both layers use the same density texture and world-space cloud identities.
Weather controls coverage, optical thickness and wind; game-time lighting
controls shadow strength/direction. Wall time moves only the visual field.
"""
from collections import OrderedDict
from math import cos, floor, pi

from worldseed.core.rng import hash_u64
from worldseed.presentation.visuals import VisualRegistry


class CloudRenderer:
    def __init__(self, pg):
        self.pg = pg
        self._source = None
        self._density = None
        self._stamps = OrderedDict()
        self._stamp_bytes = 0
        self.frames = OrderedDict()

    def _load(self):
        if self._source is not None:
            return
        pg = self.pg
        path = VisualRegistry.load_default().special('cloud_bank')
        source = pg.image.load(str(path)).convert_alpha()
        self._source = pg.transform.smoothscale(source, (192, 192))
        # Bright billows are denser than shaded/translucent wisps. Sharing this
        # field gives visible cloud detail a corresponding penumbra on terrain.
        self._density = pg.Surface((192, 192), pg.SRCALPHA)
        for y in range(192):
            for x in range(192):
                r, g, b, alpha = self._source.get_at((x, y))
                density = round(alpha * (0.25 + 0.75 * (r+g+b) / 765))
                self._density.set_at((x, y), (8, 14, 23, density))

    def _stamp(self, width, height, orientation):
        key = (width, height, orientation)
        if key in self._stamps:
            self._stamps.move_to_end(key)
            return self._stamps[key]
        self._load()
        pg = self.pg
        source = pg.transform.rotate(self._source, orientation * 90)
        density = pg.transform.rotate(self._density, orientation * 90)
        cloud = pg.transform.smoothscale(source, (width, height))
        # Low-resolution projection softens density detail rather than drawing
        # concentric outlines. The resulting shadow has no ellipse primitives.
        small = pg.transform.smoothscale(density, (max(8, width//12), max(8, height//12)))
        shadow = pg.transform.smoothscale(small, (width, height))
        size = width * height * 8
        while self._stamps and self._stamp_bytes + size > 64 * 1024 * 1024:
            _, old = self._stamps.popitem(last=False)
            self._stamp_bytes -= old[0].get_width() * old[0].get_height() * 8
        if size <= 64 * 1024 * 1024:
            self._stamps[key] = (cloud, shadow)
            self._stamp_bytes += size
        return cloud, shadow

    def layers(self, width, height, seed, cover, wind_dx, wind_dy,
               left, top, tile_px, elapsed_ms, *, storm=0, minute=720,
               daylight=65535, sunrise=360, sunset=1080):
        cover = max(0, min(100, int(cover)))
        if cover < 12:
            return None, None
        storm = max(0, min(100, int(storm)))
        phase = max(0, int(elapsed_ms)) // 33
        tile_px = max(1, int(tile_px))
        key = (width, height, bytes(seed), cover, wind_dx, wind_dy, left, top,
               tile_px, phase, storm, minute, daylight, sunrise, sunset)
        if key in self.frames:
            return self.frames[key]
        pg = self.pg
        shadows = pg.Surface((width, height), pg.SRCALPHA)
        clouds = pg.Surface((width, height), pg.SRCALPHA)
        progress = max(0, min(1, (minute % 1440 - sunrise) / max(1, sunset-sunrise)))
        sun_height = max(0.15, 1 - abs(progress * 2 - 1))
        offset_x = round(-cos(progress*pi) * tile_px * (2 + 3*(1-sun_height)))
        offset_y = round(tile_px * (0.5 + 1-sun_height))
        illumination = max(0, min(1, daylight / 65535))
        drift_x = wind_dx * phase * 33 / 4680000
        drift_y = wind_dy * phase * 33 / 4680000
        # Two overlapping scales break up repeated silhouettes into banks.
        for layer, spacing in enumerate((30, 46)):
            parallax = 1 + layer * 0.13
            dx, dy = drift_x * parallax, drift_y * parallax
            gx0 = floor((left-dx-55)/spacing)
            gx1 = floor((left+width/tile_px-dx+55)/spacing)
            gy0 = floor((top-dy-55)/spacing)
            gy1 = floor((top+height/tile_px-dy+55)/spacing)
            for gy in range(gy0, gy1+1):
                for gx in range(gx0, gx1+1):
                    token = hash_u64(seed, 'weather-art:textured-cloud', layer, gx, gy)
                    density = max(0, min(1, (cover - token%85) / 18))
                    if density == 0:
                        continue
                    cx = floor((gx*spacing + ((token>>8)%17) + dx-left)*tile_px)
                    cy = floor((gy*spacing + ((token>>16)%17) + dy-top)*tile_px)
                    w = (22 + (token>>24)%13 + layer*9)*tile_px
                    h = (15 + (token>>32)%10 + layer*6)*tile_px
                    x, y = cx-w//2, cy-h//2
                    if x > width+abs(offset_x) or y > height+abs(offset_y) or x+w < -abs(offset_x) or y+h < -abs(offset_y):
                        continue
                    cloud, shadow = self._stamp(w, h, (token>>40)%4)
                    shadow.set_alpha(round(density * illumination * (42 + storm*.25) / (1+layer*.35)))
                    shadows.blit(shadow, (x+offset_x, y+offset_y))
                    # A translucent overhead canopy preserves terrain legibility.
                    cloud.set_alpha(round(density * (10 + cover*.10 + storm*.08) * (0.25+illumination*.75) / (1+layer*.6)))
                    clouds.blit(cloud, (x, y))
        while len(self.frames) >= 2:
            self.frames.popitem(last=False)
        self.frames[key] = shadows, clouds
        return shadows, clouds
