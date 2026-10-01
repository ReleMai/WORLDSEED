"""Copy authored originals and mechanically register their stable visual IDs.

No alpha extraction or visual editing occurs here. Invalid cutouts are rejected
so they can be repaired with the original image-generation tool.
"""
import argparse
import json
import shutil
from pathlib import Path

from PIL import Image


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest',type=Path)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    visuals_path=root/'worldseed/assets/visuals.json'
    visuals=json.loads(visuals_path.read_text(encoding='utf-8'))
    rows=json.loads(args.manifest.read_text(encoding='utf-8'))
    for row in rows:
        source=Path(row['source']);name=row['name']
        if not name.replace('_','').isalnum():raise ValueError('Invalid asset basename')
        with Image.open(source) as im:
            if 'A' not in im.getbands() or im.getchannel('A').getextrema()[0]!=0:
                raise ValueError(f'Asset lacks transparent alpha: {name}')
            width,height=im.size
        if name.startswith('door_'):
            group,key,directory='building_doors',name[5:],'buildings/dev47'
        elif name.endswith('_piece'):
            group,key,directory='interiors','core:'+name,'interiors/dev47'
        else:
            group,key,directory='building_shells',name,'buildings/dev47'
        relative=f'assets/sprites/{directory}/{name}.png'
        destination=root/'worldseed'/relative
        destination.parent.mkdir(parents=True,exist_ok=True)
        if not destination.exists():shutil.copyfile(source,destination)
        elif destination.read_bytes()!=source.read_bytes():
            raise ValueError(f'Refusing to overwrite different artwork: {destination}')
        visuals.setdefault(group,{})[key]=relative
        print(f'{key}: {width}x{height}, preserved alpha -> {relative}')
    # Retain the unique Dev46 single bed; each other furnishing has its own art.
    interiors=visuals.setdefault('interiors',{})
    interiors['core:single_bed_piece']='assets/sprites/interiors/cottage_bed.png'
    # These exact station counterparts already have authored custom artwork.
    # Execution aliases with different visual meaning deliberately keep their
    # own settlement-piece art or explicit glyph fallback instead of borrowing.
    station_art={
        'forge_piece':'forge', 'carpenter_bench_piece':'workbench',
        'millstone_piece':'millstone', 'bakery_oven_piece':'bakery_oven',
        'butcher_table_piece':'butcher_table', 'loom_piece':'loom',
        'tanning_rack_piece':'tanning_frame', 'pottery_wheel_piece':'pottery_wheel',
        'brewery_vat_piece':'brewery_vat', 'herbalist_table_piece':'herbalist_table',
        'masonry_bench_piece':'masonry_bench', 'smoke_rack_piece':'smoke_rack',
    }
    for piece,station in station_art.items():
        ref=visuals.get('structures',{}).get('core:'+station)
        if ref is not None:interiors['core:'+piece]=ref
    # Catalog registration is a bulk mechanical JSON rewrite, not image editing.
    visuals_path.write_text(json.dumps(visuals,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')


if __name__=='__main__':main()
