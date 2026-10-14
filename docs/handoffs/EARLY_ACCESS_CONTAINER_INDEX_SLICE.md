# Early access container spatial-index slice

Baseline `e710c8c7ed638e4eaf9ed4896fce35ca87aa1412`. Converts **containers only** to a transient, mutation-maintained 32-cell map. This is not the entire stationary-index milestone.

- `SpatialObjectMap` accepts arbitrary authoritative mapping keys, including coordinate-keyed outdoor storage and indoor storage identities. `set`, `pop`, `del`, `clear`, `update` and `refresh_key` maintain bucket membership. Existing objects/goods are shared; buckets are not persisted. The index is prepared once on `Simulation` initialization.
- The pygame renderer queries bounded container buckets rather than counting and periodically rebuilding the entire container collection. Interior-only storage is excluded from outdoor presentation, retaining existing visibility behavior.
- `BuildingSystem.move_container` already removes the old key and inserts the changed-coordinate object under a new key. `move_storage_indoors` updates a key before reassigning entrance coordinates, so it now explicitly refreshes the new index after that mutation.
- No save schema, version, RNG or worldgen contract changes. Existing `LivingWorldState.to_dict()` writes plain container records.
- New `test_container_spatial_index` covers negative coordinates, same-count replacement, relocation, explicit in-place refresh, hidden interior storage, distant population and read-only renderer query. Existing Fast Gate suites remain in place.

**Validation gate:** merge/publish status depends on current SHA's GitHub Fast Gate; do not call the entire suite green before it reports. A separately observed baseline Fast Gate at `e710c8c7ed638e4eaf9ed4896fce35ca87aa1412` failed in the *Building asset geometry* step with Windows exit `4294967295` and no traceback; this was not caused by the current container patch. The native-exit cause remains to diagnose independently.

**Next:** index structures, crops, fires, fluids, ground piles, carcasses, signs and homes at authoritative mutation sites, with same-count and relocation tests. Profile saved-state capture and broad social/hourly work before changing SQLite save mechanics. Maintain read-only rendering.
