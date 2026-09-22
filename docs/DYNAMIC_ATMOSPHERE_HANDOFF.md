# Dynamic atmosphere foundation

## Scope

Clouds now have independently composed silhouettes rather than copies of one rotated image. Each identity uses three to seven irregular textured pieces with independent rotation, aspect, placement and opacity. A shared composited alpha field projects the same silhouette as a softened shadow. Wisps and banks have different proportions; per-particle widths/heights span small puffs through large banks.

Two world-anchored `FieldEmitter`s create deterministic, seed-specific visual particles with different wind advection rates. They form and dissipate over long, staggered lifetimes (6-12 minutes of wall time depending on layer), fading to zero before their next identity appears. Wall time affects only presentation; weather, sunlight and game time remain authoritative frozen samples. Clouds are visual, not persistent simulation entities.

## Modules / extension contract

- `presentation/atmosphere.py`: immutable `WeatherSample` and `EffectFrame`; stateless bounded `FieldEmitter`; ordered `EffectStack` with duplicate-name rejection and clip restoration even on errors.
- `presentation/clouds.py`: cloud shape composition, matching shadows, two layers, bounded source/shape/stamp/frame caches.
- `presentation/weather_fx.py`: existing fog, cloud and rain passes registered in one stack. Both full gameplay and idle rendering call the same `draw_atmosphere` entry point. Lighting and local fire glows keep their previous position before atmosphere composition.
- `ui/pygame_terminal.py`: idle animation asks the registered effects whether a repaint is needed instead of hardcoding each weather type.
- `tools/preview_weather_visuals.py`: G toggles a gallery of twelve distinct shapes; `--gallery --capture <path>` supports headless inspection.

A future effect registers a named ordered callback receiving an `EffectFrame` and returning surfaces (or an empty tuple), plus an animation predicate reading `WeatherSample`. Use a separate emitter namespace and explicit count/lifetime limits for each particle type. This is the extension point for fog motion, hail, lightning/light overlays and smoke; those new phenomena are **not** simulated or activated by this change.

Future weather phenomena must first come from authoritative simulation samples. Smoke must receive immutable samples of known nearby emitters, not scan the world or invent fires. Do not pass Simulation/World into an effect callback. Extend the copied frame/sample contract when additional authoritative inputs are needed. Registration is configuration-time, capped at 32 named passes. Normal layer order is fog 10, clouds/shadows 20, rain 30.

## Determinism / persistence / budgets

No schema, terrain, visibility, worldgen or save changes. No simulation RNG use. New presentation namespaces: `weather-art:cloud-low`, `weather-art:cloud-high`, `weather-art:cloud-piece`. Stable cell/lifetime hashes determine particle identity; viewport movement does not reroll overlapping particles. Render reconstruction does not depend on which screen was opened first.

Each emitter visits at most a 32x32 cell window and emits at most 256 particles; no history is accumulated. Cloud shapes use a 48-entry LRU, scaled cloud/shadow stamps a 64 MiB pixel budget, and composited frames two entries. At close zoom the soft atmospheric field is rendered at half resolution and upscaled once, preserving world footprint without large per-cloud cache churn. In synthetic 1280x720 checks, warm cloud frames averaged 3.5-5.9 ms across tile sizes 16-56; initial source/shape loading measured about 68 ms. This is not a full-game FPS measurement.

## Validation

New tests cover distinct silhouettes, shadow support, reconstructable particle identities, camera-independent placement, lifespan renewal, emitter bounds, immutable samples, composition order, clipping, duplicate registration and exception cleanup. Existing weather/cave/resource visual regressions remain in the targeted gate.

Validation on Python 3.13: 27 targeted atmosphere/weather/art/terrain/render tests passed; the full gameplay frame observational and centered rendering test passed across all zoom limits. Compileall and the visual coverage audit passed. Golden replay passed with hash `0b369fbd04f8fab3ce6a7b295ee942ac369f000d`. The twelve-shape gallery was rendered and visually inspected.

The preceding complete suite ran 330 tests with six failures and one error outside the edited visual logic (not all independently established as baseline). This iteration's full-suite attempt stopped at its 300-second limit, so no complete clean gate is claimed. The earlier run took 97 minutes. Changes remain on the draft branch; no main-branch merge or interactive gameplay verification is claimed.

Known limitation: a changed wind sample changes the analytic drift field immediately; interpolation of changing wind vectors is a future presentation refinement. No fog/hail/lightning/smoke behavior is invented by the rendering foundation.
