# WORLDSEED RC14 Dev19 — Graphical Inventory & Discovery Crafting UI

## Scope completed

Dev19 redesigns the pygame inventory and crafting interfaces around the actual game systems instead of presenting terminal-style text inside a window. The ANSI terminal path remains available and retains the same navigation/command authority.

### Inventory

- New **Pack dashboard** with the selected player sprite, total carried mass, estimated volume, stack/item counts, category distribution, and graphical section cards.
- New **Items grid** with real item sprites, stack counts, carried mass, pagination, and a selected-item preview pane.
- New **Item action screen** with a large item preview plus context actions such as inspect, drop, eat, equip, and store.
- New **graphical item detail view** using the real item sprite, pack statistics, description, uses, tags, and legacy detail text as a secondary information area.
- Storage/equipment/read actions still route through their existing authoritative gameplay systems; the redesign is presentation-only.

### Crafting

- New **Discovery Workbench dashboard** showing recipe discovery progress, ready experiments, examined materials, experiments completed, and crafting skill.
- New **recipe category cards** instead of plain text category rows.
- New **graphical recipe browser** with output sprites, READY/NEEDS state, result summaries, time, selected-recipe description, material counts, station, and skill information.
- New **recipe detail / craft confirmation screen** with output art and full material requirements.
- New **trial-and-error experiment browser** that reuses the graphical recipe presentation while highlighting material-clue discovery and experiment time.
- New **Material Discoveries grid** showing the actual sprites of handled material/item types.
- New **Discovery Tech Tree renderer**. It derives dependency depth from the real recipe graph, lays recipes into tier columns, draws visible parent/child connectors, and color-codes known / experiment-ready / locked states.
- New **Component Design browser** and graphical material-choice screen for modular sword, pick, helmet, and future data-defined component designs.

## Architecture

`ui/widgets.py` now supports optional structured presentation hooks:

- `presentation`
- `presentation_data`

The same `select_menu()` / `view_text()` widgets still own keyboard navigation, paging, ESC semantics, and terminal fallback. Pygame receives only observational structured data through `present_feature_menu()` / `present_feature_document()`.

The simulation remains authoritative. Browsing inventory, recipes, materials, or the tech tree does not advance time, discover recipes, consume items, or realize world state.

## Versioning

- Engine: `1.0.0-rc14-dev19`
- Package: `1.0.0rc14.dev19`
- Worldgen remains **7**. No geography/save-schema bump was required.

## Validation

Validated in this workspace:

- `python -m compileall -q worldseed`
- `tests/test_dev19_feature_ui.py`
- `tests/test_player_appearance.py`
- `tests/test_asset_readability.py`
- `tests/test_rc14_world_presentation.py`
- `tests/test_rc12_renderer.py`
- targeted inventory retained-navigation flows
- `tests/test_dev16_caves_crafting.py`

Combined targeted result before packaging: **24 tests passed** plus asset-readability subtests.

A live pygame screenshot could not be captured in this sandbox because pygame-ce is not installed and the environment cannot reach PyPI. The build already declares `pygame-ce` in both `requirements.txt` and `requirements-pygame-ce.txt` for the Windows/runtime environment.
