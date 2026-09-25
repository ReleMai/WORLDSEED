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


## Work unit 10 - Building-aware stealth, visual sight cones, and theft casing
- Added an explicit player stealth stance. It persists with the save, can be toggled from Interact actions, and is also offered contextually when casing generated settlement buildings.
- Added a Stealth skill to character creation and legacy-save defaults. Sneaking currently trades speed for quieter movement: stealth movement takes longer and feeds reduced movement noise into the existing hunting/noise system according to Stealth and Agility.
- NPCs now retain physical facing derived from their actual movement. Guard and civilian observation therefore uses where a person is facing instead of omnidirectional generic witnessing.
- Added a bounded StealthSystem that computes observer cones from NPC facing, occupation, guard duty, weather, fog, lighting and exact line of sight. It reads terrain, natural features, player-built structures and generated settlement physicalization through the same obstruction layers used by gameplay.
- Generated walls and other sight-blocking settlement pieces clip observer cones. A player on the far side of a house wall is not considered visible merely because the NPC is nearby.
- The stealth snapshot is read-only and bounded. It reports watched cells, observers, facing/range, which observers currently see the player, and the player's current physical structure/room without realizing new settlement plans from the renderer.
- Market theft now requires stealth mode and uses the StealthSystem witness set. Only NPCs whose current cone and unobstructed line of sight reach the player can witness the theft.
- The market menu exposes Enter Stealth before theft and reports the number of current observers. Theft review names discovered witnesses and keeps unknown observers as Stranger.
- Right-clicking generated buildings now uses their physical StructurePlanState. Outside stealth the player can enter stealth to case the building; in stealth the player can inspect building function, owner, room, condition, current sight coverage, known occupants and watchers. Generated markets expose their real stock theft action directly from the building context.
- Non-market residences/workplaces do not invent loot. Their casing view explicitly states that no stealable inventory exists until a real physical storage/goods source is materialized.
- Pygame stealth presentation draws translucent observer sight coverage over the local world. Amber cells are watched; red coverage and red observer outlines identify observers whose current cone includes the player. Observer facing is shown with a direction mark, and the sidebar names known observers who can see the player.
- Terminal rendering receives the same snapshot. Watched cells are highlighted and the sidebar reports Stealth skill, observed-by count and known observer names without creating a separate visibility simulation.

### Compatibility / authority
- NPC facing, player stealth mode and the Stealth skill are additive save fields/defaults; no settlement-plan or save-schema bump is required.
- Stealth does not own buildings, NPC schedules, crime, or settlement stock. It is a perception/read model over those authoritative systems.
- Theft continues to move real settlement stock and create the existing ownership-aware TheftRecordState/market transaction records. Stealth only decides who actually observes the act.
- Generated building geometry remains the sight-obstruction authority through SettlementPhysicalizationSystem/BuildingSystem. The renderer does not generate or mutate geometry.
- Observer scans are bounded to nearby named NPCs and a limited vision radius so stealth mode does not become an unbounded world simulation.

### Validation added
- an actual generated settlement wall blocks a guard's stealth cone into an interior room
- facing toward the player witnesses while facing away does not
- stealth skill reduces movement noise
- NPC facing follows physical movement
- stealth state/skill/facing survive state serialization round-trip
- Pygame sight-cone overlays alter presentation without mutating simulation state
- existing property-crime regression now requires stealth and obtains witnesses from the stealth authority
- Fast Gate settlement coverage includes building-stealth regressions

### Next dependency
Materialize stable property-owned storage and goods fixtures for residences, workshops and civic buildings so theft can extend beyond markets without inventing loot. After that, add trespass permissions, doors/locks and lockpicking, guard suspicion/search/confrontation, and cover/light/noise refinements while preserving the same physical LOS authority.


