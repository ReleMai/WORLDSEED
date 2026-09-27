# WORLDSEED Living World Systems Handoff

## Canonical baseline

This unified stream starts from GitHub `main` at `f3863a6` (`Stabilize integrated hunting and settlement build`). The earlier hunting and settlement feature branches are superseded; the integrated implementation on `main` is authoritative.

This handoff coordinates the systems that now depend on the same physical world: hunting/animal behavior, combat integration, settlement generation, NPC homes/workplaces/routines, economy/labor/transactions/households, property/storage, stealth/perception/casing/theft/trespass, security/guards/law, and the UI that exposes those systems.

## Shared authority contract

- Simulation/ledger state owns population, needs, stocks, labor, transactions, crime/law, relationships and ecology.
- Regional/settlement physical plans own stable roads, parcels, structures, rooms, fixtures, doors and ownership links.
- Local materialization projects those stable IDs into exact nearby geometry and actors; it never creates a second town/economy/ecology.
- NPC home/work/property bindings are the authority for local access. Security reads those links instead of maintaining a second household/employment roster.
- Exact schedules, local doors, witnesses and pathfinding run only where the settlement is physically active. Tier-C and farther simulation remains aggregate and bounded.
- Renderer/UI remains observational and commands remain the mutation boundary.

## Completed integrated foundation

### Hunting and combat through Phase 7

- Persistent animal state, species behavior data, hunting detection and combat integration.
- Explicit weapon handling, tactical aim, melee reach, stamina/time costs and physical projectile semantics.
- Projectile cover, shields, active defensive choices, attack modes, shield bash and combat test arena coverage.
- Tactical animal combat profiles including charges, pack behavior and herd panic/cohesion.
- Physical displacement, collision trauma, reach interception and disengage spacing.
- Unified Normal/Stalk/Crouch stealth intent shared with settlement perception.
- Animal hunger/thirst routines, real water/forage use, persistent homes/rest sites and wounded retreat.
- Physical evidence from real movement/activity: tracks, blood, scat, feeding/bedding/water/vegetation signs, calls and home-use signs.
- Data-driven animal anatomy, named vital trauma, anatomical harvesting and bounded presentation-only combat effects.

### Settlement life/security through Work Unit 12

- Terrain-aware settlement skeletons, parcels, procedural buildings/interiors and exact local materialization.
- Stable NPC home/workplace/room/bed/property bindings backed by the physical plan.
- Exact settlement atlas/detail UI over authoritative plan geometry.
- Civic services, regional trade/social identity, unified labor reservations, daily routines and persistent transactions/barter.
- Physical property authority, ownership-aware market theft and NPC profile UI.
- Shared stealth sight cones, building-aware LOS, movement-based casing and suspicion.
- Property storage seeded by transfer from real settlement stock rather than invented loot.
- Stable door security, lockpicking/forced entry, trespass, witnessed incidents, guard warning/search escalation and law/bounty integration.

## Work Unit 13 - Actor-aware access and scheduled settlement doors

Status: implemented in this development unit.

- `PropertySecuritySystem` now authorizes actors from existing physical home/property/workplace bindings. Residents and employees can traverse their own locked doors without creating a duplicate access roster.
- Stable door state supports sparse `keyholder_uids` grants for explicit guest/future-key access. This is only the permission substrate; physical key items and key crafting remain a later system.
- Public-service and workplace entrances now follow deterministic local opening hours while the settlement is active. Private/restricted doors retain their stronger security profile.
- Scheduled closure records whether the scheduler created the lock state. Opening hours therefore do not unlock unrelated/manual security state.
- Picked or forced doors are never silently repaired or relocked by the schedule.
- Nearby NPC pathfinding now consults the same actor-aware door security used by player movement. If an exact local route is blocked, an NPC waits/replans instead of falling through to coarse straight-line movement and ghosting through the door.
- Distant/Tier-C actors keep aggregate movement/labor behavior and do not require physical door simulation.
- Existing door inspect/casing UI automatically reflects scheduled locked/open state because it reads the authoritative `DoorSecurityState`; no parallel UI state was added.

## Sequential roadmap from this point

