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


## Work unit 6 - Settlement atlas detail UI
- Connected the exact settlement-plan atlas to the existing mouse-first world atlas without allowing the UI to generate or mutate settlement plans.
- Selecting a known village/city now offers `Open settlement plan` only when an authoritative plan is already active or persisted. Unprepared settlements show a short availability note instead of triggering world generation from the map screen.
- The settlement detail view uses one focused layout: the plan occupies the main area; a compact right panel contains four summary metrics, a four-item land-use legend, and one context-sensitive inspect section.
- Land-use parcels are visually separated into residential, civic, farm and industrial areas. Roads, building footprints, rooms and entrances layer on top in a clear hierarchy.
- Work buildings are labeled on the map; repeated residence labels are intentionally suppressed. Interior room labels appear only after selecting a building, preventing dense settlements from becoming text-heavy.
- Cell inspection reports coordinates, land use, parcel purpose, road access, building type/function, room kind and entrance status without exposing stable internal IDs unless needed by debugging.
- The detail map automatically fits the complete settlement bounds and does not inherit world-atlas drag/zoom controls. This keeps the settlement plan readable and prevents accidental camera changes.
- Escape from settlement detail returns to the world atlas first; the explicit `Back to atlas` button provides the same behavior.
- Added parcel-purpose, structure-function and entrance fields to `SettlementAtlasCell`, plus stable room-center labels. These remain read-only projections of the physical plan.
- UI copy is intentionally functional and sparse: names, categories, counts and actions only. No decorative slogans, generated mottos or narrative filler are added to the settlement screens.

### Validation added
- exact atlas cells expose parcel purpose, structure function, entrance state and room labels
- active physical plans take precedence over cache reads
- persisted prepared plans can be viewed without generation
- settlement detail view fits 800x520, 1280x800 and 1920x1080
- every settlement-detail pointer target remains inside the window at tested resolutions
- detail mode exposes only inspect/back interactions and does not leave the world-atlas drag target active
- inspected world coordinates round-trip correctly from the rendered plan
- Fast Gate atlas coverage now includes the settlement-detail UI module

### Next dependency
Expand the physical settlement planner with missing civic/service workplaces (market, healer, guard/watch, shrine, school/archive) and bind those professions to real structures. Keep the same UI rule: expose the resulting complexity through context and inspection rather than adding more always-visible panels.


## Work unit 7 - Civic services, regional trade foundation, and social identity
- Settlement-plan version advances to v2 because this unit changes persistent physical layouts by adding civic/service parcels and buildings. Existing v1 generated plans remain old-version cache data and are not silently treated as v2 layouts.
- Settlement cores can now allocate real market, clinic, watchhouse, shrine, archive and (city-scale) school parcels before housing consumes the best street frontage.
- Civic buildings are physically assembled from the existing construction catalog and pass through the same enclosure/room detector as homes and workshops. Market/shop, clinic, watch, sanctuary and study rooms now produce distinct building classifications.
- Merchants, healers, guards, scholars and priests bind to real market/clinic/watchhouse/archive-or-school/shrine structures instead of remaining workplace-less.
- NPC AI now routes real needs to these buildings: eating/social contact use market space, injuries/illness use clinics, guards use watchhouses, faith uses shrines, and learning uses archives/schools. Service actions consume or affect real state where applicable (food, medicine, health, literacy).
- NPC state now carries structured backstory, wants, needs, lineage/household IDs and explicit kinship labels. FamilySystem.ensure_settlement_identity(...) initializes these deterministically for represented residents while preserving existing saved values.
- Initial represented lineages connect plausible generations. Existing marriage/birth simulation continues to evolve those families, and newborns inherit lineage/household identity plus parent/child kinship.
- Existing relationship state remains authoritative for affection/trust/etc.; kinship adds the family-tree role rather than replacing relationship values.
- The existing economy already had item base values, scarcity pricing and copper coinage. This unit adds regional currency metadata per faction/culture, local currency quoting and barter valuation while preserving copper-equivalent settlement/NPC wealth for compatibility.
- Theft is now explicit state through TheftRecordState. Witnessed theft can damage relationships and be resolved by the existing law system with settlement-specific theft law/guard strength. Need-driven NPC petty theft can occur at markets under severe hunger/poverty pressure rather than as a free-floating random coordinate event.
- The old aggregate law crime pressure remains for Tier-C settlement simulation; explicit active-NPC theft records coexist with it rather than replacing distant aggregate simulation.

### Compatibility / authority
- New NPC, settlement and theft fields have defaults and load from older saves without a save-schema bump.
- Regional currency metadata does not create dynamic registry item IDs. core:copper_coin remains the physical base coin for now; local currency names/rates are simulation metadata until minted regional coin variants receive a dedicated item-variant/provenance system.
- Barter valuation reuses the settlement market price authority. There is no second price table.
- Civic service use consumes the same settlement stocks/economy/health state already used elsewhere; buildings do not create a parallel economy.

### Validation added
- town-scale plans contain physical market, clinic, watchhouse, shrine and archive parcels/buildings
- civic occupations bind to compatible generated workplaces
- represented NPCs receive stable lineages, backstories, wants, needs and real kin links
- same-faction settlements share regional currency identity
- barter values use market prices
- witnessed theft persists and can be resolved through law enforcement
- injured NPC goal selection routes to the clinic
- Fast Gate includes civic/economy/social regressions

### Next dependency
Add player-facing trade/barter presentation and ownership-aware theft interactions on real market/container/property targets, then expose NPC family/backstory/relationship detail through focused inspect views rather than a permanent data-heavy panel. Continue expanding service use with time-of-day scheduling only after these physical/service bindings remain stable.


