# WORLDSEED — GPU-first Windows playable-visual slice development handoff

**Date:** 2026-10-15. **Prior canonical head:** `198d4be2dff46d093476896db4654b5aec403756`, whose Fast Gate #38680990486 is green (7/7). See the [GPU-first ADR](../development/WORLDSPACE_WINDOWS_GPU_FIRST_G5_G6_G8_ADR_2026-10-15.md), previous [G4 layered art handoff](WORLDSPACE_G4_G8_ART_SHADER_HANDOFF_2026-10-15.md), and G0–G9 graphics roadmap.

## Changelog

- **New:** `worldseed/presentation/gl_atmosphere.py`, `worldseed/assets/shaders/worldspace_post.vert/.frag`: native OpenGL offscreen-world/postprocess compositor with continuous day/night grading, bounded read-only warm point lights, world-coordinate cloud shadows, multi-scale fog, rain and snow effects. No CPU whole-frame upload/readback, except an explicit user screenshot request.
- **Updated:** `gl_worldspace.py` + `worldspace_sprite.vert`: render into an optional GPU framebuffer with time-driven, trunk-safe crown sway, without new SDL/window/input ownership. Retain existing `draw()` default behavior and 128 MiB texture budget.
- **New:** `gpu_scene_bridge.py`: bounded and sight-gated terrain tile material batching, prepared oak/pine shadow/trunk/crown, viewer sprite and actual campfire art from the existing content pack. No tree generation, collision or selection changes.
- **New:** `tools/worldseed_gpu_playtest.py` and `RUN_WORLDSEED_GPU_PREVIEW.bat`: native Windows visual roaming/inspection in prepared real-simulation forest and camp fixtures. UI via SDL caption/keys and screenshot/report. The fixture state hash is checked before/after rendering; no saved player world is opened.
- **New:** pure GL state/contract, scene projection and real prepared fixture tests in `tests/test_gpu_weather_pipeline.py` and `tests/test_gpu_playtest_bridge.py`. Extend Fast Gate with small tests and the *manual-only* Windows-native GPU screenshot workflow for evidence.
- **No changes:** game state serializers, `WORLDGEN_VERSION`, `RESOURCEGEN_VERSION`, legacy launcher, `pygame_terminal.py` gameplay loop, M2 engine optimization plans, hardware gating, default software renderer, old saves.

## What remains / caution

This work is **GPU-first development**, not a claim of production full-game renderer completion. Trees, shadows, weather, fog and lighting run in the interactive GPU **visual arena**; the live game's NPC movement, construction UI, combat, roof/room privacy, saved-world renderer and input callbacks have not yet moved. Shadow sprites are not dynamic tree shadow casting. Shader, actual performance and driver behavior need Windows testing; automated G1/G4 and pure tests cannot approve visual fidelity. Unbounded native GPU failure must not silently alter a player's save.

## Fast continuation plan

1. Check all post-push GitHub Fast Gate jobs; fix diagnostics and tests in the same session if needed.
2. Run `RUN_WORLDSEED_GPU_PREVIEW.bat` on a real Windows PC with optional ModernGL deps and make screenshots at night, noon, storm, fog, spring/autumn/winter (both forest and camp). Collect screenshot, GL vendor/renderer, p50/p95, draw call count and atlas memory. Manual native workflow is non-default to avoid Actions cost/time.
3. Resolve lighting/shader/mobile GPU portability and actual high-FPS profiling before expanding GPU material catalog.
4. Next architectural unit: authoritative gameplay snapshot and UI/input routing in one GPU SDL window, with mouse-pointer camera parity and hard privacy gates; then native old-save/interaction regressions, roof/indoor occlusion, dynamic shadows. Do not push broken intermediate states; don't branch per phase.

**User priority:** all **new** renderer work goes to the Windows GPU path; the previous software game is a preserved older version, not the design target.
