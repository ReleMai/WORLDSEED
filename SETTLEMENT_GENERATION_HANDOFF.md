# Settlement Generation Handoff

## Scope / modules changed
- Added a dedicated settlement-piece catalog for procedural civilization generation.
- Added RC14 room-plan fields for larger multi-room buildings.
- Added deterministic building enclosure/room analysis in `worldseed/systems/settlement_planner.py`.
- Added an exact sparse settlement atlas read model in `worldseed/world/settlement_atlas.py`.
- Added deterministic regression coverage in `tests/test_settlement_generation_foundation.py`.

## Public APIs / contracts
- `ContentRegistry.settlement_pieces`
- `SettlementPieceDef`
- `RoomPlanState`
- `analyze_building(...)`
- `settlement_piece_groups(registry)`
- `build_settlement_atlas(...)`

The settlement atlas is observational. It projects stable road, parcel, structure and room plan IDs and must never become a second settlement authority.

## Building-piece catalog
The first catalog contains 128 generation pieces across walls, floors, openings, furniture, workshops, roads, agriculture/storage, mines/quarries, decorations and civic/defensive utilities. These are planner definitions, not 128 new player recipes.

## Interior-room rule
Doors count as enclosure boundaries and as room separators. This lets large structures retain separate bedrooms, workshops, storage rooms, kitchens and other interiors while still recording doorway adjacency.

## Persistence / migration
No save-schema bump and no settlement-plan-version bump in this work unit. New plan fields have backward-compatible defaults. No existing generated settlement layout is rewritten.

## RNG
No new RNG domain. Enclosure detection and atlas construction are pure/deterministic and generation-order independent.

## Performance
Both systems operate on one bounded settlement/building plan. They do not scan the world or realize distant NPCs.

## UI exposure
The new settlement atlas is a read model only. A dedicated visual settlement-atlas panel is a later consumer.

## Next dependency
Implement the terrain-aware settlement skeleton generator: primary access road/common, local street hierarchy, land-use districts, parcels, then building footprints assembled from the new piece catalog.


## Work unit 2 - Terrain-aware settlement skeletons
- Added `SettlementSkeletonPlanner`, a bounded Phase-8 planner that consumes the prepared regional settlement anchor, regional road exits and environmental fields.
- Main roads now aim toward the actual regional route exits and use terrain-cost A* rather than straight lines.
- Local streets grow from the common and reuse existing road cells where economical.
- Farm and industrial anchors are selected from causal environmental opportunity. Mining settlements, for example, prefer stone opportunity and create a `mine_approach` industrial parcel.
- Residential lots are generated from real street frontage. Fields and industrial parcels bind to explicit access-road IDs.
- Settlement plans now persist rank, common cells, gateway cells, atlas bounds and land-use summaries.
- Land-use parcels now carry purpose, access-road binding and terrain score.
- Generated skeleton bundles persist through `generated_settlement_plans` with a deterministic fingerprint and reload without raw replanning.

### Validation added
- terrain barrier avoidance / pass selection
- road/common/residential/farm/industrial generation
- stable parcel access-road bindings
- deterministic fingerprint and generated-cache reload
- unrelated state/order isolation

### Next dependency
Generate structure footprints on the new residential/civic/industrial parcels, then assemble walls/floors/doors/interior rooms/furniture/workstations from the 128-piece catalog. Structure placement should feed the existing enclosure/type detector and settlement atlas.


## Work unit 3 - Procedural buildings and interiors
- Added first-class `StructurePiecePlan` records so generated buildings preserve the exact catalog pieces used at each coordinate.
- Expanded the catalog from 128 to 136 pieces by adding eight roof families; roofs are explicit settlement construction data rather than an implicit detector-only concept.
- Residential, industrial and farm parcels can now produce physical building plans with walls, floors, roofs, exterior doors, optional interior partitions, furniture/work fixtures and stable piece IDs.
- Larger structures receive interior partitions and internal doors, then pass through the physical enclosure/room detector. Accepted `StructurePlanState` records store detected building type, interior area, room IDs, roof coverage and entrance.
- Mining industrial parcels generate smithies; forest/river settlements use workshops, agrarian settlements use mills, fishing settlements use fisheries, and farm land can receive barns.
- Town/city residential parcels are widened enough for periodic multi-room homes. Smaller settlements retain compact houses.
- Parcel `structure_ids` and settlement `structure_site_ids` bind the land-use plan to physical buildings.
- Generated-plan persistence now round-trips structures, rooms and piece placements as part of the same deterministic settlement fingerprint.

