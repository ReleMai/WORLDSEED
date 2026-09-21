# Dev20 validation

- Compile: PASS (`python -m compileall -q worldseed`).
- Targeted appearance, feature widgets, real SDL draws, navigation, cave/discovery suite: **37 passed** (237.87s). Log: artifacts/dev20_targeted_tests.txt.
- Startup/appearance + RC10 worldgen: **8 passed** (57.17s). Log: artifacts/dev20_startup_tests.txt.
- New-character no-guiding-leads regression: **1 passed** (7.26s).
- Additional startup follow-up: **2 passed, 1 failed**. The remaining RC7 zero-supply bootstrap harness harvests directly through `sim.resources.harvest` and attempts a locked recipe without the normal discovery command path. It reports “You have not discovered that recipe yet.” This is not a graphical crash and was not hidden by changing recipe-discovery rules.
- Real pygame-ce 2.5.8/SDL dummy video rendering reproduced the original keyword-only icon-scale TypeError before the fix. Post-fix actual draws passed for every affected crafting/inventory route. Simulation state and inventory are unchanged by these draws.
- 20 player assets checked for RGBA transparency, shared 160x256 canvas, unclipped bounds and loadability at multiple display sizes. Gallery and recipe screenshots visually reviewed.
- Deterministic replay: PASS; hash afdea05778f084b1e708795ad9020e470548f063.
- The initial broad unittest run began before the startup NameError was discovered and repaired. It completed 263 tests: 256 passed and seven startup NameErrors. After repair, six formerly failing cases passed; the seventh reached the separate bootstrap discovery assertion described above. Its failures and subsequent targeted results are retained separately; this release does not claim an entirely green broad suite.

No Windows desktop playthrough performed. Source atlas, import script, regression tests and screenshots are included.
