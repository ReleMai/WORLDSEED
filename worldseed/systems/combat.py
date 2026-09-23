from __future__ import annotations
from worldseed.content.registry import ContentRegistry
from worldseed.core.rng import PCG32, derive_seed
from worldseed.entities.components import Inventory, Vitals
from worldseed.systems.state import CreatureState, LivingWorldState, GroundPile, CarcassState, pos_key

class CombatSystem:
    def __init__(self,state:LivingWorldState,registry:ContentRegistry,seed:bytes,artifact_system=None):self.state=state;self.registry=registry;self.seed=seed;self.artifact_system=artifact_system
    def best_weapon(self,inv:Inventory):
        choices=[self.registry.items[i] for i,n in inv.items.items() if n>0 and i in self.registry.items and self.registry.items[i].weapon_damage>0]
        return max(choices,key=lambda x:x.weapon_damage,default=None)
    def attack_creature(self,creature:CreatureState,inv:Inventory,turn:int)->str:
        sp=self.registry.species[creature.species_id];weapon=self.best_weapon(inv);base=3 if weapon is None else weapon.weapon_damage;dtype="blunt" if weapon is None else weapon.damage_type
        if weapon is not None and self.artifact_system: base=max(1,base*self.artifact_system.best_quality(weapon.id)//50)
        strength=int(self.state.player_attributes.get('strength',5));melee=int(self.state.player_skills.get('melee',0));base+=max(0,(strength-5)//2)+melee//3
        rng=PCG32(derive_seed(self.seed,"attack",turn,creature.uid,creature.hp));parts=list(sp.body.items());total=sum(w for _,w in parts);r=rng.randbelow(max(1,total));part=parts[0][0]
        for p,w in parts:
            if r<w:part=p;break
            r-=w
        variance=80+rng.randbelow(41);base=max(1,base*(100-self.arm_injury_penalty())//100);damage=max(1,base*variance//100);creature.hp-=damage;severity=min(100,damage*5)
        penetration=damage + (6 if dtype=="pierce" else 4 if dtype=="cut" else 0)
        tissue="skin"
        if penetration>8:tissue="muscle"
        if penetration>14:tissue="bone"
        if penetration>20:tissue="organ"
        bleeding=max(0,(damage//2) + (4 if dtype in ("cut","pierce") else 0))
        fracture=(tissue=="bone" and damage>=10)
        creature.blood=max(0,creature.blood-bleeding);creature.pain=min(100,creature.pain+severity//3)
        creature.wounds.append({"part":part,"tissue":tissue,"type":dtype,"severity":severity,"bleeding":bleeding,"fracture":fracture,"turn":turn})
        if weapon is not None and self.artifact_system:
            worn=self.artifact_system.wear(weapon.id,"player",1+(1 if dtype=="blunt" else 0),turn,"combat use")
            if worn and worn.condition<=0:inv.remove(weapon.id,1)
        if creature.hp<=0 or creature.blood<=0:
            self._reconcile_population_death(creature);self._make_carcass(creature,sp);self.state.creatures.pop(creature.uid,None)
            return f"You strike the {sp.name.lower()}'s {part} for {damage}; it dies, leaving a carcass to process."
        return f"You strike the {sp.name.lower()}'s {part} for {damage} {dtype} damage."
    def ranged_attack_creature(self,creature:CreatureState,inv:Inventory,turn:int,distance:int,perception:int=5,hunting:int=0)->str:
        all_weapons=[self.registry.items[i] for i,n in inv.items.items() if n>0 and i in self.registry.items and self.registry.items[i].range>1 and self.registry.items[i].weapon_damage>0]
        if not all_weapons:return "You have no ranged weapon ready."
        in_range=[w for w in all_weapons if distance<=w.range]
        if not in_range:
            best=max(all_weapons,key=lambda x:(x.range,x.weapon_damage))
            return f"The target is beyond the useful range of your {best.name.lower()}."
        loaded=[w for w in in_range if not w.ammo_item or inv.count(w.ammo_item)>0]
        if not loaded:
            needed=next((w.ammo_item for w in in_range if w.ammo_item),None)
            return f"You have no {self.registry.items[needed].name.lower()}." if needed and needed in self.registry.items else "You have no usable ammunition."
        weapon=max(loaded,key=lambda x:(x.weapon_damage,x.range))
        if weapon.ammo_item:inv.remove(weapon.ammo_item,1)

        sp=self.registry.species[creature.species_id]
        rng=PCG32(derive_seed(self.seed,"ranged-attack",turn,creature.uid,distance,weapon.id,creature.hp,creature.blood))
        motion_penalty=18 if creature.behavior in ("flee","wounded_flee") else 10 if creature.behavior=="pursue" else 6 if creature.behavior=="alert" else 0
        range_penalty=max(0,distance-2)*4
        accuracy=max(8,min(95,38+perception*4+hunting*4-range_penalty-motion_penalty))
        if rng.randbelow(100)>=accuracy:
            return f"Your {weapon.name.lower()} shot at the {sp.name.lower()} misses."

        parts=list(sp.body.items()) or [("torso",100)]
        total=sum(max(0,int(weight)) for _,weight in parts) or 1
        roll=rng.randbelow(total);part=parts[0][0]
        for name,weight in parts:
            weight=max(0,int(weight))
            if roll<weight:
                part=name;break
            roll-=weight

        variance=75+rng.randbelow(51)
        damage=max(1,(weapon.weapon_damage+hunting//3)*variance//100)
        dtype=weapon.damage_type
        penetration=damage+(8 if dtype=="pierce" else 5 if dtype=="cut" else 1)
        tissue="skin"
        if penetration>7:tissue="muscle"
        if penetration>13:tissue="bone"
        if penetration>19 and part in ("head","neck","torso"):tissue="organ"
        if tissue=="organ":
            damage=max(damage,damage*5//4)

        bleeding=max(1,damage//3+(4 if dtype=="pierce" else 3 if dtype=="cut" else 0))
        if tissue=="organ":bleeding+=max(2,damage//3)
        fracture=tissue=="bone" and (damage>=7 or rng.randbelow(100)<25)
        severity=min(100,damage*6+max(0,penetration-6)*2)
        creature.hp-=damage
        creature.blood=max(0,creature.blood-bleeding)
        creature.pain=min(100,creature.pain+max(2,severity//4))
        creature.wounds.append({"part":part,"tissue":tissue,"type":dtype,"severity":severity,"bleeding":bleeding,"fracture":fracture,"turn":turn,"weapon":weapon.id})
        creature.alertness=100
        if creature.hp<=0 or creature.blood<=0:
            self._reconcile_population_death(creature);self._make_carcass(creature,sp);self.state.creatures.pop(creature.uid,None)
            return f"Your {weapon.name.lower()} strikes the {sp.name.lower()}'s {part}; it drops, leaving a carcass."
        condition=" and fractures bone" if fracture else f" into {tissue}"
        return f"Your {weapon.name.lower()} hits the {sp.name.lower()}'s {part}{condition} for {damage} {dtype} damage."

    @staticmethod
    def _player_part_group(part:str)->str:
        if part in ("head","neck"):return "head"
        if "arm" in part:return "arms"
        if "leg" in part:return "legs"
        return "torso"

    def _player_armor(self,part:str)->tuple[int,list[str]]:
        group=self._player_part_group(part);rating=0;names=[]
        for slot,iid in self.state.player_equipment.items():
            item=self.registry.items.get(iid)
            if not item or group not in item.coverage:continue
            artifact=self.state.artifacts.get(self.state.player_equipped_artifacts.get(slot,"")) if self.artifact_system else None
            material_id=(artifact.material if artifact else item.material);mat=self.registry.materials.get(material_id) if material_id else None
            material_bonus=0 if mat is None else (mat.hardness+mat.toughness)//35
            quality_factor=(self.artifact_system.effective_quality(artifact) if artifact and self.artifact_system else 50)
            piece=max(0,(item.armor+material_bonus)*quality_factor//50);rating += piece;names.append(artifact.name if artifact else item.name)
        return min(30,rating),names

    def creature_attack_player(self,creature:CreatureState,vitals:Vitals,turn:int)->str:
        sp=self.registry.species[creature.species_id];rng=PCG32(derive_seed(self.seed,"creature-attack",turn,creature.uid,creature.hp))
        attacks=list(sp.attacks) or [{"name":"attack","damage":sp.damage,"type":"bite" if sp.diet in ("carnivore","omnivore") else "blunt","bleeding":1,"fracture":0}]
        attack=attacks[rng.randbelow(len(attacks))];attack_name=str(attack.get("name","attack"));base_damage=max(1,int(attack.get("damage",sp.damage)));dtype=str(attack.get("type","blunt"))
        parts=(("head",10),("neck",4),("torso",38),("left_arm",11),("right_arm",11),("left_leg",13),("right_leg",13));roll=rng.randbelow(100);part="torso"
        for p,w in parts:
            if roll<w:part=p;break
            roll-=w
        raw=max(1,base_damage*(80+rng.randbelow(41))//100);armor,names=self._player_armor(part);agility=int(self.state.player_attributes.get('agility',5));athletics=int(self.state.player_skills.get('athletics',0));evasion=min(20,max(0,agility-5)*2+athletics);raw=max(1,raw*(100-evasion)//100);mitigation=min(max(0,raw-1),armor//4);damage=max(1,raw-mitigation)
        penetration=damage+(4 if dtype in ("bite","pierce") else 3 if dtype=="cut" else 0)-armor//5
        tissue="skin"
        if penetration>6:tissue="muscle"
        if penetration>12:tissue="bone"
        if penetration>19 and part in ("head","neck","torso"):tissue="organ"
        bleeding=max(0,damage//3+int(attack.get("bleeding",0))-armor//8);fracture=(tissue=="bone" and damage>=6) or (int(attack.get("fracture",0))>0 and rng.randbelow(100)<int(attack.get("fracture",0)))
        severity=min(100,damage*7+max(0,penetration)*2);vitals.hp=max(0,vitals.hp-damage);vitals.pain=min(100,vitals.pain+max(1,severity//5));vitals.blood=max(0,vitals.blood-max(0,bleeding//2))
        self.state.player_body_parts[part]=max(0,self.state.player_body_parts.get(part,100)-damage*3)
        self.state.player_wounds.append({"part":part,"tissue":tissue,"type":dtype,"severity":severity,"bleeding":bleeding,"fracture":fracture,"turn":turn,"source":attack_name})
        if self.artifact_system and names:
            group=self._player_part_group(part)
            for slot,iid in list(self.state.player_equipment.items()):
                item=self.registry.items.get(iid)
                if item and group in item.coverage:
                    a=self.state.artifacts.get(self.state.player_equipped_artifacts.get(slot,""))
                    if a:
                        a.condition=max(0,a.condition-max(1,raw//8));a.history.append(f"Armor impact at turn {turn}; condition {a.condition}%.")
                        if a.condition<=0:self.state.player_equipment.pop(slot,None);self.state.player_equipped_artifacts.pop(slot,None);a.owner='destroyed'
        if len(self.state.player_wounds)>80:self.state.player_wounds=self.state.player_wounds[-80:]
        armor_text=f"; {', '.join(names)} absorbs {mitigation}" if mitigation and names else ""
        return f"{sp.name} uses {attack_name} against your {part.replace('_',' ')}, dealing {damage} {dtype} damage{armor_text}."

    def treat_player_wound(self,index:int,item_id:str,inv:Inventory)->str:
        if index<0 or index>=len(self.state.player_wounds):return "That wound no longer exists."
        if inv.count(item_id)<=0:return "You are not carrying that treatment."
        w=self.state.player_wounds[index]
        if item_id=="core:bandage":
            if int(w.get("bleeding",0))<=0:return "That wound is not actively bleeding."
            inv.remove(item_id,1);w["bleeding"]=0;w["bandaged"]=True;w["severity"]=max(0,int(w.get("severity",0))-8);return "You bind the wound and stop the bleeding."
        if item_id=="core:splint":
            if not w.get("fracture"):return "That wound does not need a splint."
            if w.get("splinted"):return "That fracture is already splinted."
            inv.remove(item_id,1);w["splinted"]=True;w["severity"]=max(0,int(w.get("severity",0))-4);return "You brace the fracture with a splint."
        return "That item cannot treat this wound."

    def tick_player_wounds(self,vitals:Vitals)->None:
        total_bleed=0
        for w in self.state.player_wounds:
            bleed=max(0,int(w.get("bleeding",0)));total_bleed+=bleed//4
            if bleed>0 and int(w.get("severity",0))<70:w["bleeding"]=max(0,bleed-1)
        if total_bleed:
            vitals.blood=max(0,vitals.blood-total_bleed);vitals.hp=max(0,vitals.hp-max(0,total_bleed//2));vitals.pain=min(100,vitals.pain+max(1,total_bleed//2))

    def arm_injury_penalty(self)->int:
        penalty=0
        for w in self.state.player_wounds:
            if "arm" in str(w.get("part","")) and (w.get("fracture") or int(w.get("severity",0))>=60):penalty+=15
        return min(50,penalty)

    def leg_injury_penalty(self)->int:
        penalty=0
        for w in self.state.player_wounds:
            if "leg" in str(w.get("part","")) and (w.get("fracture") or int(w.get("severity",0))>=60):penalty+=3
        return min(10,penalty)

    def tick_wounds(self)->list[str]:
        died=[]
        for uid,c in list(self.state.creatures.items()):
            ongoing=sum(max(0,int(w.get("bleeding",0))//4) for w in c.wounds[-8:])
            if ongoing:
                c.blood=max(0,c.blood-ongoing);c.hp=max(0,c.hp-max(0,ongoing//3))
            c.pain=max(0,c.pain-1)
            if c.hp<=0 or c.blood<=0:
                sp=self.registry.species[c.species_id];self._reconcile_population_death(c);self._make_carcass(c,sp);self.state.creatures.pop(uid,None);died.append(uid)
        return died

    def _reconcile_population_death(self,c:CreatureState)->None:
        if c.cohort_key and c.cohort_key in self.state.cohorts:
            cohort=self.state.cohorts[c.cohort_key];cohort.count=max(0,cohort.count-1)

    def _make_carcass(self,c:CreatureState,sp)->None:
        wounds=sum(int(w.get("severity",0)) for w in c.wounds[-12:]);bleed=sum(int(w.get("bleeding",0)) for w in c.wounds[-12:])
        quality=max(20,min(100,100-wounds//12-bleed//5))
        profile=dict(sp.carcass)
        if not profile:
            meat=max(1,sp.mass_kg//25);profile={"core:raw_game_meat":meat,"core:bone":max(1,sp.mass_kg//50)}
        uid=self.state.uid("carcass");self.state.carcasses[uid]=CarcassState(uid,c.species_id,c.x,c.y,c.z,self.state.clock_minute,quality)

    def _drop(self,c:CreatureState,drops:dict[str,int])->None:
        key=pos_key(c.x,c.y,c.z);pile=self.state.ground_piles.get(key)
        if pile is None:pile=GroundPile(c.x,c.y,c.z,{});self.state.ground_piles[key]=pile
        for iid,n in drops.items():pile.items[iid]=pile.items.get(iid,0)+n
