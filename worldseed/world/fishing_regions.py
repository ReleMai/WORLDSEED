"""Deterministic fishing regions layered over authoritative WORLDSEED water terrain."""
from __future__ import annotations

from dataclasses import dataclass

from worldseed.core.coords import WorldPos
from worldseed.core.rng import hash_u64

FISHING_REGION_CELL = 192

_HABITAT_BY_TERRAIN = {
    "core:river_shallow": "river",
    "core:stream": "river",
    "core:river_rapids": "river",
    "core:river": "river_deep",
    "core:lake_shallow": "lake_shallow",
    "core:lake_deep": "lake_deep",
    "core:water": "lake_deep",
    "core:estuary_shallow": "estuary_shallow",
    "core:estuary_deep": "estuary_deep",
    "core:ocean_wade": "coast",
    "core:ocean_shallow": "ocean_shallow",
    "core:ocean_shelf": "shelf",
    "core:ocean_deep": "deep_ocean",
}

_STRUCTURES = {
    "river": ("riffle", "run", "pool", "current_seam"),
    "river_deep": ("channel", "pool", "current_seam"),
    "lake_shallow": ("weedbed", "reed_edge", "open_water"),
    "lake_deep": ("dropoff", "open_water", "deep_channel"),
    "estuary_shallow": ("mudflat", "grassbed", "channel", "shoal"),
    "estuary_deep": ("channel", "current_seam", "deep_channel"),
    "coast": ("sandbar", "grassbed", "shoal", "surf"),
    "ocean_shallow": ("shoal", "grassbed", "current_seam", "open_water"),
    "shelf": ("shelf_edge", "current_seam", "open_water"),
    "deep_ocean": ("deep_channel", "open_water", "current_seam"),
}


@dataclass(frozen=True, slots=True)
class FishingRegion:
    uid: str
    habitat: str
    structure: str
    salinity: str
    depth: str
    productivity: int
    temperature: int
    current: int
    cell_x: int
    cell_y: int


class FishingRegionSampler:
    def __init__(self, world_seed: bytes, generator) -> None:
        self.seed = bytes(world_seed)
        self.generator = generator

    def sample(self, pos: WorldPos) -> FishingRegion | None:
        if pos.z != 0:
            return None
        terrain_id = self.generator.terrain_at(pos)
        habitat = _HABITAT_BY_TERRAIN.get(terrain_id)
        if not habitat:
            return None
        cx, cy = pos.x // FISHING_REGION_CELL, pos.y // FISHING_REGION_CELL
        fields = self.generator.sample_fields(pos)
        choices = _STRUCTURES[habitat]
        structure = choices[hash_u64(self.seed, "fishing-region-structure", cx, cy, habitat) % len(choices)]
        variation = int(hash_u64(self.seed, "fishing-region-productivity", cx, cy, habitat) % 31) - 15
        productivity = max(10, min(100, 28 + fields.fertility * 48 // 65535 + fields.moisture * 20 // 65535 + variation))
        current = 0
        surface_current = self.generator.current_at(pos, prepared_only=True)
        if surface_current and surface_current.flowing:
            current = int(surface_current.speed)
            if current >= 55 and habitat in {"river", "river_deep", "estuary_deep", "ocean_shallow", "shelf"}:
                structure = "current_seam"
        salinity = "salt" if habitat in {"coast","ocean_shallow","shelf","deep_ocean"} else "brackish" if habitat.startswith("estuary") else "fresh"
        depth = "shallow" if habitat in {"river","lake_shallow","estuary_shallow","coast"} else "deep"
        uid = f"fishzone:{cx}:{cy}:{habitat}"
        return FishingRegion(uid, habitat, structure, salinity, depth, productivity, fields.temperature, current, cx, cy)
