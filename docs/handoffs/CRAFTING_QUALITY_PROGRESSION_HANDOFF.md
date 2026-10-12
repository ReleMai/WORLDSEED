# Crafting material quality progression handoff

## Scope and state ownership

Fourteen existing player recipes now opt into deterministic material quality. Recovered wood, metal and textile parts feed the same recipe IDs as conventional raw/refined stock, with recipe-local equivalent units making sound stock require fewer physical pieces. No item IDs, sprites, recipe outputs, stations, knowledge prerequisites, minutes or difficulty values are added or replaced.

The authored profiles cover Stone Knife, Stone Axe, Stone Pick, Stone Hammer, Crude Hoe, Iron Sword, Iron Pick, Iron Helmet, Short Bow, Wooden Bowl, Steel Sword, Steel Pick, Steel Helmet and Spun Yarn. Steel gear still requires its existing steel billet; recovered metal can substitute into iron forging, not directly manufacture steel. Existing scrap-to-fiber-to-cord-to-line and plant-pulp routes remain intact.

`ContentRegistry` owns authoring validation. `crafting_ingredients.resolve_recipe_inputs` owns physical allocation for player, named NPC, aggregate economy and workplace buffers. `CraftingSystem` owns player requirement previews and command execution. `ArtifactSystem` and existing metallurgy batches own instance quality/provenance; UI reads those systems rather than deriving a separate result.

## Public authoring and input contracts

- `ItemDef.crafting_quality`: integer 0–100, default 50. `crafting_source`: empty, `raw`, `recovered` or `refined`.
- `RecipeDef.input_units`: optional item-ID-to-integer map, 1–100, scoped to that recipe. `input_tags` remains a demand in logical equivalents. `material_quality` defaults false and explicitly opts a recipe into graded output.
- Weighted tag capacity is physical count times that recipe's factor. Shared overlapping allocation reserves exact inputs and catalysts first; final physical consumption rounds the total equivalents per item upward once, across all matching tags. Spare equivalents are processing waste, not newly minted partial inventory.
- Discovery clues still use one actual physical sample per clue, independently of full batch costs. Existing discovery authority and read-only browsing remain unchanged.

Examples, all preserving the same recipe ID and finished output:

| Recipe | Recovered route | Conventional route |
| --- | --- | --- |
| Stone Knife | 2 wood pieces + sharp flake + cord | 1 branch or handle + sharp flake + cord |
| Stone Hammer | 6 wood pieces + stone + cord | 1 sound branch + stone + cord |
| Iron Sword | 25 metal scraps + 25 wood pieces + hide | 1 iron bloom + 1 wood stock + hide |
| Spun Yarn (2) | 30 cleaned cloth scraps | 2 prepared fiber bundles |

Wood equivalents use a conservative 120 g basis, metal 80 g, textile fiber 10 g. Per-recipe factors honor each stock's actual mass. `audit_profiles` uses rational minimum grams per equivalent across every valid tag alternative; rounded physical consumption can only increase this lower bound. No existing item mass or nutrition is changed.

Twenty stock definitions have explicit grades. Recovered metal/wood/cloth pieces are grade 25; raw branch is 55, raw timber 60, hardwood blank 80, planed board 85, iron bloom 80 and steel billet 95. Processing a recovered component through a recipe without graded output can intentionally produce ordinary prepared stock; the entire historical intermediate tree has not been converted to provenance-bearing stacks.

## Quality, gameplay and UI

The player preview reads the concrete allocation selected by Auto, Refined or Recovered material preference. Auto favors the better authored stock grade for opted-in recipes; preferences affect selection among available sources and never grant missing items. Preview and execution use the same preference and skill/workstation bonuses.

Input quality reads owned instance quality and condition first, then actual owned metallurgy batch quality where relevant, then authored stock grades. Legacy untracked metal keeps its established fallback grade 50. Mass weights the inputs, while the head/blade/body retains an appropriate material family even if heavy shaft inputs dominate total mass. The preview exposes exact physical counts, input grades/source and resulting grade/benefits before crafting.

