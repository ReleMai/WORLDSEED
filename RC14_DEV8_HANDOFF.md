# WORLDSEED RC14 Embodied World Dev8 handoff

This work unit focused on the terrain tiling complaint from the live screenshot: repeated single-texture cells, especially sand, still read like wallpaper. The goal was to stay within one bounded session and deliver a directly playable improvement.

## Research direction applied
Modern tile workflows generally combine two ideas:
1. **terrain-aware transitions / autotiling** so boundaries pick the correct connecting edge/corner treatment
2. **alternative tiles / weighted variants** so one terrain does not repeat the exact same image on every cell

WORLDSEED already had presentation-only 8-direction local blending from Dev7. Dev8 adds the second half: deterministic multi-variant terrain sets.

## Delivered

### 1) Ten-variant terrain sets for repeating surface terrain
Added a reproducible generator script:
- `tools/build_terrain_variant_set.py`

The script now builds **10 authored runtime variants** for each of these repeat-heavy terrain types:
- `core:grass`
- `core:forest`
- `core:scrub`
- `core:sand`
- `core:rock`
- `core:tundra`
- `core:wetland`
- `core:water`
- `core:river`
- `core:river_shallow`
- `core:floodplain`
- `core:tilled_soil`
- `core:cave_floor`
- `core:berry_thicket`

Each set uses the same base material language but introduces deterministic internal variation (tone, mottling, ripples, clumps, pebbles, etc.) so the world stops reading as a repeated single tile.

### 2) Visual manifest updated for alternative terrain tiles
- `worldseed/assets/visuals.json`
  - common natural terrains now map to **lists of 10 files**, not a single texture

### 3) Renderer integration
- `worldseed/ui/pygame_terminal.py`
  - added `_terrain_variant_index(...)`
  - terrain tiles now choose a **stable per-cell variant** based on terrain ID + world coordinates
  - transition-composition cache key now includes the actual selected neighbor paths, so edge-blended tiles do not accidentally reuse the wrong composed variant

This means:
- same world seed => same terrain tile choices
- no runtime flicker
- more visual variety without affecting simulation or save format

### 4) Atlases / artifacts
- rebuilt atlases with `tools/build_sprite_atlases.py`
- added preview artifact:
  - `artifacts/terrain-variant-preview.png`

## Validation
Focused regression pass completed:
- `tests/test_terrain_variants.py`
- `tests/test_asset_readability.py`
- `tests/test_local_terrain_transitions.py`
- `tests/test_rc8_visuals.py`
- `tests/test_region_map.py`
- `tests/test_regional_terrain_assets.py`
- `tests/test_rc12_renderer.py`
- `tests/test_rc14_world_presentation.py`

Result:
- **27 passed**
- **7 skipped**
- **35 subtests passed**

## Notes / limits
- This is a strong improvement over a single repeated tile, but it is still a lightweight runtime approach.
- A future higher-end step would be a true **terrain-set / Wang / blob tile** system for same-terrain internal edge motifs as well, especially if you want hand-authored micro-transitions within the same terrain family.
- Hard authored terrain features (ruin walls, seams, shafts, caches, etc.) were intentionally left as bespoke single-purpose tiles.

## Suggested next work unit
1. run the build in a pygame-enabled environment and visually tune any terrain whose 10 variants are still too subtle
2. add **weighted probabilities** so a few calmer base variants appear more often than the noisier ones
3. if desired, move toward a **47-tile blob / mixed terrain set** for the most common surfaces
