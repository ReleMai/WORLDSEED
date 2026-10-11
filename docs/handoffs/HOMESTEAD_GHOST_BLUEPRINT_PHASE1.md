# Homestead Phase 1 — Build HUD & Cabin Ghost Handoff

Date: 2026-10-10
Canonical repository: ReleMai/WORLDSEED
Feature commit: d7da5cef4beae8917d1af7e4d15a448e621d9f84

## Implemented

- The existing main-game HUD **Build** button opens Construction > Homesteads > one of 10 log cabin styles. No longer asks for a keyboard direction before style selection.
- Picking a cabin enables a temporary mouse-placement intent in `PygameTerminal.begin_homestead_placement` and does not create or spend anything.
- A semitransparent procedural cabin footprint/roof/walls ghost follows the mouse across the current world viewport, including the actual 3x3 tile reservation, a gold doorway marker and blue exterior landing marker.
- Valid placements are green; invalid placements are red with a reason. Only prepared/known terrain may be previewed, keeping UI hover free of new world chunk realization.
- R rotates through four compass doorway orientations. Left-click on the map submits `UI_BLUEPRINT_PLACE:x:y:orientation`, then the authoritative `PlaceBlueprintCommand`; right-click or Esc cancels.
- Invalid placement leaves the preview active. Successful placement clears preview and leaves a persistent blueprint/deposit marker.
- Empty-world right-click menus no longer offer blueprint placement. Right-click on an existing placed blueprint still opens its material/storage/construction UI. Terminal-only fallback retains directional placement.
- `HomesteadBlueprintService.preview` and `place` now share identical clearance, ownership/overlap, visibility, distance and external-door checks.

## Verification

GitHub Actions run 38100539152 passed install, graphical diagnostics, `compileall`, and **Log cabin blueprint and placement ghost** (8 simulation tests + 6 UI mouse tests). Existing full Fast Gate still fails in Dev62 legacy portrait catalog SHA-256 fingerprint validation; unrelated to this feature and not resolved in this pass. No manual Windows GUI playtest performed.

## Known limitations / next development

- The ghost is a **procedural silhouette**, not one of the final 10 rendered style-specific log cabin sprites. The style selector uses stable IDs from `worldseed/data/homestead_catalog_v1.json`, but full sprite integration remains pending.
- The completed player cabin still needs a physical persistent doorway that opens into the interior engine and functional interior furnishing placement.
- Stage-by-stage construction art and a persistent moveable floating blueprint-depot window remain pending. Current deposit UI is the existing selectable modal.
- The original Dev62 portrait manifest fingerprint mismatch blocks full CI; avoid changing legacy portrait catalog without migration and verification.
- Do not add blueprint creation to right-click ground again. Keep WASD exclusively for movement.
