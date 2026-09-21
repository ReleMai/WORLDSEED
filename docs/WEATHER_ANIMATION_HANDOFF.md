# Weather animation handoff

## Scope and behavior

- `worldseed/presentation/weather_fx.py`: world-anchored cloud shadows now drift at pixel resolution with softer layered edges; rain uses stable particle identities, continuous wind-slanted falls and expanding/fading impact rings. Rain phase no longer wraps at 16 frames.
- `worldseed/ui/pygame_terminal.py`: sample lighting targets only on a gameplay render, then interpolate presentation colors over 650 ms. Idle redraw restores an ungraded snapshot before lighting, fire glow, fog, clouds and rain. The final transition frame is painted even in clear weather; viewport borders are restored.
- Initial lighting and returning from underground snap to the current authoritative sample. Interrupted fades start from the current displayed colors.

## Contracts

No simulation, geography, discovery, visibility-radius, save-schema or persistent-field changes. No migration. Wall time drives only visual phase; weather/lighting samples stay frozen between gameplay renders. Existing `weather-art:cloud-field`, `weather-art:cloud-lobe` and `weather-art:rain` deterministic namespaces remain presentation-only. Rain particle identity no longer includes animation phase; splash position comes from the matching drop.

`draw_lighting` keeps immediate rendering by default; optional `elapsed_ms` renders the interpolated colors. `rain_surface` phase is now an unwrapped 33 ms tick.

Cloud and rain caches retain at most two full-size frames each. Synthetic cloud/rain layer cost averaged 5.7 ms at 1280x720 over 30 frames on the development host (not a complete-game FPS measurement).

## Validation

- Four new regression tests cover sub-tile cloud movement and exact camera translation, deterministic rain without the old 16-frame repeat, interrupted/completed lighting fades, and idle clear-weather fading from frozen inputs without world access.
- New tests pass on Python 3.14.2 / pygame-ce 2.5.8 and Python 3.13.5 / pygame 2.6.1.
- Compileall passed. Replay command completed: `0b369fbd04f8fab3ce6a7b295ee942ac369f000d`.
- Synthetic terrain contact sheet reviewed for day/dusk/night/dawn. A live saved-world playtest is still needed for subjective animation pacing.
- Six focused animation/cloud/idle-water tests pass on Python 3.13 (four new tests also pass on 3.14).
- Full discovery contains 326 tests. Broad parallel module runs on 3.14 and 3.13 were not clean: interpreter crashes/SystemErrors occurred in world generation, and the atlas mouse test returned `ATLAS_POI:0` where it expected `ATLAS:drag_start`. These failures are outside the modified code, but are not all proven baseline failures.
- Serial full-suite attempts were stopped before completion after the unreliable broad runs; no full-suite pass is claimed. The Python 3.13 replay module passed both determinism tests.
- Work is synchronized on a separate branch for review, not merged into main. Full clean validation and a live playtest remain release gates.

## Limitations / next dependency

Idle water animation retains its existing weather/night restrictions. This patch changes no water behavior. Rain is a viewport presentation effect and does not introduce roof occlusion or authoritative puddles. Test the effects in a playable world with movement, zoom and repeated wait actions before a release.
