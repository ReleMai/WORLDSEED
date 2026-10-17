# Indoor shadow art and performance, second pass

Baseline: main `f6a4748a26e0960512920293b1bb08fbc910b27f`.

## Scope and contracts

- Replace overlapping darkzone strips with one continuous inward penumbra. A small mask uses three native box filters; exact original sight clips still gate every pixel. Unknown space and hidden actors remain hidden.
- Give furniture shadows a neutral contact core and softer outer edge, with bounded height-dependent displacement.
- Batch static interior sprites and their clips using the existing cropped UV mesh. Preserve paint order, alpha and material boundaries; animated sway retains scissor rendering.
- Reject distant wall candidates before exact segment intersection and defer sight-fan hull construction until a wall needs it. Fixed-point intersections and degenerate-cell behavior remain unchanged.
- Move the existing rectangle union helper to interior_clip_index, retaining the gpu_interiors compatibility alias.

No persistent fields, migration, RNG namespaces, geography or simulation cadence changes. Public darkzone command arguments remain compatible. Presentation is observational. The existing roof/player transparency fix remains covered.

## Performance and evidence

`python -m tools.bench_indoor_render --output <directory>` runs a bounded prepared interior trace on native OpenGL, with legal sampled positions, five warmup frames and 90 measured frames. It does not load player saves. Evidence is under `docs/evidence/indoor-shadow-pass2/{before,after}`.

RTX 4060 Ti, 960 x 640, same fixture and trace:

| Metric | Before | After |
| --- | ---: | ---: |
| Total median | 30.805 ms | 24.039 ms |
| Total p95 | 44.774 ms | 26.085 ms |
| Capture median | 18.373 ms | 13.012 ms |
| Preparation median | 8.726 ms | 7.824 ms |
| Synchronized draw median | 3.699 ms | 2.984 ms |
| Median draw calls | 107 | 29 |
| Last frame commands | 927 | 568 |
| Resident texture bytes | 7,980,972 | 21,149,100 |

Median measured frame processing dropped 22%, with 73% fewer draw calls. These are one native offscreen trace measurements, not interactive gameplay FPS or a general guarantee. Texture residency increases as sight masks vary; the existing 128 MiB texture-bank eviction limit bounds GPU residency. CPU mask caching retains only two entries, each at most 256 x 256 pixels.

## Validation

- Compileall for worldseed, tools and tests.
- Focused darkzone, interior, smoothing, floor batching and art tests: 46 tests, three EGL-only skips on Windows. Native Windows GL pixel/admission and batch tests ran successfully.
- Lighting and building stealth integration: 23 tests passed. The first attempt hit the sandbox temporary-directory restriction; rerunning with a workspace-local temporary directory passed.
- Randomized fixed-point segment parity (2,040 rays), lazy hull parity (600 cases) and exact SAT parity (1,500 cases), including thin walls, tangencies and degenerate cells.
- Mask cache/size bounds, partition-independent gradients, roof/player admission, hidden-pixel exclusion and native scissor/mesh parity regressions.
- Before/after native screenshots inspected at gameplay scale.

## Limits and next dependency

The bounded mask may soften fine contour detail at large viewport sizes; it never enlarges authorized sight. Exact sight geometry still defines the outer silhouette. This pass does not replace the visibility solver or perform a full release suite. Interactive play remains useful for assessing movement feel across additional room layouts and zoom levels.
