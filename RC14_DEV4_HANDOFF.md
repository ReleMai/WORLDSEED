# WORLDSEED RC14 Dev4 — Phase 4 handoff

## Scope and outcome

Continues the supplied RC14 Embodied World Dev3 source. Phase 4 environmental derived fields are complete. Phase 5 settlement suitability/placement is next. This remains a development checkpoint, not final RC14.

### Player-facing changes

- Look (`L`) now describes natural fertility, wetness, drainage, slope, relief, flood risk and land/resource potential when survival or naturalism is at least 4.
- Graphical camera uses an odd, centered tile grid at every zoom level. This removes the half-tile displacement that occurred with even viewport dimensions.
- The footer wraps all control hints within the 800×520 minimum window and constrains long event text to its own panel.
- Dev3 startup Escape suppression and Dev2 resource decluttering are retained and verified. This update does not add ground clutter.

### Code fix

`HydrologyGenerator.load_or_generate(..., persist=True)` now stores an already-cached in-memory plan. Dev3 returned early on a memory-cache hit and silently ignored that persistence request. The extracted cached-plan reader also verifies that payload coordinates match the requested domain.

## APIs and ownership

- `World.environment_at(WorldPos)` / `WorldGenerator.environment_at(WorldPos)` return immutable `EnvironmentalFields` or `None`.
- `EnvironmentalFields`: `slope`, `relief`, `soil_fertility`, `wetness`, `drainage`, `flood_risk`, `farmland`, `open_water`, `version`, and `resources`.
- `ResourceOpportunity`: `forage`, `timber`, `stone`, `freshwater`; `resource_opportunity` exposes a weighted summary. These are habitat/site scores, not guaranteed pickups, stock quantities, mineral deposits, or crop yields.
- `HydrologyGenerator.cached_domain(...)` loads an existing memory/SQLite plan only. `surface_at(..., prepared_only=True)` refuses a missing plan instead of solving regional drainage.
- Environmental reads never call chunk realization, settlement planning, RNG streams, or simulation mutation. A v5 area without prepared hydrology returns `None`; underground locations also return `None`.
- All indices use integer 0–100 game scales. Slope is **not degrees**, relief is **not meters**, and flood risk is a relative geographical index, not a calibrated annual probability.

## Derivation contract

Environmental version 1 uses centered elevation differences at ±8 cells for slope and a ±32-cell cross-shaped stencil for relief. All samples use absolute world coordinates, including negative coordinates. Depression, moisture, local relief and hydrology wetland/floodplain strength determine drainage and wetness. Natural fertility incorporates the existing climate fertility, alluvial influence, steepness, exposed high terrain and moisture extremes.

Farming potential combines fertility with slope, flood and temperature penalties. Forage/timber potential uses fertility, moisture, climate and exposed terrain; stone potential uses elevation and relief. Freshwater opportunity comes from hydrology water access and excludes the original ocean. Open water gets zero farmland, forage, timber and surface stone opportunity.

Look reports **natural** conditions. Mutable farm N/P/K, construction, player terrain edits and fluid simulation retain their existing owners. These base scores do not override that state.

## Compatibility, persistence and performance

- Engine: `1.0.0-rc14-dev4`; environmental model: `ENVIRONMENT_VERSION = 1`.
- Worldgen stays **5**; hydrology stays **1**; resourcegen stays **3**; save schema stays **3**.
- Continental/climate fields still use the approved v4 contract. Terrain, river geometry and resource placement are unchanged by environmental reads.
- Existing v1–v4 worlds sample their recorded generator fields with no v5 river influence. No geography migration is performed.
- Environmental data is a rebuildable 8,192-entry LRU per generator, keyed by version, coordinates and prepared hydrology fingerprint. It is not persisted and adds no save growth. A changed hydrology fingerprint cannot reuse stale environmental samples.
- No new random namespace or stateful RNG consumption.
- Three-seed audit measured approximately 0.27–0.30 ms per cold environmental-plus-terrain sample and 1.0–1.4 microseconds per cached environmental read on this Linux environment. These are observations, not hardware guarantees.

## Validation

- Full existing suite before final additions: **192 passed**.
- Full suite including environmental tests and initial graphical/UI additions: **208 passed**, 258.076 seconds.
- The subsequent footer correction and extra regression test passed the complete graphical behavior suite: **5/5**. The final source therefore contains **209 distinct tests**; the 208-test full run predates that final footer-only test.
- `python -m compileall -q worldseed tools/audit_environment.py`: passed.
- `tools/replay.py tests/fixtures/golden_replay.json`: `8bdc2f5783cab3ff8d48fc590b704480772a79b2`.
- Representative generated/saved game: `tools/verify_save.py` reports **Save integrity: OK**.
- Three-seed environmental audit: **12,288 samples**, four prepared domains per seed, **zero issues**. Maps and JSON reports are in `artifacts/phase4/`.
- Ten-seed traversability audit: **zero adjacent blocker pairs**, minimum walkable retention **0.903114186851211**, minimum connectivity **0.9995742869306088**.
- SDL dummy-display behavior checks cover stale Escape removal, fresh input, preserved window-close events, wheel limits/reset, zoom/resize rendering, exact camera centering, simulation observation, and footer containment. Actual rendered 1280×800 and 800×520 frames were visually inspected.
- Native Windows interactive play was not available in this environment.

Final clean extracted archive: compile check passed and all **31 RC14 tests passed** in 10.763 seconds. The log is in `artifacts/validation/clean_archive.txt`; other gate logs are alongside it.

## Modules and tooling changed

- New `worldseed/world/environmental_fields.py`.
- Updated `worldseed/world/{generator,world,hydrology}.py`.
- Updated `worldseed/ui/{screens,layout,pygame_terminal}.py`.
- Updated version constants/package metadata and release/roadmap documentation.
- New `tests/test_rc14_environment.py`, `tests/test_rc14_pygame_behavior.py`; updated `tests/test_ui_rc2.py`.
- New `tools/audit_environment.py` (standard library only). Re-run with:

```bash
python tools/audit_environment.py
python -m unittest discover -s tests -v
python tools/audit_traversability.py --seeds 10 --json
```

## Next dependency and known limits

Phase 5 must use these fields for causal settlement suitability, with stable plans linked to existing simulation settlements. Preserve existing settlement anchors until an explicit migration policy exists. Do not create a second decorative/economic settlement authority.

Background preparation at distant exploration margins remains Phase 11 work. The new environmental path never generates missing hydrology; pre-existing terrain/crossing fallback paths still can. Extending the prepared hydrology window can require a broader watershed solution and needs an explicit stability policy. Dev4 preserves Dev3's algorithm and does not claim to solve that frontier problem.

Resource/farming weights are initial game-design indices. Regional scoring and physical settlement footprints need Phase 5 integration and calibration; no settlements are moved or newly placed by this checkpoint.
