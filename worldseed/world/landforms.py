"""WORLDGEN v8 geological landform prototype.

Phase 1 is deliberately non-authoritative. It produces deterministic geological
fields that can be audited beside frozen worldgen v1-v7 before any save starts
using v8 geography.

Broad landforms are primary and noise is secondary: continental swells establish
land/ocean tendency, deterministic orogeny segments create elongated mountain
systems, basin seeds create depressions, plateaus add broad uplift, and only then
is fine roughness applied.
"""
from __future__ import annotations

from dataclasses import dataclass

from worldseed.core.rng import hash_u64

Q = 65535
SEA_LEVEL_REFERENCE = 23800
TECTONIC_CELL = 1536
BASIN_CELL = 2048
LANDFORM_VERSION = 1
LANDFORM_ALGORITHM = "worldgen-v8-landforms-prototype-v1"

# Integer direction vectors avoid trigonometry in the generation contract.
_DIRECTIONS = (
    (1024, 0), (946, 392), (724, 724), (392, 946),
    (0, 1024), (-392, 946), (-724, 724), (-946, 392),
    (-1024, 0), (-946, -392), (-724, -724), (-392, -946),
    (0, -1024), (392, -946), (724, -724), (946, -392),
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


def _radial_strength(px: int, py: int, cx: int, cy: int, radius: int) -> int:
    dx, dy = px - cx, py - cy
    rr = max(1, int(radius)) ** 2
    d2 = dx * dx + dy * dy
    if d2 >= rr:
        return 0
    return _smooth_q((rr - d2) * Q // rr)


def _segment_strength(
    px: int, py: int, ax: int, ay: int, bx: int, by: int, width: int
) -> int:
    """Return 0..Q influence for a finite thick line, integer-only."""
    vx, vy = bx - ax, by - ay
    wx, wy = px - ax, py - ay
    vv = vx * vx + vy * vy
    rr = max(1, int(width)) ** 2
    if vv <= 0:
        return _radial_strength(px, py, ax, ay, width)

    dot = wx * vx + wy * vy
    if dot <= 0:
        d2 = wx * wx + wy * wy
        if d2 >= rr:
            return 0
        return _smooth_q((rr - d2) * Q // rr)
    if dot >= vv:
        dx, dy = px - bx, py - by
        d2 = dx * dx + dy * dy
        if d2 >= rr:
            return 0
        return _smooth_q((rr - d2) * Q // rr)

    cross = wx * vy - wy * vx
    cross2 = cross * cross
    limit = rr * vv
    if cross2 >= limit:
        return 0
    return _smooth_q((limit - cross2) * Q // limit)


@dataclass(frozen=True, slots=True)
class LandformFields:
    continentalness: int
    tectonic_uplift: int
    mountain_chain: int
    basin: int
    plateau: int
    roughness: int
    elevation: int
    province: str
    algorithm: str = LANDFORM_ALGORITHM

    @property
    def ocean(self) -> bool:
        return self.elevation < SEA_LEVEL_REFERENCE


class LandformSampler:
    """Stateless WORLDGEN v8 geological field sampler with a bounded lattice cache."""

    def __init__(self, world_seed: bytes) -> None:
        self.seed = bytes(world_seed)
        self._lattice_cache: dict[tuple[str, int, int], int] = {}

    def _lattice_value(self, namespace: str, ix: int, iy: int) -> int:
        key = (namespace, int(ix), int(iy))
        cached = self._lattice_cache.get(key)
        if cached is not None:
            return cached
        value = hash_u64(self.seed, namespace, LANDFORM_VERSION, key[1], key[2]) & 0xFFFF
        if len(self._lattice_cache) >= 32768:
            self._lattice_cache.clear()
        self._lattice_cache[key] = value
        return value

    def _value_noise(self, namespace: str, x: int, y: int, period: int) -> int:
        period = max(1, int(period))
        ix, iy = int(x) // period, int(y) // period
        rx, ry = int(x) % period, int(y) % period
        tx = _smooth_q(rx * Q // period)
        ty = _smooth_q(ry * Q // period)
        a = _lerp_q(self._lattice_value(namespace, ix, iy), self._lattice_value(namespace, ix + 1, iy), tx)
        b = _lerp_q(self._lattice_value(namespace, ix, iy + 1), self._lattice_value(namespace, ix + 1, iy + 1), tx)
        return _lerp_q(a, b, ty)

    def _orogeny(self, x: int, y: int) -> int:
        cell = TECTONIC_CELL
        cx, cy = x // cell, y // cell
        best = 0
        # Neighboring cells are checked because a range may cross its owner's
        # tectonic-cell boundary. This remains continuous for negative coords.
        for gy in range(cy - 1, cy + 2):
            for gx in range(cx - 1, cx + 2):
                token = hash_u64(self.seed, "v8:orogeny-active", LANDFORM_VERSION, gx, gy)
                if token % 100 >= 38:
                    continue
                jx = int(hash_u64(self.seed, "v8:orogeny-x", LANDFORM_VERSION, gx, gy) % (cell // 2)) - cell // 4
                jy = int(hash_u64(self.seed, "v8:orogeny-y", LANDFORM_VERSION, gx, gy) % (cell // 2)) - cell // 4
                mx = gx * cell + cell // 2 + jx
                my = gy * cell + cell // 2 + jy
                direction = _DIRECTIONS[
                    hash_u64(self.seed, "v8:orogeny-dir", LANDFORM_VERSION, gx, gy) % len(_DIRECTIONS)
                ]
                half_len = 520 + int(hash_u64(self.seed, "v8:orogeny-len", LANDFORM_VERSION, gx, gy) % 460)
                ax = mx - direction[0] * half_len // 1024
                ay = my - direction[1] * half_len // 1024
                bx = mx + direction[0] * half_len // 1024
                by = my + direction[1] * half_len // 1024
                width = 150 + int(hash_u64(self.seed, "v8:orogeny-width", LANDFORM_VERSION, gx, gy) % 260)
                strength = _segment_strength(x, y, ax, ay, bx, by, width)
                amplitude = 36000 + int(
                    hash_u64(self.seed, "v8:orogeny-amp", LANDFORM_VERSION, gx, gy) % 29536
                )
                best = max(best, strength * amplitude // Q)
        return _clamp_q(best)

    def _basin(self, x: int, y: int) -> int:
        cell = BASIN_CELL
        cx, cy = x // cell, y // cell
        best = 0
        for gy in range(cy - 1, cy + 2):
            for gx in range(cx - 1, cx + 2):
                if hash_u64(self.seed, "v8:basin-active", LANDFORM_VERSION, gx, gy) % 100 >= 30:
                    continue
                jx = int(hash_u64(self.seed, "v8:basin-x", LANDFORM_VERSION, gx, gy) % cell) - cell // 2
                jy = int(hash_u64(self.seed, "v8:basin-y", LANDFORM_VERSION, gx, gy) % cell) - cell // 2
                bx = gx * cell + cell // 2 + jx
                by = gy * cell + cell // 2 + jy
                radius = 420 + int(hash_u64(self.seed, "v8:basin-radius", LANDFORM_VERSION, gx, gy) % 780)
                strength = _radial_strength(x, y, bx, by, radius)
                amplitude = 30000 + int(
                    hash_u64(self.seed, "v8:basin-amp", LANDFORM_VERSION, gx, gy) % 35536
                )
                best = max(best, strength * amplitude // Q)
        return _clamp_q(best)

    def sample(self, x: int, y: int) -> LandformFields:
        x, y = int(x), int(y)
        continental = (
            self._value_noise("v8:continental:macro", x, y, 4096) * 7
            + self._value_noise("v8:continental:meso", x + 8113, y - 2909, 1536) * 3
        ) // 10

        mountain = self._orogeny(x, y)
        broad_uplift = self._value_noise("v8:uplift", x - 19001, y + 7001, 2048)
        tectonic = _clamp_q(mountain * 4 // 5 + max(0, broad_uplift - 36000) * 2)

        basin = self._basin(x, y)
        plateau_raw = self._value_noise("v8:plateau", x + 44021, y + 17011, 1792)
        plateau = _clamp_q(max(0, plateau_raw - 38500) * 5 // 2)

        rough_raw = (
            self._value_noise("v8:rough:meso", x - 701, y + 503, 256) * 2
            + self._value_noise("v8:rough:local", x + 97, y - 193, 72)
        ) // 3
        roughness = _clamp_q(abs(rough_raw - Q // 2) * 2)

        # Keep the established 0..65535 elevation scale so hydrology and audit
        # code can compare the prototype beside v7 before v8 promotion.
        elevation = 12000 + continental * 30000 // Q
        elevation += tectonic * 22000 // Q
        elevation += plateau * 7000 // Q
        elevation -= basin * 9000 // Q
        elevation += (rough_raw - Q // 2) * 3200 // (Q // 2)
        elevation = _clamp_q(elevation)

        if elevation < SEA_LEVEL_REFERENCE:
            province = "oceanic_plain"
        elif mountain >= 36000 and tectonic >= 38000:
            province = "mountain_chain"
        elif plateau >= 36000:
            province = "plateau"
        elif basin >= 38000:
            province = "basin"
        elif tectonic >= 26000:
            province = "upland"
        else:
            province = "lowland"

        return LandformFields(
            _clamp_q(continental),
            tectonic,
            mountain,
            basin,
            plateau,
            roughness,
            elevation,
            province,
        )
