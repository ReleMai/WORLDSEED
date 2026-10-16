"""Authoritative, bounded 500-unit indoor exploration visibility.

Never mutates a plan, consults exterior terrain, or discovers private rooms.
The same conservative convex wall-fan test used for GPU sight gates saved
indoor floor memory. A single integer cell index identifies one fixed 0.5m
square of a *specific* persisted InteriorPlan (and thus a specific floor).
"""
from __future__ import annotations

from math import ceil

from worldseed.systems.illumination import detection_scale, indoor_light

GRID = 500
MAX_MEMORY_CELLS = 4096
MAX_SIGHT_RADIUS = 12000


def _cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def _hull(points):
    points = sorted(set(points))
    halves = []
    for values in (points, list(reversed(points))):
        half = []
        for point in values:
            while len(half) > 1 and _cross(half[-2], half[-1], point) <= 0:
                half.pop()
            half.append(point)
        halves.append(half[:-1])
    return tuple(halves[0] + halves[1])


def _intersects_wall(polygon, wall):
    ax, ay, bx, by = wall
    box = ((ax, ay), (bx-1, ay), (bx-1, by-1), (ax, by-1))
    axes = [(1, 0), (0, 1)]
    axes.extend((b[1]-a[1], a[0]-b[0])
                for a, b in zip(polygon, (*polygon[1:], polygon[0])))
    for dx, dy in axes:
        values = tuple(x*dx+y*dy for x, y in polygon)
        other = tuple(x*dx+y*dy for x, y in box)
        if max(values) < min(other) or max(other) < min(values):
            return False
    return True


def _rect_visible(px, py, bounds, walls):
    """An entire floor rectangle must have an unobstructed wall fan."""
    a, b, c, d = bounds
    polygon = _hull(((px, py), (a, b), (c-1, b), (c-1, d-1), (a, d-1)))
    if len(polygon) < 3:
        return False
    left, right = min(px, a), max(px, c-1)
    top, bottom = min(py, b), max(py, d-1)
    for wall in walls:
        x, y, x1, y1 = wall
        if x > right or x1-1 < left or y > bottom or y1-1 < top:
            continue
        if _intersects_wall(polygon, wall):
            return False
    return True


def grid_columns(plan):
    return (plan.width + GRID - 1)//GRID


def grid_rect(plan, index):
    """Saved cell indices are plan-local; invalid or oversized values stay hidden."""
    cols = grid_columns(plan)
    if cols <= 0 or type(index) is not int or index < 0:
        return None
    x, y = (index % cols)*GRID, (index // cols)*GRID
    if x >= plan.width or y >= plan.height:
        return None
    return (x, y, min(plan.width, x+GRID), min(plan.height, y+GRID))


def visible_grid_cells(plan, px, py, minute, ambient_light, sources=()):
    """Compute only the bounded viewer neighborhood, not all saved floors.

    These deterministic whole-rectangle checks are at least as conservative as
    the renderer's wall/light admission. No actor, fixture or room name is saved.
    """
    cols = grid_columns(plan)
    rows = (plan.height + GRID - 1)//GRID
    if not 0 < cols*rows <= MAX_MEMORY_CELLS or len(plan.walls) > 256:
        return ()
    walls = tuple((w.x, w.y, w.x+w.w, w.y+w.h) for w in plan.walls)
    r = MAX_SIGHT_RADIUS
    discovered = []
    for cy in range(max(0,(py-r)//GRID), min(rows,(py+r)//GRID+2)):
        for cx in range(max(0,(px-r)//GRID), min(cols,(px+r)//GRID+2)):
            rect = grid_rect(plan, cy*cols+cx)
            if rect is None:
                continue
            a,b,c,d=rect
            corners=((a,b),(c-1,b),(c-1,d-1),(a,d-1))
            # Reject on maximum sight radius before evaluating expensive lighting.
            if any((x-px)**2+(y-py)**2 > r*r for x,y in corners):
                continue
            if not _rect_visible(px,py,rect,walls):
                continue
            authorized=True
            for x,y in corners:
                light=indoor_light(plan,x,y,minute,ambient_light=ambient_light,sources=sources)
                radius=max(1000,MAX_SIGHT_RADIUS*detection_scale(light)//65535)
                if (x-px)**2+(y-py)**2>radius*radius:
                    authorized=False
                    break
            if authorized:
                discovered.append(cy*cols+cx)
    return tuple(discovered)
