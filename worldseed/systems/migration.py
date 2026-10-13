from __future__ import annotations

from worldseed.core.rng import hash_u64
from worldseed.systems.history import HistorySystem
from worldseed.systems.state import LivingWorldState, MigrationCohortState
from worldseed.systems.pathfinding import HierarchicalPathfinder


class MigrationSystem:
    """Aggregate migration/refugees with named representative NPCs when available."""

    def __init__(self, state: LivingWorldState, seed: bytes, history: HistorySystem) -> None:
        self.state = state
        self.seed = seed
        self.history = history
        self.pathfinder = HierarchicalPathfinder(state, seed)
        self.npc_index = None

    def _pressure(self, town) -> int:
        faction = self.state.factions.get(town.faction_id)
        war = 35 if faction and faction.at_war else 0
        housing = min(35, town.homeless * 3)
        poverty = 15 if town.wealth < max(50, town.population) else 0
        return min(100, town.food_stress + war + housing + poverty)

    def monthly_update(self, minute: int) -> None:
        towns = [s for s in self.state.settlements.values() if s.population > 5]
        for origin in towns:
            if any(c.origin == origin.uid and c.status == "traveling" for c in self.state.migration_cohorts.values()):
                continue
            pressure = self._pressure(origin)
            if pressure < 45:
                continue
            candidates = [d for d in towns if d.uid != origin.uid and self._pressure(d) + 20 < pressure and d.housing_capacity - d.population > 2]
            if not candidates:
                continue
            candidates.sort(key=lambda d: (self._pressure(d) * 5 + abs(d.region_x-origin.region_x) + abs(d.region_y-origin.region_y), d.uid))
            dest = candidates[0]
            month = minute // (30 * 1440)
            if hash_u64(self.seed, "migration-depart", origin.uid, dest.uid, month) % 100 >= min(80, pressure):
                continue
            count = min(max(1, origin.population // 25), max(1, dest.housing_capacity - dest.population), 12)
            if count <= 0:
                continue
            origin.population -= count
            reason = "war" if self.state.factions.get(origin.faction_id) and self.state.factions[origin.faction_id].at_war else "hardship"
            route=self.pathfinder.regional_path((origin.region_x,origin.region_y),(dest.region_x,dest.region_y))
            dist=route.distance
            travel=max(1440,route.travel_minutes)
            uid = self.state.uid("migration")
            named = sorted((n for n in self.state.npcs.values() if n.alive and n.settlement_id == origin.uid and n.age >= 16), key=lambda n: n.uid)[:min(3,count)]
            for n in named:
                n.goal = "migrate"
                n.occupation = "migrant"
            cohort = MigrationCohortState(uid, origin.uid, dest.uid, count, reason, minute, minute+travel, "traveling", sum(n.wealth for n in named), [n.uid for n in named])
            self.state.migration_cohorts[uid] = cohort
            self.history.record("refugees" if reason == "war" else "migration", f"{count} people left {origin.name} for {dest.name} because of {reason}.", minute, origin.region_x, origin.region_y, [origin.uid,dest.uid,uid], salience=35 if reason=="war" else 20)

    def process(self, minute: int) -> None:
        for cohort in self.state.migration_cohorts.values():
            if cohort.status != "traveling" or cohort.arrive_minute > minute:
                continue
            dest = self.state.settlements.get(cohort.destination)
            origin = self.state.settlements.get(cohort.origin)
            if not dest:
                cohort.status = "lost"
                continue
            # Route danger/war can cost part of a refugee cohort without deleting all consequences.
            danger = 5
            if origin and self.state.factions.get(origin.faction_id) and self.state.factions[origin.faction_id].at_war:
                danger += 20
            loss = 0
            if hash_u64(self.seed,"migration-danger",cohort.uid) % 100 < danger:
                loss = min(cohort.count-1, max(0, cohort.count//4))
            arrived = max(0, cohort.count-loss)
            dest.population += arrived
            cohort.status = "arrived"
            for uid in cohort.npc_uids:
                npc = self.state.npcs.get(uid)
                if npc and npc.alive:
                    npc.settlement_id = dest.uid
                    npc.faction_id = dest.faction_id
                    npc.x, npc.y, npc.z = dest.x, dest.y, 0
                    npc.goal = "work"
                    npc.tasks.clear()
                    npc.property_id = npc.home_id = npc.workplace_id = ""
                    if self.npc_index is not None:
                        self.npc_index(npc)
            self.history.record("migration_arrival", f"{arrived} migrants from {origin.name if origin else cohort.origin} arrived in {dest.name}." + (f" {loss} were lost on the road." if loss else ""), minute, dest.region_x, dest.region_y, [cohort.uid,dest.uid], salience=22)
        cutoff=minute-90*1440
        for uid,cohort in list(self.state.migration_cohorts.items()):
            if cohort.status!="traveling" and cohort.arrive_minute<cutoff:self.state.migration_cohorts.pop(uid,None)
