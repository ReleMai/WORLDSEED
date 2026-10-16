"""Bounded outdoor Action Hub rows and explicit authoritative dispatch.

Browsing consumes a detached W1 snapshot only. Pointer selection has no command
effect. The modal's owner retains NavigationStack state and invokes dispatch
only after the player explicitly chooses a row.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import floor

from worldseed.core.coords import WorldPos
from worldseed.presentation.live_gpu_scene import capture_live_scene
from worldseed.sim.commands import GatherCommand, MoveCommand, PickupCommand, WaitCommand
from worldseed.systems.resources import FeatureView

MAX_GPU_ACTION_ROWS = 8


@dataclass(frozen=True, slots=True)
class GpuActionRow:
    uid: str
    label: str
    kind: str
    origin: tuple[int, int, int]
    target: tuple[int, int, int]
    terrain_id: str
    feature: FeatureView | None = None


@dataclass(frozen=True, slots=True)
class GpuActionResult:
    dispatched: bool
    message: str


def _cell(target):
    if isinstance(target, WorldPos):
        target = (target.x, target.y, target.z)
    if (not isinstance(target, tuple) or len(target) != 3
            or any(type(value) is not int for value in target)):
        return None
    return target


def _near(origin, target):
    return origin[2] == target[2] and abs(origin[0]-target[0])+abs(origin[1]-target[1]) <= 1


def action_rows(snapshot, registry, selected_target=None) -> tuple[GpuActionRow, ...]:
    """Offer at most five reachable harvests and local pickup/wait/step rows.

    This does not inspect the simulation, tool availability, piles, collision or
    hidden cells. The existing command handlers validate gameplay requirements.
    A selected cell only narrows target choices; it never requests an action.
    """
    if snapshot.interior:
        return ()
    origin = (floor(snapshot.viewer.x), floor(snapshot.viewer.y), int(snapshot.viewer.z))
    terrain = dict(snapshot.terrain)
    features = dict(snapshot.resources)

    def admitted(cell):
        return cell in snapshot.current_cells and cell in terrain and _near(origin,cell)

    if not admitted(origin):
        return ()
    selected = _cell(selected_target)
    if selected_target is None:
        candidates = tuple((origin[0]+dx,origin[1]+dy,origin[2])
                           for dx,dy in ((0,0),(0,-1),(0,1),(-1,0),(1,0)))
    else:
        candidates = (selected,) if selected is not None and admitted(selected) else ()
    rows = []

    def row(kind, label, target):
        return GpuActionRow(f'{kind}:{target[2]}:{target[0]}:{target[1]}',label,
                            kind,origin,target,terrain[target],features.get(target))

    for target in candidates:
        if not admitted(target):
            continue
        feature = features.get(target)
        definition = registry.resources.get(feature.feature_id) if feature else None
        if (feature is not None and feature.stage == 'mature' and definition is not None
                and 'natural_container' not in definition.tags):
            rows.append(row('gather',f'Harvest {definition.name.lower()}',target))
        elif target[2] < 0:
            ground = registry.terrains.get(terrain[target])
            if ground and ground.gather_item and ground.gather_amount > 0 and ground.depleted_to:
                rows.append(row('gather',f'Mine {ground.name.lower()}',target))
    pickup = selected if selected is not None and admitted(selected) else origin
    rows.append(row('pickup','Pick up ground items',pickup))
    if selected is not None and admitted(selected) and selected != origin:
        rows.append(row('move','Step to selected cell',selected))
    rows.append(row('wait','Wait briefly',origin))
    if len(rows) > MAX_GPU_ACTION_ROWS:
        raise ValueError('GPU Action Hub exceeds bounded row budget')
    return tuple(rows)


def dispatch_action(sim, row: GpuActionRow, snapshot) -> GpuActionResult:
    """Reauthorize a chosen row, then invoke one existing simulation command.

    A stale snapshot is never authority. Fresh capture reuses W1's current sight,
    prepared terrain/resource identity and private roof/room gates. Rebuilding
    this small menu validates proximity, elevation, stage and action identity.
    ``dispatched`` means the command ran; its log reports gameplay acceptance or
    rejection (including missing tools, blocked trunks, combat and property).
    """
    denied = GpuActionResult(False,'That action is no longer available. Open Actions again.')
    if not isinstance(row,GpuActionRow):
        return denied
    if sim.interiors.player_presence() is not None:
        return denied
    position = sim.player_pos
    if (position.x,position.y,position.z) != row.origin:
        return denied
    if snapshot.camera.center.z != position.z:
        return denied
    fresh = capture_live_scene(sim,snapshot.camera)
    if row not in action_rows(fresh,sim.registry,row.target):
        return denied
    dx,dy = row.target[0]-position.x,row.target[1]-position.y
    if row.kind == 'gather':
        command = GatherCommand(sim.player_id,dx,dy)
    elif row.kind == 'pickup':
        command = PickupCommand(sim.player_id,dx,dy)
    elif row.kind == 'move':
        command = MoveCommand(sim.player_id,dx,dy)
    elif row.kind == 'wait':
        command = WaitCommand(sim.player_id,10)
    else:
        return denied
    before = len(sim.log)
    sim.execute(command)
    message = sim.log[-1].message if len(sim.log) > before else 'Action completed.'
    return GpuActionResult(True,message)
