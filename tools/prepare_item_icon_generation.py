"""Prepare explicit art briefs; image_gen creates the artwork, not this tool."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "worldseed" / "data"
COMPONENT_IDS = tuple("core:" + name for name in (
    "wood_pieces", "metal_scraps", "nuts_and_bolts", "tool_handles", "plant_scraps",
    "cloth_scraps", "leather_scraps", "bone_chips", "ceramic_shards", "glass_shards",
    "copper_wire", "resin_lumps", "mineral_grit", "tempered_spring", "fine_gear",
    "clear_crystal", "aromatic_oil", "tough_fiber", "silver_filament",
))
STYLE = """Create BRAND NEW professional inventory icon artwork for WORLDSEED,
a medieval wilderness survival RPG. Rich hand-painted fantasy inventory art,
believable distinct objects, dimensional material texture, warm restrained colors,
upper-left lighting and consistent three-quarter perspective. Strong readable
silhouettes at 64 pixels. No generic geometry or interchangeable symbols. No text,
numbers, labels, title, UI, borders, ground, cast shadows or checkerboard. Fully
transparent background with clean natural edges. Clothing and armor are empty
garments, never worn by people. Tools show real functional heads and handles.
Damaged objects show the named recognizable object with visible wear or breakage.
Botanicals show their distinctive botanical leaves, flowers, roots or seedheads.
Food shows the named ingredients and preparation, not identical anonymous sacks.
No glowing halos or colored key fringes. Do not merge neighboring objects.
"""


def briefs(items, expansion, size=36):
    family = {row["item_id"]: row["art_family"] for row in expansion["misc"]}
    for row in expansion["recipes"]:
        family.setdefault(row["output_item"], row["art_family"])
    remaining = [item for item in items if item["id"] not in COMPONENT_IDS]
    remaining.sort(key=lambda item: (family.get(item["id"], item["category"]),
                                      item["name"].casefold(), item["id"]))
    batches = []
    for start in range(0, len(remaining), size):
        group = remaining[start:start + size]
        prompts = [STYLE, "EXACT layout: SIX columns and SIX rows, equally sized cells. "
                   "Each listed object is centered inside the central 60% of its "
                   "cell with 20% completely transparent gutters on every side. "
                   "Exactly one icon group per cell, no overlaps. Read the "
                   "following left-to-right row-major assignment precisely:"]
        names = [item["name"] for item in group] + ["COMPLETELY EMPTY TRANSPARENT CELL"] * (size-len(group))
        for row in range(6):
            prompts.append(f"Row {row+1}: " + "; ".join(names[row*6:(row+1)*6]) + ".")
        prompts.append("Exactly 6 columns x 6 rows. Only the stated named objects; "
                       "keep their order. Every empty cell stays transparent. "
                       "Finished, beautiful, recognizable real game art.")
        batches.append({"id": f"items_{start//size+1:02d}", "source": None,
                        "columns": 6, "rows": 6, "item_ids": [item["id"] for item in group],
                        "prompt": "\n".join(prompts), "generator": "image_gen"})
    return {"schema_version": 1, "sheets": batches}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    items = json.loads((DATA / "items.json").read_text())
    expansion = json.loads((DATA / "crafting_expansion.json").read_text())
    manifest = briefs(items, expansion)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Prepared {len(manifest['sheets'])} explicit sheets for {len(items)-len(COMPONENT_IDS)} items")


if __name__ == "__main__":
    main()
