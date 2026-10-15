"""G1c/G2 opt-in **software** canopy proof, not an approved art replacement.

No gameplay queries here. The caller hands us *already prepared* resource rows
and authorized sight/roof exclusion membership. Default software rendering is
unchanged unless WORLDSEED_G2_CANOPY_PREVIEW=1. No atlas, GPU or save writes.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor
from typing import Mapping

from .worldspace import WorldCamera, WorldFoot, VisualLayer
from .worldspace_adapter import PreparedActor, PreparedScene, prepare_worldspace_scene

PREVIEW_SWITCH = 'WORLDSEED_G2_CANOPY_PREVIEW'
PREVIEW_FEATURE = 'core:oak_tree'   # single mature oak, not a new tree generator
MAX_TREE_SEARCH = 1024
MAX_PREVIEW_RADIUS = 8


@dataclass(frozen=True, slots=True)
class CanopyPreview:
    source: tuple[int, int, int]
    scene: PreparedScene


def select_oak(resource_by: Mapping, visible, *, player_x: int, player_y: int,
               z: int, excluded_cells=(), max_distance: int = MAX_PREVIEW_RADIUS):
    """Choose one currently visible mature oak, with no roof/room overlap.

    Candidate pool is exactly the prepared resource viewport, never a region
    scan or feature_at() query. Exclusion checks conservatively reject trees
    near roofs, building shells and obstructing interior scenery.
    """
    if not 0 <= max_distance <= MAX_PREVIEW_RADIUS or len(resource_by) > MAX_TREE_SEARCH:
        raise ValueError('unbounded canopy preview search')
    candidates = []
    excluded = set(excluded_cells)
    for (x, y, cz), (feature, _) in resource_by.items():
        if cz != z or feature.feature_id != PREVIEW_FEATURE or feature.stage != 'mature':
            continue
        if f'{x},{y},{z}' not in visible:
            continue
        if max(abs(x-player_x), abs(y-player_y)) > max_distance:
            continue
        # Worst-case provisional oak coverage is 3 x 2.7 cells. Restrict
        # selected preview to areas clear of roof/structure privacy concerns.
        if any((u, v, z) in excluded for u in range(x-2, x+3)
               for v in range(y-2, y+3)):
            continue
        candidates.append((abs(x-player_x)+abs(y-player_y), y, x, z))
    if not candidates:
        return None
    _, y, x, cz = min(candidates)
    return x, y, cz


def camera_for_live_grid(*, left: int, top: int, grid_x: int, grid_y: int,
                         viewport_x: int, viewport_y: int,
                         viewport_w: int, viewport_h: int, tile_px: int, z: int):
    """Match existing fractional software viewport without changing hit tests."""
    if tile_px <= 0:
        raise ValueError('invalid live tile size')
    return WorldCamera(
        WorldFoot(left - (grid_x-viewport_x)/tile_px,
                  top - (grid_y-viewport_y)/tile_px, z),
        viewport_w, viewport_h, tile_px, anchor_x=0, anchor_y=0,
    )


def prepare_one_oak(*, resource_by, resource_defs, resource_style,
                    current_cells, discovered_cells, player_x: int,
                    player_y: int, player_z: int, player_fx: float,
                    player_fy: float, camera: WorldCamera,
                    excluded_cells=()):
    """Create the G1b scene of ONE already prepared tree and the player.

    The physical trunk cell, resource and harvest/stump lifecycle all stay
    owned by ResourceSystem; this just describes screen-space attachments.
    """
    key = select_oak(resource_by, current_cells, player_x=player_x,
                     player_y=player_y, z=player_z,
                     excluded_cells=excluded_cells)
    if key is None:
        return None
    if camera.center.z != player_z:
        raise ValueError('live projection camera elevation mismatch')
    viewer = PreparedActor('player', 'core:player',
                           WorldFoot(player_x+player_fx, player_y+player_fy,
                                     player_z), True, is_viewer=True)
    scene = prepare_worldspace_scene(
        camera=camera, resource_by={key: resource_by[key]},
        resource_defs=resource_defs, resource_style=resource_style,
        current_cells=current_cells, discovered_cells=discovered_cells,
        visibility_key=lambda x,y,z: f'{x},{y},{z}',
        actors=(viewer,), z=player_z,
    )
    if not any(v.instance.layer is VisualLayer.OVERHEAD
               for v in scene.projection.visuals):
        return None
    return CanopyPreview(key, scene)


def _blit_visible(pg, screen, source, x, y, visual, viewport):
    """Blit under exact current-sight cell clips, restoring outer map clip."""
    old = screen.get_clip()
    try:
        outer = pg.Rect(viewport).clip(old)
        for c0, c1, c2, c3 in visual.clip_rects:
            region = pg.Rect(floor(c0)+viewport.x, floor(c1)+viewport.y,
                             ceil(c2)-floor(c0), ceil(c3)-floor(c1))
            region = region.clip(outer)
            if region.width > 0 and region.height > 0:
                screen.set_clip(region)
                screen.blit(source, (x, y))
    finally:
        screen.set_clip(old)


def _bounds(pg, visual, viewport):
    x0, y0, x1, y1 = visual.screen_bounds
    x, y = round(x0)+viewport.x, round(y0)+viewport.y
    w, h = max(1, round(x1-x0)), max(1, round(y1-y0))
    return pg.Rect(x, y, w, h)


def _parts(preview, layer):
    return (v for v in preview.scene.projection.visuals
            if v.instance.layer is layer)


def draw_shadow(pg, screen, preview: CanopyPreview, viewport) -> None:
    """Independent ground-contact canopy shadow, never faded with leaves."""
    for v in _parts(preview, VisualLayer.GROUND_SHADOW):
        # The G1a shadow visual uses a ground-foot attachment; a projected
        # ground ellipse must be centered *at that foot*, not above by 1 cell.
        foot_x, foot_y = v.screen_foot
        scale = preview.scene.camera.scale
        w, h = max(2, round(v.instance.width*scale)), max(2, round(.57*scale))
        img = pg.Surface((w, h), pg.SRCALPHA)
        pg.draw.ellipse(img, (19, 33, 23, 72), (0, 0, w, h))
        x = round(foot_x+viewport.x-w/2)
        y = round(foot_y+viewport.y-h*.96)
        _blit_visible(pg, screen, img, x, y, v, viewport)


def draw_trunk(pg, screen, preview: CanopyPreview, viewport) -> None:
    """Temporary recognizable bark silhouette; original trunk hitbox unchanged."""
    for v in _parts(preview, VisualLayer.GROUNDED):
        rect = _bounds(pg, v, viewport)
        img = pg.Surface(rect.size, pg.SRCALPHA)
        w, h = rect.size
        cx = w//2
        bark_w = max(3, round(w*.28))
        stem = pg.Rect(cx-bark_w//2, max(0,h-round(h*.76)), bark_w, max(1,round(h*.72)))
        pg.draw.rect(img, (73, 49, 30, 255), stem, border_radius=max(1,bark_w//6))
        pg.draw.line(img, (130, 93, 54, 240),
                     (stem.x+max(1,bark_w//3), stem.y+3),
                     (stem.x+max(1,bark_w//3), stem.bottom-2), max(1,bark_w//7))
        pg.draw.polygon(img, (67, 43, 28, 255),
                        [(cx, h-4), (max(0,cx-bark_w), h-1), (min(w-1,cx+bark_w),h-1)])
        _blit_visible(pg, screen, img, rect.x, rect.y, v, viewport)


def draw_crown(pg, screen, preview: CanopyPreview, viewport) -> None:
    """Separate local-alpha crown over actors, exact sight clipped, no hits."""
    fade_by_id = {f.cover_instance_id: f for f in preview.scene.projection.cover_fades}
    for v in _parts(preview, VisualLayer.OVERHEAD):
        rect = _bounds(pg, v, viewport)
        w, h = rect.size
        img = pg.Surface((w, h), pg.SRCALPHA)
        # Provisional geometry for game-engine inspection, NOT approved oak art.
        pg.draw.ellipse(img, (28, 68, 43, 237),
                        (int(w*.05), int(h*.09), int(w*.90), int(h*.79)))
        pg.draw.ellipse(img, (48, 103, 52, 233),
                        (int(w*.09), int(h*.02), int(w*.56), int(h*.67)))
        pg.draw.ellipse(img, (54, 115, 56, 226),
                        (int(w*.43), int(h*.17), int(w*.49), int(h*.57)))
        fade = fade_by_id.get(v.instance.instance_id)
        if fade is not None:
            # Multiply alpha only in the local player-foot circle. Full canopy
            # remains opaque away from the player, including other NPC areas.
            mask = pg.Surface((w,h), pg.SRCALPHA)
            mask.fill((255,255,255,255))
            cx = round(fade.screen_center[0]+viewport.x-rect.x)
            cy = round(fade.screen_center[1]+viewport.y-rect.y)
            radius = max(2, round(fade.radius_px))
            pg.draw.circle(mask,(255,255,255,231),(cx,cy),radius)
            pg.draw.circle(mask,(255,255,255,184),(cx,cy),max(1,round(radius*.84)))
            pg.draw.circle(mask,(255,255,255,round(255*fade.local_alpha)),
                           (cx,cy),max(1,round(radius*.70)))
            img.blit(mask, (0,0), special_flags=pg.BLEND_RGBA_MULT)
        _blit_visible(pg, screen, img, rect.x, rect.y, v, viewport)
