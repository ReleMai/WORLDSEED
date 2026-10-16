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
in the worldgen document. Final CI/build outcomes are recorded below.

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

## Published implementation and Windows test build

Implementation: [`aae1076`](https://github.com/ReleMai/WORLDSEED/commit/aae1076f8324878b901788b4c71c8b5dc5db4a40).
The final [Windows GPU main-game packaging run](https://github.com/ReleMai/WORLDSEED/actions/runs/38942972726)
passed its frozen executable/import/asset self-check and startup probes.

- [Download the Windows full main-game candidate](https://github.com/ReleMai/WORLDSEED/actions/runs/38942972726/artifacts/12064062433), then extract and run `PLAY_WORLDSEED_GPU.bat`.
- Artifact name: `WORLDSEED-Windows-GPU-CANDIDATE-e14c04810d57d4a967cefe36236665c1d8a10c9e`; 444,442,618 bytes; retention expires 2026-11-15.
- GitHub artifact digest: `sha256:7cd709037044d509d2c0716c6f1860e6c10b0e7e5c17a22f28aee28e30891a83`.
- Normal New/Load/Save and canonical gameplay commands are the entrypoint; saves remain under `%LOCALAPPDATA%\WORLDSEED\saves`. Select New Game to test v9 land cover.

The hosted driver is Microsoft GDI Generic/OpenGL 1.1. Main and QA render probes
reported `unsupported-hosted-driver-rejected`; they supplied no Windows GPU
screenshots or frame-rate evidence. The successful package is a test candidate.

Reviewed software pixel evidence is retained with the repository:
[clear landscape](../evidence/w4-landscape/natural-v9-clear.png),
[rain landscape](../evidence/w4-landscape/natural-v9-rain.png) and
[capture metadata](../evidence/w4-landscape/capture.json).
These are real v9 terrain/resources through the main-game GPU renderer with
production discovery and an unchanged authority fingerprint. The source was
prepared before capture; Linux llvmpipe supplied the pixels.

## CI fixture repair

The first implementation [Fast Gate 38926236393](https://github.com/ReleMai/WORLDSEED/actions/runs/38926236393)
passed six of seven jobs, including the W4 contracts and GPU/main-game checks.
World UI failed in the same three steps as the starting-branch
[run 38850851258](https://github.com/ReleMai/WORLDSEED/actions/runs/38850851258):
interior entry/stairs now record light-limited exploration, but lightweight test
simulations lacked the clock or `environment.visual_conditions` interface.

The shared portal fixture now supplies `GameClock` and pure `LightingSystem`
samples; the standalone floor fixture supplies its state clock. No production
behavior, gameplay assertion or CI gate was weakened. All four affected modules
passed **46 tests in 13.9 seconds** under a 90-second bound. The fixture follow-up
changes tests/documentation only; the final executable also includes the house
edge refinement described below.

[Crafting/Discovery regressions 38926236160](https://github.com/ReleMai/WORLDSEED/actions/runs/38926236160)
passed on the implementation commit.

## Final house-edge parity refinement

Review found a one-pixel conservative mismatch: GPU scissors used fragment
centers after the terrain seam fix, while house pointer masks still rounded
both clip edges inward. Pointer admission now uses the same half-open bounds at
pixel centers as drawing. A coverage-set regression compares pointer results
with actual `pixel_clip` output across fractional edges, exact half-pixel ties
and adjacent clips. All **18 house/building tests** passed under a 90-second
bound; **13 packaging tests** passed separately. Hidden/transparent pixels stay
unselectable and saved physical collision is unchanged.

The Windows packaging workflow now watches GPU house source/tests. The final
full-game executable linked above includes this production refinement and
supersedes the earlier `aae1076` package.

Final production revision: [`e14c048`](https://github.com/ReleMai/WORLDSEED/commit/e14c04810d57d4a967cefe36236665c1d8a10c9e),
including fixture/evidence follow-up [`8b6c44a`](https://github.com/ReleMai/WORLDSEED/commit/8b6c44a08ed4928dc76a48d83c047fe08bc83fba).
Final runs: [Fast Gate 38942972746](https://github.com/ReleMai/WORLDSEED/actions/runs/38942972746)
and [Windows main-game build 38942972726](https://github.com/ReleMai/WORLDSEED/actions/runs/38942972726).
Both completed successfully: **all seven Fast Gate jobs passed**, including
World UI/interior regressions, settlement/economy, NPC conservation, building
geometry, W4 contracts and main-game integration contracts. The final frozen
executable self-check passed; its native render/main/QA probes again reported
`unsupported-hosted-driver-rejected` on GDI Generic/OpenGL 1.1.

Hosted Linux optional graphics tests skip when EGL is missing (and the pure
contract job intentionally lacks ModernGL). The fractional house-pointer
coverage regression passed on CI. Actual shader/window pixels were exercised
locally through Mesa llvmpipe as recorded above; CI success must not be read as
native hardware acceptance.

Next coherent W4 work should add an admitted cover/ground mask for physical
roof/canopy precipitation interception, then directional tree/building shadows
and broader authoritative light occlusion. Keep existing contact shadows named
accurately. W5 still needs human native-Windows playtests, device recovery,
performance budgets and longer saved-world soaks. The existing bootstrap-audit
ingredient-tag helper failure above remains a separate tool issue.
