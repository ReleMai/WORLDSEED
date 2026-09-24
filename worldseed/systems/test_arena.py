from __future__ import annotations

from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory, Vitals
from worldseed.systems.state import CreatureState


class TestArenaSystem:
    """Explicit developer combat laboratory.

    Arena creatures are notable local test entities with no ecology cohort key,
    so killing them never changes wildlife population authority. The arena does
    not alter terrain or realize distant world state.
    """

    STAT_LIMITS={
        "attribute":(1,20),
        "skill":(0,20),
    }

    def __init__(self,state,registry,world,resources,building):
        self.state=state;self.registry=registry;self.world=world;self.resources=resources;self.building=building

    def _free(self,pos:WorldPos)->bool:
        if not self.world.is_passable(pos):return False
        if self.resources.blocks_movement(pos):return False
        if not self.building.passable(pos,True):return False
        return not any(c.hp>0 and (c.x,c.y,c.z)==(pos.x,pos.y,pos.z) for c in self.state.creatures.values())

    def _spawn_pos(self,origin:WorldPos,dx:int,dy:int)->WorldPos|None:
        desired=origin.moved(dx,dy)
        if self._free(desired):return desired
        # Stay local and deterministic: try a small ring around the requested
        # orientation instead of mutating terrain to manufacture an arena.
        for radius in (1,2,3):
            offsets=[]
            for oy in range(-radius,radius+1):
                for ox in range(-radius,radius+1):
                    if abs(ox)+abs(oy)!=radius:continue
                    offsets.append((ox,oy))
            offsets.sort(key=lambda q:(abs(q[1]),abs(q[0]),q[1],q[0]))
            for ox,oy in offsets:
                p=desired.moved(ox,oy)
                if self._free(p):return p
        return None

    def spawn_item(self,inv:Inventory,item_id:str,amount:int=1)->str:
        item=self.registry.items.get(item_id);amount=max(1,min(100,int(amount)))
        if not item:return "Unknown arena item."
        inv.add(item_id,amount)
        return f"Arena supplies: {amount} {item.name.lower()}."

    def spawn_creature(self,origin:WorldPos,species_id:str,dx:int,dy:int)->str:
        sp=self.registry.species.get(species_id)
        if not sp:return "Unknown arena animal."
        if dx==0 and dy==0:return "Choose a position away from the player."
        if abs(dx)+abs(dy)>14:return "Arena spawns are limited to the local practice area."
        pos=self._spawn_pos(origin,dx,dy)
        if pos is None:return "No clear practice position is available near that orientation."
        uid=self.state.uid("arena")
        self.state.creatures[uid]=CreatureState(
            uid,species_id,pos.x,pos.y,pos.z,sp.max_hp,
            notable=True,name=f"Arena {sp.name}",stamina=sp.stamina,cohort_key=""
        )
        return f"Arena spawn: {sp.name} at offset {pos.x-origin.x:+d},{pos.y-origin.y:+d}."

    def set_stat(self,stat_type:str,key:str,value:int)->str:
        table=self.state.player_attributes if stat_type=="attribute" else self.state.player_skills if stat_type=="skill" else None
        if table is None or key not in table:return "Unknown arena stat."
        lo,hi=self.STAT_LIMITS[stat_type];value=max(lo,min(hi,int(value)));table[key]=value
        return f"Arena {stat_type}: {key.replace('_',' ')} = {value}."

    def heal(self,vitals:Vitals)->None:
        vitals.hp=vitals.max_hp;vitals.stamina=100;vitals.blood=100;vitals.pain=0
        self.state.player_wounds.clear()
        for part in list(self.state.player_body_parts):self.state.player_body_parts[part]=100

    def injury(self,vitals:Vitals,preset:str)->str:
        if preset=="heal":
            self.heal(vitals);return "Arena reset: injuries healed and vitals restored."
        specs={
            "light_cut":("torso","skin","cut",28,2,False),
            "bleeding_torso":("torso","muscle","cut",62,8,False),
            "arm_fracture":("left_arm","bone","blunt",68,1,True),
            "leg_fracture":("left_leg","bone","blunt",72,2,True),
        }
        if preset=="exhausted":
            vitals.stamina=8;return "Arena injury drill: stamina reduced to severe exhaustion."
        row=specs.get(preset)
        if not row:return "Unknown injury drill."
        part,tissue,dtype,severity,bleeding,fracture=row
        self.state.player_wounds.append({"part":part,"tissue":tissue,"type":dtype,"severity":severity,"bleeding":bleeding,"fracture":fracture,"turn":0,"source":"arena"})
        self.state.player_body_parts[part]=max(10,100-severity)
        vitals.pain=min(100,vitals.pain+severity//3);vitals.blood=max(0,vitals.blood-bleeding)
        return f"Arena injury drill applied: {preset.replace('_',' ')}."

    def clear(self,vitals:Vitals|None=None,heal:bool=True)->str:
        arena_ids={uid for uid in self.state.creatures if uid.startswith("arena:")}
        for uid in arena_ids:self.state.creatures.pop(uid,None)
        for uid,sign in list(self.state.animal_signs.items()):
            if sign.source_uid in arena_ids:self.state.animal_signs.pop(uid,None)
        for uid,carcass in list(self.state.carcasses.items()):
            if carcass.source_uid in arena_ids:self.state.carcasses.pop(uid,None)
        if heal and vitals:self.heal(vitals)
        return f"Arena cleared ({len(arena_ids)} live test animals removed)"+(" and player restored." if heal else ".")

    def preset(self,name:str,origin:WorldPos,inv:Inventory,vitals:Vitals)->str:
        self.clear(vitals,True)
        spawned=[]
        def item(iid,n=1):
            if iid in self.registry.items:inv.add(iid,n)
        def animal(sid,dx,dy):
            msg=self.spawn_creature(origin,sid,dx,dy);spawned.append(msg)
        if name=="close":
            for iid in ("core:stone_knife","core:club","core:wooden_spear","core:rawhide_buckler","core:wood_round_shield"):item(iid)
            animal("core:boar",2,0);animal("core:wolf",0,-3);animal("core:deer",-2,0);animal("core:rabbit",0,2)
            return "Close-combat ring loaded: four orientations, light/heavy melee, reach weapon, and shields."
        if name=="ranged":
            item("core:short_bow");item("core:wood_arrow",30);item("core:sling");item("core:sling_stone",30);item("core:wooden_spear",4)
            animal("core:rabbit",4,0);animal("core:deer",7,0);animal("core:boar",9,0);animal("core:wolf",6,-3)
            return "Ranged lane loaded: targets at multiple ranges and a moving flank threat."
        if name=="injury":
            for iid in ("core:bandage","core:splint"):item(iid,8)
            for iid in ("core:rawhide_buckler","core:wicker_shield","core:wood_round_shield","core:hide_kite_shield","core:iron_heater_shield","core:steel_tower_shield"):item(iid)
            self.injury(vitals,"arm_fracture");self.injury(vitals,"bleeding_torso")
            animal("core:wolf",2,0)
            return "Injury lab loaded: arm fracture, bleeding wound, treatment supplies, shield set, and close threat."
        if name=="shield":
            for iid in ("core:rawhide_buckler","core:wicker_shield","core:wood_round_shield","core:hide_kite_shield","core:iron_heater_shield","core:steel_tower_shield"):item(iid)
            item("core:club");animal("core:boar",2,0);animal("core:wolf",-2,0)
            return "Shield gauntlet loaded: all six shield profiles plus threats from opposite orientations."
        if name=="tactics":
            for iid in ("core:wooden_spear","core:club","core:wood_round_shield","core:steel_tower_shield"):item(iid)
            animal("core:boar",5,0)
            animal("core:moose",0,-5)
            animal("core:wolf",-5,-1);animal("core:wolf",-5,1);animal("core:wolf",-6,0)
            animal("core:deer",6,3);animal("core:deer",7,3);animal("core:deer",6,4)
            return "Tactical AI field loaded: committed chargers, a three-wolf pack, and a deer herd for panic/cohesion drills."
        return "Unknown arena preset."
