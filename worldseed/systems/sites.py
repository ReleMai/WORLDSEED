from __future__ import annotations
from dataclasses import dataclass
from worldseed.core.coords import ChunkKey
from worldseed.core.rng import PCG32, derive_seed, hash_u64
from worldseed.systems.names import culture_name, place_name

@dataclass(frozen=True,slots=True)
class SiteInfo:
    uid:str;name:str;builder:str;age_years:int;danger:int;site_type:str

class SiteGenerator:
    def __init__(self,seed:bytes):self.seed=seed
    def has_site(self,key:ChunkKey)->bool:return key.z<0 and hash_u64(self.seed,"site-presence",key.x,key.y,key.z)%29==0
    def info(self,key:ChunkKey)->SiteInfo|None:
        if not self.has_site(key):return None
        rng=PCG32(derive_seed(self.seed,"site-info",key.x,key.y,key.z));return SiteInfo(f"site:{key.x}:{key.y}:{key.z}",f"{place_name(rng)} {rng.choice(['Crypt','Hold','Temple','Vault','Citadel','Archive'])}",culture_name(rng),80+rng.randbelow(900),20+rng.randbelow(81),rng.choice(['fortress','temple','crypt','archive','mine']))
    def layout(self,key:ChunkKey)->tuple[list[tuple[int,int,int,int]],list[tuple[int,int]]]:
        if not self.has_site(key):return [],[]
        rng=PCG32(derive_seed(self.seed,"site-layout",key.x,key.y,key.z));rooms=[]
        for _ in range(4+rng.randbelow(4)):
            w=4+rng.randbelow(7);h=3+rng.randbelow(6);x=2+rng.randbelow(max(1,30-w));y=2+rng.randbelow(max(1,30-h));rooms.append((x,y,w,h))
        return rooms,[(x+w//2,y+h//2) for x,y,w,h in rooms]
    def runtime_features(self,key:ChunkKey)->dict:
        rooms,centers=self.layout(key)
        if not centers:return {"traps":[],"locks":[],"loot":[],"occupants":[]}
        rng=PCG32(derive_seed(self.seed,"site-runtime",key.x,key.y,key.z));traps=[];locks=[];loot=[];occupants=[]
        # First room is deliberately safer; deeper rooms become mechanically dangerous.
        for i,(x,y,w,h) in enumerate(rooms):
            if i>0 and w>3 and h>3 and rng.randbelow(100)<65:
                tx=x+1+rng.randbelow(max(1,w-2));ty=y+1+rng.randbelow(max(1,h-2));traps.append((tx,ty))
        if len(centers)>=3:locks.append(centers[-2])
        loot.append(centers[0]);loot.append(centers[-1])
        occupants.extend(centers[1:-1] or centers[:1])
        return {"traps":traps,"locks":locks,"loot":loot,"occupants":occupants}
    def overlay(self,key:ChunkKey,chunk,registry)->None:
        if not self.has_site(key):return
        rooms,centers=self.layout(key)
        for x,y,w,h in rooms:
            for yy in range(y,y+h):
                for xx in range(x,x+w):
                    edge=xx in (x,x+w-1) or yy in (y,y+h-1);chunk.set(xx,yy,registry.terrain_index('core:ruin_wall' if edge else 'core:ruin_floor'))
        for (x1,y1),(x2,y2) in zip(centers,centers[1:]):
            for x in range(min(x1,x2),max(x1,x2)+1):chunk.set(x,y1,registry.terrain_index('core:ruin_floor'))
            for y in range(min(y1,y2),max(y1,y2)+1):chunk.set(x2,y,registry.terrain_index('core:ruin_floor'))
        if centers:
            cx,cy=centers[-1];chunk.set(cx,cy,registry.terrain_index('core:relic_cache'))
