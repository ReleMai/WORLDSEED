WORLDSEED WINDOWS x64 GPU CANDIDATE - TEST BUILD

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
PLAY_GPU_NEW_WORLD.bat: normal engine startup into a temporary new world.
PLAY_GPU_CAMP_RAIN.bat: synthetic camp; autumn rain at sunset; real commands.
PLAY_GPU_VILLAGE.bat: synthetic production-plan village; winter snow at noon.
PREVIEW_GPU_WEATHER.bat: visual-only forest; F weather; 1-4 seasons; [/] sun;
T torch; WASD moves the preview camera only. No gameplay commands in preview.

GAMEPLAY CONTROLS
WASD/arrows move; Shift sprint; Enter Actions; Tab World Console; Esc pause/back.
Left click selects an admitted cell; right click Actions. Wheel zooms/pages.
P pickup; period waits. F12 captures the current window to scratch/gpu-gameplay.png.
Use the pause menu to quit. This candidate uses one GPU window.

INCLUDED AND LIMITS
Current engine data/art/shaders; seasonal layered trees, terrain, canopy fading,
contact shadows, day/night and warm lighting, fog/clouds/rain/snow. Live gameplay
reads authoritative simulation weather, visibility, resources and movement.
Prepared QA environments are synthetic tests, not natural-world generation.
Contact shadows are not dynamic directional shadows. Complete UI, crafting,
storage/dialogue/combat screens, indoor acceptance and save/load remain work.
The candidate never opens existing player saves. Temporary progress is discarded
when it exits. The legacy game launcher remains separate and unchanged.

DIAGNOSTICS
The launchers retain stdout/stderr in logs. Session JSON and *.context.json
capture current driver/bootstrap evidence. Startup errors also produce *.error.log.
Logs stay local. Nothing is uploaded automatically. Share only files you choose.
CPU timing reports are not GPU completion or proof of a speedup. Check GPU_BUILD.json
for the exact canonical main commit. Run WORLDSEED_GPU.exe --selfcheck to verify
bundled imports/data/art without opening a window, starting a world or loading saves.

Additional QA example (Command Prompt in this directory):
WORLDSEED_GPU.exe --prepared-scene forest --qa-weather storm --qa-season summer --qa-time night
