from __future__ import annotations

from worldseed.core.rng import hash_u64
from worldseed.systems.history import HistorySystem
from worldseed.systems.state import ClaimState, DynastyState, LivingWorldState, OfficeState


class GovernanceSystem:
    """Persistent rulers, succession, dynasties and political claims."""

    def __init__(self, state: LivingWorldState, seed: bytes, history: HistorySystem) -> None:
        self.state = state
        self.seed = seed
        self.history = history

    def monthly_update(self, minute: int) -> None:
        for faction in self.state.factions.values():
            office_id = f"office:{faction.uid}:ruler"
            office = self.state.offices.get(office_id)
            holder = self.state.npcs.get(office.holder_uid) if office else None
            if not office:
                rule = self._succession_rule(faction.uid)
                chosen = self._choose_candidate(faction.uid, rule, "")
                if chosen:
                    title = self._title_for(faction.uid)
                    office = OfficeState(office_id, faction.uid, title, chosen.uid, rule, minute, [])
                    self.state.offices[office_id] = office
                    self._ensure_dynasty(office, chosen.uid)
                    self.history.record("accession", f"{chosen.name} became {title} of {faction.name}.", minute, subjects=[chosen.uid,faction.uid], salience=55)
            elif not holder or not holder.alive:
                old_uid = office.holder_uid
                chosen = self._choose_candidate(faction.uid, office.succession_rule, old_uid)
                if chosen:
                    office.previous_holders.append(old_uid)
                    office.holder_uid = chosen.uid
                    office.started_minute = minute
                    self._ensure_dynasty(office, chosen.uid)
                    self.history.record("succession", f"{chosen.name} succeeded to the office of {office.title} in {faction.name}.", minute, subjects=[chosen.uid,old_uid,faction.uid], salience=65)
            self._ensure_local_claims(faction.uid, minute)
        self._age_claims(minute)

    def _succession_rule(self, faction_id: str) -> str:
        faction = self.state.factions[faction_id]
        culture = self.state.cultures.get(faction.culture_id)
        values = set(culture.values if culture else [])
        if "ancestry" in values:
            return "hereditary"
        if "freedom" in values or "trade" in values:
            return "elective"
        if "order" in values:
            return "seniority"
        return "merit"

    def _title_for(self, faction_id: str) -> str:
        culture = self.state.cultures.get(self.state.factions[faction_id].culture_id)
        values = set(culture.values if culture else [])
        if "war" in values:
            return "War-Leader"
        if "trade" in values:
            return "First Speaker"
        if "ancestry" in values:
            return "High Keeper"
        return "Steward"

    def _candidates(self, faction_id: str):
        return [n for n in self.state.npcs.values() if n.alive and n.faction_id == faction_id and n.age >= 18]

    def _choose_candidate(self, faction_id: str, rule: str, old_uid: str):
        candidates = self._candidates(faction_id)
        if not candidates:
            return None
        old = self.state.npcs.get(old_uid)
        if rule == "hereditary" and old:
            heirs = [self.state.npcs[c] for c in old.children if c in self.state.npcs and self.state.npcs[c].alive and self.state.npcs[c].age >= 16]
            if heirs:
                return sorted(heirs, key=lambda n:(-n.age,n.uid))[0]
        def score(n):
            base = n.wealth + n.age
            if n.occupation in ("guard","merchant","scholar"):base += 20
            if "ambitious" in n.traits:base += 25
            if "brave" in n.traits:base += 10
            if rule == "seniority":base += n.age * 4
            if rule == "elective":base += sum(r.get("respect",0)+r.get("trust",0) for r in n.relationships.values())//10
            base += int(hash_u64(self.seed,"office-candidate",faction_id,n.uid)%11)
            return base
        return max(candidates, key=lambda n:(score(n),n.uid))

    def _ensure_dynasty(self, office: OfficeState, holder_uid: str) -> None:
        if office.succession_rule != "hereditary":
            return
        existing = next((d for d in self.state.dynasties.values() if holder_uid in d.members), None)
        if existing:
            existing.prestige = min(100, existing.prestige + 2)
            return
        npc = self.state.npcs.get(holder_uid)
        if not npc:
            return
        family = [holder_uid] + [x for x in npc.parents+npc.children if x in self.state.npcs]
        uid = self.state.uid("dynasty")
        surname = npc.name.split()[-1] if npc.name.split() else npc.name
        self.state.dynasties[uid] = DynastyState(uid, f"House {surname}", office.faction_id, holder_uid, sorted(set(family)), 15)

    def _ensure_local_claims(self, faction_id: str, minute: int) -> None:
        for town in self.state.settlements.values():
            if town.faction_id != faction_id:
                continue
            uid = f"claim:{faction_id}:settlement:{town.uid}"
            if uid not in self.state.claims:
                self.state.claims[uid] = ClaimState(uid, faction_id, "settlement", town.uid, "administration", 100, minute, True)

    def wartime_claim(self, claimant_faction: str, settlement_id: str, minute: int, strength: int = 45) -> ClaimState:
        uid = f"claim:{claimant_faction}:settlement:{settlement_id}:war"
        claim = self.state.claims.get(uid)
        if claim:
            claim.strength = min(100, max(claim.strength, strength))
            claim.active = True
            return claim
        claim = ClaimState(uid, claimant_faction, "settlement", settlement_id, "military_victory", max(1,min(100,strength)), minute, True)
        self.state.claims[uid] = claim
        return claim

    def _age_claims(self, minute: int) -> None:
        month = minute // (30*1440)
        if month % 12:
            return
        for claim in self.state.claims.values():
            if claim.basis != "administration" and claim.active:
                claim.strength = max(0, claim.strength - 2)
                if claim.strength == 0:
                    claim.active = False