### Validation added
- every generated piece ID exists in the settlement-piece catalog
- generated structures are enclosed, roofed, have entrances, room IDs and piece IDs
- multi-room structures are produced in a town fixture
- mining work areas physically classify as smithies
- roof pieces are first-class overlay pieces

### Next dependency
Materialize planned settlement pieces into local terrain/structure layers without changing the authoritative plan; then add dedicated settlement-atlas rendering for roads, parcels, buildings and named interior rooms.


## Work unit 4 - Local settlement physicalization
- Added `SettlementPhysicalizationSystem`, a bounded reconstruction layer that projects the authoritative settlement skeleton into local playable cells without copying generated civilization into player-built structure state or terrain deltas.
- Active-region physicalization indexes planned roads, parcel IDs, structure IDs, room IDs, walls/doors/partitions, fixtures, floors and roofs.
- Generated walls and workstations now participate in movement collision; wall pieces participate in line-of-sight blocking; planned doors remain passable.
- The existing `BuildingSystem` can query generated settlement rooms directly, so room classification/roof coverage comes from the same stable room plan used by the settlement atlas.
- Local rendering now displays settlement construction pieces before natural resources/ground. Planned roads, walls, doors and workshop/furniture fixtures therefore become visible when their cells are discovered.
- Natural resource features are suppressed on physicalized civilization cells for movement/visibility, preventing deterministic trees/boulders from blocking a road or appearing inside a planned building without creating fake depletion records.
- Runtime materialization is bounded to the player's current 512x512 region. Distant settlement plans stay persistent but consume no local collision/render index.
- Missing prepared environmental data causes a settlement to remain unmaterialized rather than inventing a fallback village.

### Validation added
- road glyph projection
- wall collision and sight blocking
- passable planned doors
- planned room/shelter queries through `BuildingSystem`
- no duplication into `LivingWorldState.structures`
- active-region dematerialization/rebuild when the player changes regions

### Next dependency
Expose the exact settlement atlas as a dedicated UI layer with roads, parcels, building outlines and room labels; then bind NPC homes/workplaces to generated structure/room IDs and replace random representative positions with deterministic valid settlement spawn/route points.


## Work unit 5 - NPC physical home/workplace bindings
- Added `SettlementPopulationBinder`, which binds realized NPC representatives to the existing physical settlement plan instead of inventing separate house/workplace identifiers.
- Active NPCs now receive stable `home_id`, `home_room_id`, `bed_fixture_id`, `property_id`, `workplace_id` and `work_room_id` values backed by actual generated structures, rooms, fixtures and parcels.
- Existing valid bindings survive reload/rebinding. Legacy placeholder IDs such as `settlement:...:house:...` are replaced when the authoritative plan is active.
- Home assignment is deterministic and prefers unused generated residences. If representative count ever exceeds physical homes, the binder shares the least-loaded real home rather than fabricating one.
- Mining smiths/miners bind to smithies; agrarian/farm labor can bind to mills/barns; herders bind to barns; carpenters bind to workshops when those structures physically exist. Professions without a matching generated workplace remain unbound rather than receiving fake stations.
- Newly realized representatives are placed on valid passable cells inside their assigned home rooms. Representative generation itself now starts at the settlement anchor and no longer scatters NPCs randomly into a +/-6 tile box before the physical plan exists.
- NPC AI now sends work tasks to the bound workplace room and rest tasks to the bound home room. Distant Tier-C NPCs continue to use aggregate behavior without forcing local structure generation.
- The local physicalization layer now retains the active settlement skeleton and exposes stable structure/room destinations for simulation systems without duplicating generated civilization into `LivingWorldState.structures`.

### Persistence / compatibility
- The new NPC binding fields have defaults, so legacy saves load without a save-schema bump.
- Binding IDs are simulation state referencing reconstructable plan IDs; the plan remains the physical authority.
- Rebinding is idempotent and does not teleport NPCs that already have a valid home binding.

### Validation added
- representatives bind to real residences, room IDs, bed fixture IDs and parcel IDs
- enough generated homes produce unique representative housing
- smith/miner and farm/herder professions bind only to existing compatible workplaces
- old placeholder IDs are replaced by plan-backed IDs
- repeated binding preserves IDs and positions
- AI work/rest movement targets resolve to actual workplace/home interior cells
- Fast Gate now runs settlement generation and population binding tests together

### Next dependency
Expose `build_settlement_atlas(...)` through the atlas UI as a settlement-detail view with roads, parcel land use, building footprints and room labels. After that, expand physical workplace types (healer, guard, shrine, market, school) before RC17 exact daily schedules.
