"""WORLDGEN v8 geological landform prototype.

Phase 1 remains deliberately non-authoritative. It produces deterministic
geological fields that can be audited beside frozen worldgen v1-v7 before any
save starts using v8 geography.

Large forms are primary and noise is secondary: continental swells establish
land/ocean tendency, regional tectonic stress aligns long mountain systems,
smaller branch ranges add complexity, structural valleys and basins lower the
surface, plateaus raise broad blocks, and fine roughness is applied last.
"""
from __future__ import annotations

from dataclasses import dataclass

from worldseed.core.rng import hash_u64

Q = 65535
SEA_LEVEL_REFERENCE = 23800
TECTONIC_CELL = 1536
MAJOR_RANGE_CELL = 4096
BASIN_CELL = 2048
VALLEY_CELL = 3072
LANDFORM_VERSION = 2
LANDFORM_ALGORITHM = "worldgen-v8-landforms-prototype-v2"

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
    value2 = value * value // Q
    value3 = value2 * value // Q
    return _clamp_q(3 * value2 - 2 * value3)


def _lerp_q(a: int, b: int, t: int) -> int:
    return int(a) + (int(b) - int(a)) * int(t) // Q


def _radial_strength(px: int, py: int, cx: int, cy: int, radius: int) -> int:
    dx, dy = px - cx, py - cy
    rr = max(1, int(radius)) ** 2
    distance2 = dx * dx + dy * dy
    if distance2 >= rr:
        return 0
    return _smooth_q((rr - distance2) * Q // rr)


def _segment_strength(
    px: int, py: int, ax: int, ay: int, bx: int, by: int, width: int
) -> int:
    """Return a 0..Q influence for a finite thick line, integer-only."""
    vx, vy = bx - ax, by - ay
    wx, wy = px - ax, py - ay
    vv = vx * vx + vy * vy
    rr = max(1, int(width)) ** 2
    if vv <= 0:
        return _radial_strength(px, py, ax, ay, width)

    dot = wx * vx + wy * vy
    if dot <= 0:
        distance2 = wx * wx + wy * wy
    elif dot >= vv:
        dx, dy = px - bx, py - by
        distance2 = dx * dx + dy * dy
    else:
        cross = wx * vy - wy * vx
        cross2 = cross * cross
        limit = rr * vv
        if cross2 >= limit:
            return 0
        return _smooth_q((limit - cross2) * Q // limit)

    if distance2 >= rr:
        return 0
    return _smooth_q((rr - distance2) * Q // rr)


@dataclass(frozen=True, slots=True)
class LandformFields:
    continentalness: int
    tectonic_uplift: int
    mountain_chain: int
    structural_valley: int
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
    """Stateless WORLDGEN v8 geological sampler with a bounded lattice cache."""

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
        a = _lerp_q(
            self._lattice_value(namespace, ix, iy),
            self._lattice_value(namespace, ix + 1, iy),
            tx,
        )
        b = _lerp_q(
            self._lattice_value(namespace, ix, iy + 1),
            self._lattice_value(namespace, ix + 1, iy + 1),
            tx,
        )
        return _lerp_q(a, b, ty)

    def _stress_direction(self, x: int, y: int) -> int:
        """Return a slowly changing regional tectonic direction index."""
        raw = self._value_noise("v8:tectonic:stress", x + 12011, y - 9047, 6144)
        return int(raw * len(_DIRECTIONS) // (Q + 1)) % len(_DIRECTIONS)

    def _major_ranges(self, x: int, y: int) -> int:
        """Long, regionally aligned orogenic belts spanning several regions."""
        cell = MAJOR_RANGE_CELL
        cx, cy = x // cell, y // cell
        best = 0
        for gy in range(cy - 1, cy + 2):
            for gx in range(cx - 1, cx + 2):
                if hash_u64(self.seed, "v8:major-range-active", LANDFORM_VERSION, gx, gy) % 100 >= 43:
                    continue
                jx = int(hash_u64(self.seed, "v8:major-range-x", LANDFORM_VERSION, gx, gy) % (cell // 2)) - cell // 4
                jy = int(hash_u64(self.seed, "v8:major-range-y", LANDFORM_VERSION, gx, gy) % (cell // 2)) - cell // 4
                mx = gx * cell + cell // 2 + jx
                my = gy * cell + cell // 2 + jy
                direction_index = self._stress_direction(mx, my)
                direction_index = (
                    direction_index
                    + int(hash_u64(self.seed, "v8:major-range-turn", LANDFORM_VERSION, gx, gy) % 3)
                    - 1
                ) % len(_DIRECTIONS)
                dx, dy = _DIRECTIONS[direction_index]
                half_length = 1500 + int(
                    hash_u64(self.seed, "v8:major-range-len", LANDFORM_VERSION, gx, gy) % 1000
                )
                ax = mx - dx * half_length // 1024
                ay = my - dy * half_length // 1024
                bx = mx + dx * half_length // 1024
                by = my + dy * half_length // 1024
                # Two deterministic perpendicular bends prevent long ranges from
                # reading as ruler-straight bars while preserving one coherent
                # regional stress direction.
                bend1 = int(hash_u64(self.seed, "v8:major-range-bend1", LANDFORM_VERSION, gx, gy) % 481) - 240
                bend2 = int(hash_u64(self.seed, "v8:major-range-bend2", LANDFORM_VERSION, gx, gy) % 481) - 240
                p1x = mx - dx * half_length // 3072 - dy * bend1 // 1024
                p1y = my - dy * half_length // 3072 + dx * bend1 // 1024
                p2x = mx + dx * half_length // 3072 - dy * bend2 // 1024
                p2y = my + dy * half_length // 3072 + dx * bend2 // 1024
                width = 280 + int(
                    hash_u64(self.seed, "v8:major-range-width", LANDFORM_VERSION, gx, gy) % 320
                )
                strength = max(
                    _segment_strength(x, y, ax, ay, p1x, p1y, width),
                    _segment_strength(x, y, p1x, p1y, p2x, p2y, width),
                    _segment_strength(x, y, p2x, p2y, bx, by, width),
                )
                amplitude = 47000 + int(
                    hash_u64(self.seed, "v8:major-range-amp", LANDFORM_VERSION, gx, gy) % 18536
                )
                best = max(best, strength * amplitude // Q)
        return _clamp_q(best)

    def _branch_ranges(self, x: int, y: int) -> int:
        """Smaller branches/foothill belts sharing the regional stress field."""
        cell = TECTONIC_CELL
        cx, cy = x // cell, y // cell
        best = 0
        for gy in range(cy - 1, cy + 2):
            for gx in range(cx - 1, cx + 2):
                if hash_u64(self.seed, "v8:branch-range-active", LANDFORM_VERSION, gx, gy) % 100 >= 29:
                    continue
                jx = int(hash_u64(self.seed, "v8:branch-range-x", LANDFORM_VERSION, gx, gy) % (cell // 2)) - cell // 4
                jy = int(hash_u64(self.seed, "v8:branch-range-y", LANDFORM_VERSION, gx, gy) % (cell // 2)) - cell // 4
                mx = gx * cell + cell // 2 + jx
                my = gy * cell + cell // 2 + jy
                direction_index = self._stress_direction(mx, my)
                direction_index = (
                    direction_index
                    + int(hash_u64(self.seed, "v8:branch-range-turn", LANDFORM_VERSION, gx, gy) % 5)
                    - 2
                ) % len(_DIRECTIONS)
                dx, dy = _DIRECTIONS[direction_index]
                half_length = 500 + int(
                    hash_u64(self.seed, "v8:branch-range-len", LANDFORM_VERSION, gx, gy) % 480
                )
                ax = mx - dx * half_length // 1024
                ay = my - dy * half_length // 1024
                bx = mx + dx * half_length // 1024
                by = my + dy * half_length // 1024
                width = 140 + int(
                    hash_u64(self.seed, "v8:branch-range-width", LANDFORM_VERSION, gx, gy) % 220
                )
                strength = _segment_strength(x, y, ax, ay, bx, by, width)
                amplitude = 30000 + int(
                    hash_u64(self.seed, "v8:branch-range-amp", LANDFORM_VERSION, gx, gy) % 25000
                )
                best = max(best, strength * amplitude // Q)
        return _clamp_q(best)

    def _orogeny(self, x: int, y: int) -> int:
        return _clamp_q(max(self._major_ranges(x, y), self._branch_ranges(x, y) * 4 // 5))

    def _basin(self, x: int, y: int) -> int:
        cell = BASIN_CELL
        cx, cy = x // cell, y // cell
        best = 0
        for gy in range(cy - 1, cy + 2):
            for gx in range(cx - 1, cx + 2):
                if hash_u64(self.seed, "v8:basin-active", LANDFORM_VERSION, gx, gy) % 100 >= 28:
                    continue
                jx = int(hash_u64(self.seed, "v8:basin-x", LANDFORM_VERSION, gx, gy) % cell) - cell // 2
                jy = int(hash_u64(self.seed, "v8:basin-y", LANDFORM_VERSION, gx, gy) % cell) - cell // 2
                bx = gx * cell + cell // 2 + jx
                by = gy * cell + cell // 2 + jy
                radius = 440 + int(
                    hash_u64(self.seed, "v8:basin-radius", LANDFORM_VERSION, gx, gy) % 820
                )
                strength = _radial_strength(x, y, bx, by, radius)
                amplitude = 30000 + int(
                    hash_u64(self.seed, "v8:basin-amp", LANDFORM_VERSION, gx, gy) % 35536
                )
                best = max(best, strength * amplitude // Q)
        return _clamp_q(best)

    def _structural_valley(self, x: int, y: int) -> int:
        """Long low corridors for rifts/intermontane valleys and future rivers."""
        cell = VALLEY_CELL
        cx, cy = x // cell, y // cell
        best = 0
        for gy in range(cy - 1, cy + 2):
            for gx in range(cx - 1, cx + 2):
                if hash_u64(self.seed, "v8:valley-active", LANDFORM_VERSION, gx, gy) % 100 >= 24:
                    continue
                mx = gx * cell + cell // 2 + int(
                    hash_u64(self.seed, "v8:valley-x", LANDFORM_VERSION, gx, gy) % (cell // 2)
                ) - cell // 4
                my = gy * cell + cell // 2 + int(
                    hash_u64(self.seed, "v8:valley-y", LANDFORM_VERSION, gx, gy) % (cell // 2)
                ) - cell // 4
                direction_index = self._stress_direction(mx, my)
                direction_index = (
                    direction_index
                    + int(hash_u64(self.seed, "v8:valley-turn", LANDFORM_VERSION, gx, gy) % 3)
                    - 1
                ) % len(_DIRECTIONS)
                dx, dy = _DIRECTIONS[direction_index]
                half_length = 900 + int(
                    hash_u64(self.seed, "v8:valley-len", LANDFORM_VERSION, gx, gy) % 900
                )
                ax = mx - dx * half_length // 1024
                ay = my - dy * half_length // 1024
                bx = mx + dx * half_length // 1024
                by = my + dy * half_length // 1024
                width = 180 + int(
                    hash_u64(self.seed, "v8:valley-width", LANDFORM_VERSION, gx, gy) % 320
                )
                strength = _segment_strength(x, y, ax, ay, bx, by, width)
                amplitude = 36000 + int(
                    hash_u64(self.seed, "v8:valley-amp", LANDFORM_VERSION, gx, gy) % 29536
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
        valley = self._structural_valley(x, y)

        plateau_raw = self._value_noise("v8:plateau", x + 44021, y + 17011, 1792)
        plateau = _clamp_q(max(0, plateau_raw - 38500) * 5 // 2)

        rough_raw = (
            self._value_noise("v8:rough:meso", x - 701, y + 503, 256) * 2
            + self._value_noise("v8:rough:local", x + 97, y - 193, 72)
        ) // 3
        roughness = _clamp_q(abs(rough_raw - Q // 2) * 2)

        # Coast detail is strongest near the continental land/ocean threshold.
        # It roughens broad shorelines without fragmenting continental interiors.
        coast_raw = self._value_noise("v8:coast-detail", x + 2309, y - 811, 512) - Q // 2
        coast_weight = max(0, Q - abs(continental - 26000) * Q // 14500)
        coastal_offset = coast_raw * coast_weight * 3000 // max(1, (Q // 2) * Q)

        # Keep the established 0..65535 elevation scale so the prototype can be
        # compared directly with v7 and later consumed by the existing hydrology
        # architecture after the explicit WORLDGEN v8 promotion gate.
        elevation = 8000 + continental * 30000 // Q
        uplift_support = _clamp_q((continental - 14000) * Q // 22000)
        uplift_scale = 18000 + uplift_support * (Q - 18000) // Q
        elevation += tectonic * 22000 // Q * uplift_scale // Q
        elevation += plateau * 6500 // Q * (32768 + uplift_support // 2) // Q
        elevation -= basin * 8000 // Q
        elevation -= valley * 5200 // Q
        elevation += (rough_raw - Q // 2) * 2500 // (Q // 2)
        elevation += coastal_offset
        elevation = _clamp_q(elevation)

        if elevation < SEA_LEVEL_REFERENCE:
            province = "oceanic_plain"
        elif mountain >= 35000 and tectonic >= 36000:
            province = "mountain_chain"
        elif valley >= 39000 and mountain >= 12000:
            province = "rift_valley"
        elif plateau >= 36000:
            province = "plateau"
        elif basin >= 38000:
            province = "basin"
        elif tectonic >= 25000:
            province = "upland"
        else:
            province = "lowland"

        return LandformFields(
            _clamp_q(continental), tectonic, mountain, valley, basin,
            plateau, roughness, elevation, province,
        )
