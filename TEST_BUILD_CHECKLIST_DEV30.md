# WORLDSEED RC14 Dev30 Test Build Checklist

Build target: **WORLDGEN v8 / Hydrology v2 / Hydrology Morphology v2**

Build source commit: **67b2d3d0c7c5279f9a59c959f2cfb0916c5cd864**

This checklist is the manual acceptance gate before WORLDSEED moves deeper into
Phase 4 and then Phase 5. Test on a **new world first** so the build uses the
current v8/v2/v2 generation contracts.

## 1. Startup and basic stability

- [ ] Launch `RUN_WORLDSEED.bat` and confirm the graphical client opens.
- [ ] Create a brand-new world with a seed you can record.
- [ ] Confirm the world-generation/loading screen completes without crashing.
- [ ] Confirm the game does **not** open directly into the pause/Esc menu.
- [ ] Move with WASD for several minutes and verify there is no movement queue,
      overshoot, major hitching, or input lag.
- [ ] Zoom the local view in and out repeatedly.
- [ ] Open/close Inventory, Crafting, Build, Health, Map, Actions, World, Look,
      Help and Pause using mouse controls.
- [ ] Save, quit, reopen the same world and verify your character position and
      visible terrain are unchanged.

## 2. WORLDGEN v8 geography

Test at least **3 new seeds**.

- [ ] Continents/coasts look irregular rather than like noise blobs or grids.
- [ ] Mountain chains appear as connected ranges instead of isolated circular hills.
- [ ] Valleys, basins, plateaus and uplands are visually distinguishable.
- [ ] Terrain transitions do not form obvious straight chunk/domain seams.
- [ ] Caves appear in terrain that makes physical sense.
- [ ] Spawn locations are on traversable land with useful nearby resources.
- [ ] No obviously impossible inland ocean strips, square lakes, or repeated geometric patterns are visible.

Record seeds that produce especially good or bad geography.

## 3. Physical climate and rain shadows

Explore opposite sides of mountain ranges when possible.

- [ ] Wet/windward mountain regions generally support wetter terrain.
- [ ] Some leeward regions are visibly drier, demonstrating rain-shadow effects.
- [ ] Coastal regions feel more moderate/moist than deep continental interiors.
- [ ] Climate transitions are broad and gradual rather than changing every tile.
- [ ] Forest/scrub/grass/tundra placement looks compatible with local climate.
- [ ] No obvious climate seams appear at chunk boundaries.

## 4. Dynamic weather visuals

Play long enough to observe multiple weather states.

### Clouds
- [ ] Partly cloudy conditions cast irregular moving shadow patches over terrain.
- [ ] Cloud shadows are soft and organic, not hard circles/squares.
- [ ] Cloud movement direction looks coherent.
- [ ] Heavy cloud cover darkens the world more than light cloud cover.
- [ ] Clouds do not darken menus/UI to the point of poor readability.

### Rain
- [ ] Rain streaks are visibly animated while gameplay waits for input.
- [ ] Wind changes the apparent slant/direction of rainfall.
- [ ] Rain produces visible ground splash effects.
- [ ] Vegetation, soil, sand/floodplain and stone respond differently to wetness.
- [ ] Ground remains damp for a while after rain ends instead of instantly becoming dry.
- [ ] Wet stone has a subtle damp sheen without looking metallic.
- [ ] Rain over water does not apply inappropriate land-wetness shading.
- [ ] Heavy rain/storms reduce visibility appropriately.
- [ ] Weather animation does not cause noticeable input lag or frame hitching.

### Fog/storms
- [ ] Fog produces visible haze but the game remains playable.
- [ ] Storm conditions look darker/heavier than normal rain.
- [ ] Rain visually and mechanically suppresses active fires when you can test that interaction.

## 5. Dawn, day, dusk and night

- [ ] Dawn transitions into daylight without a sudden brightness jump.
- [ ] Dusk gradually darkens the local world.
- [ ] Night is meaningfully dark.
- [ ] Night uses a cooler blue/black appearance rather than a flat black screen.
- [ ] UI/menu text remains readable at night.
- [ ] Campfires/light-producing scenes visually stand out at night.
- [ ] Cloudy daytime is dimmer than clear daytime.
- [ ] Rain/storm darkness combines correctly with time-of-day lighting.
- [ ] Water, terrain overlays, character sprites and hover highlights do not become strangely bright after night/weather overlays.

## 6. Hydrology v2 — rivers and drainage

Explore rivers on at least **3 different seeds**.

- [ ] Small streams appear upstream of larger rivers where appropriate.
- [ ] Tributaries visibly merge into larger channels.
- [ ] River size generally increases downstream.
- [ ] Rivers follow valleys/low terrain rather than climbing ridges.
- [ ] Wet regions produce more convincing headwaters than dry rain-shadow areas.
- [ ] Major rivers are less common and wider than small streams.
- [ ] Rivers do not abruptly stop at chunk/domain boundaries.
- [ ] No obvious straight grid-aligned river networks dominate the map.
- [ ] Floodplains/wetlands appear near suitable low-gradient rivers.
- [ ] Riverbanks look distinct from coastlines and open-water shores.
- [ ] Rapids appear on steeper river reaches.
- [ ] Rapids do not appear excessively on flat floodplains.
- [ ] Fords appear on physically reasonable shallow/narrow reaches rather than obviously random positions.
- [ ] Deep/major river cores remain meaningfully harder to cross.

