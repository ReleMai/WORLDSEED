"""Deterministic regional civilization potential for WORLDSEED.

This layer answers a bounded question: given physical geography, where is
permanent settlement plausible and what kind of settlement wants to emerge?
It owns no population, economy, faction state or local buildings. It is a
reconstructable planning read model consumed by RegionBlockPlanner.
"""
from __future__ import annotations

from dataclasses import dataclass

from worldseed.core.canonical import canonical_hash
from worldseed.core.coords import WorldPos
from worldseed.core.rng import hash_u64

REGION_SIZE = 512


@dataclass(frozen=True, slots=True)
class RegionalCivilizationProfile:
    region_x: int
    region_y: int
    score: int
    carrying_capacity: int
    settlement_present: bool
    anchor: tuple[int, int]
    archetype: str
    rank_hint: str
    morphology: str
    route_value: int
    defensibility: int
    crossing_value: int
    culture_seed: int
    prominent_faction_seed: bool
    fingerprint: str = ""


class RegionalCivilizationPlanner:
    """Terrain-first settlement potential without realizing civilization."""

    _MORPHOLOGY = {
        "agrarian": "field_cluster",
        "river_market": "river_spine",
        "mining": "compact_workyard",
        "forest": "clearing_web",
        "fishing": "waterfront",
        "frontier": "crossroads",
    }

    def __init__(self, world, version: int = 1, seed: bytes | None = None):
        self.world = world
        self.generator = world.generator
        self.seed = seed if seed is not None else getattr(world.generator, "world_seed", b"")
        self.version = int(version)
        self._raw_cache: dict[tuple[int, int], dict] = {}
        self._profile_cache: dict[tuple[int, int], RegionalCivilizationProfile] = {}

    def _site_score(self, x: int, y: int) -> tuple[int, str, int, int, int]:
        pos = WorldPos(int(x), int(y), 0)
        base = self.generator.sample_fields(pos)
        env_reader = getattr(self.world, "environment_at", None)
        env = env_reader(pos) if callable(env_reader) else None
        fertility = int(env.soil_fertility if env else base.fertility * 100 // 65535)
        farmland = int(env.farmland if env else max(0, fertility - 10))
        slope = int(env.slope if env else 20)
        relief = int(env.relief if env else 20)
        flood = int(env.flood_risk if env else 0)
        moisture = base.moisture * 100 // 65535
        # Before hydrology is prepared (notably Village Start candidate search),
        # climate moisture is only a coarse water-access proxy. Prepared worlds
        # replace it with the authoritative hydrology-derived freshwater field.
        freshwater = int(env.resources.freshwater if env else max(0, min(65, moisture * 3 // 4)))
        timber = int(env.resources.timber if env else moisture)
        stone = int(env.resources.stone if env else max(0, (base.elevation - 30000) * 100 // 30000))
        opportunity = int(env.resource_opportunity if env else (timber + stone + freshwater) // 3)
        temperature = base.temperature * 100 // 65535
        temperate = max(0, 100 - abs(temperature - 55) * 2)

        crossing = max(0, freshwater - flood // 2 - max(0, slope - 35))
        defensibility = max(0, min(100, relief + slope // 2 + stone // 3 - flood // 2))
        route_value = max(
            0, min(100, farmland // 2 + freshwater // 2 + opportunity // 2
                   + crossing // 3 - slope // 2 - flood // 2)
        )
        score = (
            farmland * 4 + fertility * 2 + freshwater * 2 + timber + stone
            + temperate * 2 + crossing + route_value
        ) // 13
        score -= slope // 2 + flood // 2
        score = max(0, min(100, score))

        if freshwater >= 70 and route_value >= 55:
            archetype = "river_market"
        elif stone >= 65 and (slope >= 24 or relief >= 45):
            archetype = "mining"
        elif timber >= 70:
            archetype = "forest"
        elif freshwater >= 68 and farmland < 42:
            archetype = "fishing"
        elif farmland >= 48:
            archetype = "agrarian"
        else:
            archetype = "frontier"
        return score, archetype, route_value, defensibility, crossing

    def _raw(self, rx: int, ry: int) -> dict:
        key = (int(rx), int(ry))
        cached = self._raw_cache.get(key)
        if cached is not None:
            return cached
        x0, y0 = key[0] * REGION_SIZE, key[1] * REGION_SIZE
        candidates = []
        for gy in range(1, 7):
            for gx in range(1, 7):
                jx = int(hash_u64(self.seed, "civil-site-x", key[0], key[1], gx, gy) % 37) - 18
                jy = int(hash_u64(self.seed, "civil-site-y", key[0], key[1], gx, gy) % 37) - 18
                x = max(x0 + 64, min(x0 + REGION_SIZE - 65, x0 + 54 + gx * 58 + jx))
                y = max(y0 + 64, min(y0 + REGION_SIZE - 65, y0 + 54 + gy * 58 + jy))
                score, archetype, route, defense, crossing = self._site_score(x, y)
                tie = int(hash_u64(self.seed, "civil-site-tie", key[0], key[1], x, y) % 10000)
                candidates.append((score, route, crossing, defense, tie, x, y, archetype))

        refined = list(candidates)
        for _, _, _, _, _, sx, sy, _ in sorted(candidates, reverse=True)[:3]:
            for dy in (-18, 0, 18):
                for dx in (-18, 0, 18):
                    x = max(x0 + 64, min(x0 + REGION_SIZE - 65, sx + dx))
                    y = max(y0 + 64, min(y0 + REGION_SIZE - 65, sy + dy))
                    score, archetype, route, defense, crossing = self._site_score(x, y)
                    tie = int(hash_u64(self.seed, "civil-refine-tie", key[0], key[1], x, y) % 10000)
                    refined.append((score, route, crossing, defense, tie, x, y, archetype))

        score, route, crossing, defense, _, x, y, archetype = max(
            refined, key=lambda row: (row[0], row[1], row[2], row[3], row[4])
        )
        carrying = max(0, min(100, score * 2 // 3 + route // 3 + crossing // 6))
        raw = {
            "score": int(score), "route": int(route), "crossing": int(crossing),
            "defense": int(defense), "anchor": (int(x), int(y)),
            "archetype": str(archetype), "carrying": int(carrying),
        }
        self._raw_cache[key] = raw
        return raw

    @staticmethod
    def _rank_hint(carrying: int) -> str:
        if carrying >= 78: return "city"
        if carrying >= 65: return "town"
        if carrying >= 52: return "village"
        if carrying >= 40: return "hamlet"
        return "homestead"

    def profile(self, rx: int, ry: int) -> RegionalCivilizationProfile:
        key = (int(rx), int(ry))
        cached = self._profile_cache.get(key)
        if cached is not None:
            return cached
        raw = self._raw(*key)
        neighbors = [
            self._raw(key[0] + dx, key[1] + dy)
            for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dx or dy
        ]
        better = sum(
            1 for row in neighbors
            if (row["score"], row["route"], row["crossing"]) >
               (raw["score"], raw["route"], raw["crossing"])
        )
        strong_cluster = (
            raw["score"] >= 68 and raw["route"] >= 58 and
            hash_u64(self.seed, "civil-cluster", key[0], key[1]) % 100 < 58
        )
        # Two stronger neighboring sites may suppress a marginal location, but
        # good terrain remains viable enough for natural settlement clusters and
        # Village Start to survive the later hydrology-aware refinement pass.
        present = bool(raw["score"] >= 35 and (better <= 2 or strong_cluster))
        rank = self._rank_hint(raw["carrying"])
        morphology = self._MORPHOLOGY.get(raw["archetype"], "organic")
        faction_seed = bool(
            present and rank in {"town", "city"} and raw["route"] >= 58 and better == 0
        )
        culture_seed = int(hash_u64(self.seed, "culture-region-style", key[0] // 3, key[1] // 3) & 0x7FFFFFFF)
        payload = {
            "region_x": key[0], "region_y": key[1], "score": raw["score"],
            "carrying_capacity": raw["carrying"], "settlement_present": present,
            "anchor": list(raw["anchor"]), "archetype": raw["archetype"],
            "rank_hint": rank, "morphology": morphology, "route_value": raw["route"],
            "defensibility": raw["defense"], "crossing_value": raw["crossing"],
            "culture_seed": culture_seed, "prominent_faction_seed": faction_seed,
            "version": self.version,
        }
        profile = RegionalCivilizationProfile(
            region_x=key[0], region_y=key[1], score=raw["score"],
            carrying_capacity=raw["carrying"], settlement_present=present,
            anchor=raw["anchor"], archetype=raw["archetype"], rank_hint=rank,
            morphology=morphology, route_value=raw["route"],
            defensibility=raw["defense"], crossing_value=raw["crossing"],
            culture_seed=culture_seed, prominent_faction_seed=faction_seed,
            fingerprint=canonical_hash(payload),
        )
        self._profile_cache[key] = profile
        return profile
