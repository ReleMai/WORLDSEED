# WORLDSEED Dev65 — Time controls, work visuals, weather and performance

Branch: `feature/world-speed-actions-weather-performance`
PR: https://github.com/ReleMai/WORLDSEED/pull/72

## Delivered
- Space toggles the live simulation clock; Pause, 1×, 2× and 3× are clickable
  controls on the gameplay HUD. 2×/3× increase the **rate of authoritative
  game minutes**, not animation playback speed. Returning to movement restores
  1×; paused movement is blocked until unpause. No clock catch-up after pause.
- Timed commands render a compact bar anchored above the player, with
  incrementing `+Xm` elapsed game minutes. The old bottom-center progress
  modal is removed.
- Before resource harvest, Pygame captures just the original generated
  resource sprite. It fades that art over the updated environment during the
  authoritative timed action, leaving terrain and player art untouched.
- Successfully storing and taking from ordinary containers costs one
  authoritative minute; invalid transfers stay at zero minutes. Their animation
  is about 0.18 seconds. Theft/lockpicking costs are intentionally unchanged.
- Work-rate scaling adds capped modifiers for player craft/survival skill,
  relevant harvesting tool quality, wound severity, stamina, rain and wind.
  Direct waits, combat and movement are excluded; recipe outputs, save schema,
  and resource yields are unchanged.
- V8 weather now uses multi-hour synoptic fronts, lower rain probability,
  uncommon storms, and persistent wetness. Repeated weather sampling is cached.
  Existing legacy weather remains on its old algorithm.
- Maximized windows now dynamically enlarge display tiles to cap viewport
  world-cell volume near ~1,050 (without affecting simulation coordinates), and
  cap expensive full-screen animated weather redraws to a lower rate based on
  screen area. Weather cache also avoids duplicate climate reads.
- Added `tests/test_game_clock_weather_actions.py` and included in early
  Fast Gate diagnostics. Existing action progress tests remain active.

## Important constraints / follow-up
- Commands still commit resources immediately, then animate world time.
  Interruptible partial work would require future transactional reservation and
  rollback rather than interrupting this atomic game command mid-animation.
- Performance improvements are conservative render-budget controls. For deeper
  speedups, measure frame profiler slices (terrain transitions, settlement
  overlays, sprite scaling, fog surface, weather compositing) on a maximized
  display, then prioritize caches by measured cost.
- New v8 weather front patterns use the same seed/climate but have a changed
  sampling algorithm. This intentionally changes conditions while preserving
  geography/terrain/worldgen seed consistency.
- Verify live UI interactively after workflow tests: Space pause from world and
  inventory, clicking Pause then 1×/2×/3×, walking at 3×, harvesting a tree,
  one-minute container transfer, resizing/maximizing with rain.

Do not merge before required GitHub Fast Gate jobs complete green. Follow the
normal repository rule: merge only validated clean states and keep main canonical.
