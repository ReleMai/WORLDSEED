#!/usr/bin/env python3
"""Audit WORLDGEN v8 topography and geological cave-mouth siting."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from worldseed.config import DATA_DIR, WORLDGEN_PREVIEW_VERSION
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.world.generator import WorldGenerator


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", default="v8-topography-audit")
    parser.add_argument("--radius", type=int, default=2048)
    parser.add_argument("--spacing", type=int, default=32)
    parser.add_argument("--out", type=Path, default=Path("v8_topography_audit.json"))
    args = parser.parse_args()

    registry = ContentRegistry.load(DATA_DIR)
    gen = WorldGenerator(args.seed.encode("utf-8"), registry, version=WORLDGEN_PREVIEW_VERSION)
    radius = max(256, int(args.radius))
    spacing = max(4, int(args.spacing))

    slopes = []
    relief = []
    ruggedness = []
    ridge = []
    valley = []
    land = 0
    samples = 0
    for y in range(-radius, radius + 1, spacing):
        for x in range(-radius, radius + 1, spacing):
            pos = WorldPos(x, y, 0)
            fields = gen.sample_fields(pos)
            top = gen.topography_at(pos)
            samples += 1
            land += fields.elevation >= 23800
            slopes.append(top.slope)
            relief.append(top.relief_raw)
            ruggedness.append(top.ruggedness)
            ridge.append(top.ridge_exposure)
            valley.append(top.valley_depth)

    def summarize(values):
        values = sorted(values)
        if not values:
            return {"min": 0, "mean": 0, "p95": 0, "max": 0}
        return {
            "min": values[0],
            "mean": sum(values) // len(values),
            "p95": values[min(len(values)-1, len(values)*95//100)],
            "max": values[-1],
        }

    cell = gen.caves.ENTRANCE_CELL
    cave_radius = max(4, radius // cell)
    entrances = []
    for cy in range(-cave_radius, cave_radius + 1):
        for cx in range(-cave_radius, cave_radius + 1):
            ent = gen.caves._entrance_for_cell(cx, cy)
            if ent is None:
                continue
            pos = WorldPos(ent.x, ent.y, 0)
            top = gen.topography_at(pos)
            geology = gen.landform_at(pos)
            entrances.append({
                "x": ent.x,
                "y": ent.y,
                "depth": ent.depth,
                "elevation": ent.elevation,
                "relief_raw": top.relief_raw,
                "slope": top.slope,
                "ruggedness": top.ruggedness,
                "province": geology.province,
                "mountain_chain": geology.mountain_chain,
                "plateau": geology.plateau,
            })

    payload = {
        "seed": args.seed,
        "preview_worldgen_version": WORLDGEN_PREVIEW_VERSION,
        "samples": samples,
        "land_fraction": land / max(1, samples),
        "slope": summarize(slopes),
        "relief_raw": summarize(relief),
        "ruggedness": summarize(ruggedness),
        "ridge_exposure": summarize(ridge),
        "valley_depth": summarize(valley),
        "cave_entrance_count": len(entrances),
        "cave_entrances": entrances,
    }
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"seed={args.seed} samples={samples} land={payload['land_fraction']:.3f} "
        f"slope_p95={payload['slope']['p95']} relief_p95={payload['relief_raw']['p95']} "
        f"caves={len(entrances)}"
    )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
