# W3 exterior shells and separate Windows GPU test candidate

Date: 2026-10-16 UTC. Canonical main baseline: `d3ac47c`. Previous code checkpoint `33a6a849` passed Fast Gate 38833530616 (7/7). Read this after the W2 Action Hub/context handoff; do not restart W1/W2.

## Delivered work unit

- First W3 slice: read-only exterior shell/roof and independent visible door artwork from existing physical building plans. Local per-cell shell lookup, at most 64 buildings, exact current-sight pixel clips and bounded source textures reuse existing art/geometry contracts. Closed roofs remain opaque; no private NPC, creature, fire, floor, room or inventory is admitted. Shell cells stay outside action-authorized ground cells. Opening/painting a door does not grant access. Interiors, door interaction and roof fade are still unfinished.
- Terrain resolution now follows the existing VisualRegistry: all 41 canonical terrain definitions use current art, including water/coast/cave updates. Namespace-safe physical-tag fallback supports new ground terrain; missing/unknown hard features use explicit unknown art rather than silently becoming forest. Forest uses forest-floor artwork beneath independent trees.
- Live brightness now copies the existing environment LightingState ambient factor. Seasonal day length and storm/cloud state remain engine-owned. Prepared visual preview retains its independent sun control; it is a visual arena.
- Explicit synthetic gameplay QA: `--prepared-scene forest|camp|village_street`, optional `--qa-weather clear|cloudy|rain|storm|snow|fog`, `--qa-season spring|summer|autumn|winter`, `--qa-time noon|night|sunrise|sunset`. These flags are rejected for normal world startup. Season is set before fixture resource preparation. Fixed fixture weather supplies the same weather provider to command systems and capture, never a renderer-only gameplay override. Natural production weather currently emits no snow; snow coverage here is explicitly synthetic.
- Separate `run_worldseed_gpu.py` and `windows-gpu-candidate.yml` create a Windows x64 one-directory executable, all engine modules/data/art/shaders, four batch launchers, exact commit identity and local startup/context logs. Python is not required on the test PC. The legacy launcher is unchanged. This is a temporary-session test candidate: existing saves are never opened; progress is discarded on exit.

## Validation and evidence

Focused contracts cover production-plan village capture, read-only fingerprints/no database queries, exact partial-sight shader pixels, courtyard/privacy/door identity, all-terrain catalog resolution, seasonal QA resource preparation, authoritative lighting, command revalidation and executable packaging. Existing W1/W2 input/UI/resource tests and full legacy reference captures are retained. Final bounded runs passed **94 tests**: 59 authority/build/environment contracts plus 35 renderer/legacy compatibility cases. Compileall and whitespace checks passed.

Real single SDL-window captures were collected locally using Mesa llvmpipe OpenGL 4.5: winter forest snow and autumn village rain. This is Linux **software rendering**, not Windows hardware evidence or a speedup claim. CPU frame/submission timings are not GPU completion timings. New tree shadows remain static contact art; rain/canopy/roof shelter and true directional shadows are W4 work.

The Windows packaging workflow runs the actual frozen EXE selfcheck and bounded camp/rain render attempt. Only a precisely observed OpenGL version below 3.3 with a clean capability-rejection exit can be classified as an unsupported hosted driver. Access violations, missing imports/assets and unknown native failures fail the packaging smoke. Packaging success on GDI Generic 1.1 is explicitly not rendering success. The previous hosted native run 38833104840 exposed only this unsupported driver.

Publication CI and artifact links will be recorded below after actual outcomes are reviewed.

## Test build use

Download the executable artifact from the [Windows GPU candidate workflow](https://github.com/ReleMai/WORLDSEED/actions/workflows/windows-gpu-candidate.yml), extract the complete folder, keep `_internal` beside `WORLDSEED_GPU.exe`, then double-click one launcher:

- `PLAY_GPU_NEW_WORLD.bat`: current engine normal temporary new-world startup.
- `PLAY_GPU_CAMP_RAIN.bat`: prepared camp, autumn sunset rain, authoritative commands.
- `PLAY_GPU_VILLAGE.bat`: prepared production-plan village, winter noon snow.
- `PREVIEW_GPU_WEATHER.bat`: visual-only forest with F weather, 1–4 seasons, brackets sun and T torch.

A desktop OpenGL 3.3+ hardware driver is required. On a real Windows machine, test movement/collision, Enter actions, Tab Console, mouse selection, harvest/pickup, focus loss, resize, exit and a sustained session. Retain screenshots plus `logs/*.json` and local console logs. Nothing uploads automatically.

## Next work

Finish W0/W2 native-driver interactive acceptance; extend W3 through existing authoritative door/portal/interior visibility and full inventory/crafting/storage/dialogue/combat UI. Preserve closed-room privacy until each path has tests. Continue W4 directional shadows, broader occluded fueled lighting and weather shelter. W5 saved-world acceptance, recovery/device matrix/packaging hardening and sustained performance remain promotion gates. This executable includes the current engine source and assets but does not expose every legacy UI or promise complete game parity.
