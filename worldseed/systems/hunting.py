from __future__ import annotations

from typing import Any

from worldseed.content.registry import ContentRegistry, SpeciesDef
from worldseed.core.coords import WorldPos
from worldseed.core.rng import hash_u64
from worldseed.systems.state import AnimalHomeState, AnimalSignState, CreatureState, LivingWorldState


CARDINALS = ((1, 0), (-1, 0), (0, 1), (0, -1))


class HuntingSystem:
    """Local animal perception, threat response, pursuit and physical sign.

    Ecology owns population authority. This system only drives materialized
    individuals and writes bounded evidence produced by their actual movement.
    """

    def __init__(
        self,
        state: LivingWorldState,
        registry: ContentRegistry,
        seed: bytes,
        world,
        environment=None,
        resources=None,
        building=None,
    ) -> None:
        self.state = state
        self.registry = registry
        self.seed = seed
        self.world = world
        self.environment = environment
        self.resources = resources
        self.building = building
        self._player_noise: dict[str, Any] | None = None

    def note_player_noise(
        self,
        pos: WorldPos,
        loudness: int,
        turn: int,
        minute: int,
        kind: str = "movement",
    ) -> None:
        loudness = max(0, min(100, int(loudness)))
        if loudness <= 0:
            return
        current = self._player_noise
        if current and current["turn"] == turn and current["loudness"] >= loudness:
            return
        self._player_noise = {
            "x": pos.x,
            "y": pos.y,
            "z": pos.z,
            "loudness": loudness,
            "turn": turn,
            "minute": minute,
            "kind": kind,
        }

    def set_player_stance(self, stance:str) -> str:
        stance=str(stance or "normal").lower()
        if stance not in {"normal","stalk","crouch","aggressive"}:
            return "Unknown hunting stance."
        self.state.player_hunting_stance=stance
        if stance!="aggressive" and hasattr(self.state,"player_casing_property_id"):
            self.state.player_casing_property_id=""
        if hasattr(self.state,"player_stealth_mode"):self.state.player_stealth_mode=stance!="normal"
        if stance=="normal":return "You return to a normal walking posture."
        if stance=="aggressive":return "You adopt Aggressive Stance. Casing, lockpicking, and door bashing are now available."
        if stance=="stalk":return "You begin stalking: slower movement, quieter footfalls, and a lower visible profile."
        return "You crouch low, maximizing concealment at the cost of movement speed."

    def _equipment_noise(self)->int:
        ids=list(self.state.player_equipment.values())
        if self.state.player_readied_weapon:ids.append(self.state.player_readied_weapon)
        total=0
        for iid in ids:
            item=self.registry.items.get(iid)
            if not item:continue
            hard=1 if item.material in ("core:iron","core:steel","core:copper","core:bronze") else 0
            total += min(8,item.mass_g//1800) + hard*4
        return min(28,total)

    def movement_noise(self, pos: WorldPos, minute:int|None=None) -> int:
        tile = self.world.tile_at(pos)
        tid = tile.terrain_id.split(":")[-1]
        tags = set(tile.terrain.tags)
        noise = 26
        if "water" in tags:noise += 16
        if any(k in tid for k in ("rock","gravel","rubble")):noise += 10
        if any(k in tid for k in ("forest","grass","moss","mud")):noise -= 4
        if self.resources and self.resources.is_harvestable(pos):noise += 3
        stance=str(getattr(self.state,"player_hunting_stance","normal"))
        noise_pct=58 if stance=="stalk" else 40 if stance=="crouch" else 100
        skill=max(int(self.state.player_skills.get("hunting",0)),int(self.state.player_skills.get("survival",0)))
        noise_pct=max(25,noise_pct-min(20,skill))
        noise=noise*noise_pct//100 + self._equipment_noise()
        minute=self.state.clock_minute if minute is None else minute
        if self.environment is not None:
            weather=self.environment.weather.at(minute,pos.x,pos.y)
            rain=int(weather.get("rain",0));wind=abs(int(weather.get("wind_dx",0)))+abs(int(weather.get("wind_dy",0)))
            noise-=min(16,rain//7+wind*2)
        return max(4,min(70,noise))

    def player_concealment(self,pos:WorldPos,minute:int)->int:
        stance=str(getattr(self.state,"player_hunting_stance","normal"))
        base=14 if stance=="stalk" else 24 if stance=="crouch" else 0
        skill=max(int(self.state.player_skills.get("hunting",0)),int(self.state.player_skills.get("survival",0)))
        cover=min(30,self._cover_score(pos))
        weather_mask=0
        if self.environment is not None:
            weather=self.environment.weather.at(minute,pos.x,pos.y)
            weather_mask=min(16,int(weather.get("fog",0))//8+int(weather.get("rain",0))//10)
        return max(0,min(65,base+skill*2+cover//2+weather_mask))

    def notify_attack(
        self,
        creature: CreatureState,
        player_pos: WorldPos,
        turn: int,
        minute: int,
        *,
        loudness: int,
        hit: bool,
    ) -> None:
        creature.alertness = 100
        creature.threat_x, creature.threat_y, creature.threat_z = player_pos.x, player_pos.y, player_pos.z
        creature.last_threat_turn = turn
        creature.last_attacked_turn = turn
        sp = self.registry.species.get(creature.species_id)
        if sp and sp.combat_style in ("prey","herd_prey"):
            creature.panic = 100
        if hit and creature.pain >= 35:
            creature.behavior = "wounded_flee"
        elif creature.behavior == "calm":
            creature.behavior = "alert"
        self.note_player_noise(player_pos, loudness, turn, minute, "weapon")
        if sp:
            self._alarm_group(creature, sp, turn, 85 if hit else 60)

    def _update_needs(self,c:CreatureState,sp:SpeciesDef,minute:int)->None:
        previous=int(getattr(c,"last_need_minute",-1))
        if previous<0:
            c.last_need_minute=minute
            return
        delta=max(0,min(180,minute-previous))
        c.last_need_minute=minute
        if delta<=0:return
        c.hunger=min(100,int(c.hunger)+delta//22)
        c.thirst=min(100,int(getattr(c,"thirst",0))+delta//16)
        if previous//60 < minute//60:
            roll=hash_u64(self.seed,"animal-scat",c.uid,minute//60)%100
            if roll<min(18,5+sp.mass_kg//40):
                p=WorldPos(c.x,c.y,c.z)
                self._write_sign(c,"scat",p,p,minute,max(18,min(90,25+sp.mass_kg//5)),"droppings")

    def _home_group_key(self,c:CreatureState)->str:
        return c.cohort_key or c.uid

    def _ensure_home(self,c:CreatureState,sp:SpeciesDef,minute:int)->AnimalHomeState|None:
        if not sp.home_kind or c.uid.startswith("arena:"):return None
        existing=self.state.animal_homes.get(c.home_uid) if c.home_uid else None
        if existing:
            if c.uid not in existing.occupant_uids and len(existing.occupant_uids)<16:existing.occupant_uids.append(c.uid)
            return existing
        group_key=self._home_group_key(c)
        for home in self.state.animal_homes.values():
            if home.species_id==c.species_id and home.group_key==group_key:
                c.home_uid=home.uid
                if c.uid not in home.occupant_uids and len(home.occupant_uids)<16:home.occupant_uids.append(c.uid)
                return home
        origin=WorldPos(c.x,c.y,c.z);radius=max(2,int(sp.home_radius or 6));candidates=[]
        for dy in range(-radius,radius+1):
            for dx in range(-radius,radius+1):
                dist=abs(dx)+abs(dy)
                if dist>radius:continue
                q=origin.moved(dx,dy)
                if not self._passable_for(sp,q):continue
                tile=self.world.tile_at(q);tags=set(tile.terrain.tags)
                if "water" in tags:continue
                cover=self._cover_score(q)
                water_adj=any("water" in set(self.world.tile_at(q.moved(ax,ay)).terrain.tags) for ax,ay in CARDINALS)
                if sp.home_kind in ("lodge","holt") and not water_adj:continue
                score=cover*3-dist*2
                if sp.home_kind in ("den","burrow","sett","form"):score+=cover
                if sp.home_kind=="nest":score+=12 if ("forest" in tile.terrain_id or cover>=15) else 0
                tie=int(hash_u64(self.seed,"animal-home-site",c.species_id,group_key,q.x,q.y,q.z)&0xffff)
                candidates.append((score,tie,q))
        site=max(candidates,key=lambda row:(row[0],row[1]))[2] if candidates else origin
        token=hash_u64(self.seed,"animal-home",c.species_id,group_key,site.x,site.y,site.z)
        uid=f"home:{token:016x}"
        home=AnimalHomeState(uid,c.species_id,site.x,site.y,site.z,sp.home_kind,minute,group_key,[c.uid],{},minute,False)
        self.state.animal_homes[uid]=home;c.home_uid=uid
        self._write_sign(c,"home",site,site,minute,max(45,min(100,45+sp.mass_kg//5)),sp.home_kind)
        if len(self.state.animal_homes)>600:
            live={x.home_uid for x in self.state.creatures.values() if x.home_uid}
            removable=sorted((h for h in self.state.animal_homes.values() if not h.discovered and h.uid not in live),key=lambda h:(h.last_used_minute,h.uid))
            for row in removable[:max(0,len(self.state.animal_homes)-600)]:self.state.animal_homes.pop(row.uid,None)
        return home

    def _water_bank_target(self,c:CreatureState,sp:SpeciesDef,radius:int=8)->WorldPos|None:
        origin=WorldPos(c.x,c.y,c.z);rows=[]
        for dy in range(-radius,radius+1):
            for dx in range(-radius,radius+1):
                dist=abs(dx)+abs(dy)
                if dist>radius:continue
                q=origin.moved(dx,dy)
                if not self._passable_for(sp,q):continue
                if not any("water" in set(self.world.tile_at(q.moved(ax,ay)).terrain.tags) for ax,ay in CARDINALS):continue
                tie=hash_u64(self.seed,"drink-target",c.uid,q.x,q.y,q.z)
                rows.append((dist,tie,q))
        return min(rows,key=lambda row:(row[0],row[1]))[2] if rows else None

    def _forage_target(self,c:CreatureState,sp:SpeciesDef,radius:int=7)->WorldPos|None:
        if sp.diet=="carnivore" or self.resources is None:return None
        origin=WorldPos(c.x,c.y,c.z);rows=[]
        for dy in range(-radius,radius+1):
            for dx in range(-radius,radius+1):
                dist=abs(dx)+abs(dy)
                if dist>radius:continue
                q=origin.moved(dx,dy)
                if not self._passable_for(sp,q):continue
                fv=self.resources.feature_at(q)
                if not fv or getattr(fv,"stage","mature")=="depleted":continue
                rd=self.registry.resources.get(fv.feature_id)
                if not rd or not ({"food","aquatic_plant"}&set(rd.tags)):continue
                tie=hash_u64(self.seed,"forage-target",c.uid,fv.feature_id,q.x,q.y)
                rows.append((dist,tie,q,rd.name))
        if not rows:return None
        row=min(rows,key=lambda x:(x[0],x[1]))
        return row[2]

    @staticmethod
    def _set_activity_target(c:CreatureState,target:WorldPos|None)->None:
        if target is None:
            c.activity_target_x=c.activity_target_y=c.activity_target_z=None
        else:
            c.activity_target_x,c.activity_target_y,c.activity_target_z=target.x,target.y,target.z

    def _activity_target(self,c:CreatureState)->WorldPos|None:
        if c.activity_target_x is None or c.activity_target_y is None or c.activity_target_z is None:return None
        return WorldPos(int(c.activity_target_x),int(c.activity_target_y),int(c.activity_target_z))

    def _write_activity_sign(self,c:CreatureState,kind:str,minute:int,strength:int,detail:str)->None:
        p=WorldPos(c.x,c.y,c.z)
        self._write_sign(c,kind,p,p,minute,strength,detail)

    def _activity_behavior(self,c:CreatureState,sp:SpeciesDef,turn:int,minute:int)->str:
        active={"seeking_water","seeking_food","return_home","retreat_home","drinking","foraging","resting"}
        if c.behavior in active and turn<=c.activity_until_turn:
            target=self._activity_target(c)
            if c.behavior=="seeking_water" and target and (c.x,c.y,c.z)==(target.x,target.y,target.z):
                c.behavior="drinking";c.activity_until_turn=turn+2;c.thirst=max(0,c.thirst-35)
                self._write_activity_sign(c,"drink",minute,60,"water-edge disturbance")
            elif c.behavior=="seeking_food" and target and (c.x,c.y,c.z)==(target.x,target.y,target.z):
                c.behavior="foraging";c.activity_until_turn=turn+2;c.hunger=max(0,c.hunger-30)
                self._write_activity_sign(c,"feeding",minute,58,"browsed or cropped vegetation")
            elif c.behavior in ("return_home","retreat_home") and target and (c.x,c.y,c.z)==(target.x,target.y,target.z):
                c.behavior="resting";c.activity_until_turn=turn+3
                home=self.state.animal_homes.get(c.home_uid)
                if home:
                    home.last_used_minute=minute
                    self._cache_nearby_food(home,sp)
                self._write_activity_sign(c,"bed",minute,55,"flattened bedding")
            elif c.behavior=="drinking":
                c.thirst=max(0,c.thirst-18);c.stamina=min(sp.stamina,c.stamina+2)
            elif c.behavior=="foraging":
                c.hunger=max(0,c.hunger-16);c.stamina=min(sp.stamina,c.stamina+1)
            elif c.behavior=="resting":
                c.stamina=min(sp.stamina,c.stamina+12)
            return c.behavior
        if c.behavior in active:
            c.behavior="calm";self._set_activity_target(c,None)

        bias=dict(sp.activity_bias)
        home=self.state.animal_homes.get(c.home_uid)
        if c.thirst>=35:
            target=self._water_bank_target(c,sp)
            if target:
                self._set_activity_target(c,target);c.activity_until_turn=turn+10
                return "seeking_water"
        if c.hunger>=35 and sp.diet!="carnivore":
            target=self._forage_target(c,sp)
            if target:
                self._set_activity_target(c,target);c.activity_until_turn=turn+10
                return "seeking_food"
        night=(minute%1440)>=1200 or (minute%1440)<330
        if c.stamina<65 or (night and hash_u64(self.seed,"animal-night-rest",c.uid,minute//120)%100<int(bias.get("rest",50))):
            if home:
                target=WorldPos(home.x,home.y,home.z);self._set_activity_target(c,target);c.activity_until_turn=turn+12
                if (c.x,c.y,c.z)==(target.x,target.y,target.z):
                    c.behavior="resting";c.activity_until_turn=turn+3;home.last_used_minute=minute
                    self._write_activity_sign(c,"bed",minute,55,"flattened bedding")
                    return "resting"
                return "return_home"
            c.activity_until_turn=turn+2;self._set_activity_target(c,None);self._write_activity_sign(c,"bed",minute,40,"temporary resting place");return "resting"

        if turn%4==int(hash_u64(self.seed,"animal-activity-phase",c.uid)%4):
            roll=int(hash_u64(self.seed,"animal-activity",c.uid,minute//30)%100)
            drink=int(bias.get("drink",45));forage=int(bias.get("forage",35))
            if roll<drink//5:
                target=self._water_bank_target(c,sp)
                if target:self._set_activity_target(c,target);c.activity_until_turn=turn+8;return "seeking_water"
            if roll<(drink+forage)//5 and sp.diet!="carnivore":
                target=self._forage_target(c,sp)
                if target:self._set_activity_target(c,target);c.activity_until_turn=turn+8;return "seeking_food"
        return "calm"

    def _cache_nearby_food(self,home:AnimalHomeState,sp:SpeciesDef)->None:
        """Move only already-physical food into a cache; never invent den loot."""
        if not sp.home_storage:return
        for key,pile in sorted(self.state.ground_piles.items()):
            if pile.z!=home.z or abs(pile.x-home.x)+abs(pile.y-home.y)>1:continue
            for iid,count in sorted(list(pile.items.items())):
                item=self.registry.items.get(iid)
                if count<=0 or not item or not ({"raw_meat","food"}&set(item.tags)):continue
                # Predators/omnivores cache at most one nearby physical food
                # item per rest event. Authority transfers from pile -> home.
                pile.items[iid]-=1
                if pile.items[iid]<=0:pile.items.pop(iid,None)
                home.stored_items[iid]=home.stored_items.get(iid,0)+1
                return

    def nearby_homes(self,pos:WorldPos,radius:int=10)->list[AnimalHomeState]:
        return sorted([h for h in self.state.animal_homes.values() if h.z==pos.z and abs(h.x-pos.x)+abs(h.y-pos.y)<=radius],key=lambda h:(abs(h.x-pos.x)+abs(h.y-pos.y),h.uid))

    def home_at(self,pos:WorldPos)->AnimalHomeState|None:
        return next((h for h in self.state.animal_homes.values() if (h.x,h.y,h.z)==(pos.x,pos.y,pos.z)),None)

    def describe_home(self,home:AnimalHomeState,hunting_skill:int,survival_skill:int)->str:
        skill=max(int(hunting_skill),int(survival_skill));sp=self.registry.species.get(home.species_id)
        animal=sp.name.lower() if sp and skill>=3 else "animal"
        stored=sum(home.stored_items.values())
        use="active" if home.last_used_minute>=self.state.clock_minute-360 else "old"
        detail=f" with {stored} cached item(s)" if stored and skill>=6 else ""
        return f"{use.title()} {animal} {home.kind}{detail}."

    def update_local_ai(self, player_pos: WorldPos, turn: int, minute: int) -> list[str]:
        self._prune_signs(minute)
        attackers: list[str] = []
        local = [
            c for c in self.state.creatures.values()
            if c.hp > 0 and c.z == player_pos.z
            and abs(c.x-player_pos.x) <= 42 and abs(c.y-player_pos.y) <= 32
        ]
        self._prepare_group_tactics(local, turn)
        for creature in sorted(local, key=lambda c: c.uid):
            if creature.uid not in self.state.creatures:
                continue
            sp = self.registry.species.get(creature.species_id)
            if not sp:
                continue
            self._update_needs(creature,sp,minute)
            if creature.domestic:
                # Domestic animals remain ordinary CreatureState authority but
                # their containing settlement pen owns their local range.
                creature.behavior="calm"
                creature.alertness=max(0,creature.alertness-5)
                continue
            home=self.state.animal_homes.get(creature.home_uid) if creature.home_uid else None
            # Homes are established during ordinary life, not conjured as an
            # escape destination in the middle of a fresh hunt. A threatened
            # or badly wounded animal without an existing refuge must flee
            # first; one with a previously established refuge may retreat to it.
            can_establish_home=(
                home is None and creature.blood>=80 and creature.pain<35
                and turn-creature.last_threat_turn>1 and creature.alertness<45
            )
            if can_establish_home:
                home=self._ensure_home(creature,sp,minute)

            dist = abs(creature.x - player_pos.x) + abs(creature.y - player_pos.y)
            if home and not home.discovered:
                skill=max(int(self.state.player_skills.get("hunting",0)),int(self.state.player_skills.get("survival",0)))
                hdist=abs(home.x-player_pos.x)+abs(home.y-player_pos.y)
                if hdist<=max(2,min(7,2+skill//2)) and self._visible(player_pos,WorldPos(home.x,home.y,home.z)):
                    home.discovered=True
            if turn <= int(getattr(creature,"staggered_until_turn",-1)):
                creature.behavior = "staggered"
                creature.stamina = min(sp.stamina, creature.stamina + 2)
                creature.charge_momentum = 0
                creature.charge_committed_until_turn = -1
                continue

            perceived = self._perception_score(creature, sp, player_pos, turn, minute)
            if perceived > 0:
                creature.alertness = min(100, creature.alertness + perceived)
                creature.threat_x, creature.threat_y, creature.threat_z = player_pos.x, player_pos.y, player_pos.z
                creature.last_threat_turn = turn
                if sp.combat_style in ("prey","herd_prey"):
                    creature.panic = min(100,max(creature.panic,perceived))
                self._alarm_group(creature, sp, turn, max(20, perceived))
            elif turn - creature.last_threat_turn > 2:
                creature.alertness = max(0, creature.alertness - 8)
                creature.panic = max(0,creature.panic-10)
                if creature.alertness == 0 and creature.behavior not in ("wounded_flee",):
                    creature.behavior = "calm"

            tactical = self._choose_behavior(creature, sp, dist, turn, player_pos)
            active_states={"seeking_water","seeking_food","return_home","retreat_home","drinking","foraging","resting"}
            if tactical=="calm" or (creature.behavior in active_states and perceived<=0 and turn-creature.last_threat_turn>1):
                creature.behavior=self._activity_behavior(creature,sp,turn,minute)
            else:
                creature.behavior=tactical
            if creature.behavior == "display":
                creature.stamina = min(sp.stamina,creature.stamina+3)
                continue
            if creature.behavior in ("drinking","foraging","resting"):
                self._activity_behavior(creature,sp,turn,minute)
                continue
            if creature.behavior in ("pursue","defend","charge","flank") and dist <= 1:
                attackers.append(creature.uid)
                continue
            if creature.behavior in ("flee","herd_flee","wounded_flee","pursue","defend","charge","flank","disengage","regroup","seeking_water","seeking_food","return_home","retreat_home"):
                steps = self._movement_steps(creature, sp)
                for _ in range(steps):
                    if creature.uid not in self.state.creatures:
                        break
                    moved = self._move_one(creature, sp, player_pos, turn, minute)
                    if not moved:
                        break
                    dist = abs(creature.x - player_pos.x) + abs(creature.y - player_pos.y)
                    if creature.behavior in ("seeking_water","seeking_food","return_home","retreat_home"):
                        creature.behavior=self._activity_behavior(creature,sp,turn,minute)
                        if creature.behavior in ("drinking","foraging","resting"):
                            break
                    if creature.behavior in ("pursue","defend","charge","flank") and dist <= 1:
                        break
            else:
                creature.stamina = min(sp.stamina, creature.stamina + 5)

            dist = abs(creature.x - player_pos.x) + abs(creature.y - player_pos.y)
            if creature.behavior in ("pursue","defend","charge","flank") and dist <= 1:
                # A deliberate disengage buys one exchange against ordinary
                # closing pressure if the animal had to move to re-enter reach.
                # Committed charges ignore that spacing grace.
                if not (self.state.player_disengage_turn==turn and creature.last_move_turn==turn and creature.behavior!="charge"):
                    attackers.append(creature.uid)
        return list(dict.fromkeys(attackers))

    def _prepare_group_tactics(self, local:list[CreatureState], turn:int) -> None:
        groups:dict[tuple[str,str],list[CreatureState]]={}
        for c in local:
            key=(c.species_id,c.cohort_key or "local")
            groups.setdefault(key,[]).append(c)
        for (species_id,_),members in groups.items():
            sp=self.registry.species.get(species_id)
            if not sp:
                continue
            members.sort(key=lambda c:c.uid)
            if sp.combat_style=="pack_predator" and sp.pack_coordination>0:
                ranked=sorted(members,key=lambda c:(hash_u64(self.seed,"pack-role",species_id,c.uid),c.uid))
                for i,c in enumerate(ranked):
                    c.pack_role="anchor" if i==0 else "flank_left" if i%2 else "flank_right"
            elif sp.combat_style in ("prey","herd_prey") and sp.herd_cohesion>0 and len(members)>1:
                peak=max((max(c.panic,c.alertness if c.last_threat_turn>=turn-1 else 0) for c in members),default=0)
                if peak>0:
                    shared=peak*sp.herd_cohesion//100
                    for c in members:c.panic=max(c.panic,shared)

    def _same_group(self,c:CreatureState,radius:int=12)->list[CreatureState]:
        rows=[]
        for other in self.state.creatures.values():
            if other.hp<=0 or other.z!=c.z or other.species_id!=c.species_id:
                continue
            if c.cohort_key and other.cohort_key!=c.cohort_key:
                continue
            if abs(other.x-c.x)+abs(other.y-c.y)<=radius:rows.append(other)
        return rows

    def _group_centroid(self,c:CreatureState)->tuple[int,int]:
        group=self._same_group(c,14)
        if not group:return c.x,c.y
        return round(sum(o.x for o in group)/len(group)),round(sum(o.y for o in group)/len(group))

    def _charge_possible(self,c:CreatureState,sp:SpeciesDef,player:WorldPos,dist:int)->bool:
        if sp.charge_range<2 or dist<2 or dist>sp.charge_range:return False
        if self._leg_penalty(c)>=2 or c.stamina<30:return False
        if not self._visible(WorldPos(c.x,c.y,c.z),player):return False
        return True

    def _start_charge(self,c:CreatureState,sp:SpeciesDef,turn:int)->str:
        c.charge_committed_until_turn=turn+max(1,1+sp.charge_power//45)
        c.charge_momentum=0
        return "charge"

    def _choose_behavior(self, c: CreatureState, sp: SpeciesDef, dist: int, turn: int, player:WorldPos) -> str:
        severe_leg = self._leg_penalty(c) >= 2
        badly_wounded = c.blood < 65 or c.pain >= 45 or c.hp <= max(1, sp.max_hp // 2)
        threatened = c.alertness >= sp.flee_threshold or turn - c.last_threat_turn <= 1
        critical = c.blood < 30 or c.hp <= max(1,sp.max_hp//4)

        if c.behavior=="charge" and turn<=c.charge_committed_until_turn and not critical and not severe_leg and c.stamina>=12:
            return "charge"

        if badly_wounded:
            c.charge_momentum=0
            if sp.combat_style=="pack_predator" and len(self._same_group(c))>=2:
                return "disengage"
            if sp.defensive_aggression >= 65 and dist <= 2 and c.stamina >= 15 and not severe_leg:
                return "defend"
            home=self.state.animal_homes.get(c.home_uid)
            if home and dist>2:
                self._set_activity_target(c,WorldPos(home.x,home.y,home.z));c.activity_until_turn=max(c.activity_until_turn,turn+16)
                return "retreat_home"
            return "wounded_flee"

        if sp.combat_style=="pack_predator" and threatened:
            group=self._same_group(c)
            if c.stamina<25 or c.pain>=55:
                return "disengage"
            if len(group)>=2 and sp.pack_coordination>=45:
                return "pursue" if c.pack_role=="anchor" else "flank"
            return "pursue" if sp.aggression>=55 else "flee"

        if sp.combat_style in ("charger","territorial_charger","solitary_predator") and threatened:
            if sp.display_range>=2 and 2<=dist<=sp.display_range and turn-c.last_attacked_turn>1 and turn-c.last_display_turn>5:
                c.last_display_turn=turn
                return "display"
            if self._charge_possible(c,sp,player,dist):
                if turn-c.last_attacked_turn<=1 and sp.defensive_aggression>=60:
                    return self._start_charge(c,sp,turn)
                threshold=max(sp.defensive_aggression,sp.charge_power//2)
                roll=hash_u64(self.seed,"charge-decision",c.uid,c.last_threat_turn,turn//2)%100
                if roll<threshold:
                    return self._start_charge(c,sp,turn)
            if sp.defensive_aggression>=55 and dist<=2 and not severe_leg:
                return "defend"
            return "pursue" if sp.aggression>=50 and c.stamina>=25 else "flee"

        if sp.combat_style in ("prey","herd_prey"):
            if threatened or c.panic>=max(20,sp.flee_threshold//2):
                return "herd_flee" if sp.combat_style=="herd_prey" and len(self._same_group(c))>1 else "flee"
            if c.panic>0 and dist>=6 and len(self._same_group(c))>1:
                return "regroup"

        if sp.aggression >= 50 and threatened and dist <= max(5, sp.vision):
            return "pursue"
        if threatened:
            if sp.defensive_aggression >= 55 and dist <= 2 and not severe_leg:
                return "defend"
            return "flee"
        if c.alertness >= max(10, sp.flee_threshold // 2):
            return "alert"
        return "calm"

    def _movement_steps(self, c: CreatureState, sp: SpeciesDef) -> int:
        effective = max(1, sp.speed - self._leg_penalty(c))
        if c.stamina <= 10:
            return 0
        if c.behavior=="charge":
            return max(1,min(3,1+sp.charge_power//45-self._leg_penalty(c)))
        if c.behavior in ("flank","disengage") and effective>=3 and c.stamina>=30:
            return 2
        if effective >= 3 and c.stamina >= 35:
            return 2
        return 1

    @staticmethod
    def _leg_penalty(c: CreatureState) -> int:
        penalty = 0
        for wound in c.wounds[-12:]:
            part=str(wound.get("part",""))
            if "leg" not in part and "flipper" not in part:
                continue
            sev = int(wound.get("severity", 0))
            if wound.get("fracture") or sev >= 70:
                penalty = max(penalty, 2)
            elif sev >= 35:
                penalty = max(penalty, 1)
        return penalty

    def _perception_score(
        self,
        c: CreatureState,
        sp: SpeciesDef,
        player: WorldPos,
        turn: int,
        minute: int,
    ) -> int:
        dist = abs(c.x - player.x) + abs(c.y - player.y)
        score = 0

        distracted=28 if c.behavior=="resting" else 17 if c.behavior in ("drinking","foraging") else 7 if c.behavior in ("seeking_water","seeking_food","return_home") else 0
        conceal=self.player_concealment(player,minute)
        if dist <= sp.vision and self._visible(WorldPos(c.x, c.y, c.z), player):
            dx, dy = player.x - c.x, player.y - c.y
            facing = c.facing_dx * dx + c.facing_dy * dy
            sight = max(8, 44 - dist * 3)
            if facing < 0 and dist > 2:
                sight //= 2
            sight=max(0,sight-conceal-distracted)
            score = max(score, sight)

        noise = self._player_noise
        if noise and noise["z"] == c.z and turn - int(noise["turn"]) <= 1:
            ndist = abs(c.x - int(noise["x"])) + abs(c.y - int(noise["y"]))
            effective=max(4,int(noise["loudness"])-distracted//2)
            radius = max(1, sp.hearing * max(16,effective) // 40)
            if ndist <= radius:
                score = max(score, max(5, 38 + effective // 3 - ndist * 3 - distracted//3))

        scent = self._scent_score(c, sp, player, minute)
        score = max(score, scent)
        if dist <= 2:
            score = max(score, max(18,35-conceal//3-distracted//3))
        return max(0, min(100, score))

    def _scent_score(self, c: CreatureState, sp: SpeciesDef, player: WorldPos, minute: int) -> int:
        if sp.scent <= 0:
            return 0
        dx, dy = c.x - player.x, c.y - player.y
        dist = abs(dx) + abs(dy)
        if dist > sp.scent:
            return 0
        wind_dx = wind_dy = 0
        if self.environment is not None:
            weather = self.environment.weather.at(minute, player.x, player.y)
            wind_dx = int(weather.get("wind_dx", 0))
            wind_dy = int(weather.get("wind_dy", 0))
        if wind_dx == 0 and wind_dy == 0:
            return max(0, 18 - dist * 2) if dist <= max(2, sp.scent // 3) else 0

        downwind = dx * wind_dx + dy * wind_dy
        crosswind = abs(dx * wind_dy - dy * wind_dx)
        if downwind <= 0 or crosswind > max(2, sp.scent // 2):
            return 0
        return max(8, min(42, 30 + sp.scent - dist * 2))

    def _alarm_group(self, source: CreatureState, sp: SpeciesDef, turn: int, amount: int) -> None:
        if amount>=60 and hash_u64(self.seed,"animal-alarm-call",source.uid,turn)%100<35:
            p=WorldPos(source.x,source.y,source.z)
            self._write_sign(source,"call",p,p,self.state.clock_minute,min(90,amount),"alarm or warning call")
        if sp.herd_response <= 0:
            return
        for other in self.state.creatures.values():
            if other.uid == source.uid or other.z != source.z or other.species_id != source.species_id:
                continue
            if source.cohort_key and other.cohort_key != source.cohort_key:
                continue
            dist = abs(source.x - other.x) + abs(source.y - other.y)
            if dist > 10:
                continue
            transmitted = amount * sp.herd_response // 100
            if transmitted <= other.alertness:
                continue
            other.alertness = min(100, transmitted)
            if sp.combat_style in ("prey","herd_prey"):
                other.panic=max(other.panic,min(100,transmitted*sp.herd_cohesion//100))
            other.threat_x, other.threat_y, other.threat_z = source.threat_x, source.threat_y, source.threat_z
            other.last_threat_turn = max(other.last_threat_turn, turn)

    def _move_one(
        self,
        c: CreatureState,
        sp: SpeciesDef,
        player: WorldPos,
        turn: int,
        minute: int,
    ) -> bool:
        current = WorldPos(c.x, c.y, c.z)
        occupied = {(o.x, o.y, o.z) for o in self.state.creatures.values() if o.uid != c.uid}
        candidates: list[tuple[int, int, int, WorldPos]] = []
        for dx, dy in CARDINALS:
            nxt = current.moved(dx, dy)
            if (nxt.x, nxt.y, nxt.z) in occupied or nxt == player:
                continue
            if not self._passable_for(sp, nxt):
                continue
            d = abs(nxt.x - player.x) + abs(nxt.y - player.y)
            cover = self._cover_score(nxt)
            if c.behavior in ("flee","wounded_flee","disengage"):
                score=d*26+cover
                if c.behavior=="disengage":
                    gx,gy=self._group_centroid(c);score-= (abs(nxt.x-gx)+abs(nxt.y-gy))*4
            elif c.behavior=="herd_flee":
                gx,gy=self._group_centroid(c);cohesion=sp.herd_cohesion//12
                score=d*25+cover-(abs(nxt.x-gx)+abs(nxt.y-gy))*cohesion
            elif c.behavior=="regroup":
                gx,gy=self._group_centroid(c);score=-(abs(nxt.x-gx)+abs(nxt.y-gy))*30+d*3+cover//3
            elif c.behavior=="flank":
                fx=int(getattr(self.state,"player_facing_dx",0));fy=int(getattr(self.state,"player_facing_dy",1))
                if fx==0 and fy==0:fx,fy=0,1
                side=1 if c.pack_role=="flank_left" else -1
                tx=player.x+(-fy)*side*2-fx;ty=player.y+fx*side*2-fy
                score=-(abs(nxt.x-tx)+abs(nxt.y-ty))*34-d*2+cover//5
                if d==1:score+=40
            elif c.behavior=="charge":
                score=-d*42-cover//8
            elif c.behavior in ("seeking_water","seeking_food","return_home","retreat_home"):
                target=self._activity_target(c)
                if target:
                    td=abs(nxt.x-target.x)+abs(nxt.y-target.y)
                    score=-td*(42 if c.behavior=="retreat_home" else 32)+cover//2
                    if c.behavior=="retreat_home":score+=d*8
                else:score=cover-d
            else:
                score=-d*28+cover//4
            tie = int(hash_u64(self.seed, "animal-step", c.uid, turn, c.behavior, nxt.x, nxt.y) & 0xFFFF)
            candidates.append((score, tie, dx * 10 + dy, nxt))
        if not candidates:
            return False
        candidates.sort(key=lambda row: (row[0], row[1], row[2]), reverse=True)
        nxt = candidates[0][3]
        old = WorldPos(c.x, c.y, c.z)
        c.x, c.y = nxt.x, nxt.y
        c.facing_dx, c.facing_dy = nxt.x - old.x, nxt.y - old.y
        if self.state.player_aim_target == c.uid:
            loss = 24 if c.behavior in ("flee","herd_flee","wounded_flee","charge","flank") else 20 if c.behavior=="pursue" else 10
            self.state.player_aim_quality = max(0, int(self.state.player_aim_quality) - loss)
        c.last_move_turn = turn
        if c.behavior=="charge":c.charge_momentum=min(5,c.charge_momentum+1)
        elif c.behavior not in ("pursue","flank"):c.charge_momentum=max(0,c.charge_momentum-1)
        exertion = 10 if c.behavior=="charge" else 8 if c.behavior in ("flee","herd_flee","wounded_flee","pursue","flank","disengage","retreat_home") else 3 if c.behavior in ("seeking_water","seeking_food","return_home") else 4
        c.stamina = max(0, c.stamina - exertion)
        self._leave_sign(c, sp, old, nxt, turn, minute)
        return True

    def _passable_for(self, sp: SpeciesDef, pos: WorldPos) -> bool:
        tile = self.world.tile_at(pos)
        tags = set(tile.terrain.tags)
        water = "water" in tags
        aquatic = any(h in sp.habitats for h in ("river_shallow", "stream", "lake_shallow", "wetland", "shore"))
        world_pass = self.world.is_passable(pos) or (water and aquatic)
        if not world_pass:
            return False
        if water and not aquatic:
            return False
        if self.resources and self.resources.blocks_movement(pos):
            return False
        if self.building and not self.building.passable(pos, world_pass):
            return False
        return True

    def _cover_score(self, pos: WorldPos) -> int:
        tile = self.world.tile_at(pos)
        tid = tile.terrain_id.split(":")[-1]
        score = 0
        if "forest" in tid:
            score += 24
        if any(k in tid for k in ("scrub", "thicket", "reeds")):
            score += 18
        if self.resources and self.resources.blocks_sight(pos):
            score += 20
        return score

    def _visible(self, origin: WorldPos, target: WorldPos) -> bool:
        x0, y0, x1, y1 = origin.x, origin.y, target.x, target.y
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        first = True
        while True:
            if not first and (x0, y0) != (x1, y1):
                pos = WorldPos(x0, y0, origin.z)
                if self.world.tile_at(pos).terrain.blocks_sight:
                    return False
                if self.resources and self.resources.blocks_sight(pos):
                    return False
            if (x0, y0) == (x1, y1):
                return True
            first = False
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def _leave_sign(
        self,
        c: CreatureState,
        sp: SpeciesDef,
        old: WorldPos,
        new: WorldPos,
        turn: int,
        minute: int,
    ) -> None:
        terrain = self.world.tile_at(old).terrain_id.split(":")[-1]
        hard_ground = any(k in terrain for k in ("rock", "road", "stone"))
        chance = max(5, sp.trackability - (30 if hard_ground else 0) + min(20, sp.mass_kg // 8))
        roll = int(hash_u64(self.seed, "animal-track", c.uid, turn, old.x, old.y) % 100)
        if roll < chance:
            strength = max(10, min(100, sp.trackability + min(25, sp.mass_kg // 10)))
            self._write_sign(c, "track", old, new, minute, strength, terrain)

        bleeding = sum(max(0, int(w.get("bleeding", 0))) for w in c.wounds[-10:])
        if bleeding > 0:
            strength = max(15, min(100, bleeding * 9 + max(0, 100 - c.blood) // 2))
            self._write_sign(c, "blood", old, new, minute, strength, "blood trail")
        cover=self._cover_score(old)
        if cover>=16 and hash_u64(self.seed,"animal-disturbed-cover",c.uid,turn,old.x,old.y)%100<min(75,20+sp.mass_kg//3):
            self._write_sign(c,"disturbed",old,new,minute,max(20,min(85,cover+sp.mass_kg//6)),"bent or broken vegetation")

    def _write_sign(
        self,
        c: CreatureState,
        kind: str,
        old: WorldPos,
        new: WorldPos,
        minute: int,
        strength: int,
        detail: str,
    ) -> None:
        for existing in self.state.animal_signs.values():
            if existing.source_uid==c.uid and existing.kind==kind and existing.created_minute==minute and (existing.x,existing.y,existing.z)==(old.x,old.y,old.z):
                return
        token = hash_u64(
            self.seed, "animal-sign", c.uid, kind, minute,
            old.x, old.y, new.x, new.y, len(self.state.animal_signs),
        )
        uid = f"sign:{token:016x}"
        self.state.animal_signs[uid] = AnimalSignState(
            uid=uid,
            species_id=c.species_id,
            x=old.x,
            y=old.y,
            z=old.z,
            kind=kind,
            created_minute=minute,
            direction_x=new.x - old.x,
            direction_y=new.y - old.y,
            strength=strength,
            source_uid=c.uid,
            detail=detail,
        )
        if len(self.state.animal_signs) > 1200:
            oldest = sorted(self.state.animal_signs.values(), key=lambda s: (s.created_minute, s.uid))
            for sign in oldest[: len(self.state.animal_signs) - 1200]:
                self.state.animal_signs.pop(sign.uid, None)

    def _prune_signs(self, minute: int) -> None:
        for uid, sign in list(self.state.animal_signs.items()):
            ttl={"blood":18*60,"track":36*60,"scat":72*60,"feeding":48*60,"bed":72*60,"drink":12*60,"disturbed":18*60,"call":2*60,"home":7*1440}.get(sign.kind,36*60)
            if minute - sign.created_minute > ttl:
                self.state.animal_signs.pop(uid, None)

    def nearby_signs(self, pos: WorldPos, radius: int = 8) -> list[AnimalSignState]:
        rows = [
            sign for sign in self.state.animal_signs.values()
            if sign.z == pos.z and abs(sign.x - pos.x) + abs(sign.y - pos.y) <= radius
        ]
        return sorted(rows, key=lambda s: (abs(s.x - pos.x) + abs(s.y - pos.y), -s.created_minute, s.uid))

    def signs_at(self, pos: WorldPos) -> list[AnimalSignState]:
        return sorted(
            [s for s in self.state.animal_signs.values() if (s.x, s.y, s.z) == (pos.x, pos.y, pos.z)],
            key=lambda s: (-s.created_minute, s.uid),
        )

    def describe_sign(
        self,
        sign: AnimalSignState,
        hunting_skill: int,
        survival_skill: int,
        minute: int,
        *,
        species_known: bool = True,
    ) -> str:
        skill = max(int(hunting_skill), int(survival_skill))
        sp = self.registry.species.get(sign.species_id)
        animal = sp.name.lower() if sp and species_known else "animal"
        age = max(0, minute - sign.created_minute)
        if age <= 30:
            freshness = "very fresh"
        elif age <= 120:
            freshness = "fresh"
        elif age <= 480:
            freshness = "aging"
        else:
            freshness = "old"
        generic={"blood":"Blood sign.","track":"Animal tracks.","scat":"Animal droppings.","feeding":"Feeding sign.","bed":"Animal bedding.","drink":"Disturbed water edge.","disturbed":"Disturbed vegetation.","call":"Recent animal call.","home":"Animal shelter sign."}
        if skill < 2:
            return generic.get(sign.kind,"Animal sign.")
        direction = self._direction_name(sign.direction_x, sign.direction_y)
        if sign.kind == "blood":
            severity = "heavy" if sign.strength >= 65 else "clear" if sign.strength >= 35 else "faint"
            return f"{freshness.title()} {severity} blood from a {animal}, leading {direction}."
        if sign.kind=="track":
            print_strength = "deep" if sign.strength >= 70 else "clear" if sign.strength >= 40 else "faint"
            return f"{freshness.title()} {print_strength} {animal} tracks heading {direction}."
        if sign.kind=="scat":return f"{freshness.title()} droppings from a {animal}."
        if sign.kind=="feeding":return f"{freshness.title()} feeding sign from a {animal}: {sign.detail or 'browsed vegetation'}."
        if sign.kind=="bed":return f"{freshness.title()} {animal} bedding: {sign.detail or 'flattened cover'}."
        if sign.kind=="drink":return f"{freshness.title()} {animal} water-edge sign: {sign.detail or 'disturbed bank'}."
        if sign.kind=="disturbed":return f"{freshness.title()} vegetation disturbed by a {animal}, continuing {direction}."
        if sign.kind=="call":return f"{freshness.title()} audible sign of a {animal}: {sign.detail or 'alarm call'}."
        if sign.kind=="home":return f"{freshness.title()} use sign around a {animal} {sign.detail or 'shelter'}."
        return f"{freshness.title()} sign from a {animal}."

    @staticmethod
    def _direction_name(dx: int, dy: int) -> str:
        if abs(dx) >= abs(dy) and dx:
            return "east" if dx > 0 else "west"
        if dy:
            return "south" if dy > 0 else "north"
        return "an uncertain direction"
