# WORLDSEED RC14 Embodied World Dev11 handoff

This bounded work unit focused on two follow-up visual issues from Dev10:
1. **floodplains looked too grassy / strange near water**
2. **water looked too static**

## Summary
Dev11 retunes floodplain terrain so it reads more like **silty, sandy river-adjacent ground**, and adds a lightweight **animated water shimmer overlay** so rivers, shallows, estuaries, and ocean water no longer feel completely still.

## Delivered

### 1) Floodplain retune: sandier / more alluvial
Updated `tools/build_terrain_variant_set.py` for `core:floodplain`.

Changes:
- shifted the floodplain palette away from grassy green and toward **sandy alluvial silt**
- reduced dense grass-blade decoration
- added subtle sand/silt ripple language and damp patch variation
- kept the texture seamless and compatible with Dev8/Dev9's 10-variant terrain system

Result:
- floodplain now sits visually closer to sand and river margins
- it reads better as a transitional terrain near water rather than ordinary grassland

### 2) Water-material tuning
Updated `tools/build_contextual_water_assets.py`.

Changes:
- made shallow and mixed water a bit sandier / bed-driven
- improved differentiation in:
  - `render:freshwater_shallow`
  - `render:freshwater_deep`
  - `render:ocean_shallow`
  - `render:ocean_deep`
  - `render:estuary_mix`
- increased visible current / ripple language in the generated tile art

### 3) Animated water motion overlay
Updated `worldseed/ui/pygame_terminal.py`.

Added a lightweight cached presentation overlay:
- `_animated_water_overlay(display_id, tile_px, phase)`

Behavior:
- only applies to contextual water display IDs
- phase is derived from the in-game clock for subtle motion variation
- adds moving shimmer / current lines over water tiles during rendering
- does **not** change simulation data or terrain IDs

This keeps the world-authoritative terrain system intact while making water feel less static.

## Validation
Focused regression suite completed successfully:
- `tests/test_contextual_water_rendering.py`
- `tests/test_terrain_variants.py`
- `tests/test_local_terrain_transitions.py`
- `tests/test_asset_readability.py`
- `tests/test_rc8_visuals.py`
- `tests/test_region_map.py`
- `tests/test_regional_terrain_assets.py`
- `tests/test_rc12_renderer.py`
- `tests/test_rc14_world_presentation.py`

Result:
- **31 passed**
- **7 skipped**
- **40 subtests passed**

## Useful artifacts
- `artifacts/contextual-water-preview.png`
- `artifacts/dev11-water-floodplain-preview.png`

## Changed files
Primary files changed in this work unit:
- `tools/build_terrain_variant_set.py`
- `tools/build_contextual_water_assets.py`
- `worldseed/ui/pygame_terminal.py`
- regenerated terrain sprites under `worldseed/assets/sprites/terrain/`
- regenerated atlases under `worldseed/assets/atlases/`
- regenerated `worldseed/assets/visuals.json`

## Suggested next work unit
If you want another short visual pass after testing this build in motion, the best next step would be:
1. tune water shimmer strength from live screenshots/video
2. add special muddy-bank / reed-bank overlays for wetlands and floodplains
3. introduce optional directional river-current hints tied to neighboring river cells
