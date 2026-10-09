#!/usr/bin/env python3
"""Export a deterministic 24-face modular NPC portrait proof sheet."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worldseed.presentation.portraits import PortraitComposer, portrait_spec


def main() -> None:
    import pygame as pg
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/dev61-portrait-sheet.png"))
    args = parser.parse_args()
    pg.init()
    width, height = 1024, 876
    sheet = pg.Surface((width, height))
    sheet.fill((17, 23, 32))
    title = pg.font.SysFont("DejaVu Sans", 24, bold=True)
    font = pg.font.SysFont("DejaVu Sans", 14)
    tiny = pg.font.SysFont("DejaVu Sans", 11)
    sheet.blit(title.render("WORLDSEED / layered NPC portraits", True, (230, 224, 201)), (24, 17))
    sheet.blit(font.render("Stable facial parts, overlapping male/female pools, age effects on the same identity", True, (158, 174, 178)), (24, 51))
    composer = PortraitComposer(max_entries=24)
    seed = b"WORLDSEED:Dev61:portrait-preview"
    rows = []
    for sex in ("male", "female"):
        rows.append([(f"npc:preview:{sex}:{i}", sex, 35, f"{sex.title()} / composite {i+1}") for i in range(6)])
    for sex in ("male", "female"):
        rows.append([(f"npc:preview:{sex}:{i//3}", sex, (12,35,75)[i%3], f"{sex.title()} / {('youth','adult','elder')[i%3]}") for i in range(6)])
    for row, cases in enumerate(rows):
        for col, (uid, sex, age, label) in enumerate(cases):
            spec = portrait_spec(seed, uid, sex, age)
            x, y = 24 + col*164, 90+row*190
            rect = pg.Rect(x, y, 152, 178)
            pg.draw.rect(sheet, (26, 34, 43), rect, border_radius=8)
            pg.draw.rect(sheet, (48, 62, 68), rect, 1, border_radius=8)
            image = composer.render(spec, 128)
            sheet.blit(image, (x+12,y+2))
            sheet.blit(font.render(label, True, (216, 218, 202)), (x+9,y+137))
            parts = spec.head.split(":")[1]+" + "+spec.nose.split(":")[1]
            sheet.blit(tiny.render(parts, True, (151, 172, 170)), (x+9,y+159))
    sheet.blit(tiny.render("Each bust is composed from independently selected head / jaw / ears / eyes / brows / nose / mouth / hair / neck / garment layers.", True, (141, 159, 168)), (24,861))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pg.image.save(sheet, str(args.output))
    print(args.output.resolve())
    pg.quit()


if __name__ == "__main__":
    main()
