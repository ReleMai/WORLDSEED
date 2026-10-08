# Dev58 - building footprint selection and indoor cargo

## Scope and causes

Building art was fitted to the enclosing rectangle even when its authoritative
footprint contained a cutout or courtyard. Those walkable cells could therefore
look and select like building body. Cached facade pixels now exclude cells
outside the exact footprint, and the fit key includes footprint shape. Side
portal overlays are constrained to their physical threshold tile. Existing
building-body/door selection, alpha hits, discovery filtering and stable door
IDs are preserved. No physical plan, placement seed, geography or collision
authority is changed to match the artwork.

The older workshop profile intentionally placed its primary supply crate next
to the exterior frontage. All generated property storage for enclosed buildings
now lives in the existing interior container namespace. Sync moves old crates
and bound workplace/miner bins without copying their inventories, changing UIDs,
reallocating settlement stock, or resetting tampered locks. Primary bins bind
to real indoor furniture; small/full rooms keep pending inventory safely indoors
until an approach is available. Open yards have no invented interior and may
only place service storage off actual road cells. Player-built/natural containers
without an authoritative building binding are not relocated.

## Modules and contracts

- `ui/exterior_view`: exact-footprint cached masks and tile-sized side portals.
- `systems/building_storage.move_storage_indoors`: stable object/index migration.
- `property_intrusion`: enclosed primary storage and legacy bound-bin migration;
  open-yard service placement excludes road cells.
- `npc_home_storage`: shared home/workplace destination selection and execution
  repair for saved exterior cargo routes. No goods move during route repair.
- `ai`, `professions`, `mining_profession`: use indoor storage approaches and
  existing door/stair/fixture reach, including fallback workplace destinations.
- `workplace_logistics`, `sim.engine`: aggregate-era workplace buffers remain
  addressable indoors; pickup routes and reach checks use NPCStorageAccess.
  Exact profession labor reconciliation and the existing coarse shipment policy
  are unchanged. A missing indoor approach leaves the supplies in their store.
- `tools/audit_building_assets.py`: all registered facade images, authored door
  anchors, physical cutouts, hit masks, portals and production-renderer sheets.

## Persistence, RNG, LOD and performance

Save schema remains 3, with existing ContainerState and task fields. No new RNG
namespace, generation version or collection is introduced. Container inventory,
ownership, keyholders, capacity, lock/tampering state and external UID references
survive migration. Outdoor coordinate keys are replaced by `indoor-storage:<UID>`
so those crates no longer block outside movement. Saved hauling walks repair on
execution; positions and cargo never teleport to the new destination.

Reconciliation runs on settlement preparation/sync. The renderer remains
observational and never generates plans or interiors. Facade fitting/masks keep
their existing bounded caches; footprint clipping occurs when fitting a surface,
not every frame. Exact active-worker travel uses existing fixed ticks; distant
legacy shipments retain coarse completion.

## Validation

- Compileall and diff whitespace checks passed.
- All 57 unique registered facade assets: 2,052 checks (3 footprint shapes,
  3 zooms, 4 portal sides per asset), with explicit authored door anchors.
  The four remaining building-folder PNGs (active and legacy door leaves) also
  passed decode and selectable-pixel checks at three scales: 61 PNGs covered.
  Five production-rendered review sheets inspected under `dist/dev58-buildings/`;
  the JSON audit can be regenerated with the checked-in tool.
- `exterior-focused`: 26 tests passed, including 25 settlement archetype/population
  layout cases, real frontage paths, irregular collision holes, all old facade
  fit checks, separate body/door pointer events and hidden-state-safe inspection.
- `ui-movement-routing`: 9 movement/pointer/menu tests passed.
- `dev58-storage-economy`: 103 tests passed across migration, furniture, interior
  storage, real NPC input/output/home/market travel, mining/professions, household
  and workplace logistics, ownership/security, action combat and save round trips.
  Representative `tools/verify_save.py` passed.
- One-seed one-year full-policy smoke: 120 simulated days, no invariant errors.
- An initial broad run including all `test_ui_rc2` exceeded its 180-second deadline.
  Its repeated world initialization is outside this change; the affected exterior
  and lightweight input suites above passed separately at the same/smaller limits.
- One early Python 3.14 run raised an unexpected iteration TypeError in the
  unchanged planner; the focused recheck and final combined suite passed.
- Automatic fast gate now includes indoor migration tests and the complete facade
  audit. Full release hardening and live interactive playtesting remain unrun.
- The prior Dev57 fast gate failed because its workshop test counted newly empty
  furniture inventories as a stock change. The updated test explicitly preserves
  every original container ID and its goods while allowing new empty furniture
  inventories, and verifies the new indoor access boundary. It passes locally.

## Known limits and next dependency

Artwork remains perspective-painted: irregular old plans use an exact physical
cutout rather than new custom art for every possible footprint. No inhabited
building is moved or rerolled. Very small/full legacy interiors may retain pending
storage until space is available, keeping the inventory indoors and conserved.
Next useful check is a live loaded-save village walk, particularly cramped legacy
workshops and side entrances, followed by deliberate release hardening.

Main baseline was `30d63f7`. The original dirty D:\Codex Project\wsLIVING checkout
was preserved; the attached living-village-combat managed checkout contains Dev58.
`D:\Codex Project\wsLIVING\dist\RUN_DEV58.bat` launches this source with the
original working directory/save location.