## Work unit 11 - Materialized property storage and movement-based casing
- Added stable local property storage tied directly to generated StructurePlanState IDs, physical rooms and civics ownership. Eligible residences, smithies, workshops, mills, fisheries, barns, clinics, watchhouses, archives and schools receive one bounded storage point when their settlement is active.
- Initial property-storage contents are transferred out of SettlementState.stocks. The materialization never creates duplicate goods, and a stable seeded flag prevents a container from being refilled by repeated sync/load cycles. Markets continue to use the existing settlement stock ledger instead of gaining a second container ledger.
- Private property containers carry settlement/property/room provenance plus owner/access/lock metadata. Normal storage menus exclude private containers so ordinary Take/Store actions cannot bypass theft rules.
- Replaced the previous whole-building Case Property dossier with movement-based casing. Starting a casing session only selects a nearby physical property and enters stealth; it does not reveal the owner, layout, occupants or inventory.
- Casing knowledge is gathered only from physical movement and line of sight: walking unique exterior perimeter cells surveys access, approaching the actual entrance identifies it, physically entering rooms learns their layout, seeing nearby occupants records them, and approaching materialized storage reveals that storage location.
- Casing notes expose only gathered information: exterior survey progress, known entrance, learned room kinds, discovered occupants, discovered storage and owner identity only after it is learned. Unknown people remain unidentified and raw stable IDs are not shown.
- Casing is suspicious but is not a crime. It never creates TheftRecordState, player crime heat or a bounty by itself. Repeated observed sessions and observed discovery activity accumulate suspicion against the same physical property and aggregate across properties belonging to the same owner.
- Suspicion has low/noticed/watchful/alarmed bands. Owners, occupants and guards contribute more strongly when they observe the behavior. Higher attention gives relevant observers a modest perception-range increase; repeated high-alarm casing pushes witnessing guards toward guard duty without treating the player as convicted of theft.
- Private storage theft requires all of the physical prerequisites: stealth active, active casing of the same property, that storage previously discovered through casing, and the player physically within reach. Theft removes the actual container item and transfers it to the player inventory.
- Property-storage theft reuses the existing ownership-aware theft/economy records and StealthSystem witness cones. Witnessed theft therefore feeds the existing local crime heat and later bounty path, while unwitnessed theft does not fabricate a witness.
- Pygame renders materialized storage with existing chest/box/basket structure art and keeps casing status compact in the stealth sidebar: survey percentage, attention, rooms learned and storage learned. The terminal renderer provides the same compact state and does not reveal storage through map memory when it is not currently visible.

### Compatibility / authority
- Container provenance/access fields, CasingIntelState and player_casing_property_id are additive persistent state with defaults; no settlement-plan or save-schema bump is required.
- StructurePlanState remains the property/building authority, CivicsSystem remains ownership authority, SettlementState.stocks remains aggregate goods authority, and exact local containers are a local materialization of goods reserved from that ledger.
- Casing is a player-knowledge/suspicion layer over physical structures and NPC perception; it does not own geometry, schedules, law or economy.
- Storage placement is deterministic, remains inside the assigned room, avoids planned fixtures/entrances and active NPC positions, and is skipped rather than inventing an invalid location.

### Validation added
- generated property containers bind to real physical structures and civics owners
- initial stored goods are real settlement stock and repeated synchronization does not reseed or drain stock twice
- starting casing does not reveal whole-home storage; exterior movement increases survey knowledge and physically reaching an interior storage location reveals it
- repeated witnessed casing raises attention while producing no theft record or bounty
- private-storage theft removes the real stored item, transfers it to player inventory and records real LOS witnesses/property provenance
- property container provenance and casing intelligence survive LivingWorldState serialization round-trip
- Fast Gate settlement coverage includes the property-storage/casing regression module

### Next dependency
Add physical door permissions and locks to generated properties, then build trespass state, lockpicking/forced-entry actions and guard confrontation/search behavior on the same property, casing and LOS authorities. Household consumption/budgets can then move goods between these real storage containers and the market ledger instead of remaining only aggregate settlement consumption.


