# Early access cabin construction and access safety — 2026-10-13

Started from freshly fetched canonical main `f17ca21f488d89199d0fe02ece9c9e5ea18fdce5`, with a clean complete checkout and dependency preflight. Implements the second P0 work unit in `EARLY_ACCESS_PYGAME_PLAN.md`, after save retry preservation.

## Scope and authority

- `HomesteadBlueprintService.construction_safety(site, next_stage)` validates the proposed solid footprint before changing stage or revision. Living outdoor players, NPCs and creatures cannot be buried by Frame construction; dead actors and authoritative indoor presence do not occupy saved exterior anchors.
- The exact rotated landing must be prepared, clear and connected to surrounding ground. Nearby actors, including diagonal corners, must retain a bounded escape through the two-cell apron. Terrain, natural resources, structures, fluids and actor-specific property locks remain the collision authority. The check never realizes regions or plans geography.
- Resource collision can read cardinal neighbors, so placement, construction, recovery and cabin exit guard the terrain halo before querying resources. A missing prepared neighbor fails safely rather than generating a chunk from preview or access checks.
- Rejected `AdvanceBlueprintCommand` returns before turn/time advancement, discovery reconciliation or post-action consequences. Stage, revision, deposits, carried inventory and vitals remain intact. Existing unfinished cancellation retains exact material/substitute refunds.
- Completed sites bind a stable `DoorSecurityState` with UID `<homestead uid>:entrance`. `ensure_access` runs on completion and load, preserves saved lock/tamper state, and creates no physical keys or goods. Read-only security queries no longer assign missing lock IDs.
- `structure_projection(site)` is an ephemeral adapter for existing interior geometry. The authoritative source remains `state.homesteads`; no second persistent building or settlement list is introduced.
- Explicit entry creates an existing `InteriorPlan` with stable building/door identity. Player and NPC entry use the exact rotated outside landing; ordinary exit uses that same landing and rejects obstruction. Saved geometry, fractional actor presence and contents remain persistent. The shell starts unfurnished, with no automatic beds, storage or provisions.
- Enter is exposed through Action Hub > Interact, the completed cabin panel and doorway context menu in both backends. WASD, Enter/TAB authority and NavigationStack behavior remain covered.
- On load, invalid legacy outdoor player positions inside framed/completed footprints recover through prepared legal apron cells. Prefer the exact doorway; if it is occupied or blocked, choose a stable nearby candidate with an escape route. This compatibility repair never changes ordinary entry/exit geometry or moves an actor during a rejected construction command.

## Public APIs and persistence

New access helpers live in `worldseed/systems/homestead_access.py`: `ensure_access(sim, site)` and `structure_projection(site)`. The blueprint service adds `completed(uid)`, `construction_safety(site, next_stage)` and `recovery_landing(site, origin)`; `door_uid(site)` derives stable identity.

No new persistent fields, database schema, generation versions or RNG namespaces. Existing optional `door_security`, `interiors` and `interior_actors` dictionaries already provide safe empty defaults. Old completed cabins gain a derived entrance on load; existing interior/lock state is preserved. Schema remains 3, with no migration required.

## Development validation

- Compileall for `worldseed`, `tools` and `tests`, plus whitespace checks, passed.
- Final bounded cabin run passed 73 tests in 5.767 seconds: safety/access/UI, original blueprint/ghost/panel/art regressions and the real interior command integration suite.
- Coverage includes all ten styles across all four rotations, every player footprint cell, NPC/creature/diagonal occupancy, blocked/flooded/locked/unprepared landings, rejection costs, refunds, no hidden terrain generation, and legacy load recovery that avoids isolated fallback cells.
- SQLite round trips preserve site, door lock/tamper state, interior and fractional presence; representative saves pass `tools/verify_save.py` with `Save integrity: OK`. Entry and exit conserve inventory and NPC cargo.
- Four primary-routing/HUD checks passed after extending the existing RC2 regression to cover Enter/TAB alongside WASD. The automatic fast gate now includes the new cabin modules in its existing bounded construction step.
- The separate affected interior/security/knocking/projection/activity and save-retry/UI run passed 59 tests in 5.143 seconds. Together with the cabin and primary-routing runs, 136 targeted tests passed.
- A broader integration invocation including all of `test_ui_rc2` reached its 180-second deadline during `UIRC2Tests.test_renderer_never_relies_on_terminal_wrapping`, with no assertion failure reported. Its `setUp` constructs a full procedural world for each test, including pure layout/menu assertions. The bounded runner terminated the process tree. This incomplete run is not a full-suite pass; the affected direct integration modules are validated separately.

This is development validation; comprehensive release hardening and live invited playtests remain separate.

## Cost, limitations and next dependency

The escape search is bounded to the footprint plus a two-cell apron. Actor collection still scans realized actors on the construction/load command path; this work makes no claim of constant population cost. No new scan runs from ordinary rendering. Legacy recovery requires a prepared legal local candidate; it does not search distant or unprepared regions.

The cabin entrance/interior is usable, while furnishings, storage, beds, shelter/recovery integration and the sustainable survival loop remain the later complete-home work unit. Next in the plan: runtime timing instrumentation and repeatable reference scenes, then active actor/static indexes and compact discovery persistence. Preserve the pinned geography and synchronous safe-save contracts during that work.