1. **Property security completion** - materialized container locks; physical key ownership/transfer and lock/key crafting; explicit guest access UI; owner reactions to broken doors, picked locks and missing goods; guard stop/search interaction with surrender/flee/bribe/restitution choices.
2. **Household economy and logistics** - household budgets, food/medicine/household consumption, purchases from the existing market ledger, movement of owned goods between market and property storage, local hauling and visible shortage/closed-shop consequences.
3. **Hunting progression and traps** - persistent traps/snares, bait/scent/species suitability, delayed outcomes/ecology reconciliation, skill progression for reading sign/stalking/shot placement/processing, and animal investigation of uncertain sound/scent sources.
4. **Deeper animal territory and evidence** - territorial memory, den/young defense, predator-prey encounters, pack target switching/wounded-member behavior, continuous trail reconstruction and weather/terrain erosion of sign.
5. **Crime/law and social consequences** - richer property-owner discovery, restitution/fines, relationship/memory consequences, guard pursuit/search persistence and settlement-specific legal process while preserving witness/LOS authority.
6. **Household/property lifecycle** - rent/tenure where appropriate, household moves, construction/repair demand, inheritance/ownership transfer and long-term physical-plan consequences without creating a second property simulation.
7. **Milestone hardening/playtest** - after the security + household + hunting-progress loop is integrated, run Full Validation & Package and produce the next playtest build before moving into broader conflict/civilization work.

## Validation rule

Use targeted local tests during each coherent work unit, then GitHub Fast Gate for integrated publication. Full Validation & Package is reserved for substantial milestones or a new playtest build. Fix causes rather than bypassing failing assertions.


## Work Unit 14 - Materialized property container locks

Status: implemented in this development unit.

- Generated private property storage now materializes with deterministic persistent lock strength by building function.
- Container locked/picked/tamper/attempt/keyholder state serializes with the existing container authority.
- Existing untampered pre-lock storage gains its deterministic lock during active sync without reseeding goods; picked storage is not silently relocked.
- A dedicated LockpickContainerCommand reuses the existing lockpick item and player stealth/agility progression.
- Normal store/take and property-theft paths consume the same lock authority. Casing can reveal storage but does not bypass the physical lock.
- Sparse container keyholder grants provide the permission target for the next physical-key item system.

### Next dependency
Add physical key items bound to stable lock identities, ownership/transfer and duplicate-key/lock crafting, then expose lock/key status and guest access through the interaction UI.


## Work Unit 15 - Physical keys
- Doors and property containers have stable lock identities across saves and resync.
- Individual persistent keys bind to one lock and track owner, label, copy provenance and creation time.
- Matching key possession opens locked doors/containers without mutating property permissions.
- Keys transfer between actors and duplicate into distinct persistent copies targeting the same lock.
- Simulation commands support transfer and duplication; lockpicking remains the unauthorized fallback.
- Regression coverage verifies unlocking, transfer, duplication and save roundtrip.


## Work Unit 16 - Key/lock interaction polish
- Matching keys now explicitly lock and unlock doors and property storage through authoritative simulation commands.
- Manual door operation clears schedule-lock provenance so a schedule update cannot masquerade as the player's action.
- Picked locks and forced doors cannot be magically re-secured with a key; they require later repair work.
- Inventory presentation exposes the player's persistent key ring, target lock identity and copy provenance.
- Key duplication is no longer free: it requires a nearby forge, consumes one iron bloom and takes 30 in-world minutes.
- Targeted regressions cover lock/unlock authorization and damaged-lock safety.


## Work Unit 17 - Household inventories and consumption (foundation)
- Named NPC family groups materialize as persistent households keyed by existing family identity.
- Household inventories use the already-authoritative physical home storage containers rather than creating a second invisible item ledger.
- Daily household food consumption removes real food stacks from home storage and records persistent shortage pressure.
- Member hunger rises on shortages and recovers when the household is fed.
- Aggregate settlement food consumption excludes named residents processed through households, preventing double consumption.
- This establishes the physical logistics boundary for later shopping, hauling, wages and household budgeting.


