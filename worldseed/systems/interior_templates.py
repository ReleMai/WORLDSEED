"""Validated deterministic indoor room grammars, independent of rendering."""
from __future__ import annotations

import json
from functools import lru_cache

from worldseed.config import DATA_DIR
from worldseed.core.rng import hash_u64
from worldseed.systems.interior_state import InteriorRect, InteriorRoom


@lru_cache(maxsize=1)
def interior_profiles() -> tuple[dict, ...]:
    data = json.loads((DATA_DIR / "interior_templates.json").read_text(encoding="utf-8"))
    if data.get("version") != 3:
        raise ValueError("Unsupported interior template catalog version")
    profiles = data.get("profiles", [])
    if not isinstance(profiles, list) or not profiles:
        raise ValueError("Interior profile catalog must be a nonempty list")
    seen = set()
    for profile in profiles:
        if not isinstance(profile, dict):
            raise ValueError("Interior profile must be an object")
        uid = profile.get("id", "")
        if not isinstance(uid, str) or not uid.startswith("core:") or uid in seen:
            raise ValueError("Invalid or duplicate interior profile identity")
        seen.add(uid)
        if profile.get("geometry") not in {"front_hall", "side_hall", "central_hall", "courtyard_hall"}:
            raise ValueError("Invalid interior room grammar")
        if not all(type(profile.get(key)) is int and 10000 <= profile[key] <= 30000 for key in ("width", "height")):
            raise ValueError("Invalid interior profile dimensions")
        if not isinstance(profile.get("rooms"), list) or not 2 <= len(profile["rooms"]) <= 6:
            raise ValueError("Invalid interior profile room budget")
        if any(not isinstance(name, str) or not name.strip() for name in profile["rooms"]):
            raise ValueError("Interior room names must be nonempty strings")
        if (not isinstance(profile.get("functions"), list) or not profile["functions"]
                or any(not isinstance(name, str) or not name for name in profile["functions"])
                or not isinstance(profile.get("hall"), str) or not profile["hall"].strip()):
            raise ValueError("Interior profile requires functions and a common room")
        if "forms" in profile and (not isinstance(profile["forms"], list) or any(not isinstance(form, str) for form in profile["forms"])):
            raise ValueError("Interior exterior-form selectors must be a list of strings")
    return tuple(profiles)


def profile_for(structure, *, variant_id: str = "") -> dict:
    profiles = interior_profiles()
    choices = [p for p in profiles if structure.function in p["functions"]]
    if not choices:
        return next(p for p in profiles if "*" in p["functions"])
    form_choices = [p for p in choices if getattr(structure, "building_form", "") in p.get("forms", ())]
    choices = form_choices or choices
    selected = sorted(choices, key=lambda p: p["id"])[hash_u64(b"interior-template-v3", "interior-profile", structure.uid) % len(choices)]
    from worldseed.systems.building_variants import building_variant
    variant = building_variant(structure, variant_id=variant_id)
    if variant is None:
        return selected
    # Preserve familiar layout IDs and form-specific compatibility selectors;
    # only NEWly constructed plans consume the authored variant dimensions and
    # room grammar. Existing persisted rooms are never rebuilt on inspection.
    if not form_choices:
        selected = next(p for p in profiles if p['id'] == variant['interior_profile'])
    return {**selected, **variant['interior'], 'rooms': list(variant['interior']['rooms'])}


