"""Purpose-built top-down timber, masonry and plaster wall art (GPU-only).

These are seamless, bounded RGBA textures generated deterministically once per
physical footprint. No save/loot/hitbox/LOS data changes or asset IO per frame.
"""
from __future__ import annotations
from functools import lru_cache

REVISION=2

def _shade(x,y,w,h,style,structural):
    horiz=w>=h
    along=x if horiz else y
    across=y if horiz else x
    thick=h if horiz else w
    edge=min(across,thick-1-across)
    # A subtle top-left rim and dark base clearly anchors the wall to floor.
    bevel=(15 if across<=1 else -23 if across>=thick-2 else 0)
    grit=((x*7919 ^ y*3037 ^ (x*y+11)*89)&15)-7
    if style=='stone':
        rows=max(1,thick//5)
        band=across//max(3,thick//rows)
        joint=(along+(band%2)*11)%23
        mortar=joint in (0,1) or (across%max(3,thick//rows)==0)
        base=(111,110,108) if structural else (140,135,126)
        diff=(-34 if mortar else ((along*17+band*29)%23-11))
        values=[v+diff+grit//2+bevel for v in base]
    elif style=='timber':
        joint=along%21
        rail=across<max(2,thick//5) or across>=thick-max(2,thick//5)
        base=(104,72,46) if structural else (142,109,72)
        diff=(19 if rail else -22 if joint in (0,1) else
              5 if along%21 in (2,3) else (along//3+across)%12-6)
        values=[v+diff+grit//2+bevel for v in base]
    else:
        stud=along%34 in (0,1,2)
        rail=across<max(2,thick//6) or across>=thick-max(2,thick//6)
        base=(189,171,138) if structural else (208,197,170)
        if stud or rail:base=(117,83,53) if structural else (151,113,77)
        values=[v+grit+bevel for v in base]
    return (*(max(25,min(245,int(v))) for v in values),255)


@lru_cache(maxsize=160)
def _paint(style,structural,width,height):
    if not (4<=width<=512 and 4<=height<=512):
        raise ValueError('wall-art dimensions out of bounds')
    rgba=bytearray(width*height*4)
    for y in range(height):
        for x in range(width):
            i=(y*width+x)*4
            rgba[i:i+4]=bytes(_shade(x,y,width,height,style,structural))
    return (f'gpu:interior-wall-v{REVISION}:{style}:{int(structural)}:{width}x{height}',
            REVISION,bytes(rgba),width,height)


def wall_art(kind,base_id,rect):
    a,b,c,d=rect
    if c<=a or d<=b:
        return None
    ident=base_id.lower()
    style=('stone' if 'stone' in ident or 'slate' in ident or 'fieldstone' in ident
        else 'timber' if 'timber' in ident or 'oak' in ident or 'wood' in ident
        else 'plaster')
    # Match actual measured meters, not transparent painting source padding.
    # Limit dimensions and quantize for deterministic cache reuse.
    w=max(4,min(512,round((c-a)*.032)))
    h=max(4,min(512,round((d-b)*.032)))
    return _paint(style,kind=='structural',w,h)
