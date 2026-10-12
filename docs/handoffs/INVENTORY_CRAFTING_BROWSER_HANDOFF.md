# Inventory and crafting browser overhaul

The inventory now uses consistent alpha-cropped item icons, a responsive grid,
two-line item names, stack badges, readable category filters, and a selected-item
pane with pinned quantity/use/drop/store controls. The recipe browser uses labelled
primary tabs, consistent category subtabs, wrapped recipe rows, readiness labels,
and a full scrollable list of outputs, ingredients, tool/station requirements and
descriptions above a pinned Craft action. Search, workshops, discovery, the item
index and salvaging retain their existing navigation.

- Scope: `ui/item_browser.py`, `ui/crafting_browser.py`, `ui/pygame_terminal.py`,
  `ui/widgets.py`, filter/search route resets in `app.py`, focused tests, preview
  tooling and the existing fast-gate UI check.
- Public contracts: `UI_SELECT` and context/shift-click indices remain relative to
  the visible rows. `UI_SCROLL:<absolute>` and `UI_WHEEL:<index delta>` move only
  the viewport. Each retained menu frame supplies `selected_key`; a selected row
  outside the viewport is represented by selected index -1. Hover never changes
  inventory/storage/recipe action targets. Keyboard arrows explicitly select and
  reveal rows; inventory up/down move by grid column count. W/A/S/D still move
  the world, and companion panels retain their existing stack behavior.
- Persistent fields/migration and RNG: none. Scroll/selection are route-only UI
  state, detail offsets are bounded presentation caches, and no save schema or
  generation version changes. No new items/assets or simulation rules.
- Performance: capacity and drawing share the same geometry; only visible rows
  render. Normalized icon cache is bounded to 192 scaled surfaces, independent
  detail offsets to 32 items/recipes. Detail rendering is clipped and scrollbars
  support wheel, track clicks and dragging without changing selected quantities.
- Validation: full `compileall worldseed tools tests` and `git diff --check` pass;
  92 targeted tests pass under a 180-second runner (38.5 seconds). These cover
  real split/drop commands, hover and offscreen action identity, retained route
  restoration, keyboard grid navigation, category paging, minimum/standard/large
  viewport capacity, alpha sizing, bounded caches, and read-only panel rendering.
  All four generated inventory/crafting previews were visually inspected.
- Baseline evidence: the broader legacy mouse suite has two unrelated failures
  reproduced against the unmodified main renderer: an aggressive-stance HUD
  expectation omits the existing button, and an old roster test expects 24
  characters while the current manifest has 20. These assertions are unchanged.
  A broad UI RC2 run reached its 90-second deadline during repeated generated
  world setup; focused lightweight navigation tests pass. No enlarged retry.
- Known limits: validation uses real SDL surfaces with the dummy driver and
  command fixtures; it is not a live gameplay session or a full release gate.
  The terminal backend retains its text presentation. Container storage keeps
  its existing dual-pane layout, with the same stable hover/selection fix.
- Next dependency: live playtest with a large carried collection and real
  workshop recipes; release hardening remains the deliberate manual full gate.

Use `python tools/preview_item_browsers.py` to reproduce the four panel images in
`artifacts/ui-browser-preview/` without loading/generating a world. The work unit
was based on canonical main `8b436e4323c72c9b7e8fd5e47b32c060322992c6` in a clean
managed worktree, preserving the original checkout's pre-existing changes.
