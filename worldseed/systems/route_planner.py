from __future__ import annotations

from dataclasses import asdict, dataclass
import heapq

from worldseed.config import ROUTEGEN_VERSION, CHUNK_SIZE, REGION_CHUNKS
from worldseed.core.canonical import canonical_hash
from worldseed.core.coords import WorldPos
from worldseed.core.rng import hash_u64
from worldseed.systems.regional_civilization import (
    FACTION_REGION_SPAN,
    RegionalCivilizationPlanner,
)

REGION_SIZE = CHUNK_SIZE * REGION_CHUNKS
SEA_LEVEL = 23800


@dataclass(frozen=True, slots=True)
class StrategicRoadExit:
    direction: str
    offset: int
    road_class: str
    route_uid: str


@dataclass(slots=True)
class RegionalRoutePlan:
    uid: str
    version: int
    origin_region: tuple[int, int]
    destination_region: tuple[int, int]
    road_class: str
    region_path: list[tuple[int, int]]
    cost: int
    rationale: str
    fingerprint: str = ""

    def to_dict(self) -> dict:
        payload = {
            "uid": self.uid,
            "version": self.version,
            "origin_region": list(self.origin_region),
            "destination_region": list(self.destination_region),
            "road_class": self.road_class,
            "region_path": [list(p) for p in self.region_path],
            "cost": self.cost,
            "rationale": self.rationale,
        }
        payload["fingerprint"] = self.fingerprint or canonical_hash(payload)
        return payload

    @classmethod
    def from_dict(cls, raw: dict) -> "RegionalRoutePlan":
        return cls(
            uid=str(raw["uid"]),
            version=int(raw["version"]),
            origin_region=tuple(map(int, raw["origin_region"])),
            destination_region=tuple(map(int, raw["destination_region"])),
            road_class=str(raw.get("road_class", "trail")),
            region_path=[tuple(map(int, p)) for p in raw.get("region_path", ())],
            cost=int(raw.get("cost", 0)),
            rationale=str(raw.get("rationale", "")),
            fingerprint=str(raw.get("fingerprint", "")),
        )


