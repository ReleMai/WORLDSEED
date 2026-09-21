# RC14 Phase 0 — Frozen RC13 Baseline

Baseline archive: `WORLDSEED v1.0 RC13 - Seeded World Preparation`.

This file freezes the RC13 reference before the Embodied World architecture changes. It is intentionally based on worldgen v4 / resourcegen v3; RC14 Phase 2 hydrology remains observational so these terrain fingerprints must continue to match until Phase 3 deliberately promotes new-world geography to v5.

## Golden seeds

The fingerprint is BLAKE2b-128 over terrain content IDs for the 3×3 surface chunk square centered on chunk `(0,0)`, iterated chunk rows `-1..1`, then local chunk array order. Personalization string: `WS-RC13-BASE`.

| Seed | RC13 v4 terrain fingerprint |
|---|---|
| rc14-golden-00 | `6d36ad680a8672589485deea15faa001` |
| rc14-golden-01 | `d4a87ae513f76f135f1c508d2697e75e` |
| rc14-golden-02 | `b429b73f991db55f65e023e36ea934c3` |
| rc14-golden-03 | `d4a87ae513f76f135f1c508d2697e75e` |
| rc14-golden-04 | `1f6c7dd3253896314e08d69c62c484a0` |
| rc14-golden-05 | `d1b7b0ed88a03ec0bd74c25aadd1154d` |
| rc14-golden-06 | `d4a87ae513f76f135f1c508d2697e75e` |
| rc14-golden-07 | `5f92a259c9def3d9688054d7bf67a137` |
| rc14-golden-08 | `dcdcd19ce3e378068fd83acadbe3ed60` |
| rc14-golden-09 | `125c9cce4f0d2afd248f4b1fefb6d6c3` |

## Baseline versions

- save schema: 3
- worldgen: 4
- resourcegen: 3
- RC13 automated tests collected in this archive: 176

## Baseline performance in this handoff environment

- `tools/bench_worldgen.py`: 100 chunks in 1.851 s, ~18.51 ms/chunk
- `tools/bench_movement.py`: 400 warm-cache steps, ~0.387 ms movement and ~3.372 ms movement + 100×30 render

The original RC13 report records startup preparation at roughly 20–25 seconds for the radius-8 / 17×17 opening envelope on its validation machine. Cross-machine wall-clock numbers are observational; deterministic fingerprints and invariants are the compatibility gate.
