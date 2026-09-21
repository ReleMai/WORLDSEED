from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageEnhance

ROOT = Path(__file__).resolve().parents[1]
ATLAS = ROOT / 'artifacts' / 'source-art' / 'worldseed_terrain_texture_atlas.png'
OUT = ROOT / 'worldseed' / 'assets' / 'sprites' / 'terrain'

# The generated atlas uses a regular ten-column artwork grid.  Coordinates
# intentionally stay inside the decorative border so captions never enter the
# runtime texture.
COL_BORDERS = [14, 152, 295, 438, 580, 722, 864, 1007, 1149, 1292, 1434]
ROW_BOUNDS = [(84, 220), (273, 411), (456, 595), (641, 778), (829, 967)]
INSET = 5

SOURCES = {
    'grass_hd.png': (0, 1),           # plains grass
    'forest_hd.png': (0, 3),          # dense forest floor
    'scrub_hd.png': (0, 4),
    'tilled_soil_hd.png': (0, 5),
    'rock_hd.png': (0, 7),            # rocky ground
    'wetland_hd.png': (1, 0),
    'river_hd.png': (1, 1),
    'river_shallow_hd.png': (3, 1),
    'water_hd.png': (1, 2),
    'sand_bank_hd.png': (1, 3),
    'sand_hd.png': (1, 7),
    'tundra_hd.png': (1, 8),
    'mud_hd.png': (1, 9),
    'floodplain_hd.png': (0, 0),      # grassland meadow
}


def crop_cell(atlas: Image.Image, row: int, col: int) -> Image.Image:
    left, right = COL_BORDERS[col], COL_BORDERS[col + 1]
    top, bottom = ROW_BOUNDS[row]
    box = (left + INSET, top + INSET, right - INSET, bottom - INSET)
    img = atlas.crop(box).convert('RGB')
    img = ImageEnhance.Contrast(img).enhance(1.03)
    return img.resize((128, 128), Image.Resampling.LANCZOS).convert('RGBA')


def main():
    atlas = Image.open(ATLAS)
    OUT.mkdir(parents=True, exist_ok=True)
    for filename, (row, col) in SOURCES.items():
        img = crop_cell(atlas, row, col)
        img.save(OUT / filename, optimize=True)
        print(OUT / filename)


if __name__ == '__main__':
    main()
