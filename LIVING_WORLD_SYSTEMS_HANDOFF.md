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
