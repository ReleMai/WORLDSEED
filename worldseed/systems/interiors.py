"""Continuous indoor collision and stable building portals.

Layouts are created only by explicit entry/preparation. All inspection methods
read existing plans. Exterior geography, capacities and fixture goods remain
owned by the existing physical plan and ledgers.
"""
from __future__ import annotations

from collections import deque
from math import isqrt

from worldseed.core.coords import WorldPos, split_world
from worldseed.core.rng import hash_u64
from worldseed.entities.components import Position, Vitals
from worldseed.systems.interior_state import (
    ACTOR_RADIUS, UNIT, InteriorActor, InteriorFurniture, InteriorPlan,
    InteriorRect, InteriorRoom,
)


def furniture_size(piece_id: str) -> tuple[int, int]:
    if "bed" in piece_id:
        return 950, 1450
    if "table" in piece_id:
        return 1150, 750
    if "chest" in piece_id or "storage" in piece_id:
        return 850, 650
    return 750, 750


def build_interior(structure, door, source_rooms=(), pieces=()) -> InteriorPlan:
    """Derive an expanded room arrangement from one stable building identity."""
    cells = structure.footprint or [(door.x, door.y)]
    span_x = max(x for x, _ in cells) - min(x for x, _ in cells) + 1
    span_y = max(y for _, y in cells) - min(y for _, y in cells) + 1
    width = max(10000, min(24000, span_x * 1800))
    height = max(10000, min(20000, span_y * 1800))
    plan = InteriorPlan(
        "interior:" + structure.uid, structure.uid, door.uid, door.x, door.y,
        door.z, width, height, structure.function.replace("_", " ").title(),
        structure.function, door.owner_uid, entry_x=width // 2, entry_y=height - 700,
    )
    # A wide shared hall connects every room. Partitions have real gaps rather
    # than door decoration on an impermeable wall.
    inset, thickness = 250, 180
    hall_y = height - 2800
    plan.rooms.append(InteriorRoom(plan.uid + ":hall", "Common hall", InteriorRect(inset, hall_y, width - 2 * inset, height - hall_y - inset)))
    plan.walls = [
        InteriorRect(0, 0, width, thickness), InteriorRect(0, 0, thickness, height),
        InteriorRect(width - thickness, 0, thickness, height), InteriorRect(0, height - thickness, width, thickness),
    ]
    room_count = max(2, min(4, len(source_rooms)))
    room_width = (width - 2 * inset) // room_count
    ordered_rooms = sorted(source_rooms, key=lambda r: r.uid)
    for index in range(room_count):
        left = inset + index * room_width
        right = width - inset if index == room_count - 1 else left + room_width
        source = ordered_rooms[index] if index < len(ordered_rooms) else None
        name = source.kind.replace("_", " ").title() if source else ("Sleeping room" if index == 0 else "Living room")
        room = InteriorRoom(source.uid if source else plan.uid + f":room:{index}", name, InteriorRect(left, inset, right - left, hall_y - inset))
        plan.rooms.append(room)
        if index:
            plan.walls.append(InteriorRect(left - thickness // 2, inset, thickness, hall_y - inset))
        gap = min(1400, room_width // 2)
        centre = (left + right) // 2
        plan.walls.extend([
            InteriorRect(left, hall_y - thickness // 2, max(0, centre - gap // 2 - left), thickness),
            InteriorRect(centre + gap // 2, hall_y - thickness // 2, max(0, right - centre - gap // 2), thickness),
        ])
    fixture_rooms = {uid: i for i, room in enumerate(ordered_rooms) for uid in room.fixture_ids}
    counters: dict[int, int] = {}
    for piece in sorted(pieces, key=lambda p: p.uid):
        if piece.role not in {"fixture", "tile_decor"}:
            continue
        index = min(room_count - 1, fixture_rooms.get(piece.uid, len(plan.furniture) % room_count))
        room = plan.rooms[index + 1]
        ordinal = counters.get(index, 0)
        counters[index] = ordinal + 1
        w, h = furniture_size(piece.piece_id)
        # Deliberately fractional placements, with generous circulation space.
        x = room.rect.x + 425 + (ordinal % 2) * (w + 450)
        y = room.rect.y + 425 + (ordinal // 2) * 1950
        row = InteriorFurniture(piece.uid, piece.piece_id, x, y, w, h, door.owner_uid, piece.uid, piece.role == "fixture")
        if placement_clear(plan, row.rect) and y + h < hall_y - 500:
            plan.furniture.append(row)
    return plan


def position_clear(plan: InteriorPlan, x: int, y: int, radius: int = ACTOR_RADIUS) -> bool:
    if x - radius < 0 or y - radius < 0 or x + radius > plan.width or y + radius > plan.height:
        return False
    actor = InteriorRect(x - radius, y - radius, 2 * radius, 2 * radius)
    return not any(actor.overlaps(w) for w in plan.walls) and not any(
        f.solid and actor.overlaps(f.rect) for f in plan.furniture
    )


def move_actor(plan: InteriorPlan, actor: InteriorActor, dx: int, dy: int) -> bool:
    """Axis sliding with small bounded substeps prevents thin-wall tunnelling."""
    dx, dy = max(-4000, min(4000, int(dx))), max(-4000, min(4000, int(dy)))
    count = max(1, (max(abs(dx), abs(dy)) + 89) // 90)
    origin = actor.x, actor.y
    previous_x = previous_y = 0
    for i in range(1, count + 1):
        cumulative_x, cumulative_y = dx * i // count, dy * i // count
        step_x, step_y = cumulative_x - previous_x, cumulative_y - previous_y
        previous_x, previous_y = cumulative_x, cumulative_y
        if position_clear(plan, actor.x + step_x, actor.y):
            actor.x += step_x
        if position_clear(plan, actor.x, actor.y + step_y):
            actor.y += step_y
    return origin != (actor.x, actor.y)


def placement_clear(plan: InteriorPlan, rect: InteriorRect, ignore_uid: str = "") -> bool:
    if rect.w <= 0 or rect.h <= 0 or rect.x < 250 or rect.y < 250 or rect.x + rect.w > plan.width - 250 or rect.y + rect.h > plan.height - 250:
        return False
    if any(rect.overlaps(w) for w in plan.walls):
        return False
    if any(f.uid != ignore_uid and rect.overlaps(f.rect) for f in plan.furniture):
        return False
    exit_apron = InteriorRect(plan.entry_x - 650, plan.entry_y - 650, 1300, 1300)
    return not rect.overlaps(exit_apron)


def room_at(plan: InteriorPlan, x: int, y: int) -> InteriorRoom | None:
    return next((room for room in plan.rooms if room.rect.contains(x, y)), None)


def exit_reachable(plan: InteriorPlan, x: int, y: int) -> bool:
    """Bounded conservative visibility graph; no world/grid queries are used."""
    nodes = [(x, y), (plan.entry_x, plan.entry_y)]
    obstacles = plan.walls + [f.rect for f in plan.furniture if f.solid]
    clearance = ACTOR_RADIUS + 25
    for rect in obstacles:
        for px in (rect.x - clearance, rect.x + rect.w + clearance):
            for py in (rect.y - clearance, rect.y + rect.h + clearance):
                if position_clear(plan, px, py):
                    nodes.append((px, py))
    # Household plans are bounded; de-duplicate corner nodes before graph work.
    nodes = list(dict.fromkeys(nodes))[:180]
    seen, queue = {0}, deque([0])
    while queue:
        index = queue.popleft()
        if index == 1:
            return True
        ax, ay = nodes[index]
        for other, (bx, by) in enumerate(nodes):
            if other in seen:
                continue
            steps = max(1, (max(abs(bx - ax), abs(by - ay)) + 99) // 100)
            if all(position_clear(plan, ax + (bx - ax) * i // steps, ay + (by - ay) * i // steps) for i in range(steps + 1)):
                seen.add(other)
                queue.append(other)
    return False


class InteriorSystem:
    def __init__(self, sim):
        self.sim = sim
        self.state = sim.state
        self._actors_by_space: dict[str, set[str]] = {}
        for uid, actor in self.state.interior_actors.items():
            self._actors_by_space.setdefault(actor.space_id, set()).add(uid)

    def player_presence(self) -> InteriorActor | None:
        return self.state.interior_actors.get("player")

    def current_plan(self) -> InteriorPlan | None:
        actor = self.player_presence()
        return self.state.interiors.get(actor.space_id) if actor else None

    def actors_in_space(self, space_id: str):
        return tuple((uid, self.state.interior_actors[uid]) for uid in sorted(self._actors_by_space.get(space_id, ()))
                     if uid in self.state.interior_actors and self.state.interior_actors[uid].space_id == space_id)

    def _put_actor(self, uid: str, actor: InteriorActor) -> None:
        self.state.interior_actors[uid] = actor
        self._actors_by_space.setdefault(actor.space_id, set()).add(uid)

    def _remove_actor(self, uid: str) -> None:
        actor = self.state.interior_actors.pop(uid, None)
        if actor:
            self._actors_by_space.get(actor.space_id, set()).discard(uid)

    def room_at(self, x: int, y: int) -> InteriorRoom | None:
        plan = self.current_plan()
        return room_at(plan, x, y) if plan else None

    def hit_test(self, x: int, y: int) -> InteriorFurniture | None:
        plan = self.current_plan()
        return next((f for f in reversed(plan.furniture) if f.rect.contains(x, y)), None) if plan else None

    def _prepare(self, door) -> InteriorPlan | None:
        space_id = "interior:" + door.property_id
        existing = self.state.interiors.get(space_id)
        if existing:
            return existing
        physical = self.sim.settlement_physicalization
        structure = physical.structure_by_id(door.property_id)
        if (structure is None or structure.destroyed or not structure.enclosed
                or structure.function not in {"residence", "inn", "barracks", "outskirt_camp"}):
            return None
        skeleton = physical.skeleton_for(door.settlement_id)
        if skeleton is None:
            return None
        rooms = [r for r in skeleton.rooms if r.structure_plan_id == structure.uid]
        pieces = [p for p in skeleton.pieces if p.structure_plan_id == structure.uid]
        plan = build_interior(structure, door, rooms, pieces)
        self.state.interiors[plan.uid] = plan
        register=getattr(physical,'register_interior',None)
        if register is not None:register(plan)
        return plan

    def enter(self, door_uid: str) -> str:
        if self.player_presence():
            return "You are already indoors."
        security = self.sim.property_security
        door = security.door_by_id(door_uid)
        if door is None or door.role != "entrance":
            return "That is not a building entrance."
        pos = self.sim.player_pos
        if pos.z != door.z or abs(pos.x - door.x) + abs(pos.y - door.y) > 1:
            return "Move next to the entrance first."
        if security.blocks_actor(WorldPos(door.x, door.y, door.z), "player"):
            return "The door is locked. Knock, use your key, or unlock it first."
        plan = self._prepare(door)
        if plan is None:
            return "This open-air structure has no enclosed interior."
        if not position_clear(plan, plan.entry_x, plan.entry_y):
            return "The inside landing is obstructed."
        self._put_actor("player", InteriorActor(plan.uid, plan.entry_x, plan.entry_y))
        return f"You enter the {plan.name.lower()}. WASD moves freely; right-click furniture to interact."

    def _exterior_landing(self, plan: InteriorPlan, actor_uid: str = "player") -> WorldPos | None:
        world = self.sim.world
        for dx, dy in ((0, 0), (0, 1), (-1, 0), (1, 0), (0, -1)):
            pos = WorldPos(plan.exterior_x + dx, plan.exterior_y + dy, plan.exterior_z)
            key, lx, ly = split_world(pos)
            chunk = world.cache.peek(key)
            if chunk is None:
                continue
            terrain = self.sim.registry.terrain(self.sim.registry.terrain_id(chunk.get(lx, ly)))
            if not terrain.passable or "water" in terrain.tags:
                continue
            if not self.sim.building.passable(pos, True):
                continue
            if not self.sim.environment.fluid_passable(pos):
                continue
            if self.sim.resources.blocks_movement(pos) and not self.sim.settlement_physicalization.clears_natural_feature(pos):
                continue
            if any(n.alive and n.uid != actor_uid and n.uid not in self.state.interior_actors
                   and (n.x, n.y, n.z) == (pos.x, pos.y, pos.z) for n in self.state.npcs.values()):
                continue
            if any(c.hp > 0 and (c.x, c.y, c.z) == (pos.x, pos.y, pos.z) for c in self.state.creatures.values()):
                continue
            if actor_uid != "player" and not self.player_presence() and pos == self.sim.player_pos:
                continue
            # Egress may pass the building's own locked threshold; an unrelated
            # adjoining door still follows actor-specific security.
            other_door = self.sim.property_security.door_at(pos)
            if (other_door and other_door.property_id != plan.building_id
                    and self.sim.property_security.blocks_actor(pos, actor_uid)):
                continue
            return pos
        return None

    def exit(self) -> str:
        plan, actor = self.current_plan(), self.player_presence()
        if not plan or not actor:
            return "You are already outside."
        if abs(actor.x - plan.entry_x) + abs(actor.y - plan.entry_y) > 1300:
            return "Walk to the exit doorway first."
        landing = self._exterior_landing(plan)
        if landing is None:
            return "The outside landing is blocked or not prepared; you cannot exit there."
        self.sim.entities.get(self.sim.player_id, Position).value = landing
        self._remove_actor("player")
        return "You step outside."

    def move_player(self, dx: int, dy: int) -> str:
        plan, actor = self.current_plan(), self.player_presence()
        if not plan or not actor:
            return "You are not indoors."
        dx, dy = max(-1, min(1, int(dx))), max(-1, min(1, int(dy)))
        step = 127 if dx and dy else 180
        moved = move_actor(plan, actor, dx * step, dy * step)
        actor.action = "walking" if moved else "idle"
        return "" if moved else "Furniture or an interior wall blocks the way."

    def rearrange(self, furniture_uid: str, x: int, y: int) -> str:
        plan, actor = self.current_plan(), self.player_presence()
        if not plan or not actor:
            return "You must be indoors to move furniture."
        furniture = next((f for f in plan.furniture if f.uid == furniture_uid), None)
        if furniture is None:
            return "That furnishing is not in this interior."
        if not self.can_rearrange(furniture):
            return "Only the owner may rearrange this furnishing."
        if self._distance(actor, furniture) > 1800:
            return "Move closer to the furnishing first."
        rect = InteriorRect(int(x), int(y), furniture.w, furniture.h)
        if not placement_clear(plan, rect, furniture.uid):
            return "The furnishing would overlap a wall, another furnishing, or the exit."
        old = furniture.x, furniture.y
        furniture.x, furniture.y = rect.x, rect.y
        # Furniture cannot bury an occupant or strand any room behind a blocked
        # passage. All actors in this room share the same collision authority.
        occupants = self.actors_in_space(plan.uid)
        safe = all(position_clear(plan, a.x, a.y) and exit_reachable(plan, a.x, a.y) for _, a in occupants)
        safe = safe and all(exit_reachable(plan, r.rect.x + r.rect.w // 2, r.rect.y + r.rect.h - 400) for r in plan.rooms)
        if not safe:
            furniture.x, furniture.y = old
            return "That placement would block an occupant or a room's route to the exit."
        return "You reposition the furnishing freely."

    def can_rearrange(self, furniture: InteriorFurniture) -> bool:
        plan = self.current_plan()
        if plan is None:
            return False
        prop = getattr(self.state, "properties", {}).get(plan.building_id)
        # Ownership changes after an interior was first entered must not leave
        # a stale furniture snapshot granting or denying permission forever.
        if prop is not None:
            return prop.owner_uid == "player"
        return furniture.owner_uid == "player" or plan.owner_uid == "player"

    @staticmethod
    def _distance(actor: InteriorActor, furniture: InteriorFurniture) -> int:
        dx = max(furniture.x - actor.x, 0, actor.x - furniture.x - furniture.w)
        dy = max(furniture.y - actor.y, 0, actor.y - furniture.y - furniture.h)
        return isqrt(dx * dx + dy * dy)

    def interact(self, furniture_uid: str) -> str:
        plan, actor = self.current_plan(), self.player_presence()
        if not plan or not actor:
            return "You are not indoors."
        furniture = next((f for f in plan.furniture if f.uid == furniture_uid), None)
        if furniture is None:
            return "That furnishing is not in this room."
        if self._distance(actor, furniture) > 1500:
            return "Move closer to interact with the furnishing."
        definition = self.sim.registry.settlement_pieces.get(furniture.piece_id)
        name = definition.name if definition else furniture.piece_id.split(":")[-1].replace("_", " ")
        if "bed" in furniture.piece_id or "chair" in furniture.piece_id or "bench" in furniture.piece_id:
            vitals = self.sim.entities.get(self.sim.player_id, Vitals)
            if vitals:
                vitals.stamina = min(100, vitals.stamina + 5)
                vitals.pain = max(0, vitals.pain - 1)
            actor.action = "resting"
            return f"You rest on the {name.lower()}."
        return f"{name}. This is the original building fixture, not a duplicate source of goods."

    def enter_npc(self, npc, door_uid: str) -> bool:
        """Home arrival uses the same physical door and lock authority as players."""
        if npc.uid in self.state.interior_actors:
            return False
        security = self.sim.property_security
        door = security.door_by_id(door_uid)
        if door is None or door.role != "entrance" or door.property_id != npc.home_id:
            return False
        if (npc.z != door.z or abs(npc.x - door.x) + abs(npc.y - door.y) > 1
                or security.blocks_actor(WorldPos(door.x, door.y, door.z), npc.uid)):
            return False
        plan = self._prepare(door)
        if plan is None or plan.function not in {"residence", "inn", "barracks", "outskirt_camp"}:
            return False
        if not position_clear(plan, plan.entry_x, plan.entry_y):
            return False
        minute = int(self.sim.clock.minute)
        self._put_actor(npc.uid, InteriorActor(plan.uid, plan.entry_x, plan.entry_y, action="arriving", last_need_minute=minute))
        # Legacy coordinates are an exterior portal anchor, never indoor cells.
        npc.x, npc.y, npc.z = door.x, door.y, door.z
        return True

    def _household_route(self, plan: InteriorPlan, actor: InteriorActor, target: tuple[int, int]) -> None:
        room = room_at(plan, actor.x, actor.y)
        target_room = room_at(plan, *target)
        hall_y = plan.rooms[0].rect.y + 650
        points = []
        if room and room.uid != plan.rooms[0].uid and room != target_room:
            points.extend([(room.rect.x + room.rect.w // 2, actor.y), (room.rect.x + room.rect.w // 2, hall_y)])
        if target_room and target_room.uid != plan.rooms[0].uid and room != target_room:
            points.extend([(target_room.rect.x + target_room.rect.w // 2, hall_y), (target_room.rect.x + target_room.rect.w // 2, target_room.rect.y + target_room.rect.h - 600)])
        points.append(target)
        actor.waypoints = [[x, y] for x, y in points if position_clear(plan, x, y)]

    def tick_update(self, minute: int) -> None:
        """Bounded domestic routines on simulation ticks, never rendering frames.

        Work production remains the existing external activity system. A home
        resident leaves through the portal when duty/needs require it. No indoor
        routine creates goods, food, or workplace output.
        """
        minute = int(minute)
        hour = minute % 1440 // 60
        for uid, actor in tuple(self.state.interior_actors.items()):
            if uid == "player" or actor.last_tick == minute:
                continue
            npc = self.state.npcs.get(uid)
            plan = self.state.interiors.get(actor.space_id)
            if npc is None or not npc.alive or plan is None:
                self._remove_actor(uid)
                continue
            old_tick = actor.last_tick
            actor.last_tick = minute
            elapsed_hours = min(24, max(0, (minute - actor.last_need_minute) // 60)) if actor.last_need_minute >= 0 else 0
            if elapsed_hours:
                npc.hunger = min(100, npc.hunger + elapsed_hours * 3)
                npc.thirst = min(100, npc.thirst + elapsed_hours * 5)
                npc.rest = min(100, npc.rest + elapsed_hours * 2)
                actor.last_need_minute += elapsed_hours * 60
            answering = any(t.get("action") == "answer_door" or t.get("door_answer_uid") for t in npc.tasks)
            leave = answering or npc.hunger >= 70 or npc.thirst >= 70 or (7 <= hour < 20 and npc.rest < 50)
            distant = abs(plan.exterior_x - self.sim.player_pos.x) + abs(plan.exterior_y - self.sim.player_pos.y) > 80
            if distant:
                # Tier-C does not replay household locomotion indefinitely.
                landing = self._exterior_landing(plan, uid) if leave else None
                if landing:
                    npc.x, npc.y, npc.z = landing.x, landing.y, landing.z
                    self._remove_actor(uid)
                continue
            if leave:
                if actor.action != "leaving":
                    self._household_route(plan, actor, (plan.entry_x, plan.entry_y))
                actor.action = "leaving"
                if abs(actor.x - plan.entry_x) + abs(actor.y - plan.entry_y) <= 350:
                    landing = self._exterior_landing(plan, uid)
                    if landing:
                        npc.x, npc.y, npc.z = landing.x, landing.y, landing.z
                        self._remove_actor(uid)
                    continue
            elif not actor.waypoints:
                phase = minute // 30
                sleeping = npc.rest >= 45 or hour >= 22 or hour < 6
                candidates = [f for f in plan.furniture if "bed" in f.piece_id] if sleeping else [f for f in plan.furniture if any(k in f.piece_id for k in ("chair", "table", "bench"))]
                candidate = next((f for f in candidates if f.uid == npc.bed_fixture_id), None)
                if candidate is None and candidates:
                    candidate = sorted(candidates, key=lambda f: f.uid)[hash_u64(self.sim.seed, "interior-household-routine", uid, phase) % len(candidates)]
                if candidate:
                    target = next(((x, y) for x, y in ((candidate.x + candidate.w // 2, candidate.y + candidate.h + ACTOR_RADIUS + 30), (candidate.x + candidate.w + ACTOR_RADIUS + 30, candidate.y + candidate.h // 2)) if position_clear(plan, x, y)), None)
                else:
                    room = plan.rooms[1 + hash_u64(self.sim.seed, "interior-household-room", uid, phase) % (len(plan.rooms) - 1)]
                    target = (room.rect.x + room.rect.w // 2, room.rect.y + room.rect.h - 600)
                actor.action = "resting" if sleeping else "relaxing"
                if target:
                    self._household_route(plan, actor, target)
            if actor.waypoints:
                tx, ty = actor.waypoints[0]
                dx, dy = tx - actor.x, ty - actor.y
                distance = max(1, isqrt(dx * dx + dy * dy))
                moved = move_actor(plan, actor, dx * min(220, distance) // distance, dy * min(220, distance) // distance)
                if abs(actor.x - tx) + abs(actor.y - ty) <= 90:
                    actor.waypoints.pop(0)
                elif not moved:
                    actor.waypoints.clear()
            if not actor.waypoints and actor.action == "resting" and old_tick // 30 != minute // 30:
                npc.rest = max(0, npc.rest - 20)
