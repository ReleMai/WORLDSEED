# WORLDSEED RC14 Embodied World Dev13 handoff

This bounded art pass focuses on two issues you flagged in the latest build:

1. **Water still looked too pixelated**
2. **Nettle art had a stray dark/black line artifact**

## Summary
Dev13 is a focused terrain-art and sprite-cleanup update.

### Water terrain revision
I reauthored the major water families so the surface reads as smoother, more natural, and less noisy at gameplay scale.

Updated families:
- `water_hd_v00..v09`
- `ocean_deep_hd_v00..v09`
- `ocean_shallow_hd_v00..v09`
- `estuary_mix_hd_v00..v09`
- `freshwater_deep_hd_v00..v09`
- `freshwater_shallow_hd_v00..v09`
- `river_hd_v00..v09`
- `river_shallow_hd_v00..v09`

Art changes:
- softer painterly base texture
- reduced harsh pixel-noise patterning
- smoother tonal blending
- more restrained highlight flecks
- shallow water now has gentler caustic-style variation
- river families retain some directional feel while staying visually cleaner

Fallback/base textures were also updated so non-variant reads stay consistent:
- `water_hd.png`
- `river_hd.png`
- `river_shallow_hd.png`

### Nettle sprite cleanup
Reauthored:
- `worldseed/assets/sprites/items/nettles.png`
- `worldseed/assets/sprites/resources/nettle_patch.png`

Fixes:
- removed stray dark/black artifacting
- improved silhouette readability
- clearer leaf shapes
- cleaner transparency edges

## Validation
Focused validation run:
- `tests/test_asset_readability.py`
- `tests/test_contextual_water_rendering.py`
- `tests/test_terrain_variants.py`
- `tests/test_local_terrain_transitions.py`
- `tests/test_rc8_visuals.py`
- `tests/test_rc12_renderer.py`
- `tests/test_rc14_world_presentation.py`
- `tests/test_water_currents.py`

Result:
- **32 passed**
- **40 subtests passed**

## Art preview
Generated preview artifact:
- `artifacts/dev13-water-nettle-preview.png`

## Primary changed files
- `worldseed/assets/sprites/terrain/water_hd_v00.png` ... `water_hd_v09.png`
- `worldseed/assets/sprites/terrain/ocean_deep_hd_v00.png` ... `ocean_deep_hd_v09.png`
- `worldseed/assets/sprites/terrain/ocean_shallow_hd_v00.png` ... `ocean_shallow_hd_v09.png`
- `worldseed/assets/sprites/terrain/estuary_mix_hd_v00.png` ... `estuary_mix_hd_v09.png`
- `worldseed/assets/sprites/terrain/freshwater_deep_hd_v00.png` ... `freshwater_deep_hd_v09.png`
- `worldseed/assets/sprites/terrain/freshwater_shallow_hd_v00.png` ... `freshwater_shallow_hd_v09.png`
- `worldseed/assets/sprites/terrain/river_hd_v00.png` ... `river_hd_v09.png`
- `worldseed/assets/sprites/terrain/river_shallow_hd_v00.png` ... `river_shallow_hd_v09.png`
- `worldseed/assets/sprites/terrain/water_hd.png`
- `worldseed/assets/sprites/terrain/river_hd.png`
- `worldseed/assets/sprites/terrain/river_shallow_hd.png`
- `worldseed/assets/sprites/items/nettles.png`
- `worldseed/assets/sprites/resources/nettle_patch.png`
- `CHANGELOG.md`

## Recommended next bounded work unit
If you still want the water to feel richer after testing Dev13 in motion, the best next step would be:
1. add **shore foam / breaker overlays**
2. add **river surface streak masks** for stronger flow readability
3. add **bank wetness gradients** where water meets sand / floodplain
