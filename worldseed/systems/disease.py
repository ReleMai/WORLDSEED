from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from worldseed.content.registry import ContentRegistry, DiseaseDef
from worldseed.core.coords import WorldPos
from worldseed.core.rng import hash_u64
from worldseed.entities.components import Inventory, Vitals
from worldseed.systems.history import HistorySystem
from worldseed.systems.state import DiseaseState, GraveState, InfectionState, LivingWorldState


@dataclass(frozen=True, slots=True)
class ExposureRisk:
    disease_id: str
    score: int
    source: str


class EpidemiologySystem:
    """Hybrid individual/aggregate disease simulation.

    Named actors carry explicit InfectionState records.  The anonymous remainder
    of settlement populations is represented by DiseaseState SIR-like counts.
    Trade and migration carry pathogen loads rather than individual travelers,
    preserving causal spread without simulating every distant person.
    """

    MAX_TREND = 180

    def __init__(self, state: LivingWorldState, registry: ContentRegistry, seed: bytes, history: HistorySystem):
        self.state = state
        self.registry = registry
        self.seed = seed
        self.history = history
        self.npc_index = None

    def _def(self, disease_id: str) -> DiseaseDef | None:
        return self.registry.diseases.get(disease_id)

    def _outbreak_uid(self, settlement_id: str, disease_id: str) -> str:
        return f"outbreak:{settlement_id}:{disease_id}"

    def active_outbreaks(self, settlement_id: str | None = None) -> list[DiseaseState]:
        rows = [d for d in self.state.diseases.values() if d.infected > 0]
        if settlement_id is not None:
            rows = [d for d in rows if d.settlement_id == settlement_id]
        return sorted(rows, key=lambda d: (-d.infected, d.disease_id))

    def _season(self, minute: int) -> str:
        day = minute // 1440
        return ("spring", "summer", "autumn", "winter")[(day // 30) % 4]

    def _health_capacity(self, town) -> tuple[int, int]:
        named_healers = sum(1 for n in self.state.npcs.values() if n.alive and n.settlement_id == town.uid and n.occupation == "healer")
        labor_healers = town.labor_pool.get("healer", 0)
        medicine = town.stocks.get("core:herbal_tonic", 0)
        soap = town.stocks.get("core:soap", 0)
        town.healer_capacity = max(town.healer_capacity, named_healers * 3 + labor_healers)
        # Sanitation changes gradually; soap stock and wealth support it, crowding erodes it.
        target = 35 + min(35, soap // 2) + min(15, town.wealth // max(1, town.population * 8)) - min(30, town.homeless * 2)
        if town.sanitation < target:
            town.sanitation += 1
        elif town.sanitation > target:
            town.sanitation -= 1
        return max(0, town.healer_capacity), medicine

    def _policy(self, town, prevalence: int) -> None:
        old = town.health_policy
        if prevalence >= 30:
            town.health_policy = "quarantine"
            town.quarantine_level = min(95, max(town.quarantine_level, 70 + prevalence // 3))
        elif prevalence >= 12:
            town.health_policy = "restricted"
            town.quarantine_level = min(70, max(30, prevalence * 2))
        elif prevalence > 0:
            town.health_policy = "watch"
            town.quarantine_level = max(10, town.quarantine_level - 5)
        else:
            town.health_policy = "open"
            town.quarantine_level = max(0, town.quarantine_level - 10)
        if old != town.health_policy:
            self.history.record(
                "health_policy",
                f"{town.name} changed public-health policy from {old} to {town.health_policy}.",
                self.state.clock_minute,
                town.region_x,
                town.region_y,
                [town.uid],
                salience=18,
            )

    def _emergence_score(self, town, disease: DiseaseDef, minute: int) -> int:
        crowding = min(35, town.population // 10) + min(25, town.homeless * 3)
        hunger = town.food_stress // 3
        sanitation = max(0, 55 - town.sanitation)
        season = 18 if self._season(minute) in disease.season_bias else 0
        water = 18 if "waterborne" in disease.transmissions and town.sanitation < 45 else 0
        return max(0, crowding + hunger + sanitation + season + water - 55)

    def _seed_outbreak(self, town, disease_id: str, minute: int, initial: int, source: str, salience: int = 45) -> DiseaseState:
        disease = self._def(disease_id)
        if not disease:
            raise KeyError(disease_id)
        uid = self._outbreak_uid(town.uid, disease_id)
        existing = self.state.diseases.get(uid)
        if existing:
            existing.infected = min(town.population, max(existing.infected, initial))
            existing.last_minute = minute
            return existing
        strain = int(hash_u64(self.seed, "strain", town.uid, disease_id, minute // (30 * 1440)) % 21) - 10
        row = DiseaseState(
            disease_id=disease_id,
            region_x=town.region_x,
            region_y=town.region_y,
            infected=min(max(1, initial), max(1, town.population)),
            severity=max(1, min(100, disease.severity + strain)),
            contagiousness=max(1, min(100, disease.contagiousness + strain // 2)),
            name=disease.name,
            settlement_id=town.uid,
            strain=strain,
            first_minute=minute,
            last_minute=minute,
        )
        self.state.diseases[uid] = row
        town.outbreak_history.append({"minute": minute, "disease_id": disease_id, "event": "began", "source": source})
        town.outbreak_history[:] = town.outbreak_history[-60:]
        self.history.record(
            "disease_outbreak",
            f"{disease.name} appeared in {town.name} ({source}).",
            minute,
            town.region_x,
            town.region_y,
            [town.uid, uid],
            salience=salience,
        )
        return row

    def seed_outbreak(self, settlement_id: str, disease_id: str, minute: int, initial: int = 2, source: str = "unknown") -> DiseaseState | None:
        town = self.state.settlements.get(settlement_id)
        if not town or disease_id not in self.registry.diseases:
            return None
        return self._seed_outbreak(town, disease_id, minute, initial, source)

    def expose_npc(self, npc_uid: str, disease_id: str, minute: int, source: str = "community") -> str | None:
        npc = self.state.npcs.get(npc_uid)
        disease = self._def(disease_id)
        if not npc or not npc.alive or not disease:
            return None
        if npc.immunities.get(disease_id, 0) > minute:
            return None
        for inf_uid in npc.infections:
            inf = self.state.infections.get(inf_uid)
            if inf and inf.disease_id == disease_id and inf.stage != "recovered":
                return inf.uid
        uid = self.state.uid("infection")
        self.state.infections[uid] = InfectionState(uid, disease_id, "npc", npc.uid, minute, source=source)
        npc.infections.append(uid)
        return uid

    def expose_player(self, disease_id: str, minute: int, source: str = "community") -> str | None:
        disease = self._def(disease_id)
        if not disease or self.state.player_immunities.get(disease_id, 0) > minute:
            return None
        for inf_uid in self.state.player_infections:
            inf = self.state.infections.get(inf_uid)
            if inf and inf.disease_id == disease_id and inf.stage != "recovered":
                return inf.uid
        uid = self.state.uid("infection")
        self.state.infections[uid] = InfectionState(uid, disease_id, "player", "player", minute, source=source)
        self.state.player_infections.append(uid)
        return uid

    def _named_exposures(self, town, outbreak: DiseaseState, minute: int) -> None:
        if outbreak.infected <= 0 or town.population <= 0:
            return
        prevalence = outbreak.infected * 100 // max(1, town.population)
        disease = self._def(outbreak.disease_id)
        if not disease:
            return
        candidates = [n for n in self.state.npcs.values() if n.alive and n.settlement_id == town.uid]
        for npc in sorted(candidates, key=lambda n: n.uid):
            if any(self.state.infections.get(i) and self.state.infections[i].disease_id == outbreak.disease_id and self.state.infections[i].stage != "recovered" for i in npc.infections):
                continue
            immunity = npc.immunities.get(outbreak.disease_id, 0)
            if immunity > minute:
                continue
            resistance = 10 if npc.occupation == "healer" else 0
            threshold = max(1, prevalence * disease.contagiousness // 100 - resistance - town.quarantine_level // 8)
            if hash_u64(self.seed, "named-exposure", npc.uid, outbreak.disease_id, minute // 1440) % 100 < threshold:
                self.expose_npc(npc.uid, outbreak.disease_id, minute, f"outbreak:{town.uid}")

    def _death_npc(self, npc, town, disease: DiseaseDef, minute: int) -> None:
        if not npc.alive:
            return
        npc.alive = False
        if self.npc_index is not None:
            self.npc_index(npc)
        if town:
            town.population = max(1, town.population - 1)
        gid = f"grave:{npc.uid}"
        if gid not in self.state.graves:
            gx = (town.x if town else npc.x) + int(hash_u64(self.seed, "disease-grave-x", npc.uid) % 9) - 4
            gy = (town.y if town else npc.y) + int(hash_u64(self.seed, "disease-grave-y", npc.uid) % 9) - 4
            self.state.graves[gid] = GraveState(gid, npc.uid, npc.name, gx, gy, 0, minute, "grave", f"{npc.name}, died of {disease.name} aged {npc.age}")
        self.history.record(
            "disease_death",
            f"{npc.name} died of {disease.name}.",
            minute,
            town.region_x if town else 0,
            town.region_y if town else 0,
            [npc.uid],
            salience=28 if npc.occupation in {"healer", "scholar", "priest"} else 16,
        )

    def _advance_named_infections(self, minute: int, allow_named_mortality: bool = True) -> None:
        day = minute // 1440
        for uid, inf in list(self.state.infections.items()):
            if inf.stage == "recovered":
                continue
            disease = self._def(inf.disease_id)
            if not disease:
                continue
            age_hours = max(0, (minute - inf.exposed_minute) // 60)
            if age_hours < disease.incubation_hours:
                inf.stage = "incubating"
                inf.viral_load = min(100, 10 + age_hours * 50 // max(1, disease.incubation_hours))
                continue
            illness_age = age_hours - disease.incubation_hours
            if illness_age >= disease.illness_hours:
                inf.stage = "recovered"
                inf.symptomatic = False
                inf.recovered_minute = minute
                expiry = minute + disease.immunity_days * 1440
                if inf.host_type == "npc":
                    npc = self.state.npcs.get(inf.host_id)
                    if npc:
                        npc.immunities[disease.id] = expiry
                        npc.disease_history.append(disease.id)
                        npc.infections = [x for x in npc.infections if x != uid]
                elif inf.host_type == "player":
                    self.state.player_immunities[disease.id] = expiry
                    self.state.player_infections = [x for x in self.state.player_infections if x != uid]
                continue
            inf.stage = "symptomatic"
            inf.symptomatic = True
            inf.viral_load = max(20, 100 - illness_age * 70 // max(1, disease.illness_hours))
            base_severity = disease.severity + int(hash_u64(self.seed, "infection-severity", uid) % 21) - 10
            inf.severity = max(1, min(100, base_severity - (18 if inf.treated else 0)))
            if inf.host_type == "npc":
                npc = self.state.npcs.get(inf.host_id)
                if not npc or not npc.alive:
                    continue
                town = self.state.settlements.get(npc.settlement_id)
                npc.rest = min(100, npc.rest + max(2, inf.severity // 15))
                npc.hunger = min(100, npc.hunger + max(1, inf.severity // 30))
                daily_damage = max(0, inf.severity // 28 - (1 if inf.treated else 0))
                npc.hp = max(0, npc.hp - daily_damage)
                duration_days = max(1, disease.illness_hours // 24)
                risk = disease.mortality_permille * inf.severity // 100 // duration_days
                if town and town.healer_capacity > 0:
                    risk = risk * max(25, 100 - min(70, town.healer_capacity)) // 100
                fatal = npc.hp <= 0 or hash_u64(self.seed, "disease-mortality", uid, day) % 1000 < risk
                if fatal and allow_named_mortality:
                    self._death_npc(npc, town, disease, minute)
                    inf.stage="fatal";inf.recovered_minute=minute;inf.symptomatic=False
                    if disease.id not in npc.disease_history:npc.disease_history.append(disease.id)
                    npc.infections=[x for x in npc.infections if x!=uid]
                elif fatal:
                    # SAFE/offline policy permits illness and economic absence but
                    # clamps named people above zero HP until the world is active.
                    npc.hp=max(1,npc.hp)
            # Player systemic damage is applied separately so this class does not own death/continuation.

    def _treat_named(self, town) -> int:
        capacity = max(0, town.healer_capacity)
        medicine = town.stocks.get("core:herbal_tonic", 0)
        if capacity <= 0 or medicine <= 0:
            return 0
        cases = []
        for npc in self.state.npcs.values():
            if not npc.alive or npc.settlement_id != town.uid:
                continue
            for uid in npc.infections:
                inf = self.state.infections.get(uid)
                if inf and inf.stage == "symptomatic" and not inf.treated:
                    cases.append((inf.severity, uid))
        cases.sort(reverse=True)
        treated = 0
        for _, uid in cases[: min(capacity, medicine)]:
            self.state.infections[uid].treated = True
            treated += 1
        if treated:
            town.stocks["core:herbal_tonic"] = medicine - treated
        return treated

    def _transport_pathogens(self, minute: int) -> None:
        # Load pathogens when travelers leave.  Arrival creates a seed outbreak
        # with intensity proportional to traveler prevalence/pathogen load.
        for caravan in self.state.caravans.values():
            if caravan.status == "traveling" and not caravan.pathogen_load:
                origin = self.state.settlements.get(caravan.origin)
                if origin:
                    for d in self.active_outbreaks(origin.uid):
                        prevalence = d.infected * 100 // max(1, origin.population)
                        if prevalence and hash_u64(self.seed, "caravan-pathogen", caravan.uid, d.disease_id) % 100 < prevalence:
                            caravan.pathogen_load[d.disease_id] = max(1, prevalence // 5)
            elif caravan.status == "arrived" and caravan.pathogen_load:
                dest = self.state.settlements.get(caravan.destination)
                if dest:
                    for did, load in caravan.pathogen_load.items():
                        self._seed_outbreak(dest, did, minute, max(1, load // 2), f"caravan:{caravan.uid}", salience=55)
                caravan.pathogen_load.clear()
        for cohort in self.state.migration_cohorts.values():
            if cohort.status == "traveling" and not cohort.pathogen_load:
                origin = self.state.settlements.get(cohort.origin)
                if origin:
                    for d in self.active_outbreaks(origin.uid):
                        prevalence = d.infected * 100 // max(1, origin.population)
                        expected = cohort.count * prevalence // 100
                        if expected > 0:
                            cohort.pathogen_load[d.disease_id] = expected
            elif cohort.status == "arrived" and cohort.pathogen_load:
                dest = self.state.settlements.get(cohort.destination)
                if dest:
                    for did, load in cohort.pathogen_load.items():
                        self._seed_outbreak(dest, did, minute, max(1, load), f"migration:{cohort.uid}", salience=60)
                cohort.pathogen_load.clear()

    def transport_update(self, minute: int) -> None:
        self._transport_pathogens(minute)

    def _aggregate_outbreak(self, town, outbreak: DiseaseState, minute: int) -> None:
        disease = self._def(outbreak.disease_id)
        if not disease or town.population <= 0:
            outbreak.infected = 0
            return
        healers, medicine = self._health_capacity(town)
        # Public-health capacity is not free: staffing, sanitation and quarantine
        # consume municipal wealth, creating a real tradeoff against other uses.
        health_cost=max(0,healers//4 + town.quarantine_level//20)
        if health_cost:
            town.wealth=max(0,town.wealth-health_cost)
        prevalence = outbreak.infected * 100 // max(1, town.population)
        self._policy(town, prevalence)
        susceptibility = max(0, town.population - outbreak.infected - outbreak.immune)
        crowding = 100 + min(80, town.homeless * 4 + max(0, town.population - town.housing_capacity))
        hygiene = max(30, 130 - town.sanitation)
        quarantine = max(15, 100 - town.quarantine_level)
        channel = 100
        if "waterborne" in disease.transmissions:
            channel += max(0, 60 - town.sanitation)
        if "vector" in disease.transmissions and self._season(minute) in {"summer", "autumn"}:
            channel += 30
        force = outbreak.contagiousness * crowding * hygiene * quarantine * channel
        new_cases = outbreak.infected * force // 100_000_000
        new_cases = min(susceptibility, max(0, new_cases))
        duration_days = max(2, disease.illness_hours // 24)
        treatment_factor = min(60, healers * 2 + medicine * 3)
        recoveries = min(outbreak.infected, max(1 if outbreak.infected >= duration_days else 0, outbreak.infected // duration_days + treatment_factor // 25))
        daily_mortality_permille = max(0, disease.mortality_permille * outbreak.severity // 100 // duration_days)
        deaths_expected_num = outbreak.infected * daily_mortality_permille
        deaths = deaths_expected_num // 1000
        remainder = deaths_expected_num % 1000
        if hash_u64(self.seed, "aggregate-disease-death", outbreak.settlement_id, outbreak.disease_id, minute // 1440) % 1000 < remainder:
            deaths += 1
        deaths = min(max(0, outbreak.infected - recoveries), deaths)
        if treatment_factor:
            deaths = deaths * max(25, 100 - treatment_factor) // 100
        outbreak.infected = max(0, outbreak.infected + new_cases - recoveries - deaths)
        outbreak.recovered += recoveries
        outbreak.deaths += deaths
        outbreak.immune = min(town.population, outbreak.immune + recoveries)
        immune_decay = outbreak.immune // max(1, disease.immunity_days)
        outbreak.immune = max(0, outbreak.immune - immune_decay)
        outbreak.last_minute = minute
        town.population = max(1, town.population - deaths)
        if deaths:
            self.history.record(
                "epidemic_deaths",
                f"{disease.name} killed {deaths} people in {town.name}.",
                minute,
                town.region_x,
                town.region_y,
                [town.uid],
                salience=min(85, 25 + deaths * 4),
            )
        outbreak.policy = town.health_policy
        outbreak.trend.append([minute, outbreak.infected, outbreak.recovered, outbreak.deaths])
        outbreak.trend[:] = outbreak.trend[-self.MAX_TREND:]
        if outbreak.infected == 0:
            town.outbreak_history.append({"minute": minute, "disease_id": disease.id, "event": "ended", "deaths": outbreak.deaths})
            town.outbreak_history[:] = town.outbreak_history[-60:]
            self.history.record(
                "disease_ended",
                f"The {disease.name} outbreak in {town.name} ended after {outbreak.deaths} deaths.",
                minute,
                town.region_x,
                town.region_y,
                [town.uid],
                salience=35,
            )

    def _emerge(self, minute: int) -> None:
        day = minute // 1440
        for town in sorted(self.state.settlements.values(), key=lambda t: t.uid):
            if any(d.infected > 0 and d.settlement_id == town.uid for d in self.state.diseases.values()):
                continue
            for disease in sorted(self.registry.diseases.values(), key=lambda d: d.id):
                score = self._emergence_score(town, disease, minute)
                if score <= 0:
                    continue
                # Intentionally uncommon.  Long worlds see outbreaks, but not every town every season.
                if hash_u64(self.seed, "disease-emergence", town.uid, disease.id, day) % 10000 < min(800, score * 3):
                    initial = max(1, min(6, town.population // 30 + 1))
                    self._seed_outbreak(town, disease.id, minute, initial, "local emergence")
                    break

    def _compact_infections(self, minute: int) -> None:
        cutoff=minute-30*1440
        referenced=set(self.state.player_infections)
        for npc in self.state.npcs.values():referenced.update(npc.infections)
        for uid,inf in list(self.state.infections.items()):
            if uid in referenced:continue
            if inf.stage in {"recovered","fatal"} and inf.recovered_minute and inf.recovered_minute<cutoff:
                self.state.infections.pop(uid,None)

    def daily_update(self, minute: int, allow_named_mortality: bool = True) -> None:
        self._transport_pathogens(minute)
        self._emerge(minute)
        for outbreak in list(self.state.diseases.values()):
            town = self.state.settlements.get(outbreak.settlement_id)
            if not town:
                # Compatibility for old saves that only stored region coordinates.
                town = next((t for t in self.state.settlements.values() if (t.region_x, t.region_y) == (outbreak.region_x, outbreak.region_y)), None)
                if town:
                    outbreak.settlement_id = town.uid
            if not town:
                continue
            self._aggregate_outbreak(town, outbreak, minute)
            self._named_exposures(town, outbreak, minute)
            self._treat_named(town)
        self._advance_named_infections(minute,allow_named_mortality)
        self._transport_pathogens(minute)
        self._compact_infections(minute)

    def local_player_exposure(self, pos: WorldPos, minute: int) -> list[str]:
        exposed: list[str] = []
        rx, ry = pos.x // 512, pos.y // 512
        for outbreak in self.state.diseases.values():
            if outbreak.infected <= 0 or (outbreak.region_x, outbreak.region_y) != (rx, ry):
                continue
            town = self.state.settlements.get(outbreak.settlement_id)
            disease = self._def(outbreak.disease_id)
            if not town or not disease:
                continue
            prevalence = outbreak.infected * 100 // max(1, town.population)
            distance = abs(pos.x - town.x) + abs(pos.y - town.y)
            proximity = 100 if distance <= 16 else 50 if distance <= 128 else 20
            chance = prevalence * disease.contagiousness * proximity // 10000
            if hash_u64(self.seed, "player-exposure", outbreak.disease_id, minute // 60, pos.x // 8, pos.y // 8) % 100 < chance:
                uid = self.expose_player(outbreak.disease_id, minute, f"{town.name} outbreak")
                if uid:
                    exposed.append(outbreak.disease_id)
        return exposed

    def tick_player(self, minute: int, vitals: Vitals) -> list[str]:
        messages: list[str] = []
        for uid in list(self.state.player_infections):
            inf = self.state.infections.get(uid)
            if not inf:
                self.state.player_infections.remove(uid)
                continue
            disease = self._def(inf.disease_id)
            if not disease:
                continue
            age_hours = max(0, (minute - inf.exposed_minute) // 60)
            if age_hours < disease.incubation_hours:
                inf.stage = "incubating"
                continue
            illness_age = age_hours - disease.incubation_hours
            if illness_age >= disease.illness_hours:
                inf.stage = "recovered"; inf.recovered_minute = minute; inf.symptomatic = False
                self.state.player_immunities[disease.id] = minute + disease.immunity_days * 1440
                self.state.player_infections.remove(uid)
                messages.append(f"You recover from {disease.name}.")
                continue
            newly_symptomatic = inf.stage != "symptomatic"
            inf.stage = "symptomatic"; inf.symptomatic = True
            inf.severity = max(1, min(100, disease.severity + int(hash_u64(self.seed, "player-disease-severity", uid) % 21) - 10 - (20 if inf.treated else 0)))
            # Systemic disease damage is applied at most once per six-hour
            # simulation block, not once per player keypress.
            block=minute//360
            if block>inf.last_progress_minute//360:
                inf.last_progress_minute=minute
                vitals.stamina = max(0, vitals.stamina - max(1, inf.severity // 25))
                vitals.thirst = min(100, vitals.thirst + (3 if "dehydration" in disease.symptoms else 1))
                if inf.severity >= 60:
                    vitals.hp = max(0, vitals.hp - max(1, inf.severity // 35))
            if newly_symptomatic:
                messages.append(f"You develop symptoms of {disease.name}: {', '.join(disease.symptoms)}.")
        return messages

    def treat_player(self, inventory: Inventory, minute: int, medicine_skill: int = 0, field_medic: bool = False) -> str:
        symptomatic = [self.state.infections[uid] for uid in self.state.player_infections if uid in self.state.infections and self.state.infections[uid].stage == "symptomatic"]
        if not symptomatic:
            return "You have no symptomatic infection requiring medicine."
        if not inventory.remove("core:herbal_tonic", 1):
            return "You need an herbal tonic."
        symptomatic.sort(key=lambda x: (-x.severity, x.uid))
        inf = symptomatic[0]
        inf.treated = True
        # Skill improves supportive care without turning medicine into a
        # guaranteed cure. The disease progression system still owns outcome.
        care=min(25,max(0,medicine_skill)*2+(6 if field_medic else 0))
        inf.severity=max(1,inf.severity-care)
        disease = self._def(inf.disease_id)
        return f"You take an herbal tonic for {disease.name if disease else inf.disease_id}. Care reduces the immediate severity by {care}." if care else f"You take an herbal tonic for {disease.name if disease else inf.disease_id}. It may reduce severity, but it is not a guaranteed cure."

    def summary_for_settlement(self, settlement_id: str) -> dict:
        town = self.state.settlements.get(settlement_id)
        if not town:
            return {}
        rows = self.active_outbreaks(settlement_id)
        return {
            "policy": town.health_policy,
            "quarantine": town.quarantine_level,
            "sanitation": town.sanitation,
            "healers": town.healer_capacity,
            "outbreaks": len(rows),
            "infected": sum(d.infected for d in rows),
            "deaths": sum(d.deaths for d in rows),
        }
