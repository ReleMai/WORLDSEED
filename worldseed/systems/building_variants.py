"""Authored building styles projected from stable physical structure identity.

This catalog changes appearance and indoor grammar, not the building's footprint,
capacity, owner, profession or economic authority. Loot lists select only goods
that already exist in a settlement's stock ledger.
"""
from __future__ import annotations

from functools import lru_cache
import json
import re
from types import MappingProxyType

from worldseed.config import DATA_DIR
from worldseed.core.rng import hash_u64


_ID = re.compile(r"core:[a-z][a-z0-9_]*\Z")
_ASSET = re.compile(r"[a-z][a-z0-9_]*\Z")
_GRAMMARS = {"front_hall", "side_hall", "central_hall", "courtyard_hall"}


def parse_catalog(raw: dict) -> tuple[dict, ...]:
    """Reject malformed styles before storage or interior preparation uses them."""
    if raw.get("version") != 1 or not isinstance(raw.get("variants"), list) or not raw["variants"]:
        raise ValueError("Unsupported or empty building variant catalog")
    seen, assets, tables, variants = set(), set(), set(), []
    for row in raw["variants"]:
        if not isinstance(row, dict):
            raise ValueError("Building variant must be an object")
        uid, asset = row.get("id", ""), row.get("asset", "")
        if (not isinstance(uid, str) or not _ID.fullmatch(uid) or uid in seen
                or not isinstance(asset, str) or not _ASSET.fullmatch(asset) or asset in assets
                or uid != "core:" + asset):
            raise ValueError("Invalid or duplicate building variant identity")
        seen.add(uid); assets.add(asset)
        for key in ("name", "function"):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise ValueError("Building variant requires a name and function")
        for key in ("floor", "wall", "interior_profile"):
            if not isinstance(row.get(key), str) or not _ID.fullmatch(row[key]):
                raise ValueError("Invalid building variant visual or profile reference")
        loot = row.get("loot")
        if (not isinstance(loot, list) or not 2 <= len(loot) <= 12
                or any(not isinstance(iid, str) or not _ID.fullmatch(iid) for iid in loot)
                or len(set(loot)) != len(loot)):
            raise ValueError("Invalid building variant loot table")
        fingerprint = tuple(sorted(loot))
        if fingerprint in tables:
            raise ValueError("Building variants must have genuinely distinct loot tables")
        tables.add(fingerprint)
        interior = row.get("interior", {})
        if (not isinstance(interior, dict) or interior.get("geometry") not in _GRAMMARS
                or any(type(interior.get(key)) is not int or not 10000 <= interior[key] <= 30000
                       for key in ("width", "height"))
                or not isinstance(interior.get("rooms"), list) or not 2 <= len(interior["rooms"]) <= 6
                or any(not isinstance(name, str) or not name.strip() for name in interior["rooms"])
                or not isinstance(interior.get("hall"), str) or not interior["hall"].strip()):
            raise ValueError("Invalid building variant interior grammar")
        variants.append(MappingProxyType({**row, "loot": tuple(loot),
                                          "interior": MappingProxyType({**interior, "rooms": tuple(interior["rooms"])})}))
    return tuple(sorted(variants, key=lambda row: row["id"]))


@lru_cache(maxsize=1)
def catalog() -> tuple[dict, ...]:
    return parse_catalog(json.loads((DATA_DIR / "building_variants.json").read_text(encoding="utf-8")))


def variant_by_id(uid: str) -> dict | None:
    return next((row for row in catalog() if row["id"] == str(uid)), None)


def building_variant(structure, *, variant_id: str = "") -> dict | None:
    """Read-only stable selection shared by exterior, interior and stock seeding.

    A saved explicit variant is authoritative; an unknown retired style falls
    back to existing presentation rather than silently choosing another style.
    """
    function = str(getattr(structure, "function", ""))
    pinned = str(variant_id or getattr(structure, "variant_id", ""))
    if pinned:
        result = variant_by_id(pinned)
        return result if result is not None and result["function"] == function else None
    uid = str(getattr(structure, "uid", ""))
    choices = tuple(row for row in catalog() if row["function"] == function)
    if not choices or not uid:
        return None
    index = hash_u64(b"building-variants-v1", "building-variant", function, uid) % len(choices)
    return choices[index]


def validate_catalog(registry) -> None:
    """Content references are checked without generating or reserving goods."""
    from worldseed.systems.interior_templates import interior_profiles

    profiles = {profile["id"]: profile for profile in interior_profiles()}
    for variant in catalog():
        profile = profiles.get(variant["interior_profile"])
        if profile is None or variant["function"] not in profile["functions"]:
            raise ValueError(f"Unknown or mismatched variant interior profile: {variant['id']}")
        if any(iid not in registry.items for iid in variant["loot"]):
            raise ValueError(f"Unknown variant loot item: {variant['id']}")
