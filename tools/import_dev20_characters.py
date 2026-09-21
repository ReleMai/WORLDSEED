"""Slice the authored RGBA atlas; preserve alpha and normalize actor baselines.
Requires pygame-ce. Run from the repository root.
"""
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
import json
from pathlib import Path
import pygame as pg
pg.init()
pg.display.set_mode((1, 1))
root = Path(__file__).resolve().parents[1]
atlas = pg.image.load(str(root/'artifacts/source-art/dev20_survivors.png')).convert_alpha()
# Authored atlas has six columns with deliberately generous gutters.
xs = [65, 285, 530, 775, 1010, 1250, 1490]
ys = [0, 275, 554, 805, 1024]
paths = []
for row in range(4):
    for col in range(6):
        tile = atlas.subsurface(pg.Rect(xs[col],ys[row],xs[col+1]-xs[col],ys[row+1]-ys[row])).copy()
        bounds = tile.get_bounding_rect(min_alpha=16)
        tile = tile.subsurface(bounds).copy()
        height = 240
        tile = pg.transform.smoothscale(tile,(round(tile.get_width()*height/tile.get_height()),height))
        canvas = pg.Surface((160,256), pg.SRCALPHA)
        canvas.blit(tile,((160-tile.get_width())//2,248-height))
        path=f'assets/sprites/characters/dev20_{row*6+col:02d}.png'
        pg.image.save(canvas,str(root/'worldseed'/path));paths.append(path)
manifest_path=root/'worldseed/assets/visuals.json'
manifest=json.loads(manifest_path.read_text())
manifest['player_variants']={'male':paths[:10],'female':paths[12:22]}
manifest['npc_variants']=paths
manifest['special']['player']=paths[0]
manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
pg.quit()
print('Imported 20 player appearances and 24 NPC appearances')
