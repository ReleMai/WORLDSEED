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

## Next dependency

After CI passes, index crops, fires, fluids, animal signs and animal homes with audited authoritative mutation paths. Independently profile initial/warm reference scenes and save-capture cost; avoid asynchronous persistence or GPU renderer changes without measurements. Large-save capture and region crossing remain outstanding.
