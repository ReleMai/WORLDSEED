#!/usr/bin/env python3
"""Export deterministic WORLDGEN v8 Phase-1 landform debug products.

No pygame/Pillow dependency is required. PPM previews can be opened by many
image editors or converted later; the CSV records the sampled fields used for
audits. The tool is observational and never creates game-world state.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter
from hashlib import blake2b
from pathlib import Path

from worldseed.world.landforms import LandformSampler, Q, SEA_LEVEL_REFERENCE


def _province_color(row):
    elevation = row.elevation
    if elevation < SEA_LEVEL_REFERENCE:
        depth = max(0, min(95, (SEA_LEVEL_REFERENCE - elevation) // 150))
        return (24, max(34, 92 - depth // 2), min(218, 126 + depth))
    if row.province == "mountain_chain":
        snow = max(0, min(90, (elevation - 43000) // 100))
        return (132 + snow, 130 + snow, 124 + snow)
    if row.province == "rift_valley":
        return (92, 119, 69)
    if row.province == "plateau":
        return (144, 121, 72)
    if row.province == "basin":
        return (72, 111, 65)
    if row.province == "upland":
        return (99, 116, 69)
    return (92, 137, 77)


def _height_color(row):
    if row.elevation < SEA_LEVEL_REFERENCE:
        depth = max(0, min(255, (SEA_LEVEL_REFERENCE - row.elevation) * 255 // SEA_LEVEL_REFERENCE))
        return (18, 54 + depth // 5, 105 + depth // 2)
    span = max(1, Q - SEA_LEVEL_REFERENCE)
    height = max(0, min(255, (row.elevation - SEA_LEVEL_REFERENCE) * 255 // span))
    return (56 + height * 3 // 4, 91 + height // 2, 53 + height * 2 // 3)


def _strength_color(value: int, channel: str):
    value = max(0, min(Q, int(value)))
    intensity = value * 255 // Q
    if channel == "mountain":
        return (50 + intensity * 4 // 5, 45 + intensity * 3 // 4, 40 + intensity * 2 // 3)
    return (35 + intensity // 4, 55 + intensity * 2 // 3, 55 + intensity // 5)


def _write_ppm(path: Path, grid) -> None:
    height = len(grid)
    width = len(grid[0]) if height else 0
    with path.open("wb") as handle:
        handle.write(f"P6\n{width} {height}\n255\n".encode("ascii"))
        for color_row in grid:
            for rgb in color_row:
                handle.write(bytes(max(0, min(255, int(v))) for v in rgb))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", default="worldgen-v8-audit")
    parser.add_argument("--size", type=int, default=192, help="samples per axis")
    parser.add_argument("--spacing", type=int, default=32, help="world cells per sample")
    parser.add_argument("--center-x", type=int, default=0)
    parser.add_argument("--center-y", type=int, default=0)
    parser.add_argument("--out", type=Path, default=Path("v8_landform_audit"))
    args = parser.parse_args()

    size = max(16, min(1024, args.size))
    spacing = max(1, args.spacing)
    sampler = LandformSampler(args.seed.encode("utf-8"))
    half = size * spacing // 2
    x0 = args.center_x - half
    y0 = args.center_y - half

    args.out.mkdir(parents=True, exist_ok=True)
    csv_path = args.out / f"{args.seed}_landforms.csv"
    province_path = args.out / f"{args.seed}_provinces.ppm"
    elevation_path = args.out / f"{args.seed}_elevation.ppm"
    mountain_path = args.out / f"{args.seed}_mountains.ppm"
    valley_path = args.out / f"{args.seed}_valleys.ppm"
    summary_path = args.out / f"{args.seed}_summary.txt"

    rows = []
    province_grid = []
    elevation_grid = []
    mountain_grid = []
    valley_grid = []
    elevation_values = []
    mountain_values = []
    valley_values = []
    provinces = Counter()
    digest = blake2b(digest_size=20, person=b"WORLDSEED-V8-AUD")

    for gy in range(size):
        y = y0 + gy * spacing
        province_row = []
        elevation_row = []
        mountain_row = []
        valley_row = []
        for gx in range(size):
            x = x0 + gx * spacing
            row = sampler.sample(x, y)
            values = (
                x, y, row.continentalness, row.tectonic_uplift,
                row.mountain_chain, row.structural_valley, row.basin,
                row.plateau, row.roughness, row.elevation, row.province,
            )
            rows.append(values)
            digest.update(("|".join(map(str, values)) + "\n").encode("utf-8"))
            provinces[row.province] += 1
            elevation_values.append(row.elevation)
            mountain_values.append(row.mountain_chain)
            valley_values.append(row.structural_valley)
            province_row.append(_province_color(row))
            elevation_row.append(_height_color(row))
            mountain_row.append(_strength_color(row.mountain_chain, "mountain"))
            valley_row.append(_strength_color(row.structural_valley, "valley"))
        province_grid.append(province_row)
        elevation_grid.append(elevation_row)
        mountain_grid.append(mountain_row)
        valley_grid.append(valley_row)

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow((
            "x", "y", "continentalness", "tectonic_uplift", "mountain_chain",
            "structural_valley", "basin", "plateau", "roughness", "elevation", "province",
        ))
        writer.writerows(rows)

    _write_ppm(province_path, province_grid)
    _write_ppm(elevation_path, elevation_grid)
    _write_ppm(mountain_path, mountain_grid)
    _write_ppm(valley_path, valley_grid)

    total = max(1, len(rows))
    ocean = sum(1 for value in elevation_values if value < SEA_LEVEL_REFERENCE)
    mountain = sum(1 for value in mountain_values if value >= 32000)
    valley = sum(1 for value in valley_values if value >= 32000)
    slope_values = []
    coast_edges = 0
    neighbor_edges = 0
    for gy in range(size):
        for gx in range(size):
            index = gy * size + gx
            elevation = elevation_values[index]
            if gx + 1 < size:
                other = elevation_values[index + 1]
                slope_values.append(abs(other - elevation))
                coast_edges += (elevation < SEA_LEVEL_REFERENCE) != (other < SEA_LEVEL_REFERENCE)
                neighbor_edges += 1
            if gy + 1 < size:
                other = elevation_values[index + size]
                slope_values.append(abs(other - elevation))
                coast_edges += (elevation < SEA_LEVEL_REFERENCE) != (other < SEA_LEVEL_REFERENCE)
                neighbor_edges += 1

    slope_values.sort()
    p95 = slope_values[min(len(slope_values) - 1, len(slope_values) * 95 // 100)] if slope_values else 0
    mean_slope = sum(slope_values) // max(1, len(slope_values))
    with summary_path.open("w", encoding="utf-8") as handle:
        handle.write(f"seed={args.seed}\n")
        handle.write(f"algorithm_fingerprint={digest.hexdigest()}\n")
        handle.write(f"samples={len(rows)} spacing={spacing}\n")
        handle.write(f"elevation_min={min(elevation_values)} elevation_max={max(elevation_values)}\n")
        handle.write(f"ocean_fraction={ocean / total:.4f}\n")
        handle.write(f"mountain_strength_fraction={mountain / total:.4f}\n")
        handle.write(f"structural_valley_fraction={valley / total:.4f}\n")
        handle.write(f"sample_gradient_mean={mean_slope} sample_gradient_p95={p95}\n")
        handle.write(f"coast_edge_fraction={coast_edges / max(1, neighbor_edges):.4f}\n")
        for name, count in sorted(provinces.items()):
            handle.write(f"province_{name}={count} ({count / total:.4f})\n")

    print(summary_path.read_text(encoding="utf-8"), end="")
    for path in (province_path, elevation_path, mountain_path, valley_path, csv_path):
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
