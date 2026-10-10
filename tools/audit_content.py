#!/usr/bin/env python3
"""WORLDSEED content-utility audit.

RC7 rule: content must participate in a gameplay loop.  This tool rejects
undefined references, missing prose, functionless structures, and items that
have neither direct utility nor a downstream sink.
"""
from __future__ import annotations
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from worldseed.content.registry import ContentRegistry
from worldseed.config import DATA_DIR


def audit(reg: ContentRegistry) -> list[str]:
    errors: list[str] = []
    sinks: set[str] = set()
    for definition in getattr(reg, 'salvage', {}).values():
        sinks.add(definition.item_id)
        if definition.item_id not in reg.items:
            errors.append(f"salvage {definition.id} references undefined input {definition.item_id}")
        for iid in definition.yields:
            if iid not in reg.items:
                errors.append(f"salvage {definition.id} yields undefined item {iid}")
        for drop in definition.rare_yields:
            if drop.item_id not in reg.items:
                errors.append(f"salvage {definition.id} yields undefined rare item {drop.item_id}")
    for r in reg.recipes.values():
        sinks.update(r.inputs); sinks.update(r.catalysts)
        for iid in (*r.inputs, *r.outputs, *r.catalysts):
            if iid not in reg.items: errors.append(f"recipe {r.id} references undefined item {iid}")
        if r.station and r.station not in reg.structures: errors.append(f"recipe {r.id} references undefined station {r.station}")
    for s in reg.structures.values():
        sinks.update(s.cost)
        if not s.uses: errors.append(f"structure {s.id} declares no gameplay use")
        if not s.description.strip(): errors.append(f"structure {s.id} has no description")
        for iid in s.cost:
            if iid not in reg.items: errors.append(f"structure {s.id} costs undefined item {iid}")
    for c in reg.crops.values():
        if c.seed_item not in reg.items: errors.append(f"crop {c.id} seed undefined: {c.seed_item}")
        if c.harvest_item not in reg.items: errors.append(f"crop {c.id} harvest undefined: {c.harvest_item}")
        sinks.add(c.seed_item)
    for d in reg.designs.values():
        if d.output_item not in reg.items: errors.append(f"design {d.id} output undefined: {d.output_item}")
        for opts in d.components.values():
            sinks.update(opts)
            for iid in opts:
                if iid not in reg.items: errors.append(f"design {d.id} component undefined: {iid}")
    for f in reg.resources.values():
        for iid in f.yields:
            if iid not in reg.items: errors.append(f"resource {f.id} yields undefined item {iid}")
    for sp in reg.species.values():
        for iid in sp.carcass:
            if iid not in reg.items: errors.append(f"species {sp.id} carcass yields undefined item {iid}")
    for m in reg.cooking_methods.values():
        if m.station not in reg.structures: errors.append(f"cooking method {m.id} station undefined: {m.station}")
        if m.cookware and m.cookware not in reg.items: errors.append(f"cooking method {m.id} cookware undefined: {m.cookware}")

    fishing_sinks: set[str] = set()
    for fish in reg.fish.values():
        fishing_sinks.add(fish.item_id)
        fishing_sinks.update(fish.bait_affinity)

    dynamic_food: set[str] = set()
    for iid, item in reg.items.items():
        if any(set(item.tags) & set(method.allowed_tags) for method in reg.cooking_methods.values()):
            dynamic_food.add(iid)

    for item in reg.items.values():
        if not item.description.strip(): errors.append(f"item {item.id} has no description")
        if not item.flavor.strip(): errors.append(f"item {item.id} has no flavor text")
        direct = bool(
            item.utility_roles or item.nutrition or item.hydration or item.weapon_damage or item.armor
            or item.tool_qualities or item.equip_slot or item.range > 1
            or {'currency','book','seed','medicine','container','water','fishing_rod','fishing_line','fishing_spear','fishing_net','fishing_lure','fishing_bait'} & set(item.tags)
        )
        if item.id not in sinks and item.id not in dynamic_food and item.id not in fishing_sinks and not direct:
            errors.append(f"item {item.id} has no direct use or downstream sink")
    return sorted(set(errors))


def main() -> int:
    reg = ContentRegistry.load(DATA_DIR)
    errors = audit(reg)
    print(f"items={len(reg.items)} recipes={len(reg.recipes)} salvage={len(reg.salvage)} structures={len(reg.structures)} crops={len(reg.crops)} resources={len(reg.resources)} species={len(reg.species)} cooking_methods={len(reg.cooking_methods)}")
    if errors:
        print("CONTENT AUDIT FAILED")
        for e in errors: print(" -", e)
        return 1
    print("CONTENT AUDIT PASSED")
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
