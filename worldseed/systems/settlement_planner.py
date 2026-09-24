from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Iterable, Mapping

from worldseed.world.regional_plan import RoomPlanState, stable_plan_uid

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
        return "shop"
    if "sanctuary" in kinds:
        return "shrine"
    if "workshop" in kinds:
        return "workshop"
    if "bedroom" in kinds:
        return "residence"
    if "storage" in kinds and len(kinds) == 1:
        return "storehouse"
    if all_tags & {"stable", "livestock"}:
        return "stable"
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