## Work Unit 18 - Household budgets, procurement and physical delivery
- Household money remains authoritative on individual members; the household computes spendable wealth instead of duplicating currency in a second ledger.
- Prior-day representative work now pays occupation-sensitive wages from settlement wealth into actual NPC wealth and records market transactions.
- Households calculate adaptive reserve targets from family size, wealth and recent shortage history, covering food plus fuel, soap and medicine.
- Procurement is scarcity-aware and budget-constrained. Market goods and money move at reservation time, preventing duplicate purchases and preserving price pressure.
- Bought goods become persistent HouseholdDeliveryState cargo instead of teleporting into homes. A named household member receives market-pickup/home-dropoff tasks and physically hauls the cargo when exact AI is active.
- Tiered simulation has a bounded coarse-delivery deadline so distant/offline households cannot deadlock economically when their exact actor AI is not running.
- Home container mass/volume capacity is enforced before buying. If storage changes while cargo is in transit, excess goods return to market and the household is refunded.
- Household ledgers retain bounded wage, food, purchase, delivery and refund events; unmet needs remain explicit state for later decision/social systems.
- Tests cover real storage consumption, market/cash reservation, physical pickup/dropoff, budget/stock limits, wages and save roundtrip.

- WU18 also keeps non-materialized households explicitly in aggregate logistics mode. They are not removed from settlement-wide food demand until a real home-storage container exists, preventing named distant residents from accidentally consuming zero food. Delivery movement tasks carry their delivery identity so coarse completion can cleanly cancel obsolete travel work.

- The Fast Gate settlement/economy regression step now includes `tests.test_household_economy`, so household conservation, wages, procurement, logistics tiers and save compatibility are enforced on every relevant PR rather than relying on an uninvoked standalone test file.

- Aggregate settlement food demand now uses a ceiling-style population ration calculation. After exact households are removed from the aggregate pool, one or two remaining anonymous residents still consume food instead of becoming a zero-cost rounding remainder.


## Work Unit 19 - Physical workplace production and market logistics
- Active named workers now bridge aggregate labor reservations into exact workplace production without creating duplicate output.
- A bounded physical share of a process consumes inputs already held in the worker's real workplace storage. Remaining labor continues through the aggregate settlement ledger, preserving scalability.
- Workplaces replenish one-batch input buffers from settlement stock after production, creating visible next-day supply buffers rather than making every input teleport at production time.
- Total output keeps the same culture/religion production bonus and is split between physical workplace stock and aggregate market stock while conserving the process total.
- Persistent workplace logistics records track representatives, physical batches, staged inputs, retained outputs, overflow, market transfers, blocked reasons and a bounded event ledger.
- Excess workplace output is reserved into persistent market shipments. Named workers receive source-pickup/market-dropoff tasks; distant/offline shipments have bounded coarse completion so Tier-C simulation cannot deadlock.
- Shipment cargo exists outside both source storage and market stock while in transit. Market availability therefore responds to real local delivery delay rather than instant stock teleportation.
- The Fast Gate now runs dedicated workplace logistics conservation and persistence tests.


### WU17 household resilience layer
- Household food consumption now prefers dietary variety while remaining scarcity-safe, recording persistent diet composition and nutrition quality.
- Physical fuel, hygiene supplies and medicine are consumed on distinct household cadences rather than acting as decorative reserve targets.
- Food, fuel, hygiene, medicine and poor diet combine into a bounded hardship score that changes member health/safety needs and tracks stable recovery days.
- All consumption remains attached to real home containers; no invisible duplicate household stock was introduced.


### Dev UI overlay hotfix
- Fixed retained local-world weather/water/hover animation repainting over inventory and right-click context overlays during idle input waits.
- Floating and context panels now explicitly suspend world-only hover animation state while they own UI input; the next local-world render reconstructs it normally.
- This fixes the symptom where the panel visually disappeared but the hidden modal still captured input until Escape.


### Dev UI/settlement test-start polish
- Context menus now dismiss with right-click or a left click outside, and fishing invoked from world context stays in nested cursor-anchored context menus.
- Inventory item context remains anchored while hovering other cards; clicked recipe selection is persisted before returning to the crafting controller.
- Crafting categories are top tabs with NEW markers, discovery is now a five-slot Experiment Grid with red/yellow/green recipe proximity, right-click slot removal, known-combination feedback, and zero-path materials hidden.
- New-game setup now offers a deterministic Village starting location beside a generated settlement for settlement testing.


### Interaction/crafting/village playtest polish
- World context popups are now true live overlays: water/weather/lighting continue animating behind them while the popup redraws over the current frame.
- Right-click or left-click outside restores only the popup region and closes the menu; nested fishing choices remain cursor anchored.
- Discovery Pot user-facing terminology is replaced by Experiment Grid. Its five-slot pentagonal circuit signals invalid/near/ready combinations in red/yellow/green, identifies already-tried exact mixes, and supports right-click slot removal.
- Recipe category navigation is horizontal with unseen-recipe markers, and recipe click selection persists in the controller.
- Inventory chrome is less repetitive and half-stack behavior is exposed as a visible HALF quantity selector rather than implying a second physical stack exists in the aggregate inventory model.
- Village Start now imports its generator dependencies explicitly and preferentially chooses a true village-rank settlement before falling back to another settlement.


