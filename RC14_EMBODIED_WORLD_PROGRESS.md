# RC14 Embodied World — Development Progress

Status: **development checkpoint / Dev5 regional block architecture and Phase 5 settlement-siting foundation complete**. This is not the final RC14 release.

## Phase 0 — baseline freeze

- Ten deterministic RC13 golden seeds remain the compatibility baseline.
- Legacy worldgen v4 terrain fingerprints are retained as regression contracts.
- Existing save/version boundaries remain loadable and must not be rewritten into new geography.

## Phase 1 — data contracts and versions

RC14 generator contracts remain independent:

- `HYDROLOGY_VERSION = 1`
- `SETTLEMENT_PLAN_VERSION = 1`
- `ROUTEGEN_VERSION = 1`
- stable regional physical-plan dataclasses/IDs in `worldseed/world/regional_plan.py`
- rebuildable SQLite generated caches for hydrology/regional/settlement/route plans
- authoritative `physical_plan_deltas` for mutations that must survive cache deletion/rebuild

## Phase 2 — hydrology prototype

`worldseed/world/hydrology.py` provides the deterministic causal drainage layer:

- 16-cell hydrology lattice;
- 64×64 core-node domains with 8-node halos;
- Priority-Flood-style depression handling;
- deterministic D8 flow and flat drainage;
- climate/moisture-derived runoff and accumulation;
- watershed IDs and river classes;
- floodplain strength and canonical fingerprints;
- generated-cache persistence plus invariant audits.

`tools/audit_hydrology.py` and `tools/bench_hydrology.py` remain available for isolated-domain debugging and profiling.

## Phase 3 — worldgen v5 physical geography

New worlds now use **`WORLDGEN_VERSION = 5`**. Existing v1-v4 saves continue using their recorded generator and are not retroactively given RC14 rivers.

### Seam-safe prepared hydrology

Dev2 identified that separately solved adjacent Priority-Flood domains could disagree in their overlapping halos. Dev3 resolves that for prepared regions by solving every hydrology domain required by the prepared envelope inside **one larger drainage lattice**, then slicing the result back into per-domain cache records. `audit_window_seams()` validates shared elevation, filled elevation, accumulation, watershed, river class, floodplain and flow information across the overlap.

The startup prepared envelope therefore receives one coherent watershed solution rather than independent per-chunk or per-domain river rolls.

### Physical projection

Worldgen v5 projects the hydrology plan into actual surface geography:

- deterministic meandering stream/river centerlines refined from the coarse lattice;
- `core:river_shallow` for minor streams, ford segments and shallow banks;
- `core:river` for deep medium/major channel cores;
- contiguous lake basins from interpolated depression fill depth rather than repeated circular node stamps;
- `core:wetland` and `core:floodplain` environmental overlays;
- game-readable `river_width`, `river_depth_class`, `wetland_probability`, `water_access_score`, `flood_risk` and `crossing_cost` read values;
- deterministic ford candidates on qualifying river segments.

The v5 generator intentionally reuses the approved v4 continental/climate field contract so the version bump changes physical hydrology rather than needlessly rerolling every broad biome. Underground generation remains unchanged.

### Startup/pregeneration integration

For v5 worlds, startup now:

1. selects a viable candidate region using cheap base geography;
2. resolves the complete prepared-envelope watershed plan;
3. attaches the prepared hydrology projection;
4. relocates the exact spawn locally if new physical water made the preliminary cell invalid;
5. carves/persists v5 terrain chunks;
6. prepares resources on the resulting physical geography.

This keeps regional hydrology work in the deliberate loading phase rather than normal opening movement/rendering.

### Terrain/content compatibility

The content registry now defines shallow river, deep river, wetland and floodplain terrains. Suitable existing natural resources were extended onto wetland/floodplain terrain so RC14 geography does not create sterile green zones. Existing sprites are reused as safe presentation fallbacks until the parallel art track adds dedicated bank/wetland/floodplain transitions.

## Dev2 world readability retained

- Ambient loose ground-resource coverage remains reduced so collectible items form readable pockets rather than carpeting the map.
- Structural trees/boulders retain their independent biome budget.
- Local camera remains centered on the player.
- Mouse wheel and `+`/`-` zoom the local view; `0` resets zoom.

The earlier 129×129 tuning sample reduced non-structural ambient ground resources from 7.57% to 4.04%, while structural scenery remained 1.68%.

## Dev3 startup-input fix

The pygame loading screen could leave startup key-repeat events queued long enough for gameplay to receive a stale `ESC`, immediately opening the pause menu. The loading-to-game transition now:

