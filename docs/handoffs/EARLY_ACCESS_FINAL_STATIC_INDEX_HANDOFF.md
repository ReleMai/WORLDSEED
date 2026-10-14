# Early access static-index completion — 2026-10-13

Source baseline: `fce8640166f7152aed5605f0cffea4c6ee2b4cf0` (previous stationary-index Fast Gate on `f9a00cd` passed all jobs). This commit finishes the remaining renderer-side state indexing part of `EARLY_ACCESS_PYGAME_PLAN.md` work unit 4.

## Changes
- Extend `SpatialObjectMap` initialization in `Simulation` to crops, fires, fluids, animal signs, animal homes. Existing indexes for containers, structures, piles, carcasses, creatures and NPCs remain unchanged.
- Remove the old count/hour-keyed full-collection presentation rebuild in `PygameTerminal._spatial_state_views`. All nine fixed-entity collections use bounded 32-cell bucket reads; NPCs/creatures use their own existing maintained locators. The renderer never repairs world state.
- Maintain historical y/x bucket traversal, stable insertion order and interior-container filtering. Retain a plain-dict fallback only for standalone presentation fixtures.
- Nearby hunting sign/home queries and duplicate-sign checks use prepared local indexes if available, with plain-dict fallback for standalone systems. Global home matching by species/cohort remains unchanged because it may find legitimate remote shared homes.
- Authoritative state objects and mappings remain unchanged in serialized saves. Dynamic updates to amount, crop condition, fire intensity, sign information and stored home goods require no spatial refresh; dictionary lifecycle inserts/removals remain indexed. Direct future coordinate mutations must call `refresh_key` on the corresponding mapping.

## Verification and next work
- `tests/test_remaining_spatial_index.py` covers all five types and distant populations with scan-poisoned maps, same-count relocation and exact viewport buckets, negative/multilevel coordinates, local hunting sign/home queries and identity/serialization.
- Fast Gate adds this new test module to local indexing checks. This documentation does not claim full green until the exact code-commit run succeeds.
- **Next phase**: reference-scene performance benchmark and save-capture audit, then begin shared graphical panel and cabin/recovery loop work unit 5. Existing M2 20% local-scaling and save-capture <=50ms are proposed targets, not verified results. Do not change save semantics or introduce async writes without independent measurements.
