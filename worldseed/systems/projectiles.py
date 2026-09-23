from __future__ import annotations

from dataclasses import dataclass
from worldseed.core.coords import WorldPos
from worldseed.core.rng import hash_u64


@dataclass(frozen=True, slots=True)
class ProjectilePath:
    cells: tuple[WorldPos, ...]
    blocked_at: WorldPos | None = None
    intercepted_at: WorldPos | None = None
    cover_penalty: int = 0
    cover_notes: tuple[str, ...] = ()

    @property
    def stopped_at(self) -> WorldPos | None:
        return self.blocked_at or self.intercepted_at


class ProjectileSystem:
    """Deterministic local projectile geometry.

    This system is intentionally read-mostly: it traces through already
    materialized local terrain/resources/structures and never realizes world
    content. Simulation code owns ammo consumption and ground-pile mutation.
    """

    def __init__(self,state,registry,seed:bytes,world,resources,building):
        self.state=state;self.registry=registry;self.seed=seed;self.world=world
        self.resources=resources;self.building=building

    @staticmethod
    def line(origin:WorldPos,target:WorldPos)->tuple[WorldPos,...]:
        if origin.z!=target.z:return ()
        x0,y0=origin.x,origin.y;x1,y1=target.x,target.y
        dx=abs(x1-x0);sx=1 if x0<x1 else -1
        dy=-abs(y1-y0);sy=1 if y0<y1 else -1
        err=dx+dy;out=[]
        while True:
            out.append(WorldPos(x0,y0,origin.z))
            if x0==x1 and y0==y1:break
            e2=2*err
            if e2>=dy:err+=dy;x0+=sx
            if e2<=dx:err+=dx;y0+=sy
        return tuple(out)

    def cover_at(self,pos:WorldPos)->tuple[int,str,bool]:
        tile=self.world.tile_at(pos)
        if tile.terrain.blocks_sight:return 100,tile.terrain.name,True
        structure=self.building.structure_at(pos)
        if structure:
            sdef=self.registry.structures.get(structure.structure_id)
            if sdef and sdef.blocks_sight:return 100,sdef.name,True
            if sdef and not sdef.passable:return 65,sdef.name,False
        fv=self.resources.feature_at(pos)
        if fv:
            fdef=self.registry.resources.get(fv.feature_id)
            if fdef:
                tags=set(fdef.tags)
                if "boulder" in tags:return 82,fdef.name,False
                if fdef.blocks_sight or "tree" in tags:return 68,fdef.name,False
                if {"shrub","brush","berry","thicket"} & tags:return 34,fdef.name,False
                if {"reed","tall_grass"} & tags:return 22,fdef.name,False
                if fdef.blocks_movement:return 42,fdef.name,False
        key=f"{pos.x},{pos.y},{pos.z}"
        crop=self.state.crops.get(key)
        if crop:return 14,"crop cover",False
        return 0,"",False

    def preview(self,origin:WorldPos,target:WorldPos)->ProjectilePath:
        cells=self.line(origin,target)
        if not cells:return ProjectilePath(())
        penalty=0;notes=[];blocked=None
        for cell in cells[1:-1]:
            cover,label,hard=self.cover_at(cell)
            if hard:
                blocked=cell;notes.append(label);break
            if cover:
                penalty=min(55,penalty+max(2,cover//4))
                if label and label not in notes:notes.append(label)
        return ProjectilePath(cells,blocked_at=blocked,cover_penalty=penalty,cover_notes=tuple(notes[:4]))

    def resolve(self,origin:WorldPos,target:WorldPos,weapon,turn:int,token:str)->ProjectilePath:
        preview=self.preview(origin,target)
        if preview.blocked_at:return preview
        intercepted=None;penalty=0;notes=[]
        for cell in preview.cells[1:-1]:
            cover,label,hard=self.cover_at(cell)
            if hard:
                return ProjectilePath(preview.cells,blocked_at=cell,cover_penalty=min(55,penalty),cover_notes=tuple(notes[:4]))
            if cover:
                penalty=min(55,penalty+max(2,cover//4))
                if label and label not in notes:notes.append(label)
                # Large physical cover can actually catch a projectile. Skill
                # influences shot placement elsewhere; this roll models the
                # physical obstruction that remains after aiming.
                intercept=max(0,min(70,cover//2 - max(0,int(getattr(weapon,"accuracy",0)))))
                if hash_u64(self.seed,"projectile-cover",turn,token,weapon.id,cell.x,cell.y,cell.z)%100 < intercept:
                    intercepted=cell;break
        return ProjectilePath(preview.cells,intercepted_at=intercepted,cover_penalty=penalty,cover_notes=tuple(notes[:4]))

    def miss_landing(self,origin:WorldPos,target:WorldPos,weapon,turn:int,token:str)->WorldPos:
        dx=target.x-origin.x;dy=target.y-origin.y
        sx=0 if dx==0 else (1 if dx>0 else -1);sy=0 if dy==0 else (1 if dy>0 else -1)
        # A miss can fall short/long and drift laterally. The namespace is
        # isolated from hit resolution so adding presentation never changes it.
        h=hash_u64(self.seed,"projectile-miss",turn,token,weapon.id,target.x,target.y,target.z)
        forward=(-1,0,0,1,1,2)[h%6]
        side=(-2,-1,-1,0,1,1,2)[(h//7)%7]
        if abs(dx)>=abs(dy):
            lx,ly=0,side
        else:
            lx,ly=side,0
        dest=WorldPos(target.x+sx*forward+lx,target.y+sy*forward+ly,target.z)
        max_steps=max(1,int(weapon.range)+2)
        if abs(dest.x-origin.x)+abs(dest.y-origin.y)>max_steps:
            # Pull extreme scatter back into a bounded physical flight envelope.
            cx,cy=dest.x,dest.y
            while abs(cx-origin.x)+abs(cy-origin.y)>max_steps:
                if abs(cx-origin.x)>=abs(cy-origin.y):cx-=1 if cx>origin.x else -1
                else:cy-=1 if cy>origin.y else -1
            dest=WorldPos(cx,cy,target.z)
        trace=self.preview(origin,dest)
        return trace.stopped_at or dest
