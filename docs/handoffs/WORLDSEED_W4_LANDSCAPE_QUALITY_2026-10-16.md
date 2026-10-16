# W4 landscape quality and WORLDGEN9 handoff

Canonical baseline `5201645`, fetched before edits, including recent exterior and
interior explored-memory fixes. Main-game GPU integration remains intact.

## Delivered

Read [research and defect analysis](../development/W4_NATURAL_LANDSCAPE_RESEARCH_2026-10-16.md).

- Continuous GPU terrain materials and admitted-neighbor/corner blending, with a raster-center fix for fractional clip seams. Art-wide lines/per-cell resets are reduced without baking software world surfaces. Existing terrain catalog/tag handling and hard-feature boundaries are preserved.
- Stable downward rain with three depths, variable tapered streaks, wind and light response. Unknown and remembered-only pixels remain protected. Rain/snow/fog/cloud changes never mutate authoritative weather or time.
- House artwork normalized to player-relative doorway scale. Exact drawn-alpha pointer regions replace broad cell hitboxes. Saved physical footprints, collision and door identities remain unchanged.
- WORLDGEN9 for new worlds: physical climate, fertility, exposure/shelter and coherent warped cover patches produce connected woodland/meadow/tundra/scrub/rock margins. Existing v8 geology, climate, coasts, water, cave and route systems remain the causes; no second terrain authority or resource layout was invented. Legacy geography is frozen. See [version and audit details](../development/WORLDGEN_V9_NATURAL_LANDCOVER.md).

## Validation

The combined graphics/house/main-game/material/version suite passed 105 tests
locally before the final per-world cache lifecycle refinement, which passed its
own unloaded-world regression. An additional compatibility suite passed 47 tests (including overlapping
version checks), covering legacy reference scenes, terrain performance/variants,
package contracts and saved v8/v7 compatibility. Direct worldgen physical/cache/
coast checks and twelve actual startup/resource audits passed; exact metrics are
in the worldgen document. Final CI outcomes are recorded at closeout.

Actual main-game GPU camp, village and interior screenshots were reviewed at
fractional camera coordinates; the natural seed `natural-v9-0` at (-448,832)
was prepared using real version9 terrain/resources and production discovery,
then captured through GpuTerminal with unchanged authority fingerprint. This is
Linux SDL offscreen / Mesa llvmpipe software evidence, not Windows hardware
performance. Same-snapshot rain comparison measured brightened coverage reduced
from 14.09% to 4.05% on the controlled flat-field test; this is a visual-density
metric, not a frame-rate result.

`bootstrap_smoke.py` still fails on a literal `tag:binding_material` recipe
request; it was reproduced identically on explicit v8 and v9. Full bootstrap is
not claimed green. No unrelated recipe/tool behavior was changed.

## Playtest and next work

Use the newest full main-game Windows GPU build, not older temporary-scene
artifacts. New Game is required to test version9 land-cover arrangement; loaded
older worlds receive rendering improvements while preserving their geography.
Inspect rain day/night/wind, forest/meadow/rock/water boundaries, fractional
camera movement, mixed material corners, houses at multiple scales/door sides,
hover transparent corners, enter/leave/save/reload and fog memory.

W4 is not complete: true directional shadows, broader occluded/fueled lights,
canopy/roof rain interception and splashes, hardware acceptance and performance
budgets remain open. Existing engine optimizations and legacy renderer survive.

Publication commit, GitHub gates and replacement executable link will be recorded
below after reviewing actual outcomes.
