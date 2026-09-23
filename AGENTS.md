# WORLDSEED v1.0 RC14 — coding-agent contract

This file is binding guidance for Codex and other coding agents working in this repository.


## UI / UX contract (RC6)

- New player verbs go through the Enter Action Hub unless a direct shortcut is demonstrably necessary.
- New information/management screens go through the TAB World Console hierarchy.
- `ui/router.py` is the only global key table. Never bind W/A/S/D to anything except movement.
- Use `ui/widgets.py` for menus, panels and paging; do not create bespoke number-only menus.
- Use `ui/layout.py` for viewport geometry. Never force a minimum screen larger than the real terminal.
- Every gameplay frame must fit within reported terminal width/height without relying on shell wrapping.
- UI/report code is observational. Opening a screen cannot realize regions, advance time or mutate simulation state.
- Long records must be pageable/reflowable. Do not truncate historical depth merely to fit one terminal screen.
- Update `tests/test_ui_rc2.py` when modifying HUD geometry, global key routing or primary navigation.

## RC14 Embodied World physicalization contract

RC14 introduces a binding spatial authority chain:

```text
SIMULATION / LEDGER -> REGIONAL PHYSICAL PLAN -> LOCAL MATERIALIZATION
```

Never create an unrelated decorative village, road, river, building list, or local economy beside authoritative simulation state.

- Simulation/ledger owns population, stocks, occupations, prices, health, faction state and events.
- Regional physical plans own stable roads, parcels, structure IDs, land use, crossings, capacities and ownership links.
- Local materialization owns exact nearby footprints, doors, containers and actor positions/tasks as a projection of those stable plan IDs.
- `SettlementState.buildings` may only remain as a compatibility/derived summary while RC14 migration is underway; it must not become a second building authority.
- Destroying a materialized structure/bridge must update authoritative plan state/deltas so distant simulation notices.
- Distant history damage must alter the same plan object so the next materialization shows the consequence.
- Never re-roll settlement layout merely because the player approaches.

### RC14 generation/version boundaries

- `HYDROLOGY_VERSION`, `SETTLEMENT_PLAN_VERSION`, and `ROUTEGEN_VERSION` are independent contracts.
- New saves use `HYDROLOGY_VERSION = 2`. Existing saves must instantiate hydrology from their stored `hydrology_version`; missing metadata is legacy v1. Never let a global version bump silently regenerate an existing river network.
- New saves use `HYDROLOGY_MORPHOLOGY_VERSION = 2`. Missing morphology metadata means Dev29 morphology v1. Any future change to river projection geometry must preserve or bump this contract instead of changing unexplored terrain in existing saves.
- V5+ surface chunk caches must be keyed by every active physical projection contract. For Dev35 this is worldgen + hydrology + hydrology morphology + coast morphology; underground and pre-hydrology caches may remain worldgen-only.
- Hydrology v2 consumes authoritative v8 precipitation/runoff. Do not create a second rainfall/noise authority inside drainage code.
- Phase-5 coast morphology consumes v8 geology/topography, physical climate and prepared hydrology. Do not create an unrelated coastline noise authority, and do not let atlas/renderer inspection generate missing coast or drainage plans.
- Phase-5 coast materialization is independently pinned by `COAST_MORPHOLOGY_VERSION`. Missing coast metadata means coast version 0 (pre-materialization shoreline). Never silently upgrade an existing v8 save to the newest coastline projection.
- New saves pin coast morphology v2. Existing v0/v1 saves remain unchanged. Mouths/distributaries/depositional barriers derive from prepared drainage edges; build their bounded indexes during startup/materialization, never from render or hover. Geological sample caches must preserve exact outputs and remain bounded.
- V2 ford/braid/gorge/delta/oxbow signals must derive from physical channel context; deterministic hashing may break ties only after physical suitability gates.
- New worlds use `WORLDGEN_VERSION = 8`; v8 replaces new-world elevation with the geological landform/topography system and uses v8-specific cave-mouth siting while retaining the existing prepared hydrology/coast projection until later v8 phases. Existing v1-v7 geography remains frozen by each save's recorded `worldgen_version`.
- V8 climate is physical and authoritative for v8 worlds: climate belts, maritime influence, continentality, prevailing wind, orographic lift and rain shadow feed temperature/precipitation. Do not reintroduce an unrelated moisture/temperature noise sheet for v8.
- Weather/time presentation is observational. Cloud shadows, wet-ground shading, rain/splash animation, fog and day/night grading may read simulation weather/time but must never mutate weather, clock, discovery, terrain or lighting authority.
- Wall-clock animation is allowed only for visual phase (for example rain streak movement). The sampled weather state remains fixed until simulation game time changes.
- Current sight must remain separate from persistent discovery memory. Weather/night may shrink current circular visibility; explored terrain may remain dimly remembered, but hidden entities/resources may not leak through memory.
- Atlas/map inspection is read-only and cell-exact. Never promote one discovered tile into a whole region, never generate missing terrain from atlas hover/drag, and keep atlas reads bounded by view/discovery indexes.
- Presentation performance must not scale with total realized world population. Query local spatial buckets instead of scanning all NPCs/creatures/structures each frame.
- Routine autosaves must not copy the full generated-world SQLite database. Reserve rotating full backups for explicit save/menu/quit checkpoints.
- Ground-terrain meshing is data-driven from terrain tags. New/modded `surface` or `underground` ground terrain must enter the presentation mesher automatically unless it is a hard feature (`shaft`, `ore`, `loot`). Do not add pair-by-pair renderer exceptions for ordinary biome ecotones.
- Cave mouths are contextual terrain overlays: placement belongs to world generation; presentation may choose neighboring ground only as a visual base and must never alter terrain authority.
- Recipe discovery is authoritative simulation state. UI browsing is observational; item/material discovery and trial-and-error unlocks happen on command/simulation paths, never because a crafting panel was opened.
- Adjacent prepared hydrology domains must be solved through the seam-safe multi-domain window contract; never return to independent per-chunk/per-domain river authority.
- Existing v4 saves must never be rewritten into v5 geography by normal loading.
- Generated hydrology/plan/route rows are rebuildable caches. Player/history mutations belong in authoritative state or `physical_plan_deltas` and must survive cache deletion.
- Stable plan IDs derive from stable parent identity + deterministic slot/geometry fingerprint, never transient iteration order or process hashing.
- No movement, hover, renderer, or inspection path may perform hydrology, settlement planning, or route generation. Preparation belongs in startup/background planning phases.

