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
from worldseed.systems.interior_templates import profile_for, rooms_for_profile
from worldseed.systems.workshops import STATION_PIECE_ALIASES


def furniture_size(piece_id: str) -> tuple[int, int]:
    if "bed" in piece_id:
        return 950, 1450
    if "table" in piece_id:
        return 1150, 750
    if "chest" in piece_id or "storage" in piece_id:
        return 850, 650
    return 750, 750


def build_interior(structure, door, source_rooms=(), pieces=()) -> InteriorPlan:
    """Create a v2 layout only for a building without a persisted interior.

    Every furnishing is a projection of an existing stable plan-piece identity;
    the template supplies space, not extra beds, production or material stocks.
    """
    cells = structure.footprint or [(door.x, door.y)]
    span_x = max(x for x, _ in cells) - min(x for x, _ in cells) + 1
    span_y = max(y for _, y in cells) - min(y for _, y in cells) + 1
    profile = profile_for(structure)
    width = max(profile["width"], min(30000, span_x * 1500))
    height = max(profile["height"], min(26000, span_y * 1500))
    plan = InteriorPlan(
        "interior:" + structure.uid, structure.uid, door.uid, door.x, door.y,
        door.z, width, height, structure.function.replace("_", " ").title(),
        structure.function, door.owner_uid, version=2, layout_id=profile["id"],
    )
    plan.rooms, plan.walls, (plan.entry_x, plan.entry_y) = rooms_for_profile(plan.uid, profile, width, height, source_rooms)
    fixture_rooms = {uid: i + 1 for i, room in enumerate(sorted(source_rooms, key=lambda r: r.uid)) for uid in room.fixture_ids}
    for piece in sorted(pieces, key=lambda p: p.uid):
        if piece.role not in {"fixture", "tile_decor"}:
            continue
        w, h = furniture_size(piece.piece_id)
        key = piece.piece_id.lower()
        preferred = []
        if "bed" in key:
            preferred = [r for r in plan.rooms if any(k in r.name.lower() for k in ("bed", "dorm", "bunk", "guest", "recovery"))]
        elif any(k in key for k in ("hearth", "table", "chair", "bench")):
            preferred = [r for r in plan.rooms if any(k in r.name.lower() for k in ("living", "kitchen", "tavern", "mess", "common"))]
        elif any(k in key for k in ("chest", "shelf", "rack", "hay")):
            preferred = [r for r in plan.rooms if any(k in r.name.lower() for k in ("store", "pantry", "armory", "supply", "hay", "book"))]
        else:
            preferred = [r for r in plan.rooms if any(k in r.name.lower() for k in ("work", "forge", "machinery", "preparation", "treatment", "class", "scribe", "sanctuary"))]
        original_room = plan.rooms[min(len(plan.rooms) - 1, fixture_rooms.get(piece.uid, 1))]
        choices = list(dict.fromkeys(r.uid for r in preferred + [original_room] + plan.rooms))
        rooms_by_id = {r.uid: r for r in plan.rooms}
        placed = False
        for uid in choices:
            rect = rooms_by_id[uid].rect
            # Corners first, then bounded fractional shelf rows. The free centre
            # and a 900-unit door apron remain circulation space.
            positions = [(rect.x + 425, rect.y + 425), (rect.x + rect.w - w - 425, rect.y + 425)]
            positions += [(rect.x + 425 + col * (w + 575), rect.y + 425 + row * (h + 575))
                          for row in range(1, 6) for col in range(3)]
            for x, y in positions:
                if x + w > rect.x + rect.w - 400 or y + h > rect.y + rect.h - 950:
                    continue
                furnishing = InteriorFurniture(piece.uid, piece.piece_id, x, y, w, h, door.owner_uid, piece.uid, piece.role == "fixture")
                if placement_clear(plan, furnishing.rect):
                    plan.furniture.append(furnishing)
                    placed = True
                    break
            if placed:
                break
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


