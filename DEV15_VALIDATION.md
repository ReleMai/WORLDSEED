# Dev15 validation

- Full unittest suite: 257 tests passed (416.920 seconds).
- Water/swimming and pygame focused suite: 21 passed.
- Current/rendering/UI regression suite: 37 passed.
- Final pygame checks after render caching and sidebar fit adjustments: 7 passed.
- Python compileall: passed.
- Golden replay completed successfully: d8efc89dfd69f808877c39788846d392b7ac27b0.
- Hydrology audit: 4,096 core nodes, 6,400 total nodes, zero issues; worldgen v6 / hydrology v1.
- Rendered actual generated coast and river scenes in headless pygame; checked idle animation changes pixels without changing simulation state and stops on console screens.
- Saved preview-world state passed the database verifier with zero issues.
- Warm coastal render benchmark improved from about 294 ms to 74 ms after caching prepared currents. Idle water redraw was about 2.5 ms. These are headless container timings, not Windows frame-rate guarantees.

The first full run found three outdated assertions (generator version, depth blending, and Dev14 window-close token) and a metallurgy fixture that placed its forge underwater. Assertions were aligned with the intended contracts and the workshop fixture was explicitly placed on dry ground. The full rerun passed.

The final renderer-only optimizations were also checked separately after the full suite started. Tests, rebuild scripts, source, terrain assets and handoff notes are included. Saves and platform-specific test dependencies are excluded from the release archive.

Start a new world to see v6 geography. Existing saves retain their original terrain.
