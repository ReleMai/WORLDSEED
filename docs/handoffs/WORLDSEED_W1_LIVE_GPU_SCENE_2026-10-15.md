# WORLDSEED — W1 live GPU scene integration

**Date:** 2026-10-15. **Repository:** [ReleMai/WORLDSEED](https://github.com/ReleMai/WORLDSEED), canonical `main`.
**Scope:** bounded, read-only capture of prepared live gameplay state for the new OpenGL/ModernGL renderer.

**Follow-on:** the [W2 Action Hub/context handoff](WORLDSEED_W2_ACTION_HUB_CONTEXT_HANDOFF_2026-10-15.md) supersedes the original missing Enter/Tab UI and context-startup implementation notes below. W1's capture/privacy contracts remain intact; original evidence is retained as history.

## Delivered APIs

- `worldseed/presentation/live_gpu_scene.py` adds `capture_live_scene(sim, camera)` and frozen `LiveGpuSnapshot` / `LiveFire` records.
- `player_foot(sim)` reads the existing authoritative player cell and saved fractional offsets; NPC feet use their existing `fx` / `fy`, while creatures retain their cell-centered positions.
- `LiveGpuSnapshot.gpu_frame(...)` projects detached records through the existing world-space scene and GPU material bridge; it needs content/material services, not a simulation reference.
- `LiveGpuSnapshot.atmosphere(...)` passes captured minute, weather and admitted active fires to the existing GPU atmosphere pass. Wall-clock time controls animation phase only.
- `World.prepared_tile_at(pos)` returns a resident `TileView`, or `None`; it never loads/generates chunks or changes terrain-cache LRU order.
- `ResourceSystem.prepared_feature_at(pos, minute=None)` reads resident seasonal placement and authoritative live suppression/depletion; missing preparation returns `None`.
- `ResourceSystem._feature_view(...)` shares the existing stump, sapling, mature and depleted lifecycle projection with normal gameplay `feature_at`.
- `prepare_gpu_frame(..., actors=...)` accepts caller-authorized actors in addition to its single viewer. Actor materials reuse the existing visual catalog and bounded fallback assets.

## Authority and privacy contract

Capture runs on the simulation owner's thread after simulation updates. Rendering never advances time, discovers cells, repairs indexes, materializes terrain/resources, opens interiors, moves actors or writes the database.

The adapter iterates the bounded camera rectangle and checks `sim.visible_tiles_set` / `sim.discovered_tiles_set` by exact `pos_key` membership. It never copies or scans lifetime discovery history. Unknown cells cause no terrain/resource query.

Living exterior actors come from `NPCSystem.indexed_npcs_in_rect(...)` and `state.creatures.near_rect(...)`. Active fire candidates use `state.fires.near_rect(...)`. These are simulation-maintained indexes; there is no renderer fallback that scans the global population or rebuilds an index.

Current sight remains the simulation's decision, including its existing weather/night and physical LOS rules. Capture does not reinterpret discovery as current visibility or recompute stealth awareness. The current exterior actor model has no independent hidden-NPC flag; admission requires current sight, living state, exterior membership and privacy masks.

NPCs in `state.interior_actors` are excluded even though their exterior coordinates still identify a portal anchor. Player interior presence produces an empty exterior scene. Prepared shell cells, legacy room/roof cells and intact player-built roof cells are omitted conservatively until the dedicated interior/building renderer exists.

Tree visual parts retain the same cell/content-derived resource identity. Visual size, canopy fading, shadows and actor art add no collision or interaction authority. Existing movement, harvesting, doors and property access remain simulation-owned.

## Bounds and rendering changes

- Camera capture retains the 8,192-cell viewport limit.
- Resource capture retains the 1,024 prepared-resource limit.
- Additional actors remain below the 256-actor scene budget, reserving the viewer slot.
- Fire capture permits at most 32 active visible fires; atmosphere submits at most eight lights.
- Existing scene, command, clip, source-material and GPU texture budgets remain enforced. Exceeding a budget fails explicitly.
- Fire sprites now use the same projected per-cell visibility clips as other world sprites, including at nonzero elevation; source-cell visibility alone does not authorize their full artwork extent.
- Mature oak/pine retain separate seasonal canopy, trunk and authored contact-shadow layers.
- Stumps use compact existing stump art; saplings use the existing logging sapling asset. Both preserve harvest-stage identity and avoid mature canopy/shadow output.
- The atmosphere shader treats transparent scene-target pixels as unknown and outputs black before applying fog, precipitation or lighting. The live owner must clear its scene target to `(0, 0, 0, 0)`.

## Compatibility and deliberate omissions

There are **no persistent fields, migrations, save-schema changes, worldgen/resourcegen version changes or RNG namespaces** in W1. Existing legacy resource placement, saves, simulation optimizations and the Pygame launcher remain intact.

Resident-only reads deliberately omit a missing seasonal resource chunk, even if a generated copy exists on disk. Resource preparation/loading belongs to startup or simulation paths. The adapter does not derive shoreline reeds from an empty prepared cell; explicitly prepared reeds may be read, but renderer observation cannot create missing placement.

W1 captures bounded discovered-memory membership but draws only current ground. It does not show live resources or actors through remembered terrain. Roof/private cells and interiors remain blank rather than exposing their contents.

Stump and sapling art is shared between oak and pine until species-specific growth artwork is supplied. Other prepared natural-feature identities may be captured without receiving new GPU artwork in this unit.

Warm fire glow is confined to its admitted source cell. Wider illumination requires shared wall/roof occlusion; this visual glow does not alter stealth detection or physical light authority. Weather units are adapted from simulation rain `0..10` and v8 wind direction vectors into existing shader inputs.

Tree shadows remain **static authored contact shadows**, not dynamic sun/fire directional shadows. Sheltered precipitation, proper indoor lighting, building shells, roofs and complete gameplay UI remain later integration work.

## Validation evidence

Focused coverage includes:

- `tests.test_gpu_prepared_reads`: resident terrain/delta reads, unchanged cache order, no load/generation, missing season/terrain, authoritative suppression and shared depletion/regrowth stages.
- `tests.test_gpu_live_materials`: authorized actor materials, viewer/budget protection, distinct harvest-stage art, stable feature identity, fire extent visibility clips and content fallback paths.
- `tests.test_gpu_visibility_shader`: optional real OpenGL 3.3 EGL context, compiling the repository's sprite and atmosphere GLSL. A single authorized tile remains visible while every unknown pixel stays black under heavy fog/cloud, exclusive rain then snow, and a strong nearby light.
- `tests.test_live_gpu_scene`: nine controlled live captures, including production circular sight/tree LOS, full authority fingerprint, no SQL queries, unchanged cache order, detached actor/weather records, roofs/interiors and budgets.
- Existing world-space, prepared GPU bridge, tree-art and weather-pipeline regression suites remain relevant.

The prepared-read unit and reed regressions passed together: **12 tests**. The real shader regression passed locally on **EGL llvmpipe (LLVM 19.1.7, 256 bits)**. Missing ModernGL/EGL drivers skip that optional test; shader or rendering failure on an available context fails it.

EGL llvmpipe is software shader-correctness evidence. It establishes no native Windows GPU screenshot, hardware frame-time result, renderer speedup or production readiness.

An additional controlled 1280×720 EGL capture used production circular LOS for forest and camp, 12 frames each, with identical before/after authority fingerprints. Software-only synchronized capture/draw p50/p95/p99 were **32.80/38.67/38.67 ms** (forest: 152 current cells, 15 resources, 198 commands) and **27.00/39.70/39.70 ms** (camp: 191 current cells, 8 resources, 217 commands). The small sample includes source preparation and is a correctness smoke, not a benchmark or speedup comparison. PNGs were inspected: unknown cells remain black and tree/campfire anchors are present; art approval remains open.

Native SDL execution in the Linux cloud instance could not create a window with OpenGL support. The separately created EGL context is the only local graphics evidence. Native Windows workflow results must be recorded independently.

## Next dependency

W2's bounded foundation is implemented in `worldseed/ui/gpu_gameplay_input.py`, `tools/worldseed_gpu_gameplay.py` and `RUN_WORLDSEED_GPU_GAMEPLAY.bat`. One SDL window/event pump feeds `ui.router.classify_key`; held walking/sprinting uses existing `update_free_movement`, fresh combat steps use `MoveCommand`, and wait/pickup use their existing commands. `RealtimeSimulationDriver` remains the clock authority. Focus loss clears held input and discards wall-time backlog; mouse hover only projects the exact camera and shows current cells. Capture/draw cannot dispatch commands.

The default candidate boot uses normal `_load_context` startup into a **temporary new world**, with empty inventory and no player save opened. Startup can take time and is currently synchronous. `--prepared-scene forest|camp` uses the existing synthetic fixtures for bounded smoke capture; these override discovery/realization and are not natural-world exploration proof. The seven new input tests include real-engine trunk collision and production sight; the 40-test input/movement/combat/realtime/reed compatibility run passed.

```powershell
py -3 -m pip install -e ".[gpu]"
py -3 -m tools.worldseed_gpu_gameplay
py -3 -m tools.worldseed_gpu_gameplay --prepared-scene camp --frames 30 --screenshot scratch/gpu-live-camp.png --report scratch/gpu-live-camp.json
```

Controls: WASD/arrows move, Shift sprint, `.` wait, `P` pickup, F12 capture, Esc exit. Enter/Tab remain reserved for the Action Hub/World Console and do not yet open GPU UI. Candidate reports explicitly distinguish CPU frame/submission timings from GPU completion, include p50/p95/p99 and GL vendor/renderer/version, and label the source and missing acceptance gates. The manual native workflow now requests this controlled camp capture alongside the prior probes.

Local validation covered **127 unique tests**: 50 integration, 46 privacy/art/reference, 40 input/compatibility (12 overlap), plus three SDL/GL loop tests. The loop tests run real prepared gameplay/capture with fake graphics: one window and event pump, repeated-key suppression, release before update, update→capture→draw ordering, transparent clear, report output and cleanup on draw failure. Compileall and whitespace checks passed. Publication CI is recorded at closeout. W0 native driver/screenshots/performance acceptance, full W2 click interactions, W3 privacy/UI and W4 directional shadows/environment remain open. No default launcher promotion.

## Publication and native probe closeout

- Implementation: [`265ba115cb0837d6b51314ee37a057449f194032`](https://github.com/ReleMai/WORLDSEED/commit/265ba115cb0837d6b51314ee37a057449f194032), directly on canonical `main`; no extra branch.
- [Fast Gate #38754472201](https://github.com/ReleMai/WORLDSEED/actions/runs/38754472201): **success, all seven jobs**. New Linux resident/material/input/window contracts and Windows controlled live-scene tests passed, alongside the retained reference, engine, economy, NPC and world/UI checks.
- [Resource and Homestead Regression #38754472140](https://github.com/ReleMai/WORLDSEED/actions/runs/38754472140): **success**, including existing resource/save compatibility checks.
- [Manual Windows OpenGL probe #38754527895](https://github.com/ReleMai/WORLDSEED/actions/runs/38754527895): **failed** in the preexisting `tools.worldspace_opengl_probe` before any W1/W2 capture. Windows reported an **access violation inside ModernGL `init_context` / `get_context` / `create_context`** (probe line 77, runner exit `4294967295`). Installed versions were Python 3.11.9, pygame-ce 2.5.8, ModernGL 5.11.0 and glcontext 2.5.0. No driver JSON or PNG was produced; the later forest and live-camp steps were skipped. The root cause is not established by this trace and must be diagnosed on Windows; do not label it a confirmed hardware capability issue or a successful GPU validation.
- The local Linux SDL attempt also could not detect a supported OpenGL window. Only standalone **EGL llvmpipe** shader tests and controlled screenshots succeeded locally. Neither constitutes native Windows evidence.

Next work should diagnose the Windows context-startup access violation, obtain driver evidence, and continue W2 interaction/UI/native acceptance from the implemented movement foundation. Keep the read-only snapshot and all compatibility/privacy tests intact.

For the next isolated Windows diagnosis, run a minimal SDL 3.3 reproducer with `py -3 -X faulthandler -u`. Flush SDL GL attributes, raw GL vendor/renderer/version, current WGL context/DC and dependency versions **before** ModernGL initialization. Compare fresh processes calling `moderngl.create_context(require=330)` and `moderngl.create_context(require=330, libgl="opengl32.dll")`: in 5.11.0 the latter bypasses `DefaultLoader` and asks glcontext to detect the existing SDL context. This is an unvalidated diagnostic comparison, not an implemented fix. Do not use `standalone=True` or `share=True` to create another window/context. Invalid function pointers/driver startup are hypotheses; the current trace does not establish the cause.
