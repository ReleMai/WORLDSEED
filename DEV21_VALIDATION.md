# Dev21 validation

- Compile: PASS.
- Real SDL pointer tests: **10 passed** in 7.38s (artifacts/dev21_mouse_tests.txt).
- Navigation/shared widgets and updated control-contract regressions: **34 passed** in 137.96s (artifacts/dev21_navigation_tests.txt).
- Existing pygame behavior, crafting/inventory render and feature-hook regressions: **11 passed** in 18.72s (artifacts/dev21_renderer_tests.txt).
- Deterministic replay: PASS, afdea05778f084b1e708795ad9020e470548f063.
- Visual review: clickable HUD and crafting screenshot; all menu-card hit regions checked at 800x520 and 1600x900. Existing pygame suite checks centered observational world rendering at zoom limits and map hover isolation.

The broad unittest run completed 265 tests: 262 passed, with two failures and one error. It started before two old control assertions were updated: one demanded inert mouse buttons, the other used D to confirm the main menu. Both contradict the requested controls; their updated replacements passed in the focused navigation run. The remaining known RC7 bootstrap discovery failure (`test_zero_supply_bootstrap_reaches_food_and_fire`) reports that the stone-flake recipe has not been discovered. It remains separate from UI controls and is not fixed in this release. The entire broad suite was not rerun after updating the obsolete assertions.

SDL dummy-driver tests were run here; a Windows desktop playthrough was not performed.
