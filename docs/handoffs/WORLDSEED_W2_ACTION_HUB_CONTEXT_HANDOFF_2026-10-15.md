# WORLDSEED — W2 outdoor Action Hub, HUD and current-context bootstrap

**Date:** 2026-10-15 (America/New_York). Canonical repository: `ReleMai/WORLDSEED`, `main`.
**Previous validated checkpoint:** implementation `265ba11`, documentation `59bb754`; Fast Gate #38754472201 passed 7/7. This unit extends that implementation; do not restart W1.

## Implemented

- `worldseed/presentation/gl_context.py`: inspect the already-current SDL/native OpenGL context, persist and flush dependency/SDL/raw GL evidence before entering ModernGL, reject missing/unsupported desktop GL, then wrap the same context. Windows uses explicit `opengl32.dll` detection through glcontext rather than ModernGL's failing first-use `DefaultLoader` route. Linux GLX uses its discovered soname; an existing SDL EGL context uses an explicit function table from discovered EGL/GL sonames. No standalone/shared context or extra window is created.
- `tools/worldseed_gl_diagnostics.py`: compare default/explicit detection in isolated, bounded faulthandler child processes. Preserve child exits, stdout/stderr, preflight and JSON even if one child crashes. It diagnoses startup and does not certify hardware or performance.
- All three GPU entrypoints now use the common bootstrap: the standalone probe, prepared visual arena and actual gameplay candidate. Optional `*.context.json` accompanies reports; diagnostics print before native calls even without a file path.
- `worldseed/ui/gpu_gameplay_actions.py`: immutable, bounded Action Hub rows from W1's authorized snapshot. Selection re-captures the current prepared view and checks player origin, elevation, proximity, exact terrain/resource identity and harvest stage before one existing `GatherCommand`, `PickupCommand`, `MoveCommand` or `WaitCommand`. Tool requirements, collision, loot, time and depletion remain engine decisions.
- `worldseed/ui/gpu_gameplay_session.py`: shared `NavigationStack` routes for Enter Actions, Interact/Harvest/Pickup/Step, Tab World Console, Character/Inventory/Health, Local/Inspect, System/Controls and Pause. Escape pops exactly one child while retaining parent selection/scroll. WASD never selects menus. Opening UI/focus loss clears held movement and pauses the existing realtime driver; closing UI discards time spent reading.
- `worldseed/presentation/gl_gameplay_ui.py`: GPU HUD/menu rendering after the atmosphere pass in the same window/context. Shared `MenuRow`, wrapping and layout helpers feed immutable hit regions. Small font/panel textures use bounded caches; no full software world frame or second event pump is introduced. Explicit UI chrome blocks pointer fall-through. World left-click only selects an admitted cell; right-click opens Actions. Choosing an action is the command boundary.
- The gameplay tool now supports mouse-wheel zoom/record paging, actual resized viewport dimensions, paged owned inventory, current vitals/time/selection and canonical command feedback. Inventory can page through more than 2,048 owned records without overfilling an overlay frame. Enter/Tab are functional; Esc is pause/back, with explicit Quit for the temporary session.

## Authority and compatibility

No persistent fields, migrations, generation versions, RNG namespaces or legacy-renderer changes. No starter items are granted. Normal startup still creates a temporary new world with the existing empty-inventory rule; prepared scenes remain controlled synthetic fixtures. No existing player save is opened or saved by this candidate.

Hover, selection, HUD, action browsing, health, inventory and help are observational. A stale or private target cannot become authorized because a menu stayed open. Roof/shell/private/interior cells continue to fail closed through the same W1 capture, including explicit action revalidation. UI never updates simulation time or repairs world/index caches. The renderer receives authorized strings and detached commands, not simulation callbacks.

GPU UI limits: 64 commands per frame, 96 source text entries / 4 MiB source cache, 8 MiB UI GPU texture bank, bounded row/string/geometry contracts. Font surfaces are small cached UI assets; gameplay world imagery remains GPU-resident. No growth policy or prior engine optimization was removed.

## Validation completed locally

