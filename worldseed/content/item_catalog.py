"""Shared, simulation-free item groups and deterministic catalog ordering.

Classification is authoring metadata. Gameplay continues to use item IDs,
tags and physical qualities; sorting never changes those fields.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TypeVar


ITEM_TYPE_ORDER = (
    "resource", "plant", "herb", "food", "seed", "material", "medicine",
    "tool", "weapon", "ammo", "armor", "utility", "misc", "special",
)
ITEM_TYPE_LABELS = {
    "resource": "Resources", "plant": "Plants", "herb": "Herbs",
    "food": "Food", "seed": "Seeds & Farming", "material": "Materials",
    "medicine": "Medicine", "tool": "Tools", "weapon": "Weapons",
    "ammo": "Ammo", "armor": "Armor", "utility": "Utility & Containers",
    "misc": "Miscellaneous Finds", "special": "Special",
}
ITEM_SUBCATEGORY_ORDER = {
    "plant": ("wild", "farmed"),
    "herb": ("cooking", "medical", "poisonous"),
    "misc": ("hardware", "woodwork", "textiles", "leatherwork", "ceramics",
             "glassware", "paperwork", "stonework", "mechanisms", "provisions", "animal_parts"),
}
ITEM_SUBCATEGORY_LABELS = {
    ("plant", "wild"): "Wild Plants", ("plant", "farmed"): "Farmed Plants",
    ("herb", "cooking"): "Cooking Herbs", ("herb", "medical"): "Medical Herbs",
    ("herb", "poisonous"): "Poisonous Herbs",
    ("misc", "hardware"): "Damaged Hardware", ("misc", "woodwork"): "Broken Woodwork",
    ("misc", "textiles"): "Worn Textiles", ("misc", "leatherwork"): "Worn Leatherwork",
    ("misc", "ceramics"): "Broken Ceramics", ("misc", "glassware"): "Broken Glassware",
    ("misc", "paperwork"): "Discarded Paperwork", ("misc", "stonework"): "Broken Stonework",
    ("misc", "mechanisms"): "Damaged Mechanisms", ("misc", "provisions"): "Spent Provisions",
    ("misc", "animal_parts"): "Animal Parts",
}

_MISC_FAMILIES = {
    "metal": "hardware", "wood": "woodwork", "cloth": "textiles",
    "leather": "leatherwork", "ceramic": "ceramics", "glass": "glassware",
    "paper": "paperwork", "stone": "stonework", "mixed": "mechanisms",
    "provisions": "provisions",
}
_COOKING_HERBS = {
    "core:dandelion_greens", "core:moonmint_sprig", "core:sunspice_rhizome", "core:frost_sage_branch",
    "core:saffron_crocus_tuft",
}
_MEDICAL_HERBS = {
    "core:medicinal_herb", "core:yarrow", "core:plantain_leaf", "core:silverleaf_sprig",
    "core:ghost_orchid_stem", "core:blue_lotus_stalk",
    "core:marsh_amber_bulb", "core:crimson_stonecrop_crown",
}
_REUSABLE_POTTERY = {
    "core:ceramic_mould", "core:stoneware_crucible", "core:ceramic_distillation_coil",
    "core:porous_filter_candle",
}


def _field(item, key: str, default=""):
    return item.get(key, default) if isinstance(item, Mapping) else getattr(item, key, default)


def item_sort_key(item) -> tuple:
    """Use the same order for JSON records, runtime definitions and catalogs.

    Mods may author extra groups. They sort after core groups with a stable
    category/subcategory/name/ID tie-break instead of depending on load order.
    Core authoring validation remains strict in validate_item_group().
    """
    category = str(_field(item, "category"))
    subcategory = str(_field(item, "subcategory"))
    known = ITEM_SUBCATEGORY_ORDER.get(category, ())
    return (
        ITEM_TYPE_ORDER.index(category) if category in ITEM_TYPE_ORDER else len(ITEM_TYPE_ORDER),
        category.casefold(),
        known.index(subcategory) if subcategory in known else len(known),
        subcategory.casefold(),
        str(_field(item, "name")).casefold(),
        str(_field(item, "id")),
    )


T = TypeVar("T")


def ordered_items(items: Iterable[T]) -> list[T]:
    return sorted(items, key=item_sort_key)


def validate_item_group(item) -> None:
    category = str(_field(item, "category"))
    subcategory = str(_field(item, "subcategory"))
    if category not in ITEM_TYPE_ORDER:
        raise ValueError(f"Unknown item category {category!r} on {_field(item, 'id')}")
    known = ITEM_SUBCATEGORY_ORDER.get(category)
    if known is not None and subcategory not in known:
        raise ValueError(f"Unknown {category} subcategory {subcategory!r} on {_field(item, 'id')}")
    if known is None and subcategory:
        raise ValueError(f"Unexpected {category} subcategory {subcategory!r} on {_field(item, 'id')}")


def classified_item(raw: Mapping) -> dict:
    """Copy one authored record, correcting only its category metadata."""
    item = dict(raw)
    iid = str(item["id"])
    tags = set(item.get("tags", ()))
    category, subcategory = item.get("category", "misc"), item.get("subcategory", "")
    if "animal_part" in tags:
        category, subcategory = "misc", "animal_parts"
    elif "village_salvage" in tags:
        families = [group for tag, group in _MISC_FAMILIES.items() if tag in tags]
        if len(families) != 1:
            raise ValueError(f"Village find needs one physical family: {iid}")
        category, subcategory = "misc", families[0]
    elif iid in _COOKING_HERBS:
        category, subcategory = "herb", "cooking"
    elif iid in _MEDICAL_HERBS:
        category, subcategory = "herb", "medical"
    elif "seed" in tags:
        category, subcategory = "seed", ""
    elif "crop" in tags:
        category, subcategory = "plant", "farmed"
    elif "fishing_line" in tags:
        category, subcategory = "tool", ""
    elif iid in _REUSABLE_POTTERY:
        category, subcategory = "utility", ""
    item["category"] = category
    if subcategory:
        item["subcategory"] = subcategory
    else:
        item.pop("subcategory", None)
    validate_item_group(item)
    return item


def canonical_item_catalog(items: Iterable[Mapping]) -> list[dict]:
    return ordered_items(classified_item(item) for item in items)
