from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from worldseed.content.item_catalog import (
    ITEM_TYPE_ORDER, ITEM_TYPE_LABELS, ITEM_SUBCATEGORY_ORDER,
    ITEM_SUBCATEGORY_LABELS, item_sort_key, ordered_items, validate_item_group,
)
AS = ROOT / "worldseed" / "assets"
SP = AS / "sprites"
OUT = AS / "atlases"
DATA = ROOT / "worldseed" / "data"
CELL = 64
COLS = 16

def load_items() -> list[dict]:
    return json.loads((DATA / "items.json").read_text(encoding="utf-8"))


def item_asset_path(raw: dict) -> Path:
    asset = str(raw.get("asset") or str(raw["id"]).split(":", 1)[-1])
    if "/" in asset or "\\" in asset or asset.endswith(".png"):
        raise ValueError(f"item asset must be a simple basename, got {asset!r} for {raw['id']}")
    return SP / "items" / f"{asset}.png"


def item_sections(items: list[dict]) -> list[tuple[str, str, str, list[dict]]]:
    for raw in items:
        validate_item_group(raw)
    ordered = ordered_items(items)
    sections: list[tuple[str, str, str, list[dict]]] = []
    for category in ITEM_TYPE_ORDER:
        subcategories = ITEM_SUBCATEGORY_ORDER.get(category)
        if subcategories:
            for subcategory in subcategories:
                group = [
                    raw for raw in ordered
                    if raw["category"] == category and raw.get("subcategory", "") == subcategory
                ]
                if group:
                    sections.append((category, subcategory, ITEM_SUBCATEGORY_LABELS[(category, subcategory)], group))
        else:
            group = [raw for raw in ordered if raw["category"] == category]
            if group:
                sections.append((category, "", ITEM_TYPE_LABELS[category], group))
    return sections


