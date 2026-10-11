"""Art projection for persistent player homesteads.

An exterior sprite is presentation only.  The reserved cells and actual door
come from homestead_blueprints.  In particular, rotating a blueprint must never
move its collision footprint or invent a different entrance.
"""
from __future__ import annotations

from pathlib import Path

from worldseed.systems.homestead_blueprints import catalog, doorway, footprint

ASSET_ROOT=Path(__file__).resolve().parents[1]/"assets"/"sprites"/"buildings"/"homestead"
DOOR_IMAGE_X={
    "log_cabin_01":.20,"log_cabin_02":.63,
    "log_cabin_03":.39,"log_cabin_04":.34,
    "log_cabin_05":.81,"log_cabin_06":.45,
    "log_cabin_07":.17,"log_cabin_08":.79,
    "log_cabin_09":.46,"log_cabin_10":.83,
}
DOOR_IMAGE_Y={
    "log_cabin_01":.81,"log_cabin_02":.86,
    "log_cabin_03":.86,"log_cabin_04":.86,
    "log_cabin_05":.84,"log_cabin_06":.86,
    "log_cabin_07":.86,"log_cabin_08":.85,
    "log_cabin_09":.84,"log_cabin_10":.85,
}

def cabin_asset_path(style_id:str)->Path|None:
    style=catalog()[1].get(style_id)
    if not style or style.get("home_id")!="log_cabin":return None
    path=ASSET_ROOT/(str(style_id)+".png")
    return path if path.is_file() else None

def doorway_pixel(site,grid_x:int,grid_y:int,left:int,top:int,size:int):
    """Exact render-space center of the authoritative entrance tile."""
    inside,_=doorway(site)
    return (grid_x+(inside[0]-left+.5)*size,
            grid_y+(inside[1]-top+.5)*size)

def cabin_image_rect(site,grid_x:int,grid_y:int,left:int,top:int,size:int,source_size):
    """Position the upright isometric exterior over the reserved 3x3 cell area.

    Only south-facing exteriors place their painted door directly above its
    doorstep. Other orientations keep an upright (not sideways-rotated) roof;
    the explicit physical door below is drawn at the actual rotated doorway.
    """
    cells=footprint(site)
    lo_x=min(x for x,y,z in cells);hi_x=max(x for x,y,z in cells)
    lo_y=min(y for x,y,z in cells);hi_y=max(y for x,y,z in cells)
    bounds_width=(hi_x-lo_x+1)*size
    iw=max(12,round(bounds_width*1.16))
    ih=max(12,round(iw*source_size[1]/max(1,source_size[0])))
    px=grid_x+(lo_x-left)*size
    py=grid_y+(lo_y-top)*size
    if site["orientation"]==0:
        door_x,door_y=doorway_pixel(site,grid_x,grid_y,left,top,size)
        ix=round(door_x-iw*DOOR_IMAGE_X[site["style_id"]])
        iy=round(door_y+size*.24-ih*DOOR_IMAGE_Y[site["style_id"]])
    else:
        ix=px+(bounds_width-iw)//2
        iy=py+(hi_y-lo_y+1)*size-ih-round(size*.1)
    return ix,iy,iw,ih

def doorway_edge_rect(pg,site,grid_x:int,grid_y:int,left:int,top:int,size:int):
    """One edge of the actual entry tile, never the sprite's painted roof."""
    (wx,wy,z),_=doorway(site)
    x=grid_x+(wx-left)*size;y=grid_y+(wy-top)*size
    thick=max(2,size//9);m=max(2,size//5)
    orientation=int(site["orientation"])
    if orientation==0:return pg.Rect(x+m,y+size-thick-2,size-2*m,thick)
    if orientation==2:return pg.Rect(x+m,y+2,size-2*m,thick)
    if orientation==1:return pg.Rect(x+2,y+m,thick,size-2*m)
    return pg.Rect(x+size-thick-2,y+m,thick,size-2*m)

def draw_cabin_art(term,site,*,grid_x,grid_y,left,top,size,clip,opacity=255):
    """Draw an authored sprite. Returns painted rect, or None if not installed.

    Exact door markers are drawn by the owner view, after the art, so they
    remain at the same real tile in the world and placement preview.
    """
    path=cabin_asset_path(str(site.get("style_id","")))
    if path is None:return None
    pg=term.pg
    original=term._load_sprite(path,size*5,size*5,smooth=True)
    if original is None:return None
    x,y,w,h=cabin_image_rect(site,grid_x,grid_y,left,top,size,original.get_size())
    art=term._load_sprite(path,w,h,smooth=True)
    if art is None:return None
    # East/west door orientation changes perspective, but never rotates an
    # upright cabin sideways. Physical door is separately painted on its edge.
    if site["orientation"] in (2,3):
        key=("homestead-mirror-v1",str(path),w,h)
        flip=term._sprite_cache.get(key)
        if flip is None:
            flip=pg.transform.flip(art,True,False)
            term._sprite_cache[key]=flip
        art=flip
    if opacity!=255:
        art=art.copy()
        art.set_alpha(max(0,min(255,int(opacity))))
    old=term.screen.get_clip()
    term.screen.set_clip(pg.Rect(clip).clip(old))
    term.screen.blit(art,(x,y))
    term.screen.set_clip(old)
    return pg.Rect(x,y,art.get_width(),art.get_height())
