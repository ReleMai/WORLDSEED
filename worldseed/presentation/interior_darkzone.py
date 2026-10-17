"""Inward-only penumbra on the boundary of already authorized indoor sight.

Shared patch edges cancel, including coarse/fine neighbors. No hidden floor,
room, light or entity is consulted, and no pixel outside sight is admitted.
"""
from functools import lru_cache

from .gl_worldspace import SpriteCommand


def sight_boundary(rectangles):
    lines={}
    for a,b,c,d in rectangles:
        for axis,fixed,start,end,side in (
                ('y',b,a,c,1),('y',d,a,c,-1),
                ('x',a,b,d,1),('x',c,b,d,-1)):
            events=lines.setdefault((axis,fixed),{})
            events[start]=events.get(start,0)+side
            events[end]=events.get(end,0)-side
    result=[]
    for (axis,fixed),events in sorted(lines.items()):
        active=0
        start=None
        for point,delta in sorted(events.items()):
            new=active+delta
            if new != active:
                if active and start is not None:
                    result.append((axis,fixed,start,point,1 if active>0 else -1))
                start=point
                active=new
    return tuple(result)


@lru_cache(maxsize=4)
def _edge_texture(axis,side):
    width,height=(32,1) if axis=='x' else (1,32)
    values=[]
    for index in range(32):
        t=(index+.5)/32
        if side<0:t=1-t
        # A broad smooth penumbra finishes almost black at the unknown edge.
        alpha=round(248*(1-t*t*(3-2*t)))
        values.extend((7,10,15,alpha))
    return ('indoor-darkzone:'+axis+str(side),1,bytes(values),width,height)


def darkzone_commands(clips,index,scale,*,budget=512):
    if budget <= 0:
        return ()
    width=max(2.,min(18.,scale*.32))
    commands=[]
    for axis,fixed,start,end,side in sight_boundary(clips):
        lo,hi=(fixed,fixed+width) if side>0 else (fixed-width,fixed)
        bounds=(lo,start,hi,end) if axis=='x' else (start,lo,end,hi)
        admitted=index.intersect(bounds)
        for clip in admitted:
            if len(commands) >= budget:
                return tuple(sorted(commands,key=lambda command:command.texture_id))
            commands.append(SpriteCommand('interior-fog:'+str(len(commands)),
                *_edge_texture(axis,side),bounds,(clip,)))
    # Group immutable gradients for exact clipped-mesh batching.
    return tuple(sorted(commands,key=lambda command:command.texture_id))
