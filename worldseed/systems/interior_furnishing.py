"""Bounded indoor furnishing grammar, applied only during explicit preparation.

The stable physical plan remains the source of beds, productive stations and
inventory. This grammar adds household seating, lighting and domestic fittings
only; it does not mint housing capacity, reservations, stock or containers.
"""
from __future__ import annotations

from functools import lru_cache
import json
import re

from worldseed.config import DATA_DIR
from worldseed.core.rng import hash_u64
from worldseed.systems.interior_state import ACTOR_RADIUS, InteriorFurniture, InteriorRect


@lru_cache(maxsize=1)
def furnishing_catalog() -> dict:
    data = json.loads((DATA_DIR / "interior_furnishing.json").read_text(encoding="utf-8"))
    if data.get("version") != 2 or not 1 <= data.get("maximum_additions", 0) <= 32:
        raise ValueError("Invalid interior furnishing catalog version or budget")
    for row in furniture_variant_catalog():
        if row["base_piece"] not in data["pieces"]:
            raise ValueError("Unknown furniture variant base: " + row["base_piece"])
        base = data["pieces"][row["base_piece"]]
        if any(row[key] != base[key] for key in ("width", "depth")):
            raise ValueError("Furniture artwork variants cannot change physical footprints")
        data["pieces"][row["id"]] = {key: row[key] for key in ("width", "depth", "height_ratio")}
    for uid, row in data["pieces"].items():
        if (not uid.startswith("core:") or any(type(row.get(key)) is not int
                or not 300 <= row[key] <= 4000 for key in ("width", "depth"))
                or not 1 <= row.get("height_ratio", 0) <= 4):
            raise ValueError("Invalid furniture footprint or artwork dimensions")
    anchors = {"north", "south", "west", "east", "centre", "seat_south", "seat_west", "hearth_apron", "bedside"}
    for slot, row in data["slots"].items():
        if (row.get("piece") not in data["pieces"] or row.get("anchor") not in anchors
                or any(not 0 <= row.get(key, -1) <= 1 for key in ("x", "y"))):
            raise ValueError("Invalid furnishing slot: " + slot)
    for slot, row in data["fixture_anchors"].items():
        if (row.get("anchor") not in anchors
                or any(not 0 <= row.get(key, -1) <= 1 for key in ("x", "y"))):
            raise ValueError("Invalid source fixture anchor: " + slot)
    for role in data["fixture_roles"]:
        if (not role.get("words") or not role.get("styles") or not role.get("anchors")
                or any(style not in data["styles"] for style in role["styles"])
                or any(anchor not in data["fixture_anchors"] for anchor in role["anchors"])):
            raise ValueError("Invalid source fixture room role")
    for style, slots in data["styles"].items():
        if not isinstance(slots, list) or any(slot not in data["slots"] for slot in slots):
            raise ValueError("Invalid furnishing style: " + style)
    if any(row.get("style") not in data["styles"] or not row.get("words") for row in data["room_sets"]):
        raise ValueError("Invalid furnishing room selector")
    return data


