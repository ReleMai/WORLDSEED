#!/usr/bin/env python3
"""Export the expanded portrait gallery and controlled sprite-feature boards."""
from __future__ import annotations

import argparse
from dataclasses import replace
import os
from pathlib import Path
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worldseed.presentation.portraits import PortraitComposer, portrait_catalog, portrait_spec


BACKGROUND = (17, 23, 32)
CARD = (26, 34, 43)
BORDER = (48, 62, 68)
TEXT = (230, 224, 201)
MUTED = (158, 174, 178)
SEED = b"WORLDSEED:Dev62:portrait-preview"


def label(value):
    return value.split(":", 1)[-1].replace("_", " ").title()


def base_face():
    spec = portrait_spec(SEED, "npc:feature:baseline", "unknown", 35, version=2)
    return replace(
        spec, head="core:oval", jaw="core:soft", ears="core:wide",
        nose="core:straight", eyes="core:round", brows="core:straight",
        mouth="core:full", hair="core:bald", facial_hair="core:none",
        neck="core:regular", bust="core:broad", skin_palette="core:sand",
        hair_palette="core:chestnut", eye_palette="core:blue", cloth_palette="core:indigo",
        tattoo="core:none", markings="core:none", accessory="core:none",
        shading="core:soft", cloth_detail="core:plain", complexion=0, detail=0,
        eye_spacing=0, eye_height=0, asymmetry=0,
    )


def sheet_header(pg, width, height, title, subtitle):
    sheet = pg.Surface((width, height))
    sheet.fill(BACKGROUND)
    fonts = {
        "title": pg.font.SysFont("DejaVu Sans", 25, bold=True),
        "label": pg.font.SysFont("DejaVu Sans", 13),
        "small": pg.font.SysFont("DejaVu Sans", 11),
    }
    sheet.blit(fonts["title"].render(title, True, TEXT), (24, 15))
    sheet.blit(fonts["label"].render(subtitle, True, MUTED), (24, 51))
    return sheet, fonts


def card(pg, sheet, rect):
    pg.draw.rect(sheet, CARD, rect, border_radius=8)
    pg.draw.rect(sheet, BORDER, rect, 1, border_radius=8)


