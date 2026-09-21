# RC14 Dev30 — Hydrology v2 morphology materialization

Scope: continue WORLDGEN v8 Phase 4 without changing the persisted Hydrology v2
drainage solve. This work versions and upgrades the local river projection layer.

## Implemented

- Added `HYDROLOGY_MORPHOLOGY_VERSION = 2` for newly created saves.
- Saves created during Dev29 with hydrology v2 but no morphology metadata infer
  morphology v1, preserving their single-midpoint river projection.
- Added a dedicated `generated_surface_chunks` cache keyed by:
  - worldgen version,
  - hydrology version,
  - morphology version.
  This closes the old ambiguity where surface terrain could depend on hydrology
  while the cache key recorded worldgen only.
- Existing underground/pre-hydrology chunk caches remain worldgen-keyed.
- Morphology v2 replaces the single midpoint with deterministic multi-point
  centerlines. Low-gradient reaches can form broader S-curves; steep reaches
  remain comparatively direct.
- Suitable medium/major reaches now physically split into a secondary channel
  and rejoin at the downstream node. Base terrain remains between threads,
  creating natural deterministic river islands without renderer-owned geometry.
- Mature low-gradient floodplains can materialize detached shallow-water oxbow
  scars. The oxbow contract is deterministic from the parent flow edge.
- Oxbow ellipses orient their long axis with the dominant channel direction.
- Steep, rugged near-channel cells can materialize as rocky gorge banks.
- River current lookup now consumes the same morphology centerlines as terrain,
  including secondary braided threads.
- Channel/oxbow geometry helpers are bounded LRU caches to keep repeated
  per-tile projection inexpensive during chunk generation.
- No new terrain IDs were required:
  - braid threads use the existing stream/river water family,
  - islands use the authoritative underlying terrain,
  - oxbows use freshwater lake shallows,
  - gorge banks use existing rock terrain.
  Existing water animation/autotiling therefore applies automatically.

## Compatibility boundary

Drainage and morphology are separate contracts.

- Dev29/newer hydrology domain solve: `hydrology_version = 2`
- Dev29 projection: `hydrology_morphology_version = 1`
- Dev30 projection: `hydrology_morphology_version = 2`
- older saves missing hydrology metadata: hydrology v1 + morphology v1
- existing saves are never assigned a newer morphology contract on open

Generated hydrology-domain fingerprints do not change in Dev30 because the
Priority-Flood/runoff/discharge arrays are unchanged. Only local materialization
changes behind the new morphology version.

## Regression coverage

`tests/test_rc14_hydrology.py` now also checks:

- current morphology version constant,
- deterministic four-point morphology-v2 centerlines,
- braid split/rejoin endpoint invariants,
- deterministic detached oxbow geometry,
- Dev29 morphology-v1 single-midpoint compatibility,
- current lookup on braided water,
- new-save morphology metadata,
- missing morphology metadata -> v1,
- save-pinned morphology during World auto-hydrology,
- surface chunk cache isolation by hydrology/morphology version.

## Audit tooling

Added `tools/audit_hydrology_morphology.py` to report:

- channel style counts,
- braided / gorge / ford / delta / oxbow samples,
- terrain override distribution,
- crossing-cost distribution,
- domain fingerprint/invariant results.

`tools/audit_hydrology.py` now reports the active morphology version too.

## Required executable validation

The connected GitHub environment still does not provide an executable checkout,
so these commands are documented rather than claimed as executed:

```bash
python -m unittest \
  tests.test_rc14_hydrology \
  tests.test_worldgen_v8_climate_weather \
  tests.test_worldgen_v8_phase2 \
  tests.test_worldgen_v8_topography \
  tests.test_worldgen_v8_promotion \
  tests.test_rc13_pregeneration

python tools/audit_hydrology.py --seed v8-hydro-dev30
python tools/audit_hydrology_morphology.py --seed v8-hydro-dev30 --domain-x 0 --domain-y 0
python tools/audit_hydrology_morphology.py --seed v8-hydro-dev30-b --domain-x -1 --domain-y 1
python tools/audit_traversability.py
python tools/bench_pregeneration.py
```

Visual validation should inspect at least one braided reach, one mature
low-gradient floodplain, one steep rapid/gorge reach, and a legacy
morphology-v1 save to confirm the old local river path does not move.

## Phase-4 work still open

- sediment transport/deposition proxy,
- stronger deterministic alluvial-island shaping inside large braids,
- oxbow infill succession / abandoned meander scars beyond open water,
- delta distributary materialization (candidate signal remains only),
- broader gorge/valley-wall interaction,
- multi-seed discharge/morphology calibration,
- performance profiling of very large prepared hydrology windows.
