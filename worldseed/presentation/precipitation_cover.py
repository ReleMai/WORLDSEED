"""Select detached, current overhead cover for visual precipitation interception.

The producer owns semantic roof/canopy classification and exact sight clips.
This helper never infers cover from asset names or sprite bounds, queries a
world, expands visibility, or changes gameplay shelter/weather authority.
"""
from __future__ import annotations

from .gl_worldspace import MAX_COMMANDS, SpriteCommand

# Existing viewport producers admit at most 1,024 resource crowns, 1,024
# independent roof objects and 64 public building shells. Do not silently drop
# a cover when these contracts change; fail at the detached frame boundary.
MAX_PRECIPITATION_COVERS = 2112


def cover_commands(commands) -> tuple[SpriteCommand, ...]:
    """Return original immutable commands, preserving clips, art alpha and sway.

    Cosmetic cutouts are deliberately retained here: the coverage-only shader
    ignores them while the ordinary scene continues to show the player clearly.
    Remembered art and departing harvest ghosts cannot affect current weather.
    """
    covers = []
    for index, command in enumerate(commands):
        if index >= MAX_COMMANDS:
            raise ValueError('precipitation source exceeds bounded frame budget')
        if not isinstance(command, SpriteCommand):
            raise ValueError('precipitation cover requires detached sprite commands')
        if (not command.precipitation_cover or command.remembered
                or command.visual_id.startswith(('memory:', 'action-fade:'))):
            continue
        if not command.clip_rects:
            continue
        covers.append(command)
        if len(covers) > MAX_PRECIPITATION_COVERS:
            raise ValueError('precipitation cover exceeds bounded overhead budget')
    return tuple(covers)
