from __future__ import annotations
from collections import deque
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory
from worldseed.core.rng import hash_u64
from worldseed.systems.state import LivingWorldState, StructureInstance, RoofState, ContainerState, GroundPile, pos_key
from worldseed.systems.workshops import STATION_PIECE_ALIASES
from worldseed.systems.salvage_loot import candidates, select_misc

class BuildingSystem:
    def __init__(self,state:LivingWorldState,registry:ContentRegistry):
        self.state=state;self.registry=registry;self.resources=None;self.seed=b"";self.settlement_overlay=None

    def attach_settlement_physicalization(self,overlay)->None:
        self.settlement_overlay=overlay

    def attach_resources(self,resources,seed:bytes)->None:
        self.resources=resources;self.seed=seed or b""

    def materialize_natural_container_at(self,pos:WorldPos)->ContainerState|None:
        """Convert a deterministic generated container feature into persistent state.

        Merely rendering the world never calls this. Simulation discovery owns
        realization, after which movement/loot/destruction can diverge from the
        original deterministic resource placement and save normally.
        """
        key=pos_key(pos.x,pos.y,pos.z)
        existing=self.state.containers.get(key)
        if existing:return existing
        if pos.z!=0 or self.resources is None:return None
        # Moving or destroying a generated cache cannot re-create its goods at
        # its old coordinate, even after prepared base caches are rebuilt.
        if key in self.state.resource_depletion:return None
        if self.settlement_overlay is not None and self.settlement_overlay.clears_natural_feature(pos):
            return None
        fv=self.resources.feature_at(pos)
        if not fv or fv.stage!="mature":return None
        rdef=self.registry.resources.get(fv.feature_id)
        if not rdef or "natural_container" not in rdef.tags or not rdef.container_structure_id:return None
        sdef=self.registry.structures.get(rdef.container_structure_id)
        if not sdef:return None
        items={}
        for iid,(lo,hi) in sorted(rdef.container_loot.items()):
            if iid not in self.registry.items:continue
            span=max(1,int(hi)-int(lo)+1)
            amount=int(lo)+(hash_u64(self.seed,"natural-container-loot",fv.feature_id,pos.x,pos.y,pos.z,iid)%span)
            if amount>0:items[iid]=amount
        context={"core:hollow_log_cache":"natural_log","core:rotten_stump_cache":"natural_stump",
                 "core:rock_crevice_cache":"natural_rock"}.get(fv.feature_id,"wild_ground")
        world=getattr(self.resources,'world',None)
        habitats={world.tile_at(pos).terrain_id} if world is not None else set(rdef.terrains)
        rows=tuple(row for row in candidates(self.registry,(context,'wild_ground'))
                   if row.get('source')!='wild' or habitats.intersection(row.get('habitats',())))
        for iid,amount in select_misc(self.seed,'salvage-natural-container',
                                     f'{fv.feature_id}:{key}',rows,2).items():
            items[iid]=items.get(iid,0)+amount
        self.state.resource_depletion[key]=self.state.clock_minute
        self.resources.revision+=1
        self.state.structures[key]=StructureInstance(rdef.container_structure_id,pos.x,pos.y,pos.z,"world",100)
        c=ContainerState(
            f"natural:{fv.feature_id}:{pos.x}:{pos.y}:{pos.z}",pos.x,pos.y,pos.z,"world",
            rdef.container_capacity_mass_g or sdef.capacity_mass_g,
            rdef.container_capacity_volume_ml or sdef.capacity_volume_ml,
            items,name=rdef.name,kind="natural",movable=bool(rdef.container_movable),
            source_id=fv.feature_id,salvage=dict(rdef.container_salvage),
        )
        self.state.containers[key]=c
        return c

    def materialize_natural_containers(self,positions)->int:
        made=0
        for pos in positions:
            key=pos_key(pos.x,pos.y,pos.z);existed=key in self.state.containers
            if self.materialize_natural_container_at(pos) and not existed:made+=1
            self.materialize_salvage_ground_at(pos)
        return made

    def materialize_salvage_ground_at(self,pos:WorldPos)->GroundPile|None:
        """Realize sparse loose finds on the authoritative discovery path.

        Named depletion markers retain collection history when an empty pile is
        removed, and old resource-generation versions retain their exact world.
        """
        if pos.z!=0 or self.resources is None or int(getattr(self.resources,'version',0))<5:
            return None
        key=pos_key(pos.x,pos.y,pos.z);marker='salvage-scatter:'+key
        if marker in self.state.resource_depletion:
            return None
        if int(hash_u64(self.seed,'salvage-wild-ground-gate',pos.x,pos.y,pos.z)%1000)>=22:
            return None
        if key in self.state.structures or key in self.state.containers or key in self.state.crops or key in self.state.soils:
            return None
        if self.settlement_overlay is not None and self.settlement_overlay.clears_natural_feature(pos):
            return None
        world=getattr(self.resources,'world',None)
        if world is None:return None
        tile=world.tile_at(pos)
        if not tile.terrain.passable or 'water' in tile.terrain.tags:
            return None
        if self.resources.blocks_movement(pos):return None
        rows=candidates(self.registry,source='wild',terrain_id=tile.terrain_id)
        generator=getattr(world,'generator',None)
        sampler=getattr(generator,'sample_fields',None)
        if callable(sampler):
            fields=sampler(pos)
            season_fn=getattr(self.resources,'_season',None)
            season=season_fn() if callable(season_fn) else None
            suited=[]
            for row in rows:
                feature=self.registry.resources.get('core:salvage_patch_'+row['item_id'].split(':',1)[-1])
                if feature is None or tile.terrain_id not in feature.terrains:continue
                if not (feature.min_temp<=fields.temperature<=feature.max_temp
                        and feature.min_moisture<=fields.moisture<=feature.max_moisture):continue
                if season is not None and feature.seasons and season not in feature.seasons:continue
                suited.append(row)
            rows=tuple(suited)
        wanted=select_misc(self.seed,'salvage-wild-ground-item',key,rows,1)
        if not wanted:return None
        pile=self.state.ground_piles.setdefault(key,GroundPile(pos.x,pos.y,pos.z,{}))
        for iid,amount in wanted.items():pile.items[iid]=pile.items.get(iid,0)+amount
        self.state.resource_depletion[marker]=self.state.clock_minute
        return pile

    def clear_conflicting_generated_natural_containers(self)->int:
        """Remove un-moved generated caches that conflict with settlement plans.

        Natural containers are realized from deterministic resource potential,
        so a settlement plan has higher spatial authority.  Containers that the
        player has moved are preserved: their stable generated UID still names
        the original coordinate and therefore no longer matches their position.
        """
        if self.settlement_overlay is None:
            return 0
        removed=0
        for key,c in list(self.state.containers.items()):
            if c.kind!="natural" or not c.source_id:
                continue
            origin_uid=f"natural:{c.source_id}:{c.x}:{c.y}:{c.z}"
            if c.uid!=origin_uid:
                continue
            pos=WorldPos(int(c.x),int(c.y),int(c.z))
            if not self.settlement_overlay.clears_natural_feature(pos):
                continue
            self.state.containers.pop(key,None)
            self.state.structures.pop(key,None)
            removed+=1
        return removed

    def structure_at(self,pos:WorldPos)->StructureInstance|None:return self.state.structures.get(pos_key(pos.x,pos.y,pos.z))
    def roof_at(self,pos:WorldPos)->RoofState|None:return self.state.roofs.get(pos_key(pos.x,pos.y,pos.z))
    def container_at(self,pos:WorldPos)->ContainerState|None:return self.state.containers.get(pos_key(pos.x,pos.y,pos.z))
    def nearby_container(self,pos:WorldPos,radius:int=1,include_private:bool=False)->ContainerState|None:
        rows=[
            c for c in self.state.containers.values()
            if not c.interior_space_id and c.z==pos.z and abs(c.x-pos.x)+abs(c.y-pos.y)<=radius
            and (include_private or c.kind!="property" or c.owner=="player" or c.access=="public")
        ]
        return min(rows,key=lambda c:(abs(c.x-pos.x)+abs(c.y-pos.y),c.uid),default=None)
    def container_load(self,c:ContainerState)->tuple[int,int]:
        mass=volume=0
        for iid,n in c.items.items():
            item=self.registry.items.get(iid)
            if item:mass+=item.mass_g*n;volume+=item.volume_ml*n
        return mass,volume
    def store(self,c:ContainerState,inv:Inventory,item_id:str,amount:int=1)->tuple[bool,str]:
        if amount<=0 or inv.count(item_id)<amount:return False,"You do not have that quantity."
        item=self.registry.items.get(item_id)
        if not item:return False,"Unknown item."
        mass,volume=self.container_load(c)
        if mass+item.mass_g*amount>c.capacity_mass_g or volume+item.volume_ml*amount>c.capacity_volume_ml:return False,"The container has no room for that."
        inv.remove(item_id,amount);c.items[item_id]=c.items.get(item_id,0)+amount;return True,f"You store {amount} {item.name.lower()}."
    def take(self,c:ContainerState,inv:Inventory,item_id:str,amount:int=1)->tuple[bool,str]:
        have=c.items.get(item_id,0)
        if amount<=0 or have<amount:return False,"The container does not hold that quantity."
        left=have-amount
        if left:c.items[item_id]=left
        else:c.items.pop(item_id,None)
        inv.add(item_id,amount);return True,f"You take {amount} {self.registry.items[item_id].name.lower()}."
    def passable(self,pos:WorldPos,world_passable:bool=True)->bool:
        # A completed or framed player home blocks exterior motion, unlike
        # its unfinished floor-level blueprint which the builder may traverse.
        homestead=getattr(self,"homestead",None)
        site=homestead.at(pos) if homestead is not None else None
        if site is not None and site["stage"]>=2:return False
        shell_blocks=getattr(self.settlement_overlay,"shell_blocks",None)
        if callable(shell_blocks) and shell_blocks(pos):return False
        s=self.structure_at(pos)
        if s is not None:
            sd=self.registry.structures[s.structure_id]
            if "bridge" in sd.tags:return sd.passable
            return world_passable and sd.passable
        container=self.container_at(pos)
        if container is not None and container.kind=="property":
            sd=self.registry.structures.get(container.source_id)
            if sd is not None and not sd.passable:
                return False
        if self.settlement_overlay is not None:
            return self.settlement_overlay.passable(pos,world_passable)
        return world_passable
    def blocks_sight(self,pos:WorldPos)->bool:
        shell_blocks=getattr(self.settlement_overlay,"shell_blocks",None)
        if callable(shell_blocks) and shell_blocks(pos):return True
        s=self.structure_at(pos)
        if s is not None:return self.registry.structures[s.structure_id].blocks_sight
        return bool(self.settlement_overlay and self.settlement_overlay.blocks_sight(pos))
    def place(self,structure_id:str,pos:WorldPos,inv:Inventory,owner:str="player")->tuple[bool,str]:
        if structure_id not in self.registry.structures:return False,"Unknown structure."
        key=pos_key(pos.x,pos.y,pos.z);sdef=self.registry.structures[structure_id]
        if "roof" in sdef.tags:
            if key in self.state.roofs:return False,"That tile is already roofed."
            if not inv.consume(sdef.cost):return False,"You lack the construction materials."
            self.state.roofs[key]=RoofState(structure_id,pos.x,pos.y,pos.z,owner,100);return True,f"You build {sdef.name}."
        if key in self.state.structures:return False,"That tile is already occupied by a structure."
        if not inv.consume(sdef.cost):return False,"You lack the construction materials."
        self.state.structures[key]=StructureInstance(structure_id,pos.x,pos.y,pos.z,owner,100)
        if "container" in sdef.tags:
            self.state.containers[key]=ContainerState(
                f"container:{key}",pos.x,pos.y,pos.z,owner,sdef.capacity_mass_g,sdef.capacity_volume_ml,{},
                name=sdef.name,kind="built",movable=("movable" in sdef.tags),source_id=structure_id,
            )
        return True,f"You build {sdef.name}."
    def dismantle(self,pos:WorldPos,inv:Inventory)->tuple[bool,str]:
        key=pos_key(pos.x,pos.y,pos.z);roof=self.state.roofs.get(key)
        if roof:
            rdef=self.registry.structures[roof.structure_id]
            for iid,n in rdef.cost.items():inv.add(iid,max(0,n//2))
            self.state.roofs.pop(key,None);return True,f"You dismantle {rdef.name} and salvage part of it."
        s=self.state.structures.get(key)
        if not s:return False,"There is no structure here."
        sdef=self.registry.structures[s.structure_id]
        c=self.state.containers.pop(key,None)
        if c and c.items:
            pile=self.state.ground_piles.setdefault(key,GroundPile(pos.x,pos.y,pos.z,{}))
            for iid,n in c.items.items():pile.items[iid]=pile.items.get(iid,0)+n
        portable_container=("container" in sdef.tags and "movable" in sdef.tags)
        for iid,n in sdef.cost.items():inv.add(iid,n if portable_container else max(0,n//2))
        self.state.structures.pop(key,None)
        if portable_container:return True,f"You pack up {sdef.name} for reuse."
        return True,f"You dismantle {sdef.name} and salvage part of it."
    def move_container(self,c:ContainerState,dest:WorldPos)->tuple[bool,str]:
        if not c.movable:return False,"That container is fixed in place."
        old_key=pos_key(c.x,c.y,c.z);new_key=pos_key(dest.x,dest.y,dest.z)
        if new_key==old_key:return False,"The container is already there."
        if new_key in self.state.structures or new_key in self.state.containers:return False,"That space is already occupied."
        structure=self.state.structures.pop(old_key,None)
        self.state.containers.pop(old_key,None)
        c.x,c.y,c.z=dest.x,dest.y,dest.z
        self.state.containers[new_key]=c
        if structure:
            structure.x,structure.y,structure.z=dest.x,dest.y,dest.z
            self.state.structures[new_key]=structure
        return True,f"You move {c.name.lower() if c.name else 'the container'}."

    def destroy_container(self,c:ContainerState)->tuple[bool,str]:
        if c.kind!="natural":return False,"Built storage should be dismantled with the construction tools."
        key=pos_key(c.x,c.y,c.z)
        pile=self.state.ground_piles.setdefault(key,GroundPile(c.x,c.y,c.z,{}))
        for iid,n in c.items.items():
            if n>0:pile.items[iid]=pile.items.get(iid,0)+n
        salvage_parts=[]
        for iid,(lo,hi) in sorted(c.salvage.items()):
            if iid not in self.registry.items:continue
            span=max(1,int(hi)-int(lo)+1)
            amount=int(lo)+(hash_u64(self.seed,"natural-container-salvage",c.uid,iid)%span)
            if amount>0:
                pile.items[iid]=pile.items.get(iid,0)+amount
                salvage_parts.append(f"{amount} {self.registry.items[iid].name.lower()}")
        self.state.containers.pop(key,None);self.state.structures.pop(key,None)
        extra=(" Salvage: "+", ".join(salvage_parts)+".") if salvage_parts else ""
        return True,f"You break apart {c.name.lower() if c.name else 'the container'}; its contents spill onto the ground."+extra

    def nearby_station_ids(self,pos:WorldPos,radius:int=2)->set[str]:
        """Stations available to the player from built and generated civilization."""
        out=set()
        for s in self.state.structures.values():
            if s.z==pos.z and abs(s.x-pos.x)<=radius and abs(s.y-pos.y)<=radius:
                definition=self.registry.structures.get(s.structure_id)
                if definition is not None and "station" in definition.tags:
                    out.add(s.structure_id)
        if self.settlement_overlay is not None and pos.z==0:
            cells=self.settlement_overlay.cells_in_bounds(
                int(pos.x)-radius,int(pos.y)-radius,int(pos.x)+radius,int(pos.y)+radius
            )
            for cell in cells:
                if max(abs(int(cell.x)-int(pos.x)),abs(int(cell.y)-int(pos.y)))>radius:
                    continue
                for piece_id in (cell.fixture_piece_id,cell.structure_piece_id):
                    station_id=STATION_PIECE_ALIASES.get(str(piece_id))
                    if station_id and station_id in self.registry.structures:
                        out.add(station_id)
        return out

    def environmental_bonuses(self,pos:WorldPos,radius:int=2)->dict[str,int]:
        out={"warmth":0,"shelter":0,"comfort":0,"work_bonus":0}
        for s in self.state.structures.values():
            if s.z!=pos.z:continue
            dist=abs(s.x-pos.x)+abs(s.y-pos.y)
            if dist>radius:continue
            sd=self.registry.structures.get(s.structure_id)
            if not sd:continue
            fall=max(1,dist+1)
            out["warmth"]+=max(0,sd.warmth//fall)
            out["shelter"]+=max(0,sd.shelter//fall)
            out["comfort"]+=max(0,sd.comfort//fall)
            out["work_bonus"]+=max(0,sd.work_bonus//fall)
        room=self.room_at(pos)
        if room.get("sheltered"):
            out["shelter"]+=20
            out["comfort"]+=5
        return {k:min(100,v) for k,v in out.items()}

    def best_rest_structure(self,pos:WorldPos,radius:int=2):
        rows=[]
        for s in self.state.structures.values():
            if s.z!=pos.z or abs(s.x-pos.x)+abs(s.y-pos.y)>radius:continue
            sd=self.registry.structures.get(s.structure_id)
            if sd and (sd.comfort>0 or "bed" in sd.tags or "rest" in sd.uses):rows.append((sd.comfort,s,sd))
        return max(rows,key=lambda r:(r[0],r[2].name),default=(0,None,None))

    def stability_report(self,pos:WorldPos,radius:int=8)->dict:
        supports=0;walls=0;flammable=0;damaged=0
        for s in self.state.structures.values():
            if s.z!=pos.z or abs(s.x-pos.x)>radius or abs(s.y-pos.y)>radius:continue
            sd=self.registry.structures[s.structure_id]
            if "support" in sd.tags:supports+=1
            if "wall" in sd.tags:walls+=1
            if "flammable" in sd.tags:flammable+=1
            if s.condition<60:damaged+=1
        roofs=[r for r in self.state.roofs.values() if r.z==pos.z and abs(r.x-pos.x)<=radius and abs(r.y-pos.y)<=radius]
        unsupported=0
        for r in roofs:
            req=self.registry.structures[r.structure_id].load;support=self._support_for(r.x,r.y,r.z)
            if support<req:unsupported+=1
        score=max(0,min(100,40+supports*12+walls*3-damaged*15-unsupported*8))
        return {"supports":supports,"walls":walls,"roofs":len(roofs),"unsupported_roofs":unsupported,"flammable_elements":flammable,"damaged_elements":damaged,"stability":score}

    def room_at(self,pos:WorldPos,max_cells:int=600)->dict:
        if self.settlement_overlay is not None:
            planned=self.settlement_overlay.room_at(pos)
            if planned is not None:return planned
        # flood fill through passable non-wall tiles; if search escapes bounding box, not enclosed
        start=(pos.x,pos.y);q=deque([start]);seen={start};escaped=False;doors=0;beds=0;stations=[]
        limit=12
        while q and len(seen)<=max_cells:
            x,y=q.popleft()
            if abs(x-pos.x)>limit or abs(y-pos.y)>limit:escaped=True;break
            for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
                nx,ny=x+dx,y+dy;npos=WorldPos(nx,ny,pos.z);s=self.structure_at(npos)
                if s:
                    sd=self.registry.structures[s.structure_id]
                    if "door" in sd.tags:doors+=1
                    if "bed" in sd.tags:beds+=1
                    if "station" in sd.tags:stations.append(sd.name)
                    if not sd.passable:continue
                if (nx,ny) not in seen:seen.add((nx,ny));q.append((nx,ny))
        enclosed=not escaped and len(seen)<=max_cells
        roofed=sum(1 for x,y in seen if pos_key(x,y,pos.z) in self.state.roofs);roof_percent=0 if not seen else roofed*100//len(seen);sheltered=enclosed and roof_percent>=60
        classification="outdoors"
        if enclosed:
            if not sheltered:classification="courtyard"
            elif beds:classification="bedroom"
            elif any("Forge" in x for x in stations):classification="smithy"
            elif stations:classification="workshop"
            else:classification="room"
        return {"enclosed":enclosed,"sheltered":sheltered,"roof_percent":roof_percent,"area":len(seen),"doors":doors,"beds":beds,"stations":sorted(set(stations)),"classification":classification}

    def _support_for(self,x:int,y:int,z:int)->int:
        total=0
        for s in self.state.structures.values():
            if s.z!=z:continue
            dist=abs(s.x-x)+abs(s.y-y)
            if dist>2:continue
            strength=self.registry.structures[s.structure_id].support_strength
            if strength:total+=max(1,strength//(dist+1))
        return total

    def hourly_update(self)->list[WorldPos]:
        collapsed=[]
        for key,r in list(self.state.roofs.items()):
            rdef=self.registry.structures[r.structure_id];required=max(1,rdef.load);support=self._support_for(r.x,r.y,r.z)
            if support<required:r.condition-=max(1,(required-support+7)//8)
            else:r.condition=min(100,r.condition+1)
            if r.condition<=0:
                self.state.roofs.pop(key,None);collapsed.append(WorldPos(r.x,r.y,r.z))
        return collapsed
