from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from worldseed.config import CHUNK_SIZE, REGION_CHUNKS
from worldseed.core.coords import WorldPos
from worldseed.core.rng import hash_u64

REGION_SIZE = CHUNK_SIZE * REGION_CHUNKS
SEA_LEVEL = 23800
FACTION_REGION_SPAN = 6

FACTION_TRADITIONS = {
    "river_compact": {
        "suffix": "Compact",
        "motto": "Roads, markets, and safe crossings bind the realm.",
        "laws": (("theft", 82), ("assault", 72), ("trespass", 54), ("tax", 9)),
        "values": ("trade", "hospitality", "order"),
    },
    "stone_march": {
        "suffix": "March",
        "motto": "Hold the passes. Keep the roads.",
        "laws": (("theft", 72), ("assault", 90), ("trespass", 78), ("tax", 8)),
        "values": ("honor", "craft", "order"),
    },
    "green_covenant": {
        "suffix": "Covenant",
        "motto": "Land and water are inherited, not consumed.",
        "laws": (("theft", 76), ("assault", 70), ("trespass", 42), ("tax", 6)),
        "values": ("stewardship", "ancestry", "hospitality"),
    },
    "freeholds": {
        "suffix": "Freeholds",
        "motto": "No distant hall owns a free hearth.",
        "laws": (("theft", 66), ("assault", 74), ("trespass", 28), ("tax", 4)),
        "values": ("freedom", "craft", "trade"),
    },
    "scholars_concord": {
        "suffix": "Concord",
        "motto": "Measure first; build what can endure.",
        "laws": (("theft", 80), ("assault", 68), ("trespass", 48), ("tax", 10)),
        "values": ("scholarship", "craft", "order"),
    },
}

_FACTION_ROOTS = (
    "Alder", "Veyr", "Caldrin", "Morrow", "Thorn", "Aurel",
    "Harth", "Velan", "Demer", "Oris", "Rathen", "Selvar",
)


@dataclass(frozen=True, slots=True)
class CivilizationRegionPotential:
    region_x: int
    region_y: int
    capacity: int
    land_ratio: int
    coast_ratio: int
    arable: int
    timber: int
    stone: int
    water: int
    route_value: int
    defensibility: int
    ruggedness: int
    priority: int
    settlement_present: bool
    rank_hint: str
    archetype: str
    regional_role: str


@dataclass(frozen=True, slots=True)
class FactionSeed:
    uid: str
    domain_x: int
    domain_y: int
    seat_region_x: int
    seat_region_y: int
    tradition: str
    name: str
    motto: str
    laws: tuple[tuple[str, int], ...]
    values: tuple[str, ...]


