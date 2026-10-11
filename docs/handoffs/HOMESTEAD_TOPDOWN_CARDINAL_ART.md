# WORLDSEED Top-Down Log Cabin Artwork — GitHub Sync and UI Handoff

Date: 2026-10-11

## GitHub access diagnosis

- Authenticated GitHub connector account: `ReleMai`.
- Repo `ReleMai/WORLDSEED`: `admin: true`, `push: true`, default branch `main`.
- The previous inability to push using local Git was a **container DNS failure**: `git ls-remote https://github.com/ReleMai/WORLDSEED.git HEAD` returned `Could not resolve host: github.com`.
- No repository permission change was necessary. Used the GitHub connector Git Data API to create 16 binary PNG blobs, create a tree and commit, then fast-forward `main` with a compare-and-swap expected SHA.
- Artwork commit: `8b1a1bcbf66026caf678c340131f6cdf64f32d4f`.
- Runtime code commit: `10a692eb644a00d97f3ad6b49c29570fe54b9142`.

## Artwork added

16 optimized transparent PNGs (448px maximum dimension, 256-color palette, ~1.15MB total), in:

`worldseed/assets/sprites/buildings/homestead_topdown/{cozy,rustic,mossy,fortified}/{north,east,south,west}.png`

Source: WORLDSEED_Topdown_Cabin_Integration_Pack.zip (provided for this work; the original full-resolution source remains available in the conversation artifact).

The authoritative style-family/rotation lookup is `worldseed/data/homestead_topdown_v1.json`. The 10 existing cabin catalog entries currently share these FOUR visual families; they are not ten independent new top-down designs. The ten previous isometric PNGs were preserved as fallbacks.

## Runtime implementation

- `worldseed/ui/homestead_art.py`: `topdown_cabin_asset_path(style_id,orientation)` and `topdown_manifest()` read the manifest and resolve each actual file; `draw_cabin_art` now chooses the directional sprite without mirroring. Uses per-direction painted-door anchors to position images relative to the authoritative entrance tile. The placement ghost and the stage-2+ world renderer both call this same function.
- `worldseed/ui/homestead_panels.py`: Build carousel displays the top-down south-facing art for each style as the initial preview (orientation chosen during placement). The existing over-game panel remains unchanged.
- Orientation index mapping matches `worldseed/systems/homestead_blueprints.py`: 0=south; 1=west; 2=north; 3=east. Physically legal sites, stored materials, collision, construction stages and saved game formats were not altered.
- `tests/test_homestead_art.py`: verifies all 16 distinct alpha PNGs resolve for every catalog style and cardinal facing, and the rendered door anchor matches the physically authoritative edge. Prior base art tests still pass.

## Validation

GitHub Actions: https://github.com/ReleMai/WORLDSEED/actions/runs/38167528899

Passed: installation, Python compilation, graphical diagnostics, `Log cabin blueprint and placement ghost` smoke suite including the new top-down art checks, and Linux process deadline tests.

Full workflow still fails in the pre-existing Dev62 portrait layer / version compatibility test. No manual native Windows game playtest occurred in this session.

## Known limitations

- Only four new base art families exist, assigned among the ten cabin style entries; style-specific top-down variants would improve visual variety.
- The generated sprites place the painted door near the center of its selected compass edge. Historical cabin styles with a left/right doorway use a positional alignment offset to bring the painted doorway to their actual gameplay entrance; art may overhang the reserved 3×3 footprint. A future authored pass should move the door within each sprite rather than translating the whole art image.
- Cabin interior entry is outside this art integration.
- Continue to avoid empty-ground right-click blueprint creation and retain cursor ghost placement through the Build UI.
