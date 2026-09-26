from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from worldseed.config import CHUNK_SIZE, REGION_CHUNKS, SETTLEMENT_PLAN_VERSION
from worldseed.core.canonical import canonical_hash
from worldseed.core.coords import WorldPos
from worldseed.core.rng import derive_seed, hash_u64
from worldseed.world.regional_civilization import RegionalCivilizationPlanner

REGION_SIZE = CHUNK_SIZE * REGION_CHUNKS
CARDINALS = {
    "north": (0, -1),
    "east": (1, 0),
    "south": (0, 1),
    "west": (-1, 0),
}


def region_coords(x: int, y: int) -> tuple[int, int]:
    return int(x) // REGION_SIZE, int(y) // REGION_SIZE


def entry_side(old_x: int, old_y: int, new_x: int, new_y: int) -> str | None:
    """Side of the destination region crossed by a cardinal world step."""
    a = region_coords(old_x, old_y)
    b = region_coords(new_x, new_y)
    if a == b:
        return None
    dx, dy = b[0] - a[0], b[1] - a[1]
    if (dx, dy) == (0, 1):
        return "north"
    if (dx, dy) == (0, -1):
        return "south"
    if (dx, dy) == (1, 0):
        return "west"
    if (dx, dy) == (-1, 0):
        return "east"
    return None


@dataclass(frozen=True, slots=True)
class RegionRoadExit:
    direction: str
    offset: int
    road_class: str


@dataclass(frozen=True, slots=True)
class RegionWaterExit:
    direction: str
    offset: int
    river_class: int
    current_heading: str = 'still'
    current_strength: int = 0
    water_kind: str = 'river'


@dataclass(frozen=True, slots=True)
class RegionBlockPlan:
    uid: str
    region_x: int
    region_y: int
    version: int
    dominant_biome: str
    biome_mix: dict[str, int]
    mean_elevation: int
    mean_moisture: int
    mean_temperature: int
    relief: int
    settlement_present: bool
    settlement_anchor: tuple[int, int] | None
    settlement_score: int
    settlement_archetype: str
    control_potential: str
    wilderness_tags: tuple[str, ...] = ()
    site_potential: bool = False
    roads: tuple[RegionRoadExit, ...] = ()
    waters: tuple[RegionWaterExit, ...] = ()
    carrying_capacity: int = 0
    settlement_rank_hint: str = "homestead"
    settlement_morphology: str = "organic"
    route_value: int = 0
    defensibility: int = 0
    crossing_value: int = 0
    culture_seed: int = 0
    prominent_faction_seed: bool = False
    fingerprint: str = ""

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["settlement_anchor"] = list(self.settlement_anchor) if self.settlement_anchor else None
        value["wilderness_tags"] = list(self.wilderness_tags)
        value["roads"] = [asdict(x) for x in self.roads]
        value["waters"] = [asdict(x) for x in self.waters]
        return value

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RegionBlockPlan":
        anchor = raw.get("settlement_anchor")
        return cls(
            uid=str(raw["uid"]), region_x=int(raw["region_x"]), region_y=int(raw["region_y"]),
            version=int(raw["version"]), dominant_biome=str(raw["dominant_biome"]),
            biome_mix={str(k): int(v) for k, v in dict(raw.get("biome_mix", {})).items()},
            mean_elevation=int(raw.get("mean_elevation", 0)), mean_moisture=int(raw.get("mean_moisture", 0)),
            mean_temperature=int(raw.get("mean_temperature", 0)), relief=int(raw.get("relief", 0)),
            settlement_present=bool(raw.get("settlement_present", False)),
            settlement_anchor=(int(anchor[0]), int(anchor[1])) if anchor else None,
            settlement_score=int(raw.get("settlement_score", 0)),
            settlement_archetype=str(raw.get("settlement_archetype", "wilderness")),
            control_potential=str(raw.get("control_potential", "wild")),
            wilderness_tags=tuple(str(x) for x in raw.get("wilderness_tags", ())),
            site_potential=bool(raw.get("site_potential", False)),
            roads=tuple(RegionRoadExit(str(x["direction"]), int(x["offset"]), str(x["road_class"])) for x in raw.get("roads", ())),
            waters=tuple(RegionWaterExit(
                str(x["direction"]), int(x["offset"]), int(x["river_class"]),
                str(x.get("current_heading", 'still')), int(x.get("current_strength", 0)),
                str(x.get("water_kind", 'river')),
            ) for x in raw.get("waters", ())),
            carrying_capacity=int(raw.get("carrying_capacity", 0)),
            settlement_rank_hint=str(raw.get("settlement_rank_hint", "homestead")),
            settlement_morphology=str(raw.get("settlement_morphology", "organic")),
            route_value=int(raw.get("route_value", 0)),
            defensibility=int(raw.get("defensibility", 0)),
            crossing_value=int(raw.get("crossing_value", 0)),
            culture_seed=int(raw.get("culture_seed", 0)),
            prominent_faction_seed=bool(raw.get("prominent_faction_seed", False)),
            fingerprint=str(raw.get("fingerprint", "")),
        )


