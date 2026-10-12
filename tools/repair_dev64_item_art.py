"""Repair the three Dev64 catalog additions with distinct reproducible RGBA art.

Run explicitly when introducing these legacy items; this is an authoring tool,
not a runtime asset generator. Existing published source sprites are untouched.
"""
from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw
import hashlib
import json
import math
import random

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "worldseed/data/items.json"
ICONS = ROOT / "worldseed/assets/sprites/items"
PROVENANCE = ROOT / "worldseed/assets/source_items/dev64/manifest.json"
SCALE = 3
TARGETS = ("pine_bough", "hearth_root_stew", "berry_barley_bun")


def pt(x, y):
    return round(x * SCALE), round(y * SCALE)


def painter():
    image = Image.new("RGBA", (64 * SCALE, 64 * SCALE))
    return image, ImageDraw.Draw(image, "RGBA")


def ell(d, rect, color, outline=None, width=1):
    d.ellipse(tuple(round(v * SCALE) for v in rect),
              fill=color, outline=outline, width=width * SCALE)


def line(d, points, color, width=1):
    d.line([pt(*p) for p in points], fill=color,
           width=max(1, round(width * SCALE)), joint="curve")


def poly(d, points, color):
    d.polygon([pt(*p) for p in points], fill=color)


def paint_pine_bough():
    image, d = painter()
    line(d, [(14, 54), (24, 43), (31, 36), (42, 20), (47, 9)], (59, 42, 25, 255), 4.6)
    line(d, [(14, 54), (24, 43), (31, 36), (42, 20), (47, 9)], (147, 99, 50, 255), 2.1)
    line(d, [(23, 44), (20, 32)], (110, 75, 44, 255), 2.5)
    line(d, [(31, 36), (43, 38)], (105, 70, 39, 255), 2.5)
    clusters = [((21,35), (-1.,-.6)), ((28,39), (-.85,-.6)),
                ((29,33), (.35,-.95)), ((35,27), (-.7,-.8)),
                ((41,21), (0.,-1.)), ((43,36), (.9,.25)), ((46,14), (.25,-1.))]
    rng = random.Random(32)
    palette = [(35,73,51,230), (29,64,46,245), (56,92,59,243),
               (77,110,64,248), (92,119,70,225)]
    for (cx,cy),(dx,dy) in clusters:
        for i in range(18):
            angle = i * 2.399 + cx * .1
            length = 7 + rng.random() * 8
            bx,by = cx + rng.uniform(-1.6,1.6), cy + rng.uniform(-1.6,1.6)
            ex,ey = bx + dx * length + math.cos(angle) * 5, by + dy * length + math.sin(angle) * 5
            line(d, [(bx,by), (ex,ey)], rng.choice(palette), rng.choice([.7,.9,1.]))
        for off in (-2,1,3):
            line(d, [(cx+off,cy), (cx+off+dx*7,cy+dy*7)], (154,163,91,140), .55)
    ell(d, (10,51,16,57), (134,89,50,255), outline=(72,45,29,240))
    return image


def paint_hearth_root_stew():
    image,d = painter()
    ell(d, (9,33,55,57), (42,36,29,120))
    ell(d, (8,22,57,51), (55,43,36,255), outline=(30,28,26,240), width=2)
    poly(d, [(10,33),(54,33),(50,51),(45,55),(20,55),(14,50)], (123,71,43,255))
    poly(d, [(13,37),(52,37),(49,48),(44,53),(21,53),(16,47)], (163,95,54,255))
    ell(d, (8,22,57,42), (66,46,34,255), outline=(28,27,23,255))
    ell(d, (12,24,53,38), (165,115,63,255), outline=(225,163,89,255))
    for rect,color in [((15,25,27,31),(201,97,44,255)),
                       ((31,26,43,33),(223,154,66,255)),
                       ((24,29,33,36),(229,195,111,255)),
                       ((42,26,50,31),(201,104,39,255)),
                       ((18,32,24,36),(122,137,58,255)),
                       ((37,31,43,36),(105,135,60,255)),
                       ((28,24,31,29),(84,120,47,255))]:
        ell(d, rect, color)
    line(d, [(15,40),(18,46),(22,49)], (216,144,86,170), 1.2)
    line(d, [(26,49),(40,50),(47,46)], (110,60,38,230), 1.1)
    for points in ([(22,20),(20,16),(23,12)],
                   [(34,19),(32,14),(35,8)],
                   [(44,20),(42,15),(44,12)]):
        line(d, points, (186,179,152,105), 1.3)
    return image


