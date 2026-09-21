# RC14 Dev27 — WORLDGEN v8 promotion

Scope: promote WORLDGEN v8 from staged preview to the default generator for all
newly created worlds while preserving every existing world's recorded geography.

## Promotion changes

- `WORLDGEN_VERSION = 8`.
- `WORLDGEN_PREVIEW_VERSION` remains as an alias to the current v8 contract so
  existing audit tooling does not need a flag rename.
- `WorldDatabase.create()` now records worldgen version 8 for new saves through
  the existing version metadata contract.
- `WorldDatabase.open()` still reads and preserves the version already stored
  in the save. There is no v7 -> v8 geography migration.
- The generator's explicit `version <= 7` field path remains frozen.
- Default `WorldGenerator(...)` instances now use:
  - v8 geological elevation,
  - v8 derived topography,
  - v8 geological cave-mouth siting,
  - the existing independently versioned hydrology/coast projection,
  - the existing v4-derived moisture/temperature fields until Phase 3.
- The v8-aware large-scale spawn search from Dev25 is now the normal new-world
  startup path.
- Added a startup audit that uses the real default generator/resource/hydrology
  stack and reports final spawn dryness, passability, local reachability and
  landform type across deterministic seeds.
- Updated project agent/system/readme contracts so future work treats v8 as the
  current new-world generator and v1-v7 as immutable legacy geography.

## Regression coverage added/updated

- `tests/test_worldgen_v8_phase2.py` now requires default WORLDGEN v8 while
  continuing to hard-code representative v7 field tuples.
- `tests/test_worldgen_v8_promotion.py` verifies:
  - new databases record v8,
  - a stored v7 save remains v7 after reopen,
  - default generators are v8 while explicit v7 generators remain legacy.
- `tests/test_rc14_hydrology.py` now expects the current new-world version to
  be 8 while retaining the frozen RC13/v4 terrain fingerprint gate.
- Existing v7 cave tests continue to instantiate `version=7` explicitly, so
  v8 promotion does not rewrite their contract.

## Required executable validation

The connected GitHub environment can read/write the private repository but does
not provide a full executable checkout, so the full suite is not claimed as run
in this work session. Run:

```bash
python -m unittest \
  tests.test_worldgen_v8_landforms \
  tests.test_worldgen_v8_phase2 \
  tests.test_worldgen_v8_topography \
  tests.test_worldgen_v8_promotion \
  tests.test_rc14_hydrology \
  tests.test_rc13_pregeneration \
  tests.test_rc10_worldgen \
  tests.test_dev16_caves_crafting

python tools/audit_worldgen_v8_phase2.py
python tools/audit_worldgen_v8_topography.py
python tools/audit_worldgen_v8_startup.py
python tools/audit_traversability.py
python tools/bench_pregeneration.py
```

## Compatibility statement

Dev27 intentionally changes geography only for worlds created after the
promotion. A save whose metadata says worldgen 7 continues to instantiate
`WorldGenerator(..., version=7)` and therefore keeps its old elevation, climate,
coasts and v7 cave entrances. Generated chunk caches remain keyed by each save's
recorded worldgen version and authoritative tile/player/history deltas remain
separate.

## Next phase

Phase 3 should replace the temporary v4 moisture/temperature driver for v8 with
physical climate circulation: broad climate bands, prevailing winds, maritime
moderation, continentality, orographic precipitation and rain shadows. That
phase must retain the same explicit `version <= 7` compatibility boundary.
