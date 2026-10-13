"""Persistent, player-owned log cabin blueprint material depot.
Only simulation commands may change stored materials or construction stages.
"""
from __future__ import annotations
import json
from collections import deque
from functools import lru_cache
from worldseed.config import DATA_DIR
from worldseed.core.coords import WorldPos
from worldseed.systems.state import pos_key

STAGES = ("Foundation", "Frame", "Roof", "Finishing")
MILESTONES = (0, 20, 60, 90, 100)

# Each roofing item supplies one unit of thatch. Keep its original identity in
# the saved depot so refunds and inventory history are not silently converted.
THATCH_MATERIALS = (
    "core:reed_bundle", "core:pine_bough", "core:juniper_bough",
    "core:beachgrass", "core:saltmarsh_grass", "core:eelgrass",
    "core:rush_pith_bundle", "core:brush",
)

def material_sources(required_item_id):
    return THATCH_MATERIALS if required_item_id=="core:reed_bundle" else (required_item_id,)

def carried_material(inv,required_item_id):
    return sum(inv.count(iid) for iid in material_sources(required_item_id))

@lru_cache(maxsize=1)
def catalog():
    raw = json.loads((DATA_DIR / "homestead_catalog_v1.json").read_text(encoding="utf-8"))
    if raw.get("version") != 1: raise ValueError("Unknown homestead catalog")
    return ({r["id"]: r for r in raw["home_types"]}, {r["id"]: r for r in raw["styles"]})

def rotate(x, y, w, h, turns):
    for _ in range(turns % 4):
        x, y, w, h = h-1-y, x, h, w
    return x,y

def footprint(site):
    home = catalog()[0][site["home_id"]]
    return tuple((site["x"] + rotate(x,y,home["width"],home["depth"],site["orientation"])[0],
                  site["y"] + rotate(x,y,home["width"],home["depth"],site["orientation"])[1],site["z"])
                 for y in range(home["depth"]) for x in range(home["width"]))

