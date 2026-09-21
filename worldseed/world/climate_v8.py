"""WORLDGEN v8 physical climate circulation.

Climate is derived from v8 geography rather than an unrelated moisture/temperature
noise sheet. Broad climate bands establish solar potential, continentalness and
near-sea relief shape maritime moderation, prevailing winds advect moisture, and
terrain sampled along the upwind axis creates orographic lift and rain shadows.

The sampler works on a broad cached lattice and interpolates between nodes, so
terrain generation can query it per cell without introducing chunk seams or a
large per-tile cost.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from worldseed.core.rng import hash_u64
from worldseed.world.landforms import Q, SEA_LEVEL_REFERENCE

CLIMATE_VERSION = 1
CLIMATE_ALGORITHM = "worldgen-v8-climate-circulation-v1"
CLIMATE_NODE = 96
CLIMATE_BELT_PERIOD = 32768

_WIND_DIRECTIONS = (
    (1024, 128), (896, 384), (384, 896), (-384, 896),
    (-1024, 128), (-896, -384), (-384, -896), (384, -896),
)


def _clamp_q(value: int) -> int:
    return max(0, min(Q, int(value)))


def _smooth_q(value: int) -> int:
    value = _clamp_q(value)
    v2 = value * value // Q
    v3 = v2 * value // Q
    return _clamp_q(3 * v2 - 2 * v3)


def _lerp_q(a: int, b: int, t: int) -> int:
    return int(a) + (int(b) - int(a)) * int(t) // Q


@dataclass(frozen=True, slots=True)
class ClimateFields:
    mean_temperature: int
    precipitation_potential: int
    humidity: int
    maritime_influence: int
    continentality: int
    prevailing_wind_dx: int
    prevailing_wind_dy: int
    wind_strength: int
    orographic_lift: int
    rain_shadow: int
    latitude_heat: int
    algorithm: str = CLIMATE_ALGORITHM


class ClimateV8Sampler:
    """Cached broad-field climate solver over the immutable v8 landform model."""

    def __init__(self, world_seed: bytes, landforms, topography) -> None:
        self.seed = bytes(world_seed)
        self.landforms = landforms
        self.topography = topography

    def _latitude_heat(self, y: int) -> int:
        # WORLDSEED's surface is unbounded, so climate belts repeat at planetary
        # scale rather than introducing a hard north/south edge. Shift the cycle
        # so the origin is temperate instead of accidentally becoming a pole.
        phase = (int(y) + CLIMATE_BELT_PERIOD // 4) % CLIMATE_BELT_PERIOD
        distance = abs(phase - CLIMATE_BELT_PERIOD // 2)
        return _clamp_q(Q - distance * Q // (CLIMATE_BELT_PERIOD // 2))

    def _wind_vector(self, x: int, y: int, latitude_heat: int) -> tuple[int, int, int]:
        belt = ((int(y) + CLIMATE_BELT_PERIOD // 4) // 4096) & 7
        # Alternating easterly/westerly belts are perturbed only at a very broad
        # scale. This preserves coherent fronts instead of cell-scale wind noise.
        base = (0, 1, 2, 3, 4, 5, 6, 7)[belt]
        region_x = int(x) // 6144
        region_y = int(y) // 6144
        turn = int(hash_u64(self.seed, "v8:climate:wind-turn", CLIMATE_VERSION, region_x, region_y) % 3) - 1
        index = (base + turn) % len(_WIND_DIRECTIONS)
        dx, dy = _WIND_DIRECTIONS[index]
        thermal = 22000 + latitude_heat * 19000 // Q
        jitter = int(hash_u64(self.seed, "v8:climate:wind-strength", CLIMATE_VERSION, region_x, region_y) % 9000)
        return dx, dy, _clamp_q(thermal + jitter)

    @lru_cache(maxsize=32768)
    def _node(self, ix: int, iy: int) -> ClimateFields:
        x = int(ix) * CLIMATE_NODE
        y = int(iy) * CLIMATE_NODE
        land = self.landforms.sample(x, y)
        latitude_heat = self._latitude_heat(y)
        wind_dx, wind_dy, wind_strength = self._wind_vector(x, y, latitude_heat)

        # Continentalness and elevation relative to sea level together provide a
        # cheap, continuous proxy for ocean proximity. The near-sea term is high
        # on coastal plains and island margins while deep interiors stay dry.
        coast_band = max(0, Q - abs(int(land.elevation) - SEA_LEVEL_REFERENCE) * Q // 15000)
        oceanic = _clamp_q((36000 - int(land.continentalness)) * 2)
        maritime = _clamp_q(max(oceanic, coast_band * 4 // 5))
        continentality = _clamp_q(Q - maritime)

        # Sample terrain along the upwind axis. Rising ground enhances rainfall;
        # descending from a high upwind barrier produces a leeward rain shadow.
        ux = -1 if wind_dx < -256 else 1 if wind_dx > 256 else 0
        uy = -1 if wind_dy < -256 else 1 if wind_dy > 256 else 0
        if ux == 0 and uy == 0:
            ux = 1
        e0 = int(land.elevation)
        e1 = int(self.landforms.sample(x - ux * 288, y - uy * 288).elevation)
        e2 = int(self.landforms.sample(x - ux * 576, y - uy * 576).elevation)
        lift_raw = max(0, e0 - e1) + max(0, e1 - e2)
        shadow_raw = max(0, e1 - e0) + max(0, e2 - e0) // 2
        orographic_lift = _clamp_q(lift_raw * Q // 10500)
        rain_shadow = _clamp_q(shadow_raw * Q // 11500)

        # Broad humidity texture prevents every same-latitude coast from looking
        # identical while remaining subordinate to physical geography.
        humidity_noise = self.landforms._value_noise(
            "v8:climate:humidity", x + 17011, y - 9017, 2304
        )

        # Temperature starts with latitude, is moderated toward temperate values
        # by maritime influence, then cools with altitude. Local climate texture
        # is intentionally small compared with those physical drivers.
        temperature = 8500 + latitude_heat * 50000 // Q
        moderation_target = 34000
        moderation = maritime * 3 // 10
        temperature = (
            temperature * (Q - moderation) + moderation_target * moderation
        ) // Q
        altitude = max(0, e0 - SEA_LEVEL_REFERENCE)
        temperature -= altitude * 13 // 20
        temp_texture = self.landforms._value_noise(
            "v8:climate:temperature", x - 41003, y + 9237, 2048
        ) - Q // 2
        temperature += temp_texture * 3200 // (Q // 2)
        temperature = _clamp_q(temperature)

        precipitation = 8500
        precipitation += maritime * 23 // 40
        precipitation += humidity_noise * 7 // 25
        precipitation += orographic_lift * 19 // 50
        precipitation -= rain_shadow * 21 // 50
        # Warm belts can carry more moisture, but high continentality still wins.
        precipitation += latitude_heat * 2500 // Q
        precipitation -= continentality * 3500 // Q
        precipitation = _clamp_q(precipitation)

        humidity = _clamp_q(
            precipitation * 7 // 10 + maritime * 2 // 10 + humidity_noise // 10
        )
        return ClimateFields(
            temperature,
            precipitation,
            humidity,
            maritime,
            continentality,
            wind_dx,
            wind_dy,
            wind_strength,
            orographic_lift,
            rain_shadow,
            latitude_heat,
        )

    def sample(self, x: int, y: int) -> ClimateFields:
        x, y = int(x), int(y)
        ix, iy = x // CLIMATE_NODE, y // CLIMATE_NODE
        rx, ry = x % CLIMATE_NODE, y % CLIMATE_NODE
        tx = _smooth_q(rx * Q // CLIMATE_NODE)
        ty = _smooth_q(ry * Q // CLIMATE_NODE)
        n00 = self._node(ix, iy)
        n10 = self._node(ix + 1, iy)
        n01 = self._node(ix, iy + 1)
        n11 = self._node(ix + 1, iy + 1)

        def blend(name: str) -> int:
            a = _lerp_q(getattr(n00, name), getattr(n10, name), tx)
            b = _lerp_q(getattr(n01, name), getattr(n11, name), tx)
            return _lerp_q(a, b, ty)

        # Wind direction changes only at very broad belts; interpolate components
        # then clamp to the original fixed-vector range.
        wind_dx = max(-1024, min(1024, blend("prevailing_wind_dx")))
        wind_dy = max(-1024, min(1024, blend("prevailing_wind_dy")))
        return ClimateFields(
            _clamp_q(blend("mean_temperature")),
            _clamp_q(blend("precipitation_potential")),
            _clamp_q(blend("humidity")),
            _clamp_q(blend("maritime_influence")),
            _clamp_q(blend("continentality")),
            wind_dx,
            wind_dy,
            _clamp_q(blend("wind_strength")),
            _clamp_q(blend("orographic_lift")),
            _clamp_q(blend("rain_shadow")),
            _clamp_q(blend("latitude_heat")),
        )
