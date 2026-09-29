"""Persistent claim monuments and causal capture state.

Monuments are prepared only from the bounded settlement/route network.  They
never cause world realization from UI or map inspection, and their mutable
state is separate from rebuildable regional route data.
"""
from __future__ import annotations

from collections import defaultdict

from worldseed.config import TERRITORY_VERSION
from worldseed.core.coords import WorldPos
from worldseed.core.rng import hash_u64
from worldseed.systems.state import ClaimMonumentState, LivingWorldState
from worldseed.world.regional_plan import stable_plan_uid

REGION_SIZE = 512
CARDINALS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def monument_effective_control(monument: ClaimMonumentState) -> int:
    """Return the monument's present influence without mutating state."""
    if not monument.controller_faction_id or monument.integrity <= 0:
        return 0
    integrity = max(0, min(100, int(monument.integrity)))
    supply = max(0, min(100, int(monument.supply_level)))
    garrison = max(0, min(100, int(monument.garrison_strength)))
    support = 35 + supply * 35 // 100 + garrison * 30 // 100
    return max(0, int(monument.base_control) * integrity * support // 10_000)


class TerritorySystem:
    """Own generated monument sites and authoritative capture consequences."""

    def __init__(self, world, state: LivingWorldState, region_planner, history=None):
        self.world = world
        self.state = state
        self.region_planner = region_planner
        self.history = history
        self.seed = world.generator.world_seed
        self._presence: dict[str, dict[str, int]] = defaultdict(dict)

    @staticmethod
    def _route_regions(plans) -> set[tuple[int, int]]:
        out: set[tuple[int, int]] = set()
        for route in plans:
            out.update((int(x), int(y)) for x, y in route.region_path)
        return out

    def _score(self, rx: int, ry: int, route_regions: set[tuple[int, int]]) -> tuple[int, object]:
        plan = self.region_planner.plan(rx, ry, persist=True)
        route_junction = sum((rx + dx, ry + dy) in route_regions for dx, dy in CARDINALS)
        score = int(plan.route_value) + int(plan.crossing_value) + int(plan.defensibility) // 2
        score += route_junction * 12 + (12 if plan.waters else 0)
        if plan.control_potential in {"crossroads", "river_gate", "mountain_pass"}:
            score += 24
        if plan.settlement_present:
            score -= 80  # settlements already act as powerful control anchors
        if plan.dominant_biome == "water":
            score -= 100
        return score, plan

    def _physical_cell(self, rx: int, ry: int) -> tuple[int, int]:
        base_x = rx * REGION_SIZE + 64 + int(hash_u64(self.seed, "claim-monument-x", rx, ry) % 384)
        base_y = ry * REGION_SIZE + 64 + int(hash_u64(self.seed, "claim-monument-y", rx, ry) % 384)
        # This runs only during explicit route/region preparation.  The bounded
        # search gives the regional plan an exact legal surface coordinate.
        for radius in range(0, 13):
            cells = []
            for oy in range(-radius, radius + 1):
                for ox in range(-radius, radius + 1):
                    if max(abs(ox), abs(oy)) != radius:
                        continue
                    cells.append((hash_u64(self.seed, "claim-monument-cell", rx, ry, ox, oy), base_x + ox, base_y + oy))
            for _, x, y in sorted(cells):
                if self.world.is_passable(WorldPos(x, y, 0)):
                    return x, y
        return base_x, base_y

    @staticmethod
    def _archetype(score: int, crossing: int, defensibility: int) -> tuple[str, int, int]:
        if score >= 175 or (crossing >= 70 and defensibility >= 65):
            return "regional_stronghold", 90, 4
        if score >= 130:
            return "frontier_post", 70, 3
        if score >= 95:
            return "watch_monument", 52, 2
        return "claim_stone", 36, 1

    def prepare_sites(self, plans) -> tuple[ClaimMonumentState, ...]:
        """Prepare stable sites in already bounded civilization/route space."""
        route_regions = self._route_regions(plans)
        candidates = set(route_regions)
        for rx, ry in tuple(route_regions):
            candidates.update((rx + dx, ry + dy) for dx, dy in CARDINALS)
        ranked = []
        for rx, ry in sorted(candidates):
            score, plan = self._score(rx, ry, route_regions)
            if score < 62:
                continue
            tie = int(hash_u64(self.seed, "claim-monument-rank", TERRITORY_VERSION, rx, ry))
            ranked.append((-score, tie, rx, ry, plan))
        selected: list[tuple[int, int]] = []
        for neg_score, _tie, rx, ry, plan in sorted(ranked):
            if any(max(abs(rx - sx), abs(ry - sy)) < 2 for sx, sy in selected):
                continue
            uid = stable_plan_uid("claim-monument", f"territory-v{TERRITORY_VERSION}", f"{rx},{ry}")
            if uid not in self.state.claim_monuments:
                x, y = self._physical_cell(rx, ry)
                kind, base, reach = self._archetype(-neg_score, int(plan.crossing_value), int(plan.defensibility))
                self.state.claim_monuments[uid] = ClaimMonumentState(
                    uid=uid, monument_type=kind, region_x=rx, region_y=ry, x=x, y=y,
                    strategic_value=max(0, min(255, -neg_score)), base_control=base,
                    max_reach=reach, generation_version=TERRITORY_VERSION,
                )
            selected.append((rx, ry))
        return tuple(self.state.claim_monuments[uid] for uid in sorted(self.state.claim_monuments))

    def record_presence(self, monument_uid: str, faction_id: str, strength: int) -> None:
        if monument_uid not in self.state.claim_monuments or faction_id not in self.state.factions:
            return
        rows = self._presence[monument_uid]
        rows[faction_id] = rows.get(faction_id, 0) + max(0, int(strength))

    def damage(self, monument_uid: str, amount: int, minute: int, reason: str = "conflict") -> bool:
        monument = self.state.claim_monuments.get(monument_uid)
        if monument is None or amount <= 0:
            return False
        monument.integrity = max(0, monument.integrity - int(amount))
        monument.siege_state = "ruined" if monument.integrity == 0 else "damaged"
        monument.contested = True
        if monument.integrity == 0:
            monument.capture_progress = 0
            monument.claimant_faction_id = ""
        return True

    def repair(self, monument_uid: str, faction_id: str, amount: int, minute: int) -> bool:
        monument = self.state.claim_monuments.get(monument_uid)
        if monument is None or monument.controller_faction_id != faction_id or amount <= 0:
            return False
        monument.integrity = min(100, monument.integrity + int(amount))
        if monument.integrity > 0:
            monument.siege_state = "peace"
        return True

    def _supply_level(self, monument: ClaimMonumentState) -> int:
        if not monument.controller_faction_id or monument.integrity <= 0:
            return 0
        towns = [
            s for s in self.state.settlements.values()
            if s.faction_id == monument.controller_faction_id and s.population > 0
        ]
        if not towns:
            return 0
        distance = min(abs(int(s.region_x) - monument.region_x) + abs(int(s.region_y) - monument.region_y) for s in towns)
        region = f"{monument.region_x},{monument.region_y}"
        route_support = int(self.state.factions[monument.controller_faction_id].influence_regions.get(region, 0))
        return max(0, min(100, 90 - distance * 18 + route_support // 3))

    def daily_update(self, minute: int) -> None:
        for monument in sorted(self.state.claim_monuments.values(), key=lambda row: row.uid):
            monument.supply_level = self._supply_level(monument)
            if monument.supply_level > 0:
                monument.last_supplied_minute = int(minute)
            elif monument.controller_faction_id:
                monument.garrison_strength = max(0, monument.garrison_strength - 2)
            forces = sorted(self._presence.get(monument.uid, {}).items(), key=lambda row: (-row[1], row[0]))
            attacker = next((row for row in forces if row[0] != monument.controller_faction_id), None)
            defender = next((strength for faction, strength in forces if faction == monument.controller_faction_id), 0)
            if attacker and attacker[1] > defender and monument.integrity > 0:
                faction_id, strength = attacker
                if monument.claimant_faction_id != faction_id:
                    monument.claimant_faction_id = faction_id
                    monument.capture_progress = 0
                monument.capture_progress = min(100, monument.capture_progress + max(4, min(20, (strength - defender) // 2 + 4)))
                monument.contested = True
                monument.siege_state = "capture"
                if monument.capture_progress >= 100:
                    prior = monument.controller_faction_id
                    monument.controller_faction_id = faction_id
                    monument.claimant_faction_id = ""
                    monument.capture_progress = 0
                    monument.garrison_strength = min(100, strength)
                    monument.supply_level = self._supply_level(monument)
                    monument.last_supplied_minute = int(minute)
                    monument.contested = False
                    monument.siege_state = "occupied"
                    if self.history is not None:
                        self.history.record(
                            "claim_monument_captured",
                            f"{self.state.factions[faction_id].name} captured a {monument.monument_type.replace('_', ' ')}.",
                            minute, monument.region_x, monument.region_y,
                            [monument.uid, faction_id] + ([prior] if prior else []), salience=58,
                        )
            elif monument.capture_progress:
                monument.capture_progress = max(0, monument.capture_progress - 8)
                monument.contested = monument.capture_progress > 0
                if monument.capture_progress == 0:
                    monument.claimant_faction_id = ""
                    monument.siege_state = "peace"
        self._presence.clear()
