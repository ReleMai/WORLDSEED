# RC14 Dev34 — Phase 5 coast projection and local presentation

## Scope and authority

Phase 5 physical implementation is delivered: Dev33 coast classes/bathymetry plus coast-v2 estuary widening, connected distributaries, shallow sediment lobes, and sediment-fed longshore barriers/lagoon pockets. This is a bounded first physical model, not fluid/sediment simulation. Coastline erosion over game time, dedicated coastal art and Phase-6 soil/substrate refinement are not included. Phase 6 is the next development dependency; final WORLDGEN v8 acceptance still belongs to Phase 15.

`world/coastal_mouths.py` derives plans from prepared land-to-sea hydrology edges, geological depth, discharge, gradient, shelter, sediment potential and prevailing wind. Branches start on the existing channel and end below sea level; unsuitable high-ground branches are rejected. Discharge shares exactly conserve source accumulation. Deposits cannot overwrite other existing channels or lakes. Hydrology, actual terrain, crossing costs and current direction consume this projection. Raster geometry uses integer calculations and stable coordinate ordering, without new RNG namespaces.

## Persistence and preparation

`COAST_MORPHOLOGY_VERSION = 2` for new worlds only. Missing metadata remains 0; saved 1 remains 1. Schema 3, WORLDGEN 8, Hydrology 2 and Hydrology Morphology 2 are unchanged. Existing version-keyed surface caches distinguish v0/v1/v2. Generated mouth indexes are reconstructed, not saved; player deltas still apply after base terrain. Startup prepares loaded-domain mouth indexes; renderer/current inspection cannot build them. A maximum of 12 domain indexes is retained. Geometry fits within the existing 128-cell hydrology halo.

## Measured performance and forest fix

The 2560x1392 render profile found redundant full-screen alpha work, per-frame rain identity hashes, filesystem stats before sprite-cache lookup, and irrelevant terrain-neighbor reads. The revised path reuses rain identities and cached sprites, queries neighbors only for contextual water, and composites soft clouds at bounded density. Profiled warm frames fell from about 57 ms to 45 ms in the same fixture; these include profiling overhead, not live gameplay FPS claims.

The larger stall came from geological work during chunk materialization. The startup profile made nearly 16 million hash calls; ecology's sparse sampling touched 22 chunks. Instance-owned LRUs now retain 8192 geological feature hashes, 8192 stress directions and 65536 immutable landform samples. Frozen Dev33 fingerprints remain unchanged. In matched unprofiled runs with identical coast-v1 geography, startup fell from 38.415 s to 5.571 s; cached movement from 1.485 to 1.154 ms/step. Current render code averaged about 32.4 ms/frame in both cache-comparison runs. These are synthetic local measurements, not a guarantee for every saved world; cold exploration still requires materialization outside prepared terrain.

Forest now uses one continuous 16-cell litter/moss material, with a small overlapping boundary blend. The camera samples absolute world coordinates. It removes per-cell repetition and avoids mirror seams. Existing cloud/pine/morel/cave art remains intact. `PREVIEW_VISUALS.bat` renders this material; `tools/preview_coastal_morphology.py` compares real coast-v1/v2 terrain at the same seed and coordinates.

## Tests and audits

- Nine coast mouth/save tests: channel connectivity, discharge conservation, physical suitability, barriers/lagoon gating, read-only current lookup, deterministic rebuild, shared halo copies, v1 save/v2 cache separation.
- Four terrain/performance tests: frozen Dev33 geology, adjacent hash reuse, continuous world-coordinate crops, no filesystem stats on warm sprites.
- Texture-diversity tests count actual material cells for continuous textures, retaining the diversity gate instead of demanding separate PNG files.
- Twelve-seed audit: 725 mouths, 11 deltas, 4 barriers, 94 duplicate plan comparisons and 15,360 exact seam raster samples checked. No plan mismatch. See final recorded gate results below.
- Existing full-suite fixture failures were traced and repaired: resource tests now search around the real spawn rather than offshore (0,0); corruption changes the value; LOS resets its runtime discovery cache; bootstrap uses inventory discovery and the experiment command before crafting. Gameplay assertions were retained.

Release checks in progress; final suite/package results are recorded before publication.

- Golden replay preserved: `0b369fbd04f8fab3ce6a7b295ee942ac369f000d`.
- Century soak, one seed/full policy: 12,000 days, no invariant errors; 9 realized regions, 48 NPCs, 54 routes, 2.06 MB serialized state. Advancement took 35.224 s on this machine (not a hardware-independent gate).
- Content and visual coverage audits passed. Python compile and diff whitespace checks passed.
- Concurrent upstream inventory work at `8032a8f` is retained during integration; its UI regression tests are included in the final validation.

## Asset provenance

Built-in imagegen, prompt: "Create a seamless tileable square top-down forest FLOOR material texture for a realistic painterly 2D survival game. Entire image is flat ground seen orthographically straight down: dark brown decomposing leaf litter, very fine irregular pine needles, scattered small dull leaves, restrained patches of olive moss and exposed humus. Low contrast, subdued olive-brown palette, evenly distributed small-scale natural detail. No trees, bushes, mushrooms, stones larger than leaves, objects, shadows, lighting gradients, borders, grid, stripes, repeated directional lines, paths, text, or isolated focal point. Uniform soft ambient lighting. Seamless matching opposite edges. 1024 square. This is a single continuous terrain texture, not a sprite sheet. Save output for use in WORLDSEED project."

Saved asset: `worldseed/assets/sprites/terrain/forest_floor.png`. The renderer supplies continuous sampling and edge blending; no generated geography is inferred from the art.
