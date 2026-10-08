"""A finite, disposable NPC job laboratory, independent of the game launcher.

The scenario supplies explicit starting geography, stores and assignments. All
planning, movement, station reservations, production, hauling and paid trade run
through the existing game systems. There is no aggregate production, save file,
world generation or presentation clock here. Snapshots are detached read models.
"""
from __future__ import annotations

from collections import Counter, deque
from copy import deepcopy
from dataclasses import dataclass, field

from worldseed.config import DATA_DIR, SIMULATION_TICK_MINUTES
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.systems.activities import ActivitySystem
from worldseed.systems.ai import NPCSystem
from worldseed.systems.economy import EconomySystem
from worldseed.systems.environment import EnvironmentSystem
from worldseed.systems.history import HistorySystem
from worldseed.systems.npc_commerce import NPCCommerceSystem
from worldseed.systems.npc_home_storage import NPCStorageAccess
from worldseed.systems.physical_goods import SettlementPhysicalGoodsSystem
from worldseed.systems.professions import SettlementProfessionSystem
from worldseed.systems.resources import FeatureView
from worldseed.systems.state import (
    ContainerState, CropPlot, LaborReservationState, LivingWorldState,
    NPCState, SettlementState, SoilState, pos_key,
)


SCENARIOS = {
    "supply_chain": "Lumberjacks harvest trees, sell wood, and supply carpenters.",
    "workshops": "Supplied craft stations and a wheat field exercise varied jobs.",
    "scarcity": "Crafters lack real inputs and must wait without making goods.",
    "blocked_path": "A wall separates a carpenter's supplies from the workbench.",
    "station_contention": "Several carpenters compete for one reserved workbench.",
}
MAX_MINUTES = 7 * 1440
START_MINUTE = 7 * 60
BOUNDS = (-32, -24, 32, 24)
HISTORY_LIMIT = 100


@dataclass(frozen=True)
class LabPiece:
    uid: str
    piece_id: str
    structure_plan_id: str
    x: int
    y: int
    role: str = "station"


@dataclass
class LabParcel:
    uid: str
    cells: list[tuple[int, int]]
    kind: str = "farm"
    purpose: str = "field"
    crop_id: str = "core:wheat"


@dataclass
class LabPlan:
    """Explicit finite scenario plan, consumed by normal activity affordances."""
    pieces: list[LabPiece] = field(default_factory=list)
    parcels: list[LabParcel] = field(default_factory=list)
    structures: tuple = ()
    roads: tuple = ()


class LabWorld:
    """Bounded passability authority; walls and furniture are physical obstacles."""

    def __init__(self, bounds=BOUNDS):
        self.bounds = tuple(bounds)
        self.blocked: set[tuple[int, int]] = set()

    def is_passable(self, pos: WorldPos) -> bool:
        xmin, ymin, xmax, ymax = self.bounds
        return (pos.z == 0 and xmin <= pos.x <= xmax and ymin <= pos.y <= ymax
                and (pos.x, pos.y) not in self.blocked)


class LabPhysicalization:
    """Read-only projection of the lab plan through game system query contracts."""

    def __init__(self, world: LabWorld, plan: LabPlan, town_uid: str):
        self.world, self.plan, self.town_uid = world, plan, town_uid
        self.destinations: dict[str, WorldPos] = {}

    def skeleton_for(self, settlement_id):
        return self.plan if settlement_id == self.town_uid else None

    def passable(self, pos, world_passable=True):
        return bool(world_passable and self.world.is_passable(pos))

    def destination_for(self, structure_id, room_id=""):
        return self.destinations.get(str(structure_id))

    def destination_for_function(self, settlement_id, functions):
        return WorldPos(0, 0, 0) if settlement_id == self.town_uid else None

    def cell_at(self, pos):
        return None

    def crossing_at(self, pos):
        return None


class LabResources:
    """Finite starting trees sharing the real persistent depletion authority.

    Trees do not regrow in this short lab. Exhaustion is visible and meaningful;
    the runner never refills depleted resources or any inventory.
    """

    def __init__(self, state):
        self.state = state
        self.trees: dict[tuple[int, int], str] = {}
        self.revision = 0

    def feature_at(self, pos, minute=None):
        resource_id = self.trees.get((pos.x, pos.y)) if pos.z == 0 else None
        if resource_id is None:
            return None
        depleted = pos_key(pos.x, pos.y, pos.z) in self.state.resource_depletion
        return FeatureView(resource_id, "stump" if depleted else "mature")


