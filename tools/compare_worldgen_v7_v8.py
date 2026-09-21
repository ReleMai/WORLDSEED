#!/usr/bin/env python3
"""Compare frozen v7 elevation to the non-authoritative WORLDGEN v8 prototype."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.world.generator import WorldGenerator
from worldseed.world.landforms import SEA_LEVEL_REFERENCE


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", default="worldgen-v8-compare")
    parser.add_argument("--size", type=int, default=128)
    parser.add_argument("--spacing", type=int, default=64)
    parser.add_argument("--center-x", type=int, default=0)
    parser.add_argument("--center-y", type=int, default=0)
    parser.add_argument("--out", type=Path, default=Path("v8_landform_audit"))
    args = parser.parse_args()

    size = max(16, min(512, args.size))
    spacing = max(1, args.spacing)
    half = size * spacing // 2
    x0, y0 = args.center_x - half, args.center_y - half
    registry = ContentRegistry.load(DATA_DIR)
    generator = WorldGenerator(args.seed.encode("utf-8"), registry, version=7)

    args.out.mkdir(parents=True, exist_ok=True)
    csv_path = args.out / f"{args.seed}_v7_vs_v8.csv"
    summary_path = args.out / f"{args.seed}_v7_vs_v8.txt"

    rows = []
    v7_elevations = []
    v8_elevations = []
    absolute_deltas = []
    for gy in range(size):
        y = y0 + gy * spacing
        for gx in range(size):
            x = x0 + gx * spacing
            v7 = generator.sample_fields(WorldPos(x, y, 0))
            v8 = generator.prototype_landform_at(x, y)
            delta = int(v8.elevation) - int(v7.elevation)
            rows.append((
                x, y, v7.elevation, v8.elevation, delta,
                int(v7.elevation < SEA_LEVEL_REFERENCE), int(v8.ocean),
                v8.province, v8.mountain_chain, v8.structural_valley,
                v8.basin, v8.plateau,
            ))
            v7_elevations.append(v7.elevation)
            v8_elevations.append(v8.elevation)
            absolute_deltas.append(abs(delta))

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow((
            "x", "y", "v7_elevation", "v8_elevation", "delta",
            "v7_ocean", "v8_ocean", "v8_province", "v8_mountain_chain",
            "v8_structural_valley", "v8_basin", "v8_plateau",
        ))
        writer.writerows(rows)

    total = max(1, len(rows))
    v7_ocean = sum(value < SEA_LEVEL_REFERENCE for value in v7_elevations)
    v8_ocean = sum(value < SEA_LEVEL_REFERENCE for value in v8_elevations)
    with summary_path.open("w", encoding="utf-8") as handle:
        handle.write(f"seed={args.seed}\n")
        handle.write(f"samples={len(rows)} spacing={spacing}\n")
        handle.write(f"v7_elevation_min={min(v7_elevations)} v7_elevation_max={max(v7_elevations)}\n")
        handle.write(f"v8_elevation_min={min(v8_elevations)} v8_elevation_max={max(v8_elevations)}\n")
        handle.write(f"v7_ocean_fraction={v7_ocean / total:.4f}\n")
        handle.write(f"v8_ocean_fraction={v8_ocean / total:.4f}\n")
        handle.write(f"mean_absolute_elevation_delta={sum(absolute_deltas) // total}\n")

    print(summary_path.read_text(encoding="utf-8"), end="")
    print(f"wrote {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
