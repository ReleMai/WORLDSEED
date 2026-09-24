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
