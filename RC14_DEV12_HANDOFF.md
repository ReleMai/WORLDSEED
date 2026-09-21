# WORLDSEED RC14 Embodied World Dev12 handoff

This bounded work unit extends the earlier water polish with a **world-generation current field** and **directional current visuals**.

## Goals addressed
1. Add **river currents**
2. Add **ocean/coastal currents**
3. Improve the **visual readability** of moving water
4. Surface this information in both the **local view** and the **regional map**

## Summary
Dev12 introduces a deterministic current-sampling layer that reads from the existing world and hydrology authorities instead of inventing random visual motion.

- **Rivers** now expose a directional current derived from the hydrology flow graph.
- **Ocean/coastal water** now exposes a deterministic large-scale circulation field, with extra along-shore bias near coasts.
- The pygame renderer now draws **direction-aware animated water overlays** instead of generic shimmer only.
- Hover tooltips and regional planning now expose **current direction / strength** metadata.

## Delivered

### 1) Surface current model
Updated `worldseed/world/generator.py`.

Added:
- `SurfaceCurrent` read model
- `WorldGenerator.current_at(...)`
- internal helpers for:
  - `_river_current_at(...)`
  - `_ocean_current_at(...)`

Behavior:
- **River current** is derived from the RC14 hydrology flow network and river segment dominance around a queried cell.
- **Ocean current** is derived from a stable large-scale deterministic vector field with coastal alignment bias near shorelines.
- Output includes:
  - current kind
  - flow vector (`dx`, `dy`)
  - speed
  - heading label
  - strength band

### 2) World wrapper support
Updated `worldseed/world/world.py`.

Added:
- `World.current_at(...)`

This keeps current sampling accessible to presentation / planning code without making the UI a generation authority.

### 3) Regional planning now records water-current metadata
Updated `worldseed/world/region_blocks.py`.

`RegionWaterExit` now includes:
- `current_heading`
- `current_strength`
- `water_kind`

Planner changes:
- river exits now record current direction / strength
- coastal/ocean-facing edges can now be represented as water exits when a region edge has sustained ocean exposure

This is the main **world-generation/planning update** for the feature.

### 4) Local renderer: directional animated currents
Updated `worldseed/ui/pygame_terminal.py`.

Changes:
- animated water overlay now accepts current vector + speed
- current streaks now align with sampled water flow
- water motion is no longer only decorative shimmer; it now reflects generated current direction
- hover tooltips now show entries such as:
  - `River current: moderate southeast`
  - `Ocean current: gentle west`

### 5) Regional map current visualization
Updated `worldseed/ui/region_map.py`.

Changes:
- water links now draw **cyan arrow markers** showing current direction
- sidebar includes short **water current summaries** for the current region
- legend updated to explain current arrows

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
- `tests/test_rc14_region_blocks.py`
- `tests/test_rc14_environment.py`
- `tests/test_water_currents.py`

Result:
- **48 passed**
- **7 skipped**
- **40 subtests passed**

## New / updated tests
Added:
- `tests/test_water_currents.py`

This verifies:
- directional river current samples exist
- directional ocean current samples exist
- regional plans encode current metadata

## Primary changed files
- `worldseed/world/generator.py`
- `worldseed/world/world.py`
- `worldseed/world/region_blocks.py`
- `worldseed/ui/pygame_terminal.py`
- `worldseed/ui/region_map.py`
- `tests/test_water_currents.py`

## Suggested next work unit
Best next bounded follow-up after you test this build in motion:
1. give **major rivers** stronger visual hierarchy than minor streams
2. add **foam / breaker visuals** where ocean currents meet coastlines
3. optionally let fish / floating debris / boats read current direction for immersion