- **128 unique affected tests passed**: 59 context/UI/action/session/window/input/live-view/navigation checks plus 69 direct GPU bridge, weather, art, projection, movement, combat, realtime and full legacy reference-scene regressions. Compileall and whitespace checks passed.
- A dependency-isolated CI-like run passed; optional ModernGL/pygame rendering checks skip explicitly where those dependencies are absent. Real EGL and pygame-font cases passed with dependencies present.
- Real SDL offscreen context/window now opens with the explicit EGL function table. Driver: Mesa llvmpipe, OpenGL 4.5, Linux — **software evidence only**. The earlier default path fails to locate its unversioned `libGL.so`; the new path discovers the actual libraries.
- Actual single-window GPU camp/HUD capture passed at 1280×720. Controlled forest mouse/Enter navigation opened Harvest with no commands, no time advance and an identical authority fingerprint. Confirming once issued exactly one `GatherCommand`, advanced game minute 720→750 and changed the same prepared pine from mature to stump, with canonical wood/bark/bough yields. The QA axe was supplied only by test setup, not production startup. Screenshots were inspected for readable UI, current-sight masking and command feedback.
- Renderer reports remain CPU frame/submission samples. Neither llvmpipe screenshots nor their timings establish Windows hardware performance, production readiness or a speedup.

## CI and reproducible commands

Fast Gate retains all prior coverage and adds the new bounded context/action/navigation contracts. The native workflow remains manual for ordinary graphics work; changes to the two context-bootstrap/diagnostic files also trigger one scoped Windows run to validate the previously observed native crash. The isolated default comparison may reproduce the old failure; it cannot make required explicit real-render probes green. Preflight files are uploaded even on failure.

```powershell
py -3 -m pip install -e ".[gpu]"
py -3 -m tools.worldseed_gl_diagnostics --mode compare --report scratch/gl-context-diagnostics.json
py -3 -m tools.worldseed_gpu_gameplay
py -3 -m tools.worldseed_gpu_gameplay --prepared-scene camp --frames 30 --screenshot scratch/gpu-live-camp.png --report scratch/gpu-live-camp.json
```

**Published implementation:** `76c7e82f33a0ac694ef808ac9a143b14b140396f` on canonical main. [Fast Gate](https://github.com/ReleMai/WORLDSEED/actions/runs/38833104890) is being checked at closeout.

**Windows diagnostic outcome:** [native run 38833104840](https://github.com/ReleMai/WORLDSEED/actions/runs/38833104840) failed the required real-render probe cleanly before ModernGL. Raw WGL metadata reports Microsoft Corporation / GDI Generic / OpenGL `1.1.0`, despite SDL reporting requested 3.3 attributes. Both isolated loaders therefore reject this unsupported current context; neither reaches the previous access violation. This establishes the hosted runner capability limit, not successful Windows 3.3 rendering or proof of every prior crash cause. Forest/camp rendering steps were skipped; no native screenshots or performance samples exist. [Uploaded preflight diagnostics](https://github.com/ReleMai/WORLDSEED/actions/runs/38833104840/artifacts/12017693557) preserve the evidence. A real Windows OpenGL 3.3+ hardware driver is still required.

**Resize follow-up:** gameplay and preview screenshot reads now specify the actual viewport instead of relying on cached default-framebuffer dimensions. An actual EGL framebuffer regression verifies both capture paths at 320×240 from a 640×480 backing target, including pixel orientation. All 13 UI/window tests passed after this fix; the total above includes the new unique test.

## Remaining roadmap gates

- W0/full W2: actual Windows driver evidence and interactive WASD, mouse, focus, resize, alt-tab and longer playtest acceptance. The hosted runner now rejects its observed OpenGL 1.1 context cleanly; hardware-driver initialization and rendering remain unvalidated.
- W3: exterior building/roof rendering, authoritative indoor wall/room/light visibility, doors/portals, full inventory/crafting/storage/dialogue/combat screens and complete game UI. Only the bounded outdoor Action Hub/basic readouts are delivered here.
- W4: true directional actor/tree shadows, wall/roof-aware broader lights, rain/canopy/roof shelter and environment polish. Tree shadows are still authored contact sprites. Fire glow remains within its admitted source cell.
- W5: live-save acceptance, packaging/fallback/device-loss handling, native hardware/device matrix and sustained performance/soak gates. Keep the legacy/default launcher unchanged until promotion gates pass. G3 resource spacing remains deferred and versioned.

The next implementation should extend this event/navigation/rendering boundary; do not create another movement, visibility, resource or UI-navigation authority.
