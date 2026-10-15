# WORLDSEED — GPU-first Windows next-chat handoff

**Prepared:** 2026-10-15. **Source of truth:** [ReleMai/WORLDSEED](https://github.com/ReleMai/WORLDSEED) `main`. **Purpose:** resume a coherent GPU renderer implementation unit without repeating G0/G1 or reworking the old software game.

## Paste this into the next WORLDSEED chat

```text
Continue WORLDSEED GPU-first development from the canonical GitHub repo https://github.com/ReleMai/WORLDSEED on the latest validated main. First read docs/development/WORLDSPACE_RENDERER_ART_WORLDGEN_ROADMAP_2026-10-14.md and docs/handoffs/WORLDSEED_GPU_FIRST_NEXT_CHAT_HANDOFF_2026-10-15.md, then inspect the current code and CI before making changes.

Primary target: the NEW native Windows OpenGL 3.3/ModernGL renderer. Treat the older pygame software game as a preserved legacy version, not the target of new graphics development. Do not rewrite the simulation, lose existing engine optimizations, change worldgen/resourcegen or save formats, or work across many branches.

Verified baseline prior to this documentation handoff: 44b41d9df06620359094fa68a29afc0a1d3101e9, with Fast Gate #38684262876 passing all 7 jobs. Current GPU visual arena runs prepared forest/camp scenes using layered seasonal oak/pine artwork, distinct trunk/shadow/canopy, shader-based day/night colors, campfire/debug torch lights, cloud shadows, moving fog, rain and snow. Windows launcher: RUN_WORLDSEED_GPU_PREVIEW.bat; source: gpu_scene_bridge.py, gl_worldspace.py, gl_atmosphere.py, worldspace_adapter.py, and tools/worldseed_gpu_playtest.py. This is currently a VISUAL TEST WINDOW, not the game's real movement, save, NPC, inventory, construction or combat renderer.

NEXT CODING UNIT: W1, the read-only, immutable, strictly bounded real-game GPU scene snapshot, sourced from the actual prepared live simulation (terrain and trees including harvest/stump/sapling stages, actor foot positions, visible NPCs/creatures, fire/weather/time, exact current sight, stealth and private-room gating). Inspect actual engine interfaces and test the adapter; never render unknown cells or mutate state. After a green W1, start W2 authoritative movement/input in ONE GPU SDL window, retaining exact collision, cursor projection and game command semantics. Avoid converting the existing software renderer into an OpenGL framebuffer upload.

Also arrange W0 native Windows OpenGL screenshots/driver/performance evidence for forest and camp (night, sunrise, noon, rain, storm, snow, fog, 4 seasons); use the manual worldspace-opengl-probe.yml workflow or a real Windows machine. Do not call the renderer production-ready or claim FPS improvement until a hardware driver and gameplay acceptance tests confirm it. Shadows today are source-authored contact sprites, not directional shadow casting. More work remains for roofs, interior privacy, UI, gameplay lights and sheltered weather.

Preserve every old save/resource identity, the previous software launcher, documented M2 optimizations, existing tooling and Fast Gate. Write focused FOW/privacy/interaction/camera/performance-budget tests, validate each coherent work unit, update roadmap and handoff, and sync only green changes to GitHub main the same session (no proliferating branches). Explain what genuinely changed, what tests passed, and what still blocks a playable Windows GPU build.
```

## Exact verified checkpoint

- **Last code + CI-fix baseline before documentation update:** `44b41d9df06620359094fa68a29afc0a1d3101e9` on `main`. [Fast Gate run #38684262876](https://github.com/ReleMai/WORLDSEED/actions/runs/38684262876) **completed successfully: seven of seven jobs**. That run includes the new pure GPU weather/scene contracts and **Windows prepared forest GPU adapter** test. The unchanged legacy `tests.test_reference_scenes` suite was rerouted to Linux headless after a Windows SDL dummy process exit `-1`; on the corrected run it passed. See [CI relocation evidence](WORLDSPACE_GPU_FAST_GATE_LINUX_REFERENCE_RELOCATION_2026-10-15.md).
- **No native GPU driver proof is established by that Fast Gate.** The separately dispatched workflow [`worldspace-opengl-probe.yml`](../../.github/workflows/worldspace-opengl-probe.yml) is manual to control CI cost. Before accepting pixel quality or performance, obtain PNGs and JSON reporting actual GL_VENDOR/GL_RENDERER/GL_VERSION and p50/p95/p99 from physical/native Windows GPU context. Software-emulated hosted GL is not a graphics release sign-off.
- This documentation handoff will have a newer docs-only commit. Always inspect live `main` and the latest relevant CI status; do not assume the baseline commit is still tip after the handoff commit.

## What's already implemented (do not rebuild)

| Delivered slice | Existing files and behavior |
| --- | --- |
| **G0/G1a/G1b** | `worldseed/presentation/worldspace.py` and `worldspace_adapter.py`: bounded immutable foot-anchored instances, world-space camera, deterministic layers and prepared, FOW-gated resource/actor projection |
| **G2 software proof** | `canopy_preview.py`: one-to-four-tree overhead compositing and alpha masks, with old software render opt-in and preserved tree gameplay identities |
| **G4 tree artwork** | `tree_art.py`, `assets/sprites/worldspace/trees/manifest.json` + `tree_layers.b85`: hash-checked separate oak/pine trunk, shadow, seasonal crown for four seasons; artwork still awaits real native visual sign-off |
| **G8 shader candidate** | `gl_worldspace.py` + `assets/shaders/worldspace_sprite.vert/.frag`: ModernGL 3.3, sprite batching, texture budgets, visibility scissors and GPU-resident passes |
| **G5/G6/G7 atmosphere preview** | `gl_atmosphere.py` + `worldspace_post.vert/.frag`: shader day/night grading, debug torch and already-prepared campfire light, wind-based clouds, mist/fog, rain and snow. These are graphics features in the GPU arena, **not authoritative visibility/physics/indoor lighting** |
| **GPU first visual arena** | `gpu_scene_bridge.py`, `tools/worldseed_gpu_playtest.py`, `RUN_WORLDSEED_GPU_PREVIEW.bat`: a single native OpenGL window from prepared forest/camp fixtures, with **visual-only** WASD, season/weather toggles, screenshots/report; no real player moves or old saves loaded |

**Known gaps:**
- The GPU renderer is not the default game renderer. There is **no authoritative real-game GPU world loop** for live saves, entity controls, harvesting, NPC AI, combat, inventory/crafting, property/door/roof privacy or interior scenes.
- Tree shadows are **static authored contact shadows**, not live sun/fire directional casting or actor shadows. Covered rain, ground wetness, indoor blockers, lighting occlusion and authoritative fire/fuel interactions are not complete.
- Atmospheric effects and art have passed structural/source tests but still need real Windows driver, screenshots, high-resolution performance, resize/alt-tab/device-loss and long-session validation.
- G3 new placement/ecology and G9 polish are not implemented. Never silently change resourcegen v5 or worldgen v8, especially for legacy saves.

## Current roadmap and development priority

The in-place [G0–G9 roadmap](../development/WORLDSPACE_RENDERER_ART_WORLDGEN_ROADMAP_2026-10-14.md) has been reconciled with actual progress. **Windows GPU-first W0–W5 packages** now describe the practical critical path. GPU-first means spending new engineering time on the native OpenGL world/gameplay ownership—not polishing the legacy software renderer.

1. **W0 native evidence (parallel):** launch 720p and 1080p forest/camp, examine at least noon/night/storm/fog/snow and seasonal crowns, record performance/driver, capture images, measure draw calls and source/GPU cache usage, document defects; do not claim hardware proof without it.
2. **W1 NEXT COHERENT CODING UNIT:** map an actual **live game** read-only prepared viewport (player fractional foot, current terrain, visible/remembered cells, feature stages and depletion, authorized NPCs/creatures, fired and active lights, current authoritative weather/minute) into immutable GPU world-space scene/material commands. Strictly use simulation-managed visibility, property/interior privacy and NPC stealth. Refuse unknown or unprepared geometry; no game state mutation, no database writes, no worldgen or save version change. Inspect actual engine APIs rather than guessing.
3. **W2 gameplay input:** make GPU SDL window owner route actual player WASD and pointer commands to existing sim engine, with trunk/door collision and continuous fractional motion; no duplicate event pump or renderer-driven simulation ticks.
4. **W3 privacy/UI:** buildings, exterior shells/roofs, interiors/portals, gameplay-visible NPCs/creatures, inventory/crafting, interaction HUD, hover/click and combat overlays; test room/roof LOS and pointer masks before release.
5. **W4 real environment:** directional shadows, fuel and wall/roof-aware lights, proper rain/roof/canopy occlusion and safe FOW, user-reviewed art/performance.
6. **W5 promotion:** Windows native driver matrix, packaged GPU assets and dependencies, no shader crash, resize/alt-tab/fullscreen, 30–60-minute active session, long soak, old saves, p50/p95/p99, bounded memory and quality presets. Do **not** switch the default launcher until this gate passes.

**First-unit acceptance:** run targeted tests proving no hidden NPC/private rooms/unexplored terrain rendered, exact old resource/collision identity and harvested state, no state fingerprint change after GPU capture, preserved viewport/instance/texture limits, camera/actor foot alignment; run Fast Gate and inspect outcomes. If a test cannot run locally, use GitHub Windows/Linux CI and record what was *actually* verified. Only commit/push green and update handoff. Respect the established ~25-minute coherent work-unit habit; the project is larger than a single chat, but each work session should finish in a clean state.

## Native Windows testing commands

From the checked-out repository root with updated OpenGL drivers:

```powershell
py -3 -m pip install -e ".[gpu]"
py -3 -m tools.worldseed_gpu_playtest --scene forest
py -3 -m tools.worldseed_gpu_playtest --scene camp --frames 180 --screenshot scratch/gpu-camp.png --report scratch/gpu-camp.json
```

Or double-click `RUN_WORLDSEED_GPU_PREVIEW.bat`. **Visual-only** controls: WASD roam the fixture camera, `1`–`4` seasons, `F` weather, `T` torch, `[`/`]` time, `+`/`-` zoom, `P` screenshot, Esc exit. These must not be mistaken for real gameplay.

## Keep these invariants and resources

- Canonical `main`: `https://github.com/ReleMai/WORLDSEED`; commit validated code, docs, CI, handoff together. No persistent extra branches or broken intermediate pushes.
- Existing engine implementation/optimization documents **must stay**: `docs/development/EARLY_ACCESS_PYGAME_PLAN.md`, `docs/development/GPU_COMPOSITING_EXPERIMENT.md`, `docs/handoffs/EARLY_ACCESS_M2_ENGINE_CLOSEOUT.md`, `docs/handoffs/EARLY_ACCESS_NATIVE_HIGHRES_HANDOFF_2026-10-14.md`.
- Main GPU ADR: [G5/G6/G8 Windows GPU-first](../development/WORLDSPACE_WINDOWS_GPU_FIRST_G5_G6_G8_ADR_2026-10-15.md). Previous art/shader handoff: [G4/G8](WORLDSPACE_G4_G8_ART_SHADER_HANDOFF_2026-10-15.md).
- Test sources: `tests/test_gpu_weather_pipeline.py`, `tests/test_gpu_playtest_bridge.py`, `tests/test_worldspace_gpu_art.py`, `tests/test_worldspace_scene.py`. Existing Windows Fast Gate and Linux legacy reference regressions remain mandatory.

**Delivery expectation for the next chat:** actually implement the next bounded GPU gameplay bridge after inspecting `main`, demonstrate tests/CI and authoritative state safety, explain remaining blockers, update this handoff and roadmap, and sync validated work. Do not present preview-only visuals as a playable GPU game.