## 7. Hydrology Morphology v2 — new Dev30 features

These are the most important Phase-4 visual checks.

### Multi-point/meandering channels
- [ ] Mature low-gradient rivers form broad curves/S-bends.
- [ ] Steep mountain streams stay tighter/straighter.
- [ ] Curves are continuous and do not create broken water pixels.

### Braided rivers and islands
- [ ] Find at least one braided reach across your test seeds if possible.
- [ ] A braided river visibly splits into two water threads.
- [ ] The threads rejoin naturally downstream.
- [ ] Land between braid threads appears as a believable river island.
- [ ] The island uses surrounding/base terrain rather than a fake overlay.
- [ ] Water current animation follows both braid geometry and downstream flow.
- [ ] Braid entrances/exits do not create blocked one-cell artifacts.

### Oxbows/meander scars
- [ ] Find a mature floodplain with an oxbow if possible.
- [ ] Oxbow water is detached from the active river channel.
- [ ] The oxbow shape curves/orients with the parent river rather than always appearing horizontal.
- [ ] Oxbow shallows blend correctly into surrounding floodplain/wetland.
- [ ] Oxbows do not appear in steep mountain terrain.

### Gorges
- [ ] Steep rugged river reaches can produce rocky gorge margins.
- [ ] Gorge banks visually read as confined terrain.
- [ ] Gorge rivers/rapids remain continuous through the confined reach.
- [ ] Gorge rock does not create impossible isolated walls or trap the player in otherwise traversable terrain.

## 8. Water animation/current consistency

- [ ] River animation flows generally downstream.
- [ ] Braided threads do not visually flow against their terrain path.
- [ ] Rapids animate differently/intensely enough to read as faster water.
- [ ] Ocean/coastal current animation still works.
- [ ] River/ocean meeting areas do not flicker between incompatible visuals.
- [ ] Zooming does not reverse or break water animation.

## 9. World map / atlas consistency

- [ ] Open the world map after exploring several terrain types.
- [ ] Terrain shown on the map corresponds to what is actually present locally.
- [ ] Rivers/lakes/coasts visible locally are represented coherently on the map.
- [ ] Moving the cursor over the map never reveals or flashes the gameplay screen.
- [ ] Pan and zoom repeatedly without corruption or major lag.
- [ ] Known villages/cities/camps/caves/sites remain in sensible locations.
- [ ] Unexplored terrain is not falsely revealed.

## 10. Save/load and compatibility

### Current test world
- [ ] Save beside a river/braid/oxbow/gorge.
- [ ] Reopen the save.
- [ ] Confirm the exact river path and surrounding terrain did not move.
- [ ] Cross chunk boundaries after reload and confirm river continuity.
- [ ] Confirm explored map terrain remains consistent after reload.

### Older save, if available
- [ ] Back up the save first.
- [ ] Open a pre-Dev30 world.
- [ ] Confirm it loads without regeneration errors.
- [ ] Confirm existing river/coast geography has not visibly shifted.
- [ ] Save/reopen once and verify it remains stable.

## 11. Performance / regression checks

- [ ] Hold movement across several prepared chunks and watch for stutter.
- [ ] Travel alongside a large animated river during rain.
- [ ] Zoom while rain/cloud shadows/wetness/night effects are active.
- [ ] Hover many tiles rapidly and confirm no map/gameplay flashing.
- [ ] Leave the game open during animated rain for several minutes and look for memory growth or progressively worse performance.
- [ ] Open crafting and inventory repeatedly; confirm neither crashes.
- [ ] Press Q only when you intend to save/quit; confirm it no longer crashes.
- [ ] Generate another new world in the same session and confirm startup remains reliable.

## 12. What to report back

For every problem, record:

- seed;
- save name;
- approximate world coordinates if visible;
- screenshot;
- what you were doing immediately before the issue;
- whether it reproduces after save/reload;
- whether it occurs at all zoom levels;
- whether it is graphical only or affects movement/gameplay.

### Phase-4 acceptance

Do **not** move to the next major world-generation phase if any of these are repeatable:

- rivers break or jump at chunk/domain seams;
- saved river geography changes after reload;
- new weather/night rendering causes movement or UI regressions;
- rain/cloud/night overlays make important gameplay unreadable;
- braids create impassable accidental walls;
- oxbows or gorge banks appear in physically absurd locations at high frequency;
- world-map terrain contradicts local terrain;
- new-world generation crashes or regularly creates invalid spawns.

Minor art tuning, rare morphology calibration issues and missing delta
distributaries can be logged for later work without blocking basic Dev30 testing.
