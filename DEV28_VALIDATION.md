# RC14 Dev28 — WORLDGEN v8 physical climate and weather presentation

Scope: Phase 3 physical climate circulation plus climate-driven local weather,
wet terrain, cloud shadows, rain animation and day/night presentation.

## Implemented

- Added `worldseed/world/climate_v8.py`.
- V8 temperature/precipitation now derive from latitude-style climate belts,
  maritime influence, continentality, prevailing winds, altitude, orographic
  lift and leeward rain shadow.
- Added humidity and wind-strength read fields.
- V8 `sample_fields()` now consumes physical climate directly; v1-v7 remains
  on the frozen legacy path.
- Existing hydrology/environment/resource consumers therefore see v8 physical
  precipitation without a second climate authority.
- Reworked v8 weather into moving deterministic two-hour weather cells driven
  by local physical climate and prevailing wind.
- Added cloud cover, rain, storm intensity, fog, humidity, recent-rain wetness,
  wind vector and wind speed.
- Rain now waters crops and suppresses realized fire.
- Added season-aware dawn/day/dusk/night lighting read model.
- Added procedural pygame weather art: terrain-group wet textures, soft cloud
  shadow masks, animated rain streaks, ground splashes, fog haze, dark night
  grading and local fire glow.
- Weather visual animation is wall-clock-only presentation; authoritative
  weather remains seed + game-time + coordinate derived.
- Added weather status to the local sidebar.
- Added deterministic climate/weather/lighting tests and a multi-seed climate
  audit utility.

## Compatibility

- `WORLDGEN_VERSION` remains 8 for new worlds.
- Explicit v1-v7 generators retain their old moisture/temperature/elevation
  paths and existing saves remain pinned to their stored `worldgen_version`.
- Save schema is unchanged.
- Hydrology remains version 1 until Phase 4.
- Renderer weather effects are observational and never modify terrain,
  discovery, weather or clock state.

## Required executable validation

The connected GitHub environment does not provide the full executable private
checkout, so the complete test/render suite is not claimed as run here.

```bash
python -m unittest \
  tests.test_worldgen_v8_phase2 \
  tests.test_worldgen_v8_topography \
  tests.test_worldgen_v8_climate_weather \
  tests.test_worldgen_v8_promotion \
  tests.test_rc14_hydrology \
  tests.test_rc14_environment \
  tests.test_rc14_pygame_behavior

python tools/audit_worldgen_v8_climate.py
python tools/audit_worldgen_v8_phase2.py
python tools/audit_worldgen_v8_startup.py
python tools/audit_traversability.py
python tools/bench_pregeneration.py
```

Visual validation should explicitly inspect clear/cloudy/rain/storm/fog states
at dawn, midday, dusk and night, including zoom changes, hover redraw and idle
rain animation.
