from __future__ import annotations

from typing import Any

from worldseed.content.registry import ContentRegistry, SpeciesDef
from worldseed.core.coords import WorldPos
from worldseed.core.rng import hash_u64
from worldseed.systems.state import AnimalDenState, AnimalSignState, CreatureState, LivingWorldState


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

    def set_player_stance(self, stance:str)->str:
        stance="stalk" if stance=="stalk" else "normal"
        self.state.player_stance=stance
        if stance=="stalk":
            return "You lower your profile and begin stalking: slower movement, less noise, and better use of cover."
        return "You rise out of the stalking stance and resume normal movement."

    def movement_noise(self, pos: WorldPos, minute:int|None=None) -> int:
        tile = self.world.tile_at(pos)
        tid = tile.terrain_id.split(":")[-1]
        tags = set(tile.terrain.tags)
        noise = 26
        if "water" in tags: noise += 16
        if any(k in tid for k in ("rock", "gravel", "rubble")): noise += 10
        if any(k in tid for k in ("forest", "grass", "moss", "scrub")): noise -= 4
        if self.resources and self.resources.is_harvestable(pos): noise += 3
        # Equipment is physical noise: heavy/metal gear is harder to move quietly in.
        for iid in self.state.player_equipment.values():
            item=self.registry.items.get(iid)
            if not item:continue
            noise += min(8,max(0,int(item.mass_g)//1800))
            if item.material and "metal" in item.material:noise += 3
        if self.state.player_stance=="stalk":
            skill=max(int(self.state.player_skills.get("hunting",0)),int(self.state.player_skills.get("survival",0)))
            agility=int(self.state.player_attributes.get("agility",5))
            cover=self._cover_score(pos)
            noise -= 9 + min(14,skill) + max(0,agility-5) + min(8,cover//6)
        if self.environment is not None:
            when=self.state.clock_minute if minute is None else int(minute)
            weather=self.environment.weather.at(when,pos.x,pos.y)
            # Rain/wind mask footfall rather than making the player magically silent.
            noise -= min(12,int(weather.get("rain",0))*2 + int(weather.get("wind_speed",0))//18)
        return max(3, min(70, noise))

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
            self._ensure_den(creature,sp,minute)

            dist = abs(creature.x - player_pos.x) + abs(creature.y - player_pos.y)
            if turn <= int(getattr(creature,"staggered_until_turn",-1)):
                creature.behavior = "staggered"
                creature.stamina = min(sp.stamina, creature.stamina + 2)
                creature.charge_momentum = 0
                creature.charge_committed_until_turn = -1
                continue

            perceived = self._perception_score(creature, sp, player_pos, turn, minute)
            if perceived > 0:
                creature.activity="";creature.activity_until_turn=-1
                creature.activity_target_x=creature.activity_target_y=creature.activity_target_z=None
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

            creature.behavior = self._choose_behavior(creature, sp, dist, turn, player_pos)
            if creature.behavior=="calm" and creature.alertness < max(10,sp.flee_threshold//3):
                if self._activity_tick(creature,sp,player_pos,turn,minute):
                    continue
            if creature.behavior == "display":
                creature.stamina = min(sp.stamina,creature.stamina+3)
                continue
            if creature.behavior in ("pursue","defend","charge","flank") and dist <= 1:
                attackers.append(creature.uid)
                continue
            if creature.behavior in ("flee","herd_flee","wounded_flee","pursue","defend","charge","flank","disengage","regroup"):
                steps = self._movement_steps(creature, sp)
                for _ in range(steps):
                    if creature.uid not in self.state.creatures:
                        break
                    moved = self._move_one(creature, sp, player_pos, turn, minute)
                    if not moved:
                        break
                    dist = abs(creature.x - player_pos.x) + abs(creature.y - player_pos.y)
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

    def _update_needs(self,c:CreatureState,sp:SpeciesDef,minute:int)->None:
        if c.last_need_minute<0:
            c.last_need_minute=minute
            return
        elapsed=max(0,minute-c.last_need_minute)
        if elapsed<=0:return
        c.hunger=min(100,c.hunger+elapsed//28)
        c.thirst=min(100,c.thirst+elapsed//20)
        c.last_need_minute=minute

    def _den_owner_token(self,c:CreatureState,sp:SpeciesDef)->str:
        shared=sp.den_type in ("den","nest","lodge","cave") and bool(c.cohort_key)
        return c.cohort_key if shared else c.uid

    def _ensure_den(self,c:CreatureState,sp:SpeciesDef,minute:int)->AnimalDenState|None:
        if not sp.den_type:return None
        if c.home_den_uid and c.home_den_uid in self.state.animal_dens:
            return self.state.animal_dens[c.home_den_uid]
        owner=self._den_owner_token(c,sp)
        token=hash_u64(self.seed,"animal-den",sp.id,owner,c.z)
        uid=f"den:{token:016x}"
        existing=self.state.animal_dens.get(uid)
        if existing:
            c.home_den_uid=uid;return existing
        origin=WorldPos(c.x,c.y,c.z);candidates=[]
        for radius in range(0,7):
            for dx in range(-radius,radius+1):
                for dy in range(-radius,radius+1):
                    if abs(dx)+abs(dy)!=radius:continue
                    pos=origin.moved(dx,dy)
                    if not self._passable_for(sp,pos):continue
                    terrain=self.world.tile_at(pos).terrain_id.split(":")[-1]
                    cover=self._cover_score(pos);score=cover
                    if sp.den_type in ("burrow","den","bed") and any(k in terrain for k in ("forest","scrub","grass","moss")):score+=18
                    if sp.den_type=="nest" and any(k in terrain for k in ("forest","grass","marsh","shore")):score+=16
                    if sp.den_type=="wallow" and any(k in terrain for k in ("mud","flood","wet","marsh","grass")):score+=20
                    if sp.den_type in ("lodge","holt") and self._water_near(pos):score+=30
                    if sp.den_type=="cave" and pos.z<0:score+=35
                    tie=hash_u64(self.seed,"animal-den-site",uid,pos.x,pos.y,pos.z)&0xffff
                    candidates.append((score,int(tie),pos))
        if not candidates:return None
        candidates.sort(key=lambda row:(row[0],row[1]),reverse=True);pos=candidates[0][2]
        detail={"burrow":"dug burrow","bed":"flattened bedding site","nest":"nesting site","den":"sheltered den","wallow":"wallow and bedding hollow","lodge":"lodge","holt":"bank-side holt","cave":"cave refuge"}.get(sp.den_type,sp.den_type)
        den=AnimalDenState(uid,sp.id,pos.x,pos.y,pos.z,sp.den_type,minute,c.cohort_key,minute,{},100,detail)
        self.state.animal_dens[uid]=den;c.home_den_uid=uid
        if len(self.state.animal_dens)>320:
            referenced={x.home_den_uid for x in self.state.creatures.values() if x.home_den_uid}
            old=sorted((d for d in self.state.animal_dens.values() if d.uid not in referenced),key=lambda d:(d.last_used_minute,d.created_minute,d.uid))
            for d in old[:max(0,len(self.state.animal_dens)-320)]:self.state.animal_dens.pop(d.uid,None)
        return den

    def _water_near(self,pos:WorldPos)->bool:
        for dx,dy in ((0,0),(1,0),(-1,0),(0,1),(0,-1)):
            q=pos.moved(dx,dy);tile=self.world.tile_at(q)
            if "water" in set(tile.terrain.tags):return True
            if self.environment is not None:
                f=self.environment.fluid_at(q)
                if f is not None and getattr(f,"fluid","")=="water" and getattr(f,"amount",0)>10:return True
        return False

    def _find_activity_target(self,c:CreatureState,sp:SpeciesDef,kind:str,radius:int=7)->WorldPos|None:
        origin=WorldPos(c.x,c.y,c.z);rows=[]
        for r in range(0,radius+1):
            for dx in range(-r,r+1):
                for dy in range(-r,r+1):
                    if abs(dx)+abs(dy)!=r:continue
                    q=origin.moved(dx,dy)
                    if not self._passable_for(sp,q):continue
                    ok=False
                    if kind=="water":
                        ok=self._water_near(q)
                    elif kind=="food":
                        if sp.diet in ("herbivore","omnivore") and self.resources is not None:
                            fv=self.resources.feature_at(q)
                            rd=self.registry.resources.get(fv.feature_id) if fv else None
                            ok=bool(rd and "food" in rd.tags)
                        if not ok and sp.diet in ("carnivore","omnivore"):
                            ok=any(k.z==q.z and abs(k.x-q.x)+abs(k.y-q.y)<=1 and k.quality>15 for k in self.state.carcasses.values())
                    if ok:
                        score=-r*20+self._cover_score(q)//3
                        tie=hash_u64(self.seed,"animal-activity-target",c.uid,kind,q.x,q.y)&0xffff
                        rows.append((score,int(tie),q))
            if rows:break
        if not rows:return None
        rows.sort(key=lambda row:(row[0],row[1]),reverse=True);return rows[0][2]

    def _set_activity_target(self,c:CreatureState,target:WorldPos,activity:str,turn:int)->None:
        c.activity=activity;c.activity_until_turn=turn+12
        c.activity_target_x,c.activity_target_y,c.activity_target_z=target.x,target.y,target.z

    def _activity_tick(self,c:CreatureState,sp:SpeciesDef,player:WorldPos,turn:int,minute:int)->bool:
        # Existing stationary activity.
        if c.activity in ("feeding","drinking","resting") and turn<=c.activity_until_turn:
            if c.activity=="feeding":
                c.hunger=max(0,c.hunger-10);c.stamina=min(sp.stamina,c.stamina+2)
            elif c.activity=="drinking":
                c.thirst=max(0,c.thirst-14);c.stamina=min(sp.stamina,c.stamina+2)
            else:
                c.stamina=min(sp.stamina,c.stamina+12);c.pain=max(0,c.pain-1)
            return True
        if c.activity in ("feeding","drinking","resting") and turn>c.activity_until_turn:
            if c.activity=="feeding" and hash_u64(self.seed,"animal-scat",c.uid,turn//3)%100<38:
                pos=WorldPos(c.x,c.y,c.z);self._write_stationary_sign(c,"scat",pos,minute,max(20,sp.trackability//2),"droppings")
            c.activity="";c.activity_target_x=c.activity_target_y=c.activity_target_z=None

        # Continue travel toward an actual resource/den.
        if c.activity in ("to_food","to_water","to_den"):
            if c.activity_target_x is None or turn>c.activity_until_turn:
                c.activity="";return False
            target=WorldPos(int(c.activity_target_x),int(c.activity_target_y),int(c.activity_target_z or c.z))
            if (c.x,c.y,c.z)==(target.x,target.y,target.z):
                next_activity={"to_food":"feeding","to_water":"drinking","to_den":"resting"}[c.activity]
                c.activity=next_activity;c.activity_until_turn=turn+(3 if next_activity!="resting" else 5)
                detail="feeding sign" if next_activity=="feeding" else "trampled bank at a drinking spot" if next_activity=="drinking" else "flattened bedding"
                kind="feeding" if next_activity=="feeding" else "drink" if next_activity=="drinking" else "bed"
                self._write_stationary_sign(c,kind,target,minute,max(25,sp.trackability),detail)
                den=self.state.animal_dens.get(c.home_den_uid)
                if den and (den.x,den.y,den.z)==(c.x,c.y,c.z):den.last_used_minute=minute
                return True
            return self._move_activity_one(c,sp,target,turn,minute)

        # Needs and deterministic opportunistic distractions.
        profile=sp.activity_profile or {"feed":55,"drink":45,"rest":40}
        day_min=minute%1440;night=day_min<300 or day_min>1200
        choices=[]
        if c.thirst>=38:choices.append(("water",100+c.thirst))
        if c.hunger>=34:choices.append(("food",90+c.hunger))
        if c.stamina<=58 or night:choices.append(("rest",80+(sp.stamina-c.stamina)+(15 if night else 0)))
        if not choices:
            roll=hash_u64(self.seed,"animal-distraction",c.uid,turn//3)%300
            feed=int(profile.get("feed",55));drink=int(profile.get("drink",45));rest=int(profile.get("rest",40))
            if roll<feed:choices=[("food",feed)]
            elif roll<feed+drink:choices=[("water",drink)]
            elif roll<feed+drink+rest:choices=[("rest",rest)]
        if not choices:return False
        choices.sort(key=lambda row:row[1],reverse=True)
        for kind,_ in choices:
            if kind=="rest":
                den=self.state.animal_dens.get(c.home_den_uid)
                target=WorldPos(den.x,den.y,den.z) if den else WorldPos(c.x,c.y,c.z)
                if target==WorldPos(c.x,c.y,c.z):
                    c.activity="resting";c.activity_until_turn=turn+5
                    self._write_stationary_sign(c,"bed",target,minute,max(25,sp.trackability),"flattened bedding")
                    if den:den.last_used_minute=minute
                    return True
                self._set_activity_target(c,target,"to_den",turn);return self._move_activity_one(c,sp,target,turn,minute)
            target=self._find_activity_target(c,sp,kind)
            if target is None:continue
            self._set_activity_target(c,target,"to_"+kind,turn)
            return self._move_activity_one(c,sp,target,turn,minute)
        return False

    def _move_activity_one(self,c:CreatureState,sp:SpeciesDef,target:WorldPos,turn:int,minute:int)->bool:
        current=WorldPos(c.x,c.y,c.z);occupied={(o.x,o.y,o.z) for o in self.state.creatures.values() if o.uid!=c.uid}
        rows=[]
        for dx,dy in CARDINALS:
            q=current.moved(dx,dy)
            if q==target or ((q.x,q.y,q.z) not in occupied and self._passable_for(sp,q)):
                d=abs(q.x-target.x)+abs(q.y-target.y)
                score=-d*30+self._cover_score(q)//5
                tie=hash_u64(self.seed,"animal-activity-step",c.uid,c.activity,turn,q.x,q.y)&0xffff
                rows.append((score,int(tie),q))
        if not rows:return False
        rows.sort(key=lambda row:(row[0],row[1]),reverse=True);q=rows[0][2]
        old=current;c.x,c.y=q.x,q.y;c.facing_dx,c.facing_dy=q.x-old.x,q.y-old.y;c.last_move_turn=turn
        c.stamina=max(0,c.stamina-2);self._leave_sign(c,sp,old,q,turn,minute)
        return True

    def _write_stationary_sign(self,c:CreatureState,kind:str,pos:WorldPos,minute:int,strength:int,detail:str)->None:
        if c.last_sign_turn==minute and kind!="blood":return
        self._write_sign(c,kind,pos,pos,minute,strength,detail)
        c.last_sign_turn=minute

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
            if "leg" not in str(wound.get("part", "")):
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

        if dist <= sp.vision and self._visible(WorldPos(c.x, c.y, c.z), player):
            dx, dy = player.x - c.x, player.y - c.y
            facing = c.facing_dx * dx + c.facing_dy * dy
            sight = max(8, 44 - dist * 3)
            if facing < 0 and dist > 2:sight //= 2
            distraction={"feeding":72,"drinking":78,"resting":52}.get(c.activity,100)
            sight=sight*distraction//100
            if self.state.player_stance=="stalk":
                skill=max(int(self.state.player_skills.get("hunting",0)),int(self.state.player_skills.get("survival",0)))
                agility=int(self.state.player_attributes.get("agility",5));cover=self._cover_score(player)
                conceal=min(32,7+skill+max(0,agility-5)+cover//4)
                sight=max(0,sight-conceal)
            if self.environment is not None:
                weather=self.environment.weather.at(minute,player.x,player.y)
                sight=sight*max(4,min(8,int(weather.get("visibility",8))))//8
            score = max(score, sight)

        noise = self._player_noise
        if noise and noise["z"] == c.z and turn - int(noise["turn"]) <= 1:
            ndist = abs(c.x - int(noise["x"])) + abs(c.y - int(noise["y"]))
            radius = max(1, sp.hearing * max(20, int(noise["loudness"])) // 40)
            if ndist <= radius:
                heard=max(8,38+int(noise["loudness"])//3-ndist*3)
                heard=heard*{"feeding":76,"drinking":82,"resting":62}.get(c.activity,100)//100
                score=max(score,heard)

        scent = self._scent_score(c, sp, player, minute)
        score = max(score, scent)
        if dist <= 2:
            score = max(score, 35)
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
        exertion = 10 if c.behavior=="charge" else 8 if c.behavior in ("flee","herd_flee","wounded_flee","pursue","flank","disengage") else 4
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
        if self._cover_score(old)>=18 and hash_u64(self.seed,"animal-disturbance",c.uid,turn,old.x,old.y)%100<55:
            self._write_sign(c,"disturbed",old,new,minute,max(15,min(80,sp.mass_kg//3+sp.trackability//2)),"bent vegetation / disturbed ground")

        bleeding = sum(max(0, int(w.get("bleeding", 0))) for w in c.wounds[-10:])
        if bleeding > 0:
            strength = max(15, min(100, bleeding * 9 + max(0, 100 - c.blood) // 2))
            self._write_sign(c, "blood", old, new, minute, strength, "blood trail")

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
        ttl_by={"blood":18*60,"track":36*60,"disturbed":24*60,"drink":18*60,"feeding":48*60,"bed":72*60,"scat":96*60,"call":4*60}
        for uid, sign in list(self.state.animal_signs.items()):
            ttl=ttl_by.get(sign.kind,36*60)
            if minute-sign.created_minute>ttl:self.state.animal_signs.pop(uid,None)

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

    def nearby_dens(self,pos:WorldPos,radius:int=10)->list[AnimalDenState]:
        rows=[d for d in self.state.animal_dens.values() if d.z==pos.z and abs(d.x-pos.x)+abs(d.y-pos.y)<=radius]
        return sorted(rows,key=lambda d:(abs(d.x-pos.x)+abs(d.y-pos.y),-d.last_used_minute,d.uid))

    def describe_den(self,den:AnimalDenState,hunting_skill:int,survival_skill:int,minute:int,species_known:bool=True)->str:
        sp=self.registry.species.get(den.species_id);skill=max(int(hunting_skill),int(survival_skill))
        animal=sp.name.lower() if sp and species_known else "animal"
        age=max(0,minute-den.last_used_minute)
        use="freshly used" if age<=60 else "recently used" if age<=360 else "old"
        if skill<3:return f"An animal {den.kind}."
        stored=sum(den.stored_items.values())
        cache=f" It contains {stored} cached item(s)." if stored and skill>=6 else ""
        return f"A {use} {animal} {den.kind}: {den.detail}.{cache}"

    def describe_sign(
        self,
        sign: AnimalSignState,
        hunting_skill: int,
        survival_skill: int,
        minute: int,
        *,
        species_known: bool = True,
    ) -> str:
        skill=max(int(hunting_skill),int(survival_skill));sp=self.registry.species.get(sign.species_id)
        animal=sp.name.lower() if sp and species_known else "animal";age=max(0,minute-sign.created_minute)
        freshness="very fresh" if age<=30 else "fresh" if age<=120 else "aging" if age<=480 else "old"
        direction=self._direction_name(sign.direction_x,sign.direction_y)
        if skill<2:
            basic={"blood":"Blood sign.","track":"Animal tracks.","scat":"Animal droppings.","feeding":"Feeding sign.","bed":"Flattened bedding.","drink":"Tracks at a drinking spot.","disturbed":"Disturbed vegetation.","call":"Recent animal sign."}
            return basic.get(sign.kind,"Animal sign.")
        if sign.kind=="blood":
            severity="heavy" if sign.strength>=65 else "clear" if sign.strength>=35 else "faint"
            return f"{freshness.title()} {severity} blood from a {animal}, leading {direction}."
        if sign.kind=="track":
            clarity="deep" if sign.strength>=70 else "clear" if sign.strength>=40 else "faint"
            return f"{freshness.title()} {clarity} {animal} tracks heading {direction}."
        labels={"scat":"droppings","feeding":"feeding sign","bed":"bedding depression","drink":"drinking sign","disturbed":"disturbed vegetation","call":"calling sign"}
        label=labels.get(sign.kind,sign.kind.replace("_"," "))
        extra=f" ({sign.detail})" if skill>=6 and sign.detail else ""
        return f"{freshness.title()} {animal} {label}{extra}."

    @staticmethod
    def _direction_name(dx: int, dy: int) -> str:
        if abs(dx) >= abs(dy) and dx:
            return "east" if dx > 0 else "west"
        if dy:
            return "south" if dy > 0 else "north"
        return "an uncertain direction"
