# WORLDSEED RC14 Embodied World Dev10 handoff

This bounded work unit focused on **shoreline quality** and **water-context differentiation**. The request was to make coastlines prettier and clearly distinguish:
- river beds
- shorelines
- river edges / banks
- freshwater shallow vs deep
- ocean shallow vs deep
- mixed water where fresh and ocean meet

## Summary
Dev10 keeps the world/sim terrain IDs authoritative, but upgrades the **presentation layer** so water and adjacent terrain render differently based on context. This avoids risky simulation churn while making the map read much more like a natural world.

## Delivered

### 1) Context-sensitive water tile families
Added new contextual presentation terrain families with **10 variants each**:
- `render:ocean_deep`
- `render:ocean_shallow`
- `render:estuary_mix`
- `render:freshwater_deep`
- `render:freshwater_shallow`

These are render-only terrain visuals stored in `visuals.json` and resolved by the pygame local renderer.

### 2) New water art assets
Created `tools/build_contextual_water_assets.py` to generate new runtime tileable water materials.

Visual intent:
- **ocean deep**: darker blue open water
- **ocean shallow**: brighter shallower coastal water with sandy undertones
- **estuary mix**: greener/brackish transitional water where river and ocean meet
- **freshwater deep**: cooler inland channel water
- **freshwater shallow**: lighter water with visible bed hints for shallows / riverbed feel

Preview artifact:
- `artifacts/contextual-water-preview.png`

### 3) Context-aware water display selection
Updated `worldseed/presentation/local_terrain.py` with presentation helpers:
- `contextual_display_id(...)`
- `edge_overlay_kind(...)`
- `edge_overlay_signature(...)`

Rules now used by the renderer:
- `core:river_shallow` -> freshwater shallow visuals
- `core:river` -> freshwater deep visuals
- `core:water` next to land -> ocean shallow visuals
- `core:water` next to river -> estuary mix visuals
- `core:water` surrounded by water -> ocean deep visuals

### 4) Prettier coasts and riverbanks
Updated `worldseed/ui/pygame_terminal.py` to apply directional **edge overlays** after terrain composition.

Overlay types include:
- `water_ocean_shore`
- `water_estuary`
- `water_river_edge`
- `land_beach`
- `land_shore`
- `land_rock_shore`
- `land_riverbank_bare`
- `land_riverbank_soft`

This gives better visual separation between:
- open water edge vs bank edge
- beach vs grassy shoreline vs rocky shoreline
- ocean shore vs river bank
- water-body edge vs interior water tile

### 5) Existing blending retained
Dev9's terrain blending remains in place, but Dev10 now layers context-specific shoreline/bank presentation on top of it instead of treating all water contacts the same.

## Validation
Focused regression pass completed successfully:
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

## Changed files
Primary files changed this work unit:
- `tools/build_contextual_water_assets.py`
- `worldseed/presentation/local_terrain.py`
- `worldseed/ui/pygame_terminal.py`
- `tests/test_contextual_water_rendering.py`
- regenerated `worldseed/assets/visuals.json`
- regenerated water-related terrain assets under `worldseed/assets/sprites/terrain/`
- regenerated atlases under `worldseed/assets/atlases/`

## Suggested next work unit
The best next short pass would be one of:
1. tune the shoreline overlays against a live gameplay screenshot so the effect is stronger/weaker where needed
2. add dedicated muddy-bank / reed-bank overlays for wetlands and floodplains
3. if simulation expansion is desired later, introduce explicit sim terrain IDs for estuary / coast shallows rather than only presentation-layer distinctions