@lru_cache(maxsize=1)
def furniture_variant_catalog() -> tuple[dict, ...]:
    """Small authored visual families; no inventories or capacity are added."""
    raw = json.loads((DATA_DIR / "interior_furniture_variants.json").read_text(encoding="utf-8"))
    if raw.get("version") != 1 or not isinstance(raw.get("pieces"), list):
        raise ValueError("Invalid furniture variant catalog")
    seen, assets = set(), set()
    for row in raw["pieces"]:
        if not isinstance(row, dict):
            raise ValueError("Furniture variant must be an object")
        uid, asset = row.get("id", ""), row.get("asset", "")
        if (not isinstance(asset, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", asset)
                or uid != "core:" + asset + "_piece" or uid in seen or asset in assets
                or not isinstance(row.get("base_piece"), str)
                or not re.fullmatch(r"core:[a-z][a-z0-9_]*", row["base_piece"])
                or not isinstance(row.get("name"), str) or not row["name"].strip()
                or any(type(row.get(key)) is not int
                    or not 300 <= row[key] <= 4000 for key in ("width", "depth"))
                or not 1 <= row.get("height_ratio", 0) <= 4):
            raise ValueError("Invalid furniture variant identity or dimensions")
        seen.add(uid)
        assets.add(asset)
    return tuple(sorted(raw["pieces"], key=lambda row: row["id"]))


def furniture_base_piece(piece_id: str) -> str:
    return next((row["base_piece"] for row in furniture_variant_catalog() if row["id"] == piece_id), piece_id)


def is_bed_piece(piece_id: str) -> bool:
    """Bedside carpets and generic names never acquire housing/rest capacity."""
    return furniture_base_piece(piece_id) in {
        "core:single_bed_piece", "core:double_bed_piece", "core:bunk_bed_piece",
    }


def furniture_variant(piece_id: str, stable_uid: str) -> str:
    """Choose once when a new fixture is prepared; never restyle saved pieces."""
    if furniture_base_piece(piece_id) != piece_id:
        return piece_id
    choices = tuple(row["id"] for row in furniture_variant_catalog() if row["base_piece"] == piece_id)
    if not choices or not stable_uid:
        return piece_id
    return choices[hash_u64(b"interior-furniture-variants-v1", "fixture-style", piece_id, stable_uid) % len(choices)]


def furniture_dimensions(piece_id: str) -> tuple[int, int]:
    """Return a physical floor footprint in fixed-point indoor units."""
    row = furnishing_catalog()["pieces"].get(piece_id)
    if row:
        return row["width"], row["depth"]
    # Mod/legacy fixtures retain the conservative established dimensions.
    if "bed" in piece_id:
        return 950, 1450
    if "table" in piece_id:
        return 1150, 750
    if "chest" in piece_id or "storage" in piece_id:
        return 850, 650
    return 750, 750


def furniture_visual(piece_id: str) -> dict:
    """Artwork canvas is footprint-width by depth*ratio, bottom anchored.

    The renderer aspect-fits the native silhouette in this canvas rather than
    crushing upright furniture into its shallow collision rectangle. Flat
    fittings should be drawn before furniture and actors, not over their feet.
    """
    row = furnishing_catalog()["pieces"].get(piece_id, {})
    return {"height_ratio": float(row.get("height_ratio", 1.6)), "flat": bool(row.get("flat", False))}


def _style(room, plan, catalog) -> str:
    name = room.name.lower()
    if room.uid.endswith(":gallery") or any(word in name for word in ("passage", "gallery", "aisle", "muster")):
        return "passage"
    for row in catalog["room_sets"]:
        if any(word in name for word in row["words"]):
            return row["style"]
    return "living" if plan.function in {"residence", "inn", "outskirt_camp"} else "work"


def room_furnishing_style(room, plan) -> str:
    """Read-only room purpose used by both fixture projection and decoration."""
    return _style(room, plan, furnishing_catalog())


def _anchor_position(plan, room, spec, width, depth):
    """Resolve a named room slot, never a random scatter or a search grid."""
    rect, margin = room.rect, 425
    if width + 2 * margin > rect.w or depth + 2 * margin > rect.h:
        return None
    x = rect.x + margin + round((rect.w - width - 2 * margin) * spec["x"])
    y = rect.y + margin + round((rect.h - depth - 2 * margin) * spec["y"])
    anchor = spec["anchor"]
    if anchor in {"seat_south", "seat_west", "hearth_apron", "bedside"}:
        families = ({"core:large_table_piece", "core:small_table_piece", "core:writing_desk_piece", "core:scribe_desk_piece"}
                    if anchor.startswith("seat_") else {"core:house_hearth_piece"}
                    if anchor == "hearth_apron" else {"core:single_bed_piece", "core:double_bed_piece", "core:bunk_bed_piece"})
        targets = sorted((f for f in plan.furniture
                          if furniture_base_piece(f.piece_id) in families
                          and rect.contains(f.x + f.w // 2, f.y + f.h // 2)), key=lambda f: f.uid)
        if not targets:
            # Carpets still have an intentional open-floor slot in rooms whose
            # physical plan has no bed/hearth; seating needs a real table/desk.
            return None if anchor.startswith("seat_") else (x, y)
        target = targets[0]
        gap = 450
        if anchor in {"seat_south", "hearth_apron"}:
            x, y = target.x + (target.w - width) // 2, target.y + target.h + gap
        elif anchor == "seat_west":
            x, y = target.x - width - gap, target.y + (target.h - depth) // 2
        else:
            x = target.x + target.w + gap
            y = max(rect.y + margin, target.y + (target.h - depth) // 2)
    return x, y


def fixture_slot_candidates(plan, piece_id: str, preferred_room_uid: str = "", *, width=None, depth=None):
    """Finite semantic candidates for a NEW physical fixture or storage binding.

    Returned tuple rows are (room UID, named slot, x, y). Callers must preserve
    the original fixture UID/inventory and never apply these to saved positions.
    Optional dimensions let container profiles retain their real footprints.
    """
    catalog = furnishing_catalog()
    base = furniture_base_piece(piece_id).lower()
    role = next((r for r in catalog["fixture_roles"] if any(word in base for word in r["words"])), None)
    styles = role["styles"] if role else ["work", "store", "living"]
    slots = role["anchors"] if role else ["north_left", "north_right", "west_upper", "east_upper"]
    default_w, default_h = furniture_dimensions(piece_id)
    width, depth = default_w if width is None else width, default_h if depth is None else depth
    rooms = sorted(plan.rooms, key=lambda room: (
        styles.index(_style(room, plan, catalog)) if _style(room, plan, catalog) in styles else len(styles),
        room.uid != preferred_room_uid, room.uid))
    for room in rooms:
        # Shared service galleries are circulation, not fallback workshops.
        if _style(room, plan, catalog) == "passage":
            continue
        for slot in slots:
            pos = _anchor_position(plan, room, catalog["fixture_anchors"][slot], width, depth)
            if pos is not None:
                yield room.uid, slot, *pos


def place_source_fixture(plan, piece_id: str, uid: str, owner_uid: str = "", source_uid: str = "", *,
                         solid: bool = True, preferred_room_uid: str = "", width=None, depth=None):
    """Project one source into a sensible slot without adding capacity/goods."""
    if any(furniture.uid == uid for furniture in plan.furniture):
        return None
    default_w, default_h = furniture_dimensions(piece_id)
    width, depth = default_w if width is None else width, default_h if depth is None else depth
    protected = _protected_routes(plan)
    rooms = {room.uid: room for room in plan.rooms}
    for room_uid, slot, x, y in fixture_slot_candidates(plan, piece_id, preferred_room_uid, width=width, depth=depth):
        room = rooms[room_uid].rect
        if x < room.x + 400 or y < room.y + 400 or x + width > room.x + room.w - 400 or y + depth > room.y + room.h - 400:
            continue
        candidate = InteriorFurniture(uid, furniture_variant(piece_id, uid), x, y, width, depth,
                                      owner_uid, source_uid, solid)
        if _fits(plan, candidate, protected, ()):
            return candidate
    return None


def _protected_routes(plan) -> list[InteriorRect]:
    """Reserve portals and a spine in narrow shared circulation galleries."""
    protected = [InteriorRect(plan.entry_x - 800, plan.entry_y - 1200, 1600, 2000)]
    for stair in getattr(plan, "stairs", ()):
        rect = getattr(stair, "rect", stair)
        protected.append(InteriorRect(rect.x - 350, rect.y - 350, rect.w + 700, rect.h + 700))
    rooms = plan.rooms
    for room in rooms:
        rect = room.rect
        if (room.uid.endswith(":gallery") or any(word in room.name.lower()
                for word in ("gallery", "passage", "aisle", "muster"))):
            if rect.w < rect.h:
                protected.append(InteriorRect(rect.x + rect.w // 2 - 650, rect.y, 1300, rect.h))
            else:
                protected.append(InteriorRect(rect.x, rect.y + rect.h // 2 - 650, rect.w, 1300))
        # Wall gaps open at the centre of the shared boundary. Keep a broad
        # apron on both sides so wardrobes/chairs cannot obstruct doorways.
        for other in rooms:
            if other is room:
                continue
            edge = other.rect
            top, bottom = max(rect.y, edge.y), min(rect.y + rect.h, edge.y + edge.h)
            left, right = max(rect.x, edge.x), min(rect.x + rect.w, edge.x + edge.w)
            if bottom > top and (abs(rect.x - edge.x - edge.w) < 200 or abs(rect.x + rect.w - edge.x) < 200):
                x = rect.x if abs(rect.x - edge.x - edge.w) < 200 else rect.x + rect.w
                mid = (top + bottom) // 2
                if not any(wall.contains(x, mid) for wall in plan.walls):
                    protected.append(InteriorRect(x - 1100, mid - 1000, 2200, 2000))
            if right > left and (abs(rect.y - edge.y - edge.h) < 200 or abs(rect.y + rect.h - edge.y) < 200):
                y = rect.y if abs(rect.y - edge.y - edge.h) < 200 else rect.y + rect.h
                mid = (left + right) // 2
                if not any(wall.contains(mid, y) for wall in plan.walls):
                    protected.append(InteriorRect(mid - 1000, y - 1100, 2000, 2200))
    return protected


def _fits(plan, candidate, protected, occupants) -> bool:
    rect = candidate.rect
    if rect.x < 400 or rect.y < 400 or rect.x + rect.w > plan.width - 400 or rect.y + rect.h > plan.height - 400:
        return False
    if any(rect.overlaps(wall) for wall in plan.walls) or any(rect.overlaps(zone) for zone in (*protected, *occupants)):
        return False
    for furniture in plan.furniture:
        # Preserve walking/interaction aprons around real fixtures, not just
        # absence of exact overlap. Rugs remain clear too: moving a player-owned
        # rug must not make the selected table appear to teleport with it.
        other = furniture.rect
        margin = 350 if furniture.solid and candidate.solid else 120
        clearance = InteriorRect(other.x - margin, other.y - margin,
                                 other.w + 2 * margin, other.h + 2 * margin)
        if rect.overlaps(clearance):
            return False
    # At least one usable edge must have a whole standing apron. A cupboard
    # which fits geometrically but can only be clicked through a wall is invalid.
    if candidate.solid:
        radius = ACTOR_RADIUS + 50
        centres = ((rect.x - radius, rect.y + rect.h // 2),
                   (rect.x + rect.w + radius, rect.y + rect.h // 2),
                   (rect.x + rect.w // 2, rect.y - radius),
                   (rect.x + rect.w // 2, rect.y + rect.h + radius))
        obstacles = tuple(plan.walls) + tuple(f.rect for f in plan.furniture if f.solid)
        if not any(400 <= cx - radius and 400 <= cy - radius
                   and cx + radius <= plan.width - 400 and cy + radius <= plan.height - 400
                   and not any(InteriorRect(cx - radius, cy - radius, 2 * radius, 2 * radius).overlaps(obstacle)
                               for obstacle in obstacles) for cx, cy in centres):
            return False
    return True


def slot_placement_clear(plan, candidate, actors=()) -> bool:
    """Shared collision, doorway/stair protection and interaction-apron check."""
    occupied = [InteriorRect(actor.x - ACTOR_RADIUS - 250, actor.y - ACTOR_RADIUS - 250,
                             (ACTOR_RADIUS + 250) * 2, (ACTOR_RADIUS + 250) * 2)
                for actor in actors if actor.space_id == plan.uid]
    return _fits(plan, candidate, _protected_routes(plan), occupied)


def furnish_plan(plan, registry=None, actors=()) -> int:
    """Add safe, deterministic furnishings without re-rolling saved geometry.

    Existing furniture and occupants are never moved. Stable slot identities
    make repeated preparations idempotent and additions are capped per floor.
    Source UIDs are deliberately empty: these props are not a second physical
    workstation/capacity authority. No inventories or item goods are created.
    """
    catalog = furnishing_catalog()
    prefix = plan.uid + ":furnishing:"
    existing = {f.uid for f in plan.furniture}
    used = sum(uid.startswith(prefix) for uid in existing)
    budget = catalog["maximum_additions"] - used
    if budget <= 0:
        return 0
    protected = _protected_routes(plan)
    occupants = [InteriorRect(actor.x - ACTOR_RADIUS - 250, actor.y - ACTOR_RADIUS - 250,
                              (ACTOR_RADIUS + 250) * 2, (ACTOR_RADIUS + 250) * 2)
                 for actor in actors if actor.space_id == plan.uid]
    added = 0
    # Round-robin across rooms, not room-by-room until the global budget is
    # exhausted. The last room must not be left bare in a large inn or market.
    room_slots = [(room, catalog["styles"][_style(room, plan, catalog)]) for room in sorted(plan.rooms, key=lambda r: r.uid)]
    for index in range(max((len(slots) for _, slots in room_slots), default=0)):
        for room, slots in room_slots:
            if index >= len(slots) or added >= budget:
                continue
            slot = slots[index]
            uid = prefix + room.uid + ":" + slot
            if uid in existing:
                continue
            spec = catalog["slots"][slot]
            piece_id = furniture_variant(spec["piece"], uid)
            if registry is not None and piece_id not in registry.settlement_pieces:
                continue
            # Project the existing hearth/table/desk when present instead of
            # piling a second copy beside it. Seating can form a useful cluster.
            if slot in {"table", "desk", "hearth"} and any(furniture_base_piece(f.piece_id) == furniture_base_piece(piece_id)
                    and room.rect.contains(f.x + f.w // 2, f.y + f.h // 2) for f in plan.furniture):
                continue
            w, h = furniture_dimensions(piece_id)
            rect = room.rect
            if w + 1100 > rect.w or h + 1100 > rect.h:
                continue
            pos = _anchor_position(plan, room, spec, w, h)
            if pos is None:
                continue
            for x, y in (pos,):
                if x < rect.x + 400 or y < rect.y + 400 or x + w > rect.x + rect.w - 400 or y + h > rect.y + rect.h - 400:
                    continue
                candidate = InteriorFurniture(uid, piece_id, x, y, w, h, plan.owner_uid,
                                              source_uid="", solid=not furniture_visual(piece_id)["flat"])
                if _fits(plan, candidate, protected, occupants):
                    plan.furniture.append(candidate)
                    existing.add(uid)
                    added += 1
                    break
    return added