### WU18 crafting bootstrap and village-start correction
- Fixed the legacy Twist Cordage content collision: the old recipe is now explicitly brush-to-fiber processing, while the two-brush primitive recipe produces actual Cordage.
- Experiment discovery now uses authored 1-5 item signatures separated from full crafting cost. Registry validation rejects any recipe with no valid 1-5 clue signature, and the two recipes whose build cost exceeds five items now define explicit five-item research signatures.
- Added a Crude Knife from one stone flake plus bark with early cut/skin/butcher/scrape capability.
- Crafting's three primary tabs are icon-only with hover tooltips; moving across a tab requests a lightweight UI redraw so the tooltip appears immediately.
- Removed connector lines from the five-slot Experiment Grid; the isolated slots retain red/yellow/green recipe proximity feedback.
- Fixed Village Start being overwritten to 'custom' during new-world setup. Village start now persists the selected origin, builds the same authoritative settlement skeleton used by runtime physicalization, and places the character just outside a settlement gateway.


### Village-start load-order hotfix
- Root cause of the village-start load failure was startup ordering: the new gateway-spawn helper asked SettlementSkeletonPlanner to build the village before hydrology had been prepared/attached. For worldgen v5+, EnvironmentalFieldSampler intentionally returns no site fields before that point, so the planner correctly raised "Settlement anchor has no legal common site inside planning bounds."
- Village startup is now two-phase. A cheap deterministic village target is selected first, hydrology/environmental fields are prepared around its anchor, and only then is the authoritative settlement skeleton built and the player placed just outside its gateway.
- Base-ocean strategic anchors are rejected during the cheap selection phase. Regression coverage verifies target selection never invokes the skeleton planner before environmental preparation and that final placement is two cells outside the planned gateway.


### Village anchor root-cause correction
- The repeated Village Start failure had two independent causes that the prior hotfix did not remove. Candidate discovery still instantiated RegionBlockPlanner before hydrology, which persisted a fallback-field anchor; after hydrology the gateway code reloaded that stale anchor rather than re-scoring the region. In addition, SettlementSkeletonPlanner's error claimed the full planning bounds had no legal common while its fallback searched only 12 cells, far smaller than village/town/city bounds.
- Village candidate discovery is now purely strategic and never creates a regional plan. Startup prepares hydrology around candidate region centers, explicitly refreshes the regional plan with real environmental fields, refreshes the settlement skeleton, and tries bounded alternate settlement candidates if a hydrology-resolved site is genuinely invalid.
- Common-site fallback now searches the complete planning bounds. New regressions verify no pre-hydrology planner is used, post-hydrology refresh is mandatory, and legal land beyond 12 cells is accepted.

- Candidate population/rank selection now derives the settlement RNG directly rather than instantiating the society generator without a planner. The latter consumed two fallback-coordinate RNG draws and could classify a different settlement rank than the hydrology-aware settlement that would actually be created.
- Village-start validation plans are transient (persist=False); only the normal simulation materialization path persists the region/skeleton after a candidate is known to be physically valid, so rejected candidates cannot poison the new save with invalid plans.

### Village graphical materialization hotfix
- Root cause of the invisible village was presentation-only: authoritative settlement walls, doors, floors and roads were present in the physicalization index, which is why collision, casing and NPC interactions worked, but the pygame renderer never projected those cells. Only the text renderer consumed settlement glyphs.
- The local graphical renderer now queries only settlement cells intersecting the viewport. Generated roads and floors are painted as top-down material tiles before entities; walls, doors, roofs and fixtures reuse the authored structure sprite set, with deterministic visible fallbacks for rare civic/decorative pieces.
- Natural resource sprites are suppressed where physical roads/buildings clear a cell. Exterior roofs cover interior cells while the player is outside; entering a building exposes its generated floors and fixtures.
- Hover inspection now identifies generated building functions and settlement pieces.
- Fast-Gate regressions require graphical coverage for every settlement piece and verify the physicalized viewport contains generated roads, walls and building floors.


