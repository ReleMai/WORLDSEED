# Dev55 - moving residents, material equipment and action-driven combat

## Scope and causes

Three independent defects made residents appear stationary. Goal hysteresis
compared a historical peak score after the underlying need was satisfied.
Breadth-first local pathfinding exhausted its node budget on ordinary straight
trips and rejected diagonal waypoints outside a Manhattan bound. Fresh named
workers also lacked today's labor assignment until the first daily economy pass.

Utility hysteresis now compares current needs. Deterministic bounded A* reaches
ordinary village destinations, retaining terrain, shell, door and actor-lock
checks. Active residents complete domestic/social tasks against absolute-minute
deadlines instead of waiting for an arbitrary next hourly call. Generic work,
food purchases, healing, learning and theft still require at least 60 minutes per
completion; faster locomotion does not multiply economic output. An unavailable
exact job approaches its real workplace and waits/retries rather than producing
invented goods. Positions/facing remain in the existing NPC state/spatial index.

Combat previously called wildlife AI/attacks from idle real-time heartbeats.
Peaceful heartbeats now inspect each minute separately and stop on hostile intent
before resolving an enemy strike. Combat stays paused while choosing an action.
A physical action advances one game minute and one enemy-response pass. Waiting
spends one tick; long work/rest rejects before applying effects. Inspection,
dialogue and menus are free. Leaving combat discards wall-clock backlog.
Graphical held movement cannot repeat combat actions: release and press again.
Terminal/graphical HUDs identify the pause. Outdoor wildlife combat remains the
existing combat authority; attack damage has not been rebalanced.

## Modules and public contracts

- `ai.py`: fixed utility hysteresis, timed local routines, job preparation and
  once-per-active-town hourly equipment retry.
- `pathfinding.local_path(..., goal_radius=0)`: deterministic cardinal A*, at most
  the supplied node budget and forty cells from the start on each axis. Optional
  radius one supports ordinary adjacent arrival; exact portals stay exact.
- `economy.ensure_work_assignments(town, minute)`: prepares today's existing labor
  reservations without production or resetting same-day completed work hours.
- `npc_equipment.NPCEquipmentSystem`: provisions existing supplies, reconciles
  carried gear, and retries shortages. Settlement activation owns provisioning.
- `physical_goods.issue_equipment`: debits town stock or an authorized property
  store exactly once. Ordinary cargo deposits preserve equipped units.
- `Simulation.combat_active()`: observational query over simulation-prepared local
  creature IDs, using the same 42-by-32 extent as local hunting AI.
- `Simulation.advance_realtime(minutes) -> int`: returns actual minutes advanced,
  stopping at combat. `RealtimeSimulationDriver` discards suspended backlog.
- NPC profile adds current task/position and a pageable Cash / Gear / Pack route
  using NavigationStack. Appearance reads equipped items rather than assuming
  all clothing in a pack is worn. Unknown people retain identity/privacy gating.

## Persistent state, economy and versions

`NPCState.equipment` is an additive slot-to-item map referencing reserved units
already in `NPCState.inventory`. Missing legacy fields default to `{}`. Carried
cash remains `NPCState.wealth`; no second wallet or stock ledger was added.
Task dictionaries may store `started_minute`/`complete_minute`; legacy tasks
initialize their deadlines when next executed. Save validation checks gear slots,
items and sufficient carried units. Schema remains 3; no migration or geography,
hydrology, settlement-plan, route or RNG-version change is required.

Newly created settlements include modest existing-item clothing/tool capital for
named adults. Issuance removes that capital from stock. Existing saves receive
only their real available supply. There is one bounded cumulative equipment
issuance record per NPC, not an event per attempt. Existing professions retain
physical extraction, station reservations, cargo/storage transfers and aggregate
labor reconciliation. No new items/assets or RNG namespaces were introduced.

## Validation

- 160 combined NPC, gear, activities, mining, farming/workshops, households,
  workplace logistics, interior AI, combat/hunting and realtime tests passed.
- 15 generated-building-access, physical-property/profile and dialogue tests
  passed, including all 25 synthetic settlement layouts and shared NPC paths.
- 29 graphical input/floating-panel tests passed, including fresh combat key
  presses, normal movement repeat and retained stacked panels.
- 7 focused HUD/profile checks passed, including narrow observational combat
  display, normal terminal geometry and belongings paging/ESC restoration.
  These batches overlap by four profile tests.
- The broad UI module first hit its 180-second budget in repeated generated-world
  fixture setup. The affected HUD checks above were then run explicitly within
  90 seconds; the full UI module is not reported as passing.
- A one-seed, one-year FULL smoke soak passed with no invariant errors (WORLDSEED
  year = 120 simulated days). Gear tests write a representative SQLite save and
  execute `tools/verify_save.py`, reporting `Save integrity: OK`.
- Compileall and Git whitespace checks passed. New regression modules are in the
  automatic fast gate; publication/CI status is reported separately.

This is targeted development/integration evidence, not a live manual village
playtest or a full release-hardening run.

## Performance, limitations and next dependency

Path searches, local waypoints, carried inventories, gear slots and issuance
records remain bounded. Large/offline waits retain coarse processing. Renderer
and profile reads do not plan terrain, execute jobs, issue supplies or advance
time. Combat HUD queries reuse local IDs rather than scan all world inhabitants.

Equipment issuance is simulation-owned allocation during activation/hourly
preparation, not an animated fetch trip. Missing resources/workstations/supplies
still constrain physical jobs. Distant populations retain aggregate LOD, and
direct NPC combat remains outside current wildlife combat authority. The next
useful slice is live playtesting several existing-save villages and extending
shared physical profession/logistics coverage based on observed shortages.

The original dirty `D:\Codex Project\wsLIVING` checkout was preserved. This work
uses the attached clean `living-village-combat` checkout from freshly verified
GitHub main. The local Dev55 launcher runs that source with the original working
directory so the existing `saves/` list remains available.
