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