class ObservedProfessions(SettlementProfessionSystem):
    """Observe existing completion methods without replacing their behavior."""

    def __init__(self, *args, lab, **kwargs):
        super().__init__(*args, **kwargs)
        self.lab = lab

    def complete_process(self, npc, town, task, minute):
        success = super().complete_process(npc, town, task, minute)
        if success:
            self.lab.produced.update(task.get("outputs", {}))
            self.lab.consumed.update(task.get("inputs", {}))
            self.lab.batches[str(task.get("process_id", ""))] += 1
        return success

    def complete_resource(self, npc, town, task, minute):
        before = Counter(npc.inventory)
        success = super().complete_resource(npc, town, task, minute)
        if success:
            self.lab.gathered.update(Counter(npc.inventory) - before)
        return success

    def complete_farm(self, npc, town, task, minute):
        before = Counter(npc.inventory)
        success = super().complete_farm(npc, town, task, minute)
        if success:
            after = Counter(npc.inventory)
            self.lab.gathered.update(after - before)
            self.lab.consumed.update(before - after)
        return success


class ObservedNPCSystem(NPCSystem):
    """Account for actual meal completion, including hourly boundary execution."""

    def __init__(self, *args, lab, **kwargs):
        super().__init__(*args, **kwargs)
        self.lab = lab

    def _execute_task(self, npc, town, minute, player_pos, *, allow_interior_activity=False):
        task = npc.tasks[0] if npc.tasks else {}
        eating = task.get("kind") == "perform" and task.get("action") == "eat"
        before = Counter(town.stocks) if eating else None
        super()._execute_task(npc, town, minute, player_pos,
                              allow_interior_activity=allow_interior_activity)
        if eating:
            # This synchronous action has no intervening purchase or craft by
            # another actor. Observe the owning system rather than infer a meal
            # from stock differences across an entire multi-actor tick.
            self.lab.consumed.update(before - Counter(town.stocks))


