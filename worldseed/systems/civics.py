from __future__ import annotations

from worldseed.core.rng import hash_u64
from worldseed.systems.history import HistorySystem
from worldseed.systems.state import LivingWorldState, PropertyState


class CivicsSystem:
    """Property claims, housing cashflows, taxes, and municipal maintenance.

    The settlement plan owns physical buildings. Civics attaches ownership and
    cashflows to those stable structure IDs when a physical plan is active.
    Distant/unprepared settlements keep the older aggregate property fallback.
    """

    PRIVATE_PROPERTY_KINDS = {"home", "workshop", "shop", "farm"}

    def __init__(self, state: LivingWorldState, seed: bytes, history: HistorySystem) -> None:
        self.state = state
        self.seed = seed
        self.history = history
        self.physicalization = None

    def attach_settlement_physicalization(self, physicalization) -> None:
        self.physicalization = physicalization

    def _skeleton(self, settlement_id: str):
        if self.physicalization is None:
            return None
        return self.physicalization.skeleton_for(settlement_id)

    @staticmethod
    def _property_kind(function: str) -> str:
        return {
            "residence": "home",
            "inn": "home",
            "barracks": "home",
            "outskirt_camp": "home",
            "market": "shop",
            "smithy": "workshop",
            "workshop": "workshop",
            "mill": "workshop",
            "fishery": "workshop",
            "barn": "farm",
            "clinic": "civic",
            "watchhouse": "civic",
            "shrine": "institution",
            "archive": "institution",
            "school": "institution",
        }.get(function, "civic")

    @staticmethod
    def _base_value(function: str) -> int:
        return {
            "residence": 55,
            "market": 120,
            "smithy": 135,
            "workshop": 105,
            "mill": 130,
            "fishery": 95,
            "barn": 80,
            "clinic": 125,
            "watchhouse": 145,
            "shrine": 110,
            "archive": 150,
            "school": 165,
        }.get(function, 90)

    def _sync_physical_properties(self, settlement_id: str) -> set[str]:
        town = self.state.settlements.get(settlement_id)
        skeleton = self._skeleton(settlement_id)
        if town is None or skeleton is None:
            return set()
        room_by_structure: dict[str, list] = {}
        for room in skeleton.rooms:
            room_by_structure.setdefault(room.structure_plan_id, []).append(room)
        valid: set[str] = set()
        for structure in sorted(skeleton.structures, key=lambda row: row.uid):
            if structure.destroyed:
                continue
            uid = structure.uid
            valid.add(uid)
            kind = self._property_kind(structure.function)
            area = max(1, int(structure.interior_area or len(structure.footprint)))
            bedrooms = sum(1 for r in room_by_structure.get(uid, ()) if r.kind == "bedroom")
            capacity = (
                max(2, bedrooms * 2, min(8, area // 3 + 1))
                if kind == "home"
                else max(1, min(12, area // 4 + 1))
            )
            base = self._base_value(structure.function)
            value = base + area * 4 + int(hash_u64(self.seed, "physical-property-value", uid) % 25)
            owner = town.property_owners.get(uid, town.uid)
            prop = self.state.properties.get(uid)
            if prop is None:
                prop = PropertyState(
                    uid=uid,
                    settlement_id=town.uid,
                    kind=kind,
                    owner_uid=owner,
                    value=value,
                    rent=max(1, value // (34 if kind == "home" else 28)),
                    capacity=capacity,
                    condition=max(0, min(100, int(structure.condition))),
                )
                self.state.properties[uid] = prop
            else:
                prop.settlement_id = town.uid
                prop.kind = kind
                prop.value = value
                prop.rent = max(1, value // (34 if kind == "home" else 28))
                prop.capacity = capacity
                # Physical structure condition remains authoritative. Property
                # state mirrors it and never becomes a second damage model.
                prop.condition = max(0, min(100, int(structure.condition)))
                if uid in town.property_owners:
                    prop.owner_uid = town.property_owners[uid]
            town.property_owners.setdefault(uid, prop.owner_uid)
        return valid

    def _properties(self, settlement_id: str) -> list[PropertyState]:
        skeleton = self._skeleton(settlement_id)
        if skeleton is not None:
            valid = self._sync_physical_properties(settlement_id)
            return sorted(
                (p for uid, p in self.state.properties.items() if uid in valid),
                key=lambda p: p.uid,
            )
        return sorted(
            (p for p in self.state.properties.values() if p.settlement_id == settlement_id),
            key=lambda p: p.uid,
        )

    def ensure_settlement(self, settlement_id: str) -> None:
        town = self.state.settlements.get(settlement_id)
        if not town:
            return
        if self._skeleton(settlement_id) is not None:
            self._sync_physical_properties(settlement_id)
            self._assign_ownership(town.uid)
            self._sync_physical_housing(town.uid)
            return

        # Aggregate fallback for distant/unprepared settlements. Do not consult
        # SettlementState.buildings as a second structure authority. Until the
        # physical plan is prepared, bounded property LOD is estimated from
        # population/occupations and is discarded in favor of plan IDs locally.
        houses = max(1, int(town.housing_capacity)//4) if town.housing_capacity > 0 else max(1, int(town.population)//4)
        workshops = max(0, len({
            n.occupation for n in self.state.npcs.values()
            if n.alive and n.settlement_id == town.uid and n.occupation in {"smith","carpenter","merchant","healer","scholar","priest"}
        }))
        for i in range(houses):
            uid = f"property:{town.uid}:home:{i}"
            if uid not in self.state.properties:
                value = 45 + int(hash_u64(self.seed, "property-value", uid) % 85)
                self.state.properties[uid] = PropertyState(
                    uid, town.uid, "home", town.uid, value, max(1, value // 30), 4
                )
        for i in range(workshops):
            uid = f"property:{town.uid}:shop:{i}"
            if uid not in self.state.properties:
                value = 80 + int(hash_u64(self.seed, "property-value", uid) % 140)
                self.state.properties[uid] = PropertyState(
                    uid, town.uid, "workshop", town.uid, value, max(2, value // 25), 3
                )
        self._assign_ownership(town.uid)
        self._assign_housing(town.uid)

    def _assign_ownership(self, settlement_id: str) -> None:
        town = self.state.settlements[settlement_id]
        candidates = sorted(
            (
                n
                for n in self.state.npcs.values()
                if n.alive and n.settlement_id == settlement_id and n.age >= 18
            ),
            key=lambda n: (-n.wealth, n.uid),
        )
        props = self._properties(settlement_id)
        for i, prop in enumerate(props):
            claimed = town.property_owners.get(prop.uid)
            if claimed:
                prop.owner_uid = claimed
                continue
            if prop.owner_uid != town.uid or prop.kind not in self.PRIVATE_PROPERTY_KINDS:
                continue
            if candidates and i < max(1, len(candidates) // 3):
                owner = candidates[i % len(candidates)]
                if owner.wealth >= prop.value // 5:
                    prop.owner_uid = owner.uid
                    town.property_owners[prop.uid] = owner.uid

    def _sync_physical_housing(self, settlement_id: str) -> None:
        town = self.state.settlements[settlement_id]
        skeleton=self._skeleton(settlement_id)
        shared_lodging={
            row.uid for row in (() if skeleton is None else skeleton.structures)
            if row.function in {"inn","barracks","outskirt_camp"}
        }
        homes = {
            p.uid: p
            for p in self._properties(settlement_id)
            if p.kind == "home" and p.condition > 20
        }
        for home in homes.values():
            home.occupants = []
        residents = sorted(
            (
                n
                for n in self.state.npcs.values()
                if n.alive and n.settlement_id == settlement_id
            ),
            key=lambda n: n.uid,
        )
        for npc in residents:
            home = homes.get(npc.home_id)
            if home is None:
                if npc.property_id in homes:
                    home = homes[npc.property_id]
                    npc.home_id = home.uid
                else:
                    npc.property_id = ""
                    continue
            # Lodging occupancy and private property ownership are separate.
            # Inns, barracks and camps house people without handing each guest
            # an ownership claim to the building.
            npc.property_id = "" if home.uid in shared_lodging else home.uid
            if npc.uid not in home.occupants:
                home.occupants.append(npc.uid)
        town.housing_capacity = sum(h.capacity for h in homes.values())
        represented_homeless = sum(1 for n in residents if n.home_id not in homes)
        aggregate_shortfall = max(0, town.population - town.housing_capacity)
        town.homeless = max(represented_homeless, aggregate_shortfall)

    def _assign_housing(self, settlement_id: str) -> None:
        if self._skeleton(settlement_id) is not None:
            self._sync_physical_housing(settlement_id)
            return
        town = self.state.settlements[settlement_id]
        homes = sorted(
            (
                p
                for p in self.state.properties.values()
                if p.settlement_id == settlement_id
                and p.kind == "home"
                and p.condition > 20
            ),
            key=lambda p: p.uid,
        )
        for h in homes:
            h.occupants = [
                uid
                for uid in h.occupants
                if uid in self.state.npcs
                and self.state.npcs[uid].alive
                and self.state.npcs[uid].settlement_id == settlement_id
            ]
        residents = sorted(
            (
                n
                for n in self.state.npcs.values()
                if n.alive and n.settlement_id == settlement_id
            ),
            key=lambda n: (0 if n.spouse_uid else 1, n.uid),
        )
        assigned = {uid for h in homes for uid in h.occupants}
        for npc in residents:
            if npc.uid in assigned:
                continue
            chosen = None
            if npc.spouse_uid:
                chosen = next(
                    (
                        h
                        for h in homes
                        if npc.spouse_uid in h.occupants and len(h.occupants) < h.capacity
                    ),
                    None,
                )
            if not chosen:
                chosen = next((h for h in homes if len(h.occupants) < h.capacity), None)
            if chosen:
                chosen.occupants.append(npc.uid)
                npc.property_id = chosen.uid
                npc.home_id = chosen.uid
                assigned.add(npc.uid)
        town.housing_capacity = sum(h.capacity for h in homes)
        represented_homeless = sum(1 for n in residents if not n.property_id)
        aggregate_shortfall = max(0, town.population - town.housing_capacity)
        town.homeless = max(represented_homeless, aggregate_shortfall)

    def owner_for_structure(self, settlement_id: str, structure_id: str) -> str:
        self.ensure_settlement(settlement_id)
        prop = self.state.properties.get(str(structure_id))
        if prop and prop.settlement_id == settlement_id:
            return prop.owner_uid
        town = self.state.settlements.get(settlement_id)
        return town.property_owners.get(str(structure_id), town.uid if town else "")

    def monthly_update(self, minute: int) -> None:
        for town in self.state.settlements.values():
            self.ensure_settlement(town.uid)
            physical = self._skeleton(town.uid) is not None
            rent_income = tax_income = maintenance = guard_wages = 0
            for prop in self._properties(town.uid):
                if prop.condition <= 0:
                    continue
                tenants = [
                    self.state.npcs[uid]
                    for uid in prop.occupants
                    if uid in self.state.npcs and self.state.npcs[uid].alive
                ]
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
                    if not physical:
                        prop.condition = min(100, prop.condition + 1)
                elif not physical:
                    prop.condition = max(0, prop.condition - 4)
            tax_rate = max(0, min(25, town.law.get("tax", 5)))
            for npc in (
                n
                for n in self.state.npcs.values()
                if n.alive and n.settlement_id == town.uid and n.age >= 18
            ):
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
                self.history.record(
                    "housing_crisis",
                    f"Overcrowding and homelessness worsened in {town.name}.",
                    minute,
                    town.region_x,
                    town.region_y,
                    [town.uid],
                    salience=22,
                )
