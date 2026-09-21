# WORLDSEED RC7 Content Economy Audit

## Current content surface

Release audit counts:

- 105 items
- 52 crafting/process recipes
- 23 structures/furniture definitions
- 8 crops
- 22 natural resource/forage definitions
- 17 authored animal species, plus procedural species
- 4 dynamic cooking methods

`python tools/audit_content.py` is a release gate and currently reports `CONTENT AUDIT PASSED`.

## Anti-clutter rule

An item is not accepted merely because it is realistic. It must satisfy at least one of these roles:

1. directly usable (food, medicine, tool, weapon, armor, knowledge);
2. process input for another useful output;
3. construction material;
4. equipment component;
5. storage/container function;
6. fuel/catalyst/ammunition;
7. trade/currency value backed by another role;
8. agriculture/fertilizer/seed role;
9. cultural/historical/knowledge artifact with gameplay consequences.

Items that cannot satisfy one of these are content clutter and should be removed, merged into a broader material, or given a meaningful process.

## Tool-quality economy

Processes request capability rather than exact item IDs. Examples: cut, skin, butcher, scrape, chop, mine, hammer, till, dig, sew. This allows a stone knife, metal knife, specialized skinning knife, or future magical edge to satisfy the same process at different quality/speed.

## Material chain examples

### Wood/fiber

fallen branch -> haft/fuel/crude structure
brush/bark -> cordage -> bound tools/weapon/furniture
mature tree + axe -> timber/bark -> construction/workstations/fuel

### Animal

carcass -> hide/meat/offal/fat/bone/sinew
hide -> scrape -> rawhide or tanning -> leather
meat -> cook or dry
fat -> meal enrichment / soap
bone -> tools / needle / broth / fertilizer pathway
sinew -> strong cordage

### Agriculture

wild plant -> food and sometimes seed -> field crop -> food/fiber/seed -> meals/materials
soil N/P/K + water + temperature + disease pressure -> yield

### Stone/metal

loose stone -> primitive edge/head/ammunition
rock/ore + pick -> stone/ore -> smelting/metallurgy -> durable equipment/components

## Furniture usefulness contract

Furniture must provide at least one implemented mechanical effect. Decorative-only furniture is deferred until social/aesthetic systems can consume beauty/prestige values.

Current examples include shelter, warmth, comfort, storage, crafting work bonus, processing station, cooking station, enclosure, crossing, structural support, or metallurgical workstation.

## Flavor text policy

Every item has both a factual description and short flavor text. Description explains physical/gameplay identity; flavor text supports imagination without hiding required mechanics. Numerical stats are shown where decision-relevant.

## Automated audit checks

The content audit rejects:

- undefined recipe inputs/outputs;
- resource yields that point to missing items;
- missing item descriptions/flavor;
- structures without declared uses;
- invalid crop seed/harvest links;
- invalid station references;
- obvious orphan items with no use or sink.

## Future audit extensions

- supply/demand simulation for all tradeable intermediate goods;
- spoilage sink verification;
- item value derived partly from process time/material scarcity;
- equipment component compatibility validation;
- automatic graph detection of unreachable recipes;
- biome-level availability simulations for rare inputs;
- settlement production-chain coverage.
