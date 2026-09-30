# Crafting and discovery pot handoff

## Scope

The Pygame crafting route now shares one retained, draggable and resizable panel across Recipes, Discovery Pot and Item Index tabs. The recipe tab groups known recipes by category, pages categories and recipe cards, dims uncraftable recipes, highlights missing quantities and conditions in red, and lists each product's quantity, item description, roles, skill and time. Item Index shows every catalog recipe involving the selected carried item, masking names until discovered.

The player places one to five carried items into the pot. The simulation validates actual quantities, enumerates matching undiscovered catalog recipes and chooses one via `hash_u64(world_seed, 'crafting.discovery_pot.v1', successful_attempt_count, sorted_ingredients)`. A successful attempt consumes the placed items, records the recipe and increments `player_crafting_experiments`. Failed or exhausted combinations do not consume items. A short item-flight and pot-glow animation runs only after the command succeeds. Single-item recipes remain learnable by experimenting with one item; multi-item combinations unlock more complex recipes. The terminal backend uses the same pot command without graphical animation.

## Contracts

- UI browsing and candidate/index queries are read-only. `DiscoveryPotCommand` is the simulation mutation boundary; existing `CraftCommand` still governs actual products and stations.
- Existing discovered recipe IDs and the experiment counter remain in the current save schema; no migration or new field is needed. Worlds with discovery disabled retain their visible recipe catalog.
- Fixed recipe selection and automatic recipe unlock on handling an item are disabled for discovery-enabled worlds. Handling still records item knowledge.
- The result pool derives from the current content catalog, so mods may add recipes without a separate discovery table. Placed item types and quantities must match a catalog recipe's inputs exactly, preventing unrelated or surplus materials from being consumed for a result.
- No global RNG or generated world state is touched by rendering. The 520 ms pot effect is presentation only.

## Verification

Focused Pygame and system tests cover cursor tabs, narrow panels, pagination, craftable/missing card states, deterministic outcomes, consumption, exhaustion, observation, legacy command rejection and state round-trip. Run `PYTHONPATH=repo python -m unittest discover -s repo/tests -p test_crafting_pot_ui.py -v`, `PYTHONPATH=repo:repo/tests python -m unittest test_dev16_caves_crafting.Dev16CraftDiscoveryTests -v`, and the Dev37 floating UI suite with dummy SDL drivers. `compileall` covers the changed Python modules. The fast gate runs the focused crafting tests after Dev37 UI tests. Full release validation remains the manual release gate.


## WU18 experiment-grid contract
- The player-facing discovery surface is now named Experiment Grid throughout the crafting flow.
- Recipe discovery uses an explicit physical clue signature of 1-5 items. Full crafting cost can be larger; large recipes must author a bounded discovery signature and registry validation enforces the contract.
- Cordage progression is unambiguous: one brush can be processed into loose Fiber, while two brush bundles reveal/craft actual plant Cordage.
- The early Crude Knife is a bark-wrapped stone flake with minimum skin/butcher/scrape capability, bridging primitive hunting into the hafted Stone Knife.