def doorway(site):
    home, style = catalog()[0][site["home_id"]],catalog()[1][site["style_id"]]
    dx={"left":0,"center":home["width"]//2,"right":home["width"]-1}[style["door_position"]]
    a,b=rotate(dx,home["depth"]-1,home["width"],home["depth"],site["orientation"])
    inside=(site["x"]+a,site["y"]+b,site["z"])
    ox,oy=((0,1),(-1,0),(0,-1),(1,0))[site["orientation"]]
    return inside,(inside[0]+ox,inside[1]+oy,inside[2])

def door_uid(site):
    return str(site['uid'])+':entrance'

def progress(site):
    materials=catalog()[0][site["home_id"]]["materials"]
    # Count substitute items toward the roof without losing refund identities.
    return {iid: (min(n,sum(site["stored"].get(source,0)
                        for source in material_sources(iid))),n)
            for iid,n in materials.items()}

class HomesteadBlueprintService:
    def __init__(self,sim):
        self.sim=sim
        self.sites=sim.state.homesteads

    def at(self,pos):
        key=(pos.x,pos.y,pos.z)
        return next((site for site in self.sites.values() if key in footprint(site)),None)

    def completed(self,uid):
        site=self.sites.get(str(uid))
        return site if site and int(site['stage'])==4 else None

    def _outdoor_actors(self):
        """Indoor actors' saved exterior anchors are not occupied ground."""
        indoor=getattr(self.sim.state,'interior_actors',{})
        if 'player' not in indoor:
            yield 'player',self.sim.player_pos
        for uid,npc in self.sim.state.npcs.items():
            if npc.alive and uid not in indoor:
                yield uid,WorldPos(npc.x,npc.y,npc.z)
        for uid,creature in self.sim.state.creatures.items():
            if creature.hp>0:
                yield 'creature:'+uid,WorldPos(creature.x,creature.y,creature.z)

    def _prepared(self,pos):
        """Resource collision may also read the four neighboring ground cells."""
        from worldseed.core.coords import split_world
        cache=getattr(self.sim.world,'cache',None)
        peek=getattr(cache,'peek',None)
        if not callable(peek):return True
        queries=(pos,*(pos.moved(dx,dy) for dx,dy in ((0,-1),(-1,0),(1,0),(0,1))))
        return all(peek(split_world(q)[0]) is not None for q in queries)

    def _ground_open(self,pos,actor_uid='player'):
        """Read prepared collision authority without generating nearby land."""
        if not self._prepared(pos):return False
        terrain=self.sim.world.tile_at(pos).terrain
        if not terrain.passable or 'water' in terrain.tags:return False
        if not self.sim.building.passable(pos,True):return False
        overlay=getattr(self.sim,'settlement_physicalization',None)
        clears=getattr(overlay,'clears_natural_feature',None)
        if self.sim.resources.blocks_movement(pos) and not (callable(clears) and clears(pos)):
            return False
        environment=getattr(self.sim,'environment',None)
        if environment is not None and not environment.fluid_passable(pos):return False
        security=getattr(self.sim,'property_security',None)
        if security is not None and security.blocks_actor(pos,actor_uid):return False
        return True

    def recovery_landing(self,site,origin):
        """Repair an invalid legacy outdoor anchor using only the local apron."""
        cells=set(footprint(site));outside=WorldPos(*doorway(site)[1])
        x0=min(x for x,y,z in cells)-2;x1=max(x for x,y,z in cells)+2
        y0=min(y for x,y,z in cells)-2;y1=max(y for x,y,z in cells)+2
        occupied={(p.x,p.y,p.z):uid for uid,p in self._outdoor_actors() if uid!='player'}
        apron=[WorldPos(x,y,site['z']) for y in range(y0,y1+1) for x in range(x0,x1+1)
               if (x,y,site['z']) not in cells]
        apron.sort(key=lambda p:(abs(p.x-origin.x)+abs(p.y-origin.y),p.y,p.x))
        for pos in dict.fromkeys([outside,*apron]):
            if self._apron_escape(cells,pos,'player',occupied):return pos
        return None

    def _apron_escape(self,cells,start,actor_uid,occupied):
        """Shared bounded reachability for construction and legacy recovery."""
        x0=min(x for x,y,z in cells)-2;x1=max(x for x,y,z in cells)+2
        y0=min(y for x,y,z in cells)-2;y1=max(y for x,y,z in cells)+2
        queue=deque([start]);seen={start}
        while queue:
            pos=queue.popleft()
            if ((pos.x,pos.y,pos.z) in cells or not self._ground_open(pos,actor_uid)
                    or occupied.get((pos.x,pos.y,pos.z),actor_uid)!=actor_uid):continue
            if pos.x in (x0,x1) or pos.y in (y0,y1):return True
            for dx,dy in ((0,-1),(-1,0),(1,0),(0,1)):
                nxt=pos.moved(dx,dy)
                if x0<=nxt.x<=x1 and y0<=nxt.y<=y1 and nxt not in seen:
                    seen.add(nxt);queue.append(nxt)
        return False

    def construction_safety(self,site,next_stage):
        """Validate the proposed shell before committing any stage/depot change."""
        if next_stage<2:return True,''
        cells=set(footprint(site));outside=WorldPos(*doorway(site)[1])
        actors=list(self._outdoor_actors())
        if any((p.x,p.y,p.z) in cells for _,p in actors):
            return False,'Move all people and animals outside the cabin footprint before building.'
        if not self._ground_open(outside):
            return False,'Clear and prepare the cabin doorway landing before building.'
        if any(uid!='player' and p==outside for uid,p in actors):
            return False,'Wait for the cabin doorway landing to be unoccupied before building.'
        x0=min(x for x,y,z in cells)-2;x1=max(x for x,y,z in cells)+2
        y0=min(y for x,y,z in cells)-2;y1=max(y for x,y,z in cells)+2
        occupied={(p.x,p.y,p.z):uid for uid,p in actors}

        if not self._apron_escape(cells,outside,'player',occupied):
            return False,'The cabin doorway needs a clear route to surrounding ground.'
        for uid,pos in actors:
            nearby=pos.z==site['z'] and x0<pos.x<x1 and y0<pos.y<y1
            if (nearby or uid=='player') and not self._apron_escape(cells,pos,uid,occupied):
                return False,'This stage would block an occupant or their route away from the cabin.'
        return True,''

    def _clear(self,cell):
        sim=self.sim;pos=WorldPos(*cell)
        if not self._prepared(pos):return False
        tile=sim.world.tile_at(pos).terrain
        if not tile.passable or "water" in tile.tags:return False
        if sim.resources.blocks_movement(pos) or not sim.building.passable(pos,True):return False
        if sim.building.container_at(pos) or pos_key(*cell) in sim.state.crops:return False
        overlay=getattr(sim,"settlement_physicalization",None)
        projected=overlay.cell_at(pos) if overlay else None
        if projected and projected.occupied:return False
        if any((p.x,p.y,p.z)==cell for _,p in self._outdoor_actors()):return False
        return True

    def preview(self,style_id,x,y,orientation=0):
        """Read-only placement check. Both cursor preview and command use this."""
        style=catalog()[1].get(style_id)
        if not style or style["home_id"]!="log_cabin" or orientation not in range(4):
            return False,"Unknown log cabin style or rotation.",None
        p=self.sim.player_pos
        site={"uid":"","home_id":"log_cabin","style_id":style_id,"x":int(x),"y":int(y),"z":0,
              "orientation":int(orientation),"owner_uid":"player","stage":0,"stored":{},"revision":0}
        cells=footprint(site);inside,outside=doorway(site)
        if p.z!=0 or abs(p.x-x)+abs(p.y-y)>8:
            return False,"Too far away: choose ground within 8 tiles.",site
        # Mouse preview must not reveal unexplored construction sites.
        known=getattr(self.sim,"discovered_tiles_set",None)
        if known is not None and any(pos_key(*cell) not in known for cell in (*cells,outside)):
            return False,"Explore the complete footprint and doorway first.",site
        # Validate only prepared tiles. A cursor preview may not realize world
        # chunks, generate terrain, or mutate persistent world state.
        tile_cache=getattr(getattr(self.sim.world,"cache",None),"peek",None)
        if callable(tile_cache) and any(not self._prepared(WorldPos(*cell)) for cell in (*cells,outside)):
            return False,"Move closer so this area loads before building.",site
        if any(not self._clear(cell) for cell in (*cells,outside)):
            return False,"Clear terrain, trees, objects and the doorway first.",site
        occupied=set(cells)
        for other in self.sites.values():
            other_cells=set(footprint(other))
            other_exit=doorway(other)[1]
            if occupied & other_cells or outside in other_cells or other_exit in occupied:
                return False,"Overlaps an existing home or blocks its doorway.",site
        return True,"Clear site. Left-click to place the blueprint.",site

    def place(self,style_id,x,y,orientation=0):
        ok,msg,site=self.preview(style_id,x,y,orientation)
        if not ok:return False,msg
        # Placement is free; no inventory or save state is changed on hover.
        site["uid"]=self.sim.state.uid("homestead")
        self.sites[site["uid"]]=site
        return True,"Blueprint placed. Right-click its marker to deposit materials."

    def _reachable(self,uid):
        site=self.sites.get(uid)
        if not site or site.get("owner_uid")!="player":return None
        p=self.sim.player_pos
        if p.z!=site["z"] or min(abs(p.x-x)+abs(p.y-y) for x,y,z in footprint(site))>2:return None
        return site

    def deposit(self,uid,item_id,count,inv):
        site=self._reachable(uid)
        if not site or site["stage"]==4:return False,"Move within reach of your unfinished marker."
        required=catalog()[0][site["home_id"]]["materials"]
        target=("core:reed_bundle" if item_id in THATCH_MATERIALS and "core:reed_bundle" in required
                else item_id)
        if target not in required or count<1:return False,"Not a required material."
        supplied,needed=progress(site)[target]
        n=min(int(count),inv.count(item_id),needed-supplied)
        if n<1:return False,"Nothing more of that item can be deposited."
        if not inv.remove(item_id,n):return False,"Those materials are no longer carried."
        site["stored"][item_id]=site["stored"].get(item_id,0)+n
        site["revision"]+=1
        return True,f"Deposited {n} {item_id.split(':')[-1].replace('_',' ')}."

    def advance(self,uid):
        site=self._reachable(uid)
        if not site:return False,"Move closer to the blueprint."
        if site["stage"]==4:return False,"The log cabin is complete."
        materials=catalog()[0][site["home_id"]]["materials"]
        threshold=MILESTONES[site["stage"]+1]
        ledger=progress(site)
        missing=[name for name,n in materials.items()
                 if ledger[name][0]<n*threshold//100]
        if missing:return False,"Still needed for this stage: "+", ".join(missing)
        safe,reason=self.construction_safety(site,site['stage']+1)
        if not safe:return False,reason
        stage=site["stage"];site["stage"]+=1;site["revision"]+=1
        if site['stage']==4 and hasattr(self.sim.state,'door_security'):
            from worldseed.systems.homestead_access import ensure_access
            ensure_access(self.sim,site)
        return True,"Log cabin complete." if site["stage"]==4 else STAGES[stage]+" constructed."

    def cancel(self,uid,inv):
        site=self._reachable(uid)
        if not site or site["stage"]==4:return False,"Only your unfinished blueprint may be cancelled."
        for iid,n in site["stored"].items():inv.add(iid,n)
        del self.sites[uid]
        return True,"Blueprint removed; all deposited goods refunded."
