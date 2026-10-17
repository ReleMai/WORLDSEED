"""Read-only daylight shadows for currently authorized outdoor ground.

No physics or time changes; shadows never reveal unknown or indoor cells.
"""
from __future__ import annotations
from math import pi, sin

from .gl_worldspace import SpriteCommand
from .worldspace import WorldFoot

CONTACT_W,CONTACT_H=24,12
CONTACT_BYTES=bytes(
    channel for y in range(CONTACT_H) for x in range(CONTACT_W)
    for channel in (10,14,20,max(0,min(105,int(105*(1-((x+0.5-CONTACT_W/2)/(CONTACT_W/2))**2
                      -((y+0.5-CONTACT_H/2)/(CONTACT_H/2))**2)))))
)

def sun_offset(minute,scale):
    """Solar-noon short shadows and long dawn/dusk shadows."""
    h=(int(minute)%1440)/60.
    if not 6.<h<18.:
        return None
    t=(h-6.)/12.
    altitude=sin(pi*t)
    distance=(1.55-altitude*.95)*float(scale)
    return ((.5-t)*distance*2.,(.38+(.55-altitude)*.22)*distance,
            .18+.20*altitude)

def ground_clips(camera,ground_cells,bounds,limit=480):
    clips=[]
    x0,y0,x1,y1=bounds
    for x,y,z in sorted(ground_cells,key=lambda p:(p[1],p[0])):
        if z!=camera.center.z:continue
        px,py=camera.to_screen(WorldFoot(x,y,z))
        a,b,c,d=px,py,px+camera.scale,py+camera.scale
        if a < x1 and c > x0 and b < y1 and d > y0:
            clips.append((a,b,c,d))
            if len(clips)==limit:break
    return tuple(clips)

def _silhouette(materials,source):
    key=('shadow-outline',source[0],source[1])
    def prepare():
        rgba=source[2]
        pixels=bytearray(len(rgba))
        for i in range(0,len(rgba),4):
            pixels[i:i+4]=bytes((10,14,19,rgba[i+3]))
        return ('shadow:'+str(source[0]),source[1],bytes(pixels),source[3],source[4])
    reader=getattr(materials,'_read',None)
    return reader(key,prepare) if callable(reader) else prepare()

def sunlight_commands(camera,viewer,buildings,visible_ground,materials,minute):
    if camera.center.z!=0:return ()
    solar=sun_offset(minute,camera.scale)
    commands=[]
    foot_x,foot_y=camera.to_screen(viewer)
    # Physical contact stays directly under the feet at every hour.
    # Directional daylight is a separate, weaker cast.
    player=(foot_x-camera.scale*.32,foot_y-camera.scale*.14,
            foot_x+camera.scale*.32,foot_y+camera.scale*.06)
    clip=ground_clips(camera,visible_ground,player)
    if clip:
        commands.append(SpriteCommand('sun-shadow:player','sun-shadow-contact',1,
            CONTACT_BYTES,CONTACT_W,CONTACT_H,player,clip,opacity=.86))
    if solar is None or not buildings:return tuple(commands)
    dx,dy,strength=solar
    from .gpu_buildings import _art
    for row in buildings:
        left,top,right,bottom=row.shell.bounds
        x0,y0=camera.to_screen(WorldFoot(left,top,0))
        x1,y1=camera.to_screen(WorldFoot(right+1,bottom+1,0))
        bounds=(x0+dx,y0+dy,x1+dx,y1+dy)
        clip=ground_clips(camera,visible_ground,bounds)
        if not clip:continue
        source=_silhouette(materials,_art(materials,row).body)
        commands.append(SpriteCommand('sun-shadow:building:'+row.shell.uid,*source,
                                      bounds,clip,opacity=strength*.9))
    return tuple(commands)