def _segment_hits_rect(a: tuple[int, int], b: tuple[int, int], rect: InteriorRect) -> bool:
    left, top, right, bottom = rect.x, rect.y, rect.x + rect.w, rect.y + rect.h
    if max(a[0], b[0]) < left or min(a[0], b[0]) > right or max(a[1], b[1]) < top or min(a[1], b[1]) > bottom:
        return False
    if any(left <= p[0] <= right and top <= p[1] <= bottom for p in (a, b)):
        return True
    def cross(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    corners = [(left, top), (right, top), (right, bottom), (left, bottom)]
    for c, d in zip(corners, corners[1:] + corners[:1]):
        if (max(a[0], b[0]) < min(c[0], d[0]) or min(a[0], b[0]) > max(c[0], d[0])
                or max(a[1], b[1]) < min(c[1], d[1]) or min(a[1], b[1]) > max(c[1], d[1])):
            continue
        if cross(a, b, c) * cross(a, b, d) <= 0 and cross(c, d, a) * cross(c, d, b) <= 0:
            return True
    return False


def segment_clear(plan: InteriorPlan, start: tuple[int, int], target: tuple[int, int], radius: int = ACTOR_RADIUS) -> bool:
    if not position_clear(plan, *start, radius) or not position_clear(plan, *target, radius):
        return False
    return not any(_segment_hits_rect(start, target, InteriorRect(r.x - radius, r.y - radius, r.w + radius * 2, r.h + radius * 2))
                   for r in plan.walls + [f.rect for f in plan.furniture if f.solid])


def interior_path(plan: InteriorPlan, start: tuple[int, int], target: tuple[int, int]) -> list[tuple[int, int]] | None:
    """Bounded continuous corner visibility graph, shared by every room grammar."""
    if segment_clear(plan, start, target):
        return [target] if start != target else []
    if not position_clear(plan, *start) or not position_clear(plan, *target):
        return None
    nodes = [start, target]
    obstacles = plan.walls + [f.rect for f in plan.furniture if f.solid]
    clearance = ACTOR_RADIUS + 25
    for rect in obstacles:
        for px in (rect.x - clearance, rect.x + rect.w + clearance):
            for py in (rect.y - clearance, rect.y + rect.h + clearance):
                if position_clear(plan, px, py):
                    nodes.append((px, py))
    # Household plans are bounded; de-duplicate corner nodes before graph work.
    nodes = list(dict.fromkeys(nodes))[:180]
    parents, queue = {0: None}, deque([0])
    while queue:
        index = queue.popleft()
        if index == 1:
            path = []
            while index:
                path.append(nodes[index])
                index = parents[index]
            return list(reversed(path))
        ax, ay = nodes[index]
        for other, (bx, by) in enumerate(nodes):
            if other in parents:
                continue
            if segment_clear(plan, (ax, ay), (bx, by)):
                parents[other] = index
                queue.append(other)
    return None


def exit_reachable(plan: InteriorPlan, x: int, y: int) -> bool:
    return interior_path(plan, (x, y), (plan.entry_x, plan.entry_y)) is not None


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

    def station_ids_near_player(self) -> set[str]:
        """Observe recipe station aliases within continuous indoor reach.

        This reads only the currently occupied persisted plan, never prepares
        another building or exposes stations through interior partitions.
        """
        plan, actor = self.current_plan(), self.player_presence()
        if plan is None or actor is None:
            return set()
        return {station_id for furnishing in plan.furniture
                if (station_id := STATION_PIECE_ALIASES.get(furnishing.piece_id))
                and station_id in self.sim.registry.structures
                and self._furniture_reachable(plan, actor, furnishing, 1800)}

    def furniture_in_reach(self, furniture_uid: str, reach: int = 1800) -> bool:
        """Observe actual furniture reach in the player's current space."""
        plan, actor = self.current_plan(), self.player_presence()
        if plan is None or actor is None:
            return False
        furnishing = next((f for f in plan.furniture if f.uid == furniture_uid), None)
        return bool(furnishing and self._furniture_reachable(plan, actor, furnishing, max(0, int(reach))))

    def _prepare(self, door) -> InteriorPlan | None:
        space_id = "interior:" + door.property_id
        physical = self.sim.settlement_physicalization
        structure = physical.structure_by_id(door.property_id)
        if structure is None or structure.destroyed or not structure.enclosed:
            return None
        existing = self.state.interiors.get(space_id)
        if existing:
            return existing
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
        notice = getattr(security, "note_interior_entry", None)
        messages = notice(plan, int(self.sim.clock.minute), getattr(self.sim, "stealth", None)) if notice else []
        return f"You enter the {plan.name.lower()}. WASD moves freely; right-click furniture to interact." + (" " + " ".join(messages) if messages else "")

    def _exterior_landing(self, plan: InteriorPlan, actor_uid: str = "player") -> WorldPos | None:
        world = self.sim.world
        frontage_lookup = getattr(self.sim.settlement_physicalization, "frontage_for", None)
        frontage = frontage_lookup(plan.building_id) if frontage_lookup else None
        candidates = ([frontage] if frontage else []) + [WorldPos(plan.exterior_x + dx, plan.exterior_y + dy, plan.exterior_z) for dx, dy in ((0, 0), (0, 1), (-1, 0), (1, 0), (0, -1))]
        for pos in dict.fromkeys(candidates):
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
        notice = getattr(self.sim.property_security, "note_interior_exit", None)
        messages = notice(plan, int(self.sim.clock.minute)) if notice else []
        return "You step outside." + (" " + " ".join(messages) if messages else "")

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
        if any(row.target_uid == furniture.uid and row.status in {"reserved", "active"}
               for row in self.state.activity_reservations.values()):
            return "That work station is reserved; wait until its current activity finishes."
        if not self._furniture_reachable(plan, actor, furniture, 1800):
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

    @classmethod
    def _furniture_reachable(cls, plan: InteriorPlan, actor: InteriorActor, furniture: InteriorFurniture, reach: int) -> bool:
        if cls._distance(actor, furniture) > reach:
            return False
        nearest = (max(furniture.x, min(actor.x, furniture.x + furniture.w)),
                   max(furniture.y, min(actor.y, furniture.y + furniture.h)))
        return not any(_segment_hits_rect((actor.x, actor.y), nearest, wall) for wall in plan.walls)

    def interact(self, furniture_uid: str) -> str:
        plan, actor = self.current_plan(), self.player_presence()
        if not plan or not actor:
            return "You are not indoors."
        furniture = next((f for f in plan.furniture if f.uid == furniture_uid), None)
        if furniture is None:
            return "That furnishing is not in this room."
        if not self._furniture_reachable(plan, actor, furniture, 1500):
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

    def prepare_workplace(self, building_id: str, door_uid: str = "") -> InteriorPlan | None:
        security = self.sim.property_security
        door = security.door_by_id(door_uid) if door_uid else next((d for d in security.doors_for_property(building_id) if d.role == "entrance"), None)
        if door is None or door.property_id != building_id:
            return None
        return self._prepare(door)

    @staticmethod
    def fixture_use_position(plan: InteriorPlan, fixture: InteriorFurniture | None) -> tuple[int, int] | None:
        if fixture is None:
            return None
        distance = ACTOR_RADIUS + 70
        candidates = ((fixture.x + fixture.w // 2, fixture.y + fixture.h + distance),
                      (fixture.x + fixture.w + distance, fixture.y + fixture.h // 2),
                      (fixture.x + fixture.w // 2, fixture.y - distance),
                      (fixture.x - distance, fixture.y + fixture.h // 2))
        return next((p for p in candidates if position_clear(plan, *p) and exit_reachable(plan, *p)), None)

    def enter_work_npc(self, npc, door_uid: str) -> bool:
        if npc.uid in self.state.interior_actors:
            return False
        security = self.sim.property_security
        door = security.door_by_id(door_uid)
        if door is None or door.property_id != npc.workplace_id or door.role != "entrance":
            return False
        if (npc.z != door.z or abs(npc.x - door.x) + abs(npc.y - door.y) > 1
                or security.blocks_actor(WorldPos(door.x, door.y, door.z), npc.uid)):
            return False
        plan = self._prepare(door)
        if plan is None or not position_clear(plan, plan.entry_x, plan.entry_y):
            return False
        self._put_actor(npc.uid, InteriorActor(plan.uid, plan.entry_x, plan.entry_y, action="working", last_need_minute=int(self.sim.clock.minute)))
        npc.x, npc.y, npc.z = door.x, door.y, door.z
        return True

    def _workplace_tick(self, npc, actor: InteriorActor, plan: InteriorPlan, minute: int) -> None:
        task = npc.tasks[0] if npc.tasks else {}
        reservation = self.state.activity_reservations.get(str(task.get("reservation_uid", "")))
        meta = reservation.metadata if reservation else {}
        working_here = bool(meta.get("space_id") == plan.uid and task.get("kind") in {"move", "activity"})
        if working_here and reservation.status in {"reserved", "active"}:
            target = int(meta["interior_use_x"]), int(meta["interior_use_y"])
            if actor.target_x != target[0] or actor.target_y != target[1]:
                actor.target_x, actor.target_y = target
                self._household_route(plan, actor, target)
            if max(abs(actor.x - target[0]), abs(actor.y - target[1])) <= 200:
                actor.waypoints.clear()
                actor.action = str(task.get("action", reservation.phase))
                if task.get("kind") == "move":
                    npc.tasks.pop(0)
                else:
                    town = self.state.settlements.get(npc.settlement_id)
                    if town is not None:
                        self.sim.npcs.execute_interior_activity(npc, town, minute)
                return
        else:
            if task.get("kind") == "activity" and reservation and reservation.status in {"cancelled", "completed"}:
                npc.tasks.pop(0)
            target = plan.entry_x, plan.entry_y
            if actor.action != "leaving":
                actor.target_x, actor.target_y = target
                self._household_route(plan, actor, target)
            actor.action = "leaving"
            if abs(actor.x - plan.entry_x) + abs(actor.y - plan.entry_y) <= 350:
                landing = self._exterior_landing(plan, npc.uid)
                if landing:
                    npc.x, npc.y, npc.z = landing.x, landing.y, landing.z
                    self._remove_actor(npc.uid)
                return
        if actor.waypoints:
            tx, ty = actor.waypoints[0]
            dx, dy = tx - actor.x, ty - actor.y
            distance = max(1, isqrt(dx * dx + dy * dy))
            moved = self._move_npc(npc, plan, actor, dx * min(350, distance) // distance, dy * min(350, distance) // distance)
            if abs(actor.x - tx) + abs(actor.y - ty) <= 60:
                actor.waypoints.pop(0)
            elif not moved:
                actor.target_x = actor.target_y = None
                actor.waypoints.clear()

    def _household_route(self, plan: InteriorPlan, actor: InteriorActor, target: tuple[int, int]) -> None:
        actor.waypoints = [list(p) for p in (interior_path(plan, (actor.x, actor.y), target) or [])]

    @staticmethod
    def _move_npc(npc, plan: InteriorPlan, actor: InteriorActor, dx: int, dy: int) -> bool:
        old_x, old_y = actor.x, actor.y
        moved = move_actor(plan, actor, dx, dy)
        if moved:
            npc.facing_dx = 0 if actor.x == old_x else (1 if actor.x > old_x else -1)
            npc.facing_dy = 0 if actor.y == old_y else (1 if actor.y > old_y else -1)
        return moved

    def tick_update(self, minute: int) -> None:
        """Bounded domestic routines on simulation ticks, never rendering frames.

        Work arrivals call the existing reservation/completion authority only
        after continuous station arrival. Household routines create no goods.
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
            if plan.building_id == npc.workplace_id and (actor.action == "working" or plan.function not in {"residence", "inn", "barracks", "outskirt_camp"}
                    or any(t.get("profession_task") or t.get("space_id") == plan.uid for t in npc.tasks)):
                self._workplace_tick(npc, actor, plan, minute)
                continue
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
                moved = self._move_npc(npc, plan, actor, dx * min(220, distance) // distance, dy * min(220, distance) // distance)
                if abs(actor.x - tx) + abs(actor.y - ty) <= 90:
                    actor.waypoints.pop(0)
                elif not moved:
                    actor.waypoints.clear()
            if not actor.waypoints and actor.action == "resting" and old_tick // 30 != minute // 30:
                npc.rest = max(0, npc.rest - 20)
