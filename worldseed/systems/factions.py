from __future__ import annotations

from worldseed.core.rng import hash_u64
from worldseed.systems.history import HistorySystem
from worldseed.systems.state import ClaimState, LivingWorldState


class FactionSystem:
    def __init__(self, state: LivingWorldState, seed: bytes, history: HistorySystem):
        self.state = state
        self.seed = seed
        self.history = history
        self.route_planner = None

    def attach_route_planner(self, route_planner) -> None:
        self.route_planner = route_planner

    def monthly_update(self, minute: int) -> None:
        factions = list(self.state.factions.values())
        self._mobilize_and_supply(factions, minute)
        for f in factions:
            tax = 0
            for s in self.state.settlements.values():
                if s.faction_id == f.uid:
                    take = max(0, s.wealth * s.law.get("tax", 5) // 1000)
                    s.wealth -= take
                    f.treasury += take
                    tax += take
            f.power = max(1, min(200, f.power + (tax // 150) - len(f.at_war) - f.war_exhaustion // 35))
            if not f.at_war:
                f.war_exhaustion = max(0, f.war_exhaustion - 5)
        for i, a in enumerate(factions):
            for b in factions[i+1:]:
                rel = a.relations.get(b.uid, 0)
                claimed_by_a = any(c.active and c.claimant_id==a.uid and c.target_type=="settlement" and self.state.settlements.get(c.target_id) and self.state.settlements[c.target_id].faction_id==b.uid for c in self.state.claims.values())
                claimed_by_b = any(c.active and c.claimant_id==b.uid and c.target_type=="settlement" and self.state.settlements.get(c.target_id) and self.state.settlements[c.target_id].faction_id==a.uid for c in self.state.claims.values())
                drift = int(hash_u64(self.seed, "diplomacy", a.uid, b.uid, minute//(30*1440)) % 9) - 4
                if a.culture_id == b.culture_id:
                    drift += 2
                if claimed_by_a or claimed_by_b:
                    drift -= 3
                rel = max(-100, min(100, rel + drift))
                a.relations[b.uid] = rel
                b.relations[a.uid] = rel
                war_threshold = -55 if (claimed_by_a or claimed_by_b) else -70
                if rel < war_threshold and b.uid not in a.at_war and a.manpower >= 5 and b.manpower >= 5:
                    a.at_war.append(b.uid)
                    b.at_war.append(a.uid)
                    self.history.record("war", f"{a.name} declared war on {b.name}.", minute, subjects=[a.uid,b.uid], salience=85)
                elif (rel > 25 or a.war_exhaustion > 85 or b.war_exhaustion > 85) and b.uid in a.at_war:
                    a.at_war.remove(b.uid)
                    b.at_war.remove(a.uid)
                    a.war_exhaustion = max(0, a.war_exhaustion - 20)
                    b.war_exhaustion = max(0, b.war_exhaustion - 20)
                    self.history.record("peace", f"{a.name} and {b.name} made peace after mounting costs.", minute, subjects=[a.uid,b.uid], salience=70)
        self._resolve_conflicts(minute)

    def _mobilize_and_supply(self, factions, minute: int) -> None:
        for f in factions:
            towns = [s for s in self.state.settlements.values() if s.faction_id == f.uid and s.population > 0]
            population = sum(s.population for s in towns)
            border_posts = [
                p for p in self.state.border_posts.values()
                if p.active and p.controlling_faction_id == f.uid
            ]
            contested_towns = sum(1 for s in towns if getattr(s,"frontier_status","core")=="contested")
            target = max(3, population // 12 + len(border_posts) + contested_towns * 2)
            if f.manpower < target:
                f.manpower += min(target - f.manpower, max(1, population // 80))
            # Armies consume actual food/metal from settlements to create an aggregate military supply pool.
            for s in towns:
                if f.military_supply >= max(10, f.manpower * 2):
                    break
                food = min(3, s.stocks.get("core:wheat", 0))
                iron = min(1, s.stocks.get("core:iron_bloom", 0))
                if food:
                    s.stocks["core:wheat"] -= food
                    f.military_supply += food
                if iron:
                    s.stocks["core:iron_bloom"] -= iron
                    f.military_supply += iron * 3
            if f.at_war:
                upkeep = min(f.military_supply, max(1, f.manpower // 15))
                f.military_supply -= upkeep
                if upkeep == 0:
                    f.war_exhaustion = min(100, f.war_exhaustion + 8)

    def _resolve_conflicts(self, minute: int) -> None:
        month = minute // (30*1440)
        for a in self.state.factions.values():
            for bid in list(a.at_war):
                if a.uid > bid:
                    continue
                b = self.state.factions.get(bid)
                if not b:
                    continue
                if a.manpower <= 0 or b.manpower <= 0:
                    continue
                roll = hash_u64(self.seed, "war-month", a.uid, b.uid, month) % 100
                if roll >= 40:
                    continue
                strength_a = a.manpower * 2 + a.military_supply + a.power + int(hash_u64(self.seed,"battle-a",a.uid,b.uid,month)%30)
                strength_b = b.manpower * 2 + b.military_supply + b.power + int(hash_u64(self.seed,"battle-b",a.uid,b.uid,month)%30)
                winner, loser = (a,b) if strength_a >= strength_b else (b,a)
                winner_loss = max(1, min(winner.manpower, loser.manpower // 12 + 1))
                loser_loss = max(1, min(loser.manpower, winner.manpower // 8 + 2))
                winner.manpower -= winner_loss
                loser.manpower -= loser_loss
                winner.military_supply = max(0, winner.military_supply - winner_loss)
                loser.military_supply = max(0, loser.military_supply - loser_loss * 2)
                winner.war_exhaustion = min(100, winner.war_exhaustion + 3)
                loser.war_exhaustion = min(100, loser.war_exhaustion + 9)
                transfer = min(80, loser.treasury)
                loser.treasury -= transfer
                winner.treasury += transfer
                loser.power = max(1, loser.power - 3)
                winner.power = min(200, winner.power + 2)
                self.history.record("battle", f"Forces of {winner.name} defeated {loser.name}; casualties were {winner_loss} and {loser_loss}.", minute, subjects=[winner.uid,loser.uid], salience=65)
                if self.route_planner is not None:
                    damaged=self.route_planner.apply_war_damage(
                        winner.uid,loser.uid,minute,severity=min(70,18+winner_loss*3+loser_loss*4)
                    )
                    if damaged:
                        self.history.record(
                            "road_war_damage",
                            f"Fighting between {winner.name} and {loser.name} damaged strategic transport.",
                            minute,subjects=[winner.uid,loser.uid,*damaged],salience=42,
                        )
                if hash_u64(self.seed,"raid",winner.uid,loser.uid,month)%100 < 45:
                    self._raid_settlement(winner, loser, minute)

    def _raid_settlement(self, winner, loser, minute: int) -> None:
        targets = [s for s in self.state.settlements.values() if s.faction_id == loser.uid and s.population > 0]
        if not targets:
            return
        targets.sort(key=lambda s: (s.wealth, s.uid), reverse=True)
        target = targets[0]
        loot_value = 0
        for good in ("core:wheat", "core:turnip", "core:iron_bloom", "core:iron_ore", "core:coal"):
            qty = min(target.stocks.get(good,0), max(0, target.stocks.get(good,0)//5))
            if qty:
                target.stocks[good] -= qty
                loot_value += qty
        cash = min(target.wealth, 50)
        target.wealth -= cash
        winner.treasury += cash
        target.food_stress = min(100, target.food_stress + 12)
        casualties = min(max(0,target.population-5), max(0, target.population//40))
        target.population -= casualties
        if self.route_planner is not None:
            damaged=self.route_planner.apply_region_hazard(
                (target.region_x,target.region_y),"war",35,minute
            )
            if damaged:
                self.history.record(
                    "raid_road_damage",
                    f"The raid around {target.name} disrupted roads and crossings.",
                    minute,target.region_x,target.region_y,[winner.uid,loser.uid,target.uid,*damaged],salience=40,
                )
        claim_uid=f"claim:{winner.uid}:settlement:{target.uid}:war"
        if claim_uid in self.state.claims:
            self.state.claims[claim_uid].strength=min(100,self.state.claims[claim_uid].strength+10);self.state.claims[claim_uid].active=True
        else:
            self.state.claims[claim_uid]=ClaimState(claim_uid,winner.uid,"settlement",target.uid,"military_victory",45,minute,True)
        self.history.record("raid", f"{winner.name} raided {target.name}, seizing stores and coin; {casualties} residents were killed.", minute, target.region_x,target.region_y,[winner.uid,loser.uid,target.uid], salience=58)
