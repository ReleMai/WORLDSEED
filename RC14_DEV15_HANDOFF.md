# WORLDSEED RC14 Dev15 - physical water and swimming

Based on Dev14, including the Q-key and map-hover fixes.

## Play
Extract the ZIP into a new folder and run RUN_WORLDSEED.bat. Use a new world
for the new geography. Move normally into water to wade or swim. Choose
Swimming during character creation, or improve it by swimming. Endurance
reduces exertion. Travel light; swimming against currents costs more.

Deep water is hazardous: strokes and treading consume stamina. Below 20
stamina, entry from dry/shallow ground is refused. Exhausted swimmers can
still move toward safety, but suffer health damage. Resting in swimming
depth does not replenish stamina. Reach wading water, land or a bridge.
Menus and idle visual animation do not advance time.

## Scope and authority
- Worldgen v6 retains v4 continental/climate fields and hydrology v1 drainage.
- Shore distance is estimated from elevation relative to sea level and local
  slope. Ordered zones: wet sandy shore, coastal wading water, shallow ocean,
  shelf, deep ocean. The shelf spans multiple physical cells.
- River classes continue to come from prepared discharge/flow accumulation.
  Streams, wading margins, deeper channels, slope-driven rapids and sandy
  gravel banks materialize from that same plan. Existing fords remain.
- Lakes get freshwater shallow/deep terrain. River mouths have explicit
  brackish nearshore terrain; offshore shelf/deep water stays marine.
- No per-frame or movement drainage solving. Current lookup for swimming is
  prepared-only. River currents affect stroke cost; ocean currents do likewise.
- 12 new terrain IDs are appended; all old content indices stay in place.
- 120 new code-authored terrain textures, smooth depth transitions, restrained
  wavelets, wet shore/gravel bank materials and submerged player/wake rendering.
- Idle waves redraw only cached water rectangles clear of sprites at 6.25 Hz;
  animation is disabled on console/menu screens. No simulation time advance.

## State and compatibility
WORLDGEN_VERSION=6, HYDROLOGY_VERSION=1, SAVE_SCHEMA_VERSION=3.
All v1-v5 saves retain recorded terrain. New art and swimming apply to them;
legacy generic water retains its ambiguous fresh/salt identity. To get the
new physical ocean shelf and river/lake types, create a new world.

Swimming rules live in systems/swimming.py; command effects and vitals remain
in sim/engine.py. Existing player_skills gains swimming (0 when absent).
player_swimming_xp is one bounded optional integer, default 0 for old saves.
Successful strokes grant practice; threshold is 20 + 10 * current level,
maximum skill 10. Round-trip serialization and verifier cover the new field.
No save-schema migration is needed for this additive, defaulted field.
No new simulation RNG namespace: shelf/slope/materialization is deterministic.

## Visual and UI exposure
Terrain names and hover identify water types and wading/swimming; hover shows
estimated stroke effort. Sidebar shows Swimming and Endurance while in water.
The player appears partly submerged with a small wake. Existing character
skill screens and point-buy include Swimming. No new movement hotkeys.
Water-current render metadata is cached with a bounded 8,192-cell limit, keyed
by seed, worldgen version and prepared-domain fingerprint. This avoids stale
currents when prepared plans change.
Art source: tools/build_water_v6.py. Preview source: tools/preview_water_v6.py.
The renderer still uses cells; transitions are feathered, not a polygon mesh.
Headless 1600x900 coastal test: warm rendering improved from about 294 ms
to 74 ms after current caching; idle animation was about 2.5 ms per update.
These are container timings, not Windows GPU/frame-rate guarantees.

## Validation
See DEV15_VALIDATION.md for final results. Focused tests cover ordered coastal
zones, deterministic generation order, legacy water, material coverage,
nearshore-only estuaries, stroke/current costs, practice, exhaustion escape,
rest/wait consequences, bridge safety, blockers, state roundtrip/defaults,
verifier bounds, idle animation and menu isolation. Existing hydrology tests
exercise repeatability, cache rebuilding, prepared-domain seams and legacy
fingerprints. Real rendered previews are in artifacts/dev15-*.png.

## Limitations and next dependency
Depth is categorical rather than a meter-accurate bathymetry simulation.
Sea-level height divided by local slope approximates shelf distance; this is
not an erosion solver. Salinity is categorical, with no tidal mixing cycle.
Currents affect effort and visual flow; they do not physically displace actors.
No boats, diving or buoyant equipment are implemented. Swimming progression
currently belongs to the player, not autonomous NPC navigation. The riverbed
is represented by shallow-water material, not an independently excavatable
underwater elevation layer. Next useful work: continuous shoreline contours,
water-aware NPC pathfinding and buoyancy/equipment support.
