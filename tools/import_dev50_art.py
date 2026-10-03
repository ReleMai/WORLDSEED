"""Register individual imagegen cutouts; retain originals and normalize animal exports.

This mechanical import uses the existing livestock export pipeline after the
actual chicken correction has been authored by imagegen, not by pixel edits.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from PIL import Image

from tools.import_dev43_settlement_assets import _normalize


def main():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / 'docs/handoffs/DEV50_ART_MANIFEST.json').read_text(encoding='utf-8'))
    visual_path = root / 'worldseed/assets/visuals.json'
    visuals = json.loads(visual_path.read_text(encoding='utf-8'))
    for row in manifest:
        source, name, kind = Path(row['source']), row['name'], row['kind']
        if not name.replace('_', '').isalnum() or kind not in {'container', 'chicken'}:
            raise ValueError('Invalid Dev50 asset identity')
        with Image.open(source) as im:
            alpha = im.convert('RGBA').getchannel('A')
            if 'A' not in im.getbands() or alpha.getextrema()[0] != 0 or alpha.getbbox() is None:
                raise ValueError(f'Asset must have visible content and genuine alpha: {name}')
            relative = (f'assets/sprites/containers/dev50/{name}.png' if kind == 'container'
                        else f'assets/sprites/species/domestic/dev50/{name}.png')
            destination = root / 'worldseed' / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if kind == 'container':
                if not destination.exists():
                    shutil.copyfile(source, destination)
                elif destination.read_bytes() != source.read_bytes():
                    raise ValueError(f'Refusing to replace different art: {destination}')
                visuals.setdefault('containers', {})['core:' + name] = relative
            else:
                if not destination.exists():
                    _normalize(im, (320, 256)).save(destination, optimize=True)
            print(f'{name}: imported to {relative}')
    visuals['species']['core:chicken'] = [f'assets/sprites/species/domestic/dev50/chicken_{i}.png' for i in (0, 1)]
    visual_path.write_text(json.dumps(visuals, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
