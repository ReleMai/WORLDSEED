# WORLDSEED Fast Gate — smoke regression handoff (2026-10-12)

## Canonical status
- Main work session has addressed the legacy checksum, NPC no-recipe work planning, deterministic movement test fixtures, homestead building-audit coverage, biome generated catalog/Markdown, world pickup transfer test fixture, and revised crafting navigation tab test.
- Fast Gate run **38269871868** (`273a045cfe122e0f5f903090f4e11f0d46f49986`): main **smoke: PASS**, settlement/economy **PASS** (prior run logged 134 passing cases), Linux **PASS**, full-day NPC conservation **PASS**, NPC 1-worker **PASS**. NPC 8-worker is long-running.
- All remaining world/UI checks have been moved to parallel `world-smoke`, with all 25 checks continuing after local failures and final step `Enforce world smoke results` failing if any check failed. This preserves test coverage while surfacing all errors in one run.
- **world-smoke: FAIL**, four actual failing checks: `smoke_08` Dev46, `smoke_09` Dev47–48, `smoke_13` Dev52, `smoke_15` crafting discovery. All 21 other world-smoke checks passed.

## Fix the remaining four failures, preserving behavioral constraints

1. **Dev46 continuous interiors**: `tests.test_interior_ai.InteriorAITests.test_legacy_state_without_interior_records_retains_outdoor_execution` at test line 85 expects NPC location `(4,4)` and sees `(3,4)`. Inspect the stubbed world/pathing and actual fixed-tick movement pace; adjust the physical fixture or the assertion to match current path rules, not by relaxing game collision.
2. **Dev47–48 building interactions/interiors**:
   - `tests.test_building_shells.BuildingShellTests.test_workshop_storage_moves_inside_without_copying_goods` calls `property_intrusion.sync_settlement`, which provisions scavenged village loot. Test registry stub is missing `items` used by `worldseed/systems/salvage_loot.py:candidates`. Use a production-shaped registry fixture.
   - `tests.test_exterior_pointer_routing` and `tests.test_dev47_building_context`: fake `sim` has no `homestead`, but `worldseed/app.py:_world_context_menu` now calls `sim.homestead.at(target)`. Supply an observational stub or robustly handle optional homestead service in context menus without exposing undiscovered actors/cargo.
   - `tests.test_interior_work.InteriorWorkshopTests.test_overflow_stays_at_continuous_station_and_cannot_repeat` line 137: `professions.complete_process` returned False. Check physical stock, tagged ingredient resolver, current recipe/proc consistency, and reservation duration; do not force success or mint inventory.
3. **Dev52 building variants**: `tests.test_dev52_building_variants`: empty-settlement test expected 0 reserved items but got 6; nearly every variant compared physically stored loot against `variant["loot"][:5]` and now sees authored salvage items outside that original list. Determine whether these are legitimately persisted authored village salvage finds or duplication/new stock. Test starting physical supplies vs granted salvage loot and correct expectations/source authority without deleting valid salvage content or enabling free item creation.
4. **Crafting discovery pot**: `tests.test_dev16_caves_crafting.Dev16CraftDiscoveryTests.test_material_discovery_requires_pot_for_recipe_branch` line 102: `discover` returns `These materials reveal no new recipe. Try another combination.` Determine what tags the test expects vs the updated recipe catalog (new material-quality and salvaging expansion). Preserve the discoverability of legitimate primitive material combinations and don't bypass the discovery pot or auto-grant recipes.

## Reproduction and next steps
- https://github.com/ReleMai/WORLDSEED/actions/runs/38269871868 — logs of the `World UI and content smoke` job (four failing checks, full stack traces).
- Run affected modules with `python -m unittest -v tests.test_interior_ai tests.test_building_shells tests.test_exterior_pointer_routing tests.test_dev47_building_context tests.test_interior_work tests.test_dev52_building_variants tests.test_dev16_caves_crafting`.
- Validate `python -m compileall -q worldseed tools tests`; update handoff and publish only validated coherent unit.
- Run Fast Gate once after publishing, inspect `smoke` and `world-smoke` independently; avoid starting another full long NPC lab repeatedly just for doc updates.
