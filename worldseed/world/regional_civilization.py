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
        # Permanent settlement anchors must be land. Water access is valuable,
        # but an open-water cell itself can never win the civilization-site
        # search; fishing/river settlements are selected on adjacent dry ground.
        if env is not None and bool(getattr(env, "open_water", False)):
            return 0, "frontier", 0, 0, 0
        base_fertility = int(getattr(base, "fertility", 36000))
        base_moisture = int(getattr(base, "moisture", 33000))
        base_temperature = int(getattr(base, "temperature", 36000))
        base_elevation = int(getattr(base, "elevation", 32000))
        # Before prepared hydrology exists this is only a provisional land
        # candidate. Do not let the coarse climate proxy settle the base sea.
        if self.version >= 11 and env is None and base_elevation < 23800:
            return 0, "frontier", 0, 0, 0
        fertility = int(env.soil_fertility if env else base_fertility * 100 // 65535)
        farmland = int(env.farmland if env else max(0, fertility - 10))
        slope = int(env.slope if env else 20)
        relief = int(env.relief if env else 20)
        flood = int(env.flood_risk if env else 0)
        moisture = base_moisture * 100 // 65535
        # Before hydrology is prepared (notably Village Start candidate search),
        # climate moisture is only a coarse water-access proxy. Prepared worlds
        # replace it with the authoritative hydrology-derived freshwater field.
        freshwater = int(env.resources.freshwater if env else max(0, min(65, moisture * 3 // 4)))
        timber = int(env.resources.timber if env else moisture)
        stone = int(env.resources.stone if env else max(0, (base_elevation - 30000) * 100 // 30000))
        opportunity = int(env.resource_opportunity if env else (timber + stone + freshwater) // 3)
        temperature = base_temperature * 100 // 65535
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
        if self.version >= 11:
            # Productive woodland/quarry/shore hinterlands can sustain a site
            # without pretending they also have excellent farmland.
            score = min(100, score + max(0, max(timber, stone, freshwater) - farmland) // 5)

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

    def _site_fitness(self, x: int, y: int, samples: dict) -> int | None:
        """Bounded civic-core fit; never reads tiles or prepares geography.

        Missing environmental fields mean startup's *provisional* base-land
        search, not verified slope/flood suitability. It receives no fit bonus
        and must be refreshed after hydrology before local materialization.
        """
        env_reader = getattr(self.world, "environment_at", None)
        patch = []
        for dy in (-12, 0, 12):
            for dx in (-12, 0, 12):
                key = (int(x + dx), int(y + dy))
                sample = samples.get(key)
                if sample is None:
                    pos = WorldPos(*key, 0)
                    env = env_reader(pos) if callable(env_reader) else None
                    if env is None:
                        base = self.generator.sample_fields(pos)
                        sample = (int(getattr(base, "elevation", 0)) >= 23800, 0, 0, False)
                    else:
                        slope = int(env.slope)
                        flood = int(env.flood_risk)
                        sample = (not bool(env.open_water) and slope <= 78 and flood <= 88,
                                  slope, flood, True)
                    samples[key] = sample
                patch.append(sample)
        center = patch[4]
        buildable = sum(int(sample[0]) for sample in patch)
        prepared = sum(int(sample[3]) for sample in patch)
        if not center[0] or buildable < 7:
            return None
        # Do not combine verified land with unknown slope/flood cells on the
        # edge of a prepared domain and call the whole foundation buildable.
        if prepared == 0:
            return 0
        if prepared != 9 or center[1] > 72 or center[2] > 82:
            return None
        slope = sum(sample[1] for sample in patch) // 9
        flood = sum(sample[2] for sample in patch) // 9
        return (buildable - 7) * 2 + (max(0, 24 - slope) + max(0, 24 - flood)) // 12

    def _fit_candidates(self, key: tuple[int, int], candidates: list) -> list:
        """V11 checks six coarse cores, then three local finalists at most.

        Together with the existing 36 coarse samples this costs at most 126
        environment reads per raw region. The temporary patch cache is bounded
        to 81 cells and discarded immediately; infinite-world growth is not
        proportional to all evaluated foundation cells.
        """
        samples: dict = {}
        fitted = []
        for row in sorted(candidates, reverse=True)[:6]:
            if row[0] <= 0:
                continue
            fitness = self._site_fitness(row[5], row[6], samples)
            if fitness is not None:
                fitted.append((min(100, row[0] + fitness), *row[1:]))
        if not fitted:
            row = max(candidates)
            return [(0, 0, 0, row[3], row[4], row[5], row[6], row[7])]
        _, _, _, _, _, sx, sy, _ = max(fitted)
        x0, y0 = key[0] * REGION_SIZE, key[1] * REGION_SIZE
        refined = []
        for dy in (-18, 0, 18):
            for dx in (-18, 0, 18):
                x = max(x0 + 64, min(x0 + REGION_SIZE - 65, sx + dx))
                y = max(y0 + 64, min(y0 + REGION_SIZE - 65, sy + dy))
                score, archetype, route, defense, crossing = self._site_score(x, y)
                tie = int(hash_u64(self.seed, "civil-refine-tie", *key, x, y) % 10000)
                refined.append((score, route, crossing, defense, tie, x, y, archetype))
        for row in sorted(refined, reverse=True)[:3]:
            if row[0] <= 0:
                continue
            fitness = self._site_fitness(row[5], row[6], samples)
            if fitness is not None:
                fitted.append((min(100, row[0] + fitness), *row[1:]))
        return fitted

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

        refined = self._fit_candidates(key, candidates) if self.version >= 11 else list(candidates)
        for _, _, _, _, _, sx, sy, _ in ([] if self.version >= 11 else sorted(candidates, reverse=True)[:3]):
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
        if self.version >= 11:
            # Compete for nearby physical hinterlands, not an entire 3x3
            # region square. A broad valley need not lose a suitable site to a
            # stronger settlement hundreds of cells beyond its own catchment.
            def priority(row):
                return (row["score"], row["route"], row["crossing"],
                        hash_u64(self.seed, "civil-spacing-tie", *row["anchor"]))

            nearby_stronger = any(
                (row["anchor"][0] - raw["anchor"][0]) ** 2 +
                (row["anchor"][1] - raw["anchor"][1]) ** 2 < 384 ** 2
                and priority(row) > priority(raw)
                for row in neighbors
            )
            present = bool(raw["score"] >= 35 and not nearby_stronger)
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
