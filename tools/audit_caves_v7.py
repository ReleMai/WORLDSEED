"""Deterministic cave-v7 entrance/connectivity/geology audit."""
from __future__ import annotations
from collections import Counter
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.world.generator import WorldGenerator

SEED=b'dev16-cave-audit'

def main() -> int:
    reg=ContentRegistry.load(DATA_DIR);gen=WorldGenerator(SEED,reg,version=7);caves=gen.caves
    issues=[];entrances=[]
    for cy in range(-5,6):
        for cx in range(-5,6):
            ent=caves._entrance_for_cell(cx,cy)
            if not ent:continue
            entrances.append(ent)
            if gen.terrain_at(WorldPos(ent.x,ent.y,0))!='core:cave_mouth':issues.append(f'missing surface mouth {ent.x},{ent.y}')
            for d in range(1,ent.depth+1):
                if gen.terrain_at(WorldPos(ent.x,ent.y,-d))!='core:shaft':issues.append(f'broken connector {ent.x},{ent.y},-{d}')
            if not (ent.relief>=420 or ent.elevation>=43000):issues.append(f'implausibly flat entrance {ent}')
    print(f'entrances in 11x11 cave macro-cells: {len(entrances)}')
    if entrances:
        depths=[e.depth for e in entrances];print(f'entrance depth range: {min(depths)}..{max(depths)}')
    layers={}
    for z in (-1,-3,-6,-10):
        c=Counter(gen.terrain_at(WorldPos(x,y,z)) for y in range(-48,49) for x in range(-48,49));layers[z]=c
        print(f'z={z}: '+', '.join(f'{k.split(":")[-1]}={v}' for k,v in c.most_common()))
    if layers[-1]['core:coal_seam']==0:issues.append('no shallow coal')
    if layers[-1]['core:aquifer']==0:issues.append('no shallow aquifer')
    if layers[-3]['core:copper_vein']==0:issues.append('no mid-depth copper')
    if layers[-10]['core:iron_vein']<=layers[-3]['core:iron_vein']:issues.append('iron does not increase with depth in audit sample')
    if layers[-10]['core:coal_seam'] or layers[-10]['core:copper_vein']:issues.append('shallow/mid ores leaked into deep crystalline band')
    if issues:
        print('ISSUES');print('\n'.join(' - '+x for x in issues));return 1
    print('cave v7 audit: PASS');return 0

if __name__=='__main__':raise SystemExit(main())