class RegionalRoutePlanner:
    """Sparse strategic road network for deterministic civilization regions.

    Each faction-domain receives a terrain-cost MST-like backbone plus a small
    number of redundant links. Neighboring faction seats receive trunk links.
    Only region paths and crossings are planned here; tile-level road geometry
    remains a later refinement consumer.
    """

    def __init__(
        self,
        world,
        civilization: RegionalCivilizationPlanner | None = None,
        version: int | None = None,
    ):
        self.world = world
        self.generator = world.generator
        self.seed = world.generator.world_seed
        self.civilization = civilization or RegionalCivilizationPlanner(world)
        if version is None:
            version = getattr(world, "routegen_version", ROUTEGEN_VERSION)
        self.version = int(version)
        self.cache_source = world.delta_source
        self._route_cache: dict[str, RegionalRoutePlan] = {}
        self._domain_cache: dict[tuple[int, int], tuple[RegionalRoutePlan, ...]] = {}
        self._path_cache: dict[tuple[tuple[int, int], tuple[int, int]], tuple[list[tuple[int, int]], int] | None] = {}

    @staticmethod
    def _ordered_pair(a: tuple[int, int], b: tuple[int, int]):
        return (a, b) if a <= b else (b, a)

    def _step_cost(self, rx: int, ry: int) -> int | None:
        p = self.civilization.potential(rx, ry)
        if p.land_ratio < 25:
            return None
        return 10 + p.ruggedness // 4 + max(0, 55 - p.route_value) // 3 + p.coast_ratio // 14

    def _region_path(self, a: tuple[int, int], b: tuple[int, int]) -> tuple[list[tuple[int, int]], int] | None:
        key = self._ordered_pair(a, b)
        if key in self._path_cache:
            cached = self._path_cache[key]
            if cached is None:
                return None
            path, cost = cached
            return (list(reversed(path)) if a != key[0] else list(path), cost)

        min_x, max_x = min(a[0], b[0]) - 2, max(a[0], b[0]) + 2
        min_y, max_y = min(a[1], b[1]) - 2, max(a[1], b[1]) + 2
        queue = [(0, 0, a[1], a[0])]
        best = {a: 0}
        came: dict[tuple[int, int], tuple[int, int]] = {}
        goal = b
        while queue:
            _, cost, y, x = heapq.heappop(queue)
            node = (x, y)
            if cost != best.get(node):
                continue
            if node == goal:
                path = [node]
                while node in came:
                    node = came[node]
                    path.append(node)
                path.reverse()
                canonical = path if a == key[0] else list(reversed(path))
                self._path_cache[key] = (canonical, cost)
                return path, cost
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nxt = (x + dx, y + dy)
                if not (min_x <= nxt[0] <= max_x and min_y <= nxt[1] <= max_y):
                    continue
                step = self._step_cost(*nxt)
                if step is None and nxt != goal:
                    continue
                step = 18 if step is None else step
                ncost = cost + step
                if ncost >= best.get(nxt, 1 << 60):
                    continue
                best[nxt] = ncost
                came[nxt] = node
                heuristic = (abs(goal[0] - nxt[0]) + abs(goal[1] - nxt[1])) * 9
                heapq.heappush(queue, (ncost + heuristic, ncost, nxt[1], nxt[0]))
        self._path_cache[key] = None
        return None

    def _road_class(self, a, b, rationale: str) -> str:
        ranks = {a.rank_hint, b.rank_hint}
        if rationale == "inter_faction_trunk" and ("city" in ranks or "town" in ranks):
            return "maintained_road"
        if "city" in ranks or "town" in ranks:
            return "road"
        return "trail"

    def _build_route(self, a, b, rationale: str) -> RegionalRoutePlan | None:
        aa = (a.region_x, a.region_y)
        bb = (b.region_x, b.region_y)
        ordered = self._ordered_pair(aa, bb)
        uid = f"route:{canonical_hash({'version': self.version, 'a': ordered[0], 'b': ordered[1], 'kind': rationale})[:24]}"
        cached = self._route_cache.get(uid)
        if cached is not None:
            return cached
        prepared = self.read_prepared(uid)
        if prepared is not None:
            return prepared
        routed = self._region_path(ordered[0], ordered[1])
        if routed is None:
            return None
        path, cost = routed
        road_class = self._road_class(a, b, rationale)
        payload = {
            "uid": uid, "version": self.version,
            "origin_region": ordered[0], "destination_region": ordered[1],
            "road_class": road_class, "region_path": path, "cost": cost,
            "rationale": rationale,
        }
        plan = RegionalRoutePlan(**payload)
        check = plan.to_dict(); check.pop("fingerprint", None)
        plan.fingerprint = canonical_hash(check)
        self._route_cache[uid] = plan
        return plan

    def _internal_routes(self, domain_x: int, domain_y: int) -> list[RegionalRoutePlan]:
        nodes = list(self.civilization.settlements_in_domain(domain_x, domain_y))
        if len(nodes) < 2:
            return []
        candidates = []
        for i, a in enumerate(nodes):
            for b in nodes[i + 1:]:
                routed = self._region_path((a.region_x, a.region_y), (b.region_x, b.region_y))
                if routed is None:
                    continue
                path, cost = routed
                distance = abs(a.region_x - b.region_x) + abs(a.region_y - b.region_y)
                utility = cost + distance * 3 - (a.route_value + b.route_value) // 8
                candidates.append((utility, cost, a.region_y, a.region_x, b.region_y, b.region_x, a, b))
        candidates.sort(key=lambda row: row[:6])

        parent = {(n.region_x, n.region_y): (n.region_x, n.region_y) for n in nodes}
        degree = {key: 0 for key in parent}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra == rb:
                return False
            parent[rb] = ra
            return True

        chosen: list[RegionalRoutePlan] = []
        chosen_pairs = set()
        for _, _, _, _, _, _, a, b in candidates:
            ka, kb = (a.region_x, a.region_y), (b.region_x, b.region_y)
            if not union(ka, kb):
                continue
            route = self._build_route(a, b, "faction_backbone")
            if route is None:
                continue
            chosen.append(route)
            chosen_pairs.add(self._ordered_pair(ka, kb))
            degree[ka] += 1; degree[kb] += 1

        # One bounded layer of useful cycles makes roads resilient without
        # degenerating into a complete graph.
        redundant_budget = max(1, len(nodes) // 3)
        for _, _, _, _, _, _, a, b in candidates:
            if redundant_budget <= 0:
                break
            ka, kb = (a.region_x, a.region_y), (b.region_x, b.region_y)
            pair = self._ordered_pair(ka, kb)
            if pair in chosen_pairs or degree[ka] >= 4 or degree[kb] >= 4:
                continue
            if abs(ka[0] - kb[0]) + abs(ka[1] - kb[1]) > 5:
                continue
            route = self._build_route(a, b, "redundant_trade_link")
            if route is None:
                continue
            chosen.append(route)
            chosen_pairs.add(pair)
            degree[ka] += 1; degree[kb] += 1
            redundant_budget -= 1
        return chosen

    def domain_routes(self, domain_x: int, domain_y: int, *, persist: bool = False) -> tuple[RegionalRoutePlan, ...]:
        key = (int(domain_x), int(domain_y))
        if key in self._domain_cache:
            rows = self._domain_cache[key]
        else:
            rows = self._internal_routes(*key)
            current_seed = self.civilization.faction_seed_for_region(
                key[0] * FACTION_REGION_SPAN, key[1] * FACTION_REGION_SPAN
            )
            current_nodes = self.civilization.settlements_in_domain(*key)
            if current_nodes:
                current = self.civilization.potential(current_seed.seat_region_x, current_seed.seat_region_y)
                for dx, dy in ((1, 0), (0, 1)):
                    neighbor_key = (key[0] + dx, key[1] + dy)
                    neighbor_nodes = self.civilization.settlements_in_domain(*neighbor_key)
                    if not neighbor_nodes:
                        continue
                    neighbor_seed = self.civilization.faction_seed_for_region(
                        neighbor_key[0] * FACTION_REGION_SPAN,
                        neighbor_key[1] * FACTION_REGION_SPAN,
                    )
                    neighbor = self.civilization.potential(
                        neighbor_seed.seat_region_x, neighbor_seed.seat_region_y
                    )
                    trunk = self._build_route(current, neighbor, "inter_faction_trunk")
                    if trunk is not None:
                        rows.append(trunk)
            unique = {row.uid: row for row in rows}
            rows = tuple(unique[k] for k in sorted(unique))
            self._domain_cache[key] = rows
        if persist:
            storer = getattr(self.cache_source, "store_generated_route_plan", None)
            if callable(storer):
                for row in rows:
                    storer(row.uid, self.version, row.to_dict())
                commit = getattr(self.cache_source, "commit_generated", None)
                if callable(commit):
                    commit()
        return tuple(rows)

    def read_prepared(self, route_uid: str) -> RegionalRoutePlan | None:
        route_uid = str(route_uid)
        if route_uid in self._route_cache:
            return self._route_cache[route_uid]
        loader = getattr(self.cache_source, "load_generated_route_plan", None)
        if not callable(loader):
            return None
        raw = loader(route_uid, self.version)
        if not raw:
            return None
        try:
            check = dict(raw); fingerprint = str(check.pop("fingerprint", ""))
            if fingerprint != canonical_hash(check):
                return None
            plan = RegionalRoutePlan.from_dict(raw)
            if plan.uid != route_uid or plan.version != self.version:
                return None
            self._route_cache[route_uid] = plan
            return plan
        except (KeyError, TypeError, ValueError):
            return None

    @staticmethod
    def _direction(a: tuple[int, int], b: tuple[int, int]) -> str:
        dx, dy = b[0] - a[0], b[1] - a[1]
        if (dx, dy) == (1, 0):
            return "east"
        if (dx, dy) == (-1, 0):
            return "west"
        if (dx, dy) == (0, 1):
            return "south"
        if (dx, dy) == (0, -1):
            return "north"
        raise ValueError("Route path contains a non-cardinal regional edge")

    def _boundary_offset(self, a: tuple[int, int], b: tuple[int, int], route_uid: str) -> int:
        # Score several actual boundary samples. This is still reconstructable
        # base geography, so querying a road never depends on hydrology cache order.
        horizontal = a[1] == b[1]
        offsets = tuple(range(64, REGION_SIZE - 63, 48))
        rows = []
        for offset in offsets:
            if horizontal:
                boundary_x = max(a[0], b[0]) * REGION_SIZE
                y = a[1] * REGION_SIZE + offset
                p1, p2 = WorldPos(boundary_x - 8, y, 0), WorldPos(boundary_x + 8, y, 0)
            else:
                boundary_y = max(a[1], b[1]) * REGION_SIZE
                x = a[0] * REGION_SIZE + offset
                p1, p2 = WorldPos(x, boundary_y - 8, 0), WorldPos(x, boundary_y + 8, 0)
            f1, f2 = self.generator.sample_fields(p1), self.generator.sample_fields(p2)
            water = 1000 if int(f1.elevation) < SEA_LEVEL or int(f2.elevation) < SEA_LEVEL else 0
            grade = abs(int(f1.elevation) - int(f2.elevation)) // 120
            wet = (int(f1.moisture) + int(f2.moisture)) // 8192
            lo, hi = self._ordered_pair(a, b)
            tie = int(hash_u64(
                self.seed, "route-boundary", route_uid,
                lo[0], lo[1], hi[0], hi[1], offset,
            ) % 1000)
            rows.append((water + grade + wet, tie, offset))
        return min(rows)[2]

    def road_exits_for_region(self, rx: int, ry: int, *, persist: bool = False) -> tuple[StrategicRoadExit, ...]:
        region = (int(rx), int(ry))
        domain = self.civilization.faction_domain(*region)
        routes: dict[str, RegionalRoutePlan] = {}
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for route in self.domain_routes(domain[0] + dx, domain[1] + dy, persist=False):
                    if region in route.region_path:
                        routes[route.uid] = route
        if persist and routes:
            storer = getattr(self.cache_source, "store_generated_route_plan", None)
            if callable(storer):
                for route in routes.values():
                    storer(route.uid, self.version, route.to_dict())
                commit = getattr(self.cache_source, "commit_generated", None)
                if callable(commit):
                    commit()

        exits = []
        for route in routes.values():
            path = route.region_path
            for index, cell in enumerate(path):
                if cell != region:
                    continue
                for neighbor_index in (index - 1, index + 1):
                    if not (0 <= neighbor_index < len(path)):
                        continue
                    neighbor = path[neighbor_index]
                    direction = self._direction(region, neighbor)
                    offset = self._boundary_offset(region, neighbor, route.uid)
                    exits.append(StrategicRoadExit(direction, offset, route.road_class, route.uid))
        unique = {(e.direction, e.offset, e.route_uid): e for e in exits}
        rank = {"maintained_road": 0, "road": 1, "trail": 2, "path": 3}
        ordered = sorted(unique.values(), key=lambda e: (rank.get(e.road_class, 9), e.direction, e.offset, e.route_uid))
        return tuple(ordered[:12])
