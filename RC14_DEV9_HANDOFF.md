# WORLDSEED RC14 Embodied World Dev9 handoff

This bounded work unit focused on **terrain realism and blending quality** after Dev8's first alternative-tile pass. The goal was to make repeated terrain read more like connected natural ground instead of visible wallpaper while keeping the renderer presentation-only.

## Summary
Dev9 replaces the main repeating surface materials with **new seamless terrain art assets** generated specifically for runtime tiling, then tunes the local renderer's blend behavior so different materials meet more naturally.

## Delivered

### 1) New seamless terrain material pass
Reworked `tools/build_terrain_variant_set.py` into a proper terrain material generator.

It now creates fresh seamless/tileable material art for the main natural terrains instead of only lightly modifying the prior texture files.

Terrains covered:
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

For each terrain, the generator now produces:
- an updated primary base texture (for compatibility / inspection)
- **10 deterministic variants** used by the renderer

Visual goals of the new assets:
- remove obvious tile-edge repetition
- keep material language readable at small in-game tile sizes
- give each terrain a more realistic ground feel
- maintain enough shared palette structure for cross-terrain blending

### 2) Blend-profile tuning for more natural transitions
Updated `worldseed/presentation/local_terrain.py` and `worldseed/ui/pygame_terminal.py`.

Added terrain-aware transition tuning via `transition_profile(center_id, neighbor_id)`.

This means local presentation blends are no longer one-size-fits-all:
- **shorelines** (water/sand, water/wetland) use wider and stronger blends
- **soil/surface transitions** use medium blends
- **rock/cave contacts** stay tighter and crisper
- same-family materials still remain crisp to avoid muddy blur

### 3) Stable per-cell terrain variation retained
Kept Dev8's deterministic per-cell terrain variant selection so there is still:
- no flicker
- same look for the same world coordinates
- significantly less visible repetition on large surfaces

### 4) Atlases and artifacts refreshed
Rebuilt atlases and generated updated visual QA artifacts:
- `artifacts/terrain-variant-preview.png`
- `artifacts/terrain-tiling-preview.png`

`terrain-tiling-preview.png` is especially useful because it shows repeated copies of the new material tiles, making seam issues easy to inspect.

## Validation
Focused regression suite completed successfully:
- `tests/test_terrain_variants.py`
- `tests/test_asset_readability.py`
- `tests/test_local_terrain_transitions.py`
- `tests/test_rc8_visuals.py`
- `tests/test_region_map.py`
- `tests/test_regional_terrain_assets.py`
- `tests/test_rc12_renderer.py`
- `tests/test_rc14_world_presentation.py`

Result:
- **28 passed**
- **7 skipped**
- **35 subtests passed**

## Changed files
Primary files changed in this work unit:
- `tools/build_terrain_variant_set.py`
- `worldseed/presentation/local_terrain.py`
- `worldseed/ui/pygame_terminal.py`
- `tests/test_local_terrain_transitions.py`
- `tests/test_terrain_variants.py`
- regenerated terrain sprites under `worldseed/assets/sprites/terrain/`
- regenerated atlases under `worldseed/assets/atlases/`
- updated `worldseed/assets/visuals.json`

## Suggested next work unit
If you want another short pass, the next best visual improvement would be:
1. render a live gameplay screenshot from the Dev9 build and tune any terrain that still reads too flat in motion
2. add a small number of **edge-detail overlays** (shore foam, grassy fringe, muddy banks) for the most common transition pairs
3. optionally add **weighted terrain variants** so calm base textures appear more often than noisier alternates
