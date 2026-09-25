from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
import heapq
from typing import Iterable, Mapping

from worldseed.config import SETTLEMENT_PLAN_VERSION
from worldseed.core.canonical import canonical_hash
from worldseed.core.coords import WorldPos
from worldseed.world.regional_plan import (
    LandUseParcel,
    RoadSegmentPlan,
    RoomPlanState,
    SettlementPlanState,
    StructurePiecePlan,
    StructurePlanState,
    stable_plan_uid,
)

CARDINALS = ((1, 0), (-1, 0), (0, 1), (0, -1))

SETTLEMENT_RANKS: dict[str, tuple[int, int]] = {
    "homestead": (1, 5),
    "hamlet": (5, 20),
    "village": (15, 60),
    "town": (50, 180),
    "city": (150, 800),
}


@dataclass(frozen=True, slots=True)
class BuildingAnalysis:
    structure_uid: str
    enclosed: bool
    footprint_area: int
    interior_area: int
    roof_percent: int
    building_type: str
    rooms: tuple[RoomPlanState, ...]
    exterior_doorways: tuple[tuple[int, int], ...]


def _bounds(cells: set[tuple[int, int]], margin: int = 1) -> tuple[int, int, int, int]:
    if not cells:
        return 0, 0, 0, 0
    xs = [p[0] for p in cells]
    ys = [p[1] for p in cells]
    return min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin


def _flood(
    starts: Iterable[tuple[int, int]],
    *,
    blocked: set[tuple[int, int]],
    bounds: tuple[int, int, int, int],
    allowed: set[tuple[int, int]] | None = None,
) -> set[tuple[int, int]]:
    left, top, right, bottom = bounds
    seen: set[tuple[int, int]] = set()
    queue = deque()
    for start in starts:
        if start in blocked:
            continue
        x, y = start
        if not (left <= x <= right and top <= y <= bottom):
            continue
        if allowed is not None and start not in allowed:
            continue
        if start not in seen:
            seen.add(start)
            queue.append(start)
    while queue:
        x, y = queue.popleft()
        for dx, dy in CARDINALS:
            p = (x + dx, y + dy)
            if p in seen or p in blocked:
                continue
            px, py = p
            if not (left <= px <= right and top <= py <= bottom):
                continue
            if allowed is not None and p not in allowed:
                continue
            seen.add(p)
            queue.append(p)
    return seen


def _room_kind(tags: set[str]) -> str:
    if tags & {"forge", "smithy", "anvil", "bellows"}:
        return "smithy"
    if tags & {"oven", "hearth", "kitchen", "cooking"}:
        return "kitchen"
    if tags & {"bed", "sleep"}:
        return "bedroom"
    if tags & {"merchant", "shop", "market"}:
        return "shop"
    if tags & {"healing", "clinic", "medicine", "apothecary"}:
        return "clinic"
    if tags & {"guard", "defense", "watch"}:
        return "watch"
    if tags & {"writing", "archive", "school", "study"}:
        return "study"
    if tags & {"storage", "stockpile", "granary"}:
        return "storage"
    if tags & {"workshop", "station", "crafting", "loom", "carpentry", "tanning"}:
        return "workshop"
    if tags & {"worship", "shrine", "ritual"}:
        return "sanctuary"
    return "room"


def _building_type(room_kinds: list[str], all_tags: set[str]) -> str:
    kinds = set(room_kinds)
    if "smithy" in kinds:
        return "smithy"
    if "shop" in kinds:
        return "market"
    if "clinic" in kinds:
        return "clinic"
    if "watch" in kinds:
        return "watchhouse"
    if "study" in kinds:
        return "archive"
    if "sanctuary" in kinds:
        return "shrine"
    if "workshop" in kinds:
        return "workshop"
    if "bedroom" in kinds:
        return "residence"
    if all_tags & {"stable", "livestock"}:
        return "stable"
    if "storage" in kinds and len(kinds) == 1:
        return "storehouse"
    return "building"


def analyze_building(
    structure_uid: str,
    *,
    wall_cells: Iterable[tuple[int, int]],
    door_cells: Iterable[tuple[int, int]] = (),
    roof_cells: Iterable[tuple[int, int]] = (),
    floor_cells: Iterable[tuple[int, int]] = (),
    fixture_tags: Mapping[tuple[int, int], Iterable[str]] | None = None,
) -> BuildingAnalysis:
    """Detect enclosure, rooms and functional type from physical building cells.

    Exterior detection treats walls and doors as the shell. Room segmentation
    also treats doors as boundaries, so larger buildings with interior partitions
    retain distinct rooms while doorway cells keep their adjacency explicit.
    """
    walls = {tuple(map(int, p)) for p in wall_cells}
    doors = {tuple(map(int, p)) for p in door_cells}
    roofs = {tuple(map(int, p)) for p in roof_cells}
    floors = {tuple(map(int, p)) for p in floor_cells}
    fixtures = {
        tuple(map(int, p)): {str(tag) for tag in tags}
        for p, tags in (fixture_tags or {}).items()
    }
    architecture = walls | doors | floors | set(fixtures)
    if not architecture:
        return BuildingAnalysis(str(structure_uid), False, 0, 0, 0, "open_site", (), ())

    bounds = _bounds(architecture, margin=1)
    left, top, right, bottom = bounds
    perimeter = {
        (x, y)
        for x in range(left, right + 1)
        for y in range(top, bottom + 1)
        if x in (left, right) or y in (top, bottom)
    }
    shell = walls | doors
    exterior = _flood(perimeter, blocked=shell, bounds=bounds)
    bounded = {
        (x, y)
        for x in range(left + 1, right)
        for y in range(top + 1, bottom)
        if (x, y) not in shell and (x, y) not in exterior
    }
    interior = bounded & floors if floors else bounded
    if floors:
        interior |= {p for p in fixtures if p in bounded}

    enclosed = bool(interior)
    room_cells_remaining = set(interior)
    components: list[set[tuple[int, int]]] = []
    while room_cells_remaining:
        start = min(room_cells_remaining)
        component = _flood([start], blocked=shell, bounds=bounds, allowed=room_cells_remaining)
        if not component:
            component = {start}
        room_cells_remaining -= component
        components.append(component)

    room_rows = []
    exterior_doorways: set[tuple[int, int]] = set()
    for component in components:
        doorway_cells: set[tuple[int, int]] = set()
        tags: set[str] = set()
        for cell in component:
            tags.update(fixtures.get(cell, ()))
            x, y = cell
            for dx, dy in CARDINALS:
                door = (x + dx, y + dy)
                if door not in doors:
                    continue
                doorway_cells.add(door)
                if (door[0] + dx, door[1] + dy) in exterior:
                    exterior_doorways.add(door)
        room_rows.append((min(component), component, doorway_cells, tags))

    room_rows.sort(key=lambda row: (row[0][1], row[0][0], len(row[1])))
    rooms: list[RoomPlanState] = []
    all_tags: set[str] = set()
    for _, component, doorway_cells, tags in room_rows:
        all_tags.update(tags)
        ordered_cells = sorted(component, key=lambda p: (p[1], p[0]))
        ordered_doors = sorted(doorway_cells, key=lambda p: (p[1], p[0]))
        roofed = sum(1 for p in component if p in roofs)
        roof_percent = 0 if not component else roofed * 100 // len(component)
        kind = _room_kind(tags)
        rooms.append(RoomPlanState(
            uid=stable_plan_uid("room", str(structure_uid), kind, ordered_cells),
            structure_plan_id=str(structure_uid),
            kind=kind,
            cells=ordered_cells,
            doorway_cells=ordered_doors,
            area=len(component),
            enclosed=True,
            sheltered=roof_percent >= 60,
            roof_percent=roof_percent,
        ))

    interior_roofed = sum(1 for p in interior if p in roofs)
    roof_percent = 0 if not interior else interior_roofed * 100 // len(interior)
    return BuildingAnalysis(
        structure_uid=str(structure_uid),
        enclosed=enclosed,
        footprint_area=len(architecture | interior),
        interior_area=len(interior),
        roof_percent=roof_percent,
        building_type=_building_type([room.kind for room in rooms], all_tags) if enclosed else "open_site",
        rooms=tuple(rooms),
        exterior_doorways=tuple(sorted(exterior_doorways, key=lambda p: (p[1], p[0]))),
    )