class RegionBlockPlanner:
    """Cheap strategic plan for one 512x512 explorable block.

    This layer is reconstructable generated data. It summarizes terrain and
    selects stable settlement/connection potential without creating local NPCs,
    buildings, resources or a second economy. Exact local physicalization stays
    under the existing simulation/world authorities.
    """

    def __init__(self, world, version: int | None = None):
        self.world = world
        self.generator = world.generator
        self.seed = world.generator.world_seed
        self.cache_source = world.delta_source
        if version is None:
            version = getattr(world, "settlement_plan_version", SETTLEMENT_PLAN_VERSION)
        self.version = int(version)
        self._cache: dict[tuple[int, int], RegionBlockPlan] = {}
        self.civilization = RegionalCivilizationPlanner(world, self.version)

    def _presence(self, rx: int, ry: int) -> bool:
        if self.version < 4:
            return derive_seed(self.seed, "settlement-presence", int(rx), int(ry)) % 100 < 42
        return self.civilization.profile(int(rx), int(ry)).settlement_present

    def _biome_for(self, pos: WorldPos) -> str:
        f = self.generator.sample_fields(pos)
        if f.elevation < 23800:
            return "water"
        if f.elevation < 26500:
            return "coast"
        if f.elevation > 52500:
            return "highland"
        if f.temperature < 15000:
            return "tundra"
        if f.moisture < 17500 and f.temperature > 36000:
            return "scrub"
        if f.moisture > 42500 and 16500 < f.temperature < 56500:
            return "forest"
        if f.moisture > 37500 and 19500 < f.temperature < 53500 and f.fertility > 39000:
            return "forest"
        return "grassland"

    def _candidate_score(self, x: int, y: int) -> tuple[int, str]:
        pos = WorldPos(x, y, 0)
        f = self.generator.sample_fields(pos)
        env = self.world.environment_at(pos)
        fertility = int(env.soil_fertility if env else f.fertility * 100 // 65535)
        farmland = int(env.farmland if env else max(0, fertility - 10))
        slope = int(env.slope if env else 18)
        flood = int(env.flood_risk if env else 0)
        freshwater = int(env.resources.freshwater if env else 0)
        timber = int(env.resources.timber if env else f.moisture * 100 // 65535)
        stone = int(env.resources.stone if env else max(0, (f.elevation - 30000) * 100 // 30000))
        temperature = f.temperature * 100 // 65535
        temperate = max(0, 100 - abs(temperature - 55) * 2)
        # Bounded causal score. Water helps strongly but never outweighs severe
        # flooding/steepness. Resource access breaks ties between fertile sites.
        score = (farmland * 3 + fertility * 2 + freshwater * 2 + timber + stone + temperate * 2) // 11
        score -= slope // 2 + flood // 2
        score = max(0, min(100, score))
        if freshwater >= 65 and farmland >= 45:
            archetype = "river_market" if freshwater >= 85 else "agrarian"
        elif stone >= 65 and slope >= 25:
            archetype = "mining"
        elif timber >= 70:
            archetype = "forest"
        elif freshwater >= 70:
            archetype = "fishing"
        else:
            archetype = "frontier"
        return score, archetype

    def _best_settlement_site(self, rx: int, ry: int) -> tuple[tuple[int, int], int, str]:
        if self.version >= 4:
            profile = self.civilization.profile(int(rx), int(ry))
            return profile.anchor, profile.score, profile.archetype
        x0, y0 = rx * REGION_SIZE, ry * REGION_SIZE
        best: tuple[int, int, int, str] | None = None
        for gy in range(1, 7):
            for gx in range(1, 7):
                jx = int(hash_u64(self.seed, "region-site-x", rx, ry, gx, gy) % 33) - 16
                jy = int(hash_u64(self.seed, "region-site-y", rx, ry, gx, gy) % 33) - 16
                x = max(x0 + 64, min(x0 + REGION_SIZE - 65, x0 + 64 + gx * 55 + jx))
                y = max(y0 + 64, min(y0 + REGION_SIZE - 65, y0 + 64 + gy * 55 + jy))
                score, archetype = self._candidate_score(x, y)
                tie = int(hash_u64(self.seed, "region-site-tie", rx, ry, x, y) % 1000)
                row = (score * 1000 + tie, x, y, archetype)
                if best is None or row[0] > best[0]:
                    best = row
        assert best is not None
        return (best[1], best[2]), best[0] // 1000, best[3]

    def _road_edge(self, rx: int, ry: int, direction: str) -> RegionRoadExit | None:
        dx, dy = CARDINALS[direction]
        if self.version < 4:
            nx, ny = rx + dx, ry + dy
            a, b = sorted(((rx, ry), (nx, ny)))
            both = int(self._presence(rx, ry)) + int(self._presence(nx, ny))
            threshold = 16 if both == 0 else 46 if both == 1 else 78
            roll = hash_u64(self.seed, "regional-road-edge", a[0], a[1], b[0], b[1]) % 100
            if roll >= threshold:
                return None
            offset = 64 + int(hash_u64(self.seed, "regional-road-offset", a[0], a[1], b[0], b[1]) % (REGION_SIZE - 128))
            return RegionRoadExit(direction, offset, "road" if both == 2 else "trail")
        nx, ny = rx + dx, ry + dy
        a_profile = self.civilization.profile(rx, ry)
        b_profile = self.civilization.profile(nx, ny)
        if not (a_profile.settlement_present or b_profile.settlement_present):
            return None
        both = a_profile.settlement_present and b_profile.settlement_present
        utility = (a_profile.route_value + b_profile.route_value) // 2
        utility += 18 if both else 0
        utility += (a_profile.crossing_value + b_profile.crossing_value) // 8
        if utility < (42 if both else 58):
            return None
        pair = sorted(((rx, ry), (nx, ny)))
        candidates = []
        for offset in range(64, REGION_SIZE - 63, 32):
            if direction in {"north", "south"}:
                x = rx * REGION_SIZE + offset
                y = ry * REGION_SIZE if direction == "north" else (ry + 1) * REGION_SIZE - 1
                ax, ay = x, y
                bx, by = x, y - 1 if direction == "north" else y + 1
            else:
                x = rx * REGION_SIZE if direction == "west" else (rx + 1) * REGION_SIZE - 1
                y = ry * REGION_SIZE + offset
                ax, ay = x, y
                bx, by = x - 1 if direction == "west" else x + 1, y
            ea = self.world.environment_at(WorldPos(ax, ay, 0))
            eb = self.world.environment_at(WorldPos(bx, by, 0))
            if ea is None or eb is None:
                continue
            penalty = int(ea.slope) + int(eb.slope) + int(ea.flood_risk) + int(eb.flood_risk)
            if ea.open_water or eb.open_water:
                penalty += 120
            tie = int(hash_u64(self.seed, "regional-road-footing", pair[0][0], pair[0][1], pair[1][0], pair[1][1], offset) % 1000)
            candidates.append((penalty, tie, offset))
        if candidates:
            offset = min(candidates)[2]
        else:
            offset = 64 + int(hash_u64(self.seed, "regional-road-offset", pair[0][0], pair[0][1], pair[1][0], pair[1][1]) % (REGION_SIZE - 128))
        high_rank = {"town", "city"}
        road_class = "maintained_road" if a_profile.rank_hint in high_rank and b_profile.rank_hint in high_rank else ("road" if both else "trail")
        return RegionRoadExit(direction, offset, road_class)

    def _water_edges(self, rx: int, ry: int) -> tuple[RegionWaterExit, ...]:
        hydro = getattr(self.generator, "hydrology", None)
        if hydro is None:
            return ()
        x0, y0 = rx * REGION_SIZE, ry * REGION_SIZE
        found: list[RegionWaterExit] = []
        sea_level = 23800
        for direction in CARDINALS:
            best_river: tuple[int, int, int, Any | None] | None = None
            best_ocean: tuple[int, int, Any | None] | None = None
            ocean_hits = 0
            for offset in range(32, REGION_SIZE, 32):
                if direction == "north": x, y = x0 + offset, y0
                elif direction == "south": x, y = x0 + offset, y0 + REGION_SIZE - 1
                elif direction == "west": x, y = x0, y0 + offset
                else: x, y = x0 + REGION_SIZE - 1, y0 + offset
                surface = hydro.surface_at(WorldPos(x, y, 0), prepared_only=True)
                if surface is None:
                    continue
                current = self.world.current_at(WorldPos(x, y, 0), prepared_only=True)
                strength = int(getattr(current, 'speed', 0) or 0)
                cls = int(getattr(surface, "river_class", 0) or 0)
                if getattr(surface, "lake", False):
                    cls = max(cls, 3)
                if cls > 0:
                    row = (cls, strength, offset, current)
                    if best_river is None or row[:2] > best_river[:2]:
                        best_river = row
                    continue
                if self.generator.sample_fields(WorldPos(x, y, 0)).elevation < sea_level:
                    ocean_hits += 1
                    row = (strength, offset, current)
                    if best_ocean is None or row[0] > best_ocean[0]:
                        best_ocean = row
            if best_river:
                cls, strength, offset, current = best_river
                heading = str(getattr(current, 'heading', 'still')) if current is not None else 'still'
                found.append(RegionWaterExit(direction, offset, cls, heading, strength, 'river'))
            elif best_ocean and ocean_hits >= 3:
                strength, offset, current = best_ocean
                heading = str(getattr(current, 'heading', 'still')) if current is not None else 'still'
                found.append(RegionWaterExit(direction, offset, 0, heading, strength, 'ocean'))
        return tuple(found)

    def _generate(self, rx: int, ry: int) -> RegionBlockPlan:
        x0, y0 = rx * REGION_SIZE, ry * REGION_SIZE
        mix: dict[str, int] = {}
        elevations: list[int] = []
        moistures: list[int] = []
        temperatures: list[int] = []
        for gy in range(1, 6):
            for gx in range(1, 6):
                p = WorldPos(x0 + gx * REGION_SIZE // 6, y0 + gy * REGION_SIZE // 6, 0)
                biome = self._biome_for(p); mix[biome] = mix.get(biome, 0) + 1
                f = self.generator.sample_fields(p)
                elevations.append(f.elevation); moistures.append(f.moisture); temperatures.append(f.temperature)
        dominant = max(sorted(mix), key=lambda k: mix[k])
        profile = self.civilization.profile(rx, ry) if self.version >= 4 else None
        present = profile.settlement_present if profile is not None else self._presence(rx, ry)
        if present:
            if profile is not None:
                anchor, settlement_score, archetype = profile.anchor, profile.score, profile.archetype
            else:
                anchor, settlement_score, archetype = self._best_settlement_site(rx, ry)
        else:
            anchor = None
            settlement_score = profile.score if profile is not None else 0
            archetype = "wilderness"
        relief = max(elevations) - min(elevations)
        mean_m = sum(moistures) // len(moistures)
        mean_t = sum(temperatures) // len(temperatures)
        tags: list[str] = []
        if dominant == "forest" or mean_m > 43000: tags.append("wooded")
        if relief > 10000: tags.append("rugged")
        if mean_m < 19000: tags.append("dry")
        if mean_t < 17000: tags.append("cold")
        if "water" in mix or "coast" in mix: tags.append("waterside")
        control = "settled" if present else ("bandit_frontier" if hash_u64(self.seed, "region-bandit-potential", rx, ry) % 100 < 11 else "wild")
        site_potential = bool(profile.score >= 34) if profile is not None else hash_u64(self.seed, "region-site-potential", rx, ry) % 100 < 18
        roads = tuple(x for d in CARDINALS if (x := self._road_edge(rx, ry, d)) is not None)
        waters = self._water_edges(rx, ry)
        payload = {
            "uid": f"region:{rx}:{ry}", "region_x": rx, "region_y": ry, "version": self.version,
            "dominant_biome": dominant, "biome_mix": mix,
            "mean_elevation": sum(elevations) // len(elevations), "mean_moisture": mean_m,
            "mean_temperature": mean_t, "relief": relief, "settlement_present": present,
            "settlement_anchor": list(anchor) if anchor else None, "settlement_score": settlement_score,
            "settlement_archetype": archetype, "control_potential": control,
            "wilderness_tags": tags, "site_potential": site_potential,
            "roads": [asdict(x) for x in roads], "waters": [asdict(x) for x in waters],
            "carrying_capacity": profile.carrying_capacity if profile is not None else 0,
            "settlement_rank_hint": profile.rank_hint if profile is not None else "homestead",
            "settlement_morphology": profile.morphology if profile is not None else "organic",
            "route_value": profile.route_value if profile is not None else 0,
            "defensibility": profile.defensibility if profile is not None else 0,
            "crossing_value": profile.crossing_value if profile is not None else 0,
            "culture_seed": profile.culture_seed if profile is not None else 0,
            "prominent_faction_seed": profile.prominent_faction_seed if profile is not None else False,
        }
        payload["fingerprint"] = canonical_hash(payload)
        return RegionBlockPlan.from_dict(payload)

    def read_prepared(self, rx: int, ry: int) -> RegionBlockPlan | None:
        """Read a validated existing plan without generation or cache mutation."""
        key = (int(rx), int(ry))
        if key in self._cache:
            return self._cache[key]
        loader = getattr(self.cache_source, "load_generated_regional_plan", None)
        if callable(loader):
            raw = loader(key[0], key[1], self.version)
            if raw:
                try:
                    plan = RegionBlockPlan.from_dict(raw)
                    check = plan.to_dict(); fingerprint = check.pop("fingerprint", "")
                    if (plan.region_x == key[0] and plan.region_y == key[1]
                            and plan.version == self.version and fingerprint == canonical_hash(check)):
                        return plan
                except (KeyError, TypeError, ValueError):
                    pass
        return None

    def plan(self, rx: int, ry: int, *, persist: bool = True, refresh: bool = False) -> RegionBlockPlan:
        key = (int(rx), int(ry))
        prepared = None if refresh else self.read_prepared(*key)
        if prepared is not None:
            self._cache[key] = prepared
            return prepared
        plan = self._generate(*key)
        self._cache[key] = plan
        if persist:
            storer = getattr(self.cache_source, "store_generated_regional_plan", None)
            if callable(storer):
                storer(key[0], key[1], self.version, plan.to_dict())
                commit = getattr(self.cache_source, "commit_generated", None)
                if callable(commit): commit()
        return plan

    def anchor_for(self, rx: int, ry: int) -> tuple[int, int] | None:
        return self.plan(rx, ry).settlement_anchor
