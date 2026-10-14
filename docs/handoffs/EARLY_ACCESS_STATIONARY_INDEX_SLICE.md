# Early access stationary spatial-index slice — 2026-10-13

**Parent baseline:** `edd07fb3b009dcd3a1c81a37085b3409fb5e5275`. Source roadmap: [Pygame engine and early-access plan](../../EARLY_ACCESS_PYGAME_PLAN.md), work unit 4. This continues the previously validated creature and container indexing units. The work is a limited engine-performance change, not completion of M2.

## Scope and engine contracts

- Convert three existing authoritative `LivingWorldState` mappings—`structures`, `ground_piles`, `carcasses`—to the existing transient `SpatialObjectMap` once during `Simulation` construction. Mapping values remain their original dataclass objects, and dictionary keys remain unchanged.
- Every ordinary dictionary insertion, replacement, pop, setdefault, clear and explicit moved-entry reinsertion updates the 32-cell spatial locator through existing mapping hooks. The building system already re-keys an attached structure when a movable container relocates. These map types do not autonomously move during ordinary gameplay; any future direct coordinate mutation must call `refresh_key` on its authoritative path.
- `PygameTerminal._spatial_state_views` reads bounded buckets for the three types, never rebuilding their indexes during UI rendering or iterating their distant populations. Previous 32-cell y/x bucket traversal and stable insertion order within each bucket are preserved. Standalone presentation-only controllers with plain dictionaries retain a compatibility fallback.
- The legacy renderer cache continues to handle only **crops, fires, fluids, animal signs and animal homes**; these five are the remaining stationary-index conversion targets. NPCs, creatures and containers were completed in earlier slices.
- No content changes, schema fields, RNG namespaces, generator versions or persistent index blobs. Save/load remains ordinary schema-3 dataclass maps.

## Regressions and verification

New `tests/test_stationary_spatial_index.py` exercises negative and underground coordinates, strict local lookups, large distant populations without whole-map scans, same-count replacement, removal, immediately visible relocation, unchanged renderer cache, historical bucket order, attached-container/structure relocation with conserved goods and plain-dict legacy state roundtrip.

`.github/workflows/fast-gate.yml` adds this module to the bounded local-indexing check. **Release verification is not claimed here**: run this commit's Fast Gate and record its exact conclusion after publication. Preserve any existing independent audit failures separately; do not hide failed CI.

## Validation and checkpoint

- Initial code commit `85ccde992a2fe127132a23e51df17953ef42fad3` compiled successfully, and **48/49 tests passed** in the local-indexing/discovery step, including 4/5 new stationary-index tests. [Fast Gate run 38493876927](https://github.com/ReleMai/WORLDSEED/actions/runs/38493876927) failed one new regression due to the **test fixture constructing a different fake Simulation for each render**, which correctly invalidated the renderer's `id(sim)`-keyed cache. This did not establish a runtime-gameplay defect.
- Correction `f9a00cd7a127f34edc6ba76248304f7689c044a1` keeps the fake Simulation stable across repeated render calls; it contains no gameplay or engine change. [Follow-up Fast Gate 38494019371](https://github.com/ReleMai/WORLDSEED/actions/runs/38494019371) was queued when this handoff was written. **Do not declare the corrected build green until that exact run succeeds**.
- Parent baseline `edd07fb` remains the last *fully* validated earlier unit. The new indexing code is synchronized to main but awaits full gate confirmation. If CI shows new failures, repair them before beginning the remaining indexing work.
- Source-only checks confirm the commit changes five paths: renderer, Simulation wrapping, bounded CI test list, the new regression module, and this handoff. No persistent data changes.

## Next dependency

After CI passes, index crops, fires, fluids, animal signs and animal homes with audited authoritative mutation paths. Independently profile initial/warm reference scenes and save-capture cost; avoid asynchronous persistence or GPU renderer changes without measurements. Large-save capture and region crossing remain outstanding.
