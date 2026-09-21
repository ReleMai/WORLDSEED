#!/usr/bin/env python3
"""Exercise default WORLDGEN v8 startup selection across deterministic seeds.

This is a release/audit tool, not part of ordinary startup. It creates temporary
save databases, uses the real new-world generator/resource stack, finds a spawn,
prepares hydrology around it, and reports whether the final spawn is dry,
passable and locally connected.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from collections import deque
from pathlib import Path

from worldseed.app import _find_spawn, _pregen_bounds, _relocate_spawn_after_hydrology
from worldseed.config import DATA_DIR, WORLDGEN_VERSION
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.persistence.database import WorldDatabase
from worldseed.systems.resources import ResourceSystem
from worldseed.systems.state import LivingWorldState
from worldseed.world.generator import WorldGenerator
from worldseed.world.hydrology import HydrologyGenerator
from worldseed.world.world import World

DEFAULT_SEEDS = tuple(f"v8-startup-{i:02d}" for i in range(8))


def _reachable(world: World, resources: ResourceSystem, origin: WorldPos, radius: int = 14) -> int:
    def good(pos: WorldPos) -> bool:
        return world.is_passable(pos) and not resources.blocks_movement(pos)

    if not good(origin):
        return 0
    seen = {(origin.x, origin.y)}
    queue = deque([origin])
    while queue:
        cur = queue.popleft()
        for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
            nx, ny = cur.x + dx, cur.y + dy
            if (nx, ny) in seen or max(abs(nx-origin.x), abs(ny-origin.y)) > radius:
                continue
            nxt = WorldPos(nx, ny, 0)
            if not good(nxt):
                continue
            seen.add((nx, ny))
            queue.append(nxt)
    return len(seen)


def _audit_one(registry, seed_text: str) -> dict:
    seed = seed_text.encode("utf-8")
    with tempfile.TemporaryDirectory() as td:
        db = WorldDatabase.create(Path(td) / "audit.db", seed_text, seed.hex())
        try:
            generator = WorldGenerator(seed, registry)
            world = World(generator, registry, db, auto_hydrology=False)
            state = LivingWorldState()
            resources = ResourceSystem(state, registry, seed, world)
            proposed = _find_spawn(world, "wanderer", resources)

            hydrology = HydrologyGenerator(generator, db)
            x0, y0, x1, y1 = _pregen_bounds(proposed, 2)
            hydrology.prepare_world_bounds(x0, y0, x1, y1, persist=False)
            generator.attach_hydrology(hydrology)
            final = _relocate_spawn_after_hydrology(world, proposed, resources)

            tile = world.tile_at(final)
            reachable = _reachable(world, resources, final)
            return {
                "seed": seed_text,
                "worldgen_version": generator.version,
                "proposed_spawn": [proposed.x, proposed.y],
                "final_spawn": [final.x, final.y],
                "terrain": tile.terrain_id,
                "dry": "water" not in tile.terrain.tags,
                "passable": bool(tile.terrain.passable),
                "reachable_14": reachable,
                "landform": getattr(generator.landform_at(final), "province", None),
            }
        finally:
            db.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", action="append", dest="seeds")
    parser.add_argument("--out", type=Path, default=Path("v8_startup_audit.json"))
    args = parser.parse_args()

    registry = ContentRegistry.load(DATA_DIR)
    rows = [_audit_one(registry, seed) for seed in tuple(args.seeds or DEFAULT_SEEDS)]
    payload = {"worldgen_version": WORLDGEN_VERSION, "results": rows}
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for row in rows:
        print(
            f"{row['seed']}: spawn={row['final_spawn']} terrain={row['terrain']} "
            f"reachable={row['reachable_14']} landform={row['landform']}"
        )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
