"""A continuous inward penumbra over already authorized indoor sight.

Only a small alpha mask is rasterized, never terrain or a software world frame.
The blurred mask cannot admit pixels: exact live sight clips remain mandatory.
"""
from functools import lru_cache
from hashlib import blake2b
from math import ceil

from .gl_worldspace import SpriteCommand
from .interior_clip_index import union_rects

MAX_MASK_EDGE=256


@lru_cache(maxsize=2)
def _mask_source(rectangles,width,height,radius):
    import pygame as pg
    mask=pg.Surface((width,height),pg.SRCALPHA)
    for a,b,c,d in rectangles:
        pg.draw.rect(mask,(0,0,0,255),(a,b,c-a,d-b))
    # Three native sliding-window box filters approximate a Gaussian without
    # the radius-dependent convolution cost of pygame's gaussian_blur.
    blurred=mask
    for _ in range(3):
        blurred=pg.transform.box_blur(blurred,radius,repeat_edge_pixels=False)
    # One smooth field avoids multiplying overlapping corner/edge strips.
    # Twice the inverse coverage reaches black at the true visibility edge.
    fog=pg.Surface((width,height),pg.SRCALPHA)
    fog.fill((3,5,7,255))
    fog.blit(blurred,(0,0),special_flags=pg.BLEND_RGBA_SUB)
    fog.blit(fog,(0,0),special_flags=pg.BLEND_RGBA_ADD)
    rgba=pg.image.tobytes(fog,'RGBA')
    identity=blake2b(rgba,digest_size=12).hexdigest()
    return ('indoor-darkzone:'+identity,1,rgba,width,height)


def darkzone_commands(clips,index,scale,*,budget=512):
    if budget<=0 or not clips:
        return ()
    parts=union_rects(clips)
    if not parts:
        return ()
    # Camera translation disappears from the cache key; no per-edge queries.
    feather=max(3.,min(20.,scale*.36))
    padding=feather*2
    left=min(r[0] for r in parts)-padding
    top=min(r[1] for r in parts)-padding
    right=max(r[2] for r in parts)+padding
    bottom=max(r[3] for r in parts)+padding
    step=max(1.,(right-left)/MAX_MASK_EDGE,(bottom-top)/MAX_MASK_EDGE)
    width=max(1,min(MAX_MASK_EDGE,ceil((right-left)/step)))
    height=max(1,min(MAX_MASK_EDGE,ceil((bottom-top)/step)))
    rectangles=tuple((ceil((a-left)/step-.5),ceil((b-top)/step-.5),
                      ceil((c-left)/step-.5),ceil((d-top)/step-.5))
                     for a,b,c,d in parts)
    source=_mask_source(rectangles,width,height,max(1,round(feather*.32/step)))
    return (SpriteCommand('interior-fog:field',*source,
        (left,top,left+width*step,top+height*step),tuple(clips)),)
