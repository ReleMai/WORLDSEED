"""Bounded inward-only sight feathering over detached, authorized rectangles."""
from functools import lru_cache
from hashlib import blake2b
from math import ceil
from .gl_worldspace import SightMask
from .interior_clip_index import union_rects


@lru_cache(maxsize=4)
def _pixels(rectangles, width, height, radius):
    import pygame as pg
    surface=pg.Surface((width,height),pg.SRCALPHA)
    for a,b,c,d in rectangles:
        pg.draw.rect(surface,(255,255,255,255),(a,b,c-a,d-b))
    for _ in range(3):
        surface=pg.transform.box_blur(surface,radius,repeat_edge_pixels=False)
    # Erode before easing: even concave stair corners disappear inside the
    # authorized boundary. Blur alone leaves visible square scissor edges.
    def value(a):
        t=max(0.,min(1.,(a/255.-.78)/.22))
        return round(255*t*t*(3-2*t))
    alpha=pg.image.tobytes(surface,'RGBA')[3::4].translate(bytes(value(a) for a in range(256)))
    rgba=bytearray(b'\xff\xff\xff\xff'*(width*height))
    rgba[3::4]=alpha
    rgba=bytes(rgba)
    return ('sight-mask:'+blake2b(rgba,digest_size=12).hexdigest(),1,rgba,width,height)


def sight_mask(rectangles, scale):
    parts=union_rects(rectangles)
    if not parts:return None
    feather=max(8.,scale*.8)
    left=min(r[0] for r in parts)-feather*2
    top=min(r[1] for r in parts)-feather*2
    right=max(r[2] for r in parts)+feather*2
    bottom=max(r[3] for r in parts)+feather*2
    step=max(1.,(right-left)/256,(bottom-top)/256)
    width=min(256,ceil((right-left)/step))
    height=min(256,ceil((bottom-top)/step))
    rects=tuple((ceil((a-left)/step-.5),ceil((b-top)/step-.5),
                ceil((c-left)/step-.5),ceil((d-top)/step-.5)) for a,b,c,d in parts)
    source=_pixels(rects,width,height,max(1,round(feather*.42/step)))
    return SightMask(*source,(left,top,left+width*step,top+height*step))


def mask_for_bounds(mask,bounds):
    """Skip shader work for a patch whose complete bilinear footprint is opaque."""
    if mask is None:return None
    from math import floor
    a,b,c,d=mask.bounds
    x,y,x1,y1=bounds
    left=max(0,floor((x-a)*mask.image_w/(c-a)-.5))
    top=max(0,floor((y-b)*mask.image_h/(d-b)-.5))
    right=min(mask.image_w,ceil((x1-a)*mask.image_w/(c-a)+.5))
    bottom=min(mask.image_h,ceil((y1-b)*mask.image_h/(d-b)+.5))
    for row in range(top,bottom):
        alpha=mask.rgba[(row*mask.image_w+left)*4+3:(row*mask.image_w+right)*4:4]
        if alpha and min(alpha)<255:return mask
    return None
