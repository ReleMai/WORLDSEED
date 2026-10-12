# Crafting material progression — focused handoff

Baseline: WORLDSEED main after the discovery/salvage workbench integration.

## Changes
- Existing item IDs and artwork remain unchanged. Twenty-one material families gain precise semantic tags: fibrous plants, fine-floss plants, pulp feedstocks, combustible tinder, sharp stone edges, short handles, and structural shafts.
- Plant scraps can be dried/packed (10 scraps -> one 300 g brush bundle) for the existing campfire construction cost. The existing brush offcut recipe yields only 8 scraps, so repeated processing cannot multiply brush.
- Mixed nettles, reeds, beachgrass and other fibrous plants can be stripped to prepared fiber. Fine seed-head fibers are an alternative. Existing prepared-fiber -> cordage -> line and textile chains remain available.
- Mixed plant material and clean water make pulp for downstream paper/binder production.
- Stone knife, pick, hammer, and hoe accept appropriate tagged handle/head/binding substitutes. The stone axe continues to require a struck edge, a weight-bearing stone and a branch, but accepts plant/sinew/reinforced cord as lashings.
- Discovery clues use the existing 1–5 physical-item matching contract; no recipe is learned by opening a panel. Crafting uses the existing overlap-safe ingredient allocator. NPC settlement recipes remain exact-input only because their production authority does not yet reserve tagged alternatives.
- Authored salvage-content regeneration explicitly preserves these semantic tags.

## Verification
- Static checks: all item references and tag alternatives exist, all recipe clue signatures fit 1–5 slots, and every tagged recipe conserves mass with its lightest legal ingredients.
- Regression module: `tests.test_crafting_material_progression` covers wild plants through a hafted knife, mixed alternatives, salvage-to-campfire tinder, pulp production, stone axe ingredients, discovery hints, and mass balance.
- Also run `tests.test_tagged_crafting`, `tests.test_crafting_expansion`, `tests.test_rc7_early_game.RC7EarlyGameTests.test_primitive_bootstrap_graph_has_no_wood_before_axe_dependency`, and `tools/build_crafting_economy.py --check` (expansion NPC processes are unchanged).

## Boundaries
No save-schema, geography, UI framework, sprite ID or profession production changes. Follow-up: when NPC production supports tagged ingredient reservations, broaden generated profession recipes instead of adding a second economic crafting ledger.
