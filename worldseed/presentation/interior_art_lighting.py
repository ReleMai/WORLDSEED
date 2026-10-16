"""Bounded top-down interior lighting and proportion-aware shadow artwork.

Visual-only sprite sources: no additional lamps, simulated light, object IDs,
loot, ownership or collision. All generated pixels are tiny and deterministic.
"""
from __future__ import annotations

from functools import lru_cache
from math import hypot, exp

SHADOW_SIZE=(64,40)
GLOW_SIZE=(64,64)
WALL_SHADE_SIZE=(8,32)
MAX_VISIBLE_HALO_SOURCES=8


def _rgba(size, sample):
    width,height=size
    pixels=bytearray(width*height*4)
    for y in range(height):
        for x in range(width):
            red,green,blue,alpha=sample((x+.5)/width,(y+.5)/height)
            pos=4*(y*width+x)
            pixels[pos:pos+4]=bytes((max(0,min(255,round(v))) for v in
                                    (red,green,blue,alpha)))
    return bytes(pixels)


@lru_cache(maxsize=1)
def shadow_texture():
    # Feathery dark footprint, without the old hard ellipse boundary.
    width,height=SHADOW_SIZE
    rgba=_rgba((width,height),lambda u,v: (
        17,13,10,120*exp(-4.2*((u-.5)/.5)**2-4.8*((v-.5)/.5)**2)))
    return ('indoor-soft-shadow-v2',1,rgba,width,height)


@lru_cache(maxsize=1)
def warm_glow_texture():
    # Small, diffused orange center with an extended transparent edge.
    width,height=GLOW_SIZE
    rgba=_rgba((width,height),lambda u,v: (
        255,157,75,125*exp(-5.6*((u-.5)/.5)**2-5.6*((v-.5)/.5)**2)))
    return ('indoor-warm-glow-v2',1,rgba,width,height)


@lru_cache(maxsize=1)
def wall_ambient_occlusion_texture():
    width,height=WALL_SHADE_SIZE
    rgba=_rgba((width,height),lambda u,v: (16,13,12,94*(1-v)**2.4))
    return ('indoor-wall-ambient-shadow-v2',1,rgba,width,height)


def shadow_bounds(rect, source, scale, *, height_ratio=1.):
    """Scale projected footprint by physical rectangle, not sprite padding.

    Source is an already visible prepared local-space light, never a private
    light on the other side of a wall.
    """
    x0,y0,x1,y1=rect
    width=x1-x0
    height=y1-y0
    cx=(x0+x1)*.5
    cy=y1-height*.13
    if source is None:
        dx,dy=.11*scale,.16*scale
    else:
        sx,sy=source
        vx,vy=cx-sx,cy-sy
        length=hypot(vx,vy)
        if length<.01:
            dx,dy=.09*scale,.10*scale
        else:
            offset=min(scale*.42,scale*(.12+.035*max(1.,height_ratio)))
            dx,dy=vx/length*offset,vy/length*offset
    return (cx-width*.47+dx,cy-height*.28+dy,
            cx+width*.47+dx,cy+height*.22+dy)


def light_halo_bounds(x,y,radius,camera_scale):
    """Max four-tile visual range regardless of source simulation radius."""
    extent=min(3.5,max(.55,float(radius)/1000*.6))*camera_scale
    return (x-extent,y-extent,x+extent,y+extent)


def nearest_light(x,y,sources):
    if not sources:return None
    s=min(sources,key=lambda s:((s.x/1000-x)**2+(s.y/1000-y)**2,s.uid))
    return s.x/1000,s.y/1000
