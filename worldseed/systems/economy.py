from __future__ import annotations

from collections import defaultdict

from worldseed.content.registry import ContentRegistry, SettlementProcessDef
from worldseed.core.rng import hash_u64
from worldseed.systems.history import HistorySystem
from worldseed.systems.state import CaravanState, LaborReservationState, LivingWorldState, MarketTransactionState, TradeRouteState, TheftRecordState
from worldseed.systems.pathfinding import HierarchicalPathfinder

BASE_PRICE = {
    "core:wheat": 4, "core:turnip": 5, "core:meat": 9, "core:hide": 12,
    "core:wood": 5, "core:stone": 4, "core:iron_ore": 14, "core:coal": 10,
    "core:wooden_bowl": 7, "core:cooked_meat": 13,
    "core:wheat_seed": 3, "core:turnip_seed": 3, "core:relic": 120,
    "core:iron_bloom": 28, "core:steel_billet": 55,
    "core:medicinal_herb": 5, "core:herbal_tonic": 18, "core:soap": 10,
    "core:fiber": 4, "core:bark": 3, "core:clay_lump": 4, "core:largemouth_bass": 20,
    "core:flour": 6, "core:bread": 11, "core:woven_cloth": 14, "core:leather": 18,
    "core:small_ale": 12, "core:clay_pot": 9, "core:dressed_stone": 9, "core:smoked_fish": 18,
}
TARGET = {
    "core:wheat": 120, "core:turnip": 80, "core:meat": 35, "core:hide": 20,
    "core:wood": 70, "core:stone": 70, "core:iron_ore": 30, "core:coal": 30,
    "core:wooden_bowl": 18, "core:cooked_meat": 28,
    "core:wheat_seed": 25, "core:turnip_seed": 20, "core:iron_bloom": 15,
    "core:medicinal_herb": 20, "core:herbal_tonic": 16, "core:soap": 24,
    "core:fiber": 36, "core:bark": 28, "core:clay_lump": 30, "core:largemouth_bass": 24,
    "core:flour": 36, "core:bread": 28, "core:woven_cloth": 18, "core:leather": 18,
    "core:small_ale": 24, "core:clay_pot": 14, "core:dressed_stone": 24, "core:smoked_fish": 18,
}

# Aggregate labor composition. Named NPCs are representatives; this pool models the rest of a town.
MAX_TRADE_PARTNERS = 6

LABOR_SHARES = {
    "farmer": 22, "miner": 8, "lumberjack": 5, "carpenter": 4, "cook": 3,
    "hunter": 5, "smith": 4, "merchant": 6, "guard": 6, "healer": 4,
    "scholar": 3, "herder": 4, "miller": 3, "baker": 3, "butcher": 3,
    "fisher": 3, "weaver": 3, "tanner": 2, "brewer": 2, "potter": 2, "mason": 3,
}


