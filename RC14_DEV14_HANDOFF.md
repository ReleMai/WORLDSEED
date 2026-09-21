# WORLDSEED RC14 Embodied World Dev14 handoff

This bounded maintenance pass fixes the reported issue where pressing **Q** appeared to crash/close the game.

## Root cause
The pygame backend used the exact same raw key token (`"q"`) for two unrelated events:

1. an actual **Q/q keyboard press**
2. the operating-system **window close** (`pygame.QUIT`) event

`worldseed/ui/router.py` then classified `q` as `Intent('quit')`.

As a result, pressing Q during gameplay did not hit an exception in the renderer or simulation. It entered the immediate quit path:

- `_save(ctx)`
- return `'quit'`
- close database
- restore terminal/window
- exit application

From the player's perspective this looked like a crash because the game disappeared immediately with no confirmation.

## Fix
### `worldseed/ui/pygame_terminal.py`
- `pygame.QUIT` now returns the dedicated token `"QUIT"` instead of `"q"`.
- This separates a real OS close request from ordinary keyboard input.

### `worldseed/ui/router.py`
- only the dedicated `"QUIT"` token maps to `Intent('quit')`.
- ordinary `q` / `Q` is now inert during gameplay.
- quitting remains available through the existing safe flow:
  - **Esc -> Pause -> Save & quit WORLDSEED**
- clicking the window close button still performs the normal save-and-quit path.

## Regression coverage
Updated tests now explicitly verify:
- `classify_key('q')` -> `none`
- `classify_key('Q')` -> `none`
- `classify_key('QUIT')` -> `quit`
- pygame's window-close handler returns `"QUIT"`, not `"q"`
- the old direct-q quit mapping is absent

## Validation
Focused validation completed:
- Python compile pass for `worldseed/`
- `tests/test_rc14_world_presentation.py`
- Q/router regression in `tests/test_ui_rc2.py`
- `tests/test_rc5_gameplay.py::RC5GameplayTests::test_mouse_and_paste_tokens_are_never_gameplay_commands`
- `tests/test_contextual_water_rendering.py`
- `tests/test_water_currents.py`
- `tests/test_asset_readability.py`

Result:
- **14 passed**
- **9 subtests passed**

## Changed files
- `worldseed/ui/pygame_terminal.py`
- `worldseed/ui/router.py`
- `tests/test_ui_rc2.py`
- `tests/test_rc14_world_presentation.py`
- `CHANGELOG.md`

No world-generation, save-schema, terrain, or simulation-state formats were changed in this maintenance pass.
