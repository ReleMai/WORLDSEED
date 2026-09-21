#!/usr/bin/env python3
"""Multi-seed calibration for the staged WORLDGEN v8 elevation authority path."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from hashlib import blake2b
from pathlib import Path

from worldseed.config import DATA_DIR, WORLDGEN_PREVIEW_VERSION
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.world.generator import WorldGenerator
from worldseed.world.landforms import SEA_LEVEL_REFERENCE

DEFAULT_SEEDS = (
    "v8-calibration-00", "v8-calibration-01", "v8-calibration-02", "v8-calibration-03",
    "v8-calibration-04", "v8-calibration-05", "v8-calibration-06", "v8-calibration-07",
)


def _audit_seed(registry, seed_text: str, radius: int, spacing: int) -> dict:
    seed = seed_text.encode("utf-8")
    legacy = WorldGenerator(seed, registry, version=7)
    preview = WorldGenerator(seed, registry, version=WORLDGEN_PREVIEW_VERSION)
    rows = []
    elevations = {}
    provinces = Counter()
    digest = blake2b(digest_size=16, person=b"WS-V8-PHASE2")

    for y in range(-radius, radius + 1, spacing):
        for x in range(-radius, radius + 1, spacing):
            pos = WorldPos(x, y, 0)
            old = legacy.sample_fields(pos)
            new = preview.sample_fields(pos)
            landform = preview.landform_at(pos)
            values = (
                x, y, old.elevation, new.elevation, new.moisture,
                new.temperature, new.fertility, landform.province,
            )
            digest.update(("|".join(map(str, values)) + "\n").encode("utf-8"))
            rows.append((old, new, landform))
            elevations[(x, y)] = new.elevation
            provinces[landform.province] += 1

    gradients = []
    for (x, y), value in elevations.items():
        for dx, dy in ((spacing, 0), (0, spacing)):
            other = elevations.get((x + dx, y + dy))
            if other is not None:
                gradients.append(abs(other - value))

    total = max(1, len(rows))
    old_ocean = sum(old.elevation < SEA_LEVEL_REFERENCE for old, _, _ in rows)
    new_ocean = sum(new.elevation < SEA_LEVEL_REFERENCE for _, new, _ in rows)
    start_like = sum(
        26500 <= new.elevation <= 51500
        and new.moisture >= 22000
        and 17000 <= new.temperature <= 56500
        for _, new, _ in rows
    )
    deltas = [abs(new.elevation - old.elevation) for old, new, _ in rows]
    gradients.sort()
    p95 = gradients[min(len(gradients)-1, len(gradients)*95//100)] if gradients else 0
    return {
        "seed": seed_text,
        "fingerprint": digest.hexdigest(),
        "samples": len(rows),
        "v7_ocean_fraction": old_ocean / total,
        "v8_ocean_fraction": new_ocean / total,
        "start_like_fraction": start_like / total,
        "mean_absolute_elevation_delta": sum(deltas) // total,
        "sample_gradient_mean": sum(gradients) // max(1, len(gradients)),
        "sample_gradient_p95": p95,
        "province_fraction": {
            key: count / total for key, count in sorted(provinces.items())
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", action="append", dest="seeds")
    parser.add_argument("--radius", type=int, default=6144)
    parser.add_argument("--spacing", type=int, default=192)
    parser.add_argument("--out", type=Path, default=Path("v8_phase2_audit.json"))
    args = parser.parse_args()

    registry = ContentRegistry.load(DATA_DIR)
    seeds = tuple(args.seeds or DEFAULT_SEEDS)
    rows = [
        _audit_seed(registry, seed, max(1024, args.radius), max(16, args.spacing))
        for seed in seeds
    ]
    payload = {
        "preview_worldgen_version": WORLDGEN_PREVIEW_VERSION,
        "seed_count": len(rows),
        "results": rows,
    }
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for row in rows:
        print(
            f"{row['seed']}: ocean={row['v8_ocean_fraction']:.3f} "
            f"start_like={row['start_like_fraction']:.3f} "
            f"gradient_p95={row['sample_gradient_p95']} "
            f"fingerprint={row['fingerprint']}"
        )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
