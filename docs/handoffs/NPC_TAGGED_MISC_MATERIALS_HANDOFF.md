# Tagged miscellaneous materials and NPC crafting: work-unit handoff

## Scope
The existing 252 salvageable miscellaneous finds now have explicit deterministic source-family tags, including 180 village objects, 48 wild botanical finds, and 24 animal byproducts. Every find retains its original guaranteed multistage salvage outputs and rare odds. Fourteen quick-recovery recipes produce a single conservative common component; multistage salvage remains the better recovery source and preserves rare recovery. Wild botanical material can also enter plant-pulp processing.

Shared `resolve_recipe_inputs` handles exact quantities, overlapping tag alternatives and catalysts for both player and NPC production. Named work orders persist the exact materials they will consume. Aggregate town production and workplace buffers use the same tag resolver and bounded batch-count search. No visual callback becomes a new simulation authority.

The economy catalog has 25 NPC processes for all tagged player recipes (14 new recovery routes plus 11 previous tagged recipes). Existing 242 authored profession recipes and NPC definitions remain unchanged. NPC processes read tag rules through their linked recipe rather than duplicating ingredient-definition authority. All source IDs, save schemas, sprites, hydrology and settlement-plan data remain stable.

## Validation and limitations
Static authoring checks require 252/252 item-to-recipe coverage, 1–5 physical discovery clues, tag existence and no mass creation for the lightest tagged input. New tests are in `tests.test_npc_tagged_materials` and updated `tests.test_tagged_crafting`. Fast-gate steps exercise these before the unrelated existing portrait fingerprint failure.

The NPC profession and workplace systems still require real stations, available physical inventory, paid market purchases or actual town stock. Tagged candidates cannot generate inventory from an empty buffer. Large scripted profession recipes stay exact for compatibility; future expansion to tag variants should be authored incrementally with per-recipe mass and nutrient audits.

## Generated content
`tools/build_salvage_content.py` reapplies source tags when rebuilding its 252 generated miscellaneous items.
`tools/build_crafting_economy.py --check` verifies both expansion NPC jobs and tagged NPC jobs.
