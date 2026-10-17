"""Viewport-local transparency for authorised overhead cover, including roofs.

The producer supplies only *already visible* cover clips. This never requests
private rooms or changes collisions: it merely reveals a nearby actor through
the pixels that would otherwise occlude their body.
"""
from __future__ import annotations

from .worldspace import WorldFoot

LOCAL_ALPHA = .08
RADIUS_CELLS = 1.12


def overlaps(a, b):
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def cover_fade(camera, viewer: WorldFoot | None, bounds, clips):
    """Return fade shader kwargs, or empty dict if cover misses the actor.

    Scissor clipping remains authoritative: even a full-frame roof image
    cannot become a sight or roof-collision workaround.
    """
    if viewer is None or not clips:
        return {}
    x, y = camera.to_screen(viewer)
    scale = camera.scale
    player_body = (x-.40*scale, y-1.5*scale,
                   x+.40*scale, y+.08*scale)
    if not overlaps(player_body,bounds):
        return {}
    if not any(overlaps(rect,bounds) and overlaps(rect,player_body)
               for rect in clips):
        return {}
    return dict(fade_center=(x,y-.76*scale),
                fade_radius=RADIUS_CELLS*scale,local_alpha=LOCAL_ALPHA)
