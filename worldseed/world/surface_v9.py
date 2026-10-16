"""WORLDGEN v9 continuous, terrain-aware terrestrial land cover.

The v8 geological height and physical climate remain the causes of geography.
This layer only classifies dry land after cave mouths and coastal materials have
been admitted by WorldGenerator; prepared river/floodplain projection still has
the final say. It never invents water, precipitation, collision or resources.

Broad domain-warped cover patches modulate habitat margins rather than rolling
one random biome per tile. All stencils use absolute coordinates, including
negative coordinates, and caches are bounded/rebuildable.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

Q = 65535
TOPOGRAPHY_NODE = 16
SURFACE_ALGORITHM = "worldgen-v9-physical-landcover-v1"


def _smooth(value: int) -> int:
    square = value * value // Q
    return max(0, min(Q, 3 * square - 2 * square * value // Q))


def _lerp(a: int, b: int, weight: int) -> int:
    return a + (b - a) * weight // Q


@dataclass(frozen=True, slots=True)
class LandcoverFields:
    terrain_id: str
    cover_patch: int
    woodland_suitability: int
    slope: int
    ridge_exposure: int
    valley_depth: int
    algorithm: str = SURFACE_ALGORITHM


class SurfaceV9Sampler:
    """Bounded projection of v8 physical fields into coherent land cover.

    Topography is interpolated from a 16-cell lattice: habitat responds to a
    hillside rather than paying thirteen geological samples for every tile.
    The exact v8 elevation, drainage and climate solvers are unchanged.
    """

    def __init__(self, value_noise, topography) -> None:
        self._noise = value_noise
        self._topography = topography
        # Per-world ownership: a class-wide method cache would retain old
        # samplers and their generators after the player leaves a world.
        self._topographic_node = lru_cache(maxsize=8192)(self._topographic_node)

    def _topographic_node(self, ix: int, iy: int) -> tuple[int, int, int]:
        t = self._topography.sample_xy(ix * TOPOGRAPHY_NODE, iy * TOPOGRAPHY_NODE)
        return t.slope, t.ridge_exposure, t.valley_depth

    def _terrain_context(self, x: int, y: int) -> tuple[int, int, int]:
        step = TOPOGRAPHY_NODE
        ix, iy = x // step, y // step
        tx, ty = _smooth(x % step * Q // step), _smooth(y % step * Q // step)
        a = self._topographic_node(ix, iy)
        b = self._topographic_node(ix + 1, iy)
        c = self._topographic_node(ix, iy + 1)
        d = self._topographic_node(ix + 1, iy + 1)
        return tuple(_lerp(_lerp(a[i], b[i], tx), _lerp(c[i], d[i], tx), ty)
                     for i in range(3))

    def _cover_patch(self, x: int, y: int) -> int:
        # Warping only cover texture avoids straight lattice-shaped margins;
        # it never moves geological elevation, rivers, coasts or climate.
        wx = x + (self._noise("v9:landcover:warp-x", x, y, 256) - Q // 2) * 64 // Q
        wy = y + (self._noise("v9:landcover:warp-y", x, y, 256) - Q // 2) * 64 // Q
        broad = self._noise("v9:landcover:groves", wx, wy, 80)
        local = self._noise("v9:landcover:clearings", wx, wy, 32)
        return (((broad * 3 + local) // 4) - Q // 2) * 9000 // Q

    def sample(self, x: int, y: int, fields) -> LandcoverFields:
        x, y = int(x), int(y)
        patch = self._cover_patch(x, y)
        slope, ridge, valley = self._terrain_context(x, y)
        e, moisture, temperature = fields.elevation, fields.moisture, fields.temperature

        # Water balance comes from physical v8 precipitation. These are small
        # habitat corrections for sheltered hollows and exposed/eroding slopes,
        # not another rainfall field. Fertility remains the v8 source value.
        shelter = min(2200, valley // 4)
        exposure = min(5500, ridge // 3 + max(0, slope - 10000) // 5)
        thermal_penalty = max(0, 19500 - temperature) + max(0, temperature - 53500)
        woodland = (moisture + (fields.fertility - 39000) // 4
                    + shelter - exposure - thermal_penalty + patch)

        terrain = "core:grass"
        if e > 52500:
            terrain = "core:rock"
        elif e > 45500 and slope + ridge // 2 > 23000 + patch:
            # Exposed mountain shoulders gain connected rocky outcrops, while
            # sheltered upland soil can still carry grass or woodland.
            terrain = "core:rock"
        elif temperature < 15000:
            terrain = "core:tundra"
        elif (temperature < 18500
              and (18500 - temperature) * 3 + ridge // 3 + patch > 8500):
            terrain = "core:tundra"
        elif (temperature > 33000 and moisture < 23500
              and 17500 - moisture + (temperature - 36000) // 5
              + exposure // 3 + patch // 2 > 0):
            terrain = "core:scrub"
        elif 15500 < temperature < 57500 and woodland > 39000:
            terrain = "core:forest"
        return LandcoverFields(terrain, patch, woodland, slope, ridge, valley)
