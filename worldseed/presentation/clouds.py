"""Textured cloud canopy and its projected shadow, with no world access.

Both layers use the same density texture and world-space cloud identities.
Weather controls coverage, optical thickness and wind; game-time lighting
controls shadow strength/direction. Wall time moves only the visual field.
"""
from collections import OrderedDict
from math import cos, floor, pi

from worldseed.core.rng import hash_u64
from worldseed.presentation.visuals import VisualRegistry
from worldseed.presentation.atmosphere import EffectFrame, WeatherSample, FieldEmitter


class CloudRenderer:
    def __init__(self, pg):
        self.pg = pg
        self._source = None
        self._density = None
        self._stamps = OrderedDict()
        self._shapes = OrderedDict()
        self.emitters = (FieldEmitter("weather-art:cloud-low",24),
                         FieldEmitter("weather-art:cloud-high",40,drift_scale=1.13,lifetime_ms=480000))
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

    def _shape(self, identity, family):
        """Compose a unique silhouette, then derive its matching optical density."""
        key = (identity, family)
        if key in self._shapes:
            self._shapes.move_to_end(key)
            return self._shapes[key]
        self._load()
        pg = self.pg
        cloud = pg.Surface((192,192),pg.SRCALPHA)
        # Pieces are irregular authored texture, not circular primitives. Their
        # independent placement/rotation/aspect creates combinatorial outlines.
        pieces = 3 + identity % 5
        for i in range(pieces):
            token = hash_u64(identity.to_bytes(8,'little'),'weather-art:cloud-piece',i)
            w = 62 + token%63
            h = (28 + (token>>8)%36) if family == 'wisp' else 58 + (token>>8)%64
            rotated = pg.transform.rotate(self._source, (token>>16)%360)
            piece = pg.transform.smoothscale(rotated,(w,h))
            x = 12 + (token>>25)%max(1,168-w)
            y = (72 + (token>>33)%26) if family == 'wisp' else 12+(token>>33)%max(1,168-h)
            piece.set_alpha(150 + (token>>42)%106)
            cloud.blit(piece,(x,y))
        # The composited alpha is the optical-density field. Preserve it
        # exactly for the shadow; native blends avoid a Python pixel loop for
        # every newly encountered particle.
        density = cloud.copy()
        density.fill((0,0,0,255),special_flags=pg.BLEND_RGBA_MULT)
        density.fill((8,14,23,0),special_flags=pg.BLEND_RGBA_ADD)
        while len(self._shapes) >= 48:
            self._shapes.popitem(last=False)
        self._shapes[key] = cloud,density
        return cloud,density

    def _stamp(self, width, height, identity, family):
        key = (width, height, identity, family)
        if key in self._stamps:
            self._stamps.move_to_end(key)
            return self._stamps[key]
        pg = self.pg
        source,density = self._shape(identity,family)
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
        if tile_px >= 40 and tile_px % 2 == 0:
            # Clouds have soft detail: render a half-resolution field at close
            # zoom, then upscale once. This avoids huge per-cloud stamps and
            # cache churn while preserving their world-space footprint.
            lw,lh = (width+1)//2,(height+1)//2
            low = self.layers(lw,lh,seed,cover,wind_dx,wind_dy,left,top,tile_px/2,
                              elapsed_ms,storm=storm,minute=minute,daylight=daylight,
                              sunrise=sunrise,sunset=sunset)
            return tuple(self.pg.transform.smoothscale(layer,(lw*2,lh*2)).subsurface(
                (0,0,width,height)).copy() for layer in low)
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
        frame = EffectFrame(bytes(seed),width,height,left,top,tile_px,phase*33,minute,
                            WeatherSample(cloud_cover=cover,storm_intensity=storm,
                                          wind_dx=wind_dx,wind_dy=wind_dy))
        for layer, emitter in enumerate(self.emitters):
            for particle in emitter.particles(frame):
                token = particle.identity
                density = max(0,min(1,(cover-token%85)/18)) * particle.opacity
                if density == 0:
                    continue
                # Wisps, small puffs and larger banks share one material but
                # have independently assembled outlines and different extents.
                family = 'wisp' if layer and token%3==0 else 'bank'
                size = 10 + (token>>24)%27 + layer*5
                w = size*tile_px
                h = (7+(token>>32)%19+layer*3)*tile_px
                cx = floor((particle.x-left)*tile_px)
                cy = floor((particle.y-top)*tile_px)
                x,y = cx-w//2,cy-h//2
                if x > width+abs(offset_x) or y > height+abs(offset_y) or x+w < -abs(offset_x) or y+h < -abs(offset_y):
                    continue
                cloud,shadow = self._stamp(w,h,token,family)
                shadow.set_alpha(round(density*illumination*(42+storm*.25)/(1+layer*.35)))
                shadows.blit(shadow,(x+offset_x,y+offset_y))
                cloud.set_alpha(round(density*(10+cover*.10+storm*.08)*(0.25+illumination*.75)/(1+layer*.6)))
                clouds.blit(cloud,(x,y))
        while len(self.frames) >= 2:
            self.frames.popitem(last=False)
        self.frames[key] = shadows, clouds
        return shadows, clouds
