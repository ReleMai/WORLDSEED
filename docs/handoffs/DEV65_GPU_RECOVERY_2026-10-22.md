# Dev65 recovered on the GPU main game

Baseline: canonical main `7f5dc8ee663ea60d9f47d5b9f6d9c23017a1684f`.
This supersedes the conflicted Dev65 PR #72 as an implementation baseline. Its
historical branch remains a reference; it was not merged into current main.

## Player behavior

- Space and the GPU HUD Pause control toggle ambient world time. HUD buttons
  select 1x, 2x or 3x. Selecting speed preserves an explicit pause. Walking
  returns accelerated time to 1x without repeatedly resetting the 1x clock.
- Explicit pause blocks locomotion, including retained-panel WASD and distant
  click-to-pickup walking. Deliberate work and waits still spend their committed
  game minutes. Combat, focus and nested conversation/menu holds remain separate
  owners; releasing one cannot erase an explicit pause or replay missed time.
- Space also controls time inside retained inventory, storage and crafting
  panels rather than confirming the selected item. Dialogue/text entry retains
  its existing semantics. WASD remains movement; Escape remains menu/back.
- GPU timed actions show elapsed/total game minutes and percentage above the
  player. Retained crafting windows remain visible. Resource art for committed
  GatherCommand work fades using at most eight detached, previously admitted
  sprite parts, reprojected on resize/zoom and clipped to old and current sight.
  No ghost becomes a target, memory record or physical object.
- Successful active work accounts for stamina, wounds, relevant tool quality
  and outdoor rain/wind. Existing owning-system skill reductions are retained
  once; additional relevant skill scaling is used only where absent. Invalid
  commands retain their old costs; peaceful container transfers remain instant.
- V8+ weather now has deterministic six-slot/twelve-hour fronts, longer dry
  spells and rarer storms. Wetness persists after rain. A per-instance 512-entry
  cache returns detached samples. Pre-v8 weather remains exact legacy behavior.

## Modules and authority

`sim/realtime.py` owns time controls and bounded pumping. The app installs that
ephemeral driver in the backend for read-only HUD state and routed input.
`sim/work_duration.py` owns the bounded adjustment formula; engine call sites
apply it after successful work without duplicating outputs or elapsed time.
`systems/environment.py` owns weather; GPU/legacy rendering only reads samples.
`ui/gpu_hud.py`, `gpu_terminal.py`, shared progress hooks in `pygame_terminal.py`,
and `presentation/action_resource_fade.py` own visual feedback.

Engine/package versions are Dev65; WEATHER_VERSION is 3. No save schema,
geography, resource placement, settlement-plan or collision version changed.
Clock speed/pause, visual fades and weather cache are ephemeral. V8+ future
weather intentionally changes under the new algorithm, including existing
worlds; geography and saved state are not regenerated. New RNG namespace:
`weather-v8-dev65-front`.

## Fast Gate repairs

The Linux contract job now installs pygame-ce for CPU sight-mask rasterization.
Window-loop mocks delegate pixel surfaces to real pygame while retaining fake
SDL/GL. Live-scene tests distinguish original authorized cell IDs from dim
transition backing draws, asserting both exact sets and shared bounds/pixels.
Native interior fixtures budget for sight masks; the floor-crack geometry test
isolates optional edge feathering while dedicated native mask/privacy tests
retain real masks and verify unknown pixels remain black.

New clock/work/weather/route/feedback contracts run early in Fast Gate and before
Windows freezing. The actual OpenGL action test runs with existing Linux native
main-window checks. GPU package triggers cover the new runtime modules.

## Validation

- Reproduced the original ground-count, missing-pygame and fake-Surface errors.
- Repaired gate/native privacy and raster suite: 144 tests passed without skips.
- Successful work/crafting/water/interior/construction/fishing/salvage suite:
  59 tests passed. Clock/combat/resource and weather batches also passed, with
  overlap; counts are not cumulative unique totals.
- Final combined GPU main game, saved-world reload, package, all new Dev65
  modules and affected HUD routing: 56 tests passed in 29.3 seconds, no skips.
  Actual SDL offscreen/OpenGL Mesa llvmpipe rendered departing sprites, player
  layering, the work counter, retained panels, and resized 640x480 output.
- Compilation, whitespace and workflow YAML checks passed. Screenshot captures
  were inspected at gameplay scale. Independent review found no blockers.
- An overly broad legacy UI compatibility selection reached its 180-second
  deadline during repeated generated-world setup without an assertion failure;
  it is not claimed complete. The directly affected routing/HUD/native classes
  and separate movement/conversation regressions passed. No longer rerun was used.

## Limits and next dependency

This is targeted development validation, not full release hardening or native
Windows hardware/performance acceptance. Check the exact published SHA in Fast
Gate and the Windows GPU candidate workflow; packaging alone is insufficient.
Play the current candidate with a representative existing save and viewport.

Harvest fade currently covers GatherCommand resource work, not crop HarvestCommand
or instant loose-item pickups. Salvage minigame durations remain with their
existing authority so its saved session/completion reports remain consistent.
Existing GPU viewport tile budgets and cadence remain in use; obsolete software
world-render throttling from PR #72 was not copied over the GPU compositor.
Roof/canopy rain interception, fuller physical shadows, device recovery, the
known bootstrap-audit helper fault and full release/long-soak gates remain
separate follow-up work.

## CI fixture closeout and Windows package

Production commit `aa998ab339fb2d36a0905ea69008d2bda533effe` passed the new
Windows Dev65 checks, real saved-world load and frozen GPU packaging. The
[GPU candidate](https://github.com/ReleMai/WORLDSEED/actions/runs/39897283219/artifacts/12476908165)
contains this final gameplay code; run `PLAY_WORLDSEED_GPU.bat` after extraction.
Hosted driver rejection is still not native hardware/performance acceptance.

CI exposed two older partial test simulations in pot discovery and interior
workstations that lacked the actor/duration context now required for successful
work. Their fixtures now supply rested actors, real duration/tool resolution
and neutral exposure while retaining all original input/output/time assertions.
The complete crafting/discovery workflow selection plus workstation module
passed 72 tests in 97.9 seconds. Workflow paths now cover those tests and the
shared work-duration helper. This follow-up changes tests, CI and this handoff
only; the packaged production code above remains current.

## Subsequent continuation

[Dev66](DEV66_GPU_PRECIPITATION_COVER.md) implements the GPU roof/canopy
precipitation interception left open above. Its remaining limitations and next
dependencies are recorded in that handoff.