def _bounded_integer(value, name, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")
    return value


class NPCJobLab:
    """Reusable headless lab. ``workers`` is the worker count per tested job.

    ``step`` advances fixed game ticks; ``run`` accepts minutes divisible by the
    fixed tick duration. Both return a snapshot. A lab runs at most seven game
    days; create a fresh lab to repeat a scenario. No game save is read or written.
    """

    def __init__(self, scenario="supply_chain", seed="npc-lab", workers=1):
        if scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario {scenario!r}; choose from {', '.join(SCENARIOS)}")
        if not isinstance(seed, str) or not seed or len(seed) > 128:
            raise ValueError("seed must be a nonempty string of at most 128 characters")
        _bounded_integer(workers, "workers", 1, 8)
        self.scenario, self.seed, self.workers = scenario, seed, workers
        self.registry = ContentRegistry.load(DATA_DIR)
        self.state = LivingWorldState(clock_minute=START_MINUTE)
        self.town = SettlementState(
            uid="settlement:npc-lab", name="NPC Job Lab", region_x=0, region_y=0,
            x=0, y=0, population=2400, culture_id="", religion_id="", faction_id="",
            wealth=100000, stocks={"core:bread": 500},
        )
        self.state.settlements[self.town.uid] = self.town
        self.world = LabWorld()
        self.plan = LabPlan()
        self.physicalization = LabPhysicalization(self.world, self.plan, self.town.uid)
        self.resources = LabResources(self.state)
        self.history = HistorySystem(self.state)
        seed_bytes = seed.encode("utf-8")
        self.economy = EconomySystem(self.state, self.registry, seed_bytes, self.history)
        self.activities = ActivitySystem(self.state, self.registry, self.physicalization, self.world)
        self.goods = SettlementPhysicalGoodsSystem(self.state, self.registry)
        self.produced, self.consumed, self.gathered, self.batches = (Counter() for _ in range(4))
        self.professions = ObservedProfessions(
            self.state, self.registry, seed_bytes, self.world, self.physicalization,
            self.activities, self.goods, self.resources, lab=self,
        )
        self.storage_access = NPCStorageAccess(self.state, self.world, self.physicalization, None, self.goods)
        self.commerce = NPCCommerceSystem(self.state, self.registry, self.economy, self.goods,
                                          self.physicalization, self.storage_access)
        self.ai = ObservedNPCSystem(self.state, seed_bytes, self.history, self.world, lab=self)
        self.ai.attach_activity_system(self.activities)
        self.ai.attach_profession_system(self.professions)
        self.ai.attach_economy(self.economy)
        self.ai.settlement_physicalization = self.physicalization
        self.economy.attach_physical_labor_authority(self.professions)
        for system in (self.ai, self.professions):
            system.storage_access = self.storage_access
            system.commerce = self.commerce
        # Reuse crop/weather rules against bounded lab fields, with no worldgen.
        self.environment = EnvironmentSystem(self.state, self.registry, seed_bytes, self.history)
        self.events = deque(maxlen=HISTORY_LIMIT)
        self.completed_activities = self.transactions = self.transfers = 0
        self._stalls: dict[str, int] = {}
        self._assignments: dict[str, str] = {}
        self._build_scenario()
        self._prepare_assignments()
        self.ai.rebuild_spatial_index()
        self.initial_goods = self._goods_totals()
        self.initial_cash = self._cash_total()
        self._event(f"Started {scenario}: {SCENARIOS[scenario]}")

    @property
    def minute(self):
        return self.state.clock_minute

    def _event(self, message):
        self.events.append({"minute": self.minute, "message": str(message)})

    def _add_station(self, property_id, piece_id, x, y):
        uid = f"fixture:{property_id}:{piece_id}:{len(self.plan.pieces)}"
        self.plan.pieces.append(LabPiece(uid, piece_id, property_id, x, y))
        self.world.blocked.add((x, y))

    def _add_container(self, uid, name, property_id, x, y, owner, items=None):
        container = ContainerState(
            uid=uid, name=name, x=x, y=y, z=0, owner=owner,
            capacity_mass_g=2000000, capacity_volume_ml=2000000,
            kind="property", property_id=property_id, settlement_id=self.town.uid,
            items=dict(items or {}), access="private",
        )
        self.state.containers[uid] = container
        self.world.blocked.add((x, y))
        return container

    def _job_group(self, occupation, process_id, x, y, count=None, supplied=False,
                   home_x=None, home_y=None):
        count = self.workers if count is None else count
        property_id = f"work:{occupation}"
        self.physicalization.destinations[property_id] = WorldPos(x - 1, y, 0)
        process = self.registry.settlement_processes[process_id]
        tags = {"forge"} if occupation == "smith" else set(self.professions.WORKSHOP_TAGS.get(occupation, ()))
        stations = sorted(
            (p for p in self.registry.settlement_pieces.values()
             if p.workplace_role == occupation and tags.intersection(p.tags)),
            key=lambda p: ("dev52_furniture_variant" in p.tags, p.id),
        )
        if stations:
            self._add_station(property_id, stations[0].id, x, y)
        if occupation == "smith":
            self._add_station(property_id, "core:anvil_piece", x + 3, y)
        # A finite supplied input buffer, never refilled by the runner.
        inputs = {iid: qty * 30 * count for iid, qty in process.inputs.items()} if supplied else {}
        self._add_container(f"store:{property_id}", f"{occupation.title()} work stores", property_id,
                            x - 3, y + 2, self.town.uid, inputs)
        hx, hy = (x + 1 if home_x is None else home_x), (y + 5 if home_y is None else home_y)
        for index in range(count):
            uid = f"npc:{occupation}:{index + 1}"
            home_id = f"home:{occupation}:{index + 1}"
            cx, cy = hx + index % 4, hy + index // 4 * 2
            self.physicalization.destinations[home_id] = WorldPos(cx, cy - 1, 0)
            npc = NPCState(
                uid=uid, name=f"{occupation.title()} {index + 1}", age=30,
                occupation=occupation, traits=["patient"], x=cx, y=cy - 1, z=0,
                settlement_id=self.town.uid, faction_id="", home_id=home_id,
                workplace_id=property_id, wealth=2000, needs={"social": 0, "purpose": 0},
            )
            self.state.npcs[uid] = npc
            self._assignments[uid] = process_id
            self.professions.ensure_profile(npc)
            self._add_container(f"store:{home_id}", f"{npc.name} home stores", home_id,
                                cx, cy, uid)
        return property_id

    def _build_scenario(self):
        if self.scenario == "supply_chain":
            self._job_group("lumberjack", "core:logging", -16, -8)
            self._job_group("carpenter", "core:woodcraft", 12, -8)
            for y in (-19, -17, -15):
                for x in (-25, -23, -21, -19, -17, -15):
                    self.resources.trees[x, y] = "core:oak_tree"
                    self.world.blocked.add((x, y))
        elif self.scenario == "workshops":
            # Catalogue processes and fixture tags determine actual recipes.
            jobs = [
                ("smith", "core:iron_smelt"), ("cook", "core:hearth_roast"),
                ("miller", "core:grain_milling"), ("baker", "core:bread_baking"),
                ("weaver", "core:cloth_weaving"), ("tanner", "core:leather_tanning"),
                ("potter", "core:pottery_work"), ("brewer", "core:small_ale_brewing"),
                ("healer", "core:town_tonic"), ("mason", "core:masonry_work"),
                ("fisher", "core:fish_smoking"), ("butcher", "core:butcher_portions"),
                ("farmer", "core:field_wheat"), ("carpenter", "core:woodcraft"),
            ]
            for index, (occupation, process_id) in enumerate(jobs):
                x, y = -24 + (index % 5) * 12, -18 + (index // 5) * 14
                self._job_group(occupation, process_id, x, y, supplied=True)
            field = [(x, y) for y in range(14, 17) for x in range(-3, 1)]
            self.plan.parcels.append(LabParcel("field:wheat", field))
            for x, y in field:
                key = pos_key(x, y, 0)
                self.state.crops[key] = CropPlot("core:wheat", x, y, 0, 0, mature=True)
                self.state.soils[key] = SoilState(x, y, 0)
            farmer_store = self.state.containers["store:work:farmer"]
            farmer_store.items["core:wheat_seed"] = 20 * self.workers
        elif self.scenario == "scarcity":
            self._job_group("carpenter", "core:woodcraft", -12, -8)
            self._job_group("smith", "core:iron_smelt", 12, -8)
        elif self.scenario == "blocked_path":
            self._job_group("carpenter", "core:woodcraft", 12, -8, supplied=True,
                            home_x=-12, home_y=2)
            store = self.state.containers["store:work:carpenter"]
            self.world.blocked.discard((store.x, store.y))
            store.x, store.y = -16, 4
            self.world.blocked.add((store.x, store.y))
            self.world.blocked.update((4, y) for y in range(BOUNDS[1], BOUNDS[3] + 1))
        elif self.scenario == "station_contention":
            self._job_group("carpenter", "core:woodcraft", 4, -8,
                            count=max(2, self.workers), supplied=True)

    def _prepare_assignments(self):
        """Choose the scenario's experiments, using the existing labor state.

        The lab fixes which catalogue recipe is under test. Assignments are real
        LaborReservationState rows; calling normal daily economy production would
        introduce anonymous labor and obscure the individual experiment.
        """
        day = self.minute // 1440
        groups = {}
        for uid, process_id in self._assignments.items():
            groups.setdefault(process_id, []).append(uid)
            npc = self.state.npcs[uid]
            if npc.work_assignment_day != day:
                npc.work_hours_today = 0
            npc.assigned_process_id, npc.work_assignment_day = process_id, day
        for process_id, uids in sorted(groups.items()):
            proc = self.registry.settlement_processes[process_id]
            uid = f"labor:{self.town.uid}:{process_id}"
            self.state.labor_reservations[uid] = LaborReservationState(
                uid, self.town.uid, process_id, proc.occupation,
                len(uids) * max(1, proc.workers), day, True, sorted(uids),
            )

    def _cash_total(self):
        return self.town.wealth + sum(n.wealth for n in self.state.npcs.values())

    def _goods_totals(self):
        totals = Counter(self.town.stocks)
        for npc in self.state.npcs.values():
            totals.update(npc.inventory)
        for container in self.state.containers.values():
            totals.update(container.items)
        for pile in self.state.ground_piles.values():
            totals.update(pile.items)
        return {iid: qty for iid, qty in sorted(totals.items()) if qty}

    def _tick(self):
        prior_reservations = {r.uid: r.status for r in self.state.activity_reservations.values()}
        prior_transactions = set(self.state.market_transactions)
        prior_transfers = set(self.state.physical_goods_transfers)
        prior_npcs = {uid: (npc.x, npc.y, npc.goal, deepcopy(npc.tasks[0]) if npc.tasks else {})
                      for uid, npc in self.state.npcs.items()}
        self.state.clock_minute += int(SIMULATION_TICK_MINUTES)
        if self.minute % 1440 == 0:
            self._prepare_assignments()
        if self.minute % 60 == 0:
            self.environment.hourly_update(self.minute)
            self.ai.decision_update(self.minute, WorldPos(0, 0, 0))
        self.ai.tick_update(self.minute, WorldPos(0, 0, 0))
        for uid, npc in self.state.npcs.items():
            x, y, goal, task = prior_npcs[uid]
            moving = task.get("kind") == "move"
            self._stalls[uid] = self._stalls.get(uid, 0) + 1 if moving and (x, y) == (npc.x, npc.y) else 0
            if goal != npc.goal:
                self._event(f"{npc.name} chose {npc.goal}")
        for row in self.state.activity_reservations.values():
            if row.status == "completed" and prior_reservations.get(row.uid) != "completed":
                self.completed_activities += 1
                npc = self.state.npcs.get(row.actor_uid)
                self._event(f"{npc.name if npc else row.actor_uid} completed {row.activity} ({row.phase})")
        for uid, row in self.state.market_transactions.items():
            if uid not in prior_transactions:
                self.transactions += 1
                self._event(f"{row.actor_uid}: {row.kind}, {row.copper_value} cash")
        self.transfers += sum(uid not in prior_transfers for uid in self.state.physical_goods_transfers)
        # Completed reservations are audit history, never goods or current work.
        completed = [uid for uid, row in self.state.activity_reservations.items()
                     if row.status in {"completed", "cancelled"}
                     and not any(t.get("reservation_uid") == uid
                                 for n in self.state.npcs.values() for t in n.tasks)]
        for uid in completed[:-200]:
            self.state.activity_reservations.pop(uid)
        self.state.history[:] = self.state.history[-HISTORY_LIMIT:]

    def step(self, ticks=1):
        _bounded_integer(ticks, "ticks", 0, MAX_MINUTES // SIMULATION_TICK_MINUTES)
        if self.minute - START_MINUTE + ticks * SIMULATION_TICK_MINUTES > MAX_MINUTES:
            raise ValueError("a lab run is limited to seven game days; reset to run again")
        for _ in range(ticks):
            self._tick()
        return self.snapshot()

    def run(self, minutes):
        _bounded_integer(minutes, "minutes", 0, MAX_MINUTES)
        if minutes % SIMULATION_TICK_MINUTES:
            raise ValueError(f"minutes must be divisible by the {SIMULATION_TICK_MINUTES}-minute simulation tick")
        return self.step(minutes // SIMULATION_TICK_MINUTES)

    def _warnings(self):
        warnings = []
        if self._cash_total() != self.initial_cash:
            warnings.append("Cash conservation failed")
        inventories = [self.town.stocks] + [n.inventory for n in self.state.npcs.values()]
        inventories += [c.items for c in self.state.containers.values()]
        inventories += [p.items for p in self.state.ground_piles.values()]
        if any(qty < 0 for items in inventories for qty in items.values()):
            warnings.append("Negative goods balance")
        if self.town.wealth < 0 or any(n.wealth < 0 for n in self.state.npcs.values()):
            warnings.append("Negative cash balance")
        occupied = set()
        for row in self.state.activity_reservations.values():
            if row.status not in {"reserved", "active"} or row.expires_minute < self.minute:
                continue
            if row.target_uid in occupied:
                warnings.append(f"Duplicate station reservation: {row.target_uid}")
            occupied.add(row.target_uid)
        totals = self._goods_totals()
        expected = Counter(self.initial_goods)
        expected.update(self.produced)
        expected.update(self.gathered)
        expected.subtract(self.consumed)
        for iid in sorted(set(totals) | set(expected)):
            if totals.get(iid, 0) != expected.get(iid, 0):
                warnings.append(f"Goods conservation failed: {iid}")
        for npc in self.state.npcs.values():
            if not self.world.is_passable(WorldPos(npc.x, npc.y, npc.z)):
                warnings.append(f"Actor on blocked/outside cell: {npc.name}")
        return warnings

    def _diagnostics(self):
        # Unreachable paths are deliberate in one experiment. Keep explanatory
        # conditions visible without classifying them as conservation failures.
        return [f"No path progress for at least one hour: {npc.name}"
                for npc in self.state.npcs.values() if self._stalls.get(npc.uid, 0) >= 12]

    @staticmethod
    def _task_label(npc):
        if not npc.tasks:
            return "Choosing next goal"
        task = npc.tasks[0]
        if task.get("kind") == "move":
            return f"Walk to ({task.get('x')}, {task.get('y')})"
        if task.get("kind") == "wait":
            return f"Wait: {task.get('reason', 'work')}"
        return str(task.get("action") or task.get("kind", ""))

    def snapshot(self):
        """Inspect without executing work, cleaning reservations or changing state."""
        npcs = [dict(
            uid=n.uid, name=n.name, occupation=n.occupation, x=n.x, y=n.y, z=n.z,
            goal=n.goal, task=self._task_label(n), tasks=n.tasks, inventory=n.inventory,
            skills=n.skills, needs=n.needs, hunger=n.hunger, thirst=n.thirst,
            rest=n.rest, wealth=n.wealth, workplace_id=n.workplace_id, home_id=n.home_id,
            process_id=n.assigned_process_id,
        ) for n in self.state.npcs.values()]
        fixtures = [dict(uid=p.uid, x=p.x, y=p.y,
                         label=self.registry.settlement_pieces[p.piece_id].name,
                         piece_id=p.piece_id) for p in self.plan.pieces]
        containers = [dict(uid=c.uid, name=c.name, x=c.x, y=c.y, items=c.items,
                           property_id=c.property_id) for c in self.state.containers.values()]
        trees = [dict(x=x, y=y, stage=self.resources.feature_at(WorldPos(x, y, 0)).stage)
                 for x, y in sorted(self.resources.trees)]
        reservations = [dict(uid=r.uid, actor_uid=r.actor_uid, target_uid=r.target_uid,
                             status=r.status, started_minute=r.started_minute,
                             duration_minutes=r.duration_minutes, expires_minute=r.expires_minute)
                        for r in self.state.activity_reservations.values()]
        crops = [dict(x=c.x, y=c.y, crop_id=c.crop_id, growth=c.growth,
                      mature=c.mature, moisture=c.moisture, health=c.health)
                 for c in self.state.crops.values()]
        piles = [dict(x=p.x, y=p.y, z=p.z, items=p.items)
                 for p in self.state.ground_piles.values()]
        return deepcopy(dict(
            minute=self.minute, scenario=self.scenario, seed=self.seed, workers=self.workers,
            bounds=list(self.world.bounds), blocked=[list(p) for p in sorted(self.world.blocked)],
            fixtures=fixtures, trees=trees, crops=crops, piles=piles, npcs=npcs, containers=containers,
            market=dict(stocks=self.town.stocks, wealth=self.town.wealth), reservations=reservations,
            metrics=dict(completed_activities=self.completed_activities,
                         transactions=self.transactions, transfers=self.transfers,
                         goods_totals=self._goods_totals(), initial_goods=self.initial_goods,
                         produced=dict(self.produced), consumed=dict(self.consumed),
                         gathered=dict(self.gathered), batches=dict(self.batches),
                         cash_total=self._cash_total(), cash_delta=self._cash_total()-self.initial_cash,
                         warnings=self._warnings(), diagnostics=self._diagnostics()), events=list(self.events),
        ))
