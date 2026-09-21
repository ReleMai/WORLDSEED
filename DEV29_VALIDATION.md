# RC14 Dev29 — WORLDGEN v8 Hydrology v2 foundation

Scope: begin Phase 4 by promoting hydrology v2 for new saves while preserving
legacy river geography and extending the drainage/read-model contract.

## Implemented

- Promoted `HYDROLOGY_VERSION` to 2 for newly created saves.
- Existing saves continue to use the hydrology version stored in metadata.
- Saves missing hydrology metadata are inferred as legacy v1; they are never
  silently assigned the newest river algorithm during open.
- `World` and the application startup path now instantiate hydrology from the
  save's recorded hydrology contract.
- Added version-aware hydrology algorithm IDs so v1 cache rows remain readable
  while v2 uses `worldgen-v8-hydrology-v2`.
- V2 generated domains persist:
  - local climate-driven runoff contribution,
  - downstream channel gradient,
  - existing elevation/fill/flow/accumulation/watershed/river/floodplain fields.
- V2 runoff consumes authoritative Phase-3 precipitation. Wet high terrain gets
  bounded headwater support; arid/rain-shadow areas contribute less because
  precipitation already carries that climate effect.
- River classes remain discharge/accumulation driven with v2 source thresholds.
- Channel midpoint refinement is now gradient-sensitive:
  - steep headwaters remain direct,
  - low-gradient rivers can meander farther.
- Tributary confluences widen from actual upstream river count.
- Ford candidates are physically gated by river class, gradient, bank slope,
  discharge and floodplain context. Stable hashing only breaks ties among
  physically suitable reaches.
- Rapids and gorge labels derive from channel gradient plus ruggedness.
- Added first-pass read-model signals for:
  - braided reaches,
  - meandering/oxbow potential,
  - low-gradient delta candidates.
  These do not yet invent separate terrain outside the hydrology authority.
- Expanded hydrology audit CSV/JSON output with runoff and channel-gradient
  statistics.

## Compatibility boundary

Hydrology is independently versioned from WORLDGEN.

- new v8 save: worldgen 8 + hydrology 2
- existing v8/hydrology-1 save: remains hydrology 1
- existing v5-v7/hydrology-1 save: remains hydrology 1
- missing historical hydrology metadata: inferred as v1
- generated v1 and v2 hydrology cache rows may coexist because version is part
  of the SQLite primary key

V1 serialization/fingerprints omit the new v2 arrays so the old payload
contract is preserved.

## Regression coverage added/updated

`tests/test_rc14_hydrology.py` now covers:

- current version constants,
- v1/v2 algorithm mapping,
- v2 runoff and channel-gradient arrays,
- v1 cache compatibility,
- v2 multi-domain seam checks including derived arrays,
- physical channel morphology reads,
- v1 and v2 generated cache coexistence,
- new-save hydrology v2 metadata,
- existing-save hydrology v1 pinning,
- World auto-hydrology respecting save metadata,
- existing RC13/v4 geography fingerprints.

## Required executable validation

The connected GitHub environment still does not expose a full executable private
checkout, so the suite below is not claimed as run in this work session.

```bash
python -m unittest \
  tests.test_rc14_hydrology \
  tests.test_worldgen_v8_climate_weather \
  tests.test_worldgen_v8_phase2 \
  tests.test_worldgen_v8_topography \
  tests.test_worldgen_v8_promotion \
  tests.test_rc13_pregeneration \
  tests.test_rc10_worldgen

python tools/audit_hydrology.py --seed v8-hydro-dev29
python tools/audit_worldgen_v8_climate.py
python tools/audit_worldgen_v8_startup.py
python tools/audit_traversability.py
python tools/bench_pregeneration.py
```

## Phase-4 work still open

- multi-point terrain-aware channel splines,
- explicit sediment transport proxy,
- natural river islands / fully materialized braided channels,
- oxbow lake/meander-scar materialization,
- delta distributary terrain,
- stronger valley-confined gorge shaping,
- dedicated v2 river/coast art where morphology needs new visual classes,
- multi-seed discharge/class calibration and performance profiling.
