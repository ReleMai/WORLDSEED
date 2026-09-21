# RC13 Seeded World Preparation Report

## Goal

Move expensive first-contact terrain/resource generation out of moment-to-moment movement and into an explicit seeded-world loading phase.

## Research conclusion

Open-world chunk pre-generation is a proven way to exchange startup time and disk space for smoother exploration. Chunky, a widely used Minecraft pre-generator, specifically recommends preparing chunks before players enter so generation does not affect gameplay, while also warning that preparation cost grows rapidly with radius. Modern chunk systems still retain streaming/caching because an actually infinite procedural world cannot be fully materialized. WORLDSEED therefore uses a hybrid: prepare the likely opening exploration envelope, persist it, and keep deterministic expansion beyond it.

## Implementation

### Persistent prepared terrain

SQLite now contains a `generated_chunks` table keyed by chunk coordinate, z-level and world-generator version. Each prepared chunk stores a compressed array of terrain content IDs rather than registry indexes, so content ordering cannot silently reinterpret an old prepared chunk. If an ID no longer exists, runtime falls back to deterministic generation. Player terrain changes remain in `tile_deltas` and are applied after the prepared base chunk loads.

### Persistent prepared natural resources

`generated_resource_chunks` stores compressed current-season base placement keyed by chunk, resource-generator version and season. Harvesting/depletion/regrowth are not baked into this data; they remain living simulation overlays. Structures/crops/soil continue to suppress underlying natural features at read time.

### New-game preparation envelope

Default: radius 8 chunks around the selected spawn = 17×17 = 289 surface chunks = 544×544 cells.

Loading phases:

1. read content and seed rules
2. select a viable starting region
3. shape/persist terrain chunks
4. place/persist current-season natural resources
5. realize nearby ecology/settlements/living-world systems
6. enter gameplay

### Existing saves

Existing saves warm a 5×5 chunk neighborhood around the player while the normal load screen is visible. Missing prepared data can be generated there rather than during the first movement after loading.

### Memory discipline

- terrain LRU raised to 384 chunks, enough to retain the 289-chunk opening envelope plus working margin
- resource prepared-chunk LRU capped at 384 chunks
- large interpolation/candidate scratch dictionaries are cleared after preparation
- deterministic prepared data lives in SQLite, so cache eviction does not lose generation work

## Benchmarks

`PYTHONPATH=. python tools/bench_pregeneration.py` on the validation environment produced approximately:

- cold first terrain tile in a new chunk: 20.350 ms
- prepared first terrain tile: 0.303 ms
- cold 1,024-cell resource chunk lookup: 77.595 ms
- prepared 1,024-cell resource chunk lookup: 3.454 ms

The exact numbers vary by CPU, but the architectural change removes generator work from the movement path inside the prepared envelope.

A full radius-8 new-world preparation on the validation environment took roughly 20–25 seconds and produced only a few hundred KB of prepared chunk data in SQLite. Subsequent loading around the same spawn was effectively immediate because it read prepared data instead of recomputing it.

## Compatibility

- save schema remains 3; the cache tables are additive
- worldgen remains version 4
- resourcegen remains version 3
- existing worlds remain loadable
- WORLDSEED remains unbounded and deterministic outside the prepared region

## Validation

RC13 adds tests proving that prepared terrain reloads without calling the procedural generator, prepared resource chunks reload without raw placement work, and the graphical loading-screen/progeneration contract is present.
