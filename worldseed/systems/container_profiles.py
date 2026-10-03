"""Bounded, validated storage styles and building stock-selection tables.

Tables describe how existing settlement goods are reserved into physical storage;
they are not a random loot generator and never manufacture missing supplies.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class ContainerProfile:
    uid: str
    name: str
    piece_id: str
    source_id: str
    width: int
    height: int
    rooms: tuple[str, ...]
    lock_level: int
    lock_chance: int
    capacity_mass_g: int
    capacity_volume_ml: int
    loot: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BuildingStorageProfile:
    primary: str
    inside: tuple[str, ...]
    outside: bool = False
    stock: tuple[str, ...] = ()


def parse_catalog(raw: dict):
    if raw.get("version") != 1:
        raise ValueError("Unsupported container profile catalog")
    profiles = {}
    for row in raw.get("profiles", []):
        uid = row["id"]
        if not isinstance(uid, str) or not uid.startswith("core:") or any(c.isspace() for c in uid) or uid in profiles:
            raise ValueError("Invalid or duplicate container profile ID")
        width, height = row["size"]
        values = (width, height, row["capacity_mass_g"], row["capacity_volume_ml"])
        if any(type(v) is not int or v <= 0 for v in values) or max(width, height) > 3000:
            raise ValueError("Invalid container capacity or size")
        if not all(type(row[k]) is int and 0<=row[k]<=100 for k in ('lock_level','lock_chance')):
            raise ValueError("Invalid container lock profile")
        if not row.get("loot") or any(not isinstance(v, str) or ":" not in v for v in row["loot"]):
            raise ValueError("Invalid container stock table")
        if any(not isinstance(row[k],str) or ':' not in row[k] or any(c.isspace() for c in row[k])
               for k in ('piece_id','source_id')):
            raise ValueError("Invalid container content reference")
        profiles[uid] = ContainerProfile(uid, row["name"], row["piece_id"], row["source_id"], width, height,
                                         tuple(row["rooms"]), row["lock_level"], row["lock_chance"],
                                         row["capacity_mass_g"], row["capacity_volume_ml"], tuple(row["loot"]))
    buildings = {}
    for function, row in raw.get("buildings", {}).items():
        if row["primary"] not in profiles or len(row.get("inside", [])) > 3 or any(uid not in profiles for uid in row.get("inside", [])):
            raise ValueError("Unknown or excessive building container profile")
        buildings[function] = BuildingStorageProfile(row["primary"], tuple(row.get("inside", [])),
                                                    bool(row.get("outside", False)), tuple(row.get("stock", [])))
    return MappingProxyType(profiles), MappingProxyType(buildings)


@lru_cache(maxsize=1)
def catalog():
    path = Path(__file__).resolve().parents[1] / "data" / "container_profiles.json"
    return parse_catalog(json.loads(path.read_text(encoding="utf-8")))


def container_profile(profile_id: str) -> ContainerProfile | None:
    return catalog()[0].get(str(profile_id))


def building_storage_profile(function: str) -> BuildingStorageProfile | None:
    return catalog()[1].get(str(function))


def validate_catalog(registry) -> None:
    """Reject dangling content references before any goods are allocated."""
    profiles,buildings=catalog()
    for profile in profiles.values():
        if profile.piece_id not in registry.settlement_pieces or profile.source_id not in registry.structures:
            raise ValueError(f'Unknown storage content reference: {profile.uid}')
        if any(iid not in registry.items for iid in profile.loot):
            raise ValueError(f'Unknown storage loot item: {profile.uid}')
    for function,building in buildings.items():
        if any(iid not in registry.items for iid in building.stock):
            raise ValueError(f'Unknown building storage item: {function}')
