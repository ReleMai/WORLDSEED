"""Derived topographic fields for WORLDGEN v8.

This module is deliberately a read model over authoritative v8 geological
elevation. It does not own terrain IDs, hydrology, persistence, or rendering.
The same absolute-coordinate stencil is used everywhere so chunk boundaries and
negative coordinates cannot reset slope/relief calculations.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Callable

from worldseed.core.coords import WorldPos

Q = 65535
NEAR_RADIUS = 6
RELIEF_RADIUS = 32


def _clamp_q(value: int) -> int:
    return max(0, min(Q, int(value)))


@dataclass(frozen=True, slots=True)
class TopographyFields:
    elevation: int
    slope_x: int
    slope_y: int
    slope: int
    relief_raw: int
    relief: int
    ridge_exposure: int
    valley_depth: int
    ruggedness: int

    @property
    def steep(self) -> bool:
        return self.slope >= 42000

    @property
    def low_relief(self) -> bool:
        return self.relief <= 12000


class TopographySampler:
    """Deterministic derivative sampler over a v8 elevation callable."""

    def __init__(self, elevation_at: Callable[[int, int], int]) -> None:
        self._elevation_at = elevation_at

    def _elevation(self, x: int, y: int) -> int:
        return int(self._elevation_at(int(x), int(y)))

    @lru_cache(maxsize=32768)
    def sample_xy(self, x: int, y: int) -> TopographyFields:
        x, y = int(x), int(y)
        center = self._elevation(x, y)

        west = self._elevation(x - NEAR_RADIUS, y)
        east = self._elevation(x + NEAR_RADIUS, y)
        north = self._elevation(x, y - NEAR_RADIUS)
        south = self._elevation(x, y + NEAR_RADIUS)

        slope_x = east - west
        slope_y = south - north
        gradient = abs(slope_x) + abs(slope_y)
        slope = _clamp_q(gradient * Q // 9000)

        far = (
            self._elevation(x - RELIEF_RADIUS, y),
            self._elevation(x + RELIEF_RADIUS, y),
            self._elevation(x, y - RELIEF_RADIUS),
            self._elevation(x, y + RELIEF_RADIUS),
            self._elevation(x - RELIEF_RADIUS, y - RELIEF_RADIUS),
            self._elevation(x + RELIEF_RADIUS, y - RELIEF_RADIUS),
            self._elevation(x - RELIEF_RADIUS, y + RELIEF_RADIUS),
            self._elevation(x + RELIEF_RADIUS, y + RELIEF_RADIUS),
        )
        local_min = min(far)
        local_max = max(far)
        relief_raw = local_max - local_min
        relief = _clamp_q(relief_raw * Q // 18000)

        near_mean = (west + east + north + south) // 4
        ridge_exposure = _clamp_q(max(0, center - near_mean) * Q // 7000)
        valley_depth = _clamp_q(max(0, near_mean - center) * Q // 7000)

        # Ruggedness combines large relief and short-range slope while keeping
        # each field independently inspectable by later hydrology/soil systems.
        ruggedness = _clamp_q((relief * 3 + slope * 2) // 5)
        return TopographyFields(
            center, slope_x, slope_y, slope, relief_raw, relief,
            ridge_exposure, valley_depth, ruggedness,
        )

    def sample(self, pos: WorldPos) -> TopographyFields | None:
        if pos.z != 0:
            return None
        return self.sample_xy(pos.x, pos.y)