def settlement_piece_groups(registry) -> dict[str, tuple]:
    """Return deterministic category buckets consumed by settlement generation."""
    groups: dict[str, list] = {}
    for piece in registry.settlement_pieces.values():
        groups.setdefault(piece.category, []).append(piece)
    return {
        category: tuple(sorted(values, key=lambda piece: piece.id))
        for category, values in sorted(groups.items())
    }


@dataclass(slots=True)
class SettlementSkeleton:
    """Persistent, reconstructable Phase-8 settlement skeleton.

    The skeleton owns spatial planning only: streets, gateways, commons and
    land-use parcels. Population/economy remain in the simulation ledger.
    """
    plan: SettlementPlanState
    roads: list[RoadSegmentPlan] = field(default_factory=list)
    parcels: list[LandUseParcel] = field(default_factory=list)
    structures: list[StructurePlanState] = field(default_factory=list)
    rooms: list[RoomPlanState] = field(default_factory=list)
    pieces: list[StructurePiecePlan] = field(default_factory=list)
    fingerprint: str = ""

    def to_dict(self) -> dict:
        payload = {
            "plan": asdict(self.plan),
            "roads": [asdict(row) for row in self.roads],
            "parcels": [asdict(row) for row in self.parcels],
            "structures": [asdict(row) for row in self.structures],
            "rooms": [asdict(row) for row in self.rooms],
            "pieces": [asdict(row) for row in self.pieces],
        }
        payload["fingerprint"] = self.fingerprint or canonical_hash(payload)
        return payload

    @classmethod
    def from_dict(cls, raw: dict) -> "SettlementSkeleton":
        plan_raw = dict(raw["plan"])
        if plan_raw.get("atlas_bounds") is not None:
            plan_raw["atlas_bounds"] = tuple(int(v) for v in plan_raw["atlas_bounds"])
        plan_raw["common_cells"] = [tuple(map(int, p)) for p in plan_raw.get("common_cells", ())]
        plan_raw["gateway_cells"] = [tuple(map(int, p)) for p in plan_raw.get("gateway_cells", ())]
        plan = SettlementPlanState(**plan_raw)
        roads = []
        for item in raw.get("roads", ()):
            row = dict(item)
            row["polyline"] = [tuple(map(int, p)) for p in row.get("polyline", ())]
            row["chunk_corridor"] = [tuple(map(int, p)) for p in row.get("chunk_corridor", ())]
            roads.append(RoadSegmentPlan(**row))
        parcels = []
        for item in raw.get("parcels", ()):
            row = dict(item)
            row["cells"] = [tuple(map(int, p)) for p in row.get("cells", ())]
            parcels.append(LandUseParcel(**row))
        structures = []
        for item in raw.get("structures", ()):
            row = dict(item)
            row["footprint"] = [tuple(map(int, p)) for p in row.get("footprint", ())]
            if row.get("entrance") is not None:
                row["entrance"] = tuple(map(int, row["entrance"]))
            structures.append(StructurePlanState(**row))
        rooms = []
        for item in raw.get("rooms", ()):
            row = dict(item)
            row["cells"] = [tuple(map(int, p)) for p in row.get("cells", ())]
            row["doorway_cells"] = [tuple(map(int, p)) for p in row.get("doorway_cells", ())]
            rooms.append(RoomPlanState(**row))
        pieces = [StructurePiecePlan(**dict(item)) for item in raw.get("pieces", ())]
        return cls(plan, roads, parcels, structures, rooms, pieces, str(raw.get("fingerprint", "")))


def settlement_rank_for_population(population: int) -> str:
    population = max(0, int(population))
    if population < 6:
        return "homestead"
    if population < 21:
        return "hamlet"
    if population < 61:
        return "village"
    if population < 181:
        return "town"
    return "city"


def derived_building_summary(skeleton: SettlementSkeleton) -> dict[str, int]:
    """Compatibility summary derived only from the authoritative physical plan."""
    summary: dict[str, int] = {}
    ruins = 0
    for structure in skeleton.structures:
        if structure.destroyed:
            ruins += 1
            continue
        key = "house" if structure.function == "residence" else str(structure.function)
        summary[key] = summary.get(key, 0) + 1
    farms = sum(1 for parcel in skeleton.parcels if parcel.kind == "farm")
    if farms:
        summary["farm"] = farms
    if ruins:
        summary["ruins"] = ruins
    return summary


