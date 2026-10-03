# Dev50 settlement access, storage and introductions

Baseline: canonical main `92ff972c04ea3e9e93d5fdf377a77c40e7008a19`, fetched and
workspace-preflight verified. Original dirty D: checkout remains untouched.

## Player-facing changes / scope

- New town plans put enclosed entrances on south-facing, reachable frontages,
  matching the upright facade art. Every usable entrance gets an authoritative
  service road. Split-rail fences join across cells and around corners; gates
  are placed between reachable exterior and interior cells, not on corners.
- Unbound fallback gateways stop near local streets instead of making a long
  road to the empty plan edge. Selected strategic roads/crossings remain intact.
- Building art anchors its painted doorway on the physical door. Removed the
  roof/sidebar threshold boxes and added soft ground-contact shadows.
- Ten custom storage styles have building-specific stock tables and mixed locks.
  Homes/civic cabinets are indoors; productive workshops retain explicitly
  labeled outside Supply Crates for exact-worker cargo, plus indoor storage.
  Indoor right-click menus use real reach, walls, locks and inventory transfers;
  private removal dispatches theft, never an authorized take command. Picking
  remains available only in the HUD-selected Aggressive Stance.
- A stranger's chat starts with an explicit introduction. Only this command
  exchanges names and unlocks ordinary topics. Seen/hearsay NPC knowledge is
  distinct from personally introduced identities. Inspect still shows visible
  clothing/injuries, not an unknown person's private history or relationships.
- Both chicken cutouts were corrected to remove stray cow sprite-sheet pieces.

## Authority / persistent fields / compatibility

Schema stays 3; geography/worldgen/hydrology/coast/route versions are unchanged.
New saves pin settlement-plan v12; old recorded versions remain pinned and v11
catalog/siting is retained. Missing settlement-version metadata still means10.

On activation, v10/v11 plans may receive one explicit `settlement_access` revision1
overlay in the existing physical_plan_deltas table. Original generated cache
bytes/fingerprints remain unchanged. The overlay retains building, room, door
and gate IDs, moving only generated access pieces and adding bounded service
paths. Where an intact neighbor blocks an entire old south facade, a single
outer wall row may be inset to form an apron, retaining at least four rows;
independent saved interiors and housing/workplace capacities remain unchanged.
Picked/forced doors, lock condition, NPC bindings, stocks and container cargo
are preserved. Another mutation already owning that delta ID is never overwritten.
Two synthetic legacy fishing cases retain a reachable side portal because a
south apron would shrink their existing 5x4 shell below the 4x4 minimum. Their
selectable door leaf is displayed at that actual portal, not the painted front.
New v12 placement excludes this configuration; the reported town has no such cases.
Stored overlays are applied by prepared reads without terrain queries or writes;
cache deletion/rebuild retains the repair. No renderer/hover performs planning.

ContainerState adds profile_id/interior_space_id/interior_furniture_uid (empty
legacy defaults). Indoor container identities are stored under indoor-storage
keys and bound to persistent freely positioned furnishings during preparation.
Opening/returning/loading never refreshes their loot. All stock selection is an
explicit one-time town-ledger -> physical-container transfer, not a second loot
or production authority. Empty town supplies can therefore yield empty storage.
Migration furniture avoids existing player/NPC bodies and preserves their escape
paths. When all safe slots are occupied, goods remain indoors with an empty
furnishing binding until the next explicit preparation can project them safely.
Pending inventory cannot appear outside, be reached, or be transferred remotely.

LivingWorldState adds introduced_npcs. Missing legacy data treats existing
discovered acquaintances as already introduced; new worlds require introductions.
NPC introduction memories use the existing bounded 40-entry history.

## APIs / content / RNG / performance

New helpers: settlement_access.prepare_access_repairs/apply_access_delta;
container_profiles immutable validated catalog; interior_storage.bind_storage;
InteriorSystem.container_for_furniture/container_in_reach; IntroduceNPCCommand.
Simulation.introduced_npc_ids is the live-recognition query; known_npc_ids retains
testimony/ledger knowledge without revealing an unmet live actor's identity.
Presentation fence_view consumes only prepared neighbor pieces; shadows and
furniture sprite-fit caches remain bounded (96/128 entries).

Storage has at most three containers per building and <=five stacks per seed;
actual reserve amounts are constrained by existing stocks. Container IDs derive
from stable building+slot identities. RNG: existing property-storage-stock and
new container-profile-lock. Intro commands add no RNG. Access repair searches
are bounded to local 32/48-cell neighborhoods, not regional/infinite realization.

## Verification / handoff

Compileall passed. Final publication regression:78tests,36.007s; storage UI,
natural storage and workshop integration:29tests,3.161s; presentation suite:
30tests,5.236s. Final storage migration integration:59tests,16.1s; focused
storage suite:10tests,2.7s. Final access matrix:6tests,32.630s. The v12 audit covers
five resource economies x five settlement ranks with south facade/gate-pair
reachability; selected route preservation and legacy v10 fingerprint tests pass.
Representative storage and introduction SQLite round trips and verify_save
passed. Content audit passed (154 items, 82 recipes, 35 structures, 10 crops,
34 resources, 27 species); image-asset validation passed. A read-only SQLite backup
of the reported New_World_180a.db town settlement:1:1 passed the access audit:
21 entrance/gate positions corrected, no missing/disconnected/blocked approaches,
all enclosed portals southern, no footprint insets, base cache unchanged. Road
cells decreased from 781 to 683 including the new real service paths. The copied
save passed the verify_save CLI; the original save was never modified.
Final façade/side-door rendering and pointer batch: 28 tests, 4.282s.
Earlier test selection errors named three absent modules; the corrected batches
above are green (no weakened tests). A transient tuple-iterator exception did not
recur in fresh planner processes; the legacy matrix explicitly verifies the
two safe side-portal exceptions rather than forcing illegal footprint changes.

Validation is targeted development/headless visual evidence, not a full release
suite or supervised interactive playtest. Original saves/logs and old authored
art remain recoverable. Automatic fast-gate includes this regression group.

Next dependency: interactive playtest of frontages, private storage theft and
NPC introduction flow with new and resumed worlds. No unrelated feature work
or manual long-soak/full-release gate was started.