def save(pg, sheet, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    pg.image.save(sheet, str(path))
    print(path.resolve())


def gallery(pg, output):
    columns, rows, stride, card_height = 6, 6, 192, 190
    sheet, fonts = sheet_header(
        pg, 24 + columns * stride, 94 + rows * 202,
        "WORLDSEED / expanded character portraits",
        "36 layered composites: shared male/female feature pools, clothing, markings and the same faces at different ages",
    )
    composer = PortraitComposer(max_entries=40)
    cases = []
    for row in range(4):
        sex = "male" if row % 2 == 0 else "female"
        for column in range(columns):
            number = (row // 2) * columns + column
            cases.append((f"npc:gallery:{sex}:{number}", sex, 35, f"{sex.title()} / portrait {number + 1}"))
    for sex in ("male", "female"):
        for number in range(2):
            for age in (12, 35, 75):
                cases.append((f"npc:gallery:aging:{sex}:{number}", sex, age,
                              f"{sex.title()} / {('youth' if age < 18 else 'elder' if age > 55 else 'adult')}"))
    for index, (uid, sex, age, caption) in enumerate(cases):
        x, y = 24 + (index % columns) * stride, 90 + (index // columns) * 202
        card(pg, sheet, pg.Rect(x, y, stride - 12, card_height))
        spec = portrait_spec(SEED, uid, sex, age, version=2)
        sheet.blit(composer.render(spec, 144), (x + 18, y - 3))
        sheet.blit(fonts["label"].render(caption, True, TEXT), (x + 10, y + 144))
        sheet.blit(fonts["small"].render(label(spec.hair) + " / " + label(spec.bust), True, MUTED), (x + 10, y + 165))
    save(pg, sheet, output)


def feature_board(pg, output, groups, title, subtitle):
    """Each tile shows the same face at chat scale 64 and inspection scale 128."""
    catalog = portrait_catalog(version=2)
    width, columns, stride, row_height = 1564, 7, 220, 180
    sections = [(group, list(catalog["parts"][group])) for group in groups]
    height = 90 + sum(40 + ((len(keys) + columns - 1) // columns) * row_height for _, keys in sections)
    sheet, fonts = sheet_header(pg, width, height, title, subtitle)
    baseline = base_face()
    composer = PortraitComposer(max_entries=96)
    y = 88
    for group, keys in sections:
        heading = group.replace("_", " ").title()
        sheet.blit(fonts["label"].render(f"{heading} / {len(keys)} sprite parts", True, TEXT), (24, y))
        y += 30
        active = replace(baseline, hair="core:crop") if group == "accessory" else baseline
        for index, key in enumerate(keys):
            x, tile_y = 24 + (index % columns) * stride, y + (index // columns) * row_height
            card(pg, sheet, pg.Rect(x, tile_y, 208, 166))
            spec = replace(active, **{group: key})
            sheet.blit(composer.render(spec, 128), (x + 4, tile_y + 2))
            sheet.blit(composer.render(spec, 64), (x + 138, tile_y + 56))
            sheet.blit(fonts["label"].render(label(key), True, TEXT), (x + 9, tile_y + 136))
        y += ((len(keys) + columns - 1) // columns) * row_height + 10
    save(pg, sheet, output)


def palette_board(pg, output):
    catalog = portrait_catalog(version=2)
    width, columns, stride, row_height = 1240, 6, 200, 172
    groups = list(catalog["palettes"])
    height = 90 + sum(40 + ((len(catalog["palettes"][group]) + columns - 1) // columns) * row_height for group in groups)
    sheet, fonts = sheet_header(
        pg, width, height, "WORLDSEED / expanded portrait colors",
        "Hold the face constant: independent skin, hair, eye, clothing, tattoo ink and metal palettes",
    )
    baseline = replace(base_face(), hair="core:crop")
    composer = PortraitComposer(max_entries=96)
    y = 88
    for group in groups:
        keys = list(catalog["palettes"][group])
        sheet.blit(fonts["label"].render(f"{group.title()} / {len(keys)} palettes", True, TEXT), (24, y))
        y += 30
        active = baseline
        if group in ("ink", "metal"):
            part = "tattoo" if group == "ink" else "accessory"
            key = next(key for key, value in catalog["parts"][part].items() if value["style"] != "none")
            active = replace(active, **{part: key})
        for index, key in enumerate(keys):
            x, tile_y = 24 + (index % columns) * stride, y + (index // columns) * row_height
            card(pg, sheet, pg.Rect(x, tile_y, stride - 12, 158))
            spec = replace(active, **{group + "_palette": key})
            sheet.blit(composer.render(spec, 128), (x + 2, tile_y))
            for offset, color in enumerate(catalog["palettes"][group][key]["colors"]):
                pg.draw.rect(sheet, color, (x + 140, tile_y + 33 + offset * 18, 29, 15))
            sheet.blit(fonts["label"].render(label(key), True, TEXT), (x + 9, tile_y + 133))
        y += ((len(keys) + columns - 1) // columns) * row_height + 10
    save(pg, sheet, output)


def main():
    import pygame as pg
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts"))
    args = parser.parse_args()
    pg.init()
    try:
        gallery(pg, args.output_dir / "dev62-portrait-gallery.png")
        feature_board(
            pg, args.output_dir / "dev62-portrait-eyes-hair.png", ("eyes", "hair"),
            "WORLDSEED / eye and hair sprite library",
            "One controlled face for each part. Left: 128px inspection portrait. Right: 64px conversation portrait.",
        )
        feature_board(
            pg, args.output_dir / "dev62-portrait-details.png",
            ("bust", "cloth_detail", "facial_hair", "tattoo", "markings", "accessory", "shading"),
            "WORLDSEED / clothing, facial details and shading",
            "Same face and colors throughout: garment shapes, stitching, beards, tattoos, markings, jewelry and lighting.",
        )
        feature_board(
            pg, args.output_dir / "dev62-portrait-facial-features.png",
            ("head", "jaw", "ears", "nose", "brows", "mouth", "neck"),
            "WORLDSEED / facial feature sprite library",
            "Change one facial part at a time: head silhouettes, jawlines, ears, noses, brows, mouths and neck proportions.",
        )
        palette_board(pg, args.output_dir / "dev62-portrait-colors.png")
    finally:
        pg.quit()


if __name__ == "__main__":
    main()