### RC14 release gates

New physical-world work must add deterministic tests and the relevant audits. At minimum preserve:

- same seed + same versions -> identical hydrology/plan/route fingerprints;
- generated-cache reload skips raw generation;
- generated-cache deletion/rebuild reproduces base data without erasing authoritative deltas;
- hydrology has no unintentional prepared-core sinks/cycles and downstream accumulation does not decrease;
- settlement plans have legal footprints/access/capacity and no duplicate economic authority;
- strategic route graphs remain sparse and crossings reference real hydrology;
- legacy saves retain recorded geography;
- ordinary movement/render latency does not invoke regional planning.



## Canonical GitHub repository and cross-chat synchronization rule

The canonical WORLDSEED repository is:

`https://github.com/ReleMai/WORLDSEED`

Repository full name: `ReleMai/WORLDSEED`  
Canonical branch: `main`

This rule applies to every WORLDSEED development chat, Codex session, coding agent, and handoff.

1. **GitHub `main` is the default source of truth.** At the start of a WORLDSEED coding task, read/fetch the latest repository state before editing. Do not assume an older chat attachment or local archive is newer.
2. **A user-supplied newer build may supersede the repository only when the user explicitly asks to work from it.** In that case, reconcile/import that build into the repository before allowing the project to diverge into a separate long-lived branch of history.
3. **Every validated WORLDSEED change must be synchronized back to GitHub in the same work session.** This includes code, game data, authored assets, tests, migration files, documentation, changelogs, and agent handoff notes that are part of the completed change.
4. **Do not wait for a separate “push it” request.** Repository synchronization is part of the Definition of Done for any task that changes project files.
5. **Never push a knowingly broken or unvalidated intermediate state to `main`.** Run the relevant targeted tests/audits first. If a task is incomplete, keep the incomplete work out of `main` or clearly isolate it on an explicit work branch when branch tooling is available.
6. **Do not overwrite newer remote work.** Re-read the remote branch/ref before final synchronization when another chat/agent could have changed it. Reconcile conflicts deliberately; never force-update `main` simply to make a push succeed.
7. **Commits must be descriptive.** Use concise messages that identify the subsystem and completed result, for example: `Fix crafting crash and pointer input regression` or `Rebuild atlas terrain projection for Dev23`.
8. **Substantive commits must leave a handoff trail.** Update the relevant changelog/release/handoff notes so the next WORLDSEED chat can determine what changed, what was validated, and what remains.
9. **If GitHub synchronization cannot be completed because the connector, permissions, or service is unavailable, say so explicitly in the final response.** Never claim the repository is current unless the write actually succeeded. Preserve a clean patch/archive so the change can be synchronized later.
10. **Do not create a second canonical WORLDSEED repository.** Forks, temporary branches, archives, and generated ZIPs are secondary working artifacts unless the user explicitly changes this rule.

