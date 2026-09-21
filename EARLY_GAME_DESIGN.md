# WORLDSEED RC7 Early-Game Design

## Design goal

RC7 rebuilds the opening hours around one rule: **the character begins with nothing**. No tool, food, money, medicine, container, weapon, recipe kit, objective, or class package is granted. Character creation defines capability; the world supplies opportunity.

The start is not a tutorial corridor. It is a sandbox bootstrap in which loose natural materials can become the first tools, those tools unlock heavier resources, and those resources open hunting, preservation, construction, cooking, agriculture, exploration, and trade.

## Zero-supply invariant

A new character's inventory must be `{}` at creation. The spawn algorithm may choose a fair region, but it must never create supplies, mark resource locations, or disclose a prescribed route.

Release checks require every sampled start to provide naturally occurring stone, branch, and fiber/brush within a short search radius while keeping the exact locations undisclosed. Water and edible forage are desirable but not guaranteed at the player's feet.

## Bootstrap loops

### Primitive materials

- Loose stone -> stone flakes, sling stones, hammer/pick heads.
- Fallen branches -> hafts, fuel, crude furniture, spears.
- Brush/fiber/bark -> cordage and bindings.
- Forage -> immediate calories, herbs, possible future seeds.
- Natural water -> immediate drinking risk/reward and cooking support.

### Primitive tools

Stone flakes are the first cutting edge. Cordage binds improved tools. The intended progression is:

`empty hands -> loose stone/branch/fiber -> flake/cordage -> knife/axe/pick/hammer/digging stick -> workstations -> advanced processes`

Tool *qualities* are the contract. A process asks for cutting, skinning, scraping, mining, hammering, tilling, digging, sewing, etc., not a hard-coded item name. Better quality improves speed or outcome.

### Shelter and furniture

Every buildable furniture piece must do useful work. Early structures include:

- campfire: heat, cooking, light, primitive hardening;
- brush lean-to: shelter and exposure reduction;
- sleeping mat: rest/recovery;
- storage basket/chest: physical storage;
- crude work surface/workbench: crafting speed/work quality;
- butcher table: carcass-processing bonus;
- drying rack: meat/hide/herb preservation;
- tanning frame: leather production;
- beams/pillars/roofs/walls/gates: structural shelter and enclosure.

## Hunting and carcass economy

Killing is only the beginning of animal use. Animals leave carcasses with species, mass, damage-derived quality, kill time, and processing state.

- Skin first to preserve hide quality.
- Butcher to obtain meat, fat, and offal.
- Debone after butchery to recover bones and sinew.
- Delay reduces carcass quality; neglected carcasses become unsafe.
- A butcher table and good cutting tools improve processing.

Carcass products intentionally have multiple sinks:

- meat -> roast/stew/broth/drying;
- hide -> scraped hide -> rawhide or leather;
- bone -> tools/needles/stock/broth/fertilizer pathways;
- sinew -> strong cordage and equipment;
- fat -> cooking, preservation, soap;
- offal -> food/bait/future animal-feed or fertilizer systems.

## Dynamic cooking and nutrition

Meals are composed from actual ingredients rather than selected from hundreds of fixed recipes. Current cooking methods are roast, stew, porridge, and broth. Each method specifies stations/cookware, ingredient categories, water needs, time, and modifiers.

The resulting meal inherits calories, protein, carbohydrates, fat, fiber, hydration, food groups, satiety and effects from its ingredients. Prepared meals have finite shelf lives.

Nutrition uses a rolling seven-day model with broad diet groups: protein, vegetables, grains, fruit, and fats. Immediate hunger and long-term diet are separate. A diverse adequate diet can improve recovery, stamina, or cold resilience without turning nutrition into a medical simulator.

## Farming

Crops are wheat, turnip, barley, beans, cabbage, carrot, onion, and flax. Farming requires a tilling-quality tool. Crop definitions own their growth duration, temperature/water envelope, disease family, yields, and N/P/K demand. Rotating crops with different demands reduces repeated depletion and disease pressure.

Wild plant resources can provide seeds where appropriate, so agriculture can emerge from exploration rather than requiring a starter seed packet.

## Ecology and foraging

Authored natural resources and animals have habitat/climate envelopes. Forage uses terrain, moisture, temperature, season, patch scale, density and regrowth. Animals use regional habitat suitability and local passability when populations materialize.

The player does not automatically know ecological population counts. Better Naturalism/Survival or reports from knowledgeable NPCs can improve estimates.

## UI principles

Crafting and construction are grouped by purpose rather than presented as flat lists. Entries show READY/NEEDS, readable material names, station/tool requirements, time, and what the result enables. Ingredient-based cooking previews nutrition before confirmation.

The UI should explain *consequences*, not engine internals.

## Release gates

RC7 is not considered complete unless:

1. zero-item bootstrap succeeds from generated landscapes across many seeds;
2. no primitive recipe contains a circular dependency;
3. every item has direct utility or a downstream sink;
4. every furniture piece declares and implements a purpose;
5. forage and species reference valid items/habitats;
6. meals/carcasses/jobs/diet survive serialization;
7. full legacy regression suite remains green;
8. long-world invariant tests remain green.
