> **Dev21 controls:** WASD moves your character only. Click the HUD buttons for Inventory, Crafting, Build, Health, Map, Actions, World, Look, Help and Pause. Click menu cards; use the wheel or Previous/Next to page; Back or right-click returns. Character creation and target selection support the mouse. Typing names still uses the keyboard. Arrow/Enter/Esc navigation and existing game shortcuts remain available.

> **Dev20:** Clean rebuilt player/NPC art, crafting and inventory crash fixes, and new-character appearance startup repair. See `RC14_DEV20_HANDOFF.md` and `DEV20_VALIDATION.md`.

> **Dev16:** New worlds now use terrain-aware cave entrances/geology and the
> discovery crafting model. Grassland/floodplain and other ground types use a
> data-driven local mesher. Inventory/crafting use the new graphical panel
> renderer in the pygame client. See `RC14_DEV16_HANDOFF.md`.

> **Dev22 atlas:** Map now displays the actual prepared terrain and saved terrain edits. Use the mouse wheel or Zoom buttons, pan buttons or arrow keys, Center, and click terrain or a known-place icon to inspect it. Dark areas are uncharted or not yet prepared, not an invented biome. Known villages/cities, built camps, observed caves and discovered historical sites have illustrated markers. See `RC14_DEV22_HANDOFF.md` for coverage and compatibility limits.

# WORLDSEED v1.0 RC14 Development - Embodied World Foundation

> **Development status:** RC14 Dev30 continues **Hydrology v2** with a separately versioned morphology layer. New worlds use multi-point river centerlines, split/rejoining braided channels with natural land islands, materialized shallow oxbow scars, and rock-confined gorge banks. Surface caches are keyed by worldgen + hydrology + morphology so older Dev29 river projection remains stable.

WORLDSEED is a deterministic, persistent fantasy sandbox with a terminal-native information model and a new dedicated graphical window. The world is the durable protagonist: terrain, ecology, settlements, history, trade, disease, knowledge, magic, structures and consequences continue beyond any single character.


RC13 is the **Seeded World Preparation** release. New worlds now spend a deliberate loading phase generating and persisting a large deterministic exploration envelope around the selected spawn before gameplay begins. Terrain chunks and current-season natural-resource placement are written to the save and kept in runtime caches, so walking across ordinary early-game chunk boundaries reads prepared data instead of invoking the procedural generator inside the movement/render loop. WORLDSEED remains deterministically unbounded: travel beyond the prepared envelope still expands from the same seed, while the normal opening region is already built.

The **empty hands** opening introduced earlier remains in place. A new character begins with no items at all. Your first tools, food, shelter and infrastructure must come from the generated world.


## RC13 seeded world preparation

After the player confirms a new seed and character, WORLDSEED now displays a dedicated world-generation screen with progress for viable-spawn selection, terrain shaping, natural-resource placement and nearby living-world realization.

The default prepared surface envelope is **17×17 chunks** (289 chunks / 544×544 cells) centered on the selected spawn. Prepared terrain and current-season base resource placement are stored in SQLite. The prepared data is immutable generation data; harvesting, depletion, regrowth, structures, crops and other simulation state remain normal persistent overlays.

This is intentionally a hybrid rather than an attempt to pre-generate literal infinity. Fully generating an unbounded deterministic world can never finish; RC13 shifts the expensive high-probability exploration area to startup and preserves deterministic expansion beyond it. Existing saves also warm a smaller 5×5 chunk neighborhood during loading.

The chunk cache was enlarged to retain the prepared opening area in memory, and temporary lattice/resource-generation scratch caches are released after preparation to avoid turning the loading optimization into a memory leak.

## Run

Requires Python 3.11+. The graphical window uses `pygame-ce`; the Windows launcher installs it automatically if it is missing.

Windows: double-click `RUN_WORLDSEED.bat` for the graphical window. Use `RUN_WORLDSEED_TERMINAL.bat` for the legacy ANSI renderer.

Or run:

```bash
python run_worldseed.py

# force graphical backend
python run_worldseed.py --window

# force ANSI terminal backend
python run_worldseed.py --terminal
```

## Main controls

