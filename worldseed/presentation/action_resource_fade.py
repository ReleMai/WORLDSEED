"""Bounded, detached harvest artwork fading; no world or resource queries.

Only previously admitted art for the committed GatherCommand target survives.
Each new frame re-clips it against current sight; it never becomes a target,
collision body, remembered resource, or source of new knowledge.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from math import ceil, floor

from .worldspace import WorldFoot

MAX_RESOURCE_PARTS = 8
MAX_FADE_CLIPS = 2048


@dataclass(frozen=True, slots=True)
class ResourceFade:
    cell: tuple[int, int, int]
    commands: tuple
    camera: object
    origin: tuple[int, int]
    followers: tuple[tuple[str, ...], ...]


def capture_resource_fade(command, snapshot, commands, viewport):
    """Read a cached pre-redraw snapshot after command effects have committed."""
    if (type(command).__name__ != 'GatherCommand' or snapshot is None
            or snapshot.interior or viewport is None):
        return None
    x, y, z = snapshot.viewer.cell
    cell = (x + int(command.dx), y + int(command.dy), z)
    if cell not in snapshot.current_cells:
        return None
    feature = next((row for pos, row in snapshot.resources if pos == cell), None)
    if feature is None:
        return None
    prefix = f'feature:{cell[2]}:{cell[0]}:{cell[1]}:{feature.feature_id}:'
    parts = tuple(row for row in commands if row.visual_id.startswith(prefix)
                  and not row.remembered)[:MAX_RESOURCE_PARTS]
    followers = tuple(tuple(other.visual_id for other in commands[index + 1:index + 17]
                            if not other.visual_id.startswith(prefix))
                      for index, row in enumerate(commands) if row in parts)
    return ResourceFade(cell, parts, snapshot.camera, viewport.topleft, followers) if parts else None


def merge_resource_fade(commands, ghosts, fade):
    """Retain original depth neighbors and the player's final self-visible pass."""
    result = list(commands)
    for ghost in ghosts:
        original = ghost.visual_id.removeprefix('action-fade:')
        index = next(i for i, row in enumerate(fade.commands) if row.visual_id == original)
        by_id = {row.visual_id: i for i, row in enumerate(result)}
        slot = next((by_id[uid] for uid in fade.followers[index] if uid in by_id),
                    by_id.get('actor:gpu-viewer', len(result)))
        result.insert(slot, ghost)
    return tuple(result)


def resource_fade_commands(fade, snapshot, viewport, fraction, live_commands):
    """Reproject cached art on resize/zoom and intersect old and current sight."""
    if (fade is None or snapshot is None or snapshot.interior or viewport is None
            or fade.cell not in snapshot.current_cells or snapshot.camera.center.z != fade.cell[2]):
        return ()
    fraction = max(0., min(1., float(fraction)))
    if fraction >= 1.:
        return ()
    current_ids = {row.visual_id for row in live_commands}
    camera = snapshot.camera
    ratio = camera.scale / fade.camera.scale

    def point(x, y):
        world = fade.camera.to_world(x - fade.origin[0], y - fade.origin[1], ground_z=fade.cell[2])
        px, py = camera.to_screen(world)
        return px + viewport.x, py + viewport.y

    def rectangle(row):
        return (*point(row[0], row[1]), *point(row[2], row[3]))

    result = []
    # Alpha-only fading leaves the already committed stump/depletion art below.
    opacity = 1. - fraction * fraction * (3. - 2. * fraction)
    for row in fade.commands:
        if row.visual_id in current_ids:
            continue  # Partial harvest did not remove this visual stage.
        bounds = rectangle(row.bounds)
        world0 = camera.to_world(bounds[0] - viewport.x, bounds[1] - viewport.y,
                                 ground_z=fade.cell[2])
        world1 = camera.to_world(bounds[2] - viewport.x, bounds[3] - viewport.y,
                                 ground_z=fade.cell[2])
        clips = []
        old_clips = tuple(rectangle(clip) for clip in row.clip_rects)
        for y in range(floor(world0.y), ceil(world1.y)):
            for x in range(floor(world0.x), ceil(world1.x)):
                if (x, y, fade.cell[2]) not in snapshot.current_cells:
                    continue
                a, b = camera.to_screen(WorldFoot(x, y, fade.cell[2]))
                c, d = camera.to_screen(WorldFoot(x + 1, y + 1, fade.cell[2]))
                for old in old_clips:
                    clip = (max(old[0], a + viewport.x, viewport.left),
                            max(old[1], b + viewport.y, viewport.top),
                            min(old[2], c + viewport.x, viewport.right),
                            min(old[3], d + viewport.y, viewport.bottom))
                    if clip[0] < clip[2] and clip[1] < clip[3]:
                        clips.append(clip)
                        if len(clips) >= MAX_FADE_CLIPS:
                            break
                if len(clips) >= MAX_FADE_CLIPS:
                    break
            if len(clips) >= MAX_FADE_CLIPS:
                break
        if clips:
            result.append(replace(row, visual_id='action-fade:' + row.visual_id,
                bounds=bounds, clip_rects=tuple(clips), opacity=row.opacity * opacity,
                precipitation_cover=False,
                fade_center=point(*row.fade_center), fade_radius=row.fade_radius * ratio,
                sway_px=min(6., row.sway_px * ratio), sight_center=point(*row.sight_center),
                sight_radius=row.sight_radius * ratio,
                sight_mask=(replace(row.sight_mask, bounds=rectangle(row.sight_mask.bounds))
                            if row.sight_mask is not None else None)))
    return tuple(result)
