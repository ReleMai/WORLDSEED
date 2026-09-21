# Procedural regional terrain assets

The M region map generates cartographic terrain artwork from each discovered region's prepared `RegionBlockPlan`. Every block still represents 512 x 512 world cells. Grass tufts, trees, stone, sand, snow marks, waves and ridge symbols replace the flat fill and single relief slash.

The plan's dominant biome selects a profile. Moisture changes the palette and vegetation density; temperature changes the cold tint; elevation changes material brightness and ridge snow; relief controls ridge symbols. The forest share of `biome_mix` controls tree symbols in grassland. These are summary symbols, not exact local feature positions. Summary data does not contain a spatial biome raster, so the artwork does not invent coastlines, waterways, settlements or roads. Existing regional connection and discovery rendering stays authoritative.

## Ownership and customization

- `worldseed/presentation/regional_terrain.py` owns `TerrainAppearance`, `RegionalTerrainAssets.surface(plan, pixels)` and procedural painting.
- `worldseed/assets/regional_terrain.json` contains namespaced biome profiles with base/dry/cold palettes, mark colors, symbol kind and density. Unknown biomes have an explicit gray fallback.
- `worldseed/ui/region_map.py` draws these surfaces below the existing water/road/settlement/player overlays. The hover snapshot fix remains in place.
- `tools/export_regional_terrain_samples.py` exports 21 sample PNGs plus a labeled atlas. Run `python tools/export_regional_terrain_samples.py --output artifacts/regional-terrain-assets` using the pygame-enabled Python environment. These are illustrative sample plans, not geography added to a saved world.

## Determinism, persistence and cost

Artwork uses the named `presentation:regional-terrain` RNG namespace and asset version 1. Its private PCG stream depends on region coordinates and biome; public terrain fields control the appearance. It does not read hidden control/site potential or the all-fields plan fingerprint, consume simulation RNG, call terrain/region generation, or write saves. No schema/worldgen migration or gameplay content changes are required.

Canonical assets are 128 x 128 pixels, preserving the same motifs on resize. Display variants are capped at 256 x 256 before final viewport scaling. A per-renderer LRU holds at most 256 surfaces, enough for base and display assets for the full 13 x 9 regional viewport. Eviction only costs regeneration of artwork. There is no persistent generated-image collection in normal gameplay.

Tests cover repeatability, request-order independence, field sensitivity, hidden-state isolation, all seven biome profiles, unknown fallback, cache reuse/eviction, full-viewport cache retention, and unchanged hover/discovery/connection behavior. The save preview is rendered offscreen through a read-only SQLite connection with terrain and plan generation forbidden. See `artifacts/terrain-assets-profile.json` for the local cold/cached generation measurement.

Next dependency: exact spatial regional terrain illustration would require an authoritative prepared spatial raster; this system deliberately remains a cartographic summary of existing Dev5 data.