class RegionalCivilizationPlanner:
    """Deterministic terrain-first potential for regional civilization.

    This is deliberately cheaper than physical settlement planning. It may be
    queried before hydrology exists (for new-world origin selection), so it only
    consumes immutable base geography/climate fields. Hydrology, crossings and
    exact local opportunities refine the final anchor later in RegionBlockPlanner.
    """

    MIN_CAPACITY = 36

    def __init__(self, world, version: int = 1):
        self.world = world
        self.generator = world.generator
        self.seed = world.generator.world_seed
        self.version = int(version)
        self._raw_cache: dict[tuple[int, int], dict[str, int]] = {}
        self._potential_cache: dict[tuple[int, int], CivilizationRegionPotential] = {}
        self._faction_cache: dict[tuple[int, int], FactionSeed] = {}

    @staticmethod
    def _score(value: int) -> int:
        return max(0, min(100, int(value)))

    def _raw(self, rx: int, ry: int) -> dict[str, int]:
        key = (int(rx), int(ry))
        cached = self._raw_cache.get(key)
        if cached is not None:
            return cached
        x0, y0 = key[0] * REGION_SIZE, key[1] * REGION_SIZE
        rows = []
        for gy in range(1, 6):
            for gx in range(1, 6):
                p = WorldPos(x0 + gx * REGION_SIZE // 6, y0 + gy * REGION_SIZE // 6, 0)
                f = self.generator.sample_fields(p)
                elev = int(f.elevation)
                moisture = int(f.moisture) * 100 // 65535
                temperature = int(f.temperature) * 100 // 65535
                fertility = int(f.fertility) * 100 // 65535
                rows.append((elev, moisture, temperature, fertility))

        land = [row for row in rows if row[0] >= SEA_LEVEL]
        land_ratio = len(land) * 100 // len(rows)
        coast_ratio = sum(1 for elev, *_ in rows if SEA_LEVEL <= elev < 28500) * 100 // len(rows)
        if not land:
            result = {
                "capacity": 0, "land_ratio": 0, "coast_ratio": coast_ratio,
                "arable": 0, "timber": 0, "stone": 0, "water": 100,
                "route_value": 0, "defensibility": 0, "ruggedness": 0,
                "priority": int(hash_u64(self.seed, "civilization-priority", key[0], key[1]) % 1000000),
            }
            self._raw_cache[key] = result
            return result

        mean_elevation = sum(r[0] for r in land) // len(land)
        mean_moisture = sum(r[1] for r in land) // len(land)
        mean_temperature = sum(r[2] for r in land) // len(land)
        mean_fertility = sum(r[3] for r in land) // len(land)
        temperate = self._score(100 - abs(mean_temperature - 55) * 2)
        relief = max(r[0] for r in rows) - min(r[0] for r in rows)
        ruggedness = self._score(relief * 100 // 15000)
        arable = self._score(mean_fertility * temperate * land_ratio // 10000)
        timber = self._score(mean_moisture * temperate // 100)
        stone = self._score(ruggedness * 3 // 4 + max(0, mean_elevation - 36000) * 100 // 28000)
        water = self._score(mean_moisture * 2 // 3 + coast_ratio // 2 + (12 if coast_ratio else 0))
        route_value = self._score(88 - ruggedness * 2 // 3 - max(0, 60 - land_ratio) // 2 + temperate // 5)
        defensibility = self._score(ruggedness * 2 // 3 + max(0, mean_elevation - 33000) * 100 // 32000)
        capacity = (
            arable * 3 + water * 2 + timber + stone + route_value * 2 + temperate * 2
        ) // 11
        capacity = self._score(capacity - max(0, 55 - land_ratio) // 2)
        priority = capacity * 1000000 + int(
            hash_u64(self.seed, "civilization-priority", key[0], key[1]) % 1000000
        )
        result = {
            "capacity": capacity, "land_ratio": land_ratio, "coast_ratio": coast_ratio,
            "arable": arable, "timber": timber, "stone": stone, "water": water,
            "route_value": route_value, "defensibility": defensibility,
            "ruggedness": ruggedness, "priority": priority,
        }
        self._raw_cache[key] = result
        return result

    def potential(self, rx: int, ry: int) -> CivilizationRegionPotential:
        key = (int(rx), int(ry))
        cached = self._potential_cache.get(key)
        if cached is not None:
            return cached
        raw = self._raw(*key)
        viable = raw["capacity"] >= self.MIN_CAPACITY and raw["land_ratio"] >= 45
        settlement_present = False
        if viable:
            best = raw["priority"]
            for ny in range(key[1] - 1, key[1] + 2):
                for nx in range(key[0] - 1, key[0] + 2):
                    if (nx, ny) == key:
                        continue
                    other = self._raw(nx, ny)
                    if other["capacity"] >= self.MIN_CAPACITY and other["land_ratio"] >= 45:
                        best = max(best, other["priority"])
            settlement_present = raw["priority"] == best

        if raw["capacity"] >= 76:
            rank = "city"
        elif raw["capacity"] >= 63:
            rank = "town"
        elif raw["capacity"] >= 48:
            rank = "village"
        else:
            rank = "hamlet"

        if raw["coast_ratio"] >= 18 and raw["water"] >= 55:
            archetype = "fishing"
        elif raw["stone"] >= 68 and raw["defensibility"] >= 42:
            archetype = "mining"
        elif raw["timber"] >= 68 and raw["arable"] < 58:
            archetype = "forest"
        elif raw["arable"] >= 58:
            archetype = "agrarian"
        elif raw["water"] >= 60 and raw["route_value"] >= 62:
            archetype = "river_market"
        else:
            archetype = "frontier"

        if rank == "city":
            role = "regional_seat"
        elif rank == "town" and raw["route_value"] >= 62:
            role = "market_hub"
        elif archetype in {"mining", "forest", "fishing"}:
            role = "resource_hub"
        elif archetype == "agrarian":
            role = "agrarian_core"
        else:
            role = "frontier_hold"

        value = CivilizationRegionPotential(
            key[0], key[1], raw["capacity"], raw["land_ratio"], raw["coast_ratio"],
            raw["arable"], raw["timber"], raw["stone"], raw["water"],
            raw["route_value"], raw["defensibility"], raw["ruggedness"],
            raw["priority"], settlement_present, rank, archetype, role,
        )
        self._potential_cache[key] = value
        return value

    def population_for_region(self, rx: int, ry: int) -> int:
        p = self.potential(rx, ry)
        jitter = int(hash_u64(self.seed, "civilization-population", int(rx), int(ry)) % 23)
        if p.rank_hint == "city":
            return 190 + max(0, p.capacity - 76) * 8 + jitter
        if p.rank_hint == "town":
            return 80 + max(0, p.capacity - 63) * 5 + jitter
        if p.rank_hint == "village":
            return 28 + max(0, p.capacity - 48) * 2 + jitter // 2
        return 10 + max(0, p.capacity - self.MIN_CAPACITY) + jitter // 3

    def faction_domain(self, rx: int, ry: int) -> tuple[int, int]:
        return int(rx) // FACTION_REGION_SPAN, int(ry) // FACTION_REGION_SPAN

    def settlements_in_domain(self, domain_x: int, domain_y: int) -> tuple[CivilizationRegionPotential, ...]:
        x0, y0 = int(domain_x) * FACTION_REGION_SPAN, int(domain_y) * FACTION_REGION_SPAN
        rows = [
            self.potential(rx, ry)
            for ry in range(y0, y0 + FACTION_REGION_SPAN)
            for rx in range(x0, x0 + FACTION_REGION_SPAN)
        ]
        return tuple(sorted((p for p in rows if p.settlement_present), key=lambda p: (p.region_y, p.region_x)))

    def faction_seed_for_region(self, rx: int, ry: int) -> FactionSeed:
        domain = self.faction_domain(rx, ry)
        cached = self._faction_cache.get(domain)
        if cached is not None:
            return cached
        nodes = self.settlements_in_domain(*domain)
        if nodes:
            seat = max(nodes, key=lambda p: (p.capacity, p.route_value, p.priority))
        else:
            x0, y0 = domain[0] * FACTION_REGION_SPAN, domain[1] * FACTION_REGION_SPAN
            candidates = [self.potential(x, y) for y in range(y0, y0 + FACTION_REGION_SPAN) for x in range(x0, x0 + FACTION_REGION_SPAN)]
            seat = max(candidates, key=lambda p: (p.capacity, p.priority))

        traditions = tuple(FACTION_TRADITIONS)
        tradition = traditions[int(hash_u64(self.seed, "faction-tradition", domain[0], domain[1]) % len(traditions))]
        profile = FACTION_TRADITIONS[tradition]
        root = _FACTION_ROOTS[int(hash_u64(self.seed, "faction-root", domain[0], domain[1]) % len(_FACTION_ROOTS))]
        name = f"The {root} {profile['suffix']}"
        value = FactionSeed(
            uid=f"faction:{domain[0]}:{domain[1]}",
            domain_x=domain[0], domain_y=domain[1],
            seat_region_x=seat.region_x, seat_region_y=seat.region_y,
            tradition=tradition, name=name, motto=str(profile["motto"]),
            laws=tuple(profile["laws"]), values=tuple(profile["values"]),
        )
        self._faction_cache[domain] = value
        return value
