from __future__ import annotations
from collections import deque
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory
from worldseed.systems.state import LivingWorldState, StructureInstance, RoofState, ContainerState, GroundPile, pos_key

class BuildingSystem:
    def __init__(self,state:LivingWorldState,registry:ContentRegistry):self.state=state;self.registry=registry
    def structure_at(self,pos:WorldPos)->StructureInstance|None:return self.state.structures.get(pos_key(pos.x,pos.y,pos.z))
    def roof_at(self,pos:WorldPos)->RoofState|None:return self.state.roofs.get(pos_key(pos.x,pos.y,pos.z))
    def container_at(self,pos:WorldPos)->ContainerState|None:return self.state.containers.get(pos_key(pos.x,pos.y,pos.z))
    def nearby_container(self,pos:WorldPos,radius:int=1)->ContainerState|None:
        rows=[c for c in self.state.containers.values() if c.z==pos.z and abs(c.x-pos.x)+abs(c.y-pos.y)<=radius]
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
        s=self.structure_at(pos)
        if s is None:return world_passable
        sd=self.registry.structures[s.structure_id]
        if "bridge" in sd.tags:return sd.passable
        return world_passable and sd.passable
    def blocks_sight(self,pos:WorldPos)->bool:
        s=self.structure_at(pos);return False if s is None else self.registry.structures[s.structure_id].blocks_sight
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
            self.state.containers[key]=ContainerState(f"container:{key}",pos.x,pos.y,pos.z,owner,sdef.capacity_mass_g,sdef.capacity_volume_ml,{})
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
        for iid,n in sdef.cost.items():inv.add(iid,max(0,n//2))
        self.state.structures.pop(key,None);return True,f"You dismantle {sdef.name} and salvage part of it."
    def nearby_station_ids(self,pos:WorldPos,radius:int=2)->set[str]:
        out=set()
        for s in self.state.structures.values():
            if s.z==pos.z and abs(s.x-pos.x)<=radius and abs(s.y-pos.y)<=radius and "station" in self.registry.structures[s.structure_id].tags:out.add(s.structure_id)
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
