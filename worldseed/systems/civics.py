from __future__ import annotations

from worldseed.core.rng import hash_u64
from worldseed.systems.history import HistorySystem
from worldseed.systems.state import LivingWorldState, PropertyState


class CivicsSystem:
    """Housing, property ownership, rents, local taxes and municipal maintenance.

    This intentionally models *claims and cashflows*, not legal prose. Law/history/UI can
    consume the same state without owning it.
    """

    def __init__(self, state: LivingWorldState, seed: bytes, history: HistorySystem) -> None:
        self.state = state
        self.seed = seed
        self.history = history

    def ensure_settlement(self, settlement_id: str) -> None:
        town = self.state.settlements.get(settlement_id)
        if not town:
            return
        houses = max(0, town.buildings.get("house", 0))
        workshops = max(0, sum(v for k, v in town.buildings.items() if k not in ("house", "farm", "ruins")))
        for i in range(houses):
            uid = f"property:{town.uid}:home:{i}"
            if uid not in self.state.properties:
                value = 45 + int(hash_u64(self.seed, "property-value", uid) % 85)
                self.state.properties[uid] = PropertyState(uid, town.uid, "home", town.uid, value, max(1, value // 30), 4)
        for i in range(workshops):
            uid = f"property:{town.uid}:shop:{i}"
            if uid not in self.state.properties:
                value = 80 + int(hash_u64(self.seed, "property-value", uid) % 140)
                self.state.properties[uid] = PropertyState(uid, town.uid, "workshop", town.uid, value, max(2, value // 25), 3)
        self._assign_ownership(town.uid)
        self._assign_housing(town.uid)

    def _assign_ownership(self, settlement_id: str) -> None:
        town = self.state.settlements[settlement_id]
        candidates = sorted(
            (n for n in self.state.npcs.values() if n.alive and n.settlement_id == settlement_id and n.age >= 18),
            key=lambda n: (-n.wealth, n.uid),
        )
        props = sorted((p for p in self.state.properties.values() if p.settlement_id == settlement_id), key=lambda p: p.uid)
        for i, prop in enumerate(props):
            if prop.owner_uid != town.uid:
                continue
            # Property ownership is uncommon at low wealth; municipal housing remains possible.
            if candidates and i < max(1, len(candidates) // 3):
                owner = candidates[i % len(candidates)]
                if owner.wealth >= prop.value // 5:
                    prop.owner_uid = owner.uid
                    town.property_owners[prop.uid] = owner.uid

    def _assign_housing(self, settlement_id: str) -> None:
        town = self.state.settlements[settlement_id]
        homes = sorted((p for p in self.state.properties.values() if p.settlement_id == settlement_id and p.kind == "home" and p.condition > 20), key=lambda p: p.uid)
        for h in homes:
            h.occupants = [uid for uid in h.occupants if uid in self.state.npcs and self.state.npcs[uid].alive and self.state.npcs[uid].settlement_id == settlement_id]
        residents = sorted((n for n in self.state.npcs.values() if n.alive and n.settlement_id == settlement_id), key=lambda n: (0 if n.spouse_uid else 1, n.uid))
        assigned = {uid for h in homes for uid in h.occupants}
        for npc in residents:
            if npc.uid in assigned:
                continue
            chosen = None
            # Prefer spouse's household.
            if npc.spouse_uid:
                chosen = next((h for h in homes if npc.spouse_uid in h.occupants and len(h.occupants) < h.capacity), None)
            if not chosen:
                chosen = next((h for h in homes if len(h.occupants) < h.capacity), None)
            if chosen:
                chosen.occupants.append(npc.uid)
                npc.property_id = chosen.uid
                npc.home_id = chosen.uid
                assigned.add(npc.uid)
        town.housing_capacity = sum(h.capacity for h in homes)
        represented_homeless = sum(1 for n in residents if not n.property_id)
        # Population includes aggregate residents not represented by NPC objects.
        aggregate_shortfall = max(0, town.population - town.housing_capacity)
        town.homeless = max(represented_homeless, aggregate_shortfall)

    def monthly_update(self, minute: int) -> None:
        for town in self.state.settlements.values():
            self.ensure_settlement(town.uid)
            rent_income = tax_income = maintenance = guard_wages = 0
            for prop in (p for p in self.state.properties.values() if p.settlement_id == town.uid):
                if prop.condition <= 0:
                    continue
                tenants = [self.state.npcs[uid] for uid in prop.occupants if uid in self.state.npcs and self.state.npcs[uid].alive]
                owner = self.state.npcs.get(prop.owner_uid)
                for tenant in tenants:
                    if tenant.uid == prop.owner_uid:
                        continue
                    due = min(prop.rent, max(0, tenant.wealth // 4))
                    tenant.wealth -= due
                    if owner and owner.alive:
                        owner.wealth += due
                    else:
                        town.wealth += due
                    rent_income += due
                upkeep = max(1, prop.value // 80)
                if town.wealth >= upkeep:
                    town.wealth -= upkeep
                    maintenance += upkeep
                    prop.condition = min(100, prop.condition + 1)
                else:
                    prop.condition = max(0, prop.condition - 4)
            tax_rate = max(0, min(25, town.law.get("tax", 5)))
            for npc in (n for n in self.state.npcs.values() if n.alive and n.settlement_id == town.uid and n.age >= 18):
                due = min(npc.wealth, max(0, npc.wealth * tax_rate // 1000))
                npc.wealth -= due
                town.wealth += due
                tax_income += due
                if npc.occupation == "guard" and town.wealth >= 3:
                    town.wealth -= 3
                    npc.wealth += 3
                    guard_wages += 3
            town.budget = {
                "tax_income": tax_income,
                "rent_flow": rent_income,
                "maintenance": maintenance,
                "guard_wages": guard_wages,
                "balance": tax_income - maintenance - guard_wages,
            }
            self._assign_housing(town.uid)
            if town.homeless > max(3, town.population // 10):
                town.food_stress = min(100, town.food_stress + 4)
                self.history.record("housing_crisis", f"Overcrowding and homelessness worsened in {town.name}.", minute, town.region_x, town.region_y, [town.uid], salience=22)