## Work unit 8 - Unified labor authority, daily routines, transactions, and executable barter
- Named NPC work no longer directly creates a second copy of settlement goods. Daily aggregate labor reservations remain the production authority.
- Labor reservations now retain the named representative NPCs physically performing that work. Active representatives receive a stable daily process assignment and record worked hours against it.
- NPC physical work therefore explains the aggregate economy without becoming another production ledger.
- Added a bounded market transaction ledger covering player purchases, sales, barter, NPC purchases, and theft. Transactions retain settlement, participants, local currency identity, copper-equivalent value, goods moved, and minute.
- Transaction history is capped at 400 records so active trade does not grow save state without limit.
- Player barter is now executable rather than valuation-only. Barter transfers actual inventory/settlement stock without minting copper and uses the same scarcity-adjusted local market authority as coin trade.
- The market UI now exposes Buy, Sell, and Barter in one focused flow. It shows copper price plus the settlement's regional-currency value quote, but keeps copper as the physical coin until regional minted variants receive a provenance/minting system.
- Market access uses the physical generated market building when one is active. Legacy/unprepared settlements keep the older settlement-center fallback rather than losing access.
- NPCs now follow a soft occupation-aware daily rhythm layered under urgent needs: work shifts, meal periods, evening social activity, sleep, scholar study time, priest worship preference, and deterministic three-shift guard coverage.
- Urgent hunger, thirst, exhaustion, injury, and similar needs can override the routine.
- Social goal selection now prioritizes spouses/parents/children/kin and routes family social time toward home; non-kin social activity continues to prefer civic gathering places.

### Compatibility / authority
- New transaction/work fields have defaults and load through existing state serialization.
- No save-schema or settlement-plan bump is required; this work changes simulation state and UI behavior, not settlement geometry.
- LaborReservationState remains the economic authority for production; NPCState.assigned_process_id is only a binding to that authority.
- Regional currency remains a quote/identity layer over copper-equivalent accounting. No duplicate price table was introduced.

### Validation added
- named workers bind to current labor reservations
- named work does not directly alter settlement stock
- daily routine bias produces work, meal, rest, and full guard-shift coverage
- transaction records survive state round-trip
- item-for-item barter transfers goods while leaving copper unchanged
- family social selection prefers actual kin and home
- Fast Gate settlement coverage includes economy/routine/transaction regressions

### Next dependency
Add ownership-aware player theft/trespass against real settlement structures and containers, including witness line-of-sight, property ownership, guard response, restitution/fines, and relationship consequences. Then add a compact NPC inspect window with Overview, Family, Relations, Needs, and History tabs fed from the now-stable social state.


## Work unit 9 - Physical property authority, witnessed theft, and NPC profile UI
- Civics now attaches to settlement physicalization. When a settlement plan is active, PropertyState records use the exact stable structure ID as their property ID instead of creating a parallel set of abstract house/shop identifiers.
- Physical homes, markets, workshops, farms, clinics, watchhouses, shrines, archives and schools receive property claims/value/capacity metadata. Structure condition remains the physical-plan authority; property state mirrors it rather than creating a second damage/decay model.
- Legacy aggregate property generation remains only as a Tier-C fallback for distant or unprepared settlements and is ignored while an authoritative physical plan is active.
- NPC home_id and property_id now point to the same physical residence structure. Civics derives occupants from those bindings and no longer overwrites an active physical home assignment during monthly housing updates.
- Added ownership lookup for physical structures so crime and later trespass/rent systems can identify the actual owner rather than a synthetic property record.
- Player market theft now targets the generated market building and real settlement stock. It requires physical proximity, records the market structure/property source, transfers the stolen goods, and determines witnesses from actual nearby NPC positions plus line of sight.
- Theft records now retain property/source context and explicit witness NPC IDs. Witnesses and victims can lose trust/respect toward the thief through the existing relationship state.
- Witnessed player theft accumulates local crime heat. The law system can convert a reported theft into a settlement-specific bounty according to local theft law and guard strength. Crime heat slowly falls; bounty debt persists.
- The market UI now includes a restrained Steal flow with item, quantity and review steps. It reports local bounty status without adding a separate crime dashboard.
- Right-clicking a known NPC now offers a focused Inspect action. Unknown people remain strangers until spoken to, preserving the existing knowledge boundary.
- Added a movable/resizable NPC profile window with Overview, Family, Relations, Needs and History tabs. It shows context-specific information instead of one dense stat sheet, uses qualitative relationship/need labels, hides raw stable IDs, and does not reveal undiscovered relatives by name.
- Terminal fallback exposes the same profile sections through a text document after tab selection.

### Compatibility / authority
- New player bounty/heat and theft witness/source fields have defaults and serialize additively; no save-schema or settlement-plan bump is required.
- Physical StructurePlanState IDs are now the active property identity. Parcel IDs remain land-use/access geometry, not ownership IDs.
- Property maintenance does not mutate a second condition value for physical structures; future repair/destruction must continue through physical-plan deltas.
- Distant aggregate civics remains bounded and does not force settlement materialization.

### Validation added
- active civics properties are exact generated structure IDs and include the physical market
- monthly civics updates preserve physical NPC home bindings
- witnessed player theft records the market property and witness IDs, moves real stock, raises heat and can become a bounty
- NPC profile data hides undiscovered relative names and raw internal IDs
- the graphical NPC profile stays within 800x520, 1280x800 and 1920x1080 and exposes tab, drag, resize and close targets
- Fast Gate settlement coverage includes property/crime/profile regressions

### Next dependency
Extend ownership-aware crime from the market to private homes/workplaces and generated storage fixtures, including trespass permissions, locks, restitution and guard confrontation. Then add household budgets/consumption so families buy food, medicine and household goods from the same market ledger instead of relying only on settlement-level aggregate consumption.
