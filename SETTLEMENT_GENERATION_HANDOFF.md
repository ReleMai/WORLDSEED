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


## Work unit 3 - Composite building generation
- Promoted the settlement planning contract to v2 for new worlds. Existing saves remain pinned to stored v1; saves missing settlement metadata infer v1.
- Region and settlement planners now read the save-pinned settlement-plan version.
- Added exact `BuildingPiecePlan` placements and v2 persistence for structures, rooms and building pieces.
- Added 8 roof pieces, bringing the settlement catalog to 136 pieces.
- Town/city residential lots can be 7x7, allowing multi-room houses with interior partitions and doors.
- V2 plans generate enclosed residences, one farm barn/outbuilding, and archetype-driven industrial workplaces. Mining uses mine workshops, forest settlements use logging/carpentry workshops, agrarian settlements use mill workshops, and river/fishing settlements use matching work buildings.
- The existing enclosure detector remains authoritative for final room segmentation and building classification.
- Fixtures are attached to detected room IDs. Settlement plans now expose housing and workplace capacity for later NPC home/work schedules.
- Settlement atlas cells can expose exact piece placement IDs/content IDs together with parcel, structure and room identity.
- Farm/industry access roads now terminate outside their work parcel rather than cutting through the building site.

### Validation added
- v2 structures stay inside parcels and have valid entrances
- generated homes expose bedrooms and housing capacity
- mining workplaces classify as workshops and contain multiple rooms
- generated buildings use wall/floor/roof/opening/furniture/workshop pieces
- parcel/structure/room/piece IDs remain linked and deterministic
- settlement atlas exposes exact building pieces
- legacy v1 settlement-plan metadata remains pinned while new worlds use v2

### Next dependency
Add richer civic/market parcels and property/home/work bindings, then move into Phase 9 projection so the stable v2 road/parcel/building/room/piece plan becomes actual local terrain and structure state without rerolling.
