"""Author shared material families and mass-safe recovered/refined craft costs.

One logical wood unit is at least 120 g, metal 80 g, textile fiber 10 g.
Recipe-local input_units convert physical stock to those equivalents; unrelated
recipes keep their exact legacy costs. Existing IDs, art and outputs are reused.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "worldseed" / "data"

# Item quality describes the stock before the player's skill/process modifies
# it. Recovered material can be refined through the existing processing trees.
ITEM_PROFILES = {
    "core:wood_pieces": (25, "recovered", ("wood_stock", "short_haft", "shaft_material")),
    "core:metal_scraps": (25, "recovered", ("metal_stock",)),
    "core:plant_scraps": (20, "recovered", ()),
    "core:cloth_scraps": (25, "recovered", ("textile_fiber",)),
    "core:leather_scraps": (30, "recovered", ()),
    "core:tool_handles": (45, "recovered", ("wood_stock", "short_haft", "shaft_material")),
    "core:wood": (60, "raw", ("wood_stock", "short_haft", "shaft_material")),
    "core:stout_branch": (55, "raw", ("wood_stock", "short_haft", "shaft_material")),
    "core:hardwood_blank": (80, "refined", ("wood_stock",)),
    "core:planed_board": (85, "refined", ("wood_stock", "short_haft", "shaft_material")),
    "core:shaft_bundle": (75, "refined", ("wood_stock", "short_haft", "shaft_material")),
    "core:iron_bloom": (80, "refined", ("metal_stock",)),
    "core:steel_billet": (95, "refined", ("metal_stock",)),
    "core:iron_tool_blank": (85, "refined", ("metal_stock",)),
    "core:fiber": (75, "refined", ("textile_fiber", "fiber", "textile", "prepared_fiber", "spinnable_plant_fiber")),
    "core:pasture_fiber_bundle": (65, "raw", ("textile_fiber",)),
    "core:spun_yarn": (80, "refined", ()),
    "core:plant_cordage": (75, "refined", ("plant", "textile", "binding_material")),
    "core:sinew_cord": (70, "refined", ("binding_material", "animal_fiber")),
    "core:binding_cord": (85, "refined", ()),
}

WOOD_UNITS = {
    "core:wood_pieces": 1, "core:wood": 25, "core:stout_branch": 5,
    "core:hardwood_blank": 10, "core:planed_board": 3,
    "core:tool_handles": 1, "core:shaft_bundle": 1,
}
METAL_UNITS = {
    "core:metal_scraps": 1, "core:iron_bloom": 25,
    "core:steel_billet": 22, "core:iron_tool_blank": 16,
}
HAFT_UNITS = {**WOOD_UNITS, "core:stout_branch": 2, "core:tool_handles": 2}
SHAFT_UNITS = {**WOOD_UNITS, "core:stout_branch": 6}


def profile(inputs, tags, units, description):
    return {"inputs": inputs, "input_tags": tags, "input_units": units,
            "material_quality": True, "discovery_items": list(inputs),
            "discovery_tags": list(tags), "description": description}


RECIPE_PROFILES = {
    "core:stone_knife": profile({}, {"sharp_edge": 1, "short_haft": 2, "binding_material": 1}, HAFT_UNITS,
        "Haft a sharp stone edge using two wood-piece equivalents and secure it with cord. One branch or fitted handle replaces several recovered pieces; sound stock gives a stronger knife."),
    "core:stone_axe": profile({"core:stone_flake": 1, "core:stone": 1}, {"shaft_material": 6, "binding_material": 1}, SHAFT_UNITS,
        "Shape a stone axe head, fit six recovered wood-piece equivalents or one sound branch, and lash it with cord. Better stock improves the finished tool."),
    "core:stone_pick": profile({"core:stone": 2}, {"shaft_material": 6, "binding_material": 1}, SHAFT_UNITS,
        "Fit two hard stones to a lashed shaft: six recovered wood-piece equivalents or one sound branch. Prepared hardwood gives a stronger mining pick."),
    "core:stone_hammer": profile({"core:stone": 1}, {"shaft_material": 6, "binding_material": 1}, SHAFT_UNITS,
        "Secure a hammerstone to a shaft made from six recovered wood-piece equivalents or one sound branch, then bind the head with cord."),
    "core:crude_hoe": profile({"core:stone": 1}, {"sharp_edge": 1, "shaft_material": 6, "binding_material": 1}, SHAFT_UNITS,
        "Shape a crude stone edge, fit six recovered wood-piece equivalents or one sound branch, and bind the head. Refined hardwood improves the hoe's durability."),
    "core:iron_sword": profile({"core:hide": 1}, {"metal_stock": 25, "wood_stock": 25}, {**METAL_UNITS, **WOOD_UNITS},
        "Forge a sword from 25 metal and 25 wood equivalents with a hide grip. Sorted scraps and recovered timber share the same process as one iron bloom and one timber stock; refined material gives better damage, durability and value."),
    "core:iron_pick": profile({"core:fiber": 1}, {"metal_stock": 25, "wood_stock": 25}, {**METAL_UNITS, **WOOD_UNITS},
        "Forge and haft a mining pick from 25 metal and 25 wood equivalents, bound with fiber. One iron bloom and one timber stock replace many recovered parts; sound material gives a more durable tool."),
    "core:iron_helmet": profile({"core:hide": 1}, {"metal_stock": 25}, METAL_UNITS,
        "Forge 25 metal equivalents into a helmet and line it with hide. One iron bloom replaces 25 sorted metal scraps, improving durability and value."),
    "core:short_bow": profile({"core:plant_cordage": 2}, {"wood_stock": 8}, WOOD_UNITS,
        "Tiller and lash eight recovered wood-piece equivalents or sound timber into a self bow, then string it with two cords. Continuous refined stock makes a stronger and more durable bow."),
    "core:wooden_bowl": profile({}, {"wood_stock": 3}, WOOD_UNITS,
        "Carve and fit three recovered wood-piece equivalents or sound timber into a bowl. Better prepared wood gives a more durable, valuable vessel."),
    "core:steel_sword": profile({"core:steel_billet": 1, "core:hide": 1}, {"wood_stock": 25}, WOOD_UNITS,
        "Forge a steel billet and fit a hide-wrapped grip using 25 wood equivalents. Recovered wood and refined timber use the same recipe; the source quality changes the finished sword."),
    "core:steel_pick": profile({"core:steel_billet": 1, "core:fiber": 1}, {"wood_stock": 25}, WOOD_UNITS,
        "Forge a steel billet into a pick and fit 25 wood equivalents with fiber bindings. Better shaft stock improves the tool's durability."),
    "core:craft_spun_yarn": profile({}, {"textile_fiber": 30},
        {"core:cloth_scraps": 1, "core:fiber": 15, "core:pasture_fiber_bundle": 20},
        "Spin two yarn bundles from 30 textile-fiber equivalents: two prepared fiber bundles or 30 cleaned cloth scraps. Refined fiber takes fewer physical pieces and produces stronger yarn."),
}
QUALITY_ONLY_RECIPES = ("core:steel_helmet",)


def apply_item_profiles(items):
    for item in items:
        # The historical RC7 tool rewrites this edge before reapplying profiles.
        if item["id"] == "core:stone_flake" and "sharp_edge" not in item.get("tags", ()):
            item.setdefault("tags", []).append("sharp_edge")
        entry = ITEM_PROFILES.get(item["id"])
        if entry is None:
            continue
        quality, source, tags = entry
        item.update(crafting_quality=quality, crafting_source=source)
        for tag in tags:
            if tag not in item.get("tags", ()):
                item.setdefault("tags", []).append(tag)
    return items


def apply_recipe_profiles(recipes):
    for recipe in recipes:
        values = RECIPE_PROFILES.get(recipe["id"])
        if values is not None:
            recipe.update(deepcopy(values))
        elif recipe["id"] in QUALITY_ONLY_RECIPES:
            recipe["material_quality"] = True
    return recipes


def audit_profiles(items, recipes):
    """Conservative per-equivalent bound also covers mixed/overlapping inputs.

    Flooring stock units and rounding physical consumption upward can only add
    mass. Summing the minimum grams/equivalent therefore bounds every choice,
    including one physical item allocated between multiple matching tags.
    """
    catalog = {item["id"]: item for item in items}
    for recipe in recipes:
        if recipe["id"] not in RECIPE_PROFILES:
            continue
        minimum = Fraction(sum(catalog[iid]["mass_g"] * n for iid, n in recipe["inputs"].items()))
        for tag, demand in recipe["input_tags"].items():
            options = [Fraction(item["mass_g"], recipe["input_units"].get(item["id"], 1))
                       for item in items if tag in item.get("tags", ())]
            if not options:
                raise ValueError(f"No physical stock for {recipe['id']}: {tag}")
            minimum += min(options) * demand
        output = sum(catalog[iid]["mass_g"] * n for iid, n in recipe["outputs"].items())
        if output > minimum:
            raise ValueError(f"Material mass creation in {recipe['id']}: {minimum} -> {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check authored profiles without writing")
    args = parser.parse_args()
    item_path, recipe_path = DATA / "items.json", DATA / "recipes.json"
    original_items = json.loads(item_path.read_text(encoding="utf-8"))
    original_recipes = json.loads(recipe_path.read_text(encoding="utf-8"))
    items = apply_item_profiles(deepcopy(original_items))
    recipes = apply_recipe_profiles(deepcopy(original_recipes))
    audit_profiles(items, recipes)
    if args.check:
        if items != original_items or recipes != original_recipes:
            raise SystemExit("Material crafting profiles differ; run tools/build_material_crafting.py")
    else:
        item_path.write_text(json.dumps(items, indent=2) + "\n", encoding="utf-8")
        recipe_path.write_text(json.dumps(recipes, indent=2) + "\n", encoding="utf-8")
    print(f"{len(ITEM_PROFILES)} material grades; {len(RECIPE_PROFILES) + len(QUALITY_ONLY_RECIPES)} shared-quality recipes")


if __name__ == "__main__":
    main()
