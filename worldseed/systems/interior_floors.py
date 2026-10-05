"""Bounded residential floor projection with stable, shared door ownership."""
from __future__ import annotations

from worldseed.systems.interior_state import InteriorPlan, InteriorRect, InteriorStair
from worldseed.systems.interior_templates import rooms_for_profile


def residential_floor_count(structure) -> int:
    """Floors respond to the physical building footprint, not an RNG roll."""
    if structure.function not in {"residence", "inn", "barracks"}:
        return 1
    cells = structure.footprint or []
    if not cells:
        return 1
    span = max(max(x for x, _ in cells) - min(x for x, _ in cells) + 1,
               max(y for _, y in cells) - min(y for _, y in cells) + 1)
    return 3 if len(cells) >= 60 or span >= 10 else 2 if len(cells) >= 24 or span >= 7 else 1


def _stair_rect(plan, placement_clear) -> InteriorRect | None:
    # Hall-first, then room edges. Keep real doors, fixtures and saved furniture.
    for room in sorted(plan.rooms, key=lambda r: ("hall" not in r.name.lower(), r.uid)):
        r = room.rect
        for y in (r.y + 500, r.y + r.h - 2400):
            for x in (r.x + 550, r.x + r.w - 1950):
                rect = InteriorRect(x, y, 1400, 1900)
                if (x >= r.x + 200 and y >= r.y + 200
                        and x + rect.w <= r.x + r.w - 200
                        and y + rect.h <= r.y + r.h - 200
                        and placement_clear(plan, rect)):
                    return rect
    return None


def prepare_floors(system, ground, structure, profile, *, new_ground=False) -> list[InteriorPlan]:
    """Explicit preparation only; saved ground-floor geometry is never rerolled."""
    from worldseed.systems.interiors import InteriorSystem, placement_clear, position_clear, exit_reachable
    target_count = max(ground.floor_count, residential_floor_count(structure))
    floors = [ground]
    for index in range(1, target_count):
        uid = ground.uid + ":floor:" + str(index)
        floor = system.state.interiors.get(uid)
        if floor is None:
            floor = InteriorPlan(uid, ground.building_id, ground.door_uid,
                                 ground.exterior_x, ground.exterior_y, ground.exterior_z,
                                 ground.width, ground.height, ground.name, ground.function,
                                 ground.owner_uid, version=max(3, ground.version), layout_id=ground.layout_id,
                                 floor_index=index, floor_count=target_count,
                                 variant_id=ground.variant_id, floor_material=ground.floor_material,
                                 wall_material=ground.wall_material)
            floor.rooms, floor.walls, (floor.entry_x, floor.entry_y) = rooms_for_profile(
                uid, profile, floor.width, floor.height)
        lower = floors[-1]
        up = next((s for s in lower.stairs if s.target_space_id == floor.uid), None)
        down = next((s for s in floor.stairs if s.target_space_id == lower.uid), None)
        if up is None or down is None:
            lower_rect, upper_rect = _stair_rect(lower, placement_clear), _stair_rect(floor, placement_clear)
            if lower_rect is None or upper_rect is None:
                break
            low_landing = lower_rect.x + lower_rect.w // 2, lower_rect.y + lower_rect.h - 300
            high_landing = upper_rect.x + upper_rect.w // 2, upper_rect.y + upper_rect.h - 300
            if not (position_clear(lower, *low_landing) and position_clear(floor, *high_landing)
                    and exit_reachable(lower, *low_landing) and exit_reachable(floor, *high_landing)):
                break
            lower.stairs.append(InteriorStair(lower.uid + ":stairs:up", lower_rect.x, lower_rect.y,
                                             lower_rect.w, lower_rect.h, floor.uid, *high_landing, "up"))
            floor.stairs.append(InteriorStair(floor.uid + ":stairs:down", upper_rect.x, upper_rect.y,
                                             upper_rect.w, upper_rect.h, lower.uid, *low_landing, "down"))
            # The upper-floor escape reference is the real stair landing; it is
            # never treated as a second exterior door.
            floor.entry_x, floor.entry_y = high_landing
        floor.exterior_x, floor.exterior_y, floor.exterior_z = ground.exterior_x, ground.exterior_y, ground.exterior_z
        system.state.interiors[floor.uid] = floor
        floors.append(floor)
    for floor in floors:
        floor.floor_count = len(floors)
        if floor.stairs:
            floor.version = max(3, floor.version)
    # Only newly generated fixtures may be distributed upstairs. Their stable
    # IDs and total bed capacity remain exactly the same as the physical plan.
    if new_ground and len(floors) > 1:
        beds = [f for f in ground.furniture if "bed" in f.piece_id]
        for number, bed in enumerate(beds):
            floor = floors[1 + number % (len(floors) - 1)]
            for room in sorted(floor.rooms, key=lambda r: (not any(k in r.name.lower() for k in ("bed", "guest", "bunk", "dorm")), r.uid)):
                placed = False
                for col in range(4):
                    x, y = room.rect.x + 450 + col * (bed.w + 600), room.rect.y + 450
                    rect = InteriorRect(x, y, bed.w, bed.h)
                    if (x + bed.w <= room.rect.x + room.rect.w - 400
                            and y + bed.h <= room.rect.y + room.rect.h - 600
                            and placement_clear(floor, rect)):
                        old_position = bed.x, bed.y
                        bed.x, bed.y = x, y
                        floor.furniture.append(bed)
                        safe = (InteriorSystem.fixture_use_position(floor, bed) is not None
                                and all(exit_reachable(floor, r.rect.x + r.rect.w // 2,
                                                       r.rect.y + r.rect.h - 400) for r in floor.rooms))
                        if not safe:
                            floor.furniture.remove(bed)
                            bed.x, bed.y = old_position
                            continue
                        ground.furniture.remove(bed)
                        placed = True
                        break
                if placed:
                    break
    return floors
