"""Contextual salvage finds, projected into the existing goods authorities.

This catalog selects item identities only. Callers own placement and transfer:
settlement finds enter town stocks once, containers withdraw those stocks, and
wilderness/dungeon finds become persistent GroundPile/ContainerState goods.
"""
from __future__ import annotations

from functools import lru_cache
import json

from worldseed.config import DATA_DIR
from worldseed.core.rng import hash_u64


PROFILE_CONTEXTS = {
    "core:household_chest": ("household",),
    "core:wardrobe": ("wardrobe", "textile"),
    "core:pantry_cabinet": ("pantry", "kitchen"),
    "core:inn_barrel": ("inn", "pantry", "kitchen"),
    "core:armory_locker": ("armory", "metal"),
    "core:tool_chest": ("workshop", "wood", "metal"),
    "core:supply_crate": ("workyard", "workshop", "wood", "metal"),
    "core:grain_bin": ("grain", "farm"),
    "core:medicine_cabinet": ("medicine", "apothecary"),
    "core:archive_bookcase": ("archive", "scribe"),
    "core:tabletop": ("household", "pantry", "kitchen", "tabletop"),
}

BUILDING_CONTEXTS = {
    "residence": ("household", "wardrobe", "pantry"),
    "inn": ("inn", "pantry", "household"),
    "barracks": ("armory", "wardrobe"),
    "watchhouse": ("armory", "wardrobe"),
    "archive": ("archive", "scribe"),
    "school": ("archive", "scribe"),
    "shrine": ("archive", "household"),
    "outskirt_camp": ("household", "workyard"),
    "smithy": ("metal", "armory", "workshop"),
    "workshop": ("wood", "workshop", "workyard"),
    "mill": ("grain", "farm", "workshop"),
    "fishery": ("fishery", "pantry", "workyard"),
    "barn": ("grain", "farm", "workyard"),
    "clinic": ("medicine", "apothecary"),
    "market": ("household", "workyard", "pantry"),
    "bakery": ("kitchen", "pantry", "grain"),
    "brewery": ("inn", "kitchen", "pantry"),
    "butcher": ("pantry", "kitchen", "workyard"),
    "weavery": ("wardrobe", "textile"),
    "tannery": ("leather", "workshop", "wardrobe"),
    "pottery": ("pottery", "kitchen", "workshop"),
    "mason_yard": ("stone", "workshop", "workyard"),
}


@lru_cache(maxsize=1)
def misc_catalog() -> tuple[dict, ...]:
    raw = json.loads((DATA_DIR / "crafting_expansion.json").read_text(encoding="utf-8"))
    return tuple(raw.get("misc", ()))


def candidates(registry, contexts=(), *, source=None, terrain_id=None):
    wanted = set(contexts)
    return tuple(row for row in misc_catalog()
                 if row["item_id"] in registry.items
                 and (source is None or row.get("source") == source)
                 and (not wanted or wanted.intersection(row.get("loot_contexts", ())))
                 and (terrain_id is None or terrain_id in row.get("habitats", ())))


def select_misc(seed: bytes, domain: str, identity: str, rows, count: int = 1) -> dict[str, int]:
    """Bounded, named deterministic weighted selection; no simulation RNG draw."""
    ordered = sorted(rows, key=lambda row: row["item_id"])
    weighted = [(row["item_id"], {"common": 100, "uncommon": 25, "rare": 3}.get(row.get("rarity"), 100))
                for row in ordered]
    total = sum(weight for _, weight in weighted)
    if total <= 0:
        return {}
    out = {}
    for slot in range(max(0, min(12, int(count)))):
        roll = int(hash_u64(seed, domain, identity, slot) % total)
        for iid, weight in weighted:
            if roll < weight:
                out[iid] = out.get(iid, 0) + 1
                break
            roll -= weight
    return out


def provision_village(state, registry, seed, town, structures) -> int:
    """Give each prepared village one bounded origin batch of weathered goods.

    These are initial household/workshop refuse, like initial food and tools,
    not ongoing production. The marker survives collecting goods, cache rebuild
    and save/load; physical inventories subsequently debit the same town stock.
    """
    marker = "salvage-village-stock:" + str(town.uid)
    if marker in state.resource_depletion:
        return 0
    village = candidates(registry, source="village")
    if not village:
        return 0
    made = 0
    for structure in sorted((s for s in structures if not s.destroyed), key=lambda s: s.uid)[:64]:
        contexts = BUILDING_CONTEXTS.get(str(structure.function), ("household", "workyard"))
        rows = candidates(registry, contexts, source="village") or village
        for iid, qty in select_misc(seed, "salvage-village-origin", structure.uid, rows, 8).items():
            town.stocks[iid] = max(0, int(town.stocks.get(iid, 0))) + qty
            made += qty
    state.resource_depletion[marker] = state.clock_minute
    return made


def withdraw_misc(state, registry, seed, town, container, contexts=(), *, count=2) -> int:
    """Transfer a once-only expansion batch into existing real storage."""
    marker = "salvage-storage-stock:" + str(container.uid)
    if marker in state.resource_depletion:
        return 0
    rows = candidates(registry, contexts or PROFILE_CONTEXTS.get(container.profile_id, ()), source="village")
    available = tuple(row for row in rows if int(town.stocks.get(row["item_id"], 0)) > 0)
    from worldseed.systems.physical_goods import SettlementPhysicalGoodsSystem
    goods = SettlementPhysicalGoodsSystem(state, registry)
    wanted = select_misc(seed, "salvage-storage-allocation", container.uid, available, count)
    transfer = goods.stage_from_settlement(
        town, container, state.clock_minute, items=wanted,
        source_kind="household_refuse", source_uid=str(town.uid),
    )
    state.resource_depletion[marker] = state.clock_minute
    return sum(transfer.items.values()) if transfer else 0