### WU20 connected settlement art and doorway geometry
- Settlement-plan contract advances to v3 for new worlds because generated doorway/frontage geometry changes. Loading now pins the planner to each save's stored `settlement_plan_version`, so older v2 saves retain their established physical layouts instead of silently regenerating.
- Exterior building entrances can no longer occupy shell corners. The planner selects a non-corner edge cell with a cardinal interior floor immediately behind it and biases the outward side toward the nearest settlement road.
- Each exterior doorway receives a real threshold floor plus a short parcel-contained frontage path toward its access road. Interior doors reuse the room floor rather than stacking duplicate threshold pieces.
- Pygame settlement art now uses N/E/S/W connection masks. Wall pieces form continuous top-down runs, elbows and intersections; door tiles inherit the same wall axis and render as a framed opening inside the connected wall instead of an isolated door sprite.
- Settlement floors share one visual plane across adjacent room cells: internal grid seams disappear and dark edge shading is reserved for exposed boundaries. Roads use connected silhouettes with transparent shoulders so dirt/gravel/cobble/plank paths blend into underlying terrain rather than reading as square strips.
- Existing authored roof/floor/fixture assets remain integrated as texture/detail sources; generated connected geometry handles the directional wall/door/floor layer.
- Regression coverage now requires non-corner entrances, cardinal interior access, exterior thresholds/frontage, save-pinned settlement-plan versions, and distinct connected-vs-isolated wall/floor render variants.

- Wall piece identity now follows generated topology as well as rendering: straight runs use straight wall catalog pieces, orthogonal joins use corner pieces, high-degree joins use reinforced pieces, mining construction defaults to stone-arch doors, and ordinary buildings use wood doors instead of the previous alphabetical ironbound-door fallback. Default generated floors explicitly choose the plain material variants.

## Revised Phase 4 - Grand Regional Civilization: Living Populations & Territorial Sovereignty

Primary rule:

> NPC decisions may be abstract, but NPC actions near the player must occur physically in the same world the player occupies. Territory may be strategic, but every change in control must ultimately be explainable by settlements, monuments, people, roads, supply, or conflict.

Implementation order:

1. Introduce the fixed WORLDSEED simulation tick and move active NPC locomotion off hourly_update.
2. Split NPC AI into utility selection, plan generation, and tick execution.
3. Add activity/affordance and reservation systems.
4. Convert jobs into physical multi-step activities.
5. Create generated claim-monument sites with strategic + blue-noise placement.
6. Build persistent ClaimMonumentState, control propagation and contested-region calculations.
7. Add scout/capture/defend/supply/attack faction missions.
8. Materialize monument structures, garrisons, repairs, destruction and rebuilding.
9. Tie monument supply into the Phase 3 road network.
10. Add knowledge-aware political borders and monument/frontier overlays to the atlas.
11. Allow player capture, sabotage, repair, defense and eventual faction ownership.
12. Expand NPC social, family, market, religious, criminal, military and emergency activities.

### Phase 4 Work Unit 1 - Fixed local simulation tick + staged NPC AI

Status: implemented on the Phase 4 development branch.

- Added a deterministic 5-game-minute WORLDSEED simulation tick anchored to absolute world minutes.
- Normal advances up to six game-hours replay exact active ticks; larger waits fall back to bounded coarse/hourly progression rather than iterating thousands of local ticks.
- Tier-A NPC locomotion is no longer driven by hourly_update during normal play. Hour boundaries update needs/utility state; fixed ticks advance physical movement.
- Split NPC AI into select_utility_goal(), generate_plan(), execute_tick(), decision_update() and tick_update(), retaining _choose_goal_and_plan()/hourly_update() compatibility shims for callers not yet migrated.
- Physical movement still uses the existing local passability, building collision, crossing and actor-aware property-lock checks.
- Non-movement effects such as work/eating/social actions deliberately remain on coarse cadence for this work unit. Moving them to every 5-minute tick would multiply production/consumption before Phase 4 activity durations and reservations exist.
- Added regression coverage for absolute tick boundaries, bounded replay, AI-stage separation and active locomotion staying out of the decision update.

Next coherent work unit: activity/affordance + reservation authority, followed by converting at least one job (recommended: farmer or smith) into a physical multi-step activity using reserved stations/inputs and explicit durations.

### Phase 4 Work Unit 2 - Physical activity affordances, reservations, and smith work

Status: merged to canonical main in Phase 4 Work Unit 2.

