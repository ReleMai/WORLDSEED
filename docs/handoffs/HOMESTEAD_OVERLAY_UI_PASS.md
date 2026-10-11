# Homestead UI — Floating Cabin Catalog and Material Depot
Date: 2026-10-10
Feature head: 9cb2383d65cc002247e25e581d3215d377e27c08
GitHub Actions run: 38101713848

## Delivered
- Main-game HUD Build now opens the **log cabin catalog as a floating panel over the currently rendered gameplay scene**. The rest of the world remains visible; no full-window selection screen opens for log cabins.
- Cabin catalog has a central **style-specific illustrated preview** and left/right arrow buttons, plus keyboard Left/Right, numbered 01/10 .. 10/10, "Place blueprint" and "Other structures".
- The illustrated concept previews are deterministically rendered in Pygame from the 10 catalog style definitions (roof, trim, door, accents). If a matching authored PNG is installed in the catalog's asset path, the panel automatically uses that PNG instead. These generated previews are **not yet final production-authoring art**, nor do they change building structure/simulation geometry.
- Confirming catalog style preserves the established cursor ghost placement and rotation flow, without charging materials before placement.
- Right-clicking an existing player homestead tile directly opens a **new draggable/resizable floating material-depot panel** without a redundant context-action selection.
- Blueprint depot uses the **real registered inventory PNG art** for wood, reeds, clay, stone, and cordage, quantity supplied/required and currently carried, a depot progress meter, "+1" and "ALL" per-material deposits, a deposit-carried button, next-stage command, and an inline two-step remove/refund confirmation.
- No simulation or material state is mutated by the renderer. Inventory transfers and construction stage changes still use `DepositBlueprintCommand`, `AdvanceBlueprintCommand`, and `CancelBlueprintCommand`.
- Two-column material grid and bounded panel sizing support 800×520 windows.
- The existing non-homestead structure-building workflow remains available via the "Other structures" entry. That legacy workflow still uses older menus; it was intentionally not rewritten within this cabin-specific UI pass.

## Key code
- `worldseed/ui/homestead_panels.py`: rendering for the two floating panels and ten distinctive visual previews.
- `worldseed/ui/pygame_terminal.py`: panel presentation methods and responsive floating window defaults.
- `worldseed/app.py`: carousel selection loop, depot action loop, direct click dispatch.
- `tests/test_homestead_panels.py`: visual distinction, pointer actions, registered inventory icons, confirmation, completion, small window targets.
- `.github/workflows/fast-gate.yml`: the homestead early smoke test group includes the new panel regressions.

## Verification
On GitHub Actions run 38101713848, installation, graphical diagnostic tests, Python compileall, and "Log cabin blueprint and placement ghost" regression group PASSED. The latter now covers the new panels in addition to prior blueprint and placement tests. Remaining **full Fast Gate still fails in Dev62 legacy portrait catalog checksum validation**, unrelated to this UI change. No independent Windows manual visual playtest performed.

## Next
- Replace procedurally generated style catalog illustrations with final authored log cabin PNGs registered under `worldseed/assets/sprites/buildings/homestead`; align final exterior art, roof animation, and placement ghost.
- Migrate the existing non-homestead "Other structures" menus into the same over-game construction UI.
- Finalize placed cabin interiors/door entry and stage-specific world rendering.
