# WORLDSEED RC14 Dev18 — Graphical Survivor Appearance Picker

## This pass focused on
Adding a true graphical character appearance preview screen so players can visually choose from the new male/female survivor sprite sets instead of picking from a plain text list.

## Implemented
- Added a new startup helper: `_appearance_menu(term)` in `worldseed/ui/startup.py`.
- Added a pygame-native visual picker: `PygameTerminal.present_sprite_gallery(...)`.
- The new picker now:
  - shows a graphical gallery of the survivor sprites
  - supports **male/female toggling** on the same screen
  - shows **10 looks per sex**
  - highlights the currently selected sprite
  - shows a larger preview card for the active selection
  - lets the user navigate with **arrows or WASD**
  - confirms with **Enter/Space** and backs out with **Esc**
- Kept the old text-menu path as a fallback for non-pygame terminals.
- Updated the startup wizard to use the new combined appearance selection flow.
- Bumped build version to `1.0.0-rc14-dev18`.

## Controls on the new screen
- `Left / Right / A / D` → move across appearance choices
- `Up / Down / W / S` → move between rows
- `Tab` (also `Q` / `E`) → toggle Male / Female set
- `Enter` or `Space` → confirm
- `Esc` → back

## Validation
- `PYTHONPATH=. pytest -q tests/test_player_appearance.py tests/test_asset_readability.py`
  - **5 passed, 4 subtests passed**
- `python -m compileall -q worldseed tools/import_dev17_generated_assets.py`

## Notes
- Save persistence for `player_sex` and `player_sprite_index` remains intact from Dev17.
- The visual gallery is presentation-only and does not change the build/point-buy logic.
- The fallback text selection path is retained to preserve compatibility with the ANSI terminal backend.
