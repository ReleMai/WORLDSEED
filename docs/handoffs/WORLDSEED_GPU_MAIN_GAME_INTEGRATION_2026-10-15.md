# GPU main-game integration — persistent playtest build

Date: 2026-10-15 (America/New_York). Canonical baseline `400b5d5`. This supersedes the previous temporary-session candidate as the primary GPU launch path.

## What changed

`WORLDSEED_GPU.exe` and `PLAY_WORLDSEED_GPU.bat` now run **worldseed.app.main**, not tools.worldseed_gpu_gameplay. The real New Game / Load Game startup, normal world generation, authoritative run_game loop, free movement, realtime, all existing command/menu handlers, autosave, Pause/Save and Save & Quit are shared with the main game. `python run_worldseed.py --gpu` selects the same backend from source. The old default/legacy launcher is preserved.

New `ui/gpu_terminal.py` subclasses the existing UI backend but owns one SDL OpenGL window. Its local pygame proxy redirects the existing menu flip/update calls to GPU composition; it never globally patches pygame. Existing inventory, crafting, storage, dialogue, building, combat, map and management screens therefore use the established commands/navigation instead of a second gameplay implementation. World presentation is replaced: live snapshots feed ModernGL terrain, resources, actors, buildings, objects and atmosphere. No software world frame is generated/uploaded.

The compatibility UI surface contains UI chrome/menus and a transparent world hole. `gl_ui_surface.py` keeps one bounded GPU UI texture and fixed quad. UI changes upload full/dirty rectangles; idle weather reuses the uploaded texture. Retained copies restore raw RGBA so dismissed panels erase correctly; drawing targets keep alpha blending so font glyphs remain readable. Real capture exposed and fixed a black-glyph bug during this unit. Maximum UI storage is one 3840×2160 RGBA texture, independently bounded from world textures.

GPU world coverage now includes non-oak/pine resource artwork, player structures/public roofs, containers, loose items, crops, settlement roads/fences/fixtures, carcasses, tracks and discovered animal homes, captured from bounded local state. There are no global world/actor scans or new collision/resource authorities. Public roof admission remains separate from floors, resources and actors.

`gpu_interiors.py` consumes authoritative indoor positions, walls, furniture, stairs, piles and permitted actors. Conservative whole-rectangle wall visibility keeps occluded rooms black; shared indoor light sources/detection control visibility and illumination. Outdoor weather is suppressed indoors. Stable admitted object IDs feed existing interior commands. No indoor plan preparation, terrain realization or save migration occurs in capture.

Keyboard, mouse targets, timed actions and navigation remain the main game's. Focus loss clears movement and pauses its existing realtime driver. GPU pointer admission rejects currently hidden/remembered cells before opening context/target menus. Resize preserves the GL context and targets; camera/interaction coordinates share the fractional transform. F12 saves a local screenshot.

## Saves and launching

Extract the complete new executable artifact, then run **PLAY_WORLDSEED_GPU.bat**. `PLAY_GPU_NEW_WORLD.bat` is a compatibility alias to that same real main game. Use New Game or Load Game normally; progress is persistent. Frozen saves/logs live in `%LOCALAPPDATA%\WORLDSEED\saves` / `logs`, surviving replacement of the extracted build folder. Source runs retain ordinary current-directory saves. Existing format and stored worldgen/resource/hydrology versions remain unchanged. Copy a backup of a previous `.db` save into the frozen save folder with WORLDSEED closed to test loading; keep the original.

Prepared camp/village and visual preview launchers remain secondary explicit QA tools. Snow is supported in those controlled inputs; the existing natural WeatherSystem still emits its own established weather kinds. No renderer-driven snow/weather simulation was invented.

## Validation

Final focused runs: **81 integration/authority/packaging tests passed**, followed by **42 renderer/legacy/free-movement/weather compatibility tests**. Compileall and whitespace checks passed. Coverage includes:

- Actual SDL offscreen + ModernGL main-game menus and a single window, including inventory/crafting/Actions/Console/context pages with unchanged authoritative fingerprint.
- Real app.run_game WaitCommand (+10 minutes), normal Save & Quit checkpoint and actual app._load_context database reload preserving position, inventory, vitals, clock, turn and stored versions. Only expensive startup realization is replaced by the prepared simulation in this focused fixture test; this is not a full live-save/hardware soak.
- Shared Enter/Tab/Esc routes, native focus pause, hidden-cell pointer rejection and context-preserving resize.
- Actual entered-interior GPU rendering with outdoor terrain reads forbidden; private-room and wall-light non-disclosure pixel tests.
- Real font, alpha blending, dirty erasure and no-upload cached UI redraw; current objects/resources, shell privacy and all previous legacy reference-scene assertions.

Real production startup-menu smoke passed with two presentations; actual main-backend camp, village, inventory, crafting, Actions and interior screenshots were inspected. These use Linux Mesa llvmpipe **software rendering**, not native Windows hardware evidence or a speedup. Main executable CI now separately tests frozen main-menu startup and the secondary QA render attempt. Unknown errors/crashes fail; precisely observed unsupported GL <3.3 can be classified only as capability rejection.

Published implementation `31af3046`, Windows path-equivalence test correction `81dd31bb78c406944d3aeaa8639e1a2e27778971`. [Fast Gate 38842245684](https://github.com/ReleMai/WORLDSEED/actions/runs/38842245684) passed **all seven jobs**. Resource/Homestead 38842007315, Crafting/Discovery 38842007313 and preserved legacy Windows executable 38842007325 also passed on the implementation commit. The previous Fast Gate was superseded/cancelled after the test-only Windows short/long pathname correction; it is not counted as a full green run.

[Download the NEW main-game GPU executable (444 MB)](https://github.com/ReleMai/WORLDSEED/actions/runs/38842245713/artifacts/12021454226). [Windows build run 38842245713](https://github.com/ReleMai/WORLDSEED/actions/runs/38842245713) succeeded: actual frozen selfcheck passed; the real main-game startup and secondary QA render independently report `unsupported-hosted-driver-rejected` for the hosted Microsoft GDI Generic OpenGL 1.1 context. No Windows render screenshots/performance are claimed. [Frozen build/context evidence](https://github.com/ReleMai/WORLDSEED/actions/runs/38842245713/artifacts/12021741743). Download ZIP SHA256 `24486b10f3e95da17f314268d7c57d1fc83b616f8c360c92a72f2502aa7364a1`; artifact retention 30 days. The older `2eaf116` artifact defaults to a temporary candidate; use this replacement for main-game playtesting.

CI precision: Linux contracts passed; actual SDL/EGL main-window and shader checks skip explicitly on the hosted image because EGL is absent. Those same real graphics checks passed locally with llvmpipe. A green CI package/contract run is not proof that Windows OpenGL 3.3 hardware rendered the game.

## Remaining acceptance/polish

The main application is now connected; broad human playthrough and native Windows hardware acceptance remain necessary. Contact shadows are still contact artwork, not directional shadows. Wider outdoor light occlusion, canopy precipitation shelter, device loss/fallback, sustained profiling/soak, and comprehensive old-save/user-UI acceptance remain open. Interior visibility is deliberately conservative at wall edges. Keep the preserved legacy executable available and do not claim production readiness/performance superiority from software captures or a green package build.