### GitHub / CI efficiency contract

GitHub Actions is a verification boundary, not an edit-by-edit development loop.

- **One coherent publication per work unit.** Do not push file-by-file or bookkeeping-by-bookkeeping commits to `main`. Stage the code, tests, docs, version metadata and handoff for one validated work unit, then publish them together.
- **Batch connector writes.** When a GitHub connector can create one tree/commit containing several changed files, prefer that over repeated contents-API commits that each trigger CI.
- **Use work branches for iteration.** Intermediate experiments may live on an explicit work branch, but do not attach temporary push-triggered full-build workflows to that branch. Run targeted validation before publishing the coherent result.
- **Automatic CI is deliberately fast.** `.github/workflows/fast-gate.yml` is the normal automatic gate for `main` and pull requests. Keep it high-signal and bounded to roughly a few minutes.
- **Full validation is deliberate.** `.github/workflows/test-build.yml` is a manual release/handoff gate. Run it once when a substantial phase/build is ready for comprehensive regression validation and packaging, not after every intermediate commit.
- **Do not weaken tests to make CI green.** When the fast gate fails, inspect the failing assertion/root cause first. Update a test only when the intended contract actually changed.
- **Avoid duplicate ref updates.** Re-read the remote ref before the final write. If the intended commit is already the branch head, do not push or move the same ref again.
- **Open a PR only when the branch is coherent enough to test.** Once a PR is open, further pushes may legitimately retrigger the fast gate; avoid noisy micro-commits while the PR is active.
- **Release hardening still requires the heavy gate.** A green fast gate means the change passed development smoke/regression checks; it does not replace the full RC14 release-hardening suite.

For WORLDSEED work performed through ChatGPT, completion therefore means:

```text
fetch latest WORLDSEED main
-> implement requested change
-> validate relevant behavior
-> update handoff/changelog when substantive
-> commit/synchronize to ReleMai/WORLDSEED
-> report the commit/result to the user
```

## Product rule

> **Model causes, not scripted outcomes.**

A feature is mature only when it participates in existing state transitions.

Bad:

```text
if day == 40: spawn famine quest
```

Good:

```text
crop yield ↓
food stock ↓
price ↑
hunger ↑
labor efficiency ↓
crime/migration pressure ↑
```

The player may experience that as a famine story, but the engine should not have needed a "famine quest" to create it.

## Architectural invariants

1. Authoritative simulation state lives outside UI/rendering.
2. Rendering, dashboards, alerts and ledgers are observational.
3. No global `random` in procedural/simulation code.
4. Every random domain uses a stable named deterministic namespace.
5. Unvisited Tier-E space remains deterministic potential.
6. Do not make a new feature realize the infinite world merely by iterating coordinates.
7. Ordinary distant populations are aggregates; preserve individuals only when named/notable/relevant.
8. Promotion/demotion must conserve authoritative quantities.
9. Save growth should follow realized/mutated state, not total theoretically generated world size.
10. Never silently change save schema or worldgen version.
11. Never use `pickle` for saves or mods.
12. New data IDs are namespaced (`core:`, mod namespace, etc.).
13. Avoid god modules and cross-domain direct mutation.
14. UI complexity should expose causality, not hide it.
15. New long-lived collections need a compaction/pruning/bounded-history policy.

## System ownership examples

- AI chooses/request actions; combat owns wound resolution.
- Economy owns stocks/prices/production; factions do not directly invent goods.
- Epidemiology owns human infections; weather can influence disease pressure but does not mutate cases itself.
- History records consequences; it does not cause the battle/discovery merely because an event is desired.
- Renderer does not call realization methods.

## Time ordering

