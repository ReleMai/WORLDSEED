"""Continuous sub-tile locomotion for outdoor graphical play.

The authoritative world remains tile based for collision, interactions, path
choice, persistence, and simulation ownership. Fractions only describe where
an actor is within its current tile while a cached route is being traversed.
"""

from __future__ import annotations

from worldseed.core.coords import WorldPos

WALK_SPEED = 1.8
SPRINT_SPEED = 3.6
MAX_FRAME_DT = 0.10
ARRIVAL_EPSILON = 0.06


def _clamp_fraction(value: float) -> float:
    return max(0.0, min(0.999, float(value)))


def _blocked_token(tile: WorldPos, dx: int, dy: int) -> tuple[int, int, int, int, int]:
    return (int(tile.x), int(tile.y), int(tile.z), int(dx), int(dy))


def update_player_free(sim, dt: float, dx: float, dy: float, sprint: bool) -> bool:
    """Integrate player motion without replacing authoritative tile crossing rules."""
    dt = max(0.0, min(MAX_FRAME_DT, float(dt)))
    if dt <= 0.0:
        return False
    state = sim.state
    fx = float(getattr(state, "player_fx", 0.5))
    fy = float(getattr(state, "player_fy", 0.5))
    old_fx, old_fy = fx, fy
    if dx == 0.0 and dy == 0.0:
        setattr(sim, "_free_move_blocked", None)
        return False
    mag = (dx * dx + dy * dy) ** 0.5
    if mag <= 0.0:
        return False
    dx /= mag
    dy /= mag
    state.player_facing_dx = 0 if abs(dx) <= 1e-6 else (1 if dx > 0.0 else -1)
    state.player_facing_dy = 0 if abs(dy) <= 1e-6 else (1 if dy > 0.0 else -1)
    speed = SPRINT_SPEED if sprint else WALK_SPEED
    fx += dx * speed * dt
    fy += dy * speed * dt
    tile = sim.player_pos
    tile_changed = False
    blocked = getattr(sim, "_free_move_blocked", None)
    if blocked is not None:
        _, _, _, bdx, bdy = blocked
        if (bdx and dx * bdx <= 0.0) or (bdy and dy * bdy <= 0.0):
            blocked = None
            setattr(sim, "_free_move_blocked", None)
    step_x = 1 if fx >= 1.0 else (-1 if fx < 0.0 else 0)
    if step_x:
        token = _blocked_token(tile, step_x, 0)
        moved = False if blocked == token else bool(sim.try_free_movement_step(step_x, 0))
        if moved:
            fx -= step_x
            tile = sim.player_pos
            tile_changed = True
            blocked = None
            setattr(sim, "_free_move_blocked", None)
        else:
            fx = 0.999 if step_x > 0 else 0.0
            if blocked != token:
                blocked = token
                setattr(sim, "_free_move_blocked", token)
    step_y = 1 if fy >= 1.0 else (-1 if fy < 0.0 else 0)
    if step_y:
        token = _blocked_token(tile, 0, step_y)
        moved = False if blocked == token else bool(sim.try_free_movement_step(0, step_y))
        if moved:
            fy -= step_y
            tile_changed = True
            setattr(sim, "_free_move_blocked", None)
        else:
            fy = 0.999 if step_y > 0 else 0.0
            if blocked != token:
                setattr(sim, "_free_move_blocked", token)
    state.player_fx = _clamp_fraction(fx)
    state.player_fy = _clamp_fraction(fy)
    return bool(tile_changed or abs(state.player_fx-old_fx)>0.001 or abs(state.player_fy-old_fy)>0.001)


def _advance_npc_one_step(sim, npc, dt: float, speed: float) -> bool:
    """Move one outdoor NPC toward the next simulation-selected local waypoint."""
    tasks = npc.tasks
    if not tasks or tasks[0].get("kind") != "move":
        return False
    task = tasks[0]
    path = task.get("_local_path")
    if not path:
        return False
    fx = float(getattr(npc, "fx", 0.5))
    fy = float(getattr(npc, "fy", 0.5))
    old_fx, old_fy = fx, fy
    nx, ny = int(path[0][0]), int(path[0][1])
    tx = (nx-npc.x) + (0.5-fx)
    ty = (ny-npc.y) + (0.5-fy)
    dist = (tx*tx + ty*ty) ** 0.5
    if dist <= ARRIVAL_EPSILON:
        old_x, old_y = npc.x, npc.y
        npc.x, npc.y = nx, ny
        npc.fx, npc.fy = 0.5, 0.5
        path.pop(0)
        task["_local_path"] = path
        sim.npcs._face_step(npc, old_x, old_y)
        sim.npcs._index_npc(npc)
        if not path:
            goal=(int(task.get("x",npc.x)),int(task.get("y",npc.y)))
            portal=any(task.get(key) for key in ("interior_home_door_uid","interior_work_door_uid","interior_storage_door_uid"))
            if (npc.x,npc.y)==goal and not portal:
                npc.tasks.pop(0)
            else:
                task.pop("_local_path",None);task.pop("_local_path_goal",None)
        return True
    step=min(float(speed)*dt,dist)
    fx += (tx/dist)*step
    fy += (ty/dist)*step
    tile=WorldPos(npc.x,npc.y,npc.z)
    step_x=1 if fx>=1.0 else (-1 if fx<0.0 else 0)
    step_y=1 if fy>=1.0 else (-1 if fy<0.0 else 0)
    crossed=False
    if step_x or step_y:
        candidate=tile.moved(step_x,step_y)
        if sim.npcs.movement_passable(npc,candidate,sim.clock.minute):
            old_x,old_y=npc.x,npc.y
            fx -= step_x;fy -= step_y
            npc.x,npc.y=candidate.x,candidate.y
            sim.npcs._face_step(npc,old_x,old_y)
            sim.npcs._index_npc(npc)
            crossed=True
        else:
            if step_x:fx=0.999 if step_x>0 else 0.0
            if step_y:fy=0.999 if step_y>0 else 0.0
            task.pop("_local_path",None);task.pop("_local_path_goal",None)
    npc.fx=_clamp_fraction(fx);npc.fy=_clamp_fraction(fy)
    return bool(crossed or abs(npc.fx-old_fx)>0.001 or abs(npc.fy-old_fy)>0.001)


def update_npcs_free(sim, dt: float) -> bool:
    """Advance outdoor NPCs only when the graphical continuous mode is enabled."""
    dt=max(0.0,min(MAX_FRAME_DT,float(dt)))
    if dt<=0.0 or not getattr(sim.npcs,"continuous_motion_enabled",False):
        return False
    interiors=getattr(sim.state,"interior_actors",{})
    changed=False
    local_query=getattr(sim.npcs,"continuous_movement_npcs",None)
    # Production always uses the simulation-owned locator. The small controller
    # compatibility path keeps standalone locomotion callers without a player
    # or an NPCSystem working; it is not used by the game runtime.
    candidates=(local_query(sim.player_pos) if callable(local_query)
                else tuple(sim.state.npcs.values()))
    for npc in candidates:
        if not npc.alive or npc.uid in interiors:
            continue
        changed=_advance_npc_one_step(sim,npc,dt,WALK_SPEED) or changed
    return changed
