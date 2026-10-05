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
    if data.get("version") != 1 or not 1 <= data.get("maximum_additions", 0) <= 32:
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
    for slot, row in data["slots"].items():
        if row.get("piece") not in data["pieces"] or any(not 0 <= row.get(key, -1) <= 1 for key in ("x", "y")):
            raise ValueError("Invalid furnishing slot: " + slot)
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
    if any(rect.overlaps(wall) for wall in plan.walls) or any(rect.overlaps(zone) for zone in protected + occupants):
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
    return True


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
    room_slots = [(room, catalog["styles"][_style(room, plan, catalog)]) for room in plan.rooms]
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
            cx = rect.x + 550 + round((rect.w - 1100) * spec["x"])
            cy = rect.y + 550 + round((rect.h - 1100) * spec["y"])
            base_x = max(rect.x + 550, min(rect.x + rect.w - w - 550, cx - w // 2))
            base_y = max(rect.y + 550, min(rect.y + rect.h - h - 550, cy - h // 2))
            for dx, dy in ((0, 0), (-600, 0), (600, 0), (0, -600), (0, 600), (-600, -600), (600, 600)):
                x, y = base_x + dx, base_y + dy
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