Simulation ordering is part of determinism. Do not reorder mature cadence blocks casually.

Typical order:

```text
command validation
command effect
clock advance
scheduled/hourly systems as crossed
scheduled arrivals
daily aggregate systems
monthly systems
local post-action consequences
history/maintenance
checkpoint when due
renderer reads snapshot/state
```

Offline advancement must process meaningful boundaries and dynamically created arrivals. Never loop one minute at a time for a month-long catch-up.

## LOD rules

- A: immediate exact simulation.
- B: nearby persistent individuals at reduced cadence.
- C: regional cohorts/ledgers.
- D: distant realized aggregate events.
- E: deterministic potential only.

Before adding a persistent distant object, ask: **does this need to exist individually while unobserved?** If no, store an aggregate or deterministic potential instead.

## Data/content rules

Prefer JSON definitions for:

- materials;
- items;
- recipes/processes;
- structures;
- crops;
- species templates;
- diseases;
- future compatible content.

Code should implement rules/algorithms, not giant content switch statements.

Data validation must reject malformed IDs, negative physical values, invalid references and protected-ID collisions.

## Persistence rules

Current save schema: 3.

For any persistent-state change:

- ensure old missing fields have safe defaults;
- update `to_dict/from_dict` as needed;
- add round-trip tests;
- decide whether schema migration is required;
- update verifier invariants;
- do not change `WORLDGEN_VERSION` unless base generated geography intentionally changes.

If changing worldgen, create an explicit generation-version strategy. Never let an update invisibly move a mountain under an existing settlement.

## Performance rules

Prefer fixing complexity, not only micro-optimizing loops.

Prohibited patterns without justification:

```text
for every entity in world: ...
for every settlement × every settlement: persistent complete graph
advance every offline minute
instantiate daughter civilizations into unrealized infinity
retain every transient event forever
```

Preferred:

```text
spatial indexes
bounded partner sets
scheduled boundaries
cohorts
sparse deltas
history archives
pruned completed logistics
bounded time-series histories
```

Use `tools/soak_matrix.py`, `tools/profile_state.py` and profiling before introducing native dependencies.

## UI rules

Complexity is allowed; unusable complexity is not.

When adding a persistent system, normally add at least one of:

- main-view symbol/status;
- alert condition;
- World Console summary;
- World Ledger drill-down;
- interactive look/context action;
- explanatory causal text.

Large screens must be pageable. Do not assume a 200-line terminal.

Add observational tests for new dashboards where feasible:

```python
before = sim.state.to_dict()
text = screen(sim)
after = sim.state.to_dict()
assert before == after
```

## Input rules

`W`, `A`, `S`, `D` are reserved movement controls.

Do not reuse them as global menu hotkeys. `D` was previously shadowed by dismantle and has a regression test; dismantle is `U`.

Prefer the World Console/context menus over consuming every remaining keyboard letter.

## Testing contract

### CI failure-diagnostics contract

Every new or modified automated test must make the failing case identifiable from the CI log without reproducing it locally.

- Collection/table/variant tests must use `self.subTest(...)` (or an equivalent case label) with stable identifiers such as `content_id`, asset path, seed, coordinates, row/column, command, or fixture name.
- Assertion messages must name the object/case being checked when the raw assertion would otherwise be ambiguous.
- Asset/image tests must report the exact repository path and all relevant content IDs. Force full image decode during validation; opening only the image header is insufficient.
- Do not hide case identity inside an aggregate comprehension when a per-case failure can be reported instead.
- CI unittest invocations use verbose mode (`python -m unittest -v ...`) so test IDs are visible in Actions logs.
- Audit tools should collect and print every failing path/ID they can safely inspect in one pass, rather than stopping at the first opaque error.
- Never weaken a test merely to improve diagnostics. Preserve the contract being tested and add context around the failure.

Minimum branch gate:

```bash
python -m compileall worldseed
python -m unittest discover -s tests -v
python tools/replay.py tests/fixtures/golden_replay.json
```

Persistence change:

```bash
python tools/verify_save.py <representative-save>
```

Simulation/aggregate change:

```bash
python tools/soak_matrix.py --years 25 --seeds 4 --policy full --json
```

Performance/LOD change should also run a century-scale seed during development/nightly validation.

## Required new tests by change type

Procedural generation:
- same inputs identical;
- generation order independent;
- unrelated RNG namespace isolation where relevant.