class SettlementSkeletonPlanner:
    """Terrain-aware bounded settlement planner for RC14 Phase 8.

    Roads are chosen before parcels. The planner reads prepared environmental
    fields only and never realizes terrain/NPCs. It persists one stable physical
    plan that later local materialization and RC17 schedules can consume.
    """

    _RADIUS = {"homestead": 22, "hamlet": 30, "village": 42, "town": 58, "city": 76}
    _RESIDENTIAL_TARGET = {"homestead": 1, "hamlet": 4, "village": 10, "town": 22, "city": 40}
    _FARM_TARGET = {"homestead": 1, "hamlet": 2, "village": 4, "town": 7, "city": 10}
    _LOCAL_STREETS = {"homestead": 0, "hamlet": 1, "village": 2, "town": 4, "city": 6}

    def __init__(self, world, version: int | None = None):
        self.world = world
        self.seed = world.generator.world_seed
        if version is None:
            version = getattr(world, "settlement_plan_version", SETTLEMENT_PLAN_VERSION)
        self.version = int(version)
        self.cache_source = world.delta_source
        self._cache: dict[str, SettlementSkeleton] = {}
        self._env_cache: dict[tuple[int, int], object | None] = {}

    def _env(self, x: int, y: int):
        key = (int(x), int(y))
        if key not in self._env_cache:
            self._env_cache[key] = self.world.environment_at(WorldPos(key[0], key[1], 0))
        return self._env_cache[key]

    def _legal(self, x: int, y: int) -> bool:
        env = self._env(x, y)
        return bool(env is not None and not env.open_water and env.slope <= 78 and env.flood_risk <= 88)

    def _road_cost(self, x: int, y: int, existing: set[tuple[int, int]]) -> int | None:
        env = self._env(x, y)
        if env is None or env.open_water or env.slope > 88 or env.flood_risk > 95:
            return None
        if (x, y) in existing:
            return 3
        return 10 + env.slope * 2 + env.flood_risk * 3 + max(0, env.wetness - 60) * 2 + env.farmland // 6

    def _bounds(self, region_plan, rank: str) -> tuple[int, int, int, int]:
        radius = self._RADIUS[rank]
        ax, ay = region_plan.settlement_anchor
        region_size = 512
        x0, y0 = region_plan.region_x * region_size, region_plan.region_y * region_size
        return (
            max(x0 + 8, ax - radius), max(y0 + 8, ay - radius),
            min(x0 + region_size - 9, ax + radius), min(y0 + region_size - 9, ay + radius),
        )

    def _nearest_legal(self, target: tuple[int, int], bounds: tuple[int, int, int, int], radius: int = 8) -> tuple[int, int] | None:
        left, top, right, bottom = bounds
        tx, ty = target
        rows = []
        for d in range(radius + 1):
            for dy in range(-d, d + 1):
                dx = d - abs(dy)
                for sx in ({-1, 1} if dx else {1}):
                    x, y = tx + sx * dx, ty + dy
                    if left <= x <= right and top <= y <= bottom and self._legal(x, y):
                        env = self._env(x, y)
                        rows.append((d, env.slope + env.flood_risk * 2, y, x))
            if rows:
                row = min(rows)
                return row[3], row[2]
        return None

    def _common_center(self, anchor: tuple[int, int], bounds: tuple[int, int, int, int]) -> tuple[int, int]:
        ax, ay = anchor
        candidates = []
        for y in range(ay - 5, ay + 6):
            for x in range(ax - 5, ax + 6):
                if not (bounds[0] <= x <= bounds[2] and bounds[1] <= y <= bounds[3]):
                    continue
                env = self._env(x, y)
                if env is None or env.open_water:
                    continue
                distance = abs(x - ax) + abs(y - ay)
                score = env.slope * 3 + env.flood_risk * 4 + max(0, env.wetness - 70) * 2 + distance * 4
                candidates.append((score, y, x))
        if not candidates:
            # The old fallback only searched 12 cells while village/town/city
            # planning bounds extend 42/58/76 cells. A hydrology-resolved lake or
            # broad floodplain could therefore produce a false "no legal site"
            # even when dry legal ground existed elsewhere inside the bounds.
            left,top,right,bottom=bounds
            radius=max(abs(ax-left),abs(ax-right),abs(ay-top),abs(ay-bottom))
            legal = self._nearest_legal(anchor, bounds, radius=radius)
            if legal is None:
                raise ValueError("Settlement anchor has no legal common site inside planning bounds")
            return legal
        _, y, x = min(candidates)
        return x, y

    @staticmethod
    def _square(center: tuple[int, int], half: int) -> set[tuple[int, int]]:
        cx, cy = center
        return {(x, y) for y in range(cy - half, cy + half + 1) for x in range(cx - half, cx + half + 1)}

    def _gateway_targets(self, region_plan, common: tuple[int, int], bounds: tuple[int, int, int, int], rank: str) -> list[tuple[tuple[int, int], str]]:
        left, top, right, bottom = bounds
        region_x0, region_y0 = region_plan.region_x * 512, region_plan.region_y * 512
        targets: list[tuple[tuple[int, int], str]] = []
        for road in sorted(region_plan.roads, key=lambda row: (row.direction, row.offset, row.road_class)):
            if road.direction == "north":
                raw = (region_x0 + int(road.offset), top)
            elif road.direction == "south":
                raw = (region_x0 + int(road.offset), bottom)
            elif road.direction == "west":
                raw = (left, region_y0 + int(road.offset))
            else:
                raw = (right, region_y0 + int(road.offset))
            raw = (max(left, min(right, raw[0])), max(top, min(bottom, raw[1])))
            target = self._nearest_legal(raw, bounds, radius=10)
            if target and target not in {row[0] for row in targets}:
                targets.append((target, str(getattr(road, "route_uid", ""))))

        if targets:
            return targets[:4]

        edge = []
        samples = (1, 2, 3)
        for n in samples:
            x = left + (right - left) * n // 4
            y = top + (bottom - top) * n // 4
            for raw in ((x, top), (x, bottom), (left, y), (right, y)):
                target = self._nearest_legal(raw, bounds, radius=6)
                if target is None:
                    continue
                env = self._env(*target)
                edge.append((env.slope * 2 + env.flood_risk * 3 + abs(target[0]-common[0])//4 + abs(target[1]-common[1])//4, target[1], target[0]))
        wanted = 1 if rank in {"homestead", "hamlet"} else 2
        out: list[tuple[tuple[int, int], str]] = []
        for _, y, x in sorted(edge):
            p = (x, y)
            if p not in {row[0] for row in out}:
                out.append((p, ""))
            if len(out) >= wanted:
                break
        return out

    def _path(
        self,
        start: tuple[int, int],
        goal: tuple[int, int],
        bounds: tuple[int, int, int, int],
        existing: set[tuple[int, int]],
    ) -> list[tuple[int, int]]:
        if start == goal:
            return [start]
        left, top, right, bottom = bounds
        queue = [(0, 0, start[1], start[0])]
        best = {start: 0}
        came: dict[tuple[int, int], tuple[int, int]] = {}
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
                return path
            for dx, dy in CARDINALS:
                nx, ny = x + dx, y + dy
                if not (left <= nx <= right and top <= ny <= bottom):
                    continue
                step = self._road_cost(nx, ny, existing)
                if step is None:
                    continue
                ncost = cost + step
                nxt = (nx, ny)
                if ncost >= best.get(nxt, 10**18):
                    continue
                best[nxt] = ncost
                came[nxt] = node
                heuristic = (abs(goal[0]-nx) + abs(goal[1]-ny)) * 8
                heapq.heappush(queue, (ncost + heuristic, ncost, ny, nx))
        return []

    def _best_functional_site(
        self,
        common: tuple[int, int],
        bounds: tuple[int, int, int, int],
        *,
        kind: str,
        archetype: str,
        occupied: set[tuple[int, int]],
    ) -> tuple[int, int] | None:
        left, top, right, bottom = bounds
        rows = []
        for y in range(top + 5, bottom - 4, 4):
            for x in range(left + 5, right - 4, 4):
                if (x, y) in occupied:
                    continue
                env = self._env(x, y)
                if env is None or env.open_water or env.slope > 72 or env.flood_risk > 82:
                    continue
                distance = abs(x-common[0]) + abs(y-common[1])
                if kind == "farm":
                    score = env.farmland * 5 + env.soil_fertility * 2 - env.slope * 3 - env.flood_risk * 3 + min(distance, 50)
                else:
                    if archetype == "mining":
                        resource = env.resources.stone * 6
                    elif archetype == "forest":
                        resource = env.resources.timber * 6
                    elif archetype in {"fishing", "river_market"}:
                        resource = env.resources.freshwater * 5 + env.resources.stone
                    else:
                        resource = env.resource_opportunity * 4
                    score = resource - env.flood_risk * 2 - env.slope + min(distance, 45)
                tie = int((x * 73856093 ^ y * 19349663) & 0xFFFF)
                rows.append((-score, tie, y, x))
        if not rows:
            return None
        _, _, y, x = min(rows)
        return x, y

    @staticmethod
    def _rect(center: tuple[int, int], width: int, height: int) -> set[tuple[int, int]]:
        cx, cy = center
        left = cx - width // 2
        top = cy - height // 2
        return {(x, y) for y in range(top, top + height) for x in range(left, left + width)}

    @staticmethod
    def _approach_point(center: tuple[int,int], width: int, height: int, origin: tuple[int,int]) -> tuple[int,int]:
        """Place a road endpoint just outside a functional parcel, facing town."""
        cx,cy=center; ox,oy=origin
        dx,dy=ox-cx,oy-cy
        if abs(dx)>=abs(dy):
            step=width//2+1
            return (cx+(step if dx>=0 else -step),cy)
        step=height//2+1
        return (cx,cy+(step if dy>=0 else -step))

    def _parcel(
        self,
        plan_uid: str,
        slot: str,
        kind: str,
        purpose: str,
        center: tuple[int, int],
        width: int,
        height: int,
        *,
        forbidden: set[tuple[int, int]],
        road_cells: set[tuple[int, int]],
        access_road_id: str = "",
        min_legal_ratio: int = 82,
    ) -> LandUseParcel | None:
        raw = self._rect(center, width, height)
        if raw & forbidden:
            return None
        legal = {p for p in raw if self._legal(*p)}
        if len(legal) * 100 < len(raw) * min_legal_ratio:
            return None
        cells = legal - road_cells
        if len(cells) * 100 < len(raw) * 65:
            return None
        values = [self._env(*p) for p in cells]
        fertility = sum(v.soil_fertility for v in values) // len(values)
        wetness = sum(v.wetness for v in values) // len(values)
        terrain_score = sum(max(0, 100-v.slope-v.flood_risk//2) for v in values) // len(values)
        ordered = sorted(cells, key=lambda p: (p[1], p[0]))
        return LandUseParcel(
            uid=stable_plan_uid("parcel", plan_uid, slot, ordered),
            settlement_plan_id=plan_uid,
            cells=ordered,
            kind=kind,
            fertility=fertility,
            wetness=wetness,
            purpose=purpose,
            access_road_id=access_road_id,
            terrain_score=terrain_score,
        )

    @staticmethod
    def _parcel_bbox(parcel: LandUseParcel) -> tuple[int, int, int, int]:
        xs=[p[0] for p in parcel.cells]; ys=[p[1] for p in parcel.cells]
        return min(xs),min(ys),max(xs),max(ys)

    @staticmethod
    def _piece_choice(registry, category: str, *, tags: tuple[str, ...] = (), contains: str = ""):
        if registry is None:
            return None
        rows=[]
        for piece in registry.settlement_pieces.values():
            if piece.category!=category:
                continue
            if tags and not all(tag in piece.tags or tag in piece.room_tags for tag in tags):
                continue
            if contains and contains not in piece.id:
                continue
            rows.append(piece)
        return min(rows,key=lambda p:p.id,default=None)

    def _wall_piece_for(self, archetype: str, shape: str):
        registry=getattr(self.world,"registry",None)
        material="stone" if archetype=="mining" else "timber"
        return (
            self._piece_choice(registry,"wall",contains=f"{material}_{shape}")
            or self._piece_choice(registry,"wall",contains=f"{material}_straight")
            or self._piece_choice(registry,"wall",contains=material)
            or self._piece_choice(registry,"wall")
        )

    def _material_choices(self, archetype: str):
        registry=getattr(self.world,"registry",None)
        wall=self._wall_piece_for(archetype,"straight")
        floor_contains="stone_plain" if archetype=="mining" else "plank_plain"
        floor=self._piece_choice(registry,"floor",contains=floor_contains) or self._piece_choice(registry,"floor",contains="stone" if archetype=="mining" else "plank") or self._piece_choice(registry,"floor")
        roof_contains="stone" if archetype=="mining" else ("timber" if archetype in {"forest","frontier"} else "thatch")
        roof=self._piece_choice(registry,"roof",contains=roof_contains) or self._piece_choice(registry,"roof")
        door_contains="stone_arch" if archetype=="mining" else "wood_door"
        door=self._piece_choice(registry,"opening",contains=door_contains) or self._piece_choice(registry,"opening",tags=("door",)) or self._piece_choice(registry,"opening")
        return wall,floor,roof,door

    @staticmethod
    def _road_cell_set(roads: Iterable[RoadSegmentPlan]) -> set[tuple[int,int]]:
        return {tuple(p) for road in roads for p in road.polyline}

    def _select_entrance(
        self,
        shell: set[tuple[int,int]],
        interior: set[tuple[int,int]],
        road_cells: set[tuple[int,int]],
        x0: int, y0: int, width: int, height: int,
    ) -> tuple[tuple[int,int],tuple[int,int],tuple[int,int]]:
        """Choose a cardinally usable, non-corner doorway facing the street."""
        edges=[]
        for x in range(x0+1,x0+width-1):
            edges.append(((x,y0),(x,y0-1),(x,y0+1)))
            edges.append(((x,y0+height-1),(x,y0+height),(x,y0+height-2)))
        for y in range(y0+1,y0+height-1):
            edges.append(((x0,y),(x0-1,y),(x0+1,y)))
            edges.append(((x0+width-1,y),(x0+width,y),(x0+width-2,y)))
        candidates=[]
        for cell,outside,inside in edges:
            if cell not in shell or inside not in interior:
                continue
            road_dist=min(abs(outside[0]-rx)+abs(outside[1]-ry) for rx,ry in road_cells)
            candidates.append((0 if outside in road_cells else 1,road_dist,cell[1],cell[0],cell,outside,inside))
        if not candidates:
            raise ValueError("Building shell has no cardinally accessible entrance cell")
        *_,cell,outside,inside=min(candidates,key=lambda row:row[:4])
        return cell,outside,inside

    @staticmethod
    def _frontage_path(
        start: tuple[int,int],
        road_cells: set[tuple[int,int]],
        parcel_cells: set[tuple[int,int]],
        blocked: set[tuple[int,int]],
        *,
        limit: int = 18,
    ) -> list[tuple[int,int]]:
        """Find a short parcel-contained threshold path from the door to a road."""
        if start in road_cells:
            return [start]
        allowed=(set(parcel_cells)-set(blocked))|set(road_cells)|{start}
        queue=[start];came={start:None}
        target=None
        for cell in queue:
            if cell in road_cells:
                target=cell;break
            if len(came)>512:
                break
            x,y=cell
            for nxt in ((x,y-1),(x+1,y),(x,y+1),(x-1,y)):
                if nxt in came or nxt not in allowed:
                    continue
                if abs(nxt[0]-start[0])+abs(nxt[1]-start[1])>limit:
                    continue
                came[nxt]=cell;queue.append(nxt)
        if target is None:
            return [start]
        out=[];cur=target
        while cur is not None:
            out.append(cur);cur=came[cur]
        out.reverse()
        return out

    def _building_rect(self, parcel: LandUseParcel, *, large: bool) -> tuple[int,int,int,int] | None:
        left,top,right,bottom=self._parcel_bbox(parcel)
        available_w=right-left+1; available_h=bottom-top+1
        target_w=7 if large and available_w>=7 else 5 if available_w>=5 else available_w
        target_h=5 if available_h>=5 else available_h
        if target_w<4 or target_h<4:
            return None
        cx=(left+right)//2; cy=(top+bottom)//2
        x0=cx-target_w//2; y0=cy-target_h//2
        rect={(x,y) for y in range(y0,y0+target_h) for x in range(x0,x0+target_w)}
        if not rect.issubset(set(parcel.cells)):
            candidates=[]
            for sy in range(top,bottom-target_h+2):
                for sx in range(left,right-target_w+2):
                    cells={(x,y) for y in range(sy,sy+target_h) for x in range(sx,sx+target_w)}
                    if cells.issubset(set(parcel.cells)):
                        candidates.append((abs((sx+target_w//2)-cx)+abs((sy+target_h//2)-cy),sy,sx))
            if not candidates:
                return None
            _,y0,x0=min(candidates)
        return x0,y0,target_w,target_h

    def _fixture_piece(self, function: str, room_side: str):
        registry=getattr(self.world,"registry",None)
        if function=="residence":
            if room_side=="primary":
                return self._piece_choice(registry,"furniture",tags=("bed",))
            return self._piece_choice(registry,"furniture",contains="house_hearth")
        if function=="smithy":
            return self._piece_choice(registry,"workshop",contains="forge") if room_side=="primary" else self._piece_choice(registry,"furniture",contains="house_chest")
        if function=="workshop":
            return self._piece_choice(registry,"workshop",contains="carpenter_bench") if room_side=="primary" else self._piece_choice(registry,"furniture",contains="house_chest")
        if function=="mill":
            return self._piece_choice(registry,"workshop",contains="millstone") if room_side=="primary" else self._piece_choice(registry,"furniture",contains="house_chest")
        if function=="fishery":
            return self._piece_choice(registry,"workshop",contains="butcher_table") if room_side=="primary" else self._piece_choice(registry,"furniture",contains="house_chest")
        if function=="barn":
            return self._piece_choice(registry,"agriculture",contains="barn_stall") if room_side=="primary" else self._piece_choice(registry,"agriculture",contains="hay_rack")
        if function=="market":
            return self._piece_choice(registry,"civic",contains="market_stall") if room_side=="primary" else self._piece_choice(registry,"furniture",contains="large_table")
        if function=="clinic":
            return self._piece_choice(registry,"workshop",contains="herbalist_table") if room_side=="primary" else self._piece_choice(registry,"workshop",contains="apothecary_shelf")
        if function=="watchhouse":
            return self._piece_choice(registry,"civic",contains="guard_post") if room_side=="primary" else self._piece_choice(registry,"furniture",contains="bench")
        if function=="shrine":
            return self._piece_choice(registry,"decoration",contains="wayside_shrine") if room_side=="primary" else self._piece_choice(registry,"furniture",contains="bench")
        if function in {"archive","school"}:
            return self._piece_choice(registry,"workshop",contains="scribe_desk") if room_side=="primary" else self._piece_choice(registry,"furniture",contains="wall_shelf")
        return self._piece_choice(registry,"furniture",contains="small_table")

    def _plan_building(
        self,
        parcel: LandUseParcel,
        roads: list[RoadSegmentPlan],
        *,
        slot: str,
        function: str,
        archetype: str,
        large: bool,
    ) -> tuple[StructurePlanState,list[RoomPlanState],list[StructurePiecePlan]] | None:
        registry=getattr(self.world,"registry",None)
        if registry is None:
            return None
        rect=self._building_rect(parcel,large=large)
        if rect is None:
            return None
        x0,y0,width,height=rect
        shell={(x,y) for x in range(x0,x0+width) for y in (y0,y0+height-1)}
        shell|={(x,y) for y in range(y0,y0+height) for x in (x0,x0+width-1)}
        interior={(x,y) for y in range(y0+1,y0+height-1) for x in range(x0+1,x0+width-1)}
        road_cells=self._road_cell_set(roads)
        if not road_cells:
            return None
        entrance,entrance_outside,entrance_inside=self._select_entrance(
            shell,interior,road_cells,x0,y0,width,height
        )
        walls=set(shell); walls.discard(entrance)
        doors={entrance}
        partition_cells=set()
        if large and width>=7 and len(interior)>=9:
            px=x0+width//2
            partition_cells={(px,y) for y in range(y0+1,y0+height-1)}
            internal_door=(px,y0+height//2)
            partition_cells.discard(internal_door)
            doors.add(internal_door)
            walls|=partition_cells

        structure_uid=stable_plan_uid("structure",parcel.uid,slot,sorted(shell|interior))
        wall_piece,floor_piece,roof_piece,door_piece=self._material_choices(archetype)
        approach_piece=self._piece_choice(registry,"road",contains="cobble") if archetype=="mining" else self._piece_choice(registry,"road",contains="footpath")
        approach_piece=approach_piece or self._piece_choice(registry,"road")
        if not all((wall_piece,floor_piece,roof_piece,door_piece,approach_piece)):
            return None
        placements=[]
        def place(piece,cell,role):
            uid=stable_plan_uid("piece",structure_uid,f"{piece.id}:{role}:{cell[0]}:{cell[1]}",[cell])
            placements.append(StructurePiecePlan(uid,structure_uid,piece.id,cell[0],cell[1],piece.layer,role))
            return uid
        wall_network=walls|doors
        for cell in sorted(walls,key=lambda p:(p[1],p[0])):
            x,y=cell
            connected={
                "n":(x,y-1) in wall_network,"e":(x+1,y) in wall_network,
                "s":(x,y+1) in wall_network,"w":(x-1,y) in wall_network,
            }
            degree=sum(1 for value in connected.values() if value)
            if degree>=3:
                shape="reinforced"
            elif (connected["n"] or connected["s"]) and (connected["e"] or connected["w"]):
                shape="corner"
            else:
                shape="straight"
            selected_wall=self._wall_piece_for(archetype,shape) or wall_piece
            place(selected_wall,cell,"partition" if cell in partition_cells else "wall")
        for cell in sorted(doors,key=lambda p:(p[1],p[0])):
            place(door_piece,cell,"interior_door" if cell!=entrance else "entrance")
            # Exterior thresholds need a floor under the shell opening. Interior
            # doors already receive their floor from the interior-cell pass.
            if cell==entrance:
                place(floor_piece,cell,"threshold")
        frontage=self._frontage_path(
            entrance_outside,road_cells,set(parcel.cells),shell|interior,
        )
        for cell in frontage:
            if cell not in road_cells:
                place(approach_piece,cell,"frontage")
        for cell in sorted(interior,key=lambda p:(p[1],p[0])):
            place(floor_piece,cell,"floor")
            place(roof_piece,cell,"roof")

        fixture_tags={}
        interior_sorted=sorted(interior,key=lambda p:(p[1],p[0]))
        if interior_sorted:
            if large and partition_cells:
                px=x0+width//2
                left_cells=[p for p in interior_sorted if p[0]<px]
                right_cells=[p for p in interior_sorted if p[0]>px]
                fixture_slots=[("primary",left_cells[0] if left_cells else interior_sorted[0]),
                               ("secondary",right_cells[-1] if right_cells else interior_sorted[-1])]
            else:
                fixture_slots=[("primary",interior_sorted[0])]
            for side,cell in fixture_slots:
                fixture=self._fixture_piece(function,side)
                if fixture is None:
                    continue
                place(fixture,cell,"fixture")
                fixture_tags.setdefault(cell,set()).update(fixture.room_tags or fixture.tags)

        analysis=analyze_building(
            structure_uid,wall_cells=walls,door_cells=doors,roof_cells=interior,
            floor_cells=interior,fixture_tags=fixture_tags,
        )
        if not analysis.enclosed or analysis.roof_percent<60:
            return None
        rooms=[RoomPlanState(**asdict(room)) for room in analysis.rooms]
        fixture_placements=[p for p in placements if p.role=="fixture"]
        for room in rooms:
            room.fixture_ids=[p.uid for p in fixture_placements if (p.x,p.y) in set(room.cells)]
        structure=StructurePlanState(
            uid=structure_uid,settlement_plan_id=parcel.settlement_plan_id,
            content_id=f"core:generated_{function}",function=function,
            footprint=sorted(shell|interior,key=lambda p:(p[1],p[0])),
            entrance=entrance,building_type=analysis.building_type,enclosed=analysis.enclosed,
            interior_area=analysis.interior_area,room_ids=[r.uid for r in rooms],
            piece_ids=[p.uid for p in placements],roof_percent=analysis.roof_percent,
            workplace_role=({"smithy":"smith","workshop":"carpenter","mill":"miller","fishery":"fisher","barn":"farmer","market":"merchant","clinic":"healer","watchhouse":"guard","shrine":"priest","archive":"scholar","school":"scholar"}.get(function,"")),
        )
        return structure,rooms,placements

    def _generate_buildings(
        self,
        plan: SettlementPlanState,
        roads: list[RoadSegmentPlan],
        parcels: list[LandUseParcel],
    ) -> tuple[list[StructurePlanState],list[RoomPlanState],list[StructurePiecePlan]]:
        structures=[]; rooms=[]; pieces=[]
        residential=[p for p in parcels if p.kind=="residential"]
        for index,parcel in enumerate(residential):
            large=plan.rank in {"town","city"} and index%3==0
            result=self._plan_building(parcel,roads,slot=f"home:{index}",function="residence",archetype=plan.archetype,large=large)
            if result:
                structure,new_rooms,new_pieces=result
                structures.append(structure);rooms.extend(new_rooms);pieces.extend(new_pieces)
                parcel.structure_ids.append(structure.uid)

        industrial=[p for p in parcels if p.kind=="industrial"]
        if industrial:
            function={"mining":"smithy","forest":"workshop","agrarian":"mill","fishing":"fishery","river_market":"workshop"}.get(plan.archetype,"workshop")
            result=self._plan_building(industrial[0],roads,slot="industry:0",function=function,archetype=plan.archetype,large=True)
            if result:
                structure,new_rooms,new_pieces=result
                structures.append(structure);rooms.extend(new_rooms);pieces.extend(new_pieces)
                industrial[0].structure_ids.append(structure.uid)

        civic=[p for p in parcels if p.kind=="civic" and p.purpose not in {"","common"}]
        for index,parcel in enumerate(civic):
            function=parcel.purpose
            result=self._plan_building(parcel,roads,slot=f"civic:{index}:{function}",function=function,archetype=plan.archetype,large=plan.rank in {"town","city"})
            if result:
                structure,new_rooms,new_pieces=result
                structures.append(structure);rooms.extend(new_rooms);pieces.extend(new_pieces)
                parcel.structure_ids.append(structure.uid)

        farms=[p for p in parcels if p.kind=="farm"]
        if farms:
            result=self._plan_building(farms[0],roads,slot="farm:0",function="barn",archetype=plan.archetype,large=True)
            if result:
                structure,new_rooms,new_pieces=result
                structures.append(structure);rooms.extend(new_rooms);pieces.extend(new_pieces)
                farms[0].structure_ids.append(structure.uid)
        return structures,rooms,pieces

    def _generate(self, region_plan, settlement_id: str, population: int) -> SettlementSkeleton:
        if not region_plan.settlement_present or region_plan.settlement_anchor is None:
            raise ValueError("Cannot generate settlement skeleton for a region without a settlement anchor")
        rank = settlement_rank_for_population(population)
        bounds = self._bounds(region_plan, rank)
        common_center = self._common_center(region_plan.settlement_anchor, bounds)
        common_half = 1 if rank in {"homestead", "hamlet"} else 2 if rank in {"village", "town"} else 3
        common_cells = {p for p in self._square(common_center, common_half) if self._legal(*p)}
        if not common_cells:
            common_cells = {common_center}

        plan_uid = stable_plan_uid("settlement-plan", str(settlement_id), self.version, [region_plan.settlement_anchor])
        plan = SettlementPlanState(
            uid=plan_uid, settlement_id=str(settlement_id), version=self.version,
            anchor_x=region_plan.settlement_anchor[0], anchor_y=region_plan.settlement_anchor[1],
            archetype=region_plan.settlement_archetype, rank=rank,
            common_cells=sorted(common_cells, key=lambda p: (p[1], p[0])),
        )

        roads: list[RoadSegmentPlan] = []
        road_cells: set[tuple[int, int]] = set()
        gateway_rows = self._gateway_targets(region_plan, common_center, bounds, rank)
        gateways = [row[0] for row in gateway_rows]
        plan.gateway_cells = list(gateways)

        def add_road(slot: str, target: tuple[int, int], road_class: str, width: int = 1, route_id: str = "") -> str:
            path = self._path(common_center, target, bounds, road_cells)
            if len(path) < 2:
                return ""
            uid = stable_plan_uid("road", plan.uid, slot, path)
            roads.append(RoadSegmentPlan(
                uid=uid, route_id=str(route_id), settlement_plan_id=plan.uid, road_class=road_class,
                polyline=path, width=width, surface="earth",
            ))
            road_cells.update(path)
            return uid

        main_class = "maintained_road" if rank in {"town", "city"} else "road"
        main_width = 2 if rank in {"town", "city"} else 1
        for i, (target, route_uid) in enumerate(gateway_rows):
            add_road(f"gateway:{i}", target, main_class, main_width, route_id=route_uid)

        # Grow bounded local streets around the common. These are street seeds,
        # not arbitrary house coordinates, and provide frontage for later lots.
        local_count = self._LOCAL_STREETS[rank]
        radius = min(22, max(10, self._RADIUS[rank] // 2))
        local_targets = [
            (common_center[0] + radius, common_center[1]),
            (common_center[0] - radius, common_center[1]),
            (common_center[0], common_center[1] + radius),
            (common_center[0], common_center[1] - radius),
            (common_center[0] + radius//2, common_center[1] + radius//2),
            (common_center[0] - radius//2, common_center[1] - radius//2),
        ]
        added = 0
        for raw in local_targets:
            target = self._nearest_legal(raw, bounds, radius=7)
            if target is None or target in gateways:
                continue
            if add_road(f"street:{added}", target, "road" if rank in {"town","city"} else "path"):
                added += 1
            if added >= local_count:
                break

        # Functional land-use anchors pull roads outward toward the land that
        # explains the settlement's economy.
        occupied = set(common_cells) | road_cells
        farm_target = self._best_functional_site(
            common_center, bounds, kind="farm", archetype=plan.archetype, occupied=occupied
        )
        # Agricultural and industrial anchors must be physically distinct even
        # when a uniformly good test/plain gives both scorers the same optimum.
        industry_occupied=set(occupied)
        if farm_target:
            industry_occupied |= self._rect(farm_target,11,9)
        industry_target = self._best_functional_site(
            common_center, bounds, kind="industry", archetype=plan.archetype, occupied=industry_occupied
        )
        farm_road = add_road(
            "farm-access", self._approach_point(farm_target,9,7,common_center), "path"
        ) if farm_target else ""
        industry_road = add_road(
            "industry-access", self._approach_point(industry_target,7,7,common_center), "road"
        ) if industry_target else ""

        parcels: list[LandUseParcel] = []
        common_ordered = sorted(common_cells, key=lambda p: (p[1], p[0]))
        common_parcel = LandUseParcel(
            stable_plan_uid("parcel", plan.uid, "common", common_ordered), plan.uid,
            cells=common_ordered, kind="civic", current_use_state="common",
            purpose="common", terrain_score=100,
        )
        parcels.append(common_parcel)
        occupied = set(common_cells)
        # Functional anchors are selected before housing and must remain
        # physically available. Reserve their intended work/field footprints so
        # street-fronting homes cannot consume the very land that explains why
        # the settlement exists.
        functional_reserve=set()
        if farm_target:
            functional_reserve |= self._rect(farm_target,9,7)
        if industry_target:
            functional_reserve |= self._rect(industry_target,7,7)

        # Residential lots are street-fronting by construction. Candidate lots
        # are projected to either side of the actual curved road polyline.
        residential_goal = self._RESIDENTIAL_TARGET[rank]
        candidates = []
        for road in roads:
            path = road.polyline
            for idx in range(3, max(3, len(path)-2), 5):
                x, y = path[idx]
                prev = path[max(0, idx-1)]
                nxt = path[min(len(path)-1, idx+1)]
                dx = nxt[0] - prev[0]
                dy = nxt[1] - prev[1]
                if abs(dx) >= abs(dy):
                    normals = ((0, 5), (0, -5))
                else:
                    normals = ((5, 0), (-5, 0))
                for nx, ny in normals:
                    center = (x + nx, y + ny)
                    env = self._env(*center)
                    if env is None:
                        continue
                    candidates.append((env.slope*3 + env.flood_risk*4 + abs(center[0]-common_center[0])//2 + abs(center[1]-common_center[1])//2, center[1], center[0], road.uid))
        service_by_rank={
            "homestead":(),
            "hamlet":("market",),
            "village":("market","clinic","watchhouse","shrine"),
            "town":("market","clinic","watchhouse","shrine","archive"),
            "city":("market","clinic","watchhouse","shrine","archive","school"),
        }
        remaining_candidates=list(sorted(candidates))
        for service in service_by_rank[rank]:
            placed=None
            for _,sy,sx,access_id in list(remaining_candidates):
                size=7 if rank in {"town","city"} else 5
                parcel=self._parcel(
                    plan.uid,f"civic:{service}","civic",service,(sx,sy),size,size,
                    forbidden=occupied | functional_reserve,road_cells=road_cells,access_road_id=access_id,
                )
                if parcel is None:continue
                parcels.append(parcel);occupied.update(parcel.cells);placed=(sx,sy,access_id)
                remaining_candidates=[row for row in remaining_candidates if (row[2],row[1])!=(sx,sy)]
                break

        for _, y, x, access_id in remaining_candidates:
            parcel = self._parcel(
                plan.uid, f"residential:{len([p for p in parcels if p.kind=='residential'])}",
                "residential", "home_lot", (x, y),
                7 if rank in {"town","city"} else 5,
                7 if rank in {"town","city"} else 5,
                forbidden=occupied | functional_reserve, road_cells=road_cells, access_road_id=access_id,
            )
            if parcel is None:
                continue
            parcels.append(parcel)
            occupied.update(parcel.cells)
            if len([p for p in parcels if p.kind == "residential"]) >= residential_goal:
                break

        if farm_target:
            farm_goal = self._FARM_TARGET[rank]
            offsets = ((0,0),(10,0),(-10,0),(0,8),(0,-8),(10,8),(-10,8),(10,-8),(-10,-8),(20,0),(-20,0))
            made = 0
            for ox, oy in offsets:
                parcel = self._parcel(
                    plan.uid, f"farm:{made}", "farm", "field",
                    (farm_target[0]+ox, farm_target[1]+oy), 9, 7,
                    forbidden=occupied, road_cells=road_cells, access_road_id=farm_road,
                    min_legal_ratio=75,
                )
                if parcel is None or parcel.fertility < 22:
                    continue
                parcels.append(parcel); occupied.update(parcel.cells); made += 1
                if made >= farm_goal:
                    break

        if industry_target:
            purpose = {
                "mining": "mine_approach",
                "forest": "logging_yard",
                "fishing": "fishery",
                "river_market": "trade_workyard",
                "agrarian": "mill_workyard",
                "frontier": "general_workyard",
            }.get(plan.archetype, "general_workyard")
            parcel = self._parcel(
                plan.uid, "industrial:0", "industrial", purpose, industry_target, 7, 7,
                forbidden=occupied, road_cells=road_cells, access_road_id=industry_road,
                min_legal_ratio=70,
            )
            if parcel is not None:
                parcels.append(parcel); occupied.update(parcel.cells)

        plan.road_segment_ids = [row.uid for row in roads]
        plan.parcel_ids = [row.uid for row in parcels]
        summary: dict[str, int] = {}
        for parcel in parcels:
            summary[parcel.kind] = summary.get(parcel.kind, 0) + len(parcel.cells)
        plan.land_use_summary = summary
        all_points = set(common_cells) | road_cells | {p for parcel in parcels for p in parcel.cells}
        if all_points:
            xs = [p[0] for p in all_points]; ys = [p[1] for p in all_points]
            plan.atlas_bounds = (min(xs), min(ys), max(xs), max(ys))

        structures,rooms,pieces=self._generate_buildings(plan,roads,parcels)
        plan.structure_site_ids=[row.uid for row in structures]
        housing=0
        workplace: dict[str,int]={}
        for structure in structures:
            if structure.destroyed:
                continue
            area=max(1,int(structure.interior_area or len(structure.footprint)))
            if structure.function=="residence":
                housing += max(2,min(12,area//3+1))
            else:
                workplace[structure.function]=workplace.get(structure.function,0)+max(1,min(12,area//4+1))
        plan.housing_capacity=housing
        plan.workplace_capacity=workplace
        skeleton = SettlementSkeleton(plan, roads, parcels, structures, rooms, pieces)
        skeleton.fingerprint = canonical_hash({
            "plan": asdict(plan),
            "roads": [asdict(row) for row in roads],
            "parcels": [asdict(row) for row in parcels],
            "structures": [asdict(row) for row in structures],
            "rooms": [asdict(row) for row in rooms],
            "pieces": [asdict(row) for row in pieces],
        })
        return skeleton

    def read_prepared(self, settlement_id: str) -> SettlementSkeleton | None:
        settlement_id = str(settlement_id)
        if settlement_id in self._cache:
            return self._cache[settlement_id]
        loader = getattr(self.cache_source, "load_generated_settlement_plan", None)
        if not callable(loader):
            return None
        raw = loader(settlement_id, self.version)
        if not raw:
            return None
        try:
            fingerprint = str(raw.get("fingerprint", ""))
            check = dict(raw); check.pop("fingerprint", None)
            if fingerprint != canonical_hash(check):
                return None
            skeleton = SettlementSkeleton.from_dict(raw)
            if skeleton.plan.settlement_id != settlement_id or skeleton.plan.version != self.version:
                return None
            self._cache[settlement_id] = skeleton
            return skeleton
        except (KeyError, TypeError, ValueError):
            return None

    def plan(self, region_plan, settlement_id: str, population: int, *, persist: bool = True, refresh: bool = False) -> SettlementSkeleton:
        prepared = None if refresh else self.read_prepared(settlement_id)
        if prepared is not None:
            return prepared
        self._env_cache.clear()
        skeleton = self._generate(region_plan, settlement_id, population)
        self._cache[str(settlement_id)] = skeleton
        if persist:
            storer = getattr(self.cache_source, "store_generated_settlement_plan", None)
            if callable(storer):
                storer(str(settlement_id), self.version, skeleton.to_dict())
                commit = getattr(self.cache_source, "commit_generated", None)
                if callable(commit):
                    commit()
        return skeleton
