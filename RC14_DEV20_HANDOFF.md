# Dev20 — clean survivor art and crafting crash repair

Scope: pygame feature renderers, character atlas import, visual manifest, graphical regression tests.

Root cause: Dev19 introduced ten calls passing a positional scale to the keyword-only `_draw_item_icon(..., *, scale=...)` helper. Recipe inputs, recipe details, experiments, component designs, the tech tree and inventory details could raise TypeError. Reproduced using real SDL rendering and fixed all ten callers with `scale=`. No broad exception swallowing or changes to crafting rules.

Art: 20 selectable appearances (10 male / 10 female), 24 NPC variations from an authored RGBA atlas. Consistent front-facing stance, adult proportions, clothing silhouettes and baseline. Sprites are 160x256 RGBA with 240px figure height. Manifest references connect the artwork to both the picker and world actors. Character images use cached smooth scaling; preview is vertically centered. Existing sex/index saves continue to select the corresponding new artwork.

Source: artifacts/source-art/dev20_survivors.png. Reimport with `python tools/import_dev20_characters.py` (pygame-ce). Generated with the built-in image tool. Prompt: professional clean hand-painted grounded wilderness RPG adult survivors, varied skin tones/hair/practical clothing, consistent full-body front-facing pose, isolated silhouettes and transparent background. Final extraction source retained generated alpha. Atlas delivered 24 figures in 6x4; explicit cell bounds preserve complete silhouettes.

Public contracts: unchanged. Persistent fields, schema and worldgen versions: unchanged. RNG: none introduced. Performance: scaled images remain cached; 24 bounded NPC alternatives. UI browsing remains observational.

Tests: real pygame regression covers home/categories/recipes/experiments/details/designs/components/materials/tree and inventory home/items/actions/details; verifies simulation and inventory unchanged. Alpha/canvas checks cover all 20 player sprites. Existing persistence and navigation tests retained.

Also repaired a pre-existing new-game NameError: `_load_context(sel)` referenced undefined `selection` for appearance. Reads now use `sel` with defaults for legacy tuple callers; regression verifies female/index 8.

Limitations: static character sprites, not directional walk-cycle animation. SDL dummy-driver verification does not replace a Windows desktop playthrough. See DEV20_VALIDATION.md for exact outcomes and broader-suite findings.