Persistent state:
- round-trip;
- migration if schema changed;
- verifier invariants.

Economy/ecology/disease:
- conservation/bounds;
- no negative populations/stocks;
- long soak.

UI:
- observational/read-only;
- narrow/large record paging behavior where relevant.

## Definition of Done

A feature is not done because one button works.

It should have:

- a clear state owner;
- deterministic behavior;
- persistence policy;
- LOD policy if spatial/population based;
- interaction with existing systems;
- discoverable UI/read model;
- tests;
- bounded growth strategy for long worlds;
- updated documentation when public behavior changes.

## Agent handoff note

Every substantial agent task should leave a short handoff containing:

```text
Scope / modules changed
Public APIs/contracts
Persistent fields / migration
RNG namespaces
Tests added/changed
Performance implications
UI exposure
Known limitations
Next dependency
```

## Navigation invariant

All nested UI routes must use `NavigationStack`. ESC must pop one route, preserve the parent's selected row/scroll, and never mutate simulation state. Add a simulated-key regression test for every new multi-layer UI.

## RC6 gameplay/discovery invariants

- Simulation state is not player knowledge. New screens must filter NPC/town/faction/site/event names through discovery state.
- Surface biome terrain and harvestable features are separate. Do not reintroduce `tree == terrain`.
- Harvesting vegetation must not rewrite the underlying biome.
- Solid underground terrain must be interactable from adjacent cardinal cells; never require the actor to occupy an impassable wall.
- Worldgen v2 is a compatibility boundary. New cave topology belongs to v3+ only. Never silently migrate an old world's generator version.
- Natural connector shafts/landing chambers are protected topology and site overlays may not sever them.
- Player-authored structures/farms/containers suppress deterministic wild features on the same tile.
- Mouse reports and paste payloads are UI tokens, never gameplay commands.

## RC7 early-game invariants

1. New characters start with an empty inventory. Never add a starter kit without changing the product design explicitly.
2. Primitive progression must be reachable from generated natural resources; avoid circular recipe dependencies.
3. Processes ask for tool qualities where possible, not a single hard-coded tool ID.
4. An item needs direct utility or a downstream sink. Run `python tools/audit_content.py` after content changes.
5. Furniture must implement a gameplay use before it is added to the core set.
6. Animal kills create carcasses; do not bypass the processing loop with direct generic loot unless the species intentionally disintegrates/has a special rule.
7. Cooking nutrition derives from ingredients. Do not duplicate every ingredient combination into fixed recipes.
8. Crops own their N/P/K/disease/climate data; do not hard-code crop IDs in growth logic.
9. New forage/species content must have habitat constraints and deterministic generation.
10. Release changes to primitive resources must run `bootstrap_smoke.py` and `balance_early_game.py` across multiple seeds.

## Visual/presentation contract (RC8+)
- Never import pygame from simulation, worldgen, persistence, ecology, economy or content rules.
- Reference visuals by stable content/visual ID, not hard-coded absolute paths.
- Every new item/terrain/resource/structure/crop/authored species must receive visual coverage or intentionally defined fallback before merge.
- Rendering, resizing, hovering and animation are observational and may not advance simulation/RNG.
- Preserve `--terminal` as a regression/debug backend until the graphical renderer has equivalent accessibility and tooling.

## Dev21 pointer/input contract
- WASD is world movement only; do not restore W/S selection or A/D back/confirm mappings.
- Pointer hit regions are presentation-only and rebuilt each frame. Never dispatch simulation commands from hit tests or hover.
- Shared widgets interpret UI_SELECT/UI_HOVER page-relative tokens and retain route state.
- Menu paging must use backend capacity so every row is visible and clickable.
- Mouse wheel pages UI; only world mode changes camera zoom. Text input accepts ordinary letters.
- Entering modal UI and focus loss clear held movement; window close unwinds to the save/exit boundary.

## Dev22 atlas contract
- Graphical maps consume world.atlas snapshots, never illustrative regional art as geographic truth.
- Atlas reads may not generate/load world chunks, plan hydrology/routes, realize sites, or write state/database.
- Missing base cache is unknown. Never approximate it using a dominant biome or silently reroll old geography.
- Known POIs derive from discovery-filtered records or observed terrain/structures; artwork creates no simulation objects.
- Base generated chunk retention happens during normal materialization, before deltas, not on atlas inspection.
