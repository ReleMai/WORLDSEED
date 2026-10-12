"""Persistent, player-owned log cabin blueprint material depot.
Only simulation commands may change stored materials or construction stages.
"""
from __future__ import annotations
import json
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

    def _clear(self,cell):
        sim=self.sim;pos=WorldPos(*cell)
        tile=sim.world.tile_at(pos).terrain
        if not tile.passable or "water" in tile.tags:return False
        if sim.resources.blocks_movement(pos) or not sim.building.passable(pos,True):return False
        if sim.building.container_at(pos) or pos_key(*cell) in sim.state.crops:return False
        overlay=getattr(sim,"settlement_physicalization",None)
        projected=overlay.cell_at(pos) if overlay else None
        if projected and projected.occupied:return False
        if any((c.x,c.y,c.z)==cell and c.hp>0 for c in sim.state.creatures.values()):return False
        if any((n.x,n.y,n.z)==cell and n.alive for n in sim.state.npcs.values()):return False
        if (sim.player_pos.x,sim.player_pos.y,sim.player_pos.z)==cell:return False
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
        from worldseed.core.coords import split_world
        tile_cache=getattr(getattr(self.sim.world,"cache",None),"peek",None)
        if callable(tile_cache) and any(tile_cache(split_world(WorldPos(*cell))[0]) is None
                                        for cell in (*cells,outside)):
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
        stage=site["stage"];site["stage"]+=1;site["revision"]+=1
        return True,"Log cabin complete." if site["stage"]==4 else STAGES[stage]+" constructed."

    def cancel(self,uid,inv):
        site=self._reachable(uid)
        if not site or site["stage"]==4:return False,"Only your unfinished blueprint may be cancelled."
        for iid,n in site["stored"].items():inv.add(iid,n)
        del self.sites[uid]
        return True,"Blueprint removed; all deposited goods refunded."