New graded outputs use existing `ArtifactState.components['crafting']` metadata with `quality_version=1`. Damage/protection uses effective quality; durability converts physical wear with a retained fractional remainder so small hits still accumulate. New instance trade value follows quality. Existing artifacts without this marker retain their legacy durability/value behavior.

Inventory detail exposes input provenance, output quality, condition, durability and value effects. Market quantity quotes use the exact stable instance order transferred, including mixed-quality stacks; ordinary untracked units keep the commodity quote. Existing physical transfer paths move associated metadata, and consumed intermediate markers are removed instead of outliving their goods. Notable consumed gear retains its normal artifact history.

UI observation does not spend materials, advance time, discover recipes or generate geography. No movement key bindings are added.

## Persistence, RNG and performance

Save schema remains 3. No new persistent state fields, migration or world-generation versions are introduced: existing artifact component dictionaries and metallurgy batch state carry the metadata, with safe legacy defaults. No RNG namespace is added or reordered. Output grading is deterministic from consumed sources and existing skill/station inputs.

Allocation is bounded by existing physical stock types and recipe tags; batch capacity uses the existing bounded binary search. No terrain, hydrology, settlement or population scan is introduced. Graded intermediate metadata ends when its physical material is consumed; this work does not add a persistent history collection.

## NPC limitation

Player-crafted outputs receive material-dependent quality, wear and trade effects. Exact NPC `complete_process` and aggregate/workplace production currently place generic item outputs; they do not invoke the player's artifact/metallurgy grading pipeline. Both still consume the same real weighted ingredients through one shared resolver and conserve the same physical stock authority. NPC output-grade propagation is a later dependency, not claimed complete here.

## Modules, regeneration and validation

Code: registry, crafting, crafting ingredients/quality, metallurgy, artifacts, combat, commands/engine, app, crafting/workbench panels and trade quotes. Authored content: items, recipes, settlement processes. No new assets.

`tools/build_material_crafting.py` is the deterministic profile authoring source; `--check` validates synchronization and mass bounds without writing. The salvage and historical RC7 generators reapply profiles. Salvage regeneration now preserves all prior fiber/cloth/cord tags and recipe order. `tools/build_crafting_economy.py --check` validates the NPC catalog and avoids a duplicate process for the new tag-aware expansion yarn recipe.

Final local validation:

- `python -m compileall -q worldseed tools tests`: passed.
- Bounded coherent regression run: **200 tests passed in 7.1 s** across material allocation/content, player quality, exact instance lifecycle, UI, discovery/salvage, NPC material use, economy, component crafting and hunting. Includes marked bow shot damage/wear and no stale metal grade after shearing/experiments.
- Original dirty working checkout: surgical integration preserved unrelated changes; bounded compilation and **107 focused tests passed**. Recovery snapshots are kept in ignored `artifacts/quality-integration.tmp`.
- Both material profile and crafting-economy authoring `--check`: passed (20 stock grades, 14 recipe profiles, 242 expansion NPC processes across 19 professions).
- Representative SQLite save with crafted sword/yarn: roundtrip and `tools/verify_save.py` passed; corrupt optional crafting metadata is rejected.
- Automatic Fast Gate includes the five new regression modules in its existing 90-second material progression check. It runs on this publication; remote status is reported separately.

Broader exploratory checks found existing mouse HUD/sprite-roster expectations and a storage fixture asserting all world containers are empty after dismantling one chest. Those unrelated assertions were preserved. Concurrent main commits `e996f93` and `8528b1b` refreshed the previously stale biome catalog and its rounding. This work rebased onto both; all 8 biome-atlas tests pass. This unit changes no assets. No full RC14 release gate or live Windows play session is claimed.

Next dependency: preserve these shared allocation contracts if adding more material profiles or future NPC instance-quality production; extend conservation and metadata-transfer regressions for that slice.
