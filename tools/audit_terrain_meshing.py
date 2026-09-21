"""Audit data-driven local terrain meshing for current/future terrain content."""
from __future__ import annotations
from itertools import combinations
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.presentation.local_terrain import configure_terrain_catalog, can_blend, transition_profile
from worldseed.presentation.visuals import VisualRegistry


def main() -> int:
    reg=ContentRegistry.load(DATA_DIR);vis=VisualRegistry.load_default();configure_terrain_catalog(reg.terrains)
    excluded={'shaft','loot','ore'}
    blendable=[]
    for tid,td in sorted(reg.terrains.items()):
        tags=set(td.tags)
        if ('surface' in tags or 'underground' in tags) and not tags.intersection(excluded):
            blendable.append(tid)
    issues=[];pairs=0
    for tid in blendable:
        if not vis.ref('terrain',tid).paths:issues.append(f'missing terrain visual: {tid}')
    for a,b in combinations(blendable,2):
        if not can_blend(a,b):issues.append(f'mesher rejected blendable pair: {a} <-> {b}');continue
        depth,alpha=transition_profile(a,b);pairs+=1
        if not 2<=depth<=12 or not 40<=alpha<=220:issues.append(f'bad blend profile {a}/{b}: {depth},{alpha}')
    # Hard authored topology/features must remain excluded even if underground.
    for tid in ('core:shaft','core:iron_vein','core:coal_seam','core:copper_vein','core:relic_cache'):
        if tid in reg.terrains and can_blend('core:grass',tid):issues.append(f'hard feature entered ground mesher: {tid}')
    print(f'blendable terrain ids: {len(blendable)}')
    print(f'validated pair profiles: {pairs}')
    print('grass <-> floodplain:', 'blend' if can_blend('core:grass','core:floodplain') else 'FAIL')
    if issues:
        print('ISSUES')
        print('\n'.join(' - '+x for x in issues))
        return 1
    print('terrain meshing audit: PASS')
    return 0

if __name__=='__main__':raise SystemExit(main())