def build(name: str, entries, cols: int = COLS):
    entries = list(entries)
    rows = max(1, math.ceil(len(entries) / cols))
    sheet = Image.new("RGBA", (cols * CELL, rows * CELL), (0, 0, 0, 0))
    idx = {}
    for i, (key, path) in enumerate(entries):
        im = Image.open(path).convert("RGBA")
        im.thumbnail((60, 60), Image.Resampling.LANCZOS)
        cx = (i % cols) * CELL
        cy = (i // cols) * CELL
        x = cx + (CELL - im.width) // 2
        y = cy + (CELL - im.height) // 2
        sheet.alpha_composite(im, (x, y))
        idx[key] = {"cell": [i % cols, i // cols], "rect": [cx, cy, CELL, CELL]}
    OUT.mkdir(parents=True, exist_ok=True)
    sheet.save(OUT / f"{name}.png", optimize=True)
    return idx


def build_grouped_items(items: list[dict]):
    slot = 0
    placements: list[tuple[int, dict, Path]] = []
    groups: list[dict] = []
    for category, subcategory, label, group in item_sections(items):
        if slot % COLS:
            slot += COLS - (slot % COLS)
        start = slot
        for raw in group:
            path = item_asset_path(raw)
            if not path.exists():
                raise FileNotFoundError(f"missing item asset: {path.relative_to(ROOT)} ({raw['id']})")
            placements.append((slot, raw, path))
            slot += 1
        group_id = f"{category}:{subcategory}" if subcategory else category
        groups.append({
            "id": group_id,
            "category": category,
            "subcategory": subcategory,
            "label": label,
            "start_row": start // COLS,
            "count": len(group),
            "rows": math.ceil(len(group) / COLS),
        })

    rows = max(1, math.ceil(slot / COLS))
    sheet = Image.new("RGBA", (COLS * CELL, rows * CELL), (0, 0, 0, 0))
    idx = {}
    for slot_index, raw, path in placements:
        im = Image.open(path).convert("RGBA")
        # Generated icons already contain transparent padding. Preserve their
        # native pixels in the 64px runtime cell instead of shrinking twice.
        im.thumbnail((CELL, CELL), Image.Resampling.LANCZOS)
        col, row = slot_index % COLS, slot_index // COLS
        cx, cy = col * CELL, row * CELL
        # Atlas storage copies RGBA bytes, including transparent edge pixels;
        # compositing belongs to the renderer, not the packing step.
        sheet.paste(im, (cx + (CELL - im.width) // 2, cy + (CELL - im.height) // 2))
        idx[raw["id"]] = {"cell": [col, row], "rect": [cx, cy, CELL, CELL]}
    OUT.mkdir(parents=True, exist_ok=True)
    sheet.save(OUT / "items.png", optimize=True)
    return idx, groups


def _font(size: int):
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def build_readable_item_catalog(items: list[dict]) -> None:
    title_font = _font(24)
    header_font = _font(18)
    name_font = _font(15)
    meta_font = _font(11)
    # Keep every authored name, stable ID and filename readable in full.
    # Width follows actual font measurements, so future longer IDs also fit.
    longest_text = max((max(name_font.getlength(str(raw["name"])),
                            meta_font.getlength(str(raw["id"])),
                            meta_font.getlength(f"{raw['asset']}.png")) for raw in items), default=0)
    card_w, card_h, cols = max(250, math.ceil(longest_text) + 94), 92, 4
    margin, gap, header_h = 18, 8, 34
    title_h = 54
    sections = []
    total_h = margin + title_h
    for category, subcategory, label, group in item_sections(items):
        rows = math.ceil(len(group) / cols)
        sections.append((category, subcategory, label, group, rows))
        total_h += header_h + rows * (card_h + gap) + 14
    width = margin * 2 + cols * card_w + (cols - 1) * gap
    canvas = Image.new("RGBA", (width, total_h), (15, 18, 20, 255))
    draw = ImageDraw.Draw(canvas)
    draw.text((margin, margin), "WORLDSEED Item Atlas", fill=(235, 231, 219, 255), font=title_font)
    draw.text((margin, margin + 30), "Broad resources • split plants/herbs • stable content IDs", fill=(155, 164, 160, 255), font=meta_font)
    y = margin + title_h
    for category, subcategory, label, group, rows in sections:
        draw.rounded_rectangle((margin, y, width - margin, y + header_h - 4), radius=6, fill=(43, 48, 51, 255))
        draw.text((margin + 10, y + 7), label, fill=(220, 185, 111, 255), font=header_font)
        y += header_h
        for n, raw in enumerate(group):
            row, col = divmod(n, cols)
            x = margin + col * (card_w + gap)
            cy = y + row * (card_h + gap)
            draw.rounded_rectangle((x, cy, x + card_w, cy + card_h), radius=7, fill=(26, 30, 32, 255), outline=(66, 75, 77, 255))
            icon = Image.open(item_asset_path(raw)).convert("RGBA")
            icon.thumbnail((64, 64), Image.Resampling.LANCZOS)
            canvas.alpha_composite(icon, (x + 8 + (64 - icon.width) // 2, cy + 8 + (64 - icon.height) // 2))
            tx = x + 82
            draw.text((tx, cy + 13), str(raw["name"]), fill=(230, 232, 226, 255), font=name_font)
            draw.text((tx, cy + 38), str(raw["id"]), fill=(147, 157, 154, 255), font=meta_font)
            draw.text((tx, cy + 58), f"{raw['asset']}.png", fill=(181, 155, 103, 255), font=meta_font)
        y += rows * (card_h + gap) + 14
    canvas.save(AS / "item_catalog.png", optimize=True)


def write_markdown_catalog(items: list[dict]) -> None:
    lines = [
        "# WORLDSEED Item Atlas",
        "",
        "This is the human-readable item/asset catalog. Stable content IDs stay unchanged for save compatibility. Edit `name`, `asset`, `category`, and optional `subcategory` in `worldseed/data/items.json`, then run `python tools/build_sprite_atlases.py --items-only`.",
        "",
        "Common resources intentionally stay broad. Plants are split into wild/farmed groups; herbs are split into cooking/medical/poisonous groups.",
        "",
        "The runtime atlas is `assets/atlases/items.png`; `assets/item_catalog.png` is the larger labeled preview.",
        "",
    ]
    for category, subcategory, label, group in item_sections(items):
        lines += [f"## {label}", "", "| Icon | Item | Stable ID | Asset |", "|---|---|---|---|"]
        for raw in group:
            asset = f"{raw['asset']}.png"
            lines.append(f'| <img src="sprites/items/{asset}" width="48" height="48"> | {raw["name"]} | `{raw["id"]}` | `{asset}` |')
        lines.append("")
    (AS / "ITEM_ATLAS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_all(items_only: bool = False) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((AS / "visuals.json").read_text(encoding="utf-8"))
    items = load_items()
    if items_only and (AS / "atlas_index.json").exists():
        index = json.loads((AS / "atlas_index.json").read_text(encoding="utf-8"))
        index.setdefault("atlases", {})
        index["cell_px"] = CELL
    else:
        index = {"cell_px": CELL, "atlases": {}}

    item_idx, groups = build_grouped_items(items)
    index["atlases"]["items"] = {
        "image": "assets/atlases/items.png",
        "entries": item_idx,
        "group_order": [group["id"] for group in groups],
        "groups": groups,
    }
    build_readable_item_catalog(items)
    write_markdown_catalog(items)

    if not items_only:
        for kind in ["terrain", "resources", "structures", "crops"]:
            entries = []
            for cid, raw in manifest[kind].items():
                if isinstance(raw, list):
                    for n, path in enumerate(raw):
                        entries.append((f"{cid}#{n}", ROOT / "worldseed" / path))
                else:
                    entries.append((cid, ROOT / "worldseed" / raw))
            index["atlases"][kind] = {"image": f"assets/atlases/{kind}.png", "entries": build(kind, entries)}
        sp = []
        for cid, paths in manifest["species"].items():
            for n, path in enumerate(paths):
                sp.append((f"{cid}#{n}", ROOT / "worldseed" / path))
        index["atlases"]["species"] = {"image": "assets/atlases/species.png", "entries": build("species", sp)}
        npc = [(f"npc#{n}", ROOT / "worldseed" / p) for n, p in enumerate(manifest["npc_variants"])]
        index["atlases"]["npc"] = {"image": "assets/atlases/npc.png", "entries": build("npc", npc)}

    (AS / "atlas_index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    print(f"built item atlas: {len(items)} items across {len(groups)} sections")
    if not items_only:
        print("built atlases:", ", ".join(index["atlases"]))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build WORLDSEED runtime atlases and readable item catalog.")
    parser.add_argument("--items-only", action="store_true", help="Only rebuild the item atlas/catalog and preserve other atlas index sections.")
    args = parser.parse_args()
    build_all(items_only=args.items_only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
