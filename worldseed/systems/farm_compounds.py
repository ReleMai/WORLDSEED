"""Bounded farm geometry projected into the authoritative settlement plan.

The service court is outside the growing area. Crop rotations share one outer
fence and a walking lane, rather than becoming separate fenced postage stamps.
This module owns no persistent crops, goods, buildings or terrain.
"""
from __future__ import annotations

from dataclasses import dataclass


FARM_SIZES = {
    "homestead": (18, 16), "hamlet": (28, 30), "village": (40, 34),
    "town": (50, 42), "city": (60, 50),
}


def terrain_crop_ids(env, registry=None):
    """Shared suitability for the physical plan and new-town starting seeds."""
    if env is None:
        pool = ("core:turnip", "core:barley")
    elif env.wetness >= 68:
        pool = ("core:beans", "core:cabbage", "core:pumpkin", "core:wheat")
    elif env.soil_fertility >= 67:
        pool = ("core:wheat", "core:corn", "core:beans", "core:pumpkin")
    elif env.wetness <= 30:
        pool = ("core:barley", "core:onion", "core:flax", "core:corn")
    else:
        pool = ("core:turnip", "core:carrot", "core:wheat", "core:beans")
    available = set(getattr(registry, "crops", {})) if registry is not None else set(pool)
    return [crop for crop in pool if crop in available][:4]


def starting_farm_seeds(stocks, crop_ids, registry):
    """Allocate existing initial seed capital; never reseed a living settlement."""
    seeds = [registry.crops[crop].seed_item for crop in crop_ids if crop in registry.crops]
    if not seeds:
        return
    capital = stocks.pop("core:wheat_seed", 0) + stocks.pop("core:turnip_seed", 0)
    amount, remainder = divmod(capital, len(seeds))
    for index, seed in enumerate(seeds):
        stocks[seed] = stocks.get(seed, 0) + amount + int(index < remainder)


@dataclass(frozen=True)
class FarmCompound:
    fields: tuple[tuple[tuple[int, int], ...], ...]
    extent: frozenset[tuple[int, int]]
    lane: tuple[tuple[int, int], ...]
    court: frozenset[tuple[int, int]]
    gate: tuple[int, int]
    service_center: tuple[int, int]

    @property
    def reserved(self):
        return self.extent | self.court


def farm_compound(gate: tuple[int, int], away: tuple[int, int], rank: str,
                  crop_count: int = 4) -> FarmCompound:
    """A chamfered field with contiguous crop blocks and a separate barn court.

    ``away`` is a cardinal direction away from town. Coordinates and crop slots
    are stable and do not depend on iteration order or another RNG domain.
    """
    width, depth = FARM_SIZES[rank]
    ax, ay = away
    if abs(ax) + abs(ay) != 1:
        raise ValueError("Farm orientation must be cardinal")
    crop_count = max(1, min(4, int(crop_count)))
    side = (-ay, ax)

    def project(u, v):
        return gate[0] + side[0]*u + ax*v, gate[1] + side[1]*u + ay*v

    blocks = [set() for _ in range(crop_count)]
    extent = set()
    half = width // 2
    for v in range(depth):
        # Clip only the corners, retaining a broad, single natural compound.
        inset = max(0, 3-min(v, depth-1-v))
        for u in range(-half+inset, width-half-inset):
            cell = project(u, v)
            extent.add(cell)
            if u == 0 and v < depth-1:
                continue
            block = (int(u >= 0) + 2*int(v >= depth//2)) % crop_count
            blocks[block].add(cell)
    lane = tuple(project(0, v) for v in range(-2, depth-1))
    court = frozenset(project(u, v) for v in range(-15, -2) for u in range(3, 18))
    return FarmCompound(
        tuple(tuple(sorted(cells, key=lambda p: (p[1], p[0]))) for cells in blocks),
        frozenset(extent), lane, court, gate, project(10, -9),
    )