## Work unit 12 - Physical property security, locks, trespass, and response
- Generated settlement doors now expose the stable StructurePiecePlan UID and role through the bounded physicalization layer. Dynamic security state keys directly to that UID; the settlement plan remains the geometry authority.
- Added persistent DoorSecurityState for entrance/interior-door ownership, access class, lock state, lock level, condition, forced/picked state, attempts, and last tamper time.
- Added deterministic security profiles by building function. Markets, clinics, shrines, and schools have public front entrances; workplaces have work access; residences, watchhouses, and archives receive private/restricted locks; some back-room doors can also carry restricted locks.
- Door security synchronization is reconstructable and non-destructive: revisiting an active settlement updates provenance/ownership but does not relock a picked door, repair a forced door, or reroll its security state.
- Player movement is actor-aware at the Simulation boundary. Locked unauthorized generated doors stop the player without making the underlying settlement door impassable to resident NPC pathfinding.
- Locked, intact property doors now obstruct stealth LOS. Once unlocked/picked or forced open they stop acting as a closed security barrier.
- Casing discovers access points only by physical proximity + LOS and assesses a lock only when the player gets within one cell. Casing notes reveal only learned door/lock information, including current lock state and door condition.
- Added LockpickDoorCommand. Lockpicking requires a real core:lockpick, adjacency, and resolves deterministically from Stealth skill + Agility versus the stable lock level. Failed attempts can break the pick. Tampering consumes time and produces a security incident even when unwitnessed; only actual witnesses make it an immediately attributable offense.
- Added ForceDoorCommand. Forced entry uses Strength plus the best carried axe/hammer/pick tool, damages the actual door over repeated attempts, produces high local noise, and permanently marks the doorway forced open once condition reaches zero.
- Added persistent TrespassState. Crossing an unauthorized property boundary or a restricted interior access door activates trespass state; leaving clears the active flag without erasing the incident/history state.
- Owners, occupants, and guards can challenge a visible trespasser. The first observed confrontation warns the player to leave. Continuing after that warning escalates to an active guard search/removal response and records a more serious security incident.
- Guard response reuses existing NPC task primitives: guards are routed toward the affected property/player with guard goals rather than spawning a separate security actor system.
- Added SecurityIncidentState for lock tampering, forced entry, trespass, and defied warnings. Casing itself still creates no incident, crime heat, theft record, or bounty.
- Witnessed security incidents feed the existing local LawSystem. Law enforcement can resolve them into player bounties/recorded charges using local law strength and guard presence; unwitnessed incidents remain unattributed.
- Pygame and terminal stealth sidebars show active trespass/search state, while right-click door actions expose inspect, lockpick, and force-entry choices. Unknown lock quality is not leaked unless casing has physically learned it.

### Compatibility / authority
- New door/trespass/security records and casing door/lock knowledge are additive state with defaults; no settlement-plan or save-schema bump is required.
- Generated StructurePiecePlan remains door geometry authority, CivicsSystem remains owner authority, PropertySecuritySystem owns only dynamic security/access state, StealthSystem owns LOS witnesses, NPCSystem owns movement/tasks, and LawSystem owns charge/bounty resolution.
- NPC pathfinding is intentionally not globally blocked by resident property locks in this stage. The player-specific security gate lives in Simulation movement so residents can still reach bound homes/workplaces until actor-aware permissions are generalized.

### Validation added
- secure generated residence doors have stable private locks and public civic entrances remain public/unlocked
- security sync preserves picked/unlocked state rather than rerolling
- casing does not reveal lock quality from a remote whole-property action; physical door observation is required
- lock tampering and forced entry produce security incidents without fabricating theft records
- forced entry damages and opens the actual stable door and emits noise
- unauthorized entry creates persistent trespass state, visible warnings, and an escalating guard search after the warning is ignored
- door/trespass/security state survives LivingWorldState serialization
- witnessed security incidents can resolve through local law into a bounty
- Fast Gate settlement/security coverage includes these regressions

### Next dependency
Generalize actor-aware door permissions for resident/employee/guest keys and scheduled locking, then add container locks, key ownership, lock/key crafting, guard stop/search interactions, surrender/flee/bribe choices, and property-owner reactions to discovered damage or missing goods. Household schedules can then lock/unlock the same stable doors as occupants leave, work, sleep, and return.


## Work unit 13 - Actor-aware property access and scheduled doors
- Property security now consumes the existing physical home/property/workplace bindings when deciding whether a local actor can pass a locked generated door. Residents and employees no longer need NPC pathfinding to ignore security in order to reach their own homes or jobs.
- `DoorSecurityState` adds sparse `keyholder_uids` grants for explicit guest/future physical-key access. These grants are exceptions only; household and employment membership remain authoritative in the existing NPC/property bindings.
- Added bounded local opening schedules for generated workplace and public-service entrances. Workplaces and services close deterministically by hour while the settlement is active; private/restricted security remains unchanged.
- Scheduled lock provenance is tracked separately from the raw locked flag. Opening hours only undo locks created by the scheduler and never unlock unrelated security state.
- Picked and forced doors are not relocked or repaired by the schedule. A later owner repair/security action must restore them.
- `NPCSystem` now consumes the same `PropertySecuritySystem` as player movement. Exact nearby pathfinding treats unauthorized locked doors as blocked, while residents/employees/keyholders can route through their permitted doors.
- Fixed a local-fidelity escape hatch where an NPC with no exact local path could fall through to aggregate straight-line movement and ghost through a physical obstacle. Nearby actors now wait/replan; only remote aggregate actors use the coarse movement fallback.
- Door schedules update at active-settlement synchronization and on hourly local simulation boundaries. Distant Tier-C labor/schedules remain aggregate and do not force physical door state.
- Existing casing/door inspection surfaces read the same `DoorSecurityState`, so scheduled closures are visible without a second UI-owned state model.

