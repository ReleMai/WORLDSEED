"""G1b: opt-in, read-only bridge from prepared WORLDSEED views to 2.5D.

This adapter accepts the SAME prepared `resource_by` rows consumed by the
software renderer, never asks ResourceSystem/world for more cells and never
returns new collision, interaction or persistent gameplay state. The crown
profile is provisional test metadata, NOT an authored sprite/silhouette.
No production renderer imports or invokes it until G2 has visual approval.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor
from typing import Callable, Mapping, Sequence

from .worldspace import (
    CoverRegion, MAX_SCENE_INSTANCES, MAX_VISIBLE_CELLS, ProjectedScene,
    SceneVisibility, VisualLayer, WorldCamera, WorldFoot,
    WorldVisualInstance, project_scene,
)

MAX_PREPARED_RESOURCES = 1024
MAX_PREPARED_ACTORS = 256
MAX_VIEW_CELLS = 8192
# Explicit G1b test silhouettes in world cells; *not* new resource placement,
# collision, authored art sizes or GPU atlas metadata.
PREVIEW_CROWN_PROFILES = {
    'core:oak_tree': (3.0, 2.7),
    'core:pine_tree': (2.1, 2.5),
}


@dataclass(frozen=True, slots=True)
class PreparedActor:
    """Caller-authorized actor, not an actor fetched or revealed by this layer."""

    uid: str
    content_id: str
    foot: WorldFoot
    authorized_visible: bool
    room_id: str | None = None
    is_viewer: bool = False

    def __post_init__(self) -> None:
        if not self.uid or not self.content_id or not isinstance(self.foot, WorldFoot):
            raise ValueError('actor identity, content and foot required')
        if type(self.authorized_visible) is not bool or type(self.is_viewer) is not bool:
            raise ValueError('actor visibility and viewer status must be explicit')


@dataclass(frozen=True, slots=True)
class PreparedScene:
    """Frozen visual records and their projected viewport; no gameplay mutation."""

    instances: tuple[WorldVisualInstance, ...]
    visibility: SceneVisibility
    projection: ProjectedScene
    camera: WorldCamera


def _visibility_window(camera: WorldCamera, current, discovered, z: int,
                       visibility_key: Callable[[int, int, int], object]) -> SceneVisibility:
    """Bounded membership reads, never iterate a lifetime discovery index."""
    if type(z) is not int:
        raise ValueError('scene z must be integer')
    top_left = camera.to_world(0, 0, ground_z=z)
    bottom_right = camera.to_world(camera.width_px, camera.height_px, ground_z=z)
    left, right = floor(top_left.x), ceil(bottom_right.x)
    top, bottom = floor(top_left.y), ceil(bottom_right.y)
    if not 0 < (right-left)*(bottom-top) <= MAX_VIEW_CELLS:
        raise ValueError('prepared viewport exceeds bounded visibility budget')
    now: set[tuple[int,int,int]] = set()
    memory: set[tuple[int,int,int]] = set()
    for y in range(top, bottom):
        for x in range(left, right):
            key = (x, y, z)
            source_key = visibility_key(x, y, z)
            if source_key in current:
                now.add(key)
            elif source_key in discovered:
                memory.add(key)
    if len(now) > MAX_VISIBLE_CELLS or len(memory) > MAX_VISIBLE_CELLS:
        raise ValueError('visibility window exceeds scene budget')
    return SceneVisibility(frozenset(now), frozenset(memory))


def _preview_cover(x: int, y: int, z: int, wide: float, tall: float) -> CoverRegion:
    cx, cy = x+0.5, y+0.5
    half_w, half_h = wide/2, tall/2
    return CoverRegion(((cx-half_w, cy-half_h), (cx+half_w, cy-half_h),
                        (cx+half_w, cy+half_h), (cx-half_w, cy+half_h)), z, z+0.99)


def prepare_worldspace_scene(
    *, camera: WorldCamera,
    resource_by: Mapping[tuple[int,int,int], tuple[object, object]],
    resource_defs: Mapping[str, object],
    resource_style: Callable[[str], Mapping],
    current_cells: object,
    discovered_cells: object,
    actors: Sequence[PreparedActor],
    z: int = 0,
    visibility_key: Callable[[int, int, int], object] = lambda x, y, z: (x, y, z),
) -> PreparedScene:
    """Use already-prepared software view rows; never request unknown resources.

    `resource_by[(x,y,z)] == (FeatureView, software_visual_ref)` and
    `resource_defs` are existing game contracts. Tree parts reuse ONE legacy
    resource identity derived from its original cell and feature ID. The
    software sprite ref stays with its original renderer; these records do
    not draw pixels, create harvest targets or alter collision. The caller
    supplies `visibility_key` for authoritative `pos_key` string sets.

    The caller must prefilter actors using gameplay sight/stealth/room rules.
    No unverified NPC is included just because its tile is currently visible.
    """
    if len(resource_by) > MAX_PREPARED_RESOURCES or len(actors) > MAX_PREPARED_ACTORS:
        raise ValueError('prepared scene snapshot exceeds budget')
    if camera.center.z != z:
        raise ValueError('camera and snapshot must use the same elevation')
    vis = _visibility_window(camera, current_cells, discovered_cells, z, visibility_key)
    visuals: list[WorldVisualInstance] = []
    for (x, y, rz), pair in sorted(resource_by.items(), key=lambda it: (it[0][2],it[0][1],it[0][0])):
        if type(x) is not int or type(y) is not int or type(rz) is not int:
            raise ValueError('resource keys must be integer xyz world cells')
        if rz != z or (x, y, z) not in vis.current_cells:
            continue
        if not isinstance(pair, tuple) or len(pair) != 2:
            raise ValueError('expected existing (FeatureView, sprite ref) rows')
        feature, _software_asset = pair
        fid = str(feature.feature_id)
        stage = str(feature.stage)
        if stage == 'depleted':
            continue
        definition = resource_defs.get(fid)
        if definition is None:
            continue  # no speculative or unauthorized resources
        style = resource_style(fid)
        if not isinstance(style, Mapping):
            raise ValueError('resource style must be a mapping')
        is_tree = 'tree' in getattr(definition, 'tags', ())
        growth = 0.65 if stage == 'sapling' else 1.0
        width = max(0.1, min(16.0, float(style.get('width', 1.35))*growth))
        height = max(0.1, min(16.0, float(style.get('height', 1.7))*growth))
        resource_uid = f'feature:{rz}:{x}:{y}:{fid}'
        base_id = f'{resource_uid}:{stage}'
        # The game still controls movement/harvest and may designate a
        # nonblocking tree; visual geometry is never physical authority.
        solid = stage == 'mature' and bool(getattr(definition, 'blocks_movement', False))
        trunk = WorldVisualInstance(
            f'{base_id}:base', fid, WorldFoot(x+0.5, y+0.95, z),
            width, height, height, VisualLayer.GROUNDED,
            ((x, y, z),) if solid else (), resource_id=resource_uid,
        )
        visuals.append(trunk)
        if is_tree and stage == 'mature' and fid in PREVIEW_CROWN_PROFILES:
            cw, ch = PREVIEW_CROWN_PROFILES[fid]
            # Preliminary *projection only*: no new art or collision footprint.
            cover = _preview_cover(x, y, z, cw, ch)
            visuals.append(WorldVisualInstance(
                f'{base_id}:shadow', fid, trunk.foot, cw, 1.0, 0.0,
                VisualLayer.GROUND_SHADOW, resource_id=resource_uid,
                parent_id=trunk.instance_id,
            ))
            visuals.append(WorldVisualInstance(
                f'{base_id}:crown', fid, trunk.foot, cw, max(ch, height),
                max(ch, height), VisualLayer.OVERHEAD,
                resource_id=resource_uid, parent_id=trunk.instance_id,
                cover=cover,
            ))
    viewers = [actor for actor in actors if actor.is_viewer]
    if len(viewers) != 1 or not viewers[0].authorized_visible:
        raise ValueError('one explicitly visible viewer required')
    for actor in sorted(actors, key=lambda a: a.uid):
        # No inferred stealth or property clearance; room-gated visuals are
        # deliberately omitted in G1b until an authoritative room map exists.
        if not actor.authorized_visible or actor.room_id is not None:
            continue
        if actor.foot.cell not in vis.current_cells:
            continue
        visuals.append(WorldVisualInstance(
            f'actor:{actor.uid}', actor.content_id, actor.foot,
            0.8, 1.55, 1.55, VisualLayer.UPRIGHT,
            resource_id=None, authorized_visible=True,
        ))
    if len(visuals) > MAX_SCENE_INSTANCES:
        raise ValueError('visual scene exceeds instance budget')
    rows = tuple(visuals)
    return PreparedScene(rows, vis, project_scene(rows, camera, vis,
                                                  viewer_id=f'actor:{viewers[0].uid}'), camera)
