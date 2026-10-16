# W4 natural landscapes, rain and building alignment

This is the next engine work unit after the persistent GPU main-game integration.
It applies to the live main game; prepared scenes are validation inputs.

## Research and chosen approach

- [Red Blob Games: terrain from noise](https://www.redblobgames.com/maps/terrain-from-noise/) separates broad terrain/climate causes from finer variation and describes why elevation-only biome bands are limiting. WORLDSEED already has physical v8 geology and climate; the new v9 cover classifier uses those sources instead of replacing them with unrelated random geography.
- [de Carpentier: procedural terrain extensions](https://www.decarpentier.nl/scape-procedural-extensions) explains coherent domain distortion and terrain-aware procedural detail. Here a small globally addressed warp affects grove/clearing margins, while exposure, shelter and physical climate control habitat. Rivers, coasts, caves and elevation are not warped by presentation.
- [NVIDIA GPU Gems: tile-based texture mapping](https://developer.nvidia.com/gpugems/gpugems2/part-ii-shading-lighting-and-shadows/chapter-12-tile-based-texture-mapping) and [texture bombing](https://developer.nvidia.com/gpugems/gpugems/part-iii-materials/chapter-20-texture-bombing) discuss material continuity and repetition. The implementation uses a smaller GL 3.3-compatible approach: world-coordinate mirrored detail at unequal rotations/scales, broad modulation plus fine grain, and separable blending of admitted neighboring materials. Four contributors at a pixel and nine bounded texture bindings cover mixed corners without adding per-cell overlay passes.
- [NVIDIA: Rain, Sarah Tariq](https://developer.download.nvidia.com/SDK/10/direct3d/Source/rain/doc/RainSDKWhitePaper.pdf) motivates depth, wind and lighting response rather than flat scrolling sheets. WORLDSEED keeps its existing single postpass and adds three analytic, stable particle bands with tapered lengths, downward travel and subdued exposure. No external artwork or sample code was copied.

These are implementation choices adapted to this 2D engine, not a claim that it
implements full hydraulic erosion, NVIDIA's 3D sample or physically exact rain.

## Defects identified and fixed

1. Fractional per-cell scissors rounded both edges inward with ceil(start) and floor(end). Adjacent rectangles consequently dropped a full pixel column/row during camera motion. Raster admission now follows fragment centers: ceil(edge − 0.5) for shared boundaries. This removes gaps without expanding fog-of-war to unknown samples. Integer clips keep their coverage.
2. Ground art restarted UVs and chose independently graded variants per cell. Some authored materials also contain tile-wide strokes. The live GPU ground path now uses one canonical material source and continuous world coordinates, with softened detail and noise-modulated material transitions. A newly modded surface/underground ground definition participates by tags; shaft/ore/loot/ruin art and hard traversal boundaries remain crisp. Existing terrain IDs/collision/water depth stay authoritative.
3. Old rain had a regular grid and top-origin motion in the wrong vertical direction. New drops use stable trajectories, independent depth/speed, variable tails and lighting. Unknown pixels remain black; explored memory remains already dimmed and receives no live weather/light/fog.
4. GPU house clicks used whole visible physical cells, including transparent roof corners. Pointer regions now sample actual painted alpha and admitted clips from the same commands that draw the house, with door priority and stable threshold IDs. Source padding and doorway sizes no longer define game units: fitting uses a consistent human-scale doorway within the existing physical extent.

## Compatibility and limits

Rendering upgrades apply to existing worlds. Only **new worlds** use WORLDGEN9
land-cover placement; v1–v8 keep their saved geography. Saved house footprints,
physical collision and portal identities are not shrunk to match a sprite. This
fixes visual sizing and selection hitboxes, not the world's existing collision
layout. House styles are retained but fitted to a common scale.

The new terrain pass preserves material batching (36 same-ground cells remain
one draw/one upload in the regression), bounded caches, read-only snapshots,
exact discovered/current sight separation and one main-game window. No renderer
calls generation, discovery, collision updates or persistence. The v9 topography
cache is owned by its world and can be collected when that world unloads.

Rain interception/splashes need an admitted cover/ground mask and remain open;
this unit does not paint splash rings on actors/roofs as if they were ground.
Tree shadows remain contact art. Real Windows hardware performance/visual
acceptance, device recovery and longer playtests remain release gates.
