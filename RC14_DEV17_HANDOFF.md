# WORLDSEED RC14 Dev17 — Asset Integration / Character Appearance Pass

## What changed
- Imported the new generated art into the project tree through `tools/import_dev17_generated_assets.py`.
- Added **10 male** and **10 female** selectable player sprites under `worldseed/assets/sprites/player/`.
- Added **12 new grounded NPC variants** and wired them into the presentation manifest.
- Added broader **cave floor**, **cave wall**, and **cave entrance** variant pools.
- Replaced the core **coal**, **copper ore**, and **iron ore** item art from the new ore atlas.
- Updated animal/monster presentation so key species prefer the new grounded wildlife/monster art first.
- Added `player_sex` and `player_sprite_index` to `LivingWorldState` save data.
- Added survivor creation flow support for:
  - character name
  - sex selection
  - appearance selection (10 looks per sex)
- Updated the pygame renderer to draw the selected player sprite in-world.
- Added `requirements-pygame-ce.txt` and kept `requirements.txt` aligned with `pygame-ce`.
- Bumped the build marker to **`1.0.0-rc14-dev17`**.

## Validation
- `PYTHONPATH=. pytest -q tests/test_player_appearance.py tests/test_asset_readability.py`
  - **5 passed, 4 subtests passed**
- `python -m compileall -q worldseed tools/import_dev17_generated_assets.py`
- `VisualRegistry.coverage_issues(...)` returned **0 issues**.

## Important notes
- The new appearance selection is currently menu-driven in the startup flow; it is functional and persistent.
- Imported source sheets remain in `/mnt/data` for this workspace run, while the game-ready extracted assets are now committed inside the project tree.
- `tools/import_dev17_generated_assets.py` can be rerun if you want to regenerate the cropped in-game asset files from the source sheets.
