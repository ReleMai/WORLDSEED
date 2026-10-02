"""Preserve generated originals and mechanically register Dev48 interior art.

No pixel, alpha or composition edits occur here. The source manifest records
the built-in imagegen prompt and original file for each individual asset.
"""
import argparse
import json
import shutil
from pathlib import Path

from PIL import Image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    visuals_path = root / 'worldseed/assets/visuals.json'
    visuals = json.loads(visuals_path.read_text(encoding='utf-8'))
    for row in json.loads(args.manifest.read_text(encoding='utf-8')):
        source, name, kind = Path(row['source']), row['name'], row['kind']
        if not name.replace('_', '').isalnum() or kind not in {'texture', 'station'}:
            raise ValueError('Invalid interior asset identity')
        with Image.open(source) as im:
            if kind == 'station' and ('A' not in im.getbands() or im.getchannel('A').getextrema()[0] != 0):
                raise ValueError(f'Station lacks transparent alpha: {name}')
            if kind == 'texture' and 'A' in im.getbands() and im.getchannel('A').getextrema()[0] != 255:
                raise ValueError(f'Interior texture must be opaque: {name}')
            width, height = im.size
        relative = f'assets/sprites/interiors/dev48/{name}.png'
        destination = root / 'worldseed' / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copyfile(source, destination)
        elif destination.read_bytes() != source.read_bytes():
            raise ValueError(f'Refusing to replace different art: {destination}')
        group = 'interior_textures' if kind == 'texture' else 'interiors'
        visual_id = 'core:interior_' + name if kind == 'texture' else 'core:' + name
        visuals.setdefault(group, {})[visual_id] = relative
        print(f'{visual_id}: {width}x{height}, original preserved -> {relative}')
    # A decorative read model of existing functions/rooms, not new plan state.
    styles_path = root / 'worldseed/assets/interior_styles.json'
    visuals['interior_styles'] = json.loads(styles_path.read_text(encoding='utf-8'))
    visuals_path.write_text(json.dumps(visuals, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
