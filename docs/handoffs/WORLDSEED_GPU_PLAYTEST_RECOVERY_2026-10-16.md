# GPU main-game playtest recovery — 2026-10-16

Baseline: canonical `main` at `00f99f0`, freshly checked and preflight verified.
This unit addresses the user's Windows playtest, not the old preview arena.

## Confirmed failure and indoor repairs

The supplied debug log confirms `TypeError: '<' not supported between instances
of 'str' and 'int'` in `prepare_interior_frame`. Remembered walls and visible flat
fixtures/stairs used incompatible sort tie-breakers. All keys now use a stable
string tie-breaker, with an explicit remembered-wall depth. A regression renders
the failing combination.

Indoor sight uses world-aligned patches with 125-unit boundary refinement,
retaining exact wall occlusion. Floors, observed walls, stairs and furniture stay
dimly remembered after leaving sight. Hidden actors, piles, inventories and
unvisited rooms remain excluded; remembered fixtures are non-interactive.
Half-pixel floor/light raster cracks and overlapping wall alpha bands are fixed.
Excessive presentation darkness is reduced without granting new gameplay sight.
Transparent GPU hover backdrops now erase previous outlines correctly.

## Exterior memory and readability

Gameplay discovery writes last-seen terrain, tree/harvest stage, public shell,
observed door and static prop appearances. Capture reads sparse 32-cell buckets;
it never refreshes memory from hidden live buildings, harvests or objects.
Shared shell revisions are reference counted/pruned. There is one appearance
record per explored cell, up to twelve props per cell; viewport limits remain.
No actors, inventories, locks or live light sources enter static memory.

Older saves default to empty appearance memory and learn objects on observation.
Their explored terrain can still read immutable generated BASE cache rows under
the exact saved projection contract, avoiding hidden current deltas. This cache
is bounded to 128 positive chunks per world and never generates missing terrain.

Remembered commands explicitly preserve classification alpha while RGB blends
at .62 opacity. Stacking memory props cannot admit current weather or lights;
unknown RGB remains black. Player-centred canopy clearance now covers the body
at .08 local alpha, with trunks retained. Ground objects use category/definition
scales instead of the old uniform 1.35-by-1.9-cell override.

## Physical movement and collection

ResourceSystem owns swept circular tree-base collision, radius .16 cells plus
the actor's .14-cell foot radius, at the existing art anchor (.5,.95). Continuous
movement can use the open part of a tree cell. Terrain, buildings, property and
non-tree solids retain their authority. NPCs share the collision queries and a
bounded deterministic escape around legacy same-cell trunks; no new planner or
saved steering state was added. Resource IDs and harvest stages remain stable.

Explicit `instant_pickup` resource tags make loose items and forage immediate.
Successful peaceful pickup/gather and repeated depleted-patch clicks do not run
a progress timer or zero-minute AI/vitals/wound ticks. Depletion, item metadata,
discovery and inventory transfer still run normally. Combat collection costs
one exchange; felling, mining and digging retain work time.

## HUD and diagnostics

The GPU sidebar restores health, stamina, food and water reserve bars alongside
numbers. Sixteen illustrated control assets replace line-only controls; stance
icons retain the shared commands. `?` or the Help button opens a compact movable,
scrollable controls window. Escape closes it. Opening/dragging cannot advance
time or dispatch movement; focus-return restores only the focus pause hold.
Controls come from the existing router and use NavigationStack.

Use `OPEN_LOGS.bat` in the replacement package. Normal frozen-game data lives at
`%LOCALAPPDATA%\WORLDSEED`; full gameplay tracebacks are retained in both
`WORLDSEED_CRASH.log` and `logs\WORLDSEED_CRASH.log`. Timestamped JSONL debug logs
are in `logs`. Startup/uncaught failures additionally use
`logs\gpu-session.error.log`. Existing menu recovery remains intact.

## Compatibility and validation

Save schema and world generation versions do not change. Optional exterior
memory and indoor `explored_detail`, `observed_objects`, `observed_walls` fields
have legacy defaults, bounded validation and representative SQLite round trips.
Save verifier checks passed. No RNG namespace, legacy renderer or generated
geography is replaced. Rendering remains observational.

- Combined affected GPU/gameplay suite: **142 tests passed in 27.1 seconds**.
- Final interior/memory/main-window checks after the last raster/fallback fixes:
  **35 tests passed in 14.1 seconds**, overlapping the combined suite.
- Interior-focused suite/raster checks: 64 unique tests; physics/pickup: 28;
  existing NPC/realtime/profession/conservation compatibility: 58. These overlap
  integration checks and are not a cumulative unique total.
- Content audit, compileall and whitespace checks passed. Two-seed early-game
  balance audit passed in 99.3 seconds with zero weak starts.
- Bootstrap audit was attempted and still fails on its existing literal
  `tag:binding_material` helper issue, previously reproduced on v8. Full bootstrap
  and the full release suite are not claimed green. An overly broad legacy UI
  selection was stopped during repeated world startup; affected GPU navigation
  classes and actual main-window interactions passed instead.

Reviewed actual main-game software captures:
[HUD/controls](../evidence/gpu-playtest-recovery/hud-controls.png),
[interior memory](../evidence/gpu-playtest-recovery/interior.png),
[interior capture details](../evidence/gpu-playtest-recovery/interior.json).
The interior includes production stairs, eight remembered fixtures and eight
remembered walls; authority fingerprint stayed unchanged. SDL offscreen/Mesa
llvmpipe supplied these pixels. Draw counts/CPU timings are not GPU performance
approval. The user's earlier Windows screenshots establish a real playtest of
the prior build; this replacement still needs native Windows acceptance.

## Remaining gates

True directional shadows, roof/canopy rain interception, broader light
occlusion, device recovery and hardware/performance/soak acceptance remain open.
Remembered tree seasonal palette currently follows display season, while its
identity and harvest stage remain last seen. This is a tested development
candidate, not release hardening or production readiness.

GitHub CI and replacement package outcomes are recorded after publication.