def paint_berry_barley_bun():
    image,d = painter()
    ell(d, (7,43,58,54), (36,26,24,55))
    ell(d, (8,16,56,51), (102,59,34,255), outline=(68,37,25,255))
    ell(d, (9,13,55,45), (185,116,62,255), outline=(124,72,34,255), width=2)
    ell(d, (14,15,51,40), (222,159,87,255))
    poly(d, [(13,31),(21,27),(28,30),(32,35),(43,30),(52,32),(45,41),(25,42)],
         (136,68,42,255))
    line(d, [(17,33),(27,36),(39,36),(49,33)], (238,196,126,220), 1.3)
    for x,y,r in ((21,30,4),(36,26,3.7),(44,33,4),(30,36,3),(20,38,2.4)):
        ell(d,(x-r,y-r,x+r,y+r),(63,41,84,255),outline=(42,31,52,255))
        ell(d,(x-r+1,y-r+.5,x-.6,y-.7),(117,94,153,220))
    for x,y in ((16,24),(23,18),(34,17),(46,22),(27,24),(47,27),(35,22),(14,29)):
        ell(d,(x,y,x+2,y+.9),(239,204,133,210))
    line(d,[(13,39),(21,44),(38,45),(49,41)],(99,51,30,220),1.4)
    return image


def repair():
    catalog = json.loads(DATA.read_text(encoding="utf-8"))
    pine = next(row for row in catalog if row["id"] == "core:pine_bough")
    pine["asset"] = pine["sprite_tag"] = "pine_bough"
    DATA.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")

    ICONS.mkdir(parents=True, exist_ok=True)
    provenance = json.loads(PROVENANCE.read_text(encoding="utf-8"))
    painter_functions = (paint_pine_bough, paint_hearth_root_stew, paint_berry_barley_bun)
    for asset, draw_image in zip(TARGETS, painter_functions):
        path = ICONS / (asset + ".png")
        if path.exists():
            raise RuntimeError(f"Refusing to overwrite an existing curated icon: {path}")
        image = draw_image().resize((64,64), Image.Resampling.LANCZOS)
        image.save(path, optimize=True)
        raw = path.read_bytes()
        sid = "dev64_authored_" + asset
        item_id = "core:" + asset
        provenance["sheets"].append({
            "id":sid, "source":path.relative_to(ROOT).as_posix(),
            "source_sha256":hashlib.sha256(raw).hexdigest(),
            "source_size":[64,64], "columns":1, "rows":1, "item_ids":[item_id],
            "generator":"deterministic_pillow_authoring"
        })
        provenance["items"].append({
            "item_id":item_id, "asset":asset, "sprite_tag":asset, "sheet_id":sid,
            "png_sha256":hashlib.sha256(raw).hexdigest(),
            "rgba_sha256":hashlib.sha256(image.tobytes()).hexdigest()
        })
    PROVENANCE.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    from tools.build_sprite_atlases import build_all
    build_all(items_only=True)
    assert len({row["asset"] for row in catalog}) == len(catalog)
    assert len({row["item_id"] for row in provenance["items"]}) == len(catalog)
    print(f"Synced {len(catalog)} items, three unique sprites and their generated atlas.")


if __name__ == "__main__":
    repair()
