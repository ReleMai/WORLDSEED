# WORLDSEED — GPU-first Windows next-chat handoff

**Prepared / reconciled:** 2026-10-15. **Source of truth:** [ReleMai/WORLDSEED](https://github.com/ReleMai/WORLDSEED) `main`. **Purpose:** continue GPU gameplay ownership after the implemented W1 live scene adapter, without repeating G0/G1/W1 or reworking the legacy software game.

**Latest continuation:** [W3 exteriors and Windows candidate](WORLDSEED_W3_EXTERIORS_WINDOWS_CANDIDATE_2026-10-16.md). Closed exterior shells, current terrain catalog, engine-owned ambient light and separate executable packaging are implemented; full interiors/UI and native hardware acceptance remain open.

**W2 implementation:** [W2 Action Hub/context handoff](WORLDSEED_W2_ACTION_HUB_CONTEXT_HANDOFF_2026-10-15.md) supersedes earlier read-only-pointer and absent-UI descriptions. It records 128 affected local tests, real SDL software captures and the publication/native closeout.

## Paste this into the next WORLDSEED chat

```text
Continue WORLDSEED GPU-first development from the canonical GitHub repo https://github.com/ReleMai/WORLDSEED on the latest validated main. First read docs/development/WORLDSPACE_RENDERER_ART_WORLDGEN_ROADMAP_2026-10-14.md, docs/handoffs/WORLDSEED_GPU_FIRST_NEXT_CHAT_HANDOFF_2026-10-15.md and docs/handoffs/WORLDSEED_W1_LIVE_GPU_SCENE_2026-10-15.md and docs/handoffs/WORLDSEED_W2_ACTION_HUB_CONTEXT_HANDOFF_2026-10-15.md, then inspect the current code and CI before making changes.

Primary target: the NEW native Windows OpenGL 3.3/ModernGL renderer. Treat the older pygame software game as a preserved legacy version, not the target of new graphics development. Do not rewrite the simulation, lose existing engine optimizations, change worldgen/resourcegen or save formats, or work across many branches.

Historical GitHub-verified pre-W1 baseline: 44b41d9df06620359094fa68a29afc0a1d3101e9, Fast Gate #38684262876 all 7 jobs green; roadmap/handoff checkpoint c26a314 followed. Do not assume either is current tip. The prepared forest/camp visual arena remains available through RUN_WORLDSEED_GPU_PREVIEW.bat and tools/worldseed_gpu_playtest.py; its WASD is visual camera motion. It is distinct from the W2 authoritative gameplay candidate.

W1 IS IMPLEMENTED: live_gpu_scene.py captures immutable bounded prepared terrain/resources, exact player/NPC foot fractions, current-visible exterior actors, active fires, weather/minute and scoped memory. World.prepared_tile_at and ResourceSystem.prepared_feature_at never load or generate. Unknown/private/roof/interior cells fail closed; missing seasonal resource preparation and derived shoreline reeds are omitted. Existing resource identity, harvest stages, collision and simulation authority remain intact. 127 unique focused tests passed locally, including 9 live snapshots, 7 input and 3 event-loop cases, production collision/sight and real EGL shader checks; publication CI is recorded in the W1/W2 handoff closeout. EGL llvmpipe is software shader proof, not native GPU performance evidence. Do not restart W1.

CONTINUE FROM THE IMPLEMENTED W2 OUTDOOR ACTIONS/HUD: inspect tools/worldseed_gpu_gameplay.py, ui/gpu_gameplay_session.py, ui/gpu_gameplay_actions.py and presentation/gl_context.py before extending them. Enter Action Hub, visible-cell selection, explicit harvest/pickup/step confirmation, Tab Console, paged inventory/health/help and pause are implemented. Existing commands own all effects, and dispatch rechecks current sight/privacy/resource identity. Modal UI uses NavigationStack and pauses the clock/held motion. The common explicit bootstrap now opens the real Linux SDL offscreen GPU window; that llvmpipe evidence is software-only. Windows probe 38833104840 now cleanly rejects Microsoft GDI Generic OpenGL 1.1 before ModernGL; it supplies no native 3.3 rendering evidence and does not establish every earlier crash cause. Use a hardware driver for the next acceptance run. Next are full native acceptance and W3 roofs/interiors/full-game UI; saved-world support and default promotion remain later gates. Do not restart the adapter or implement separate gameplay logic.

Also arrange W0 native Windows OpenGL screenshots/driver/performance evidence for forest and camp (night, sunrise, noon, rain, storm, snow, fog, 4 seasons); use the manual worldspace-opengl-probe.yml workflow or a real Windows machine. Do not call the renderer production-ready or claim FPS improvement until a hardware driver and gameplay acceptance tests confirm it. Shadows today are source-authored contact sprites, not directional shadow casting. More work remains for roofs, interior privacy, UI, gameplay lights and sheltered weather.

Preserve every old save/resource identity, the previous software launcher, documented M2 optimizations, existing tooling and Fast Gate. Write focused FOW/privacy/interaction/camera/performance-budget tests, validate each coherent work unit, update roadmap and handoff, and sync only green changes to GitHub main the same session (no proliferating branches). Explain what genuinely changed, what tests passed, and what still blocks a playable Windows GPU build.
```

## Historical checkpoint and current validation

- **Last code + CI-fix baseline before documentation update:** `44b41d9df06620359094fa68a29afc0a1d3101e9` on `main`. [Fast Gate run #38684262876](https://github.com/ReleMai/WORLDSEED/actions/runs/38684262876) **completed successfully: seven of seven jobs**. That run includes the new pure GPU weather/scene contracts and **Windows prepared forest GPU adapter** test. The unchanged legacy `tests.test_reference_scenes` suite was rerouted to Linux headless after a Windows SDL dummy process exit `-1`; on the corrected run it passed. See [CI relocation evidence](WORLDSPACE_GPU_FAST_GATE_LINUX_REFERENCE_RELOCATION_2026-10-15.md).
- **No native GPU driver proof is established by that Fast Gate.** The separately dispatched workflow [`worldspace-opengl-probe.yml`](../../.github/workflows/worldspace-opengl-probe.yml) is manual to control CI cost. Before accepting pixel quality or performance, obtain PNGs and JSON reporting actual GL_VENDOR/GL_RENDERER/GL_VERSION and p50/p95/p99 from physical/native Windows GPU context. Software-emulated hosted GL is not a graphics release sign-off.
- The original roadmap/handoff documentation checkpoint was `c26a314`; preserve it as historical context. Always inspect live `main` and current CI before editing.
- **W1/W2 implementation:** `265ba115cb0837d6b51314ee37a057449f194032`. **127 unique local tests passed**, including capture, input, single-window loop, collision, full reference scenes and actual EGL shaders; compile/whitespace checks passed. See [implementation/CI closeout](WORLDSEED_W1_LIVE_GPU_SCENE_2026-10-15.md). Native Windows acceptance remains separate.
- **Current CI:** [Fast Gate #38754472201](https://github.com/ReleMai/WORLDSEED/actions/runs/38754472201) **7/7 successful**; [Resource/Homestead #38754472140](https://github.com/ReleMai/WORLDSEED/actions/runs/38754472140) also successful. [Manual Windows probe #38754527895](https://github.com/ReleMai/WORLDSEED/actions/runs/38754527895) failed in ModernGL context initialization with an access violation before driver metadata/screenshots; subsequent GPU scene steps were skipped. Diagnose this startup blocker before native graphics sign-off. The W1/W2 handoff records exact versions, trace and an isolated diagnostic comparison.

## What's already implemented (do not rebuild)

| Delivered slice | Existing files and behavior |
| --- | --- |
| **G0/G1a/G1b** | `worldseed/presentation/worldspace.py` and `worldspace_adapter.py`: bounded immutable foot-anchored instances, world-space camera, deterministic layers and prepared, FOW-gated resource/actor projection |
| **G2 software proof** | `canopy_preview.py`: one-to-four-tree overhead compositing and alpha masks, with old software render opt-in and preserved tree gameplay identities |
| **G4 tree artwork** | `tree_art.py`, `assets/sprites/worldspace/trees/manifest.json` + `tree_layers.b85`: hash-checked separate oak/pine trunk, shadow, seasonal crown for four seasons; artwork still awaits real native visual sign-off |
| **G8 shader candidate** | `gl_worldspace.py` + `assets/shaders/worldspace_sprite.vert/.frag`: ModernGL 3.3, sprite batching, texture budgets, visibility scissors and GPU-resident passes |
| **G5/G6/G7 atmosphere preview** | `gl_atmosphere.py` + `worldspace_post.vert/.frag`: shader day/night grading, debug torch and already-prepared campfire light, wind-based clouds, mist/fog, rain and snow. These are graphics features in the GPU arena, **not authoritative visibility/physics/indoor lighting** |
| **GPU first visual arena** | `gpu_scene_bridge.py`, `tools/worldseed_gpu_playtest.py`, `RUN_WORLDSEED_GPU_PREVIEW.bat`: a single native OpenGL window from prepared forest/camp fixtures, with **visual-only** WASD, season/weather toggles, screenshots/report; no real player moves or old saves loaded |
| **W1 live read-only gameplay snapshot** | `live_gpu_scene.py`, `World.prepared_tile_at`, `ResourceSystem.prepared_feature_at`: detached prepared ground/tree stages, fractional player/NPC feet, exact current-visible exterior actors, active fires and authoritative weather/minute. Pure resident reads, local spatial indexes, explicit budgets and conservative shell/roof/interior privacy gates; no save or simulation mutation |
| **W1 materials / shader visibility** | Additional authorized actors reuse the content catalog; shared stump/sapling art preserves stage identity; fire extent uses exact per-cell clips. Atmosphere leaves transparent unknown pixels black under fog/rain/snow. Actual GLSL compiled/tested using optional EGL llvmpipe; native Windows evidence remains open |

**Implemented and locally tested:** W2's separate opt-in `tools/worldseed_gpu_gameplay.py` / `ui/gpu_gameplay_input.py` single-window foundation. It starts from a temporary new world/controlled prepared scene and reuses the simulation's free movement, realtime and `MoveCommand` APIs. Inspect its current implementation/tests before continuing; outdoor actions/HUD now extend it, while full native W2 exit has not been accepted.

**Known gaps:**
- The GPU renderer is not the default game renderer. W1 supplies a real-game read-only capture and W2's opt-in outdoor Action Hub/HUD is implemented and locally tested; live-save loading, full combat/crafting/storage/dialogue/interior UI and native acceptance remain open.
- W1 deliberately omits roof/shell/private/interior cells and draws only current ground; memory is captured but not drawn. Missing resident seasonal resources and unprepared shoreline reeds remain omitted. Stump/sapling art is shared across oak/pine.
- Tree shadows are **static authored contact shadows**, not live sun/fire directional casting or actor shadows. Fueled active fires are admitted, but glow remains within the source cell until shared occlusion is integrated. Covered rain, ground wetness, indoor blockers and wider authoritative lighting remain incomplete.
- Atmospheric effects and art have passed structural/source tests but still need real Windows driver, screenshots, high-resolution performance, resize/alt-tab/device-loss and long-session validation.
- G3 new placement/ecology and G9 polish are not implemented. Never silently change resourcegen v5 or worldgen v8, especially for legacy saves.

## Current roadmap and development priority

The in-place [G0–G9 roadmap](../development/WORLDSPACE_RENDERER_ART_WORLDGEN_ROADMAP_2026-10-14.md) has been reconciled with actual progress. **Windows GPU-first W0–W5 packages** now describe the practical critical path. GPU-first means spending new engineering time on the native OpenGL world/gameplay ownership—not polishing the legacy software renderer.

1. **W0 native evidence (parallel):** launch 720p and 1080p forest/camp, examine at least noon/night/storm/fog/snow and seasonal crowns, record performance/driver, capture images, measure draw calls and source/GPU cache usage, document defects; do not claim hardware proof without it.
2. **W1 IMPLEMENTED / LOCALLY VALIDATED:** retain `capture_live_scene`, immutable snapshot/material interfaces and resident-only reads. Preserve exact sight, privacy masks, old resource identity and non-mutation tests. See [W1 handoff](WORLDSEED_W1_LIVE_GPU_SCENE_2026-10-15.md); do not rebuild the adapter or make rendering prepare missing content.
3. **W2 movement foundation IMPLEMENTED; full native/gameplay acceptance OPEN:** continue the separate opt-in single-window candidate, using existing free movement/realtime/`MoveCommand` logic, exact collision and camera/pointer projection. Pointer selection is read-only; explicit Action Hub confirmation rechecks authorization and dispatches existing commands. Basic GPU HUD/Console navigation is implemented; full game/interior UI and saved-world acceptance remain deferred. Validate focus/held keys, resize and exit, then obtain native Windows acceptance; no duplicate event pump or renderer-driven simulation ticks.
4. **W3 privacy/UI:** buildings, exterior shells/roofs, interiors/portals, gameplay-visible NPCs/creatures, inventory/crafting, interaction HUD, hover/click and combat overlays; test room/roof LOS and pointer masks before release.
5. **W4 real environment:** directional shadows, fuel and wall/roof-aware lights, proper rain/roof/canopy occlusion and safe FOW, user-reviewed art/performance.
6. **W5 promotion:** Windows native driver matrix, packaged GPU assets and dependencies, no shader crash, resize/alt-tab/fullscreen, 30–60-minute active session, long soak, old saves, p50/p95/p99, bounded memory and quality presets. Do **not** switch the default launcher until this gate passes.

**Continuation acceptance:** retain the W1 non-mutation/FOW/privacy/resource/budget suite while adding meaningful W2 input and authority tests. Run focused tests and inspect publication Fast Gate outcomes. If native input/driver checks cannot run locally, document that gap and the exact validated command without claiming hardware performance or full W2 completion. Only commit/push green and update handoff. Respect the established ~25-minute coherent work-unit habit; each session should finish in a clean state.

## Native Windows testing commands

From the checked-out repository root with updated OpenGL drivers:

```powershell
py -3 -m pip install -e ".[gpu]"
py -3 -m tools.worldseed_gpu_playtest --scene forest
py -3 -m tools.worldseed_gpu_playtest --scene camp --frames 180 --screenshot scratch/gpu-camp.png --report scratch/gpu-camp.json
```

Or double-click `RUN_WORLDSEED_GPU_PREVIEW.bat`. **Visual-only** controls: WASD roam the fixture camera, `1`–`4` seasons, `F` weather, `T` torch, `[`/`]` time, `+`/`-` zoom, `P` screenshot, Esc exit. These must not be mistaken for real gameplay.

W2's opt-in movement candidate is implemented in `tools/worldseed_gpu_gameplay.py`. Run `py -3 -m tools.worldseed_gpu_gameplay` for a temporary new world, or add `--prepared-scene camp --frames 30 --screenshot scratch/gpu-live-camp.png --report scratch/gpu-live-camp.json` for controlled capture. WASD/arrows move, Shift sprints, `.` waits, `P` picks up, F12 captures, Enter opens Actions, Tab opens Console, and Esc pauses or goes back one route. Quit is explicit in Pause. See the W1/W2 implementation handoff for limits and evidence; full native acceptance remains open.

## Keep these invariants and resources

- Canonical `main`: `https://github.com/ReleMai/WORLDSEED`; commit validated code, docs, CI, handoff together. No persistent extra branches or broken intermediate pushes.
- Existing engine implementation/optimization documents **must stay**: `docs/development/EARLY_ACCESS_PYGAME_PLAN.md`, `docs/development/GPU_COMPOSITING_EXPERIMENT.md`, `docs/handoffs/EARLY_ACCESS_M2_ENGINE_CLOSEOUT.md`, `docs/handoffs/EARLY_ACCESS_NATIVE_HIGHRES_HANDOFF_2026-10-14.md`.
- Main GPU ADR: [G5/G6/G8 Windows GPU-first](../development/WORLDSPACE_WINDOWS_GPU_FIRST_G5_G6_G8_ADR_2026-10-15.md). Previous art/shader handoff: [G4/G8](WORLDSPACE_G4_G8_ART_SHADER_HANDOFF_2026-10-15.md).
- W1 implementation/limits: [live-scene handoff](WORLDSEED_W1_LIVE_GPU_SCENE_2026-10-15.md); source `worldseed/presentation/live_gpu_scene.py`.
- Test sources: `tests/test_gpu_prepared_reads.py`, `tests/test_gpu_live_materials.py`, `tests/test_gpu_visibility_shader.py`, the live snapshot tests, and existing weather/bridge/world-space/art suites. Existing Windows Fast Gate and Linux legacy reference regressions remain mandatory.

**Delivery expectation for the next chat:** continue W2 from the current candidate after inspecting `main`, demonstrate focused tests/CI and authoritative state safety, explain remaining native/gameplay blockers, update this handoff and roadmap, and sync validated work. Preserve W1 and the legacy renderer. Do not present a partial input candidate as a production-ready GPU game or claim a speedup without native measurements.
