"""Top-down connected roofs built from the existing authored construction textures.

Only the physically occupied footprint is painted. Missing cells/courtyards
remain transparent, and no game state is consulted by this visual helper.
"""
from __future__ import annotations
from hashlib import blake2b
from pathlib import Path

ROOF_DIR=Path(__file__).resolve().parents[1]/'assets'/'sprites'/'settlement_materials'
ROOFS=('roof_thatch','roof_timber_shingle','roof_slate','roof_clay',
       'roof_reed','roof_plank','roof_sod','roof_stone')

def roof_name(shell,variant_id=''):
    kind=str(shell.function).lower()
    if any(w in kind for w in ('chapel','shrine','school','archive','barrack','guard','fortress')):
        return 'roof_slate'
    if any(w in kind for w in ('forge','smith','potter','foundry','mason','tannery')):
        return 'roof_clay'
    if any(w in kind for w in ('farm','barn','stable','granary','mill','hay')):
        return 'roof_thatch'
    if any(w in kind for w in ('fisher','reed','netmaker','fishery')):
        return 'roof_reed'
    token=(str(variant_id or shell.uid)+'|'+kind).encode('utf-8')
    return ROOFS[int.from_bytes(blake2b(token,digest_size=2).digest(),'big')%len(ROOFS)]

def roof_surface(pg,shell,width,height,texture):
    surface=pg.Surface((width,height),pg.SRCALPHA)
    left,top,right,bottom=shell.bounds
    cols,rows=right-left+1,bottom-top+1
    occupied=frozenset(shell.footprint)
    for x,y in sorted(occupied,key=lambda p:(p[1],p[0])):
        gx,gy=x-left,y-top
        xa,xb=gx*width//cols,(gx+1)*width//cols
        ya,yb=gy*height//rows,(gy+1)*height//rows
        if xa==xb or ya==yb:continue
        w,h=xb-xa,yb-ya
        surface.fill((99,80,63,255),(xa,ya,w,h))
        surface.blit(pg.transform.smoothscale(texture,(w,h)),(xa,ya))
        edge=max(1,min(w,h)//12)
        if (x,y-1) not in occupied:
            pg.draw.line(surface,(148,126,99,255),(xa,ya),(xb-1,ya),edge)
        if (x,y+1) not in occupied:
            pg.draw.line(surface,(46,38,31,245),(xa,yb-1),(xb-1,yb-1),edge)
        if (x-1,y) not in occupied:
            pg.draw.line(surface,(88,70,52,255),(xa,ya),(xa,yb-1),edge)
        if (x+1,y) not in occupied:
            pg.draw.line(surface,(53,43,35,255),(xb-1,ya),(xb-1,yb-1),edge)
    return surface
