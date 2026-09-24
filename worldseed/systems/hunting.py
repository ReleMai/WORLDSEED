from __future__ import annotations

from typing import Any

from worldseed.content.registry import ContentRegistry, SpeciesDef
from worldseed.core.coords import WorldPos
from worldseed.core.rng import hash_u64
from worldseed.systems.state import AnimalSignState, CreatureState, LivingWorldState


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

    def movement_noise(self, pos: WorldPos) -> int:
        tile = self.world.tile_at(pos)
        tid = tile.terrain_id.split(":")[-1]
        tags = set(tile.terrain.tags)
        noise = 26
        if "water" in tags:
            noise += 16
        if any(k in tid for k in ("rock", "gravel", "rubble")):
            noise += 10
        if any(k in tid for k in ("forest", "grass", "moss")):
            noise -= 4
        if self.resources and self.resources.is_harvestable(pos):
            noise += 3
        return max(10, min(60, noise))

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

            dist = abs(creature.x - player_pos.x) + abs(creature.y - player_pos.y)
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

            creature.behavior = self._choose_behavior(creature, sp, dist, turn, player_pos)
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
            if facing < 0 and dist > 2:
                sight //= 2
            score = max(score, sight)

        noise = self._player_noise
        if noise and noise["z"] == c.z and turn - int(noise["turn"]) <= 1:
            ndist = abs(c.x - int(noise["x"])) + abs(c.y - int(noise["y"]))
            radius = max(1, sp.hearing * max(20, int(noise["loudness"])) // 40)
            if ndist <= radius:
                score = max(score, max(8, 38 + int(noise["loudness"]) // 3 - ndist * 3))

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
        for uid, sign in list(self.state.animal_signs.items()):
            ttl = 18 * 60 if sign.kind == "blood" else 36 * 60
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
        if skill < 2:
            return "Blood sign." if sign.kind == "blood" else "Animal tracks."
        direction = self._direction_name(sign.direction_x, sign.direction_y)
        if sign.kind == "blood":
            severity = "heavy" if sign.strength >= 65 else "clear" if sign.strength >= 35 else "faint"
            return f"{freshness.title()} {severity} blood from a {animal}, leading {direction}."
        if skill >= 6:
            print_strength = "deep" if sign.strength >= 70 else "clear" if sign.strength >= 40 else "faint"
            return f"{freshness.title()} {print_strength} {animal} tracks heading {direction}."
        return f"{freshness.title()} {animal} tracks heading {direction}."

    @staticmethod
    def _direction_name(dx: int, dy: int) -> str:
        if abs(dx) >= abs(dy) and dx:
            return "east" if dx > 0 else "west"
        if dy:
            return "south" if dy > 0 else "north"
        return "an uncertain direction"