- Added `ActivitySystem` as the authority for nearby physical activity opportunities and exclusive station reservations.
- Affordances are reconstructed from the active settlement skeleton and authored settlement-piece metadata. They are not serialized as a second world model.
- Added persistent `ActivityReservationState` records keyed to stable physical fixture IDs, exact use cells, actor, phase, duration, lease/expiry and completion state.
- Reservation conflicts cover both the physical target fixture and its standing cell so two nearby named actors cannot occupy the same station slot simultaneously.
- Promoted smith work to the first explicit multi-step physical job: reserve forge -> walk to forge -> heat -> reserve/walk to anvil -> shape -> reconcile representative work exactly once.
- Smith activity duration now advances on the fixed Phase 4 simulation tick. The actor remains physically at the reserved station while the phase is active.
- Existing aggregate labor/production remains authoritative. Completing the physical smith chain calls the existing representative-work reconciliation and does not mint a parallel output batch.
- Other occupations intentionally retain the existing coarse work path until their own station/resource/activity chains are defined.
- Reservations persist across save/load, expire when abandoned, and are derived from stable settlement-plan fixtures rather than renderer state.
- Added Fast Gate coverage for affordance derivation, reservation exclusivity/persistence, the forge-to-anvil task chain and exactly-once smith work reconciliation.

Next coherent work unit: extend the activity framework to input/output affordances and physical hauling so a smith (and then farmer/carpenter) must acquire reserved inputs from real workplace storage, use the reserved station chain, and place outputs into real storage before aggregate market logistics can move them.

### Phase 4 Work Unit 3 - Physical miners and settlement goods flow

Status: implemented on the Phase 4 miner development branch pending Fast Gate publication.

- Added persistent named-NPC carried inventory plus profession-specific skills and skill XP. Miners currently develop mining, prospecting, hauling and cavecraft.
- Added a bounded public cave-entrance query so profession AI can prospect deterministic natural cave systems without scanning realized chunks or using private cave-generator caches.
- Miners now select a real cave and a real underground material face from authoritative cave geology. Prospecting skill expands search range/depth and biases target selection toward valuable material while travel cost still matters.
- Ore/material value is recorded from base item value, vein rarity, hauling distance and depth. This value is attached to the mining trip/physical transfer rather than changing geological spawn probability.
- Added explicit surface-to-cave connector activities. Miners physically travel to a natural cave mouth, descend its real connector, path to an adjacent mining position, reserve the mineral face, spend activity time extracting it, and ascend the same connector.
- Extraction mutates the same cave terrain delta used by player mining. A mined vein/wall becomes its authored depleted terrain and the yielded material enters the named miner's carried inventory.
- Added SettlementPhysicalGoodsSystem as the generic authority for NPC cargo to/from physical settlement-container transfers. Transfers are persisted with item quantities, source, direction and valuation.
- A miner returns carried ore/coal/stone to a dedicated Mining House Ore Bin in the miner's bound industrial workplace. The miner stands beside the container and deposits the real carried stacks; the transfer does not also add them to SettlementState.stocks.
- Added a generic physical-labor reconciliation hook to the economy. A named exact miner claims/replaces the matching represented aggregate labor batch, preventing the daily economy from minting duplicate abstract ore while that miner is physically extracting cave material.
- Active miner trips remain fixed-tick physical work through Tier B so a miner does not freeze merely by walking outside the immediate viewport or descending one cave level. Once the player leaves the nearby area entirely, normal bounded LOD cadence resumes.
- Physical mining travel uses passability/pathfinding even outside the viewport, with bounded local waypoints for longer cave trips.
- Added regression coverage for persistent miner skills/inventory, rarity/distance/depth valuation, cave/vein selection and reservations, real terrain depletion, carried cargo, mining-house deposits, physical-transfer ledgers, future physical input withdrawal and aggregate-labor replacement.

The current mining-house implementation intentionally uses the miner's already-stable bound mining industrial property and adds a dedicated ore-bin authority inside it. It does not silently change the settlement-plan version or re-roll existing structure IDs. A future settlement-plan migration can promote this into a separately generated minehouse/workyard structure without invalidating current save geography.

Next coherent work unit: connect smithing to the new physical-goods authority. Smiths should reserve/withdraw iron ore and coal from real settlement/mining storage, carry those inputs to the forge, consume them during the physical forge/anvil chain, and deposit the resulting bloom/product into physical smithy storage before market logistics can aggregate it.
