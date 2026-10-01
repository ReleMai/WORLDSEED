"""Deterministic, bounded successor placement anchored to the death location."""
from __future__ import annotations

from worldseed.core.coords import WorldPos


def nearby_land_spawn(origin: WorldPos, terrain_at, terrains, safe_cell, known_cells=()) -> WorldPos | None:
    """Probe nearby land first; validate actual projected/delta/occupancy state.

    Return None on failure rather than silently substituting an ocean origin.
    Potential queries don't materialize the intervening world.
    """
    seen = set()
    checked = 0

    def check(x, y):
        nonlocal checked
        key = (int(x), int(y))
        if key in seen: return None
        seen.add(key)
        pos = WorldPos(*key, 0)
        terrain = terrains.get(terrain_at(pos))
        if terrain is None or not terrain.passable or "water" in terrain.tags: return None
        if checked >= 512: return None
        checked += 1
        return pos if safe_cell(pos) else None

    for radius in range(0, 33):
        perimeter = [(dx, dy) for dy in range(-radius, radius+1) for dx in range(-radius, radius+1)
                     if max(abs(dx), abs(dy)) == radius]
        for dx, dy in sorted(perimeter, key=lambda p: (abs(p[0])+abs(p[1]), p[1], p[0])):
            found = check(origin.x+dx, origin.y+dy)
            if found is not None: return found
    known = sorted(set(known_cells), key=lambda p: (abs(p[0]-origin.x)+abs(p[1]-origin.y), p[1], p[0]))
    for x, y in known[:128]:
        found = check(x, y)
        if found is not None: return found
    # Sparse rings also handle deaths far offshore, without realizing each
    # intervening chunk or civilization.
    for radius in (64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384):
        for step in range(-8, 9):
            offset = step*radius//8
            for dx, dy in ((offset,-radius),(-radius,offset),(radius,offset),(offset,radius)):
                found = check(origin.x+dx, origin.y+dy)
                if found is not None: return found
    return None
