# RC14 Dev26 — WORLDGEN v8 topography and cave siting

Scope: continue Phase 2 without promoting ordinary new worlds to v8.

## Implemented

- Added `worldseed/world/topography.py` as a deterministic read model over
  authoritative v8 geological elevation.
- Added topographic fields for:
  - signed X/Y slope
  - normalized slope
  - raw and normalized local relief
  - ridge exposure
  - valley depth
  - ruggedness
- Added `WorldGenerator.topography_at()` and `World.topography_at()`.
  Legacy v1-v7 worlds return no authoritative v8 topography.
- Added `CaveGeneratorV8`, used only by explicit v8 worlds.
- v8 cave mouths now prefer exposed slopes, relief, ridges, mountain belts and
  plateaus rather than reusing the v7 entrance-placement rule.
- Deep valley-floor candidates are mildly penalized so cave mouths favor
  exposed walls/rock instead of flat depressions.
- v8 entrance depth can increase in strongly rugged/tectonically uplifted sites.
- Underground chamber/ore generation remains on the v7 contract for now. The
  later underground-geology phase will replace that separately.
- Added `tools/audit_worldgen_v8_topography.py` to measure slope, relief,
  ruggedness, ridges, valleys and generated cave-mouth characteristics.
- Added targeted topography/cave tests, including legacy-v7 planner isolation.

## Compatibility boundary

`WORLDGEN_VERSION` remains 7 and `WORLDGEN_PREVIEW_VERSION` remains 8.

No existing save changes geography. No v7 cave entrance namespace, v7 terrain
field, hydrology version, resource version or save schema changed.

## Validation notes

Representative v7 field fixtures added in Dev25 were independently recomputed
from the repository's exact `hash_u64` and v7 interpolation equations in this
work session; all five expected tuples match exactly, including negative
coordinates.

The connected GitHub environment still does not expose a full executable
checkout, so repository-level integration tests were not claimed as executed.
Run on the next executable checkout:

```bash
python -m unittest \
  tests.test_worldgen_v8_landforms \
  tests.test_worldgen_v8_phase2 \
  tests.test_worldgen_v8_topography \
  tests.test_dev16_caves_crafting

python tools/audit_worldgen_v8_phase2.py
python tools/audit_worldgen_v8_topography.py
```

The v8 promotion gate remains closed until these pass together with multi-seed
spawn/resource/traversability checks and legacy golden-terrain verification.
