from __future__ import annotations
from worldseed.content.registry import ContentRegistry
from worldseed.core.rng import PCG32, derive_seed
from worldseed.entities.components import Inventory, Vitals
from worldseed.systems.state import CreatureState, LivingWorldState, GroundPile, CarcassState, pos_key

class CombatSystem:
    AIM_ZONES = ("center","vitals","head","legs")
    MELEE_MODES = ("standard","quick","power","thrust")

    def __init__(self,state:LivingWorldState,registry:ContentRegistry,seed:bytes,artifact_system=None):
        self.state=state;self.registry=registry;self.seed=seed;self.artifact_system=artifact_system
        self.damage_callback=None

    def _damage_event(self,direction,amount,source,target,kind,part=""):
        callback=self.damage_callback
        if callback is not None and amount>0:
            callback(direction,int(amount),str(source),str(target),str(kind),str(part))

    def readied_weapon(self,inv:Inventory):
        iid=self.state.player_readied_weapon
        item=self.registry.items.get(iid) if iid else None
        if item and item.weapon_damage>0 and inv.count(iid)>0:return item
        return None

    def ready_weapon(self,item_id:str,inv:Inventory)->str:
        item=self.registry.items.get(item_id)
        if not item or item.weapon_damage<=0:return "That item is not a usable weapon."
        if inv.count(item_id)<=0:return "You are not carrying that weapon."
        if item.two_handed and self.state.player_equipment.get("offhand"):
            off=self.registry.items.get(self.state.player_equipment["offhand"]);return f"You need both hands free for the {item.name.lower()}; stow the {off.name.lower() if off else 'off-hand item'} first."
        self.state.player_readied_weapon=item_id
        self.clear_aim()
        hands="two hands" if item.two_handed else "your hands"
        return f"You ready the {item.name.lower()} in {hands}."

    def clear_ready_weapon(self)->str:
        iid=self.state.player_readied_weapon
        self.state.player_readied_weapon=""
        self.clear_aim()
        if iid and iid in self.registry.items:return f"You lower the {self.registry.items[iid].name.lower()}."
        return "You have no weapon readied."

    def clear_aim(self)->None:
        self.state.player_aim_target=""
        self.state.player_aim_zone="center"
        self.state.player_aim_quality=0

    def aim_at(self,creature:CreatureState,zone:str,perception:int,hunting:int,distance:int)->str:
        zone=zone if zone in self.AIM_ZONES else "center"
        weapon=self.registry.items.get(self.state.player_readied_weapon)
        if not weapon or weapon.weapon_damage<=0 or weapon.range<=1:
            self.clear_aim();return "Ready a ranged or throwable weapon first."
        if distance>weapon.range:
            self.clear_aim();return f"The target is beyond the useful range of your {weapon.name.lower()}."
        if self.state.player_aim_target!=creature.uid or self.state.player_aim_zone!=zone:
            self.state.player_aim_quality=0
        self.state.player_aim_target=creature.uid;self.state.player_aim_zone=zone
        motion=18 if creature.behavior in ("flee","herd_flee","wounded_flee","charge","flank","disengage") else 9 if creature.behavior in ("pursue","defend","regroup") else 3 if creature.behavior in ("alert","display") else 0
        zone_difficulty={"center":0,"vitals":10,"head":18,"legs":8}[zone]
        gain=max(6,18+perception*2+hunting*2-motion-zone_difficulty//2)
        self.state.player_aim_quality=min(100,self.state.player_aim_quality+gain)
        label={"center":"center mass","vitals":"vital area","head":"head / neck","legs":"legs"}[zone]
        steadiness="steady" if self.state.player_aim_quality>=70 else "settling" if self.state.player_aim_quality>=40 else "rough"
        return f"You settle the {weapon.name.lower()} on the {creature.species_id.split(':')[-1].replace('_',' ')}'s {label}; your aim is {steadiness}."

    def available_melee_modes(self,weapon)->tuple[str,...]:
        modes=["standard","quick","power"]
        if weapon is not None and (weapon.damage_type=="pierce" or weapon.weapon_class in ("spear","javelin","knife")):
            modes.append("thrust")
        return tuple(modes)

    def melee_mode_profile(self,weapon,mode:str)->dict[str,int|str]:
        if mode not in self.available_melee_modes(weapon):mode="standard"
        table={
            "standard":{"label":"standard","accuracy":0,"damage_pct":100,"penetration":0,"stamina_pct":100},
            "quick":{"label":"quick","accuracy":12,"damage_pct":80,"penetration":-1,"stamina_pct":65},
            "power":{"label":"power","accuracy":-10,"damage_pct":135,"penetration":3,"stamina_pct":145},
            "thrust":{"label":"thrust","accuracy":-4,"damage_pct":110,"penetration":5,"stamina_pct":120},
        }
        return dict(table[mode])

    def melee_stamina_cost(self,weapon,mode:str)->int:
        base=max(2,int(weapon.stamina_cost) if weapon else 4)
        profile=self.melee_mode_profile(weapon,mode)
        return max(1,base*int(profile["stamina_pct"])//100)

    def active_defense_base(self,mode:str,vitals:Vitals,attack_kind:str="melee",raw_damage:int=10)->int:
        agility=int(self.state.player_attributes.get("agility",5))
        athletics=int(self.state.player_skills.get("athletics",0))
        melee=int(self.state.player_skills.get("melee",0))
        fatigue=max(0,40-int(vitals.stamina))//2
        if mode=="dodge":
            shield=self.equipped_shield()
            weight=0 if not shield else max(0,(int(shield.mass_g)-2500)//450)
            chance=16+agility*3+athletics*4-self.leg_injury_penalty()*4-fatigue-weight
            if attack_kind=="ranged":chance-=8
            return max(5,min(88,chance))
        if mode=="parry":
            if attack_kind!="melee":return 0
            weapon=self.registry.items.get(self.state.player_readied_weapon)
            if not weapon or weapon.weapon_damage<=0 or ("ranged" in weapon.tags and not weapon.throwable):return 0
            chance=18+melee*4+agility*2+int(weapon.accuracy)-self.arm_injury_penalty()-max(0,int(raw_damage)-8)*2
            return max(5,min(90,chance))
        return 0

    def active_defend(self,vitals:Vitals,raw_damage:int,part:str,attack_kind:str,damage_type:str,turn:int,
                      source_uid:str="")->tuple[int,str]:
        mode=str(getattr(self.state,"player_defense_mode","") or "")
        if mode not in ("dodge","parry") or raw_damage<=0:return raw_damage,""
        chance=self.active_defense_base(mode,vitals,attack_kind,raw_damage)
        if chance<=0:return raw_damage,""
        rng=PCG32(derive_seed(self.seed,"active-defense",turn,source_uid,mode,part,attack_kind,damage_type,raw_damage))
        roll=rng.randbelow(100)
        if roll>=chance:return raw_damage,f"Your {mode} attempt fails"
        if mode=="dodge":
            return 0,"You evade the attack completely"
        weapon=self.registry.items.get(self.state.player_readied_weapon)
        melee=int(self.state.player_skills.get("melee",0));strength=int(self.state.player_attributes.get("strength",5))
        full=roll<max(5,chance//3)
        reduction=max(1,(weapon.weapon_damage if weapon else 1)+melee//2+max(0,strength-5)//2)
        if full:reduction=max(reduction,raw_damage)
        remaining=max(0,raw_damage-reduction)
        text=f"You parry with the {weapon.name.lower()}, redirecting {raw_damage-remaining} damage"
        return remaining,text

    def equipped_shield(self):
        iid=self.state.player_equipment.get("offhand","")
        item=self.registry.items.get(iid) if iid else None
        return item if item and "shield" in item.tags else None

    def shield_coverage_chance(self,part:str,attack_kind:str,stamina:int=100,source_dx:int=0,source_dy:int=0)->int:
        shield=self.equipped_shield()
        if not shield:return 0
        group=self._player_part_group(part)
        body=max(0,min(100,int(shield.shield_body_coverage.get(group,0))))
        base=int(shield.shield_ranged_coverage if attack_kind=="ranged" else shield.shield_melee_coverage)
        fx=int(getattr(self.state,"player_facing_dx",0));fy=int(getattr(self.state,"player_facing_dy",1))
        if source_dx==0 and source_dy==0:arc=100
        else:
            dot=source_dx*fx+source_dy*fy
            arc=100 if dot>0 else 65 if dot==0 else 15
        skill=int(self.state.player_skills.get("shield",0));agility=int(self.state.player_attributes.get("agility",5))
        defense_mode=str(getattr(self.state,"player_defense_mode","") or "")
        guard=18 if defense_mode=="guard" else 8 if defense_mode=="brace" else 18 if bool(getattr(self.state,"player_guarding",False)) else 0
        fatigue=max(0,40-int(stamina))//2
        weight=max(0,(int(shield.mass_g)-4500)//500)
        chance=(base*body*arc)//10000 + skill*2 + max(0,agility-5)*2 + guard - fatigue - weight
        return max(0,min(95,chance))

    def shield_defend(self,raw_damage:int,part:str,attack_kind:str,damage_type:str,turn:int,stamina:int=100,
                      source_dx:int=0,source_dy:int=0,source_uid:str="")->tuple[int,str,int]:
        shield=self.equipped_shield()
        if not shield or raw_damage<=0:return raw_damage,"",0
        chance=self.shield_coverage_chance(part,attack_kind,stamina,source_dx,source_dy)
        if chance<=0:return raw_damage,"",0
        roll=PCG32(derive_seed(self.seed,"shield-defense",turn,source_uid,part,attack_kind,damage_type,raw_damage,shield.id)).randbelow(100)
        if roll>=chance:return raw_damage,"",0
        skill=int(self.state.player_skills.get("shield",0));strength=int(self.state.player_attributes.get("strength",5))
        defense_mode=str(getattr(self.state,"player_defense_mode","") or "")
        stability=max(0,min(100,int(shield.shield_stability)+(18 if defense_mode=="brace" else 0)))
        full_threshold=chance*(45+stability//2)//100
        full=roll<full_threshold
        flat=max(0,int(shield.shield_block))+skill//2+max(0,strength-5)//2+(3 if defense_mode=="brace" else 0)
        if damage_type in ("pierce","bite") and attack_kind=="melee":flat=max(0,flat-1)
        percent=(48+stability//3) if full else (22+stability//5)
        reduced=min(raw_damage,flat + raw_damage*percent//100)
        remaining=max(0,raw_damage-reduced)
        drain=max(1,int(shield.shield_stamina_cost)+raw_damage//7-(skill//5))
        if bool(getattr(self.state,"player_guarding",False)):drain=max(1,drain-1)
        if defense_mode=="brace":drain=max(1,drain-1)
        if self.artifact_system:
            aid=self.state.player_equipped_artifacts.get("offhand","");artifact=self.state.artifacts.get(aid)
            if artifact:
                wear=max(1,raw_damage//10+(1 if damage_type=="blunt" else 0))
                artifact.condition=max(0,artifact.condition-wear)
                artifact.history.append(f"Shield impact at turn {turn}; condition {artifact.condition}%.")
                if artifact.condition<=0:
                    self.state.player_equipment.pop("offhand",None);self.state.player_equipped_artifacts.pop("offhand",None);artifact.owner="destroyed"
        # Primitive stack items do not yet have per-instance durability; durable
        # shields use the artifact condition path above.
        grade="blocks" if full and remaining==0 else "catches" if full else "deflects"
        return remaining,f"{shield.name} {grade} the {attack_kind} hit (-{reduced} damage, {drain} stamina)",drain

    def resolve_player_hit(self,vitals:Vitals,part:str,raw_damage:int,damage_type:str,attack_kind:str,turn:int,
                           source_name:str="attack",source_uid:str="",source_dx:int=0,source_dy:int=0,
                           bleeding_bonus:int=0,fracture_chance:int=0)->str:
        raw=max(1,int(raw_damage));agility=int(self.state.player_attributes.get("agility",5));athletics=int(self.state.player_skills.get("athletics",0))
        raw,active_text=self.active_defend(vitals,raw,part,attack_kind,damage_type,turn,source_uid)
        if raw<=0:return f"{source_name} misses cleanly; {active_text}."
        evasion=min(20,max(0,agility-5)*2+athletics)
        if attack_kind=="ranged":evasion//=2
        raw=max(1,raw*(100-evasion)//100)
        raw,shield_text,shield_drain=self.shield_defend(raw,part,attack_kind,damage_type,turn,vitals.stamina,source_dx,source_dy,source_uid)
        if shield_drain:vitals.stamina=max(0,vitals.stamina-shield_drain)
        if raw<=0:
            return f"{source_name} is stopped at your shield"+(f"; {shield_text}." if shield_text else ".")
        armor,names=self._player_armor(part);mitigation=min(max(0,raw-1),armor//4);damage=max(1,raw-mitigation)
        penetration=damage+(4 if damage_type in ("bite","pierce") else 3 if damage_type=="cut" else 0)-armor//5
        tissue="skin"
        if penetration>6:tissue="muscle"
        if penetration>12:tissue="bone"
        if penetration>19 and part in ("head","neck","torso"):tissue="organ"
        bleed=max(0,damage//3+int(bleeding_bonus)-armor//8)
        rr=PCG32(derive_seed(self.seed,"player-hit-fracture",turn,source_uid,part,attack_kind,raw_damage,damage_type))
        fracture=(tissue=="bone" and damage>=6) or (fracture_chance>0 and rr.randbelow(100)<int(fracture_chance))
        severity=min(100,damage*7+max(0,penetration)*2)
        old_hp=vitals.hp
        vitals.hp=max(0,vitals.hp-damage);vitals.pain=min(100,vitals.pain+max(1,severity//5));vitals.blood=max(0,vitals.blood-max(0,bleed//2))
        self._damage_event("taken",old_hp-vitals.hp,source_name,"Player",damage_type,part)
        self.state.player_body_parts[part]=max(0,self.state.player_body_parts.get(part,100)-damage*3)
        self.state.player_wounds.append({"part":part,"tissue":tissue,"type":damage_type,"severity":severity,"bleeding":bleed,"fracture":fracture,"turn":turn,"source":source_name,"attack_kind":attack_kind})
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
        details=[]
        if active_text:details.append(active_text)
        if shield_text:details.append(shield_text)
        if mitigation and names:details.append(f"{', '.join(names)} absorbs {mitigation}")
        suffix=("; "+"; ".join(details)) if details else ""
        return f"{source_name} hits your {part.replace('_',' ')}, dealing {damage} {damage_type} damage{suffix}."

    def melee_hit_chance(self,weapon,distance:int,agility:int,melee:int,stamina:int,target_behavior:str="calm",mode:str="standard")->int:
        handling=0 if weapon is None else weapon.accuracy
        profile=self.melee_mode_profile(weapon,mode)
        motion=14 if target_behavior in ("flee","herd_flee","wounded_flee","flank","disengage") else 11 if target_behavior=="charge" else 10 if target_behavior=="staggered" else 7 if target_behavior in ("pursue","regroup") else 4 if target_behavior=="defend" else 0
        fatigue=max(0,35-stamina)//2
        reach_penalty=max(0,distance-1)*8
        return max(18,min(97,70+handling+int(profile["accuracy"])+agility*2+melee*3-motion-fatigue-reach_penalty-self.arm_injury_penalty()//2))

    def ranged_hit_chance(self,weapon,distance:int,perception:int,hunting:int,zone:str="center",aim_quality:int=0,stamina:int=100,target_behavior:str="calm")->int:
        zone=zone if zone in self.AIM_ZONES else "center"
        motion_penalty=22 if target_behavior in ("flee","herd_flee","wounded_flee","flank","disengage") else 16 if target_behavior=="charge" else 11 if target_behavior in ("pursue","defend","regroup") else 6 if target_behavior in ("alert","display") else 0
        range_penalty=max(0,distance-2)*4
        fatigue=max(0,35-stamina)//2
        zone_penalty={"center":0,"vitals":11,"head":24,"legs":10}[zone]
        return max(5,min(97,35+perception*4+hunting*3+weapon.accuracy+aim_quality//3-range_penalty-motion_penalty-zone_penalty-fatigue-self.arm_injury_penalty()//2))

    @staticmethod
    def _anatomy_zone(part:str)->str:
        p=str(part).lower()
        if "head" in p:return "head"
        if "neck" in p:return "neck"
        if "wing" in p:return "wings"
        if "leg" in p or "flipper" in p:return "legs"
        return "torso"

    def _organ_hit(self,sp,part:str,rng:PCG32)->tuple[str,dict]|tuple[None,None]:
        zone=self._anatomy_zone(part)
        rows=[(name,meta) for name,meta in sp.organs.items() if str(meta.get("zone",""))==zone]
        if not rows:return None,None
        total=sum(max(1,int(meta.get("weight",1))) for _,meta in rows);roll=rng.randbelow(total)
        for name,meta in rows:
            weight=max(1,int(meta.get("weight",1)))
            if roll<weight:return name,meta
            roll-=weight
        return rows[-1]

    @staticmethod
    def _apply_organ_trauma(creature:CreatureState,organ:str,meta:dict,damage:int,bleeding:int,penetration:int)->tuple[int,int,int]:
        vitality=max(0,min(100,int(meta.get("vitality",50))));bleed=max(0,min(100,int(meta.get("bleed",50))))
        organ_damage=max(5,min(100,damage*5+max(0,penetration-14)*3))
        damage=max(1,damage + max(1,damage*vitality//180))
        bleeding=max(bleeding,bleeding+max(1,bleed//18))
        if organ in ("heart","brain") and organ_damage>=88:
            creature.hp-=max(4,damage//2)
        elif organ=="trachea" and organ_damage>=75:
            bleeding+=3
        return damage,bleeding,organ_damage

    def attack_creature(self,creature:CreatureState,inv:Inventory,turn:int,distance:int=1,stamina:int=100,mode:str="standard")->str:
        sp=self.registry.species[creature.species_id];weapon=self.readied_weapon(inv)
        if weapon is not None and distance>weapon.reach:return f"The {sp.name.lower()} is beyond the reach of your {weapon.name.lower()}."
        if weapon is None and distance>1:return f"The {sp.name.lower()} is out of reach."
        profile=self.melee_mode_profile(weapon,mode);mode=str(profile["label"])
        base=3 if weapon is None else weapon.weapon_damage;dtype="blunt" if weapon is None else weapon.damage_type
        if weapon is not None and self.artifact_system:base=max(1,base*self.artifact_system.best_quality(weapon.id)//50)
        strength=int(self.state.player_attributes.get('strength',5));agility=int(self.state.player_attributes.get('agility',5));melee=int(self.state.player_skills.get('melee',0))
        base+=max(0,(strength-5)//2)+melee//3
        rng=PCG32(derive_seed(self.seed,"attack",turn,creature.uid,creature.hp,self.state.player_readied_weapon,distance,mode))
        hit=self.melee_hit_chance(weapon,distance,agility,melee,stamina,creature.behavior,mode)
        if rng.randbelow(100)>=hit:
            return f"You miss the {sp.name.lower()}"+(f" with your {weapon.name.lower()}." if weapon else ".")
        parts=list(sp.body.items()) or [("torso",100)];total=sum(max(0,int(w)) for _,w in parts) or 1;r=rng.randbelow(total);part=parts[0][0]
        for p,w in parts:
            w=max(0,int(w))
            if r<w:part=p;break
            r-=w
        variance=80+rng.randbelow(41);base=max(1,base*(100-self.arm_injury_penalty())//100)
        damage=max(1,base*variance//100);damage=max(1,damage*int(profile["damage_pct"])//100);severity=min(100,damage*5)
        penetration=damage+(7 if dtype=="pierce" else 5 if dtype=="cut" else 1)+int(profile["penetration"]);tissue="skin"
        if penetration>8:tissue="muscle"
        if penetration>14:tissue="bone"
        organ=None;organ_damage=0
        zone=self._anatomy_zone(part)
        if penetration>20 and zone in ("head","neck","torso"):tissue="organ"
        bleeding=max(0,damage//2+(4 if dtype in ("cut","pierce") else 0)+(2 if mode=="thrust" and dtype=="pierce" else 0))
        if tissue=="organ":
            organ,meta=self._organ_hit(sp,part,rng)
            if organ and meta:
                damage,bleeding,organ_damage=self._apply_organ_trauma(creature,organ,meta,damage,bleeding,penetration)
                severity=min(100,max(severity,organ_damage))
        fracture=(tissue=="bone" and damage>=9) or (mode=="power" and dtype=="blunt" and damage>=8 and rng.randbelow(100)<35)
        old_hp=creature.hp;creature.hp-=damage
        self._damage_event("dealt",max(0,min(damage,old_hp)),"Player",sp.name,dtype,part)
        creature.blood=max(0,creature.blood-bleeding);creature.pain=min(100,creature.pain+severity//3)
        creature.wounds.append({"part":part,"tissue":tissue,"organ":organ or "","organ_damage":organ_damage,"type":dtype,"severity":severity,"bleeding":bleeding,"fracture":fracture,"turn":turn,"weapon":weapon.id if weapon else "unarmed"})
        if weapon is not None and self.artifact_system:
            worn=self.artifact_system.wear(weapon.id,"player",1+(1 if dtype=="blunt" else 0),turn,"combat use")
            if worn and worn.condition<=0:
                inv.remove(weapon.id,1)
                if inv.count(weapon.id)<=0:self.state.player_readied_weapon=""
        if creature.hp<=0 or creature.blood<=0:
            self._reconcile_population_death(creature);self._make_carcass(creature,sp);self.state.creatures.pop(creature.uid,None)
            return f"Your {mode} attack strikes the {sp.name.lower()}'s {part} for {damage}; it dies, leaving a carcass to process."
        organ_text=f", damaging the {organ.replace('_',' ')}" if organ else ""
        return f"Your {mode} attack strikes the {sp.name.lower()}'s {part}{organ_text} for {damage} {dtype} damage."

    def shield_bash(self,creature:CreatureState,turn:int,stamina:int=100)->str:
        shield=self.equipped_shield()
        sp=self.registry.species[creature.species_id]
        if not shield:return "You need an equipped shield to bash."
        skill=int(self.state.player_skills.get("shield",0));strength=int(self.state.player_attributes.get("strength",5));agility=int(self.state.player_attributes.get("agility",5))
        fatigue=max(0,35-int(stamina))//2;weight=max(0,(int(shield.mass_g)-4500)//800)
        chance=max(25,min(95,48+skill*4+agility*2+int(shield.shield_stability)//8-weight-fatigue))
        rng=PCG32(derive_seed(self.seed,"shield-bash",turn,creature.uid,shield.id,creature.hp))
        if rng.randbelow(100)>=chance:return f"You drive the {shield.name.lower()} forward, but the {sp.name.lower()} slips the bash."
        damage=max(1,int(shield.shield_block)//2+max(0,strength-4)//2+skill//4)
        part="head" if rng.randbelow(100)<20 else "torso"
        old_hp=creature.hp;creature.hp-=damage
        self._damage_event("dealt",max(0,min(damage,old_hp)),"Player",sp.name,"blunt",part)
        severity=min(100,damage*6);creature.pain=min(100,creature.pain+max(3,severity//3))
        creature.wounds.append({"part":part,"tissue":"skin","type":"blunt","severity":severity,"bleeding":0,"fracture":False,"turn":turn,"weapon":shield.id,"mode":"shield_bash"})
        stagger_force=damage+int(shield.shield_stability)//12+skill//2
        staggered=stagger_force>=9 or rng.randbelow(100)<min(70,25+skill*3)
        if staggered:
            creature.staggered_until_turn=max(creature.staggered_until_turn,turn+1);creature.behavior="staggered";creature.stamina=max(0,creature.stamina-20)
        if creature.hp<=0:
            self._reconcile_population_death(creature);self._make_carcass(creature,sp);self.state.creatures.pop(creature.uid,None)
            return f"Your {shield.name.lower()} crushes into the {sp.name.lower()}; it collapses, leaving a carcass."
        return f"You bash the {sp.name.lower()} with the {shield.name.lower()} for {damage} blunt damage"+(" and stagger it." if staggered else ".")

    def ranged_attack_creature(self,creature:CreatureState,inv:Inventory,turn:int,distance:int,perception:int=5,hunting:int=0,weapon_id:str|None=None,aim_zone:str="center",aim_quality:int=0,stamina:int=100,cover_penalty:int=0)->str:
        weapon=self.registry.items.get(weapon_id or self.state.player_readied_weapon)
        if not weapon or weapon.weapon_damage<=0 or weapon.range<=1 or inv.count(weapon.id)<=0:return "You have no usable ranged weapon readied."
        if distance>weapon.range:return f"The target is beyond the useful range of your {weapon.name.lower()}."
        if weapon.ammo_item and inv.count(weapon.ammo_item)<=0:return f"You have no {self.registry.items[weapon.ammo_item].name.lower()}."
        if weapon.ammo_item:inv.remove(weapon.ammo_item,1)

        sp=self.registry.species[creature.species_id];zone=aim_zone if aim_zone in self.AIM_ZONES else "center"
        rng=PCG32(derive_seed(self.seed,"ranged-attack",turn,creature.uid,distance,weapon.id,creature.hp,creature.blood,zone,aim_quality))
        accuracy=max(2,self.ranged_hit_chance(weapon,distance,perception,hunting,zone,aim_quality,stamina,creature.behavior)-max(0,int(cover_penalty)))
        if rng.randbelow(100)>=accuracy:
            verb="throw" if weapon.throwable else "shot"
            return f"Your {weapon.name.lower()} {verb} at the {sp.name.lower()} misses."

        source_parts=list(sp.body.items()) or [("torso",100)]
        if zone=="head":parts=[(p,w) for p,w in source_parts if p in ("head","neck")] or [("head",1)]
        elif zone=="legs":parts=[(p,w) for p,w in source_parts if ("leg" in p or "flipper" in p)] or [("legs",1)]
        elif zone=="vitals":parts=[(p,w) for p,w in source_parts if p in ("torso","head","neck")] or [("torso",1)]
        else:parts=source_parts
        total=sum(max(0,int(weight)) for _,weight in parts) or 1;roll=rng.randbelow(total);part=parts[0][0]
        for name,weight in parts:
            weight=max(0,int(weight))
            if roll<weight:part=name;break
            roll-=weight

        variance=75+rng.randbelow(51);damage=max(1,(weapon.weapon_damage+hunting//3)*variance//100);dtype=weapon.damage_type
        penetration=damage+(9 if dtype=="pierce" else 5 if dtype=="cut" else 1)+(2 if zone in ("vitals","head") else 0)
        tissue="skin"
        if penetration>7:tissue="muscle"
        if penetration>13:tissue="bone"
        organ=None;organ_damage=0
        anatomy_zone=self._anatomy_zone(part)
        if penetration>19 and anatomy_zone in ("head","neck","torso"):tissue="organ"
        bleeding=max(1,damage//3+(4 if dtype=="pierce" else 3 if dtype=="cut" else 0))
        if tissue=="organ":
            organ,meta=self._organ_hit(sp,part,rng)
            if organ and meta:
                damage,bleeding,organ_damage=self._apply_organ_trauma(creature,organ,meta,damage,bleeding,penetration)
        fracture=tissue=="bone" and (damage>=7 or rng.randbelow(100)<25);severity=min(100,damage*6+max(0,penetration-6)*2)
        if organ_damage:severity=max(severity,organ_damage)
        old_hp=creature.hp
        creature.hp-=damage;creature.blood=max(0,creature.blood-bleeding);creature.pain=min(100,creature.pain+max(2,severity//4))
        self._damage_event("dealt",max(0,min(damage,old_hp)),"Player",sp.name,dtype,part)
        creature.wounds.append({"part":part,"tissue":tissue,"organ":organ or "","organ_damage":organ_damage,"type":dtype,"severity":severity,"bleeding":bleeding,"fracture":fracture,"turn":turn,"weapon":weapon.id,"aim_zone":zone,"aim_quality":aim_quality})
        creature.alertness=100
        if creature.hp<=0 or creature.blood<=0:
            self._reconcile_population_death(creature);self._make_carcass(creature,sp);self.state.creatures.pop(creature.uid,None)
            verb="thrown " if weapon.throwable else ""
            return f"Your {verb}{weapon.name.lower()} strikes the {sp.name.lower()}'s {part}; it drops, leaving a carcass."
        condition=" and fractures bone" if fracture else (f" through the {organ.replace('_',' ')}" if organ else f" into {tissue}")
        verb="thrown " if weapon.throwable else ""
        return f"Your {verb}{weapon.name.lower()} hits the {sp.name.lower()}'s {part}{condition} for {damage} {dtype} damage."
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

    def intercept_charge(self,creature:CreatureState,inv:Inventory,turn:int,stamina:int=100)->tuple[bool,bool,str]:
        """Use a prepared reach weapon to meet a committed charge.

        This is only available when the player explicitly chose Parry. It turns
        a reach-2+ piercing weapon into a point-control defense rather than an
        automatic passive bonus.
        """
        if creature.behavior!="charge" or creature.charge_momentum<=0 or self.state.player_defense_mode!="parry":
            return False,False,""
        weapon=self.readied_weapon(inv)
        if not weapon or weapon.reach<2 or weapon.damage_type!="pierce":
            return False,False,""
        before_wounds=len(creature.wounds);before_hp=creature.hp
        msg=self.attack_creature(creature,inv,turn,min(2,weapon.reach),stamina,"thrust")
        alive=creature.uid in self.state.creatures
        hit=(not alive) or len(creature.wounds)>before_wounds or creature.hp<before_hp
        if not hit:
            return True,False,f"You set the {weapon.name.lower()} against the charge, but the animal beats the point. {msg}"
        if alive:
            creature.charge_momentum=0;creature.charge_committed_until_turn=-1
            creature.stamina=max(0,creature.stamina-18)
            creature.staggered_until_turn=max(creature.staggered_until_turn,turn+1)
            creature.behavior="staggered"
        return True,True,f"You meet the charge at reach. {msg}"

    def intercept_approach(self,creature:CreatureState,inv:Inventory,turn:int,stamina:int=100)->tuple[bool,bool,str]:
        """Prepared reach control against an animal closing from outside adjacency."""
        if self.state.player_defense_mode!="parry":
            return False,False,""
        weapon=self.readied_weapon(inv)
        if not weapon or weapon.reach<2 or ("ranged" in weapon.tags and not weapon.throwable):
            return False,False,""
        mode="thrust" if weapon.damage_type=="pierce" else "quick"
        before_wounds=len(creature.wounds);before_hp=creature.hp
        msg=self.attack_creature(creature,inv,turn,min(2,weapon.reach),stamina,mode)
        alive=creature.uid in self.state.creatures
        hit=(not alive) or len(creature.wounds)>before_wounds or creature.hp<before_hp
        if not hit:
            return True,False,f"You try to hold the {weapon.name.lower()} at reach, but the animal gets inside the line. {msg}"
        if alive:
            creature.stamina=max(0,creature.stamina-8)
            creature.alertness=100
        return True,True,f"You stop the approach at weapon reach. {msg}"

    def player_collision_injury(self,vitals:Vitals,turn:int,force:int,source_name:str="impact")->str:
        force=max(1,int(force));damage=max(1,min(14,force//10));severity=min(100,damage*7+force//3)
        fracture_chance=min(65,max(0,force-25))
        rng=PCG32(derive_seed(self.seed,"player-collision",turn,source_name,force,vitals.hp))
        fracture=rng.randbelow(100)<fracture_chance
        part=("torso","left_arm","right_arm","left_leg","right_leg")[rng.randbelow(5)]
        old_hp=vitals.hp
        vitals.hp=max(0,vitals.hp-damage);vitals.pain=min(100,vitals.pain+max(2,severity//4))
        self._damage_event("taken",old_hp-vitals.hp,source_name,"Player","collision",part)
        self.state.player_body_parts[part]=max(0,self.state.player_body_parts.get(part,100)-damage*2)
        self.state.player_wounds.append({"part":part,"tissue":"muscle" if damage>=5 else "skin","type":"blunt","severity":severity,"bleeding":0,"fracture":fracture,"turn":turn,"source":source_name,"attack_kind":"collision"})
        if len(self.state.player_wounds)>80:self.state.player_wounds=self.state.player_wounds[-80:]
        return f"You slam into solid terrain for {damage} blunt damage"+(" and suffer a fracture." if fracture else ".")

    def creature_collision_injury(self,creature:CreatureState,turn:int,force:int,source_name:str="impact")->str:
        sp=self.registry.species[creature.species_id];force=max(1,int(force));damage=max(1,min(16,force//9))
        severity=min(100,damage*6+force//3);fracture=force>=35
        old_hp=creature.hp
        creature.hp-=damage;creature.pain=min(100,creature.pain+max(2,severity//3))
        self._damage_event("dealt",max(0,min(damage,old_hp)),source_name,sp.name,"collision","torso")
        creature.wounds.append({"part":"torso","tissue":"muscle" if damage>=5 else "skin","type":"blunt","severity":severity,"bleeding":0,"fracture":fracture,"turn":turn,"weapon":source_name,"mode":"collision"})
        if creature.hp<=0:
            self._reconcile_population_death(creature);self._make_carcass(creature,sp);self.state.creatures.pop(creature.uid,None)
            return f"The {sp.name.lower()} crashes into solid terrain and dies."
        creature.staggered_until_turn=max(creature.staggered_until_turn,turn+1);creature.behavior="staggered"
        return f"The {sp.name.lower()} crashes into solid terrain for {damage} blunt damage."

    def creature_attack_player(self,creature:CreatureState,vitals:Vitals,turn:int,source_dx:int=0,source_dy:int=0)->str:
        sp=self.registry.species[creature.species_id];rng=PCG32(derive_seed(self.seed,"creature-attack",turn,creature.uid,creature.hp,creature.behavior,creature.charge_momentum))
        attacks=list(sp.attacks) or [{"name":"attack","damage":sp.damage,"type":"bite" if sp.diet in ("carnivore","omnivore") else "blunt","bleeding":1,"fracture":0}]
        if creature.behavior=="charge":
            preferred=[a for a in attacks if any(k in str(a.get("name","")).lower() for k in ("charge","rush","trampling","goring"))]
            if preferred:attacks=preferred
        elif creature.behavior=="flank" and sp.combat_style=="pack_predator":
            preferred=[a for a in attacks if any(k in str(a.get("name","")).lower() for k in ("hamstring","raking","bite"))]
            if preferred:attacks=preferred
        attack=attacks[rng.randbelow(len(attacks))];attack_name=str(attack.get("name","attack"));base_damage=max(1,int(attack.get("damage",sp.damage)));dtype=str(attack.get("type","blunt"))

        if creature.behavior=="flank" and sp.pack_coordination>0:
            parts=(("head",5),("neck",4),("torso",28),("left_arm",8),("right_arm",8),("left_leg",24),("right_leg",23))
        else:
            parts=(("head",10),("neck",4),("torso",38),("left_arm",11),("right_arm",11),("left_leg",13),("right_leg",13))
        roll=rng.randbelow(100);part="torso"
        for p,w in parts:
            if roll<w:part=p;break
            roll-=w

        raw=max(1,base_damage*(80+rng.randbelow(41))//100)
        fracture=int(attack.get("fracture",0))
        charging=creature.behavior=="charge"
        momentum=max(0,int(creature.charge_momentum))
        if charging:
            bonus=min(75,int(sp.charge_power)//3+momentum*10)
            raw=max(1,raw*(100+bonus)//100)
            fracture=min(90,fracture+int(sp.charge_power)//4+momentum*6)
        mode_before=str(getattr(self.state,"player_defense_mode","") or "")
        msg=self.resolve_player_hit(vitals,part,raw,dtype,"melee",turn,f"{sp.name} uses {attack_name}",creature.uid,source_dx,source_dy,int(attack.get("bleeding",0)),fracture)

        if charging:
            creature.charge_committed_until_turn=-1;creature.charge_momentum=0
            creature.stamina=max(0,creature.stamina-(18+momentum*3))
            lower=msg.lower()
            if "evade" in lower:
                creature.staggered_until_turn=max(creature.staggered_until_turn,turn+1);creature.behavior="recover"
            elif mode_before=="brace" and "shield" in lower:
                creature.pain=min(100,creature.pain+6+momentum*2)
                creature.stamina=max(0,creature.stamina-18)
                creature.staggered_until_turn=max(creature.staggered_until_turn,turn+1);creature.behavior="staggered"
            else:
                creature.behavior="defend" if sp.defensive_aggression>=55 else "pursue"
        return msg

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
            old_hp=vitals.hp
            vitals.blood=max(0,vitals.blood-total_bleed);vitals.hp=max(0,vitals.hp-max(0,total_bleed//2));vitals.pain=min(100,vitals.pain+max(1,total_bleed//2))
            self._damage_event("taken",old_hp-vitals.hp,"Bleeding wounds","Player","bleeding")

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
        uid=self.state.uid("carcass");embedded={};organ_damage={}
        for row in c.embedded_projectiles:
            iid=str(row.get("item_id",""))
            if iid:embedded[iid]=embedded.get(iid,0)+1
        for wound in c.wounds:
            organ=str(wound.get("organ",""))
            if organ:organ_damage[organ]=max(organ_damage.get(organ,0),int(wound.get("organ_damage",wound.get("severity",0))))
        self.state.carcasses[uid]=CarcassState(uid,c.species_id,c.x,c.y,c.z,self.state.clock_minute,quality,source_uid=c.uid,embedded_items=embedded,organ_damage=organ_damage)

    def _drop(self,c:CreatureState,drops:dict[str,int])->None:
        key=pos_key(c.x,c.y,c.z);pile=self.state.ground_piles.get(key)
        if pile is None:pile=GroundPile(c.x,c.y,c.z,{});self.state.ground_piles[key]=pile
        for iid,n in drops.items():pile.items[iid]=pile.items.get(iid,0)+n
