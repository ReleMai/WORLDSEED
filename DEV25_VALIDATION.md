# RC14 Dev25 — WORLDGEN v8 Phase-2 authority staging

Scope: authoritative elevation/version boundary for explicit v8 preview contexts.

## Implemented

- Added `WORLDGEN_PREVIEW_VERSION = 8` while keeping `WORLDGEN_VERSION = 7`.
- Split `WorldGenerator.sample_fields()` at the compatibility boundary:
  - v1-v3 keep their original fractal fields.
  - v4-v7 keep the exact established regional elevation/moisture/temperature path.
  - explicit v8 uses `LandformSampler.elevation` as authoritative elevation.
- v8 continues to use the frozen v4 moisture and broad temperature driver during
  Phase 2; altitude cooling and fertility respond to the new elevation.
- Added `WorldGenerator.landform_at()` as an authoritative read only for v8
  surface worlds; legacy worlds return `None`.
- Added a v8-aware spawn search that scans broad fields out to multi-thousand-cell
  scales before exact terrain/resource refinement. The old v4-v7 576-cell spawn
  search is untouched for legacy/explicit-v7 contexts.
- Added a hard-coded representative v7 field fixture test so later v8 work cannot
  accidentally mutate the legacy field contract.
- Added `tools/audit_worldgen_v8_phase2.py` for eight-seed elevation/ocean/start
  suitability/gradient/province calibration.

## Validation available in this session

The representative v7 fixture values in the new test were independently
recomputed from the repository's current hash and v7 regional-field equations
for five coordinates, including negative coordinates.

The GitHub connector does not provide an executable checkout of the current
private repository, so the complete registry/WorldGenerator test suite was not
run here. Before promotion of ordinary new worlds to v8, run:

```bash
python -m unittest tests.test_worldgen_v8_landforms tests.test_worldgen_v8_phase2
python tools/audit_worldgen_v8_phase2.py
python tools/audit_worldgen_v8_landforms.py --seed worldgen-v8-audit
python tools/compare_worldgen_v7_v8.py --seed worldgen-v8-compare
```

## Promotion gate still closed

Dev25 intentionally does **not** set `WORLDGEN_VERSION = 8`. Promotion requires
the repository-level tests above, multi-seed calibration review, spawn-fairness
checks with resources enabled, and confirmation that v7 golden terrain remains
unchanged. This prevents an unvalidated generator from becoming the default for
new player saves.
