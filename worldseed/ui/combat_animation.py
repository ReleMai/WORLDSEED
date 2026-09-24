from __future__ import annotations

from worldseed.core.coords import WorldPos


def _arrow_glyph(a:WorldPos,b:WorldPos,use_unicode:bool=True)->str:
    dx=b.x-a.x;dy=b.y-a.y
    if abs(dx)>=abs(dy) and dx:
        return "→" if use_unicode and dx>0 else "←" if use_unicode else ">" if dx>0 else "<"
    if dy:
        return "↓" if use_unicode and dy>0 else "↑" if use_unicode else "v" if dy>0 else "^"
    return "•" if use_unicode else "*"


def combat_animation_frames(kind:str,cells:tuple[WorldPos,...],*,use_unicode:bool=True)->tuple[dict,...]:
    """Pure presentation frames; callers may display them without mutating simulation."""
    if len(cells)<2:return ()
    kind=str(kind)
    frames=[]
    if kind=="ranged":
        trail=cells[1:]
        stride=max(1,len(trail)//5)
        indices=list(range(0,len(trail),stride))
        if indices[-1]!=len(trail)-1:indices.append(len(trail)-1)
        for idx in indices[:6]:
            cell=trail[idx];prev=cells[max(0,idx)]
            glyph=_arrow_glyph(prev,cell,use_unicode)
            rows=[]
            if idx>0:
                tail=trail[max(0,idx-1)]
                rows.append({"x":tail.x,"y":tail.y,"z":tail.z,"chance":65,"glyph":"·" if use_unicode else "."})
            rows.append({"x":cell.x,"y":cell.y,"z":cell.z,"chance":95,"glyph":glyph})
            frames.append({"cells":rows})
    elif kind in ("melee","bash"):
        target=cells[-1]
        glyph=("╱" if kind=="melee" else "◆") if use_unicode else ("/" if kind=="melee" else "#")
        frames.append({"cells":[{"x":target.x,"y":target.y,"z":target.z,"chance":92,"glyph":glyph}]})
        frames.append({"cells":[{"x":target.x,"y":target.y,"z":target.z,"chance":55,"glyph":"✦" if use_unicode else "*"}]})
    return tuple(frames)
