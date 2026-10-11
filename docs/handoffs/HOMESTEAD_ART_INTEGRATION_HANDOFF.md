# Homestead Cabin Art Integration — October 2026

## Repository / handoff
Feature commit: `b02b3e3bda00cd3b6fe09d642a200dac6e3e04b0`
Fast-gate Actions: https://github.com/ReleMai/WORLDSEED/actions/runs/38103948473

## Implemented

- Imported 10 individually transparent generated artwork PNG sprites under `worldseed/assets/sprites/buildings/homestead/log_cabin_01.png` … `log_cabin_10.png`. Each is a separate, versioned GitHub binary blob.
- Original catalog `worldseed/data/homestead_catalog_v1.json` already references these exact paths.
- `worldseed/ui/homestead_panels.py` Build carousel now prefers the real packaged PNG for each style rather than the old procedural drawing. Procedural preview remains a fallback if a local installation is missing art.
- `worldseed/ui/homestead_art.py` resolves catalog art and maps the physical `doorway(site)` to the 3×3 tile grid; door threshold follows all 4 blueprint orientations, and south-facing artwork is shifted using per-style painted-door anchors.
- `worldseed/ui/pygame_terminal.py` paints the same PNG in the translucent blueprint placement preview and on the world map after frame construction. Stage 0/1 remain footprint and foundation markers; stage 2 and 3 render semi-transparent construction art; stage 4 renders the completed exterior at full opacity.
- Hitboxes, site footprint, material deposits, stage eligibility and physical entrance edge stay authoritative in `homestead_blueprints.py`.
- `tests/test_homestead_art.py` added 5 tests checking 10 unique real PNGs, their alpha, catalog anchors, physical doorway for all 40 style×rotation pairs, render loading and Build carousel integration; `.github/workflows/fast-gate.yml` includes these tests in early smoke.

## CI
GitHub Actions run 38103948473 passed graphical diagnostics, Python compileall and the combined early homestead tests (prior blueprint/pointer/panel tests plus new art integration tests). The overall Fast Gate remains failed due to the pre-existing Dev62 portrait catalog hash mismatch, unrelated to this art pass.

## Known limitations / future work
- These are **isometric 3/4, south-view authored sprites** extracted from a common generated art contact sheet. The west/north/east directions maintain upright artwork (with perspective flip where appropriate) and paint the **precise actual door edge**. They are NOT four individually authored camera-accurate elevations. For perfect visual door facade placement on non-south facings, create and register direction-specific east/west/north PNGs and use them in `draw_cabin_art`.
- Graphical doorway markers are correct; they **do not yet implement a functioning interior/enter command** for these player cabin sites.
- The current 3D-isometric painted style is scaled to the game's top-down 3×3 tile footprint, which may need zoom-aware visual tuning.
- Binary PNGs committed into the repository are alpha-keyed and quantized from the generated art contact sheet. Preserve the independent originals when authoring directional upgrades, and avoid reintroducing right-click empty-ground placement or full-screen menus.

## Validation commands
```sh
python -m compileall -q worldseed tests
python -m unittest -v tests.test_homestead_art tests.test_homestead_blueprints tests.test_homestead_ghost_ui tests.test_homestead_panels
```
