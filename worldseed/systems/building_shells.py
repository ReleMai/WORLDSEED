"""Bounded exterior shell read models derived from authoritative buildings."""
from __future__ import annotations

from dataclasses import dataclass


def enclosed_shell(structure) -> bool:
    return bool(structure and getattr(structure,"enclosed",False)
                and not getattr(structure,"destroyed",False)
                and int(getattr(structure,"condition",100))>0
                and getattr(structure,"footprint",()))


@dataclass(frozen=True,slots=True)
class BuildingShell:
    uid: str
    settlement_id: str
    function: str
    content_id: str
    footprint: tuple[tuple[int,int],...]
    entrance: tuple[int,int] | None
    door_uid: str
    orientation: int
    building_form: str
    bounds: tuple[int,int,int,int]

    @property
    def door_side(self) -> str:
        if self.entrance is None:return "south"
        x,y=self.entrance;left,top,right,bottom=self.bounds
        return min(((abs(y-top),"north"),(abs(x-right),"east"),(abs(y-bottom),"south"),(abs(x-left),"west")),key=lambda r:r[0])[1]


def shell_from_plan(structure,settlement_id:str,pieces=()) -> BuildingShell | None:
    if not enclosed_shell(structure):return None
    cells=tuple(sorted({(int(x),int(y)) for x,y in structure.footprint},key=lambda p:(p[1],p[0])))
    doors=sorted((p for p in pieces if p.structure_plan_id==structure.uid and p.role=="entrance"),key=lambda p:p.uid)
    entrance=tuple(map(int,structure.entrance)) if structure.entrance is not None else None
    selected=next((p for p in doors if entrance==(int(p.x),int(p.y))),doors[0] if doors else None)
    if entrance is None and selected is not None:entrance=(int(selected.x),int(selected.y))
    xs=[x for x,_ in cells];ys=[y for _,y in cells]
    return BuildingShell(str(structure.uid),str(settlement_id),str(structure.function),str(structure.content_id),
        cells,entrance,selected.uid if selected is not None else "",int(getattr(structure,"orientation",0)),
        str(getattr(structure,"building_form","rectangular")),(min(xs),min(ys),max(xs),max(ys)))


def frontage_candidates(shell:BuildingShell) -> tuple[tuple[int,int],...]:
    if shell.entrance is None:return ()
    x,y=shell.entrance;occupied=set(shell.footprint)
    return tuple((x+dx,y+dy) for dx,dy in ((0,1),(-1,0),(1,0),(0,-1)) if (x+dx,y+dy) not in occupied)
