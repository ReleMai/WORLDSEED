# WORLDSEED — Windows GPU-first worldspace vertical slice (G5/G6/G8 ADR)

**Date:** 2026-10-15. **Decision:** prioritize a native, single-context OpenGL world visualization path. Keep the previous pygame Surface gameplay renderer on its existing branch of runtime behavior; do not silently change existing saves, renderer imports, movement/input authority, or worldgen versions. This ADR extends the [G4/G8 foundation](WORLDSPACE_G4_G8_LAYERED_ART_AND_OPENGL_ADR_2026-10-15.md).

## Purpose and actual scope

This unit adds a **Windows-native interactive GPU visual test window**, not a production gameplay renderer replacement. Its forest/camp comes from `tools.reference_scene_fixtures.build_fixture()`, which seeds **production prepared** terrain and resource data into an isolated temporary database. It does **not** open player save files. WASD moves a visual-world camera/avatar only; sim moves, NPC AI, hit tests, harvesting, interiors, inventory, toolbars and gameplay weather logic still belong to the old gameplay engine until separately migrated. The standard game launcher remains the previous software version. `RUN_WORLDSEED_GPU_PREVIEW.bat` is the new primary graphics development entrypoint on Windows.

### New GPU pipeline

1. **Source:** bounded `visible_prepared_window()` samples from the existing `World.tile_at` and `ResourceSystem.feature_at` prepared map. It refuses unprepared tile generation and has no authoritative writes.
2. **Geometry:** `gpu_scene_bridge.py` projects authored terrain (deterministic 10 variants), intact oak/pine sprites, physically anchored shadow sprites, separated trunk/crown sprites, viewable fire sprite and an existing player sprite. Terrain instances are sorted by texture for contiguous GPU batching. The existing `worldspace_adapter` provides independent source/child IDs, 2.5D draw order, authorized sight clips and local player-foot canopy fade. Wind moves the *upper crown vertices*, not the trunk/collision. Existing `MAX_COMMANDS=4096`, `MAX_VISIBLE_CELLS=8192` and `MAX_SCENE_INSTANCES=4096` gates still apply.
3. **GPU sprite pass:** the ModernGL 3.3 program renders into a caller-owned RGBA8 off-screen framebuffer, with bounded LRU source textures, grouped vertex batches and per-visible-cell scissor regions. No pygame Surface is used to render the whole frame to the GPU. The game input or window is never managed by the sprite renderer class.
4. **GPU atmospheric/light pass:** `gl_atmosphere.py` draws the framebuffer to the original, *single* SDL2 OpenGL window using `worldspace_post.frag`. This supplies a continuous daylight curve, cool night tones, cloud penumbrae, localized warm authored/fixture fire or explicitly debug torch lighting, independently scrolling world-aligned clouds, multiscale drifting mist, wind-driven rain streaks and snowflakes. Eight local lights max; the GL framebuffer is resize-limited to 48 MiB. Fog does not reveal or query unknown-world objects; model visibility gates still run upstream.
5. **Presentation/input for testing:** a standalone Windows fixture playtest owns exactly one OpenGL context, SDL events, resize, keyboard, screenshot and frame-pacing. The native GPU driver is reported with render times so shader output can be compared and profiled.

### Current art and lighting limitations

- Oak and pine 384×384 RGBA layered sprites were source-authored in G4; this pass **uses** that art (spring/summer/autumn/winter crown variants), not an unreviewed replacement. The visual test focuses on how they composite and animate.
- Shadows are *authored contact-shadow sprites*, not yet dynamic directional tree light-casting, normal maps or shadow maps. Local fires/torch lights brighten the prepared scene but are not gameplay-authoritative visibility or NPC-detection sources.
- Clouds are smooth world-space shader fields, not physical weather fronts. Rain/snow/fog are visual shader layers without accumulation/wetness or gameplay penalties; live weather coupling is `weather_frame()`'s read-only adapter when a game scene calls it.
- `GLWorldspaceRenderer` still renders sprite layers; high-volume terrain, dense forests, 4K 60fps, windows/portals, rooftops, UI compositing, real game controls, interactive collision, GPU device-loss recovery, shader context reset and a native hardware driver matrix are not certified. No software-rendering pixel parity claim is made; different materials and weather are intentional.
- The native Windows GPU playtest has **not** run in the assistant's source-isolated container. GitHub's pure/fixture tests are not proof of an OpenGL hardware run. Use the manually dispatched native workflow and a real user PC to review screenshots and latency. Check GL vendor/driver: Windows-hosted Actions runners may fall back to software GL.

## Windows reproduction (from repository root)

```powershell
py -3 -m pip install -e ".[gpu]"
py -3 -m tools.worldseed_gpu_playtest --scene forest
py -3 -m tools.worldseed_gpu_playtest --scene camp --frames 180 --screenshot scratch/gpu-camp.png --report scratch/gpu-camp.json
```

Double-click `RUN_WORLDSEED_GPU_PREVIEW.bat` to open the forest visual test after installing optional dependencies. **WASD:** roam prepared area; **1–4:** four tree seasons; **F:** clear/cloudy/rain/storm/snow/fog; **T:** enable/disable debug torch; **[ and ]:** adjust time of day; **+ / -:** tile zoom with safe frame-command budget; **P:** screenshot; **Esc:** exit. Caption reports visual weather/time and per-frame render estimate. This is a visual camera movement only and must not be presented as valid player physics.

## New verification gates

- `python -m unittest -v tests.test_gpu_weather_pipeline tests.test_gpu_playtest_bridge.GPUSceneBridgeContracts`: 12 pure source/GL-double tests covering day/night wrap, bounded weather/light inputs, source-scene clipping, tree grouping and shadow isolation, framebuffer resize, texture/compositor ownership and no accidental frame readback.
- `python -m unittest -v tests.test_gpu_playtest_bridge.PreparedReferenceGPUContracts`: full-installed-repo forest test, **no OpenGL requirement**, checks prepared simulation authority fingerprint unchanged and tree/ground read-only projection.
- Existing G1–G4 and M2/G8 tests preserved. Fast Gate executes short new pure tests on Linux and prepared fixture test in the Windows smoke job. The **manual** native OpenGL workflow also attempts both the original shader probe and the new visual arena, capturing driver info, render times and PNGs.

## GPU-first completion bar

1. Inspect native Windows PNGs for full-day and all-weather lighting, shadow placements, canopy overhang, smooth motion, no artifacts around sight/fog boundaries, fade radius, tree art quality and camera steadiness. Obtain approval before shipping a release.
2. Benchmark repeated warm 720p/1080p at dense trees: p50/p95/p99 render frame, GPU draw calls, texture memory and first-frame uploads; do not infer FPS gain from Linux pure or SDL dummy runs.
3. Move the actual WORLDSEED UI, interactive commands, player/collision authority, real saved-world snapshot, NPC visibility and interior/roof ownership into this GPU window through explicit adapters, then run old-save reload, harvesting, room/stealth, resize/alt-tab and 2-hour soak before switching the launcher.
4. Until these gates are passed, leave the old software executable usable as the prior release while making the GPU visual playtest the graphics-development default.