- `WASD` or arrows - move
- `Enter` - Action Hub / confirm
- `G` - harvest nearby resource (map-targeting if several are reachable)
- `I` - inventory
- `L` - look / inspect
- `M` - regional world map
- `TAB` - World Console
- `ESC` - back; at gameplay root opens pause menu
- `?` - help
- `Q` - save and quit at gameplay root

Menus support `W/S` to move, `D`/Enter to select, and `A`/ESC to go back.

## Character creation

WORLDSEED has no starting class kits. Character creation uses independent pools for Attributes, Skills and Talents, or a random build that spends the same budgets. **Inventory always starts empty.** Your build changes how efficiently you survive, craft, fight, treat injuries, trade, study and understand the world; it does not preselect your story.

## RC7 opening game

The zero-item bootstrap is designed around naturally occurring opportunities:

1. find loose stone, fallen branches and fiber/bark;
2. make flakes and cordage;
3. make a stone knife, axe, pick, hammer, digging stick or primitive weapon;
4. establish fire, shelter, storage and a work area;
5. forage, hunt, farm, mine or explore according to your own priorities;
6. process animals into meat, hide, bone, sinew, fat and offal;
7. cook ingredient-composed meals or preserve food/hides over time;
8. use better stations/materials to move into more advanced production.

There are no starting objectives or revealed routes. Exploration, observation, skill and conversation determine what your character learns.

## RC10 traversable-world generation

New worlds use **worldgen v8** and **natural-resource generation v3**. Worldgen v8 replaces new-world elevation with deterministic geological landforms and exposes derived slope/relief/ridge/valley topography; during the current transition it still consumes the established broad v4 moisture/temperature fields until Phase 3 replaces them with physical climate circulation. Natural-resource generation remains separately versioned so ecology fixes do not rewrite terrain.

Important rules:

- biome identity is terrain; a forest tile does not require a blocking tree on every cell;
- blocking natural props are accents and cannot form cardinally adjacent walls;
- cave mouths and narrow terrain bottlenecks are protected from optional blockers;
- loose stone remains available in forests so reduced boulder density does not break primitive progression;
- spawn selection requires a large connected walkable neighborhood plus primitive-resource opportunity;
- existing saves retain their recorded terrain-generation version, while pre-versioned RC9 natural-resource placement migrates to the safer v3 placement protocol.

The graphical input path no longer maps left/right mouse buttons to Enter/Escape. Mouse hover and wheel zoom remain available; click actions stay inert until explicit hit-tested widgets own them. Repeated movement events are coalesced and expensive regional/ecology refreshes run only when their coarse spatial boundary changes.

## Hunting and animal processing

Animals have habitat preferences, climate envelopes, mass, health, aggression, attacks and carcass profiles. Killed animals leave persistent carcasses instead of instant loot.

Carcass processing is staged:

- skin - preserves hide;
- butcher - recovers meat/fat/offal;
- debone - recovers bone/sinew after butchery.

Damage and age reduce carcass quality. Butchering before skinning damages hide yield. Butcher tables and better cutting tools improve the work. Meat and hides can be preserved through timed station jobs.

## Cooking and nutrition

Cooking is ingredient-driven. Current methods include roast, stew, porridge and broth. The meal inherits nutrition from the ingredients selected: calories, protein, carbohydrates, fat, fiber, hydration and broad diet groups.

The Health pane tracks a rolling diet history across Protein, Vegetables, Grains, Fruit and Fats. Immediate hunger and long-term diet variety are separate mechanics. Prepared meals have finite shelf lives.

## Farming

Current crops include wheat, turnip, barley, beans, cabbage, carrot, onion and flax. Farming requires an appropriate tilling tool. Crops have distinct N/P/K demands, disease families, water/temperature needs, seasons and growth times. Crop rotation and fertilizer matter. Some wild resources can provide seeds, allowing agriculture to emerge through exploration.

## Crafting and furniture

Crafting/building menus are grouped by purpose and show readiness, missing materials, tools/stations, time and what the result enables.

Furniture must have mechanical purpose. Examples include warmth/cooking, shelter, rest, storage, crafting bonuses, carcass processing, drying/tanning, metallurgy, crossing, enclosure or structural support.