### Compatibility / authority
- `keyholder_uids`, `schedule_locked`, and `last_schedule_minute` are additive `DoorSecurityState` fields with safe defaults; no save-schema or settlement-plan version bump is required.
- Home/work/property bindings remain resident/employee authority. Door security owns only dynamic access/lock state and sparse explicit grants.
- Physical key items are not invented in this work unit; the keyholder grant is the stable permission target that the later key ownership/crafting system will consume.
- Exact door schedules are local/Tier-A/B behavior. Distant settlement economy and labor remain bounded aggregate systems.

### Validation added
- a resident can traverse the locked entrance of the physical home bound to that NPC while a stranger cannot
- explicit player keyholder access survives LivingWorldState serialization and permits the same stable door
- workplace entrances close after hours and reopen during their deterministic schedule
- public-service entrances close after hours for ordinary player access
- picked work doors remain open instead of being silently repaired/relocked by the schedule
- nearby NPC pathfinding honors actor-aware locked-door permission and cannot fall back to coarse movement through a blocked local door
- existing property storage/casing, settlement population and building-stealth regressions remain green

### Next dependency
Materialize container locks and physical keys/key ownership/crafting on top of the new access-grant substrate. Add owner reactions to discovered damage/missing goods and guard stop/search choices (surrender, flee, bribe/restitution). Then move household budgets/consumption and local hauling through the same real market/property storage authority.


## Work unit 14 - Materialized property container locks
- Private generated property storage now has persistent deterministic locks.
- Store/take/theft paths consume the same lock authority; casing knowledge does not bypass a lock.
- Picked/tamper/keyholder state persists and active sync does not repair picked storage.
- Next: physical key ownership/transfer/crafting and interaction UI.


## Household logistics integration
Named settlement residents now participate in a physical household economy. Family groups bind to their generated home and its property storage; daily reserve planning creates persistent market deliveries carried by named household members to real containers. This preserves the settlement planner/physicalization layer as the location authority while allowing distant simulation to complete overdue deliveries at coarse fidelity. Market stock, NPC wealth, settlement wealth, container capacity and transaction history remain conserved across the flow.


## Workplace production/logistics integration
Active workplace bindings now feed a two-tier production model. The settlement labor reservation remains the workforce authority, while a bounded share of batches is materialized through the property storage attached to a representative worker's generated workplace. Inputs can persist as next-day buffers, outputs can remain visible at the workplace, and excess output travels as persistent worker-carried shipment cargo to the market. Distant/unmaterialized workplaces continue using the original aggregate process path.


## Work unit 19 - Authored settlement autotiles and doorway geometry polish
- Settlement-plan geometry advances to v3 for new worlds. Existing v1/v2 saves stay pinned to their recorded plan contract; the new geometry is not silently substituted into old physical plans.
- Exterior entrances are no longer selected from arbitrary shell cells. The planner now considers only non-corner edge cells with a cardinal interior floor directly behind the threshold, then prefers the approach facing the nearest road. This removes the case where a door looked open but a corner wall still blocked movement.
- New v3 buildings stamp a real floor threshold under exterior doors and can stamp a short footpath apron from the entrance toward the parcel access road.
- Wall placement now uses the settlement catalog semantically: straight wall pieces on edges, corner pieces on corners, and reinforced pieces on internal partitions. Ordinary non-mining buildings deliberately use the wood door rather than whichever opening happened to sort first.
- Added three authored 32px settlement autotile atlases: 16-way wall connectivity for timber/plank/stone/wattle, 16-way floor edge blending for plank/stone/packed-earth/clay, and orientation-specific doorway art for wood/ironbound/wattle/stone openings.
- The pygame renderer derives cardinal connectivity from authoritative physicalization cells and selects the exact authored frame. Walls therefore join through corners and doorframes instead of appearing as isolated blocks; floors suppress seams between connected interior tiles and keep darker boundary shading only at exposed edges.
- Door rendering now follows the wall axis, visually leaves the threshold passable, and overlays lock/forced-state cues from the existing PropertySecuritySystem. Legacy v2 door cells borrow the adjacent interior floor only for presentation so older saves do not show a bare terrain hole under the doorway.
- VisualRegistry now owns and audits the settlement autotile assets, so release asset checks fail if an atlas is missing.

### Validation added
- new-world settlement plan version is v3
- every generated exterior entrance is non-corner, has a threshold floor, and has a cardinal interior floor neighbor
- generated buildings use straight/corner/reinforced wall semantics
- every settlement wall/opening/floor has an authored autotile render path
- wall connection masks, floor edge masks, and N/S versus E/W door frames render as distinct images
