# Dev57 - functional home furnishings and supply storage

## Scope and system overlap

Prepared homes previously exposed only the small set of profile containers;
most of their authored cupboards, shelves, desks and tables were decorative.
Every supported furnishing now binds one existing ContainerState or receives one
empty ContainerState during explicit preparation, on every prepared floor.
The existing property chest/pantry/wardrobe inventories bind first. Additional
furniture never duplicates their contents or draws another allocation from town
stock. Duplicate inventory bindings are repaired and rejected by save validation.

The data-driven functions cover chests, wardrobes, cupboards, hampers, shelves,
apothecary shelves, barrels, writing/scribe desks, small/large tables and carpenter
benches, including their existing authored variants. Small surfaces have smaller
capacities. Benches retain both crafting and storage actions; beds/seats retain
their existing rest behavior. Inspection shows storage purpose and actual capacity.
Ownership, theft, reach, walls and locks continue through the existing container
commands and property security system. Furniture inventories follow property owner
changes without resetting contents or picked locks.

Workers prefer appropriate home storage for their process outputs: food in
pantries, clothing/textiles in wardrobes, seeds in bins and general work goods in
chests. Full destinations are skipped; the existing workplace fallback remains
when no usable home store is available. Household purchases use the same soft
preferences. Existing exact cargo walks, paid trade and aggregate labor
reconciliation remain the production/economy authority.

## Modules and contracts

- `data/furniture_storage.json` and `systems/furniture_storage.py`: furnishing
  functions, capacity, preparation-only inventory materialization, soft placement.
- `interiors`, `interior_storage`: every prepared floor, stable one-to-one binding.
- `npc_home_storage`, `professions`, `mining_profession`, `household_economy`:
  output-aware home destinations and household placement preferences.
- `property_intrusion`: ownership synchronization for furniture inventories.
- `app`, `ui/interior_view`: observational purpose/capacity and dual-use workbench
  actions; keep authored desk/table/variant art rather than drawing a generic chest.
- `persistence/validation`: reject duplicate nonempty furniture bindings.
- Three new RGBA sprites for the base chest, pantry and wardrobe. See
  [art sources and final prompts](DEV57_CONTAINER_ART.md).

## Persistence, determinism, performance and LOD

Schema remains 3; no new state fields, item definitions, RNG namespaces or
geography versions. Stable inventory IDs are `furniture-storage:<fixture UID>`
under the existing `indoor-storage:` index. Existing saves acquire missing empty
inventories when a home is prepared; saved furniture geometry, goods and locks
remain authoritative. Furniture moves retain the same binding. Additional
inventory count is bounded by already prepared supported furniture, with no
per-tick object creation. Preparation uses existing container records outside
the render path; UI lookups retain the current-space index. No distant homes
are materialized merely to add storage. Distant household delivery stays coarse.

## Validation

- `python -m compileall -q worldseed tools tests`: passed.
- Bounded `furniture-final`: 120 tests passed, including eight new functional
  furniture cases, interior storage/UI/floors/furnishing, production economy,
  workshops, households, property security, exact professions/miners, workplace
  logistics and item asset catalog.
- New cases verify no stock allocation or cargo duplication, every home floor,
  one-to-one binding repair/verifier, capacity/preferences/full-container fallback,
  saved/repositioned contents and locks, actual player store/take, observational
  workbench actions and distinct transparent assets. Existing SQLite roundtrip
  and `tools/verify_save.py` checks passed with the additional furniture inventories.
- Bounded one-seed one-year full-policy smoke: 120 game days, zero invariant errors.
- Production renderer preview: residence and inn both floors, market and smithy;
  rendering asserted observational. Residence screenshot reviewed locally.
- Fast gate now includes the new furniture module and direct storage/UI regressions.
  No live graphical gameplay session or full release-hardening suite was run.

## Known limits and next dependency

Storage preferences are soft, not restrictive player item filters. Inventories
are filled by existing production/purchase/transfer paths, not by opening a room.
Existing decorative washbasins/hearths do not gain a new hygiene/heating system;
beds/seats/workshop fixtures keep their established functions. Authored furniture
variants keep their distinct art, while base chest/pantry/wardrobe art is refreshed.
The next useful validation is live village observation under shortages and
full-home-storage conditions, then balancing capacity and household consumption.

The dirty original `D:\Codex Project\wsLIVING` checkout was preserved. Dev57 is
implemented in the attached `living-village-combat` managed checkout, based on
main `3f5434f`. The original workspace's ignored `dist/RUN_DEV57.bat` launches
this updated source while retaining the original working directory for saves.
