"""Build four art-direction style sheets from the *current* game assets.

The generated sheets are review artifacts, never simulation data. Images remain
at their authored resolution in source control; GPU copies are downsampled.
Usage: python tools/generate_interior_style_sheets.py --output <directory>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'worldseed/assets/visuals.json'
CATEGORIES = {
    '01_floors_and_rugs': (
        'core:floor_walnut', 'core:floor_pine', 'core:floor_limestone',
        'core:floor_slate', 'core:floor_clay_hex', 'core:floor_mosaic',
        'core:floor_packed_earth', 'core:hearth_rug_piece',
        'core:bedside_runner_piece', 'core:hall_carpet_piece'),
    '02_walls_and_architecture': (
        'core:wall_limewash','core:wall_fieldstone','core:wall_oak_panel',
        'core:interior_wall_plaster','core:interior_wall_timber',
        'core:interior_wall_stone', 'up','down'),
    '03_furniture_and_lighting': (
        'core:canopy_bed_piece','core:linen_cot_bed_piece',
        'core:oak_armchair_piece','core:padded_armchair_piece',
        'core:carved_bench_piece','core:high_back_chair_piece',
        'core:oak_dresser_piece','core:joiners_workbench_piece',
        'core:hooded_forge_piece','core:brick_cookstove_piece',
        'core:lamp_stand_piece','core:house_hearth_piece'),
    '04_containers_and_storage': (
        'core:house_chest_piece','core:wardrobe_piece','core:cupboard_piece',
        'core:painted_wardrobe_piece','core:ironbound_coffer_piece',
        'core:corner_cabinet_piece','core:wicker_hamper_piece',
        'core:small_table_piece'),
}


def resolve_asset(manifest, uid):
    # Prefer live GPU game identity. No new storage IDs or loot are created.
    for category in ('interiors','interior_textures','interior_stairs','containers'):
        raw = manifest.get(category, {}).get(uid)
        if raw:
            return ROOT / 'worldseed' / (raw[0] if isinstance(raw,list) else raw)
    return None


def build_sheets(output: Path):
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    manifest=json.loads(MANIFEST.read_text(encoding='utf-8'))
    output.mkdir(parents=True, exist_ok=True)
    font=ImageFont.load_default()
    generated=[]
    for category,ids in CATEGORIES.items():
        columns=4
        cell_width,cell_height=196,187
        rows=(len(ids)+columns-1)//columns
        sheet=Image.new('RGB',(columns*cell_width+40,rows*cell_height+104),(17,22,29))
        draw=ImageDraw.Draw(sheet)
        draw.text((22,20),'WORLDSEED  /  INTERIOR ART STUDY',fill=(206,161,105),font=font)
        draw.text((22,44),category.upper().replace('_',' '),fill=(231,231,219),font=font)
        for index,uid in enumerate(ids):
            asset=resolve_asset(manifest,uid)
            if asset is None or not asset.is_file():
                raise FileNotFoundError(f'Missing authored interior material {uid}: {asset}')
            x=20+(index%columns)*cell_width
            y=78+(index//columns)*cell_height
            draw.rounded_rectangle((x,y,x+cell_width-10,y+cell_height-10),radius=8,
                fill=(34,39,46),outline=(99,82,65),width=2)
            with Image.open(asset) as original:
                sprite=original.convert('RGBA')
                bounds=sprite.getbbox()
                if bounds:sprite=sprite.crop(bounds)
                sprite=ImageOps.contain(sprite,(144,131),method=Image.Resampling.LANCZOS)
                overlay=Image.new('RGBA',sprite.size,(0,0,0,0))
                overlay.alpha_composite(sprite)
                backing=Image.new('RGBA',(144,131),(60,57,54,255))
                backing.alpha_composite(overlay,((144-sprite.width)//2,(131-sprite.height)//2))
                sheet.paste(backing.convert('RGB'),(x+21,y+12))
            label=uid.removeprefix('core:').removesuffix('_piece').replace('_',' ')
            draw.text((x+14,y+149),label[:23],fill=(235,226,209),font=font)
        path=output/(category+'.png')
        sheet.save(path,optimize=True)
        generated.append(str(path))
    return generated


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,
                        default=ROOT/'docs/art/interior_pass2_sheets')
    args=parser.parse_args()
    for path in build_sheets(args.output):
        print(path)


if __name__=='__main__':
    main()
