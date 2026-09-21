"""Export sample procedural assets and an atlas without opening a world/save."""
from pathlib import Path
import argparse
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('artifacts/regional-terrain-assets'))
    args = parser.parse_args()
    os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
    os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
    import pygame as pg
    from worldseed.presentation.regional_terrain import RegionalTerrainAssets

    pg.init()
    try:
        assets = RegionalTerrainAssets(pg)
        args.output.mkdir(parents=True, exist_ok=True)
        biomes = ['grassland', 'forest', 'highland', 'tundra', 'scrub', 'coast', 'water']
        variants = [('Temperate', 36000, 34000), ('Dry / rugged', 8000, 44000), ('Cold', 30000, 5000)]
        atlas = pg.Surface((1190, 600))
        atlas.fill((16, 22, 24))
        font = pg.font.SysFont('Consolas', 17)
        atlas.blit(font.render('PROCEDURAL REGIONAL TERRAIN - sample plans', True, (221, 204, 156)), (20, 12))
        for col, biome in enumerate(biomes):
            x = 140 + col * 148
            atlas.blit(font.render(biome.title(), True, (216, 220, 211)), (x, 45))
            for row, (label, moisture, temperature) in enumerate(variants):
                y = 76 + row * 170
                if col == 0:
                    atlas.blit(font.render(label, True, (170, 182, 170)), (10, y + 54))
                plan = SimpleNamespace(region_x=col, region_y=0, dominant_biome=biome,
                                       mean_moisture=moisture, mean_temperature=temperature,
                                       mean_elevation=56000 if biome == 'highland' else 32000,
                                       relief=30000 if row == 1 or biome == 'highland' else 0,
                                       biome_mix={biome: 25})
                surface = assets.surface(plan, 128)
                atlas.blit(surface, (x, y))
                pg.image.save(surface, str(args.output / f'core_{biome}_{row}.png'))
        pg.image.save(atlas, str(args.output / 'atlas.png'))
        print(f'Exported 21 sample assets and atlas to {args.output.resolve()}')
    finally:
        pg.quit()


if __name__ == '__main__':
    main()