class EconomySystem:
    def __init__(self, state: LivingWorldState, registry: ContentRegistry, world_seed: bytes, history: HistorySystem):
        self.state = state
        self.registry = registry
        self.seed = world_seed
        self.history = history
        self.pathfinder = HierarchicalPathfinder(state, world_seed)
        self._route_town_ids: set[str] = set()
        self.workplace_logistics=None
        self.route_planner=None
        self.physical_labor_authorities=[]

    def attach_workplace_logistics(self,system)->None:self.workplace_logistics=system
    def attach_route_planner(self,system)->None:self.route_planner=system
    def attach_physical_labor_authority(self,system)->None:
        if system is not None and system not in self.physical_labor_authorities:
            self.physical_labor_authorities.append(system)

    def _physical_worker_claim(self,town,proc,workers:int,day:int)->int:
        claimed=0
        remaining=max(0,int(workers))
        for authority in self.physical_labor_authorities:
            fn=getattr(authority,"abstract_worker_claim",None)
            if not callable(fn):continue
            amount=max(0,int(fn(town,proc,int(day),remaining)))
            amount=min(remaining,amount)
            claimed+=amount;remaining-=amount
            if remaining<=0:break
        return claimed

    def _price(self, item: str, stock: int) -> int:
        base = BASE_PRICE.get(item, self.registry.items.get(item).base_value if item in self.registry.items else 5)
        target = TARGET.get(item, 30)
        scarcity = max(25, min(400, (target * 100) // max(1, stock)))
        return max(1, (base * scarcity) // 100)

    def ensure_currency(self, settlement) -> None:
        if settlement.currency_id:
            return
        culture=self.state.cultures.get(settlement.culture_id)
        faction=self.state.factions.get(settlement.faction_id)
        root=(culture.name.split()[0] if culture and culture.name else "Local")
        settlement.currency_id=f"currency:{settlement.faction_id}"
        settlement.currency_name=f"{root} Mark"
        settlement.currency_value=80+int(hash_u64(self.seed,"currency-value",settlement.faction_id)%41)
        settlement.barter_enabled=True

    def update_prices(self) -> None:
        for s in self.state.settlements.values():
            self.ensure_currency(s)
            goods = set(BASE_PRICE) | set(s.stocks)
            s.prices = {g: self._price(g, s.stocks.get(g, 0)) for g in goods}

    def _build_labor_pool(self, town) -> None:
        working = max(1, town.population * 55 // 100)
        # Disease removes some labor from production without requiring every
        # anonymous resident to become an entity. Quarantine also suppresses
        # merchant activity while shifting capacity toward care.
        active_cases=sum(d.infected for d in self.state.diseases.values() if d.settlement_id==town.uid and d.infected>0)
        prevalence=min(100,active_cases*100//max(1,town.population))
        working=max(1,working*(100-min(45,prevalence//2))//100)
        pool = {occ: working * pct // 100 for occ, pct in LABOR_SHARES.items()}
        if town.quarantine_level>0:
            merchant_loss=pool.get("merchant",0)*town.quarantine_level//120
            pool["merchant"]=max(0,pool.get("merchant",0)-merchant_loss)
            pool["healer"]=pool.get("healer",0)+merchant_loss//2
        used = sum(pool.values())
        pool["general"] = max(0, working - used)
        # Local conditions shift labor rather than conjuring output.
        if town.food_stress > 45:
            shift = min(pool.get("general", 0), max(1, working // 20))
            pool["general"] -= shift
            pool["farmer"] += shift
        faction = self.state.factions.get(town.faction_id)
        if faction and faction.at_war:
            shift = min(pool.get("general", 0) + pool.get("merchant", 0) // 3, max(1, working // 15))
            from_general = min(pool.get("general", 0), shift)
            pool["general"] -= from_general
            pool["guard"] += from_general
        town.labor_pool = pool
        town.unemployment = pool.get("general", 0)

    def _shortage_score(self, town, proc: SettlementProcessDef) -> int:
        good = proc.priority_good
        target = TARGET.get(good, 30)
        stock = town.stocks.get(good, 0)
        score = max(1, target - stock)
        # Inputs that cannot be supplied strongly suppress the process.
        for iid, qty in proc.inputs.items():
            if town.stocks.get(iid, 0) < qty:
                score //= 4
        if proc.knowledge and proc.knowledge not in town.knowledge:
            return 0
        return score

    def _reserve_labor(self, town, day: int) -> list[tuple[SettlementProcessDef, int]]:
        self._build_labor_pool(town)
        by_occ: dict[str, list[SettlementProcessDef]] = defaultdict(list)
        for proc in self.registry.settlement_processes.values():
            by_occ[proc.occupation].append(proc)
        assignments: list[tuple[SettlementProcessDef, int]] = []
        for occ, processes in sorted(by_occ.items()):
            available = town.labor_pool.get(occ, 0)
            if available <= 0:
                continue
            scores = [(self._shortage_score(town, p), p) for p in processes]
            scores = [(score, p) for score, p in scores if score > 0]
            if not scores:
                continue
            scores.sort(key=lambda pair: (-pair[0], pair[1].id))
            total = sum(score for score, _ in scores)
            left = available
            for idx, (score, proc) in enumerate(scores):
                if idx == len(scores) - 1:
                    workers = left
                else:
                    workers = min(left, max(proc.workers, available * score // max(1, total)))
                workers -= workers % proc.workers
                if workers <= 0 and left >= proc.workers:
                    workers = proc.workers
                workers = min(workers, left)
                left -= workers
                uid = f"labor:{town.uid}:{proc.id}"
                self.state.labor_reservations[uid] = LaborReservationState(uid, town.uid, proc.id, occ, workers, day, workers > 0, [])
                if workers:
                    assignments.append((proc, workers))
                if left < min((p.workers for _, p in scores), default=1):
                    break
        self._bind_representative_labor(town, day)
        return assignments

    def _bind_representative_labor(self, town, day: int) -> None:
        """Bind named representatives to aggregate labor slots without duplicating output."""
        reservations=[
            row for row in self.state.labor_reservations.values()
            if row.settlement_id==town.uid and row.assigned_day==day and row.active and row.workers>0
        ]
        by_occ=defaultdict(list)
        for row in reservations:
            row.representative_uids=[]
            by_occ[row.occupation].append(row)
        for rows in by_occ.values():
            rows.sort(key=lambda row:(row.process_id,row.uid))
        representatives=sorted(
            (npc for npc in self.state.npcs.values() if npc.alive and npc.settlement_id==town.uid and npc.age>=16),
            key=lambda npc:npc.uid,
        )
        for npc in representatives:
            npc.work_assignment_day=day
            npc.work_hours_today=0
            npc.assigned_process_id=""
            rows=by_occ.get(npc.occupation,())
            if not rows:
                continue
            row=min(
                rows,
                key=lambda r:(
                    len(r.representative_uids)*1000//max(1,r.workers),
                    -r.workers,
                    r.process_id,
                ),
            )
            row.representative_uids.append(npc.uid)
            npc.assigned_process_id=row.process_id

    def representative_work(self, npc, town, minute: int) -> str:
        """Record physical work against today's aggregate assignment."""
        day=int(minute)//1440
        if npc.work_assignment_day!=day:
            self._bind_representative_labor(town,day)
        if not npc.assigned_process_id:
            return ""
        reservation=self.state.labor_reservations.get(f"labor:{town.uid}:{npc.assigned_process_id}")
        if reservation is None or reservation.assigned_day!=day or not reservation.active:
            npc.assigned_process_id=""
            return ""
        npc.work_hours_today=min(24,npc.work_hours_today+1)
        if npc.uid not in reservation.representative_uids:
            reservation.representative_uids.append(npc.uid)
        return npc.assigned_process_id

    def _production_bonus(self,town,proc:SettlementProcessDef)->int:
        culture=self.state.cultures.get(town.culture_id);religion=self.state.religions.get(town.religion_id);bonus=100
        if proc.occupation=="farmer" and religion and "harvest" in religion.domains:bonus+=15
        if proc.occupation in ("smith","carpenter") and culture and "craft" in culture.values:bonus+=10
        return bonus

    def _run_process(self, town, proc: SettlementProcessDef, workers: int, day:int|None=None, minute:int=0) -> int:
        bonus=self._production_bonus(town,proc)
        if day is not None and self.physical_labor_authorities:
            workers=max(0,int(workers)-self._physical_worker_claim(town,proc,int(workers),int(day)))
            if workers<=0:return 0
        if self.workplace_logistics is not None and day is not None:
            return self.workplace_logistics.run_process(town,proc,workers,int(day),int(minute),bonus)
        batches = workers // max(1, proc.workers)
        if batches <= 0:return 0
        for iid,qty in proc.inputs.items():batches=min(batches,town.stocks.get(iid,0)//max(1,qty))
        if batches<=0:return 0
        for iid,qty in proc.inputs.items():town.stocks[iid]=town.stocks.get(iid,0)-qty*batches
        for iid,qty in proc.outputs.items():town.stocks[iid]=town.stocks.get(iid,0)+max(1,qty*batches*bonus//100)
        return batches

    @staticmethod
    def _food_need_for_population(population:int)->int:
        population=max(0,int(population))
        return 0 if population<=0 else max(1,(population+2)//3)

    def daily_update(self, minute: int) -> None:
        day = minute // 1440
        for town in self.state.settlements.values():
            if town.population <= 0:
                continue
            assignments = self._reserve_labor(town, day)
            for proc, workers in assignments:
                self._run_process(town,proc,workers,day,minute)
            # Food is physically consumed after production, so bad harvests propagate immediately.
            represented=sum(len(h.member_uids) for h in self.state.households.values() if h.settlement_id==town.uid and h.last_consumed_minute==minute)
            aggregate_population=max(0,town.population-represented)
            food_need = self._food_need_for_population(aggregate_population)
            eaten = min(food_need, town.stocks.get("core:wheat", 0))
            town.stocks["core:wheat"] = town.stocks.get("core:wheat", 0) - eaten
            remain = food_need - eaten
            eaten2 = min(remain, town.stocks.get("core:turnip", 0))
            town.stocks["core:turnip"] = town.stocks.get("core:turnip", 0) - eaten2
            remain -= eaten2
            eaten3 = min(remain, town.stocks.get("core:meat", 0))
            town.stocks["core:meat"] = town.stocks.get("core:meat", 0) - eaten3
            shortage = food_need - eaten - eaten2 - eaten3
            old_stress = town.food_stress
            town.food_stress = max(0, min(100, town.food_stress + shortage * 3 - (2 if shortage == 0 else 0)))
            if old_stress < 60 <= town.food_stress:
                self.history.record("famine", f"Food scarcity grips {town.name}.", minute, town.region_x, town.region_y, [town.uid], salience=55)
        self.update_prices()
        self._record_market_history(minute)
        self._ensure_routes(minute)
        self._create_caravans(minute)

    def _record_market_history(self, minute: int) -> None:
        # Daily samples are intentionally bounded to roughly one in-game year.
        # This supports terminal trend graphs and economic diagnosis without
        # allowing time-series state to grow forever.
        for town in self.state.settlements.values():
            for good,price in sorted(town.prices.items()):
                rows=town.market_history.setdefault(good,[])
                rows.append([int(minute),int(price),int(town.stocks.get(good,0))])
                if len(rows)>120:del rows[:-120]

    def monthly_update(self, minute: int) -> None:
        for s in self.state.settlements.values():
            if s.food_stress < 20 and s.population < 600:
                growth=max(1,s.population//50)
                # Route centrality is a consequence of the physical transport
                # graph: connected market towns attract slightly more growth,
                # but housing still bounds exact active settlements.
                growth+=max(0,int(getattr(s,"route_centrality",0))//45)
                frontier=str(getattr(s,"frontier_status","core"))
                if frontier=="contested":
                    growth=max(0,growth-1-int(getattr(s,"border_pressure",0))//50)
                elif frontier=="frontier":
                    growth=max(0,growth-1)
                if s.housing_capacity>0:growth=min(growth,max(0,s.housing_capacity-s.population))
                s.population += max(0,growth)
            elif s.food_stress > 80:
                s.population = max(5, s.population - max(1, s.population // 40))

    def _route_opportunity(self, a, b) -> int:
        """Cheap deterministic estimate used before expensive route planning.

        A settlement should not maintain a complete directed graph to every
        other realized settlement. Nearby partners are preferred, but severe
        price/stock complementarity can pull one or two more distant markets
        into the bounded partner set.
        """
        opportunity=0
        goods=set(a.stocks)|set(b.stocks)|set(TARGET)
        for good in goods:
            surplus=max(0,a.stocks.get(good,0)-TARGET.get(good,30))
            if surplus<=0:continue
            pa=a.prices.get(good,self._price(good,a.stocks.get(good,0)))
            pb=b.prices.get(good,self._price(good,b.stocks.get(good,0)))
            opportunity=max(opportunity,surplus*max(0,pb-pa))
        return min(1000,opportunity)

    def _ensure_routes(self, minute: int) -> None:
        towns = sorted(self.state.settlements.values(), key=lambda t:t.uid)
        town_ids={t.uid for t in towns}
        if self.route_planner is not None and int(getattr(self.route_planner,"version",0))>=3:
            refresh=(town_ids!=self._route_town_ids) or not self.route_planner.active_plans() or ((minute//1440)%30==0)
            plans=self.route_planner.sync_network(towns,persist=True) if refresh else self.route_planner.active_plans()
            self._route_town_ids=town_ids
            valid={p.uid for p in plans}
            # v3 removes the old independently-planned economy route graph.
            for uid,route in list(self.state.trade_routes.items()):
                if not route.physical_route_id or route.physical_route_id not in valid:
                    self.state.trade_routes.pop(uid,None)
                    continue
                a=self.state.settlements.get(route.origin);b=self.state.settlements.get(route.destination)
                plan=self.route_planner.plan_by_uid(route.physical_route_id)
                infra=self.state.route_infrastructure.get(route.physical_route_id)
                if not a or not b or plan is None or infra is None:continue
                faction_a=self.state.factions.get(a.faction_id)
                hostile=bool(faction_a and b.faction_id in faction_a.at_war)
                merchants=a.labor_pool.get("merchant",max(1,a.population//20))
                market_capacity=max(2,(20+merchants*3)*(100-a.quarantine_level)//100)
                road_cap=160 if plan.route_class=="maintained_road" else 100 if plan.route_class=="road" else 55
                physical_capacity=0 if infra.blocked else max(1,road_cap*max(10,infra.condition)//100)
                route.capacity=min(market_capacity,physical_capacity) if physical_capacity else 0
                route.danger=min(100,int(plan.danger)+(100-infra.condition)//3+a.food_stress//5+b.food_stress//6+
                                 (45 if hostile else 0)+a.quarantine_level//5+b.quarantine_level//8+
                                 (35 if infra.blocked else 0))
                route.travel_minutes=max(180,int(plan.cost)*5)*100//max(10,infra.condition)
            return
        full_refresh=(town_ids!=self._route_town_ids) or not self.state.trade_routes or ((minute//1440)%30==0)
        if not full_refresh:
            # Daily scarcity/war changes route danger, but expensive macro path
            # geometry only rebuilds monthly or when the settlement graph changes.
            for route in self.state.trade_routes.values():
                a=self.state.settlements.get(route.origin);b=self.state.settlements.get(route.destination)
                if not a or not b:continue
                faction_a=self.state.factions.get(a.faction_id);hostile=bool(faction_a and b.faction_id in faction_a.at_war)
                route.danger=min(95,max(0,route.distance*3+a.food_stress//5+b.food_stress//6+(45 if hostile else 0)))
            return
        self._route_town_ids=town_ids
        valid:set[str]=set()
        for a in towns:
            ranked=[]
            for b in towns:
                if a.uid==b.uid:continue
                rough=abs(a.region_x-b.region_x)+abs(a.region_y-b.region_y)
                if rough>12:continue
                faction_a=self.state.factions.get(a.faction_id)
                hostile=bool(faction_a and b.faction_id in faction_a.at_war)
                opportunity=self._route_opportunity(a,b)
                # Distance remains the dominant cost; opportunity may promote a
                # complementary market, while active war strongly demotes it.
                rank=rough*100 + (500 if hostile else 0) - min(450,opportunity//4)
                ranked.append((rank,rough,b.uid,b))
            ranked.sort(key=lambda row:(row[0],row[1],row[2]))
            for _,_,_,b in ranked[:MAX_TRADE_PARTNERS]:
                route_plan=self.pathfinder.regional_path((a.region_x,a.region_y),(b.region_x,b.region_y))
                dist=route_plan.distance
                if dist>12:continue
                uid=f"route:{a.uid}>{b.uid}";valid.add(uid)
                faction_a=self.state.factions.get(a.faction_id)
                hostile=bool(faction_a and b.faction_id in faction_a.at_war)
                danger=min(95,route_plan.danger+a.food_stress//5+b.food_stress//6+(45 if hostile else 0)+a.quarantine_level//5+b.quarantine_level//8)
                merchants=a.labor_pool.get("merchant",max(1,a.population//20))
                capacity=max(2,(20+merchants*3)*(100-a.quarantine_level)//100)
                waypoints=[f"{rx},{ry}" for rx,ry in route_plan.regions]
                chunk_waypoints=[f"{cx},{cy}" for cx,cy in self.pathfinder.chunk_corridor((a.x,a.y),(b.x,b.y))]
                if uid in self.state.trade_routes:
                    r=self.state.trade_routes[uid]
                    r.distance,r.danger,r.capacity=dist,danger,capacity
                    r.waypoints=waypoints;r.travel_minutes=route_plan.travel_minutes;r.chunk_waypoints=chunk_waypoints
                else:
                    self.state.trade_routes[uid]=TradeRouteState(uid,a.uid,b.uid,dist,danger,capacity,minute,0,waypoints,route_plan.travel_minutes,chunk_waypoints)
        for uid in [uid for uid in self.state.trade_routes if uid not in valid]:
            self.state.trade_routes.pop(uid,None)

    def _create_caravans(self, minute: int) -> None:
        for route in sorted(self.state.trade_routes.values(), key=lambda r: r.uid):
            a = self.state.settlements.get(route.origin)
            b = self.state.settlements.get(route.destination)
            if not a or not b or route.capacity<=0 or route.danger >= 90 or a.quarantine_level >= 90 or b.quarantine_level >= 95:
                continue
            if any(c.origin == a.uid and c.status == "traveling" for c in self.state.caravans.values()):
                continue
            best: tuple[str, int, int] | None = None
            best_score = 0
            for good, stock in sorted(a.stocks.items()):
                surplus = stock - TARGET.get(good, 30)
                diff = b.prices.get(good, self._price(good, b.stocks.get(good, 0))) - a.prices.get(good, self._price(good, stock))
                score = surplus * diff
                if surplus > 10 and diff > 0 and score > best_score:
                    qty = min(route.capacity, max(1, surplus // 2))
                    best = (good, qty, score)
                    best_score = score
            if not best or best_score <= 20:
                continue
            good, qty, _ = best
            a.stocks[good] -= qty
            travel = route.travel_minutes or max(360, route.distance * 720)
            cargo_value = qty * a.prices.get(good, BASE_PRICE.get(good, 5))
            guards = max(0, a.labor_pool.get("guard", 0) // 3)
            uid = self.state.uid("caravan")
            self.state.caravans[uid] = CaravanState(uid=uid, origin=a.uid, destination=b.uid, goods={good:qty}, wealth=0,
                                                     depart_minute=minute, arrive_minute=minute+travel, status="traveling",
                                                     route_id=route.uid, cargo_value=cargo_value, guards=guards)
            route.last_used_minute = minute
            self.history.record("caravan_departure", f"A caravan left {a.name} for {b.name} carrying {qty} {good}.", minute, a.region_x, a.region_y, [uid,a.uid,b.uid], salience=8)
            # At most one outbound caravan per settlement per daily update.

    def process_caravans(self, minute: int) -> None:
        for c in list(self.state.caravans.values()):
            if c.status != "traveling" or c.arrive_minute > minute:
                continue
            dest = self.state.settlements.get(c.destination)
            origin = self.state.settlements.get(c.origin)
            if not dest:
                c.status = "lost"
                continue
            route = self.state.trade_routes.get(c.route_id)
            if route and route.physical_route_id and self.route_planner is not None:
                self.route_planner.record_usage(route.physical_route_id,minute,1)
            danger = route.danger if route else 20
            effective_danger = max(0, danger - c.guards * 4)
            roll = hash_u64(self.seed, "caravan-risk", c.uid) % 100
            if roll < effective_danger:
                c.status = "lost"
                if route:
                    route.danger = min(100, route.danger + 4)
                self.history.record("caravan_lost", f"A caravan from {origin.name if origin else c.origin} was lost on the road to {dest.name}.", minute, dest.region_x, dest.region_y, [c.uid], salience=45)
                continue
            revenue = 0
            for good, qty in c.goods.items():
                dest.stocks[good] = dest.stocks.get(good, 0) + qty
                revenue += qty * max(1, dest.prices.get(good, BASE_PRICE.get(good, 5)))
            paid = min(dest.wealth, revenue)
            dest.wealth -= paid
            toll=0
            if route and route.physical_route_id and self.route_planner is not None and int(getattr(self.route_planner,"version",0))>=4:
                requested_toll=min(paid,max(0,int(getattr(route,"toll_copper",0))))
                payer_faction=getattr(origin,"faction_id","") if origin is not None else ""
                toll=self.route_planner.collect_toll(route.physical_route_id,requested_toll,payer_faction)
            if origin:
                origin.wealth += max(0,paid-toll)
            c.wealth = max(0,paid-toll)
            c.toll_paid = int(getattr(c,"toll_paid",0))+toll
            c.status = "arrived"
            if route:
                route.traffic += 1
                route.danger = max(0, route.danger - 1)
            toll_note=f"; {toll}c paid in road tolls" if toll else ""
            self.history.record("trade", f"A caravan reached {dest.name}; cargo sold for {paid}c{toll_note}.", minute, dest.region_x, dest.region_y, [c.uid,dest.uid], salience=12)
        # Completed caravan objects are transient logistics state. Their causal
        # outcome already lives in route traffic, settlement ledgers and history.
        cutoff=minute-30*1440
        for uid,c in list(self.state.caravans.items()):
            if c.status!="traveling" and c.arrive_minute<cutoff:self.state.caravans.pop(uid,None)
        self.update_prices()

    def trade_price(self, settlement_id: str, item_id: str, buy: bool) -> int:
        s = self.state.settlements[settlement_id]
        p = s.prices.get(item_id, self._price(item_id, s.stocks.get(item_id, 0)))
        return max(1, (p * 115)//100 if buy else (p * 85)//100)


    def record_transaction(
        self,
        settlement_id: str,
        kind: str,
        actor_uid: str,
        counterparty_uid: str,
        *,
        copper_value: int,
        minute: int,
        offered: dict[str,int] | None = None,
        requested: dict[str,int] | None = None,
    ) -> MarketTransactionState:
        town=self.state.settlements[settlement_id]
        self.ensure_currency(town)
        uid=self.state.uid("market")
        row=MarketTransactionState(
            uid=uid,settlement_id=settlement_id,kind=str(kind),
            actor_uid=str(actor_uid),counterparty_uid=str(counterparty_uid),
            currency_id=town.currency_id,copper_value=max(0,int(copper_value)),
            minute=int(minute),offered=dict(offered or {}),requested=dict(requested or {}),
        )
        self.state.market_transactions[uid]=row
        if len(self.state.market_transactions)>400:
            oldest=sorted(
                self.state.market_transactions.values(),
                key=lambda x:(x.minute,x.uid),
            )[:-400]
            for old in oldest:
                self.state.market_transactions.pop(old.uid,None)
        return row

    def currency_quote(self, settlement_id: str, copper_value: int) -> tuple[str,int]:
        town=self.state.settlements[settlement_id];self.ensure_currency(town)
        units=max(1,(max(0,int(copper_value))*100 + town.currency_value-1)//max(1,town.currency_value))
        return town.currency_name,units

    def barter_value(self, settlement_id: str, goods: dict[str,int], *, offered: bool) -> int:
        town=self.state.settlements[settlement_id]
        total=0
        for item_id,qty in goods.items():
            if qty<=0:continue
            total += self.trade_price(settlement_id,item_id,buy=not offered)*int(qty)
        return total

    def barter_balance(self, settlement_id: str, offered: dict[str,int], requested: dict[str,int]) -> int:
        return self.barter_value(settlement_id,offered,offered=True)-self.barter_value(settlement_id,requested,offered=False)

    def record_theft(
        self,
        settlement_id: str,
        thief_uid: str,
        victim_uid: str,
        item_id: str,
        quantity: int,
        minute: int,
        *,
        witnessed: bool,
        property_id: str = "",
        source_kind: str = "",
        witness_uids=(),
    ) -> TheftRecordState:
        qty=max(1,int(quantity))
        value=max(1,self.trade_price(settlement_id,item_id,buy=True)*qty)
        uid=self.state.uid("theft")
        row=TheftRecordState(
            uid,settlement_id,thief_uid,victim_uid,item_id,qty,value,int(minute),
            bool(witnessed),False,str(property_id),str(source_kind),
            sorted({str(value) for value in witness_uids if value}),
        )
        self.state.theft_records[uid]=row
        self.record_transaction(
            settlement_id,"theft",thief_uid,victim_uid or settlement_id,
            copper_value=value,minute=minute,offered={},requested={item_id:qty},
        )
        thief=self.state.npcs.get(thief_uid);victim=self.state.npcs.get(victim_uid)
        if thief is not None:
            thief.memories.append({"minute":int(minute),"type":"theft","subject":victim_uid or settlement_id,"salience":20,"valence":-10})
            thief.memories=thief.memories[-40:]
        if witnessed and victim is not None:
            rel=victim.relationships.setdefault(thief_uid,{"affection":0,"trust":0,"fear":0,"respect":0,"obligation":0,"familiarity":0})
            rel["trust"]=max(-100,rel["trust"]-25);rel["affection"]=max(-100,rel["affection"]-12)
            rel["familiarity"]=min(100,rel["familiarity"]+8)
        for witness_uid in row.witness_uids:
            witness=self.state.npcs.get(witness_uid)
            if witness is None:
                continue
            rel=witness.relationships.setdefault(thief_uid,{"affection":0,"trust":0,"fear":0,"respect":0,"obligation":0,"familiarity":0})
            rel["trust"]=max(-100,int(rel.get("trust",0))-15)
            rel["respect"]=max(-100,int(rel.get("respect",0))-8)
            rel["familiarity"]=min(100,int(rel.get("familiarity",0))+6)
        return row

    def npc_steal_food(self, npc, town, minute: int) -> bool:
        foods=[iid for iid in ("core:wheat","core:turnip","core:meat") if town.stocks.get(iid,0)>0]
        if not foods:return False
        item=min(foods,key=lambda iid:(self.trade_price(town.uid,iid,buy=True),iid))
        town.stocks[item]-=1
        guards=sum(1 for n in self.state.npcs.values() if n.alive and n.settlement_id==town.uid and n.occupation=="guard")
        witnessed=(hash_u64(self.seed,"npc-theft-witness",npc.uid,minute//60)%100)<min(90,20+guards*18)
        self.record_theft(town.uid,npc.uid,town.uid,item,1,minute,witnessed=witnessed)
        npc.hunger=max(0,npc.hunger-40)
        npc.needs["safety"]=min(100,npc.needs.get("safety",0)+(35 if witnessed else 10))
        return True
