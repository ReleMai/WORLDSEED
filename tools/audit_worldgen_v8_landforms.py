#!/usr/bin/env python3
"""Export deterministic WORLDGEN v8 Phase-1 landform debug products.

No pygame/Pillow dependency is required. The PPM can be opened by many image
editors or converted later; the CSV records the sampled fields used for audits.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter
from hashlib import blake2b
from pathlib import Path

from worldseed.world.landforms import LandformSampler, SEA_LEVEL_REFERENCE


def _color(row):
    e = row.elevation
    if e < SEA_LEVEL_REFERENCE:
        depth = max(0, min(90, (SEA_LEVEL_REFERENCE - e) // 180))
        return (32 - depth // 5, 78 - depth // 8, 126 + depth)
    if row.province == "mountain_chain":
        snow = max(0, min(80, (e - 46000) // 120))
        return (128 + snow, 126 + snow, 120 + snow)
    if row.province == "plateau":
        return (137, 121, 75)
    if row.province == "basin":
        return (77, 108, 61)
    if row.province == "upland":
        return (92, 112, 67)
    return (91, 132, 73)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="worldgen-v8-audit")
    ap.add_argument("--size", type=int, default=192, help="samples per axis")
    ap.add_argument("--spacing", type=int, default=32, help="world cells per sample")
    ap.add_argument("--center-x", type=int, default=0)
    ap.add_argument("--center-y", type=int, default=0)
    ap.add_argument("--out", type=Path, default=Path("v8_landform_audit"))
    args = ap.parse_args()

    size = max(16, min(1024, args.size))
    spacing = max(1, args.spacing)
    sampler = LandformSampler(args.seed.encode("utf-8"))
    half = size * spacing // 2
    x0 = args.center_x - half
    y0 = args.center_y - half

    args.out.mkdir(parents=True, exist_ok=True)
    csv_path = args.out / f"{args.seed}_landforms.csv"
    ppm_path = args.out / f"{args.seed}_landforms.ppm"
    summary_path = args.out / f"{args.seed}_summary.txt"

    rows = []
    colors = []
    provinces = Counter()
    digest = blake2b(digest_size=20, person=b"WORLDSEED-V8-AUD")
    elevations = []

    for gy in range(size):
        y = y0 + gy * spacing
        color_row = []
        for gx in range(size):
            x = x0 + gx * spacing
            row = sampler.sample(x, y)
            values = (
                x, y, row.continentalness, row.tectonic_uplift,
                row.mountain_chain, row.basin, row.plateau,
                row.roughness, row.elevation, row.province,
            )
            rows.append(values)
            digest.update(("|".join(map(str, values)) + "\n").encode("utf-8"))
            provinces[row.province] += 1
            elevations.append(row.elevation)
            color_row.append(_color(row))
        colors.append(color_row)

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow((
            "x", "y", "continentalness", "tectonic_uplift", "mountain_chain",
            "basin", "plateau", "roughness", "elevation", "province",
        ))
        writer.writerows(rows)

    with ppm_path.open("wb") as f:
        f.write(f"P6\n{size} {size}\n255\n".encode("ascii"))
        for color_row in colors:
            for rgb in color_row:
                f.write(bytes(max(0, min(255, int(v))) for v in rgb))

    total = max(1, len(rows))
    ocean = sum(1 for e in elevations if e < SEA_LEVEL_REFERENCE)
    with summary_path.open("w", encoding="utf-8") as f:
        f.write(f"seed={args.seed}\n")
        f.write(f"algorithm_fingerprint={digest.hexdigest()}\n")
        f.write(f"samples={len(rows)} spacing={spacing}\n")
        f.write(f"elevation_min={min(elevations)} elevation_max={max(elevations)}\n")
        f.write(f"ocean_fraction={ocean / total:.4f}\n")
        for name, count in sorted(provinces.items()):
            f.write(f"province_{name}={count} ({count / total:.4f})\n")

    print(summary_path.read_text(encoding="utf-8"), end="")
    print(f"wrote {ppm_path}")
    print(f"wrote {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