- clears queued `KEYDOWN` events;
- temporarily disables pygame key repeat;
- re-enables normal repeat on the first fresh gameplay key press.

This also prevents a held confirmation key from accidentally opening the Action Hub as soon as the world appears.

## Validation performed

Focused RC8/RC10/RC12/RC13/RC14 renderer, worldgen, pregeneration, hydrology and presentation suite: **36 passed** after Phase 3 integration.

Additional RC14 startup/hydrology contract run: **16 passed** after the held-key suppression hardening.

Ten-seed traversability audit passed with:

- `adjacent_blocker_pairs = 0`
- minimum resource connectivity ≈ `0.99957`
- minimum walkable retention ≈ `0.90311`
- maximum blocker occupancy ≈ `0.09689`

`tools/audit_phase3_geography.py --seed rc14-golden-00 --radius 192` inspected 147,456 surface cells across four prepared hydrology domains with **zero seam issues**. Physical RC14 hydrology occupied about **6.34%** of the inspected cells. The current preview contains contiguous lake shapes, branching rivers, floodplains and wetlands without the earlier node-circle/polka-dot lake artifact.

Current single-chunk pregeneration benchmark on this environment:

- fresh first terrain tile: about 208 ms (includes hydrology preparation/cache setup for an unprepared v5 area)
- prepared first terrain tile: about 0.31 ms
- fresh 1,024-cell resource chunk: about 26 ms
- prepared 1,024-cell resource chunk: about 3.19 ms

These are development measurements, not final release budgets.

A full repository-wide pytest run is not claimed for this checkpoint; the complete suite is substantially slower under v5 and exceeded the available long-run validation window without exposing a failure. Focused regression suites and required Phase-3 audits above are green.

## Phase 4 — Environmental derived fields (Dev4)

`worldseed/world/environmental_fields.py` derives immutable, 0–100 game indices for slope, relief, natural soil fertility, wetness, drainage, flood risk, farming suitability and resource opportunity. Resource potential separates forage, timber, stone and freshwater. The sampler uses the approved elevation/climate fields and prepared hydrology; it never solves regional drainage, creates settlements, or changes terrain/resource placement.

An 8,192-entry LRU is keyed by environmental version, generator version, hydrology fingerprint and absolute coordinates. It is reconstructable and writes no persistent state. Missing v5 hydrology produces an unavailable result rather than an invented dry-land score. Existing v1–v4 worlds retain their original fields and no new river influence; underground samples are deliberately unsupported.

Look mode shows natural ground signs at survival/naturalism 4+. Dynamic farm N/P/K and player changes remain with their existing simulation owners. `tools/audit_environment.py` writes exact environmental maps and machine-readable checks. See `RC14_DEV4_HANDOFF.md` for the validation record and formulas.

## Dev5 — Regional blocks and settlement-siting foundation

`worldseed/world/region_blocks.py` adds a deterministic 512×512 strategic block plan over the existing unbounded world. Blocks summarize broad landscape character, environmental settlement suitability, sparse symmetric road/trail exits and prepared authoritative water exits without duplicating simulation state. Settlement presence remains under the existing RNG contract, while settlement x/y now comes from a bounded deterministic suitability search using Phase-4 environmental fields. A regression test verifies planner/society presence and anchor agreement.

The pygame client now exposes a discovery-gated regional map that shows broad terrain, prepared waterways, road/trail connections and known settlements without revealing latent bandit/site/wildlife potential. Exact road/water edge offsets are used so neighboring regions meet at the same map boundary point. Cardinal boundary crossing keeps continuous coordinates and explicitly reports the side from which the destination was entered.

Dev5 also replaces pygame/SDL key-repeat movement with explicit key-down/key-up held-state pacing. Slow render frames no longer create a catch-up queue of movement intents. The terrain base layer can scroll-reuse a one-cell camera move and resource presentation is cached by absolute world cell.

## Next dependency

**Phase 6/7 — strategic route graph and terrain-aware route corridors.** Dev5's regional road exits are a strategic substrate, not final physical roads. The next work unit should build the sparse settlement graph/connectivity backbone, rasterize selected edges through terrain/hydrology cost, create stable crossings, and then feed those exact corridors to local materialization.

After route corridors are authoritative, continue Phase 8 with the settlement skeleton (access road/common, functional anchors, parcels and footprints). Existing saves must not relocate already-realized settlements.

Phase 11 still needs quiet-time/background planning for exploration-ring expansion. Dev5 does not make normal same-region movement generate regional plans, but crossing into a new coarse region can still realize the next nearby ring synchronously through the existing coarse-world refresh. That frontier preparation path should be moved out of latency-sensitive input before RC14 release.