## Content and visual coverage in RC10

- 105 item definitions
- 52 recipes/process recipes
- 23 structures/furniture pieces
- 8 crops
- 22 authored natural resource/forage definitions
- 17 authored animals plus procedural species
- 4 dynamic cooking methods
- 304 individual sprite PNGs before atlas/preview files
- 4 variants for each authored animal species
- 32 NPC appearance variants
- 3 growth-stage sprites for each crop

All item definitions include description and flavor text. `tools/audit_content.py` rejects missing references and obvious dead-end/clutter content.

## Deeper living-world systems

RC7 retains the larger WORLDSEED stack developed in earlier releases:

- deterministic infinite terrain and underground z-levels;
- caves, shafts, aquifers and mining;
- ecology cohorts and local individual animals;
- anatomy, wounds, bleeding, fractures and equipment;
- component equipment and metallurgy;
- freeform structures, rooms, roofs and collapse;
- NPC identity, families, relationships, jobs and utility/task AI;
- settlements, property, labor, markets, trade routes and caravans;
- factions, rulers, claims, wars, migration and refugees;
- books, literacy, languages and knowledge transmission;
- generated cultures, religions, institutions and schisms;
- seed-generated magical laws, rituals, contamination and myths;
- epidemiology, quarantine, medicine and transmission through logistics;
- persistent history, graves, artifacts, provenance and character succession;
- A/B/C/D/E simulation fidelity and event-driven offline advancement.

## Discovery

Simulation existence is separate from player knowledge. NPC identities, settlements, factions, historical sites, events, routes and wildlife estimates are only exposed when the character has actually learned them through exploration, conversation, reading, witnessing events or relevant skills.

## Validation

Release gates include:

```bash
python -m compileall worldseed
python tools/audit_content.py
python tools/audit_visuals.py
python tools/audit_traversability.py --seeds 10 --radius 25
python tools/bootstrap_smoke.py --seeds 10
python tools/balance_early_game.py --seeds 20
python tools/bench_worldgen.py
python tools/bench_movement.py
python tools/soak_matrix.py --years 25 --seeds 3 --policy full
```

The regression suite includes the RC8/RC9 visual contracts plus RC10 worldgen/resource-version, blocker-spacing, spawn-connectivity and mouse-input checks. A dedicated `tools/audit_traversability.py` gate measures walkable retention, resource-induced connectivity and accidental blocker adjacency.

## Development documents

- `EARLY_GAME_DESIGN.md` - opening-loop design and invariants
- `CONTENT_ECONOMY_AUDIT.md` - anti-clutter/item-utility rules
- `BALANCE_GUIDE.md` - start fairness, food, fauna, farming and performance budgets
- `RC7_COMPLETION_REPORT.md` - RC7 completed/remaining status
- `VISUAL_ARCHITECTURE.md` - RC8 renderer/presentation boundary
- `SPRITE_STYLE_GUIDE.md` - asset dimensions, readability and variation rules
- `RC8_VISUAL_COMPLETION_REPORT.md` - visual transition foundation status
- `RC9_VISUAL_INTERACTION_REPORT.md` - zoom and hover interaction pass
- `RC10_TRAVERSABLE_WORLD_REPORT.md` - worldgen/resource placement, input/performance fixes and release validation
- `RC11_ITEM_ASSET_AND_PERFORMANCE_REPORT.md` - first individual item-art batch and renderer optimization pass
- `RC12_RESPONSIVE_RENDERER_REPORT.md` - hover partial redraw and renderer performance architecture
- `RC13_SEEDED_WORLD_PREPARATION_REPORT.md` - startup pregeneration, persistence and benchmark details
- `SYSTEMS.md` - larger simulation architecture
- `UI_GUIDE.md` - interface architecture and navigation rules
- `AGENTS.md` - constraints for future coding agents
- `MODDING.md` - data-mod conventions

## Philosophy

WORLDSEED does not script outcomes such as "a monster attacks a village." It models hunger, prey, territory, livestock, memory, threat response and jobs, then lets such events emerge from the state of the world.
