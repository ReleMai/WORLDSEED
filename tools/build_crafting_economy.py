"""Publish authored expansion recipes into the existing NPC production catalog.

The checked-in processes remain ordinary editable game content. This tool keeps
their inputs, outputs and prerequisites synchronized with player recipes when
the expansion is regenerated; it creates no simulation goods.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"worldseed"/"data"
PREFIX="core:npc_expansion_"
TAG_PREFIX="core:npc_tagged_"


def process_rows(manifest,recipes,items):
    rows=[]
    for entry in sorted(manifest["recipes"],key=lambda row:(row["profession"],row["tier"],row["recipe_id"])):
        recipe=recipes[entry["recipe_id"]]
        if not recipe.get("inputs") and not recipe.get("input_tags"):
            raise ValueError(f"NPC craft has no physical inputs: {recipe['id']}")
        output=entry["output_item"];item=items[output];tier=max(1,int(entry["tier"]))
        tags=set(item.get("tags",()))
        component="craft_component" in tags
        intermediate="craft_intermediate" in tags
        food=int(item.get("nutrition",0))>0 and "food" in tags
        # Anonymous residents replace worn tools, garments and household
        # supplies. Foods already enter the hunger basket; parts are inputs.
        interval=0 if component or intermediate or food else {1:14,2:30,3:60}.get(tier,90)
        target=32 if component else (20 if intermediate else {1:12,2:8,3:4}.get(tier,3))
        rows.append({
            "id":PREFIX+recipe["id"].split(":",1)[-1],
            "name":recipe["name"],"occupation":entry["profession"],"workers":1,
            "inputs":dict(recipe["inputs"]),"outputs":dict(recipe["outputs"]),
            "priority_good":output,"recipe_id":recipe["id"],
            "station":recipe.get("station"),"minutes":int(recipe["minutes"]),
            "skill":recipe.get("skill","crafting"),"difficulty":int(recipe.get("difficulty",0)),
            "market_target":target,"consumption_days":interval,
            **({"knowledge":recipe["knowledge"]} if recipe.get("knowledge") else {}),
        })
    return rows


FAMILY_JOBS={"metal":"smith","wood":"carpenter","cloth":"weaver","leather":"tanner",
             "ceramic":"potter","glass":"scholar","paper":"scholar","stone":"mason",
             "mixed":"carpenter","provisions":"farmer","plant":"farmer","bone":"butcher"}
CATEGORY_JOBS={"fiberwork":"weaver","primitive_tools":"mason","fishing":"fisher",
               "survival":"farmer","hunting":"hunter","misc_recovery":"carpenter",
               "advanced":"smith","woodcraft":"carpenter","textiles":"weaver"}


def tagged_process_rows(recipes,items,covered_recipe_ids=()):
    """Mirror all tag-aware recipes into the authoritative NPC work catalog."""
    rows=[]
    covered=set(covered_recipe_ids)
    for recipe in sorted(recipes.values(),key=lambda row:row["id"]):
        tags=recipe.get("input_tags") or {}
        if not tags or recipe["id"] in covered:continue
        family=next((tag for tag in tags if tag.startswith("material_source_")),"")
        occupation=FAMILY_JOBS.get(family.split("_")[-1],"farmer") if family else CATEGORY_JOBS.get(recipe.get("category"),"carpenter")
        output=next(iter(recipe["outputs"]))
        rows.append({
            "id":TAG_PREFIX+recipe["id"].split(":",1)[-1],
            "name":recipe["name"],"occupation":occupation,"workers":1,
            "inputs":dict(recipe.get("inputs",{})),"outputs":dict(recipe["outputs"]),
            "priority_good":output,"recipe_id":recipe["id"],
            "station":recipe.get("station"),"minutes":int(recipe["minutes"]),
            "skill":recipe.get("skill","crafting"),"difficulty":int(recipe.get("difficulty",1)),
            "market_target":12 if "craft_component" in items[output].get("tags",[]) else 8,
            "consumption_days":0,
            **({"knowledge":recipe["knowledge"]} if recipe.get("knowledge") else {}),
        })
    return rows


def missing_crop_processes(original,crops):
    """Existing farm parcels and seed stocks support every authored crop."""
    ids={p["id"] for p in original};rows=[]
    for crop in sorted(crops,key=lambda row:row["id"]):
        process_id="core:field_"+crop["id"].split(":",1)[-1]
        if process_id in ids:continue
        rows.append({"id":process_id,"name":crop["name"]+" field work","occupation":"farmer",
                     "workers":1,"inputs":{crop["seed_item"]:1},
                     "outputs":{crop["harvest_item"]:max(1,int(crop["yield_min"])),crop["seed_item"]:2},
                     "priority_good":crop["harvest_item"],"required_specialization":"farming"})
    return rows


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check",action="store_true",help="Check synchronization without writing")
    args=parser.parse_args()
    manifest=json.loads((DATA/"crafting_expansion.json").read_text())
    recipes={r["id"]:r for r in json.loads((DATA/"recipes.json").read_text())}
    items={r["id"]:r for r in json.loads((DATA/"items.json").read_text())}
    path=DATA/"settlement_processes.json";original=json.loads(path.read_text())
    base=[p for p in original if not p["id"].startswith((PREFIX,TAG_PREFIX))]
    crops=json.loads((DATA/"crops.json").read_text())
    base+=missing_crop_processes(base,crops)
    base_ids={p["id"] for p in base}
    if "core:draw_settlement_water" not in base_ids:
        base.append({"id":"core:draw_settlement_water","name":"Draw settlement fresh water","occupation":"farmer",
                     "workers":1,"inputs":{},"outputs":{"core:clean_water":4},"priority_good":"core:clean_water",
                     "minutes":12,"market_target":24,"required_specialization":"freshwater"})
    # Sharp primitive flakes bootstrap workshop cutting without granting tools
    # or requiring a finished advanced tool before its own production chain.
    if "core:npc_strike_stone_flakes" not in base_ids:
        primitive=recipes["core:stone_flake"]
        base.append({"id":"core:npc_strike_stone_flakes","name":primitive["name"],"occupation":"mason",
                     "workers":1,"inputs":dict(primitive["inputs"]),"outputs":dict(primitive["outputs"]),
                     "priority_good":"core:stone_flake","recipe_id":primitive["id"],"station":primitive.get("station"),
                     "minutes":primitive["minutes"],"skill":primitive["skill"],"difficulty":primitive["difficulty"],
                     "market_target":20,"consumption_days":14})
    # Aggregate hunting already represents a processed carcass. Bone is part of
    # those same authored species carcasses, alongside its existing meat/hide.
    hunt=next((p for p in base if p["id"]=="core:hunting"),None)
    if hunt is not None:hunt["outputs"].setdefault("core:bone",1)
    rows=process_rows(manifest,recipes,items)
    if len(rows)<=200:raise ValueError("Expansion must contain more than 200 authored NPC recipes")
    updated=base+rows+tagged_process_rows(recipes,items,{entry["recipe_id"] for entry in manifest["recipes"]})
    if args.check:
        if original!=updated:raise SystemExit("Crafting economy catalog differs; run tools/build_crafting_economy.py")
    else:path.write_text(json.dumps(updated,indent=2)+"\n")
    print(f"{len(rows)} expansion NPC processes across {len({r['occupation'] for r in rows})} professions")


if __name__=="__main__":main()
