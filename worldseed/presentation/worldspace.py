"""G0/G1a: pure world-space 2.5D scene contracts (NOT the live renderer).

Inputs are immutable, observational projections of authoritative game state.
The producer owns resource IDs, physical collision, vision and room access;
this module must never query, regenerate, persist or modify world/sim data.
The software pygame renderer remains the supported backend during G1a.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from math import ceil, floor, isfinite


MAX_SCENE_INSTANCES = 4096
MAX_VISIBLE_CELLS = 8192
MAX_OBJECT_CELLS = 256
MAX_COVER_CUTOUTS = 8
MAX_CLIP_RECTS_PER_INSTANCE = 2048


class VisualLayer(IntEnum):
    GROUND = 0
    LOW_DETAIL = 10
    GROUND_SHADOW = 20
    GROUNDED = 30
    UPRIGHT = 31
    OVERHEAD = 40
    ATMOSPHERE = 50
    UI = 60


def _number(value: float, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{name} must be a finite number")


@dataclass(frozen=True, slots=True)
class WorldFoot:
    """Authoritative world-space foot/contact point; fractions are unsnapped."""

    x: float
    y: float
    z: float = 0.0

    def __post_init__(self) -> None:
        for name in ('x', 'y', 'z'):
            _number(getattr(self, name), name)

    @property
    def cell(self) -> tuple[int, int, int]:
        return floor(self.x), floor(self.y), floor(self.z)


@dataclass(frozen=True, slots=True)
class CoverRegion:
    """Author-supplied WORLD-space canopy/roof polygon and compatible foot heights.

    This shape only decides visual occlusion. It is never a collision volume.
    """

    polygon: tuple[tuple[float, float], ...]
    min_foot_z: float = 0.0
    max_foot_z: float = 1.0

    def __post_init__(self) -> None:
        if not isinstance(self.polygon, tuple) or len(self.polygon) < 3 or len(self.polygon) > 64:
            raise ValueError('cover polygon requires 3..64 vertices')
        for point in self.polygon:
            if not isinstance(point, tuple) or len(point) != 2:
                raise ValueError('cover vertices must be immutable x/y pairs')
            x, y = point
            _number(x, 'cover x')
            _number(y, 'cover y')
        _number(self.min_foot_z, 'min_foot_z')
        _number(self.max_foot_z, 'max_foot_z')
        if self.max_foot_z < self.min_foot_z:
            raise ValueError('inverted cover elevation band')

    def contains(self, foot: WorldFoot) -> bool:
        if not self.min_foot_z <= foot.z <= self.max_foot_z:
            return False
        x, y = foot.x, foot.y
        inside = False
        p = self.polygon
        for i, (ax, ay) in enumerate(p):
            bx, by = p[(i + 1) % len(p)]
            cross = (x - ax) * (by - ay) - (y - ay) * (bx - ax)
            if abs(cross) <= 1e-9 and min(ax, bx)-1e-9 <= x <= max(ax, bx)+1e-9 and min(ay, by)-1e-9 <= y <= max(ay, by)+1e-9:
                return True
            if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
                inside = not inside
        return inside


@dataclass(frozen=True, slots=True)
class WorldVisualInstance:
    """One visual, not one gameplay entity. Related tree parts share resource_id.

    ``physical_cells`` are COPIED from authority to document the real hitbox;
    visual width, height, cover, shadow and fade never add occupied cells.
    A leaf, shadow and trunk may share one resource_id but distinct instance IDs.
    """

    instance_id: str
    content_id: str
    foot: WorldFoot
    width: float
    height: float
    visual_height: float
    layer: VisualLayer
    physical_cells: tuple[tuple[int, int, int], ...] = ()
    resource_id: str | None = None
    parent_id: str | None = None
    cover: CoverRegion | None = None
    shadow_source_id: str | None = None
    emissive_source_id: str | None = None
    room_id: str | None = None
    revision: int = 0
    # Must be provided by authoritative visibility/stealth producer, not guessed
    # from cell vision alone. False disallows even a silhouette or local fade.
    authorized_visible: bool = True

    def __post_init__(self) -> None:
        if not self.instance_id or not self.content_id:
            raise ValueError('instance and content identity required')
        if not isinstance(self.layer, VisualLayer):
            raise ValueError('visual layer must be explicit')
        if not isinstance(self.foot, WorldFoot):
            raise TypeError('foot must be WorldFoot')
        for name in ('width', 'height', 'visual_height'):
            value = getattr(self, name)
            _number(value, name)
            if value < 0 or (name != 'visual_height' and value == 0):
                raise ValueError(f'{name} must be positive/nonnegative')
        if self.width > 128 or self.height > 128 or self.visual_height > 128:
            raise ValueError('unbounded object visual extent')
        if type(self.revision) is not int or self.revision < 0:
            raise ValueError('revision must be nonnegative integer')
        if type(self.authorized_visible) is not bool:
            raise ValueError('authorized visibility must be boolean')
        if not isinstance(self.physical_cells, tuple):
            raise ValueError('physical footprint must be immutable')
        if len(self.physical_cells) > MAX_OBJECT_CELLS:
            raise ValueError('physical footprint too large for a visual instance')
        for cell in self.physical_cells:
            if not isinstance(cell, tuple) or len(cell) != 3 or any(type(c) is not int for c in cell):
                raise ValueError('physical cells must be integer (x,y,z) tuples')
        if self.cover is not None and self.layer is not VisualLayer.OVERHEAD:
            raise ValueError('cover regions belong to overhead visuals')
        if self.parent_id == self.instance_id:
            raise ValueError('visual cannot attach to itself')

    @property
    def world_bounds(self) -> tuple[float, float, float, float]:
        """Artwork rectangle; bottom-center is the foot, independent of collision."""
        return (self.foot.x - self.width / 2, self.foot.y - self.height,
                self.foot.x + self.width / 2, self.foot.y)


def visual_sort_key(instance: WorldVisualInstance) -> tuple[int, float, float, float, int, str]:
    """Grounded + upright share a foot-sorted depth plane, not two rigid passes."""
    group = 30 if instance.layer in (VisualLayer.GROUNDED, VisualLayer.UPRIGHT) else int(instance.layer)
    return group, instance.foot.y, instance.foot.z, instance.foot.x, int(instance.layer), instance.instance_id


@dataclass(frozen=True, slots=True)
class WorldCamera:
    center: WorldFoot
    width_px: int
    height_px: int
    tile_px: float
    zoom: float = 1.0
    elevation_px_per_cell: float = 0.0
    anchor_x: float = 0.5
    anchor_y: float = 0.5

    def __post_init__(self) -> None:
        if type(self.width_px) is not int or type(self.height_px) is not int or min(self.width_px, self.height_px) <= 0:
            raise ValueError('viewport must have positive integer pixels')
        for name in ('tile_px', 'zoom', 'elevation_px_per_cell', 'anchor_x', 'anchor_y'):
            _number(getattr(self, name), name)
        if self.tile_px <= 0 or self.zoom <= 0 or self.elevation_px_per_cell < 0:
            raise ValueError('invalid camera scale/elevation')
        if not 0 <= self.anchor_x <= 1 or not 0 <= self.anchor_y <= 1:
            raise ValueError('camera anchor outside viewport')

    @property
    def scale(self) -> float:
        return self.tile_px * self.zoom

    def to_screen(self, point: WorldFoot) -> tuple[float, float]:
        return (self.width_px * self.anchor_x + (point.x - self.center.x) * self.scale,
                self.height_px * self.anchor_y + (point.y - self.center.y) * self.scale
                - (point.z - self.center.z) * self.elevation_px_per_cell * self.zoom)

    def to_world(self, screen_x: float, screen_y: float, *, ground_z: float = 0.0) -> WorldFoot:
        """Inverse on a KNOWN elevation plane; no hit-test of hidden geometry."""
        _number(screen_x, 'screen x')
        _number(screen_y, 'screen y')
        _number(ground_z, 'ground z')
        return WorldFoot(self.center.x + (screen_x - self.width_px * self.anchor_x) / self.scale,
                         self.center.y + (screen_y - self.height_px * self.anchor_y +
                         (ground_z - self.center.z) * self.elevation_px_per_cell * self.zoom) / self.scale,
                         ground_z)

    def bounds_for(self, item: WorldVisualInstance) -> tuple[float, float, float, float]:
        left, top, right, bottom = item.world_bounds
        x0, y0 = self.to_screen(WorldFoot(left, top, item.foot.z))
        x1, y1 = self.to_screen(WorldFoot(right, bottom, item.foot.z))
        return x0, y0, x1, y1


@dataclass(frozen=True, slots=True)
class SceneVisibility:
    """Caller-supplied current vision/memory; no memory grants entity sight."""
    current_cells: frozenset[tuple[int, int, int]]
    remembered_cells: frozenset[tuple[int, int, int]] = field(default_factory=frozenset)
    allowed_rooms: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not isinstance(self.current_cells, frozenset) or not isinstance(self.remembered_cells, frozenset) or not isinstance(self.allowed_rooms, frozenset):
            raise ValueError('visibility gates must be immutable sets')
        if len(self.current_cells) > MAX_VISIBLE_CELLS or len(self.remembered_cells) > MAX_VISIBLE_CELLS:
            raise ValueError('visibility window exceeds budget')
        for cell in self.current_cells | self.remembered_cells:
            if not isinstance(cell, tuple) or len(cell) != 3 or any(type(value) is not int for value in cell):
                raise ValueError('visibility cells must be integer xyz tuples')


@dataclass(frozen=True, slots=True)
class ProjectedVisual:
    instance: WorldVisualInstance
    screen_bounds: tuple[float, float, float, float]
    screen_foot: tuple[float, float]
    # All drawing must intersect these per-cell clip rectangles. A visible
    # resource cannot paint art into unexplored/remembered-only neighboring cells.
    clip_rects: tuple[tuple[float, float, float, float], ...]
    remembered_only: bool = False


@dataclass(frozen=True, slots=True)
class LocalCoverFade:
    cover_instance_id: str
    viewer_instance_id: str
    screen_center: tuple[float, float]
    radius_px: float
    local_alpha: float
    # This is a LOCAL mask, not opacity applied to the entire canopy.


@dataclass(frozen=True, slots=True)
class ProjectedScene:
    visuals: tuple[ProjectedVisual, ...]
    cover_fades: tuple[LocalCoverFade, ...]


def _overlaps(rect: tuple[float, float, float, float], width: int, height: int) -> bool:
    left, top, right, bottom = rect
    return right > 0 and bottom > 0 and left < width and top < height


def _clip_cells(instance: WorldVisualInstance, camera: WorldCamera,
                cells: frozenset[tuple[int, int, int]]) -> tuple[tuple[float, float, float, float], ...]:
    left, top, right, bottom = instance.world_bounds
    z = instance.foot.cell[2]
    # Intersection with caller's visibility mask, not just the source anchor.
    # The bounded viewport and limited object extent avoid any global scan.
    result = []
    # Clip the scan to the camera's world-space view plus a minimal border.
    # The z/elevation term is included when unprojecting the view corners.
    corner0 = camera.to_world(0, 0, ground_z=instance.foot.z)
    corner1 = camera.to_world(camera.width_px, camera.height_px, ground_z=instance.foot.z)
    x0 = max(floor(left), floor(corner0.x) - 1)
    x1 = min(ceil(right), ceil(corner1.x) + 1)
    y0 = max(floor(top), floor(corner0.y) - 1)
    y1 = min(ceil(bottom), ceil(corner1.y) + 1)
    for y in range(y0, y1):
        for x in range(x0, x1):
            if (x, y, z) not in cells:
                continue
            px, py = camera.to_screen(WorldFoot(x, y, instance.foot.z))
            result.append((px, py, px + camera.scale, py + camera.scale))
            if len(result) > MAX_CLIP_RECTS_PER_INSTANCE:
                raise ValueError('visual visibility mask exceeds bounded cell budget')
    return tuple(result)


def project_scene(instances: tuple[WorldVisualInstance, ...] | list[WorldVisualInstance],
                  camera: WorldCamera, visibility: SceneVisibility, *,
                  viewer_id: str | None = None, fade_alpha: float = 0.48,
                  fade_radius_cells: float = 0.9,
                  max_cutouts: int = MAX_COVER_CUTOUTS) -> ProjectedScene:
    """Bounded test scene projection. Caller must enforce clip_rects on pixels.

    Only a currently visible viewer may cause a cutout. NPCs, remembered-only
    objects and inaccessible rooms never become visible by fading a cover.
    No renderer, pygame, world generator or gameplay clock is involved.
    """
    if len(instances) > MAX_SCENE_INSTANCES:
        raise ValueError('scene instance budget exceeded')
    _number(fade_alpha, 'fade alpha')
    _number(fade_radius_cells, 'fade radius')
    if not 0.35 <= fade_alpha <= 0.60 or fade_radius_cells <= 0:
        raise ValueError('fade must be local and in the approved range')
    if type(max_cutouts) is not int or not 0 <= max_cutouts <= MAX_COVER_CUTOUTS:
        raise ValueError('invalid dynamic cover budget')
    ids = [item.instance_id for item in instances]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate visual instance IDs')
    projected = []
    for item in sorted(instances, key=visual_sort_key):
        if not item.authorized_visible:
            continue
        if item.room_id is not None and item.room_id not in visibility.allowed_rooms:
            continue
        seen = item.foot.cell in visibility.current_cells
        remembered = item.layer is VisualLayer.GROUND and item.foot.cell in visibility.remembered_cells
        if not seen and not remembered:
            continue
        bounds = camera.bounds_for(item)
        if not _overlaps(bounds, camera.width_px, camera.height_px):
            continue
        mask = visibility.current_cells if seen else visibility.remembered_cells
        rects = _clip_cells(item, camera, mask)
        if not rects:
            continue
        projected.append(ProjectedVisual(item, bounds, camera.to_screen(item.foot), rects,
                                         remembered_only=not seen))
    viewer = next((v for v in projected if v.instance.instance_id == viewer_id and
                   not v.remembered_only), None)
    fades: list[LocalCoverFade] = []
    if viewer is not None and max_cutouts:
        for v in projected:
            cover = v.instance
            if cover.layer is not VisualLayer.OVERHEAD or cover.cover is None:
                continue
            if cover.room_id != viewer.instance.room_id or not cover.cover.contains(viewer.instance.foot):
                continue
            vx, vy = viewer.screen_foot
            left, top, right, bottom = v.screen_bounds
            if not left <= vx <= right or not top <= vy <= bottom:
                continue
            if not any(cx0 <= vx <= cx1 and cy0 <= vy <= cy1 for cx0, cy0, cx1, cy1 in v.clip_rects):
                continue
            fades.append(LocalCoverFade(cover.instance_id, viewer_id,
                                        viewer.screen_foot, camera.scale * fade_radius_cells,
                                        fade_alpha))
            if len(fades) == max_cutouts:
                break
    return ProjectedScene(tuple(projected), tuple(fades[:max_cutouts]))
