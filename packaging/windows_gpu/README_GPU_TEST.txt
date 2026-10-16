WORLDSEED WINDOWS x64 GPU MAIN GAME - TEST BUILD

Download the WORLDSEED-Windows-GPU-CANDIDATE artifact from the successful run:
https://github.com/ReleMai/WORLDSEED/actions/workflows/windows-gpu-candidate.yml
Extract the entire download into a new writable folder. Keep WORLDSEED_GPU.exe,
_internal and these launchers together. Python is not required on the test PC.
Code > Download ZIP contains source and is not this executable distribution.

REQUIREMENTS
Windows x64 with a working desktop OpenGL 3.3+ graphics driver. Update the vendor
graphics driver first. Microsoft GDI Generic / OpenGL 1.1 is unsupported. The
candidate reports unsupported drivers and does not silently switch renderers.
Packaging success is not Windows hardware rendering or performance acceptance.

DOUBLE-CLICK ONE LAUNCHER
PLAY_WORLDSEED_GPU.bat: THE MAIN GAME. New Game, Load Game, full command screens,
autosave and Save & Quit use worldseed.app.main with the new GPU world renderer.
PLAY_GPU_NEW_WORLD.bat: compatibility alias for the same persistent main game.
The following launchers are secondary QA tools, not the main game:
PLAY_GPU_CAMP_RAIN.bat: synthetic camp; autumn rain at sunset; real commands.
PLAY_GPU_VILLAGE.bat: synthetic production-plan village; winter snow at noon.
PREVIEW_GPU_WEATHER.bat: visual-only forest; F weather; 1-4 seasons; [/] sun;
T torch; WASD moves the preview camera only. No gameplay commands in preview.

GAMEPLAY CONTROLS
WASD moves; Enter Action Hub; Tab World Console; Esc pause/back.
The main game retains its shared menus, interactions, text input and save flow.
Use Save & Quit in the pause menu, or close the window through the normal save
boundary. The main GPU backend uses one window for the world and every game UI.
Prepared QA tools retain their separate compact controls shown in those windows.

INCLUDED AND LIMITS
Current engine data/art/shaders; seasonal layered trees, terrain, canopy fading,
contact shadows, day/night and warm lighting, fog/clouds/rain/snow. Live gameplay
reads authoritative simulation weather, visibility, resources and movement.
Prepared QA environments are synthetic tests, not natural-world generation.
The main game uses the existing authoritative command/UI and persistence paths,
including crafting, storage, dialogue, combat and doors/interiors. Contact shadows
remain contact shadows, not dynamic directional shadows. Native hardware acceptance
and a comprehensive visual pass still need testing. The legacy game is preserved.

SAVES
The EXE stores persistent main-game worlds in %LOCALAPPDATA%\WORLDSEED\saves.
This user-writable directory survives replacing the extracted test-build folder.
With WORLDSEED closed, copy a BACKUP of a legacy .db save into this folder to
select it from Load Game. Keep the original backup; this remains a test build.
Source launches retain the normal current-directory saves folder and save format.
Only prepared QA scenes and visual previews discard their temporary progress.

DIAGNOSTICS
Double-click OPEN_LOGS.bat to open the user runtime directory. In File Explorer
you can also paste %LOCALAPPDATA%\WORLDSEED into the address bar and press Enter.
This path is independent of the folder containing WORLDSEED_GPU.exe.

Gameplay crashes write WORLDSEED_CRASH.log at the runtime directory's top level;
newer builds also keep the same full traceback in logs\WORLDSEED_CRASH.log.
The related continuous session log is logs\WORLDSEED_DEBUG_<date>_<pid>.jsonl.
The game can recover to its menu after a session crash, so do not rely only on
the launcher's exit code or on a startup error log to find a gameplay failure.
Startup/uncaught launcher exceptions write logs\gpu-session.error.log.
Session JSON and *.context.json contain driver/bootstrap evidence.
The QA launchers retain stdout/stderr in the extracted folder's logs instead.
When reporting a gameplay crash, attach WORLDSEED_CRASH.log and the newest
WORLDSEED_DEBUG_*.jsonl. These logs may contain local paths and world names.
Logs stay local. Nothing is uploaded automatically. Share only files you choose.
CPU timing reports are not GPU completion or proof of a speedup. Check GPU_BUILD.json
for the exact canonical main commit. Run WORLDSEED_GPU.exe --selfcheck to verify
bundled imports/data/art without opening a window, starting a world or loading saves.
The automated --smoke-main check draws the real startup menu and closes without
selecting a world. Passing it does not certify every gameplay path or GPU hardware.

Additional QA example (Command Prompt in this directory):
WORLDSEED_GPU.exe --prepared-scene forest --qa-weather storm --qa-season summer --qa-time night