def _wall_with_gap(walls: list[InteriorRect], *, vertical: bool, position: int, start: int, end: int, centre: int) -> None:
    thickness, gap = 180, 1500
    a, b = max(start, centre - gap // 2), min(end, centre + gap // 2)
    if a > start:
        walls.append(InteriorRect(position - thickness // 2, start, thickness, a - start) if vertical else InteriorRect(start, position - thickness // 2, a - start, thickness))
    if b < end:
        walls.append(InteriorRect(position - thickness // 2, b, thickness, end - b) if vertical else InteriorRect(b, position - thickness // 2, end - b, thickness))


def rooms_for_profile(space_id: str, profile: dict, width: int, height: int, source_rooms=()):
    """Connected layouts; private rooms open onto a circulation gallery."""
    inset, thickness = 250, 180
    walls = [InteriorRect(0, 0, width, thickness), InteriorRect(0, 0, thickness, height), InteriorRect(width - thickness, 0, thickness, height), InteriorRect(0, height - thickness, width, thickness)]
    names = profile["rooms"]
    sources = sorted(source_rooms, key=lambda r: r.uid)
    rects = []
    grammar = profile["geometry"]
    gallery = None
    if grammar == "courtyard_hall":
        # Public buildings need an actual common room, not four long strips.
        # The service spine reaches compact rear rooms without passing through
        # someone else's bedroom or a store of merchandise.
        split = height * 3 // 5
        left, right = width // 2 - 1250, width // 2 + 1250
        hall = InteriorRect(inset, split, width - 2 * inset, height - split - inset)
        gallery = InteriorRect(left, inset, right - left, split - inset)
        _wall_with_gap(walls, vertical=False, position=split, start=inset,
                       end=width - inset, centre=width // 2)
        side_counts = ((len(names) + 1) // 2, len(names) // 2)
        for index in range(len(names)):
            side, row = index % 2, index // 2
            count = side_counts[side]
            top = inset + (split - inset) * row // count
            bottom = inset + (split - inset) * (row + 1) // count
            x, end_x = (inset, left) if side == 0 else (right, width - inset)
            rects.append(InteriorRect(x, top, end_x - x, bottom - top))
            if row:
                walls.append(InteriorRect(x, top - thickness // 2, end_x - x, thickness))
            _wall_with_gap(walls, vertical=True, position=left if side == 0 else right,
                           start=top, end=bottom, centre=(top + bottom) // 2)
        entry = width // 2, height - 700
    elif grammar == "front_hall":
        split = height - max(3000, height // 3)
        hall = InteriorRect(inset, split, width - 2 * inset, height - split - inset)
        for index in range(len(names)):
            left = inset + (width - 2 * inset) * index // len(names)
            right = inset + (width - 2 * inset) * (index + 1) // len(names)
            rects.append(InteriorRect(left, inset, right - left, split - inset))
            if index:
                walls.append(InteriorRect(left - thickness // 2, inset, thickness, split - inset))
            _wall_with_gap(walls, vertical=False, position=split, start=left, end=right, centre=(left + right) // 2)
        entry = width // 2, height - 700
    elif grammar == "side_hall":
        split = max(3200, width // 3)
        hall = InteriorRect(inset, inset, split - inset, height - 2 * inset)
        for index in range(len(names)):
            top = inset + (height - 2 * inset) * index // len(names)
            bottom = inset + (height - 2 * inset) * (index + 1) // len(names)
            rects.append(InteriorRect(split, top, width - split - inset, bottom - top))
            if index:
                walls.append(InteriorRect(split, top - thickness // 2, width - split - inset, thickness))
            _wall_with_gap(walls, vertical=True, position=split, start=top, end=bottom, centre=(top + bottom) // 2)
        entry = (inset + split) // 2, height - 700
    else:
        left, right = width // 2 - 1800, width // 2 + 1800
        hall = InteriorRect(left, inset, right - left, height - 2 * inset)
        side_counts = ((len(names) + 1) // 2, len(names) // 2)
        for index in range(len(names)):
            side, row = index % 2, index // 2
            count = side_counts[side]
            top = inset + (height - 2 * inset) * row // count
            bottom = inset + (height - 2 * inset) * (row + 1) // count
            x, end_x = (inset, left) if side == 0 else (right, width - inset)
            rects.append(InteriorRect(x, top, end_x - x, bottom - top))
            if row:
                walls.append(InteriorRect(x, top - thickness // 2, end_x - x, thickness))
            _wall_with_gap(walls, vertical=True, position=left if side == 0 else right, start=top, end=bottom, centre=(top + bottom) // 2)
        entry = width // 2, height - 700
    rooms = [InteriorRoom(space_id + ":hall", profile["hall"], hall)]
    rooms.extend(InteriorRoom(sources[i].uid if i < len(sources) else space_id + ":room:" + str(i), name, rect) for i, (name, rect) in enumerate(zip(names, rects)))
    if gallery is not None:
        rooms.append(InteriorRoom(space_id + ":gallery", "Service gallery", gallery))
    return rooms, walls, entry
