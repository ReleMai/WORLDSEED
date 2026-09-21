from __future__ import annotations

from dataclasses import dataclass
import time
from collections import Counter
from typing import Iterable

from worldseed.config import OFFLINE_CAP_DAYS
from worldseed.core.coords import WorldPos
from worldseed.systems.state import LivingWorldState

TIER_A = "A"
TIER_B = "B"
TIER_C = "C"
TIER_D = "D"
TIER_E = "E"


@dataclass(frozen=True, slots=True)
class TierProfile:
    id: str
    name: str
    description: str
    ai_cadence_minutes: int | None
    ecology_cadence_minutes: int | None
    detail: str


PROFILES: dict[str, TierProfile] = {
    TIER_A: TierProfile("A", "Immediate", "Player vicinity", 60, 60, "individual movement/combat/fluids"),
    TIER_B: TierProfile("B", "Nearby", "Nearby realized area", 180, 360, "individuals at reduced cadence"),
    TIER_C: TierProfile("C", "Regional", "Player macro-region and neighbors", 1440, 1440, "cohorts, ledgers and scheduled actors"),
    TIER_D: TierProfile("D", "Distant", "Distant realized world", 43200, 10080, "aggregate daily/weekly/monthly equations"),
    TIER_E: TierProfile("E", "Potential", "Unrealized infinite world", None, None, "deterministic potential only"),
}


class LODSystem:
    """Authoritative simulation-fidelity classifier.

    Spatial infinity is permitted; infinite *individual simulation* is not.  The
    thresholds here are engine contracts rather than presentation distances.
    Systems can ask for a tier and choose an update cadence without inventing
    their own incompatible distance rules.
    """

    A_RADIUS = 64
    B_RADIUS = 256
    C_REGION_RADIUS = 1

    def __init__(self, state: LivingWorldState):
        self.state = state

    @staticmethod
    def _chebyshev(player: WorldPos, x: int, y: int, z: int) -> int:
        if z != player.z:
            # Adjacent z-levels are relevant, but not immediate unless at the
            # same horizontal position.  This keeps entire deep cave stacks
            # from becoming tier A merely because x/y happen to align.
            return max(abs(player.x - x), abs(player.y - y), 96 * abs(player.z - z))
        return max(abs(player.x - x), abs(player.y - y))

    def tier(self, player: WorldPos, x: int, y: int, z: int = 0, realized: bool = True) -> str:
        if not realized:
            return TIER_E
        d = self._chebyshev(player, x, y, z)
        if d <= self.A_RADIUS:
            return TIER_A
        if d <= self.B_RADIUS:
            return TIER_B
        prx, pry = player.x // 512, player.y // 512
        rx, ry = x // 512, y // 512
        if max(abs(prx - rx), abs(pry - ry)) <= self.C_REGION_RADIUS:
            return TIER_C
        return TIER_D

    def npc_tier(self, player: WorldPos, npc) -> str:
        return self.tier(player, npc.x, npc.y, npc.z, True)

    def creature_tier(self, player: WorldPos, creature) -> str:
        return self.tier(player, creature.x, creature.y, creature.z, True)

    def settlement_tier(self, player: WorldPos, settlement) -> str:
        return self.tier(player, settlement.x, settlement.y, 0, True)

    def should_update(self, tier: str, minute: int, kind: str = "ai") -> bool:
        profile = PROFILES[tier]
        cadence = profile.ai_cadence_minutes if kind == "ai" else profile.ecology_cadence_minutes
        if cadence is None:
            return False
        return minute % cadence == 0

    def snapshot(self, player: WorldPos) -> dict[str, dict[str, int]]:
        out = {tier: Counter() for tier in PROFILES}
        for npc in self.state.npcs.values():
            if npc.alive:
                out[self.npc_tier(player, npc)]["npcs"] += 1
        for creature in self.state.creatures.values():
            if creature.hp > 0:
                out[self.creature_tier(player, creature)]["creatures"] += 1
        for town in self.state.settlements.values():
            out[self.settlement_tier(player, town)]["settlements"] += 1
        # Cohorts are intrinsically tier C/D state.  Classify their 64-tile
        # ecology-cell centers so diagnostics reflect where aggregate life sits.
        for cohort in self.state.cohorts.values():
            x = cohort.region_x * 64 + 32
            y = cohort.region_y * 64 + 32
            tier = self.tier(player, x, y, cohort.z, True)
            if tier in (TIER_A, TIER_B):
                tier = TIER_C
            out[tier]["cohorts"] += 1
        return {tier: dict(counter) for tier, counter in out.items()}

    def offline_minutes(self, now: float | None = None) -> int:
        now = time.time() if now is None else now
        if not self.state.last_offline_wall_time:
            self.state.last_offline_wall_time = now
            return 0
        elapsed = max(0.0, now - self.state.last_offline_wall_time)
        self.state.last_offline_wall_time = now
        return min(OFFLINE_CAP_DAYS * 1440, int(elapsed // 60))

    def event_boundaries(self, start_minute: int, end_minute: int) -> list[tuple[int, str]]:
        """Return coarse boundaries relevant to offline simulation.

        The simulation advances between these boundaries rather than replaying
        every missed minute.  Six-hour environment blocks preserve crops/fire/
        local fluids approximately; arrivals/daily/monthly boundaries preserve
        causality in the social world.
        """
        if end_minute <= start_minute:
            return []
        events: set[tuple[int, str]] = set()

        # 6-hour environmental blocks.
        block = ((start_minute // 360) + 1) * 360
        while block <= end_minute:
            events.add((block, "environment"))
            block += 360

        day = ((start_minute // 1440) + 1) * 1440
        while day <= end_minute:
            events.add((day, "daily"))
            if (day // 1440) % 30 == 0:
                events.add((day, "monthly"))
            day += 1440

        for caravan in self.state.caravans.values():
            if caravan.status == "traveling" and start_minute < caravan.arrive_minute <= end_minute:
                events.add((caravan.arrive_minute, "arrival"))
        for cohort in self.state.migration_cohorts.values():
            if cohort.status == "traveling" and start_minute < cohort.arrive_minute <= end_minute:
                events.add((cohort.arrive_minute, "arrival"))

        return sorted(events, key=lambda row: (row[0], row[1]))

    def describe(self, player: WorldPos) -> list[str]:
        snap = self.snapshot(player)
        rows: list[str] = []
        for tier in (TIER_A, TIER_B, TIER_C, TIER_D, TIER_E):
            profile = PROFILES[tier]
            counts = snap.get(tier, {})
            bits = ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "empty"
            rows.append(f"{tier} {profile.name:<9} {bits:<34} {profile.detail}")
        return rows
