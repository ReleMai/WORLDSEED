# WORLDSEED — Consolidated Project Manual

This README is the single consolidated human-facing Markdown document for WORLDSEED. It absorbs the previous roadmap, system, design, validation, handoff, audit, report, release-note, UI, art, and development-history Markdown files so the repository stays clean.

> **Operational exception:** `AGENTS.md` remains separate because coding agents and automation discover repository instructions by that filename. It is operational configuration, not a second project manual.

## RC14 Dev36 — Integrated Mainline

This mainline combines the previously validated Dev34 inventory/container overhaul with the Dev35 Phase-5 coast/performance work and the latest direct world-interaction fixes.

- Inventory remains the unified graphical item grid with persistent detail/actions, quantity controls and category filtering.
- Container storage remains the dual-pane graphical transfer UI, including persistent natural containers, movable storage, deterministic seeded loot, break-apart salvage, wicker baskets and wooden storage boxes.
- Dev35 Phase-5 coast morphology v2 is integrated: estuary widening, connected distributaries, shallow sediment lobes, barrier/lagoon projection, save-version pinning and bounded coast caches.
- Forest presentation now uses the Dev35 continuous world-coordinate forest-floor material and boundary blending instead of repeated per-cell forest squares, removing visible tile seams/white lines.
- **G** now immediately gathers when only one valid resource is in reach. With multiple resources nearby it enters multi-select targeting; click or Space toggles targets and Enter gathers every selected target.
- Right-clicking the local world opens contextual actions. Adjacent harvestables can be Gathered, adjacent ground piles Picked Up, adjacent containers Opened, and any visible clicked tile can be Examined.
- Pickup commands support the current tile or one orthogonally adjacent tile, so right-click pickup does not require standing directly on the pile.
- Hollow Logs, Rotten Stumps and Rock Crevices now have dedicated transparent sprite art instead of borrowing fallen-branch/boulder graphics.
- Human-facing Markdown remains consolidated in this README; `AGENTS.md` stays separate for repository automation.

## Documentation Index

- **Current Project Overview** — 1 source document
- **Roadmaps and Plans** — 3 source documents
- **Systems, Design, UI, Modding, and Art Guides** — 10 source documents
- **Release Notes and Completion Reports** — 9 source documents
- **Validation and Test Records** — 20 source documents
- **Development Handoffs and Progress Records** — 25 source documents

## Legacy Source Map

The original filenames are preserved as section labels below. Older notes that say “see `SOME_FILE.md`” now refer to the matching **Source: `SOME_FILE.md`** section here.

---

# Current Project Overview

---

## Source: `README.md`

> **Dev21 controls:** WASD moves your character only. Click the HUD buttons for Inventory, Crafting, Build, Health, Map, Actions, World, Look, Help and Pause. Click menu cards; use the wheel or Previous/Next to page; Back or right-click returns. Character creation and target selection support the mouse. Typing names still uses the keyboard. Arrow/Enter/Esc navigation and existing game shortcuts remain available.

> **Dev20:** Clean rebuilt player/NPC art, crafting and inventory crash fixes, and new-character appearance startup repair. See `RC14_DEV20_HANDOFF.md` and `DEV20_VALIDATION.md`.

> **Dev16:** New worlds now use terrain-aware cave entrances/geology and the
> discovery crafting model. Grassland/floodplain and other ground types use a
> data-driven local mesher. Inventory/crafting use the new graphical panel
> renderer in the pygame client. See `RC14_DEV16_HANDOFF.md`.

> **Dev22 atlas:** Map now displays the actual prepared terrain and saved terrain edits. Use the mouse wheel or Zoom buttons, pan buttons or arrow keys, Center, and click terrain or a known-place icon to inspect it. Dark areas are uncharted or not yet prepared, not an invented biome. Known villages/cities, built camps, observed caves and discovered historical sites have illustrated markers. See `RC14_DEV22_HANDOFF.md` for coverage and compatibility limits.

# WORLDSEED v1.0 RC14 Development - Embodied World Foundation

> **Development status:** RC14 Dev33 continues WORLDGEN v8 Phase 5. New worlds now turn the Phase-5 coast model into real terrain: physical ocean depth bands, sandy/gravel/rocky shores, coastal cliffs, tidal flats and salt marshes. Coast materialization has its own save-pinned version and surface-cache key, so older v8 saves keep their existing shoreline. The recent rain/cloud/tree/morel/cave visual work remains intact.

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

---

# Roadmaps and Plans

---

## Source: `RC7_IMPLEMENTATION_PLAN.md`

# WORLDSEED RC7 Implementation Plan and Status

## Objective

Turn the opening hours into a self-sufficient sandbox where a character begins with nothing and can bootstrap from the landscape into primitive industry, hunting, food preservation, agriculture and improved infrastructure without scripted objectives.

## Phase A - Data contracts [COMPLETE]

- item descriptions/flavor/stats/utility roles
- tool qualities
- recipe categories/skill/tool/station metadata
- structure uses/comfort/work/warmth/shelter
- species attacks/carcass profiles/habitat
- crop N/P/K/disease/climate data
- dynamic cooking-method data

## Phase B - Zero-supply bootstrap [COMPLETE]

- empty inventory invariant
- spawn opportunity scoring
- loose stone/deadfall/fiber availability
- stone flake/cordage/tool chain
- primitive campfire/shelter/work surface
- multi-seed balance and bootstrap tools

## Phase C - Hunting/material processing [COMPLETE]

- persistent carcasses
- damage/age quality
- skin/butcher/debone order
- animal attack sets
- timed drying/tanning/preservation
- useful sinks for hide/bone/fat/sinew/offal
- primitive ranged hunting

## Phase D - Cooking/nutrition [COMPLETE]

- roast/stew/porridge/broth method system
- interactive ingredient composition
- inherited nutrition/macros/diet groups
- meal portions and shelf life
- rolling seven-day diet history
- Health-pane nutrition summary
- food effects integrated into recovery/exposure

## Phase E - Farming/forage/ecology [COMPLETE]

- 8 crops with distinct soil demands
- tilling tool requirement
- forage seeds and crop path
- habitat/season-aware natural resources
- habitat-weighted authored animal populations
- local materialization on suitable terrain

## Phase F - Functional furniture/UI [COMPLETE]

- warmth/shelter/comfort/work bonuses
- butcher/drying/tanning stations
- categorized craft/build UI
- READY/NEEDS requirements
- cooking preview and carcass actions
- item detail prose/stats

## Phase G - Quality gates [COMPLETE]

- anti-clutter content audit
- 156 automated tests
- 10-seed end-to-end bootstrap
- 20-seed start balance audit
- deterministic replay
- worldgen/movement benchmarks
- 3x25-year and 1x100-year invariant soaks

## Phase H - Documentation/release [COMPLETE]

- README/release notes: complete
- early-game design: complete
- content economy audit: complete
- balance guide: complete
- completion report: complete
- roadmap/agent/modding/UI docs: complete
- developer blueprint DOCX/PDF: generated and visually verified
- clean ZIP extraction/retest/checksum: completed as final release gate

## Post-RC7 candidates

Trapping, fishing, smoking/salting/fermentation, cold storage, livestock/domestication, animal social/territorial behavior, compost/manure, irrigation networks, recipe knowledge/proficiencies, advanced textile production and deeper aesthetic/prestige systems.

---

## Source: `ROADMAP.md`

# WORLDSEED Roadmap after RC13

RC7 completes the requested early-game overhaul. Future work should deepen systems rather than add disconnected lists.


## RC10 world-generation guardrails now in place
- broad climate/biome fields separated from local resource overlays;
- blocker-density budgets and deterministic minimum spacing;
- traversal/connectivity release audit;
- connected and zero-supply-capable spawn selection;
- versioned worldgen/resourcegen compatibility boundary.

## Near-term depth

### Fieldcraft
- trapping/snaring and trap-line maintenance;
- fishing with habitat, bait and seasonal behavior;
- tracks, scat, calls, nests/dens and hunting-sign interpretation;
- firewood/fuel quality and smoke/ventilation;
- expanded first aid, herbal preparations and sanitation.

### Food/preservation
- smoking, salting, fermentation, pickling and rendering;
- cookware/container quality and batch size;
- cellar/cold-storage temperature effects;
- food contamination and foodborne illness hooks;
- more plant ingredients without orphan content.

### Animal systems
- social groups/herds/packs;
- territories, dens/nests and breeding seasons;
- juveniles and age structure;
- domestication, livestock and selective breeding;
- scavenging and carcass ecology.

### Farming
- compost/manure loops;
- pests and crop disease depth;
- irrigation channels and stored water;
- seed quality and selective propagation;
- orchards/perennials;
- livestock integration.

### Craft knowledge
- recipe discovery/teaching instead of universal recipe knowledge;
- narrow proficiencies distinct from broad skills;
- experimentation and failed/partial products;
- more component substitution based on material properties.

## UI/accessibility
- searchable/filterable craft and construction catalogues;
- favorites/recent recipes;
- keybinding customization;
- contextual comparison panels;
- clearer multi-step job queue/status screens;
- high-contrast and low-color terminal presets.

## World depth
- deeper aesthetics/comfort/prestige so decorative furniture becomes useful;
- settlement craft traditions and local recipe variants;
- regional cuisine and material culture;
- ecosystem succession after fire/logging/agriculture;
- more detailed logistics and storage spoilage.

## Technical gates

Future releases must preserve deterministic namespace isolation, sparse persistent state, read-only rendering, bounded history/state growth, zero-orphan content graphs and long-world invariant tests.

## Visual roadmap after RC8
- explicit hit-tested click/context widgets (hover tooltips are complete)
- directional walk/combat animations
- equipment overlays and modular character composition
- terrain autotiling, animated fluids/fire/weather and lighting
- modular procedural-species sprites
- optional GPU batching only after profiling demonstrates need


## RC13 seeded world preparation now in place

- new-game loading screen prepares 17×17 surface chunks around spawn
- deterministic base terrain is persisted separately from player deltas
- current-season deterministic resource placement is persisted separately from depletion/regrowth
- existing saves warm a 5×5 neighborhood on load
- infinite deterministic expansion remains available outside the prepared area

Future optimization work can add low-priority ring expansion during long rests/saves or optional larger preparation presets without changing the generator contract.

## RC14 — Embodied World (in progress)

Architecture target: `SIMULATION STATE -> REGIONAL PHYSICAL PLAN -> LOCAL MATERIALIZATION`.

Current development checkpoint: **Phase 4 environmental derived fields complete**.

- Phase 0: frozen RC13 v4 golden-seed terrain baseline and performance reference — complete.
- Phase 1: hydrology/settlement-plan/route version contracts, plan dataclasses, stable IDs, generated-cache tables and physical mutation deltas — complete.
- Phase 2: deterministic domain hydrology, Priority-Flood-style depression handling, flow direction, accumulation, watershed IDs, river hierarchy, floodplain prototype, debug PNG/CSV and audits — complete.
- Phase 3: seam-safe prepared hydrology plus worldgen v5 physical river/lake/wetland/floodplain projection and crossing-cost read model — complete.
- Phase 4: deterministic environmental derived fields (slope/relief, fertility, wetness/drainage, flood risk, resource and farmland potential), bounded read cache, Look signs and geography audit — complete.
- Phase 5+: settlement siting, sparse strategic roads, terrain-aware corridors/crossings, settlement skeleton/parcels, materialization, economy/history reconciliation and loading integration.

RC14 does not accept decorative settlements or roads that duplicate simulation authority. Legacy v4 geography remains frozen.

---

## Source: `WORLDGEN_V8_ROADMAP.md`

# WORLDSEED WORLDGEN v8 — Geological Living World Roadmap

Status: **WORLDGEN v8 Phase 5 is active in Dev33. Dev32 established the coastal read model; Dev33 begins save-pinned physical coastline materialization while Hydrology v2 / Morphology v2 remains the drainage baseline.**

WORLDGEN v8 is a staged replacement for WORLDSEED's noise-first surface
generation. It does not discard the existing RC14 architecture: deterministic
seeds, prepared hydrology domains, sparse persistence, environmental fields,
physical settlement plans, route planning, atlas truth, and renderer
observational boundaries remain mandatory.

The new causal chain is:

```text
seed + versions
-> geological provinces / landforms
-> elevation + bathymetry
-> climate circulation
-> drainage / rivers / lakes
-> coast morphology
-> soils / geomorphology
-> ecological mosaics
-> resource opportunity
-> settlements
-> roads / crossings
-> local materialization + cartography
```

## Non-negotiable compatibility rules

- Existing worldgen v1-v7 saves never receive v8 geography during normal load.
- `WORLDGEN_VERSION = 8` applies to newly created worlds only; never rewrite the `worldgen_version` stored in an existing v1-v7 save.
- v8 landforms/topography are authoritative only for v8 worlds. The explicit `version <= 7` generator path remains the compatibility contract for legacy saves.
- Every v8 random domain uses stable named namespaces and fixed version inputs.
- No renderer, hover, movement, or inspection path may generate regional data.
- Generated base geography may be rebuilt; player/history mutations may not.
- The terrain atlas remains a truth projection, not an alternate generator.

---

## Phase 0 — v7 Baseline Freeze and Comparison Harness

### Goal
Create a permanent before/after reference so v8 improvements can be measured
without accidentally rewriting old generation contracts.

### Work
- Select 10-16 golden seeds including negative-coordinate coverage.
- Record v7 terrain fingerprints, hydrology fingerprints, spawn positions,
  start fairness, resource density, traversability, pregeneration duration, and
  representative local/atlas/region screenshots.
- Add comparison scripts that can sample v7 and prototype-v8 fields over exactly
  the same coordinates.
- Record current coastline ratio, elevation histogram, slope distribution,
  river-class distribution, biome proportions, and connected walkable area.

### Exit gates
- Repeated v7 generation matches frozen fingerprints.
- Golden seeds can be regenerated in a clean checkout.
- Comparison reports are deterministic and machine-readable.

---

## Phase 1 — Geological Landform Prototype

### Goal
Replace "elevation is mostly blended noise" with deterministic broad physical
landforms while keeping the prototype non-authoritative.

### Work
- Add a dedicated `worldseed/world/landforms.py` subsystem.
- Generate broad continentalness independent of climate.
- Generate elongated deterministic orogeny/range features rather than circular
  high-noise blobs.
- Generate inland basins and broad plateaus.
- Add fine roughness only after large-scale structure exists.
- Classify sampled points into prototype provinces:
  oceanic plain, lowland, basin, rift valley, upland, plateau, mountain chain.
- Keep all math integer-based where it enters the generation contract.
- Add a bounded debug sampler cache.
- Add a standard-library audit exporter for field CSV + PPM preview.
- Add deterministic and negative-coordinate tests.
- Expose prototype sampling through `WorldGenerator` without altering v7
  authoritative fields.

### Validation
- Same seed/coordinates -> identical field values and province IDs.
- Negative coordinates contain no seams caused by modulo/division behavior.
- Mountain influence forms connected elongated structures across tectonic-cell
  boundaries.
- Multiple large landform types occur across golden-seed windows.
- v7 `sample_fields()` is unchanged before/after prototype sampling.
- Elevation remains on WORLDSEED's existing 0..65535 scale.

### Exit gates
- Visual review confirms recognizable ranges/basins/plateaus at multiple seeds.
- No live save or v7 terrain output changes.
- Prototype generation time is acceptable for prepared-domain use.

---

## Phase 2 — v8 Elevation Authority and Version Boundary

### Goal
Promote approved geological landforms into the authoritative elevation field.

**Dev25 progress:** the authority boundary is implemented for explicit
`WorldGenerator(version=8)` contexts. v8 now uses the geological elevation
compositor while retaining the frozen v4 moisture/temperature driver until
Phase 3. The default `WORLDGEN_VERSION` remains 7, with
`WORLDGEN_PREVIEW_VERSION = 8`, so this code can be exercised by audits/tests
without silently changing newly created player worlds. A v8-aware large-scale
spawn search and multi-seed calibration tool were added before promotion.

**Dev26 progress:** Phase 2 now exposes a deterministic topographic derivative
layer over v8 elevation (slope vector, normalized slope, raw/normalized relief,
ridge exposure, valley depth and ruggedness). Cave entrances for explicit v8
worlds now use these geological/topographic fields instead of the legacy v7
siting rule, while v7 cave placement and underground generation remain frozen.
A dedicated topography/cave audit was added for calibration before promotion.

**Dev27 promotion:** `WORLDGEN_VERSION` is now 8. New save databases record v8
at creation and therefore use geological elevation, v8 topography, v8 cave-mouth
siting and the existing prepared hydrology/coast projection. Existing saves keep
their recorded version and are not migrated. The former
`WORLDGEN_PREVIEW_VERSION` name remains as an alias to 8 for audit tooling.

### Work
- **DONE Dev27:** set `WORLDGEN_VERSION = 8` for newly created worlds; persisted older versions remain immutable.
- **DONE:** freeze the exact v7 field path behind `version <= 7`.
- **DONE:** v8 elevation uses the Phase-1 landform compositor.
- Calibrate sea-level/reference elevation and continental/ocean proportions.
- Add broad valley and intermontane-lowland shaping between ranges.
- Add subregional relief without destroying large forms.
- **DONE Dev26:** v8 cave-mouth suitability uses geological topography.
- Add v8 elevation fingerprint fixtures.

### Validation
- v1-v7 golden terrain remains byte-identical.
- v8 has bounded elevation/slope distributions across 20+ seeds.
- Spawn search can find viable land on all audit seeds.
- No pathological all-ocean/all-mountain prepared windows.
- Negative-coordinate generation remains seamless.

### Exit gates
- New v8 worlds load/save/reload deterministically.
- Legacy saves never silently adopt v8 terrain.

---

## Phase 3 — Physical Climate Circulation

### Goal
Make climate respond to geography instead of acting as an independent noise map.

**Dev28 implementation:** `ClimateV8Sampler` now owns v8 temperature and
precipitation fields. It combines repeating broad climate belts, maritime
moderation, continentality, prevailing wind belts, altitude cooling, upwind
terrain sampling, orographic lift and leeward rain shadows. V8
`WorldGenerator.sample_fields()` now consumes these fields directly, so the
existing hydrology/resource/environment consumers already see physical v8
climate instead of the temporary v4 moisture/temperature sheet.

The same phase now includes a deterministic weather/light presentation chain:

```text
physical climate
-> moving weather cell / cloud cover / rain / storm / fog
-> recent-rain surface wetness
-> day/dawn/dusk/night light state
-> pygame wet-ground texture + cloud-shadow mask + rain/splash animation
-> night grading + local fire glow
```

Weather remains simulation-owned and renderer-observed. Renderer animation may
advance visual rain frames using wall-clock time, but it cannot change the
authoritative weather sample or simulation clock.

### Work
- **DONE Dev28:** add stable broad latitude/climate-band potential.
- **DONE Dev28:** add prevailing wind belts/directions.
- **DONE Dev28:** add oceanic/maritime moderation near coasts.
- **DONE Dev28:** add continentality for large inland regions.
- **DONE Dev28:** derive orographic rainfall from windward ascent.
- **DONE Dev28:** derive rain shadows on leeward sides of major uplifts.
- **DONE Dev28:** keep altitude temperature lapse effects inside the physical climate sampler.
- **DONE Dev28:** separate long-term precipitation potential from dynamic weather wetness.
- **DONE Dev28:** preserve seasonal/game-time systems as consumers rather than geography authority.

### New read fields
- mean_temperature
- precipitation_potential
- maritime_influence
- continentality
- prevailing_wind_dx/dy
- orographic_lift
- rain_shadow
- humidity
- wind_strength
- dynamic cloud_cover / rain / storm / fog / wetness (weather read model)
- daylight / ambient_light / darkness_alpha (lighting read model)

### Exit gates
- Mountain chains produce measurable wet/dry asymmetry.
- Coasts moderate temperature relative to continental interiors.
- Climate fields remain continuous across chunk/domain boundaries.
- Weather is deterministic from seed + game time + coordinates and does not mutate from rendering.
- Rain visibly wets surface terrain and produces animated streak/splash presentation.
- Cloud cover projects soft terrain shadows without revealing undiscovered geography.
- Surface gameplay visibly transitions through dawn/day/dusk/night; UI remains readable.
- Night/local-fire presentation remains observational and does not create simulation light sources.

**Implementation status:** code landed in Dev28; executable multi-seed/pygame
validation is still required before declaring the Phase-3 release gate closed.

---

## Phase 4 — Hydrology v2: Drainage That Follows v8 Landforms

### Goal
Rebuild the proven Priority-Flood pipeline on v8 geography and improve local
river morphology.

**Dev29 implementation start:** `HYDROLOGY_VERSION = 2` is now the new-save
contract. Hydrology v2 keeps the seam-safe Priority-Flood window solver, but
runoff comes from Phase-3 precipitation, wet uplands receive headwater support,
and persisted domains now record runoff plus downstream channel gradient.
Existing saves retain their stored hydrology version; missing metadata is
treated as legacy v1 rather than silently upgrading river geography.

Local channel projection now uses gradient-sensitive meander amplitude,
confluence widening, physically screened ford candidates, and first-pass
channel morphology labels for rapids/gorges, braided reaches, meandering/oxbow
potential and low-gradient delta candidates. The latter are read-model signals
for later terrain/art refinement, not a separate river authority.

**Dev30 continuation:** the projection layer now has its own
`HYDROLOGY_MORPHOLOGY_VERSION = 2`. This lets new worlds use multi-point
centerlines, split braided threads, detached oxbow scars and rocky gorge banks
without rewriting Dev29 hydrology-v2 saves, which infer morphology v1 when the
new metadata is absent. Surface chunk caches are now keyed by worldgen +
hydrology + morphology version so independently versioned river projection
cannot reuse an incompatible cached chunk.

### Work
- **DONE Dev29:** introduce `HYDROLOGY_VERSION = 2` for new saves while preserving stored v1 contracts.
- **DONE Dev29:** preserve seam-safe multi-domain window solving, including v2 runoff/gradient overlap checks.
- **DONE Dev29:** run the existing Priority-Flood depression solver directly on authoritative v8 elevation.
- **DONE Dev29:** derive local runoff from authoritative Phase-3 precipitation; rain shadows therefore reduce discharge through the climate field itself.
- **DONE Dev29:** wet high terrain receives bounded headwater runoff/classification support.
- **DONE Dev29:** preserve class hierarchy from accumulated discharge with v2 thresholds.
- **DONE Dev30:** replace single-midpoint v2 projection with deterministic multi-point channel centerlines; morphology v1 preserves Dev29 midpoint geometry.
- **DONE Dev29:** meander amplitude increases as channel gradient falls and remains tight in steep headwaters.
- **DONE Dev30:** confluences/tributary junctions widen from upstream count and braided reaches physically split/rejoin, leaving base-terrain river islands between threads.
- **DONE Dev30:** suitable braided reaches materialize as two deterministic channel threads using the existing freshwater terrain family.
- **DONE Dev30:** mature low-gradient reaches can materialize detached shallow-water oxbow/meander-scar rings in their floodplains.
- **DONE Dev30:** rapids/gorge labels remain gradient/ruggedness-driven and steep confined banks can materialize as rocky gorge margins.
- **PARTIAL Dev29:** ford selection is now physically gated by class, gradient, bank slope, discharge and floodplain; deterministic hashing only breaks ties among suitable reaches.
- **PARTIAL Dev29:** low-gradient, high-discharge near-sea reaches expose deterministic delta candidates; delta morphology remains Phase 5 work.

### Exit gates
- Every core drainage node terminates correctly.
- Downstream discharge is monotonic absent explicit splits.
- River continuity is seam-safe.
- Major rivers are rarer/wider than minor streams.
- Fords and crossing costs are physically explainable.

---

## Phase 5 — Coast, Bathymetry, Estuary and Delta Morphology

### Goal
Replace mostly uniform shoreline bands with varied coast types.

**Dev32 implementation start:** a new `CoastV8Sampler` read model derives continental-geometry bathymetry, open-sea exposure, shelter, bay/headland scores, shore-material tendency, tidal-flat/marsh/lagoon potential and river-mouth sediment/estuary/delta potential. It is deliberately **terrain-neutral** in this first slice: no existing coast tiles, saves, surface caches or user-facing graphics are rewritten yet. The purpose is to establish and audit one causal coastal authority before materialization.

**Dev33 materialization:** new worlds now pin `COAST_MORPHOLOGY_VERSION = 1`. The approved Phase-5 fields materialize into real gameplay terrain: continental-geometry ocean depth bands plus sandy, gravel, rocky, cliff, tidal-flat and salt-marsh coast classes. Existing v8 saves without coast metadata infer coast version 0 and retain their pre-Phase-5 shoreline. Surface caches now include the coast contract. Expensive coast classification is sampled on an absolute 8-cell lattice for materialization while exact geological elevation still determines land versus water per cell.

### Work
- **MATERIALIZED Dev33:** bathymetric shelf depth derives from continental geometry plus raw sea depth and now selects actual ocean depth terrain in new worlds.
- **PARTIAL/MATERIALIZED Dev33:** beaches, gravel shores, rocky shores, coastal cliffs, tidal flats and salt marshes now become real terrain. Protected-bay/headland reads exist; spits/barrier islands remain future Phase-5 work.
- **PARTIAL Dev32:** use slope, relief, shelter and wave exposure to derive shore-material tendency; Phase 6 substrate will later refine it.
- **FOUNDATION Dev32:** derive river-mouth sediment, estuary and delta potential from prepared hydrology; physical distributaries remain next.
- Expand brackish mixing zones using discharge + tidal/coastal geometry.
- **FOUNDATION Dev32:** derive shallow embayment/lagoon potential as a read field.
- Keep ocean current presentation tied to authoritative current fields.

### Exit gates
- Coastlines contain multiple morphology classes per large audit domain.
- River mouths connect cleanly into estuaries/deltas.
- No one-cell coastal discontinuities across prepared-domain seams.

---

## Phase 6 — Geomorphology, Substrate and Soil

### Goal
Make topography visible through the ground itself.

### Work
- Derive slope classes and aspect from v8 elevation.
- Add cliff/escarpment candidates on extreme gradients.
- Add talus/scree beneath steep exposed rock.
- Add alluvial fans where steep tributaries exit into flatter terrain.
- Add river terraces and young floodplain/alluvial deposits.
- Add substrate classes: sand, gravel, loam, clay-rich, shallow bedrock, rocky.
- Derive soil depth, fertility, drainage and erosion susceptibility.
- Separate stable physical substrate from seasonal surface presentation.

### Exit gates
- Soil/substrate follows landform/hydrology causally.
- Cliffs/scree do not create impossible start regions or route traps.
- Environmental fields consume the same substrate authority.

---

## Phase 7 — Ecological Mosaic / Continuous Vegetation

### Goal
Move beyond one discrete biome ID per cell while retaining readable gameplay.

### Work
- Keep broad biome/climate labels for summaries.
- Add continuous vegetation cover:
  tree canopy, shrub cover, grass/herb cover, wetland vegetation, bare ground.
- Add elevation/tree-line suppression and alpine transition.
- Add forest density/age/edge fields.
- Add woodland, savanna-like open tree cover, meadow/steppe, bog/marsh,
  alpine meadow, sparse tundra, and scree mosaics where climate supports them.
- Let disturbance/history later alter cover without rewriting climate.
- Retain terrain IDs as gameplay/materialization categories derived from fields.

### Exit gates
- Biome boundaries read as ecotones rather than threshold walls.
- Forests have internal clearings/edges and density variation.
- Vegetation distributions remain deterministic and spatially coherent.

---

## Phase 8 — Geological and Ecological Resource Placement

### Goal
Make resources appear because the world can support them.

### Work
- Tie timber/forage to actual vegetation cover.
- Tie stone/ore opportunity to geological province/substrate.
- Tie clays/sands/gravels to depositional environments.
- Tie fish/shellfish/reeds to real water habitat classes.
- Re-evaluate blocker spacing and resource clutter against new terrain.
- Preserve resource regeneration and sparse persistence contracts.

### Exit gates
- Resource opportunities correlate strongly with causal fields.
- Zero-item bootstrap remains achievable.
- Blocking resources preserve traversability.

---

## Phase 9 — Local Terrain Materialization and Visual Diversity

### Goal
Make the new physical fields visible without creating a second visual world.

### Work
- Extend terrain tags/material families for new substrate/landform categories.
- Add deterministic presentation variants driven by authoritative fields:
  wet/dry grass, exposed soil, gravel, moss/litter, reed margins, scree, etc.
- Add slope/shore/river edge overlays.
- Improve cliff and elevation readability without fake 3D topology.
- Use terrain-family autotiling rather than pair-by-pair exceptions.
- Keep microvariation presentation-only unless it affects simulation.

### Exit gates
- Local terrain visually communicates wetness, slope, substrate and vegetation.
- Tile transitions remain seamless and future/modded ground remains data-driven.
- Renderer cannot mutate or generate terrain.

---

## Phase 10 — Settlement Carrying Capacity and Geographic Siting

### Goal
Remove the remaining random 42%-presence dependency for v8 civilization.

### Work
- Preserve legacy settlement presence rules for v1-v7.
- Compute v8 settlement potential from water, farmland, timber, minerals,
  crossing value, climate stress, route opportunity and defense.
- Add regional carrying capacity and minimum spacing by settlement rank.
- Allow settlement clusters in productive valleys/coasts and sparse settlement
  in marginal environments.
- Generate daughter hamlets along routes/resource frontiers.
- Bind settlement archetypes to actual local opportunity.
- Keep simulation ledger authority separate from physical plans.

### Exit gates
- Settlement frequency tracks carrying capacity, not arbitrary region rolls.
- Settlement anchors occupy legal terrain and plausible access points.
- Same seed produces identical sites/archetypes.

---

## Phase 11 — Terrain-Constrained Roads, Passes and Crossings

### Goal
Make civilization's transport network explainable from terrain.

### Work
- Replace probability-only regional edge selection for v8.
- Build sparse strategic candidate graphs among realized/prepared settlements.
- Score economic/strategic utility.
- Rasterize accepted edges through terrain-cost corridors.
- Prefer valleys, ridgelines where appropriate, natural passes and existing roads.
- Use real ford/bridge candidates from hydrology.
- Persist route corridors and crossing IDs.
- Let road condition/traffic/history feed the same physical route plan.

### Exit gates
- Strategic graph remains sparse and connected where appropriate.
- Roads avoid cliffs/deep water unless crossing infrastructure exists.
- Route costs respond to slope, wetness, surface and bridge state.

---

## Phase 12 — Atlas and Regional Cartography Unification

### Goal
Ensure every zoom level tells the same geographic story.

### Work
- Keep the exact terrain atlas as the truth source.
- Replace dominant-biome regional squares with a prepared low-resolution
  generalized raster derived from authoritative terrain.
- Overlay relief, rivers, roads and known settlements from real plans.
- Preserve discovery/knowledge gating.
- Add cartographic generalization only; never invent unseen physical features.

### Exit gates
- Local map, terrain atlas and region map agree on coast/river/terrain placement.
- Region-map inspection performs no generation or simulation mutation.

---

## Phase 13 — Underground Geological Coupling

### Goal
Make caves and ore geology correspond to the new surface geology.

### Work
- Preserve v7 cave rules for v7 saves.
- Use v8 geological province/substrate to influence cave style/depth.
- Couple limestone/karst-like cave potential, fracture caves, volcanic/igneous
  zones, sedimentary coal and metallic ore belts to broad geology.
- Keep cave mouths terrain-aware and reciprocal.
- Preserve protected shaft/chamber traversal.

### Exit gates
- Surface geology predicts underground tendencies without perfect certainty.
- Ore/cave placement remains deterministic and bounded.

---

## Phase 14 — Pregeneration, Persistence and Performance

### Goal
Prepare richer worlds without moving expensive work into movement/render loops.

### Work
- Decide which v8 fields are reconstructable functions versus cached domains.
- Extend startup stage progress/timing.
- Precompute required geological/climate/hydrology domains for the opening ring.
- Add bounded LRU caches and revision/fingerprint keys.
- Prepare future expansion rings in explicit background/quiet phases.
- Profile CPU/memory/database growth before parallelization.
- Keep writes separate from pure CPU generation if worker pools are added.

### Exit gates
- Entering prepared chunks performs reads, not regional generation.
- Movement/hover/render latency does not trigger v8 planning.
- Cache deletion recreates identical base geography.

---

## Phase 15 — Release Hardening and WORLDGEN v8 Acceptance

### Required audits
- Determinism and RNG namespace isolation.
- v1-v7 legacy geography fingerprints.
- Hydrology sinks/cycles/seams/discharge hierarchy.
- Coast continuity/morphology distribution.
- Elevation/slope/ocean coverage distributions.
- Biome/ecotone/vegetation distribution.
- Resource opportunity and blocker density.
- Settlement legality/carrying-capacity distribution.
- Route connectivity/crossing legality.
- Spawn fairness and zero-item bootstrap.
- Save/reload and generated-cache rebuild.
- 25-year and 100-year simulation soaks.
- Pregeneration and ordinary movement/render benchmarks.
- Visual review across golden seeds at local, atlas and regional zoom.

### Final acceptance
WORLDGEN v8 is ready only when the generated world is both more believable and
more internally coherent: mountains shape climate; climate and elevation shape
water; water and soil shape ecology; ecology/resources shape settlement; terrain
and settlements shape roads; and all zoom levels display that same physical
world without contradicting simulation state.

---

# Systems, Design, UI, Modding, and Art Guides

---

## Source: `BALANCE_GUIDE.md`

# WORLDSEED RC7 Balance Guide

## Philosophy

Balance protects possibility, not a fixed sequence. A sandbox start should be difficult because of world conditions and player choices, not because a necessary primitive ingredient failed to exist anywhere nearby.

## Start fairness metrics

`tools/balance_early_game.py` samples generated starts without granting supplies. Final 20-seed sample, radius 14:

- weak starts: 0
- empty starts: 20/20
- median resource cells: stone 100.5, branch 36, fiber 39, edible 45.5, water 123, trees 206
- worst nearest distance observed: stone 13, branch 9, fiber 6, edible 5, water 10, tree 3

These are *opportunity* metrics, not guaranteed pickups; resources remain undisclosed and must be found.

## Zero-item bootstrap gate

`tools/bootstrap_smoke.py --seeds 10` must pass. It validates generated-material access through:

empty inventory -> stone/branch/fiber -> flakes/cordage -> knife/axe/sling -> campfire -> timber -> carcass processing -> cooked meal -> nutrition history.

Farming is intentionally not required in that exact chain because wild seed availability is seasonal/exploratory rather than a guaranteed spawn resource.

## Time targets

Primitive actions should create meaningful day planning. Guidelines:

- trivial hand processing: minutes;
- crude tool construction: tens of minutes;
- felling/mining: meaningful work blocks affected by skill/tool quality;
- drying: many hours;
- tanning: roughly a day or more;
- crop growth: many days/seasonal;
- construction: scales with material and sophistication.

## Food balance

Food has four simultaneous concerns:

1. immediate hunger/satiety;
2. energy/macros;
3. diet-group diversity;
4. spoilage/preservation.

No single primitive food should be optimal across all four. Cooking increases usability/satiety; preservation trades time/station requirements for shelf life; diverse meals improve longer-term diet.

## Animal balance

Mass, health, aggression, group behavior, habitat and carcass yield must correlate. Small prey should be accessible but low-yield. Large herbivores offer more material but are harder/dangerous. Predators can be resource-rich but are not intended as optimal early-game prey.

## Farming balance

Each crop has a niche across growth time, climate, nutrition, fiber utility, N/P/K usage and disease family. Crop rotation should outperform repeating one crop indefinitely, but no single rotation should be mandatory.

## Performance budgets

Final RC7 measurements in this environment:

- world generation: ~15.11 ms per 32x32 chunk (100-chunk benchmark)
- movement: ~1.62 ms per step
- movement + 100x30 render: ~3.97 ms per step
- 25-year aggregate worlds: zero invariant failures across three seeds
- 100-year aggregate world: zero invariant failures; ~1.96 MB state

These are engineering budgets, not hardware guarantees.

---

## Source: `CONTENT_ECONOMY_AUDIT.md`

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

---

## Source: `docs/REGIONAL_TERRAIN_ASSETS.md`

# Procedural regional terrain assets

The M region map generates cartographic terrain artwork from each discovered region's prepared `RegionBlockPlan`. Every block still represents 512 x 512 world cells. Grass tufts, trees, stone, sand, snow marks, waves and ridge symbols replace the flat fill and single relief slash.

The plan's dominant biome selects a profile. Moisture changes the palette and vegetation density; temperature changes the cold tint; elevation changes material brightness and ridge snow; relief controls ridge symbols. The forest share of `biome_mix` controls tree symbols in grassland. These are summary symbols, not exact local feature positions. Summary data does not contain a spatial biome raster, so the artwork does not invent coastlines, waterways, settlements or roads. Existing regional connection and discovery rendering stays authoritative.

## Ownership and customization

- `worldseed/presentation/regional_terrain.py` owns `TerrainAppearance`, `RegionalTerrainAssets.surface(plan, pixels)` and procedural painting.
- `worldseed/assets/regional_terrain.json` contains namespaced biome profiles with base/dry/cold palettes, mark colors, symbol kind and density. Unknown biomes have an explicit gray fallback.
- `worldseed/ui/region_map.py` draws these surfaces below the existing water/road/settlement/player overlays. The hover snapshot fix remains in place.
- `tools/export_regional_terrain_samples.py` exports 21 sample PNGs plus a labeled atlas. Run `python tools/export_regional_terrain_samples.py --output artifacts/regional-terrain-assets` using the pygame-enabled Python environment. These are illustrative sample plans, not geography added to a saved world.

## Determinism, persistence and cost

Artwork uses the named `presentation:regional-terrain` RNG namespace and asset version 1. Its private PCG stream depends on region coordinates and biome; public terrain fields control the appearance. It does not read hidden control/site potential or the all-fields plan fingerprint, consume simulation RNG, call terrain/region generation, or write saves. No schema/worldgen migration or gameplay content changes are required.

Canonical assets are 128 x 128 pixels, preserving the same motifs on resize. Display variants are capped at 256 x 256 before final viewport scaling. A per-renderer LRU holds at most 256 surfaces, enough for base and display assets for the full 13 x 9 regional viewport. Eviction only costs regeneration of artwork. There is no persistent generated-image collection in normal gameplay.

Tests cover repeatability, request-order independence, field sensitivity, hidden-state isolation, all seven biome profiles, unknown fallback, cache reuse/eviction, full-viewport cache retention, and unchanged hover/discovery/connection behavior. The save preview is rendered offscreen through a read-only SQLite connection with terrain and plan generation forbidden. See `artifacts/terrain-assets-profile.json` for the local cold/cached generation measurement.

Next dependency: exact spatial regional terrain illustration would require an authoritative prepared spatial raster; this system deliberately remains a cartographic summary of existing Dev5 data.

---

## Source: `EARLY_GAME_DESIGN.md`

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

---

## Source: `MODDING.md`

# WORLDSEED v1.0 RC5 — data modding

WORLDSEED's RC mod layer is intentionally **data-only**. The engine resolves manifests and loads compatible JSON data without importing arbitrary mod Python.

This makes deterministic load order, save diagnostics and security much easier to reason about.

## Directory layout

Create a `mods/` directory beside the game, then one folder per mod:

```text
mods/
  my_expansion/
    manifest.json
    data/
      items.json
      materials.json
      recipes.json
      structures.json
      crops.json
      species.json
      diseases.json
```

Only registries understood by the current loader are used.

## Manifest

Example:

```json
{
  "id": "my_expansion",
  "name": "My Expansion",
  "version": "0.1.0",
  "engine_min": "1.0.0-rc3",
  "dependencies": [],
  "load_after": []
}
```

Rules:

- `id` is a simple stable manifest ID; do not reuse another mod's ID.
- required `dependencies` must exist;
- dependency cycles fail loading;
- `load_after` participates in deterministic ordering when possible;
- duplicate protected/core content IDs are rejected rather than silently overwritten.

## Namespaces

New content IDs should use a namespace you control, for example:

```text
rele:blue_steel
rele:marsh_drake
rele:storm_temple
```

Do not define new content under `core:` unless editing the core project itself.

## Determinism

Data mods become part of the effective content set. The engine records a deterministic mod/content hash for diagnostics.

A mod should never depend on directory enumeration order or current wall-clock time to determine content.

## Save compatibility

Removing a mod from a world that already contains persistent references to its IDs may make that save invalid or incomplete. RC5 does not attempt to synthesize replacements for removed mod content.

For long-lived mods:

- keep IDs stable;
- add new content instead of renaming IDs casually;
- document removed/deprecated IDs;
- avoid changing semantic meaning of an existing ID.

## Executable mods

Arbitrary Python mod execution is deliberately outside the v1.0 RC contract. A future scripting API would need sandboxing/versioning/determinism decisions before it is safe to expose.

# RC7 data fields

RC7 expands the data contract for early-game content.

## Items

Items may define description/flavor, nutrition/macros, diet groups, utility roles, tool qualities, equipment/combat data and spoilage. A core item should have a functional use or downstream process.

## Recipes

Recipes can declare category, skill/difficulty, station, time, inputs/outputs and required tool qualities. Prefer capability requirements such as `cut`, `skin`, `mine`, `hammer`, `till` or `sew` over exact tool IDs.

## Natural resources

Resource definitions may constrain terrain, temperature, moisture, season, density/patch behavior, regrowth, tool requirements, blocking and yields.

## Species

Authored species can define habitat/climate, mass, health, group behavior, attacks and a carcass profile. Procedural species use the same runtime contracts.

## Crops

Crop definitions own growth duration, water/temperature, N/P/K consumption, disease family, seed and harvest outputs.

## Cooking methods

Cooking methods declare station/cookware/water needs, accepted ingredient roles/counts, duration and satiety/hydration modifiers. Meal nutrition is composed at runtime from ingredients.

Run `python tools/audit_content.py` before distributing a content mod.

---

## Source: `SPRITE_STYLE_GUIDE.md`

# WORLDSEED Sprite Style Guide

## Direction

Sprites use grounded, readable pixel art rather than bright iconography. The target is a rugged simulation-game aesthetic: earth tones, limited highlights, clear silhouettes, and enough internal detail to distinguish function at small sizes.

## Base sizes

- terrain: 32x32 opaque tile
- item: 32x32 transparent icon
- crop: 32x40 transparent, 3 growth stages
- resource: up to 48x56 transparent, bottom anchored
- structure/furniture: 48x48 transparent
- animal: 56x48 transparent
- NPC/player: 32x48 transparent
- atlas cell: 64x64

The renderer scales using nearest-neighbor presentation logic and bottom-centers objects that are taller than one logical tile.

## Readability rules

1. silhouette first — an axe should read as an axe before color is considered
2. category does not imply identical shape — oak, pine, birch and willow are different
3. color supports identity but is not the sole differentiator
4. one-pixel highlights are allowed where they improve material reading
5. drop shadows are presentation aids only and stay subtle
6. transparent background for non-terrain assets
7. no visual detail may imply a mechanical property the item does not have

## Variation

Each authored animal species has four deterministic variants. Variants may alter coat shade, marking detail and small body accents without changing hitbox or species identity.

NPCs currently use 32 visual variants combining several skin tones, hair colors/styles and clothing palettes. NPC visual selection is deterministic from stable identity, so reloading a save does not change appearance.

## Data contract

`worldseed/assets/visuals.json` maps content IDs to sprite paths. Runtime code requests content IDs, not filenames.

A future hand-painted sprite can replace a generated file at the same path without changing simulation or save data.

## Quality gate

Run:

```bash
PYTHONPATH=. python tools/audit_visuals.py
```

The gate requires visual mappings and valid files for every item, terrain, natural resource, structure, crop and authored species, plus a minimum NPC variation pool.

---

## Source: `SYSTEMS.md`

# WORLDSEED v1.0 RC14 Development — systems and causality map

This document describes **ownership boundaries and causal contracts**. WORLDSEED should become more complex by composing systems, not by allowing every module to edit every other module's state.

## Central architecture

```text
Terminal Input
    ↓
Typed Command
    ↓
Simulation Kernel ─────────────→ Clock / Scheduler
    │
    ├→ World Service → deterministic generation / chunk cache / sparse mutations
    ├→ Entity Store  → local player/entity components
    ├→ Living State  → sparse semantic world records
    ├→ Domain Systems
    │    ecology / AI / combat / disease / economy / factions / etc.
    └→ History Events
             ↓
          SQLite

Read Model / Renderer / World Console
    ↑
  observes only
```

The UI may ask the simulation questions. It must not create content simply because a player opened a screen.

---

## Determinism contract

The canonical inputs to procedural decisions are:

```text
world seed
system RNG namespace
stable semantic identifiers / coordinates
simulation boundary / ordinal where required
worldgen or protocol version
```

Never use Python's global `random` in authoritative generation/simulation.

Adding one random draw to ecology must not shift settlement generation, magic laws or another unrelated stream.

State hashing and cross-process replay are used as regression contracts.

---

## RC14 regional physical-plan layer (development)

RC14 adds a new authority bridge between aggregate simulation and exact nearby materialization:

```text
Simulation / ledger
    population, stocks, occupations, prices, events
            ↓
Regional physical plan
    stable roads, crossings, parcels, structure IDs, capacities, ownership links
            ↓
Local materialization
    exact footprints, doors, containers, nearby actor positions/tasks
```

The physical plan is persistent identity, not a renderer-owned decorative copy. Generated base hydrology/plans/routes are rebuildable from seed + generator versions and may be cached in SQLite. Player/history mutations are not rebuildable and therefore belong in authoritative simulation state or `physical_plan_deltas`.

### Hydrology / physical geography — Hydrology v2

WORLDGEN v8 new saves use hydrology contract v2. Prepared adjacent domains are still solved together in one larger Priority-Flood lattice and sliced back into cache records, preserving the proven seam-safe window authority. V2 samples authoritative v8 elevation plus Phase-3 precipitation, converts precipitation into bounded local runoff, accumulates discharge downstream, and persists both runoff and channel gradient beside watershed IDs, river hierarchy and floodplain strength.

Wet uplands receive bounded headwater support, while rain-shadow/arid regions contribute less runoff because the physical climate field already reduces precipitation there. Local channel projection uses gradient-sensitive meanders, tributary/confluence widening, gradient/ruggedness-driven rapid and gorge labels, physically screened ford candidates, and first-pass braided/meandering/oxbow/delta read signals. Dedicated braided islands, oxbow scars and delta terrain remain later materialization work; they do not exist as renderer-invented features.

Hydrology is independently versioned from worldgen. New saves record hydrology v2. Existing saves continue using the `hydrology_version` in their metadata; saves missing that metadata are inferred as legacy v1 rather than silently changing rivers. Generated hydrology remains rebuildable cache data, while bridges/crossing damage and other historical mutations stay in authoritative plan deltas.

River projection/morphology is independently pinned as `HYDROLOGY_MORPHOLOGY_VERSION`. Morphology v2 uses deterministic four-point centerlines, physically suitable braid splits that rejoin at drainage nodes, detached oxbow-scar water, and rocky banks around steep rugged gorge reaches. Saves missing morphology metadata infer Dev29 morphology v1. Surface chunk caches therefore use the tuple `(worldgen_version, hydrology_version, morphology_version)`; never reuse a worldgen-only surface cache for v5+ terrain.

Regional hydrology is prepared during startup pregeneration. Movement, hover, rendering and map inspection may read prepared hydrology but never solve it.

---

# Spatial model

## Tile / chunk / macro-region hierarchy

```text
Tile
  integer x,y,z

Chunk
  32 × 32 tiles

Macro-region
  coarse 512 × 512 world-tile cell
  used by settlements, economy, LOD and long-distance routing
```

Negative coordinates use floor division semantics and are regression-tested.

## Realized vs potential

A macro-region becomes realized because the player or a valid existing realized-world process makes it relevant.

Tier-E regions do **not** spontaneously instantiate daughter settlements, NPC families and markets forever into infinity.

This boundary is mandatory for scalability.

---

# Simulation LOD

## Tier A — immediate

Ownership:
- exact local map state;
- materialized individuals;
- combat and anatomy;
- local fire/fluids;
- player interactions;
- local navigation.

## Tier B — nearby

Ownership:
- named/persistent individuals;
- reduced AI cadence;
- meaningful local travel;
- state that the player could soon observe.

## Tier C — region

Ownership:
- wildlife cohorts;
- settlements;
- labor/economy;
- trade/migration;
- aggregate outbreaks;
- coarse social/political state.

## Tier D — distant realized

Ownership:
- scheduled/coarse daily or monthly equations;
- no need for every ordinary actor to receive an individual tick.

## Tier E — unrealized

Ownership:
- deterministic potential only.

Promotion/demotion must conserve authoritative quantities. Example:

```text
cohort count = 37
    ↓ materialize 3 visible wolves
player kills 1
    ↓
authoritative cohort count = 36
    ↓ surviving wolves dematerialize
count remains 36
```

Dematerialization is not a death event and must not change the aggregate.

---

# Time and offline progression

The engine separates player command cadence from slow systems.

Examples:

```text
combat/action           immediate command resolution
player survival         action / short cadence
weather/crops/fire      hourly/coarse blocks
disease/economy/ecology daily
families/politics       monthly
scheduled arrivals      exact/coarse arrival boundaries
```

Offline advancement uses event boundaries, not one-minute replay.

A newly created caravan during a fast-forward must enter the boundary schedule and may arrive before the rest of the offline interval completes.

SAFE offline policy prevents named-character fatal outcomes while still allowing illness/economic absence and aggregate progression. FULL allows eligible named mortality.

---

# Player knowledge and discovery

Simulation existence is not player knowledge. `LivingWorldState` carries discovery sets for tiles, settlements, NPC identities, factions, sites and historical events. Read models must filter through those sets rather than directly iterating all simulation records.

Discovery sources include line-of-sight exploration, entering/approaching places, direct conversation, rumors, books/records, site interaction and witnessing events. NPC identity is deliberately separate from NPC existence: an active nearby person can render as `Stranger` until `TalkCommand` reveals them.

Important invariant:

```text
engine knows X
    ≠
player knows X
```

Alerts, ledgers, ecology views, settlement/economy menus, history and look mode must never leak undiscovered proper names/details.

# Natural resource layer

Ground terrain is immutable deterministic base context unless the terrain itself is physically excavated. Surface vegetation/boulders are deterministic **features** layered over that ground. Persistent harvest state records depletion time, enabling staged regrowth without rewriting the underlying biome.

Resourcegen v3 first applies a biome-level placement budget, then chooses among habitat-eligible definitions. Blocking structural features (trees/boulders) are deterministically thinned so cardinally adjacent candidates cannot form solid walls. Cave mouths and terrain necks are protected from optional blockers. Nonblocking forage uses broader patch richness plus local gates, producing ecological pockets without making every definition an independent placement roll.

Movement and sight query both terrain and the feature layer. Mature trees/boulders may block; stumps/saplings may not. Construction, containers, crops and cultivated soils suppress wild feature realization to protect player-authored space and old-save compatibility.

Gathering accepts relative target coordinates. Surface features are harvested from current/adjacent cells; underground solid terrain is mined from adjacent cells and transformed to its declared depleted terrain.

# World generation

Base terrain is a deterministic function of seed/coordinates/version.

The persistent database stores changes such as:

- mined/changed tiles;
- structures/roofs;
- containers;
- crops/soil;
- realized fluid/fire state;
- discovered tiles;
- semantic sites/entities.

It does **not** need a serialized copy of every untouched generated tile.

Worldgen v4 keeps terrain deterministic but separates spatial scales: elevation retains local relief while moisture and temperature vary across much broader regions. Biome classification is climate-first, so forests/grasslands/scrub form coherent regions instead of depending on decoration rolls. The v3 reciprocal cave-column rules remain part of the underground contract. Recorded terrain-generation version is immutable per world; legacy saves continue to use their original generator. Natural-resource generation is versioned separately so resource-placement fixes do not require rewriting old geography.

WORLDGEN v8 is the current new-world geography/climate contract. It composes deterministic continentalness, aligned major/branch mountain belts, basins, plateaus, structural valleys, coastal detail and local roughness into one geological elevation field. A derived topography read model exposes slope, relief, ridge exposure, valley depth and ruggedness without realizing chunks. V8 physical climate then derives mean temperature, precipitation potential, humidity, maritime influence, continentality, prevailing wind, orographic lift and leeward rain shadow from that geography. `WorldGenerator.sample_fields()` consumes those physical climate values for v8, while explicit v1-v7 worlds keep their frozen field contract. New v8 cave entrances use geological/topographic fields; v1-v7 saves remain pinned to their recorded generators and are never retroactively rewritten. Hydrology remains independently versioned until the dedicated hydrology-v2 phase.

Players may also create persistent supported shafts through simulation commands. These mutations are stored as world deltas rather than changing the base generator.

Historical-site base layouts are deterministic; runtime overlays persist locks/traps/loot/occupants/clearance.

---


## Climate, weather and lighting

V8 separates long-term climate from short-term weather. Climate is reconstructable from seed + coordinates + climate version; weather is reconstructable from seed + game-time slot + weather cell + climate. The simulation owns cloud cover, precipitation, storm/fog state, recent-rain wetness and weather temperature deltas. Rain affects crops and suppresses fire through the environment system.

The pygame renderer is observational. It may render wet-ground material overlays, soft projected cloud-shadow masks, animated rain streaks/splashes, fog haze, dawn/day/dusk/night grading and local fire glow, but these effects never create or alter weather, time, terrain, discovery, or light-source simulation state. Visual animation time may move rain frames while input waits; authoritative weather remains fixed until simulation time changes.

# Ecology

## Coarse populations

`PopulationCohort` is the authoritative distant population representation.

Daily ecology uses bounded reproduction/mortality/predation/carrying-capacity equations.

## Materialized creatures

Local individuals acquire:
- position;
- HP/anatomy;
- behavior state;
- wounds;
- notable/legend status if earned.

Ordinary healthy individuals can collapse back into cohorts. Named/notable creatures remain explicit.

## Procedural species

Generation samples trait combinations under an ecological niche and runs viability checks. A species definition can affect combat, habitat, population dynamics, drops and behavior.

---

# Combat, anatomy and equipment

Combat owns attack legality/resolution. AI may request an attack but does not directly edit wounds.

Attack resolution can produce:

```text
hit location
armor interception
material/quality mitigation
surface/tissue damage
bleeding
fracture
pain/blood loss
item wear
history/legend consequences
```

Player wounds persist and can require bandage/splint treatment. Body state feeds back into stamina, movement and combat performance.

Specific durable equipment artifacts track condition and provenance. Equipment references a particular artifact where available rather than an abstract infinite item type.

---

# Crafting, materials and metallurgy

Content defines materials/items/processes. Simulation owns transformations.

Material properties include mechanical/economic characteristics. Component designs choose actual inputs per part.

Metallurgy introduces intermediate batches with carbon/purity/temperature/treatment state. Heat treatment changes quality, and that quality can flow into the finished artifact.

Important invariant:

```text
inputs consumed + outputs created
must be explainable by one declared process
```

No occupation or recipe receives resources from nowhere merely to keep gameplay moving.

---

# Building, structure, storage and fluids

Construction consumes physical inventory and creates persistent world state.

Floor-level structures and roof structures are separate layers.

Structural simulation uses support/load abstractions. Unsupported roof sections deteriorate and may collapse.

Room classification uses enclosure + semantic contents + roof/shelter data.

Containers own inventories with mass/volume capacity. Destroying a container spills contents.

Fluids use cells rather than one entity per liter. Local flow is intentionally approximate and bounded.

---

# Agriculture

Crop state depends on:

```text
species growth requirements
season / temperature
moisture / irrigation
soil N/P/K
organic matter
crop-disease pressure
rotation history
```

Agriculture feeds player survival and settlement economy through the same item/stock model.

---

# NPC AI and social state

NPC AI uses utility scoring + hierarchical tasks.

```text
needs / personality / danger / duty
              ↓
          goal score
              ↓
      selected current goal
              ↓
 typed task queue / path / action
```

Relationships are multidimensional (affection/trust/fear/respect/etc.), not one universal friendliness score.

Memories refer to meaningful events and can feed relationships/history. Families and property connect NPC identity to the settlement economy.

---

# Economy

The settlement ledger is physical/causal:

```text
labor reservation
      ↓
production process
      ↓ consumes inputs
      ↓ creates goods
stock level versus target
      ↓
price
      ↓
trade opportunity
```

Disease, hunger and war can reduce the usable labor pool.

Market price histories are bounded daily samples so the UI can render trends without unbounded save growth.

---

# Routing, caravans and migration

Long-distance movement uses:

```text
macro-region route
    ↓
chunk corridor
    ↓
local tile path
```

Trade routes are sparse and bounded per origin rather than every settlement connecting to every other settlement.

Caravans carry cargo, value, guards and pathogen load. Arrival transfers actual goods/currency and may seed infection.

Migration cohorts transfer aggregate population plus selected named representatives. War/famine/housing pressure can create them.

---

# Epidemiology

Epidemiology owns human pathogen state.

## Definitions

A `DiseaseDef` contains transmission modes, incubation/illness duration, contagiousness, severity, mortality, immunity and season/symptoms.

## Aggregate outbreak

`DiseaseState` belongs to a settlement and tracks cases/recovered/deaths/immunity/strain/policy/trend.

Aggregate transmission considers:

```text
susceptible population
case prevalence
crowding/homelessness
sanitation
quarantine
transmission channel
season
healer/medicine capacity
```

## Named infection

`InfectionState` belongs to an NPC or player and progresses:

```text
exposed → incubating → symptomatic → recovered / fatal
```

Treatment can reduce severity/risk but is not a guaranteed cure.

## Logistics

Traveling caravans and migrants can carry pathogen loads. Quarantine reduces transmission opportunity but also trade capacity and costs municipal resources.

Disease therefore has economic consequences through labor absence, medical consumption, quarantine, transport and mortality.

## Compaction

Resolved individual infection records are removed after a retention period when no longer referenced. Durable consequences remain in host immunity/history/outbreak aggregates.

---

# Property and settlements

Properties connect physical structures to ownership/occupancy, rent/value/condition and settlement housing capacity.

Settlement state owns aggregate population, goods, labor, policy and public resources—not every distant anonymous citizen.

Large stable settlements may found new realized-region settlements; collapse can leave ruins/history. This lifecycle is bounded by realized-region rules.

---

# Factions, government and law

Governance owns offices/succession/claims. Faction simulation owns diplomacy/war. Economy owns material stocks. Combat owns physical wounds.

This prevents circular "god object" behavior.

War consumes manpower and supplies, can damage settlements and routes, and can create migration pressure.

Claims provide durable political reasons that can influence relations.

Law/crime responds to social/economic conditions; it does not simply roll random flavor events independent of scarcity/security.

---

# Knowledge and language

Knowledge is represented as facts held by people/settlements/player.

Discovery checks prerequisites. Scholars/schools bias research focus. Books are physical persistent records with author/language/facts and ownership.

Libraries own book IDs and copying consumes parchment.

Language fluency gates comprehension, creating a path from exploration → manuscript → study → knowledge instead of instant global unlocking.

---

# Religion and magic

Religious institutions own priest/follower/influence state. Migration/conversion can alter local belief and pressure may generate schisms.

Magic is seed-specific. `MagicLaw` constrains source/form/catalyst/time/terrain/instability/contamination. Experimentation yields discovered spell records. Rituals combine social/religious/material requirements.

Magic effects mutate authoritative systems (fire, water, crops, wounds, contamination). Major acts can become historical events, then myths interpreted by cultures.

---

# History / archival maintenance

History receives events; it does not directly run the systems that caused them.

High-salience events remain first-class records. Old low-salience events compact into archive buckets keyed by year/type with count/sample metadata.

Transient logistics records are pruned once their consequences are durable elsewhere.

This distinction is required for century-scale worlds.

---

# Persistence and recovery

SQLite is canonical persistent storage.

Current schema = 3.

Checkpoint principles:

- transactional save;
- engine/save/worldgen versions stored separately;
- stable JSON serialization with sorted keys for canonical hashing;
- no pickle;
- rotating SQLite backup;
- cross-record semantic verifier;
- migration rather than silent overwrite.

Schema changes must preserve old public fixtures or explicitly introduce tested migrations.

---

# UI/read-model contract

Complex systems must be inspectable.

The World Console and World Ledger expose:

- current causal alerts;
- player anatomy/infection/equipment;
- settlement economy and health;
- routes and logistics;
- ecology and LOD;
- people/families;
- institutions/knowledge;
- artifacts/provenance;
- sites/graves/history;
- magic/contamination;
- engine diagnostics.

Screens are pure read models. A UI test should compare `state.to_dict()` before/after rendering for new complex views.

---

# Example multi-system chains

## Epidemic logistics spiral

```text
crowding + poor sanitation
    ↓
outbreak
    ↓
workers become symptomatic
    ↓
productive labor shrinks
    ↓
food / metal output falls
    ↓
prices rise
    ↓
quarantine imposed
    ↓
trade capacity falls
    ↓
shortage worsens
    ↓
migration pressure
    ↓
infected migrants may export pathogen
```

## War / famine / refugees

```text
political claim
    ↓
relations deteriorate
    ↓
war
    ↓
army consumes manpower + supplies
    ↓
route danger rises / caravans lost
    ↓
food imports fail
    ↓
food stress + crime + population loss
    ↓
refugee cohort
    ↓
destination housing pressure
```

## Predator legend

```text
prey decline
    ↓
predator pressure
    ↓
local individual materializes
    ↓
attacks player
    ↓
kills player
    ↓
becomes persistent named monster
    ↓
bounty/history survive successor
```

## Scholarship / craft

```text
school focus + prerequisite knowledge
    ↓
discovery
    ↓
author writes book
    ↓
library / market ownership
    ↓
book crosses cultural border
    ↓
reader learns language/fact
    ↓
new craft process becomes usable
```

# RC7 Early-Game Integration

RC7 adds an early-game production layer without bypassing the existing authoritative simulation. New state includes carcasses, timed processing jobs, prepared meals, nutrition history and food effects. These records are persisted through `LivingWorldState` and advanced by simulation time.

## Causal chains

### Primitive technology
natural resource -> hand process -> tool quality -> new harvest/process capability -> better station -> improved efficiency/yield

### Hunting
habitat/cohort -> local animal -> combat damage -> carcass quality -> field processing -> meat/hide/bone/fat/sinew/offal -> cooking/preservation/craft/trade

### Food
forage/hunt/farm -> ingredient -> cooking method + station -> prepared meal -> hunger/macros/diet groups -> short food effects -> recovery/stamina/exposure

### Farming
wild/farm seed -> tilling tool -> soil N/P/K + water + climate + disease -> crop -> food/fiber/seed -> cooking/craft -> soil depletion/rotation

### Furniture
materials -> construction -> environmental/work/processing/storage effect -> survival or production efficiency

## Ownership boundaries

- `ResourceSystem` owns deterministic natural features and depletion/regrowth.
- `ProcessingSystem` owns carcass actions and timed preservation jobs.
- `CookingSystem` composes meals.
- `NutritionSystem` owns diet history and food effects.
- `FarmingSystem` owns crop growth and soil demand.
- `BuildingSystem` exposes station/environmental bonuses but does not perform crafting itself.
- `Simulation` validates commands, advances time and composes these systems.

## RC8 presentation adapter

Graphics are downstream of simulation. `worldseed/presentation/visuals.py` resolves stable content IDs into visual paths. `worldseed/ui/pygame_terminal.py` may inspect already-realized local state for presentation, but it must not advance time, roll simulation RNG, realize distant regions, create entities or alter saves. See `VISUAL_ARCHITECTURE.md`.


## Seeded world preparation (RC13)

New worlds pre-generate and persist a bounded opening envelope before the simulation begins. The database stores deterministic base terrain chunks keyed by generator version and deterministic natural-resource chunks keyed by resource-generator version plus season. Runtime tile deltas, depletion, crops, structures and other authored state remain separate overlays. If a prepared terrain ID no longer resolves because content changed, the engine safely falls back to deterministic regeneration.

## Dev31 exploration presentation/performance contract

Ordinary movement advances **1 game minute**. Other actions retain authored durations; simulation time remains command-owned rather than tied to render frames.

Surface visibility has two layers: persistent **discovery memory** and transient **current visibility**. Current visibility is a circular, line-of-sight-limited radius derived from Perception, Survival, talents, weather visibility/fog, and ambient light. Previously discovered but currently unseen terrain may be shown dimly, but entities/resources must not be rendered outside current visibility.

The terrain atlas reads only actually discovered cells. Discovery of one cell never promotes a whole 512-cell region. Atlas reads use the same versioned surface-cache contract as local terrain, remain generation-free, and use a runtime per-chunk discovery index so panning cost is bounded by the requested view. Atlas LOD is categorical rather than raw RGB averaging so thin rivers do not acquire thick floodplain/riverbank halos.

Cloud shadows are presentation-only world-space fields. Their absolute positions derive from seed/world coordinates and their drift from weather wind plus visual elapsed time, so moving the camera cannot drag clouds with the player. Visual elapsed time never advances simulation weather or the game clock.

Local pygame entity lookup is spatially bucketed; a frame must not scan every realized NPC/creature/structure in the explored world. Routine autosaves persist authoritative state without making a full rotating SQLite backup; explicit manual/menu/quit saves retain rotating backups.

## WORLDGEN v8 Phase 5 coastal morphology

`worldseed/world/coast_v8.py` is the Phase-5 read authority over v8 coastal shape. It consumes the existing geological elevation/topography, physical climate and prepared hydrology; it does not generate a second coastline, mutate terrain, or render effects. Current fields include continental-geometry shelf depth, open-sea exposure, shelter, bay/headland tendency, coast class, shore-material tendency, tidal-flat/marsh/lagoon potential, sediment proxy, estuary strength and delta potential.

Dev33 introduces the first save-visible materialization contract. New v8 worlds record `coast_morphology_version = 1`; existing v8 saves missing the field infer version 0 and retain their previous shoreline. Surface cache identity is now `worldgen + hydrology + hydrology morphology + coast morphology`. Coast v1 can materialize `core:shore`, `core:coastal_gravel`, `core:rocky_shore`, `core:coastal_cliff`, `core:tidal_flat`, `core:salt_marsh`, and the existing ocean depth family. River-mouth fields are allowed to remain zero when hydrology is unprepared; inspection must never solve missing drainage merely to populate a coast read.

For generation performance, detailed coast geometry is reused on an absolute 8-cell materialization lattice while exact geological elevation still decides land/ocean for every tile. This is a bounded projection optimization, not a second coastline authority.

---

## Source: `UI_GUIDE.md`

# WORLDSEED v1.0 RC6 — terminal UI architecture

WORLDSEED's simulation can become arbitrarily deep; the control scheme must not become arbitrarily complicated with it. RC6 retains the retained screen-stack and canonical input model, and extends the UI contract to discovery-gated information, startup/pause flows, contextual adjacent interactions, and mouse/paste isolation.

## Player mental model

Normal play should require only seven concepts:

```text
WASD / arrows   move
Enter           do something
TAB             understand/manage the world
I               inventory
L               inspect space
?               help
Q               save and quit
```

Everything else is an optional accelerator. New systems should normally enter either the **Action Hub** or the **World Console**, not claim another globally required hotkey.

## Screen ownership

```text
raw terminal key
      ↓
ui/router.py          semantic Intent
      ↓
app.py                dispatch / command creation
      ↓
simulation kernel     authoritative state mutation
      ↓
ui/renderer.py        observational gameplay HUD
      ↓
ui/screens.py         observational reports/detail views
```

Supporting modules:

```text
ui/layout.py       responsive geometry
ui/widgets.py      menus, panels, pagers
ui/navigation.py   menu information architecture
ui/alerts.py       read-only causal alert projection
ui/terminal.py     platform input + presentation only
```

The renderer and report screens may **never** realize regions, advance time, roll simulation RNG, alter inventories, or write persistent state merely because the player opened a screen.

## Responsive layout modes

`compute_layout()` owns the viewport geometry.

### Wide

Used when the terminal is at least roughly 124 columns and 28 rows and dense UI is enabled.

```text
+------------------------------------------------------+---------------------------+
|                                                      | STATUS                    |
|                    WORLD MAP                         | health / needs            |
|                                                      |                           |
|                                                      | ALERTS                    |
|                                                      |                           |
|                                                      | NEARBY                    |
|                                                      |                           |
|                                                      | GEAR                      |
+------------------------------------------------------+---------------------------+
| recent event / action result                                                     |
| compact status                                                                    |
| WASD Move   Enter Actions   TAB Console   I Pack   L Look   ? Help   Q Save/Quit |
+-----------------------------------------------------------------------------------+
```

### Standard

The map owns the width. Status is moved below it. No sidebar is squeezed alongside the map.

### Compact

A minimal status line and the same essential controls are retained. Advanced information remains available through TAB.

### Tiny

Below 60×18, WORLDSEED displays a resize message instead of allowing the shell to wrap and corrupt the interface.

## No-overlap rule

A rendered frame must satisfy both:

```text
rendered_line_count <= terminal_height
visible_width(line) <= terminal_width
```

ANSI escape sequences do not count as visible width. Tests cover 60×18, 80×24, 100×30, 124×32 and 160×45.

`Terminal.present()` homes the cursor, resets attributes, writes the new frame, then clears the remainder of the old alternate-screen buffer. A shorter modal therefore cannot leave fragments of a previous longer screen behind it.

## Menus

Menus support a game-like WASD navigation model as well as arrows:

```text
W / Up          previous item
S / Down        next item
D / Enter       select / move forward
A / Esc         back exactly one UI layer
PageUp/PageDown page
Home / End      first / last
Q               optional back alias inside menus
1-9             optional quick choice on current page
```

The terminal backend canonicalizes platform-specific raw key values before UI code sees them. In particular, Windows `msvcrt.getwch()` emits the physical Escape key as the literal `\x1b` character; WORLDSEED normalizes that value to the canonical `ESC` token. Widgets defensively normalize it a second time so fake/test backends and future terminal adapters cannot silently bypass Back behavior.

Numbers are shortcuts, not the primary navigation requirement.

All menus use `ui/widgets.py::select_menu`. Feature code should not create bespoke menu loops.

## Action Hub — Enter

The Action Hub is for **verbs**:

```text
Interact
  gather
  pick up
  inspect
  inventory/storage

Survival
  eat
  equipment
  wound treatment

Work
  craft
  build
  dismantle
  farming

Combat
  attack

World
  market
  books
  magic
  vertical travel
```

A new player-action system should normally add itself here.

## World Console — TAB

The World Console is for **information, management and causality**.

```text
[!] Alerts
[@] Character & survival
[.] Local world & construction
[W] World, settlements & ecology
[$] Society, economy & politics
[*] Knowledge, religion & magic
[#] Records, chronicle & world ledger
[~] Simulation & settings
```

Each category opens a smaller second-level menu. This prevents a flat list of 15–30 unrelated screens.

## Long information

The pager reflows legacy/report output to the actual terminal width. Long records support arrows, PageUp/PageDown, Home and End. This is important because a 70-year-old NPC, artifact provenance chain or settlement ledger can legitimately become much longer than one terminal screen.

## HUD information budget

The normal map HUD contains only information useful for the next few actions:

- survival state;
- severe alerts;
- genuinely nearby actors;
- equipped gear;
- current terrain/room;
- last action result.

A distant housing shortage, trade-route ledger or century-old chronicle entry belongs in the World Console, not in the combat HUD.

## Adding a new UI feature

1. Decide whether it is a **verb** (Action Hub) or **information/management** (World Console).
2. Add navigation metadata to `ui/navigation.py`.
3. Use `select_menu`, `view_text`, and `panel`; do not create custom terminal loops unless a spatial interaction truly requires one.
4. Keep state mutation inside a simulation command/system.
5. Add an observational test for any read-only screen.
6. Add viewport tests if the feature changes the gameplay HUD.
7. Never allocate a global letter if the feature can be discovered through Enter or TAB.

## Power-user shortcuts

Direct hotkeys remain supported for frequent players, but they are secondary. `ui/router.py` is the only authoritative global key table. The module asserts that `W/A/S/D` can never collide with menu shortcuts.

## Retained screen stack

All hierarchical interfaces must use `NavigationStack` / `RouteState`. A route stores:

```text
route id
title
selected row
scroll offset
payload / record identity
```

The required navigation semantics are:

```text
push child        -> preserve parent state
ESC on child      -> pop child
ESC on root       -> dismiss feature to gameplay
replace route     -> explicit operation only
render/input      -> top route only
```

Never implement a feature by nesting blocking menus and then restarting the root menu after a child closes. That loses navigation context and is the navigation bug RC3 fixes. Parent selection and scroll must survive a child route.

`Q` may act as Back inside a modal/menu for accessibility, but only gameplay root interprets Q as save/quit.

Breadcrumbs should be derived from the stack, never manually assembled from feature-specific globals.


## Startup, pause and discovery UI

Startup is a first-class routed UI: Main Menu → Continue/New/Load/Help/Quit. New Game is a wizard rather than free-form terminal prompts. Gameplay-root ESC opens Pause; ESC inside a child UI still means Back.

UI code must respect the **player-knowledge boundary**. A screen may not display a proper NPC/town/faction/site/event name simply because the simulation model contains it. Use the simulation's `known_*` helpers/discovery collections. Unknown nearby NPCs render as Stranger.

Contextual interaction screens should prefer reachable targets (current tile + cardinal neighbors) and say what tool/action is required before failing. This is especially important for mining walls, chopping blocking trees, storage and structures.

# RC7 craft/build/food UI rules

- Group recipes and structures by player purpose, not internal file/order.
- Show `READY` or `NEEDS` before selection.
- Use readable material names and counts; hide raw content IDs.
- Detail panes explain description, time, station/tool/skill requirements and what the result enables.
- Cooking is ingredient selection with a live nutrition preview.
- Carcass processing presents only valid next operations for the selected carcass.
- Timed processing jobs must be inspectable as work-in-progress rather than disappearing until completion.
- Health UI separates immediate vitals from Nutrition & Diet history.

## RC8 custom-window presentation

The UI's information architecture remains renderer-independent. `PygameTerminal` implements the same basic present/read-key contract as the ANSI backend, so World Console, inventory, crafting, construction and other retained menu flows run inside the dedicated game window without simulation changes.

The local world view uses `present_game()` for a hybrid sprite map. Right-click maps to Back/Escape; mouse wheel maps to page movement. Future hover/click semantics must be implemented in the presentation layer and must not mutate simulation merely because the pointer moved.

`M` opens the graphical Region Map described in the RC14 Dev5 handoff. Each block represents 512 x 512 world cells. Discovered regions show their prepared plan's dominant biome and relief, regional road/trail connections, prepared water connections, and known settlements. Shared exits use their stored 0..511 offsets; the current region is outlined. Unknown regions stay dark. Missing plans are shown as uncharted, never generated by opening the map. Underground discoveries do not reveal the surface. Full-screen transitions clear gameplay hover overlays so moving the cursor cannot repaint the local view over the regional map. Dev5 lines are strategic connections; exact local road corridors and ford/bridge crossings remain Dev6 work.

Regional terrain artwork is procedural: biome symbols, moisture-dependent vegetation/color, cold tint, and relief ridges come from that region's existing terrain summary. The same region retains the same artwork when reopening or resizing the map. Road, water, settlement and player overlays remain visible above it. These atlas symbols summarize terrain character rather than marking exact local trees or mountain positions. See `docs/REGIONAL_TERRAIN_ASSETS.md` for profiles and sample asset export.


## RC14 parallel UI track — unified graphical inventory

The graphical inventory is a single retained surface rather than a pack-summary menu followed by a second carried-items menu and then a third action menu.

- Pressing **I** opens the carried-item icon grid directly.
- Selecting or hovering an item keeps the grid visible and updates an inspection pane on the same screen.
- The inspection pane shows the item icon, description, category, quantity, per-item mass/volume and relevant food/tool/weapon/equipment facts.
- Legal actions are contextual buttons on that pane. Current actions are **Use**, **Drop**, **Split amount**, and **Store** when a reachable container exists.
- **Split** is a UI quantity selector, not a second inventory authority. The authoritative inventory remains the existing item-count model; the selected amount is consumed only when a command such as Drop or Store is submitted.
- Mouse actions have keyboard parity: U use, X drop, H half/split, E store, [ / ] adjust quantity, M select all, arrows navigate items, and Esc closes the inventory.
- Item selection, hover and quantity changes are presentation state only. Drop, eat, equip, read and store still execute through simulation commands.
- The terminal backend retains the hierarchical fallback so the graphical redesign does not remove non-pygame access.
NaN, **ALL**, and **Half stack** control the transfer amount without a quantity submenu;
- transfer actions keep the storage view open;
- movable containers expose directional move controls;
- natural containers expose **Break apart**, which is an authoritative simulation action rather than a renderer mutation.

Container transfer keyboard parity is T transfer, H half stack, [ / ] quantity, M all, X break apart, arrows for selection, and Esc back. Pointer targets continue to emit semantic UI tokens only; store/take/move/destroy state changes remain simulation commands.

Generated natural containers are realized by simulation discovery, not by rendering. Opening an inventory or moving the pointer therefore cannot generate loot or mutate world state.

---

## Source: `UI_RESEARCH.md`

# WORLDSEED RC3 — terminal UI research notes

RC3's navigation redesign was based on patterns used by mature terminal UI systems rather than on another set of feature-specific key checks.

## Findings applied

### 1. Screen stacks are the right abstraction for Back
Textual models active views as a screen stack: pushing a screen makes it active, popping restores the previous screen, and the base/root screen is not casually discarded. WORLDSEED now mirrors that behavior with `NavigationStack` and `RouteState`.

### 2. Only the top/modal UI should own input
Textual modal screens and prompt_toolkit modal containers prevent parent bindings from firing while a child has focus. Urwid overlays similarly direct keyboard input to the top widget. WORLDSEED follows the same rule conceptually: the top route is the only route reading keys.

### 3. UI state must be explicit
Ratatui's application patterns recommend explicit current-screen/application-mode state and the Elm-style Model → Update → View separation. WORLDSEED retains route selection and pager scroll as explicit state rather than reconstructing menus after every child closes.

### 4. Back is navigation; Quit is application control
Inside a menu or detail view, ESC means Back. At a feature root, ESC dismisses that feature to gameplay. Only gameplay root interprets Q as save/quit. Q remains an optional Back alias inside modal menus for accessibility.

### 5. Breadcrumbs must reflect actual navigation state
Breadcrumbs are derived from the route stack, so `World Console > Records > World Ledger > People` corresponds to actual restorable parent states rather than decorative labels.

## WORLDSEED invariants

```text
ESC on child       -> pop exactly one route
ESC on feature root -> return to gameplay
push child         -> preserve parent selected row + scroll
close detail       -> restore exact parent
only top route     -> receives input
rendering          -> never mutates simulation
Q at gameplay root -> save and quit
```

## Relevant upstream documentation reviewed

- Textual — Screens / screen stack / modal screens
  https://textual.textualize.io/guide/screens/
- Textual — App `push_screen` / `pop_screen`
  https://textual.textualize.io/api/app/
- Ratatui — application screen state and modes
  https://www.ratatui.rs/tutorials/json-editor/app/
- Ratatui — The Elm Architecture
  https://www.ratatui.rs/concepts/application-patterns/the-elm-architecture/
- prompt_toolkit — modal containers and key-binding isolation
  https://python-prompt-toolkit.readthedocs.io/en/stable/pages/reference.html
- Urwid — overlays keep top widget focused for input
  https://urwid.org/manual/widgets.html


## RC4 finding — normalize keys before navigation

The RC3 stack logic was correct, but platform adapters were not producing a single key vocabulary. On Windows, WORLDSEED uses `msvcrt.getwch()`, which returns a single character from the console; the physical Escape key arrives as the literal escape character (`\x1b`). The Unix parser had already converted standalone Escape to `ESC`, so Windows and Unix were feeding different values into identical menu code. RC4 adds terminal-boundary normalization and widget-level defensive normalization.

The retained-screen design remains aligned with Textual's screen-stack model: only the top screen receives input and popping restores the previous screen. Prompt-toolkit similarly treats key parsing/bindings as a distinct layer from application actions; WORLDSEED now follows the same separation by canonicalizing backend input before menu semantics are applied.

---

## Source: `VISUAL_ARCHITECTURE.md`

# WORLDSEED RC8 Visual Architecture

## Decision

WORLDSEED's primary window renderer is **pygame-ce**.  The ANSI terminal backend remains supported as a fallback/debug presentation.

The renderer is an adapter.  Simulation state, command handling, deterministic RNG, saves, world generation, AI, ecology and economy do not import pygame or sprite assets.

## Presentation boundary

```text
Simulation / LivingWorldState / ContentRegistry
                |
                v
        presentation.visuals
          stable visual IDs
                |
      +---------+---------+
      |                   |
 ANSI Terminal      pygame-ce Window
 glyph fallback     hybrid sprite map
```

`worldseed/presentation/visuals.py` owns the mapping from stable content IDs to image files. Missing art can degrade to glyphs, while `tools/audit_visuals.py` makes full coverage a release gate.

## RC8 hybrid renderer

The main local world is now drawn as layered sprites inside a normal resizable game window. Menus and reports remain terminal-like text panels inside that same window. This preserves WORLDSEED's information density while removing dependence on Windows Terminal / ANSI rendering for normal play.

Layer order in RC8:

1. ground terrain
2. fluid overlay
3. natural resource feature
4. crop growth stage
5. structure/furniture
6. ground item pile
7. carcass
8. fire
9. living creature
10. NPC
11. player
12. targeting/look cursor
13. UI chrome / status / log

Visual dimensions never define simulation footprint. A tree may visually overhang neighboring cells while mechanically occupying one world position.

## Input

Pygame receives actual keyboard and mouse events. WASD/arrow semantics remain unchanged. Right-click maps to Back/Escape and mouse wheel maps to page scrolling in terminal-style menus. The old terminal parser remains available under `--terminal`.

## Assets

Generated runtime assets live under `worldseed/assets/`:

- `visuals.json` — per-content visual manifest
- `atlas_index.json` — future atlas/batching metadata
- `sprites/items/`
- `sprites/terrain/`
- `sprites/resources/`
- `sprites/structures/`
- `sprites/crops/`
- `sprites/species/`
- `sprites/npc/`
- `atlases/`

The current sprite generator is deterministic. It is safe to replace individual generated PNGs with hand-authored art while preserving the same manifest path/ID.

## Sprite evolution plan

### RC8
- dedicated pygame-ce window
- hybrid map renderer
- complete sprite coverage
- animal/NPC variation
- atlas metadata
- ANSI fallback

### Next visual pass
- proper hover hit-testing and tooltips
- click-to-select/context actions
- animation timelines driven by simulation events
- equipment overlays on NPC/player sprites
- directional animal/NPC frames
- terrain edge/autotile masks
- animated water/fire/weather
- lighting and darkness map
- zoom presets

### Later
- procedural modular sprites for generated species
- body/hair/clothing/equipment composition for named characters
- structure material overlays
- sprite LOD for local/spatial/world views
- optional GPU-batched backend if profiling justifies it

## Performance rule

Presentation must remain observational. Opening, resizing, hovering or rendering must never realize world regions, roll RNG, advance time, mutate ecology, or alter saves.

---

# Release Notes and Completion Reports

---

## Source: `CHANGELOG.md`

## RC14 Dev34 — inventory polish and living storage

- Polished the unified graphical inventory with clickable category filters while preserving the single-screen item grid, rich inspection pane and inline quantity/action controls.
- Replaced the pygame container submenu chain with a dual-pane backpack/container inventory. Items transfer directly in either direction with quantity, half-stack and all-stack controls while the container stays open.
- Added explicit container targeting to store/take commands so visual transfer actions cannot accidentally act on a different nearby container.
- Added movable-container and natural-container destruction commands; movement keeps persistent structure/container state together and natural destruction spills contents plus deterministic salvage.
- Promoted natural-resource placement to Resourcegen v4 for new worlds and added deterministic hollow logs, rotten stumps and rock crevices as discoverable storage features with habitat rules, randomized seeded contents and save-persistent realization.
- Hollow logs can be moved; rooted stumps and rock crevices remain fixed but can be broken apart. Generated natural containers never regrow after realization, movement or destruction.
- Added craftable Wicker Basket and Wooden Storage Box items and recipes, then made them placeable as movable storage through the existing construction system. Existing Wooden Chests remain available.
- Natural-only container templates are excluded from the player's construction catalog.
- Added content validation for natural-container structure/loot/salvage references and Dev34 regression coverage for deterministic loot, movement, destruction, crafted placement, keyboard transfer intent and small-window pointer bounds.
- Existing resourcegen-v3 saves remain pinned to their old natural-resource layout; Dev34 storage features appear in new resourcegen-v4 worlds rather than silently changing old exploration geography.

## RC14 Parallel UI Track 1 — unified graphical inventory

- Replaced the pygame inventory's duplicate Pack Overview -> Browse Items -> Item Actions chain with one retained visual inventory surface.
- Pressing I now opens the carried-item icon grid directly; clicking an item updates its description, physical stats and gameplay traits without leaving the grid.
- Added inline contextual Use, Drop, Split and Store controls plus quantity selection (- / + / All). Split selects a portion of the existing count for transfer/drop rather than creating a conflicting second stack model.
- Use resolves to existing authoritative commands for food, equipment and carried books; Drop and Store preserve their command boundary and support selected quantities.
- Inventory actions keep the inventory open after execution so repeated organization no longer requires reopening nested menus.
- Added mouse and keyboard parity (U/X/H/E, [ ], M, arrows, Esc) and retained the legacy terminal inventory flow as a fallback.
- Expanded the inventory presentation data with per-item mass/volume, material and relevant food/tool/weapon/equipment facts.
- Added focused widget and real pygame pointer regression coverage for unified selection, split quantity and drop behavior.

## RC14 Dev33 — Phase 5 coastline materialization

- Added `COAST_MORPHOLOGY_VERSION = 1` as an independent save-pinned shoreline contract.
- New worlds now materialize continental-geometry bathymetry into actual wading, shallow, shelf and deep-ocean terrain rather than relying only on the older local-slope distance approximation.
- Added real coast terrain classes for rocky shore, coastal cliff, coastal gravel, tidal flat and salt marsh while retaining sandy shore.
- Coastal cliffs are physically impassable/vision-blocking terrain; the other new shore classes remain traversable for now.
- Reused existing approved rock/riverbank/floodplain/wetland art families so the new geography works immediately without overwriting the newly updated rain/cloud/tree/morel/cave graphics.
- Added distinct atlas colors so the new shore types remain visible in cartography.
- Existing v8 saves without coast metadata infer coast version 0 and preserve their old shoreline instead of silently changing geography.
- Surface generated-cache identity now includes coast version. A new additive cache table preserves compatibility with Dev30/Dev32 cache rows.
- Bounded coast materialization cost with an absolute 8-cell classification lattice while retaining exact per-cell geological land/ocean authority.
- Fixed stale atlas drag regression fixtures discovered by the expanded validation gate.
- Full delta distributaries, barrier islands/spits and dedicated coast art remain later Phase-5 work.

## RC14 Dev32 — WORLDGEN v8 Phase 5 coast foundation

- Resumed the staged WORLDGEN v8 roadmap after the Dev31 playtest and visual correction work.
- Kept Hydrology v2 / morphology v2 as the frozen Phase-4 drainage baseline.
- Added a terrain-neutral Phase-5 coastal morphology read model over authoritative v8 geology, topography, climate and prepared hydrology.
- Added continental-geometry shelf depth, exposure/shelter, bay/headland tendency, coast classes and shore-material tendency.
- Added tidal-flat, marsh and lagoon potential plus river-mouth sediment, estuary and delta potential.
- Exposed coastal reads through WorldGenerator/World without changing terrain IDs, save schema or generated surface-cache contracts.
- Added deterministic Phase-5 tests and a multi-seed coastal morphology audit.
- Preserved the newly merged rain/cloud atmosphere work and the corrected tree, morel and cave artwork unchanged.

## RC14 Dev31 — playtest correction pass

- Reduced ordinary movement time from 5 minutes to 1 minute while keeping authored action durations intact.
- Replaced rectangular discovery with a true circular LOS radius driven by Perception, Survival, Keen Senses, weather visibility/fog and ambient light.
- Split persistent exploration memory from current visibility; out-of-sight known terrain is dimmed while entities/resources remain hidden.
- Reworked atlas discovery to load only actually discovered cells through the versioned surface cache, eliminating large square reveals and reducing long-exploration map cost.
- Added mouse-drag atlas panning, wheel zoom and a single Center on player control; removed directional/zoom button clutter.
- Replaced distant atlas RGB averaging with categorical LOD to reduce thick riverbank/floodplain intestine-like river outlines.
- Rebuilt cloud shadows as world-anchored, multi-lobed cloud banks that drift continuously with wind instead of following the player/camera.
- Warmed and lengthened dawn/dusk presentation with lighter amber/orange transitions.
- Added viewport spatial buckets so local rendering no longer scans all realized world entities as exploration grows.
- Routine autosaves no longer create rotating full-database backups; explicit saves still do, reducing large-world autosave freezes.
- Added Dev31 regression tests, playtest checklist and deterministic mountain-test location generation.

## RC14 Dev30 — Hydrology v2 morphology materialization

- Added `HYDROLOGY_MORPHOLOGY_VERSION = 2` so river projection can evolve without rewriting Dev29 hydrology-v2 saves.
- Added versioned surface chunk caching keyed by worldgen + hydrology + morphology, fixing the old worldgen-only surface-cache ambiguity.
- Replaced morphology-v2 single-midpoint channels with deterministic multi-point centerlines.
- Materialized suitable braided reaches as split/rejoining water threads with natural underlying-terrain islands between them.
- Materialized deterministic shallow oxbow/meander-scar water in mature low-gradient floodplains.
- Added rocky gorge-bank projection beside steep rugged reaches.
- Updated river-current lookup to use the same multi-point/braided geometry as terrain.
- Added bounded geometry caches plus morphology regression/audit tooling.
- Dev29 saves missing morphology metadata remain pinned to morphology v1.

## RC14 Dev29 — Hydrology v2 foundation

- Promoted new saves to `HYDROLOGY_VERSION = 2` while preserving existing saves at their recorded hydrology version.
- Added version-aware hydrology algorithm IDs so cached v1 river plans remain loadable beside v2 plans.
- Added persisted v2 runoff and channel-gradient fields; runoff now derives from authoritative Phase-3 precipitation with wet-upland headwater support.
- Updated river classification to use climate-driven discharge accumulation.
- Added gradient-sensitive meanders and tributary/confluence widening.
- Replaced hash-first ford placement with physical suitability gates based on river class, channel gradient, bank slope, discharge and floodplain context.
- Added rapid/gorge, braided-reach, oxbow/meander and near-sea delta candidate read fields.
- Updated World/startup hydrology construction to honor save-pinned hydrology metadata.
- Expanded hydrology audit output and regression coverage for v1/v2 compatibility and seam continuity.
- Full braided islands, oxbow terrain and delta distributaries remain later Phase-4/Phase-5 work.

## RC14 Dev28 — WORLDGEN v8 physical climate and living weather

- Replaced v8's temporary inherited moisture/temperature fields with physical climate circulation driven by climate belts, maritime influence, continentality, prevailing wind, altitude, orographic lift and rain shadows.
- Added deterministic humidity and wind-strength climate fields and exposed authoritative `climate_at()` reads through WorldGenerator/World.
- Reworked v8 weather into wind-advected climate-driven cells with cloud cover, rain, storms, fog, recent-rain wetness and weather temperature deltas.
- Rain now contributes to crop moisture and suppresses realized fires.
- Added season-aware dawn/day/dusk/night lighting.
- Added procedural weather art and animation to the pygame local renderer: wet terrain textures, projected cloud shadows, animated rain streaks and splashes, fog haze, night/dawn/dusk grading and fire glow.
- Added weather/time status to the local sidebar while keeping the renderer observational.
- Added Phase-3 climate/weather/lighting tests and `tools/audit_worldgen_v8_climate.py`.
- Hydrology v2 remains the next world-generation phase.

## RC14 Dev27 — WORLDGEN v8 promoted for new worlds

- Promoted `WORLDGEN_VERSION` from 7 to 8. Newly created save databases now use the geological v8 elevation/topography contract by default.
- Preserved v1-v7 geography through each save's recorded `worldgen_version`; opening a legacy save does not migrate or regenerate its terrain.
- Kept `WORLDGEN_PREVIEW_VERSION` as a compatibility alias for the v8 audit tools created during staging.
- Updated Phase-2 and RC14 hydrology regression contracts for the v8 default while retaining hard-coded v7 field fixtures and frozen RC13/v4 terrain fingerprints.
- Added a dedicated v8 promotion regression covering new-save metadata, legacy-v7 reopen behavior, and default-v8 versus explicit-v7 generator selection.
- Added a real-stack v8 startup audit covering spawn selection, prepared hydrology relocation, dryness/passability, local connectivity and landform context.
- Updated README, SYSTEMS and AGENTS contracts so future development treats v8 as current for new worlds and v1-v7 as immutable legacy geography.
- Phase 3 physical climate circulation is now the next world-generation development target.

## RC14 Dev26 — WORLDGEN v8 topography and cave siting

- Added a deterministic v8 topography read model exposing slope vectors, normalized slope, raw/normalized relief, ridge exposure, valley depth and ruggedness from authoritative geological elevation.
- Added `WorldGenerator.topography_at()` and `World.topography_at()`; legacy v1-v7 worlds do not expose v8 topography.
- Added a v8-specific cave entrance planner that prefers exposed geological relief, slopes, ridges, mountain belts and plateaus while preserving the entire v7 cave-placement contract for old worlds.
- Added topography-aware cave-depth adjustments for rugged/tectonically uplifted v8 sites without yet changing underground chamber or ore generation.
- Added targeted topography/cave regression tests and a calibration audit for slope, relief, ruggedness, valleys, ridges and cave-mouth characteristics.
- WORLDGEN_VERSION remains 7 and WORLDGEN_PREVIEW_VERSION remains 8 pending full promotion gates.

## RC14 Dev25 — WORLDGEN v8 Phase-2 authority staging

- Implemented the v8 elevation authority boundary for explicit preview worlds while keeping ordinary new worlds on frozen worldgen v7.
- Added `WORLDGEN_PREVIEW_VERSION = 8`; v8 sample fields now take elevation from the geological landform compositor while retaining v4 moisture/temperature drivers until the climate-circulation phase.
- Added an authoritative v8 `landform_at()` read model and hard-coded v7 field fixtures to guard the legacy generation contract.
- Added a multi-thousand-cell v8 spawn search so large v8 oceans/continents cannot strand startup inside the old 576-cell search envelope; v4-v7 spawn behavior is unchanged.
- Added an eight-seed Phase-2 calibration tool reporting ocean coverage, start-like land availability, elevation deltas, gradients, province distribution and deterministic fingerprints.
- WORLDGEN_VERSION remains 7 until executable integration, golden-seed and spawn-fairness gates pass.

## RC14 Dev24 — WORLDGEN v8 geological systems iteration 2

- Reworked the v8 prototype around slowly varying tectonic stress: long major mountain belts now share regional orientation, smaller branch ranges inherit that stress, and major belts use deterministic bends instead of perfectly straight segments.
- Added structural/rift-valley corridors and incorporated them into prototype elevation/province classification for future drainage and settlement corridors.
- Restricted shoreline roughening to the continental threshold and attenuated uplift over deep-ocean continentalness so mountain generation does not routinely create artificial ruler-like ocean bars.
- Expanded the landform audit with separate province, elevation, mountain-strength and valley-strength PPMs plus gradient and coastline-edge metrics.
- Added a direct v7-versus-v8 elevation comparison tool for Phase-0 golden-seed analysis.
- WORLDGEN_VERSION remains 7; the v8 work is still observational and cannot alter current saves, terrain, hydrology, resources or spawn behavior.

## RC14 Dev23 — WORLDGEN v8 geological prototype

- Added the detailed WORLDGEN v8 Geological Living World roadmap with 16 staged phases from baseline freeze through release hardening.
- Started Phase 1 with a non-authoritative geological landform sampler: continental swells, elongated deterministic mountain/orogeny systems, basins, plateaus, local roughness and province classification.
- Added a standard-library audit exporter that writes field CSV, PPM preview and deterministic summary fingerprints.
- Added v8 prototype determinism/integration tests and exposed read-only prototype sampling through WorldGenerator.
- Kept WORLDGEN_VERSION at 7: current/legacy terrain, hydrology, saves, spawn, resources and rendering are unchanged until the v8 elevation promotion gate is explicitly passed.

## RC14 Dev22 — Authoritative terrain atlas

- Replaced the gameplay map's illustrative biome blocks and schematic river spokes with actual prepared/local terrain tiles, saved deltas and live edits.
- Added bounded read-only atlas snapshots, exact negative-coordinate mapping, generator-version isolation and future terrain tag/color fallback.
- Added nine illustrated POI assets: village, city, camp, cave, fortress, temple, mine, archive and crypt. Markers use known world records; no invented settlements or sites.
- Added mouse zoom/pan/recenter, exact terrain inspection, clickable POIs and pageable place lists, preserving WASD movement-only controls.
- Newly materialized base chunks are retained in the existing generated cache, so atlas coverage survives LRU eviction. Missing/uncharted data remains unknown.
- No save-schema, worldgen-version or simulation RNG changes.

## RC14 Dev21 — Mouse-driven interfaces

- Added a persistent ten-button HUD for all primary routes; World and Actions expose remaining systems.
- Removed WASD menu navigation, added hit-tested card selection/hover, paging and Back controls.
- Separated gameplay, UI, text and targeting input: menu wheel cannot zoom the world; entering menus and losing focus clear held movement.
- Added mouse character appearance, point allocation, talent selection, direction prompts and map targeting.
- Added modal window-close handling that saves through the application boundary.
- Preserved arrow/Enter/Esc terminal support and existing save/gameplay contracts.

## RC14 Dev20 — Character art and crash fixes

- Recreated 10 male and 10 female player appearances; replaced NPC variants with 24 clean survivor sprites.
- Added smooth cached character scaling and centered appearance preview.
- Fixed ten keyword-only icon-scale call errors across crafting and inventory renderers.
- Fixed undefined selection variable during new character creation; preserved legacy tuple startup support.
- Added real SDL renderer and character-selection regression coverage.

# RC14 Dev16 - terrain meshing, caves, and discovery crafting UI

## RC14 Dev19 — Graphical Inventory & Discovery Crafting UI

- Replaced generic pygame inventory/crafting cards with icon-rich pack, item, recipe, experiment, material, tech-tree, and component-design presentations.
- Added structured presentation hooks to shared widgets while preserving terminal fallback and simulation authority.
- Added graphical item details, recipe readiness/material views, discovery progress, and a dependency-derived crafting tech tree.


- Replaced pair-specific local terrain transitions with a tag-driven meshing catalog. Grassland/floodplain now feather as a soft same-family ecotone, and future surface/underground ground terrain automatically participates unless marked as a hard feature such as ore, shaft or loot.
- Promoted new worlds to worldgen v7. Cave mouths are selected from terrain relief/upland candidates instead of sparse flat RNG columns; connector depth and nearby chambers are deterministic and reciprocal. Legacy v1-v6 geography remains frozen.
- Added vertically correlated cave topology with shallow/sedimentary/fracture/crystalline depth bands, depth-sensitive coal/aquifer/copper/iron placement, a complete copper ore -> ingot chain, and cave geology information for skilled inspection.
- Rebuilt cave-mouth presentation as eight transparent contextual overlays so entrances inherit their surrounding biome instead of appearing as square black/gray tiles. Added new cave wall, coal, iron, aquifer and copper textures.
- Added persisted discovery crafting for new worlds: handling new material types reveals simple techniques, compound techniques become trial-and-error experiments, and a derived discovery tree exposes known/testable/locked branches without mutating state from the UI.
- Added native graphical menu/document rendering to the pygame client. Inventory and crafting now present as card-based panels with contextual tabs while retaining the same keyboard navigation and authoritative command boundary.
- Added terrain-meshing and cave-v7 audit tools plus Dev16 regression coverage.

# RC14 Dev15 - oceans, rivers and swimming

- New-world generator v6: physical shore, wading, shallow, shelf and deep-ocean zones.
- Prepared rivers gain sandy gravel banks, streams and slope-driven rapids; lakes and brackish mouths have separate water types.
- New smooth water materials, depth blending and idle animation; swimming sprite/wake and water hover/status information.
- Swimming spends stamina, improves a persisted skill, scales with Endurance, carried mass and current direction. Exhaustion damages health; bridges and shallows provide safety.
- Existing saves preserve geography; use a new world for v6 terrain.

# Changelog

- RC14 dev5: replaced SDL/OS movement repeat with held-key state and paced simulation input so slow frames cannot queue catch-up movement after key release; added scroll-reuse terrain rendering and absolute-cell resource overlay caching. Added deterministic 512×512 regional block plans, causally scored settlement anchors, exact directional region entry, symmetric road exits, authoritative prepared river exits, and a discovery-gated graphical region map. Regional plans persist as rebuildable generated data while simulation/economy authority remains unchanged.

- RC14 dev4: added deterministic environmental read models and per-resource opportunity scores, bounded fingerprint-keyed caching, skill-gated Look ground signs, and a three-seed map audit. Preserved continental/climate fields, physical hydrology and resource density. Fixed in-memory hydrology plans failing to persist on a later save request; centered the graphical camera at every zoom; wrapped footer controls inside small windows. Added behavioral SDL startup/zoom/render checks and environmental determinism/persistence tests.

- RC14 dev3: fixed stale/held pygame startup key-repeat so new games no longer open directly into PAUSED; promoted new worlds to worldgen v5; added seam-safe multi-domain hydrology preparation, physical shallow/deep rivers, contiguous lake basins, wetlands, floodplains, crossing-cost/water-access/flood-risk read values, deterministic ford candidates, startup watershed preparation, v5 spawn repair, Phase-3 geography audit tooling and resource compatibility for new wet terrains. Legacy v1-v4 geography remains frozen.

- RC14 dev1: froze RC13 v4 golden terrain fingerprints; added hydrology/settlement-plan/route version contracts; added stable regional physical-plan dataclasses/IDs; added SQLite generated hydrology/regional/settlement/route caches and authoritative physical-plan deltas; added deterministic Priority-Flood-style hydrology prototype, basin/flow/accumulation/river/floodplain fields, persistence, audits, debug PNG/CSV exports, benchmark and regression tests. Live geography remains v4 until Phase 3.

- RC13: added startup seed-world preparation, persistent generated terrain/resource chunk caches, a pygame world-generation progress screen, larger bounded chunk caches, fast load-time neighborhood warming, scratch-cache release after preparation, and pregeneration benchmarks/tests.

- RC12: moved mouse hover to a renderer-side partial-damage fast path; added incremental terrain/discovery and resource-view caches; changed the graphical overlay pass to visit only occupied cells; disabled full-window alpha scanlines by default; added per-discovery LOS occlusion caching and renderer regression tests.

- RC11: immediate mouse-hover redraw in the pygame client, viewport-local render lookups, cached terrain base layer redraws, and a first-pass overhaul of 10 individual item sprites (stone, wood, brush, fiber, berries, stone flake, plant cordage, stone knife, stone axe, wooden spear).

## 1.0.0-rc6 — Sandbox Character & Exploration
- Replaced preset new-character origins with attribute/skill/talent point-buy and equal-budget random generation.
- Removed automatic starting leads/objectives.
- Fixed held-arrow → ESC behavior on Windows by separating native and VT input paths.
- Cached natural resources and made tile discovery incremental to remove movement lag.
- Added stable camera dead-zone.
- Tightened settlement, route, wildlife and record knowledge gating.
- Reworked multi-target gathering into adjacent map targeting.
- Added player price bargaining, medical skill treatment and survival exposure effects.
- Simplified player-facing item and world information.
- Added RC6 regression and movement benchmark coverage.


## 1.0.0-rc5 — Gameplay & Discovery

- Added proper Continue/New/Load/Help/Quit main menu and pause/save-return flow.
- Added save summaries and origin-aware new-character setup/spawn scoring.
- Added player-knowledge discovery state for NPC identities, settlements, factions, sites and historical events.
- Added line-of-sight exploration and rumor/conversation-based information discovery.
- Split surface biome ground from deterministic harvestable feature overlays.
- Added clustered tree stands, physical mature vegetation/boulders, and stump/sapling/mature regrowth.
- Added adjacent-target gathering/mining so impassable cave walls/ore can be worked correctly.
- Added worldgen v3 reciprocal natural cave columns and protected landing chambers for new worlds.
- Preserved legacy v2 worldgen behavior for existing saves.
- Added persistent player-excavated vertical shafts with support timber and aquifer interaction.
- Added Windows Quick Edit/mouse suppression plus mouse/paste input-token filtering.
- Added upgrade guards so RC4 characters/buildings cannot be trapped by newly introduced natural features.
- Added RC5-specific discovery/resource/cave/startup compatibility regression tests.

## 1.0.0-rc4 — Input Normalization & WASD Menus

- Fixed physical Escape on Windows: `msvcrt.getwch()` returns `\x1b`, which is now normalized to the canonical `ESC` token before UI dispatch.
- Added defensive widget-level Escape normalization for alternate/fake terminal adapters.
- Menus now support `W/S` for previous/next, `A` for Back, and `D`/Enter for Select/Forward.
- Pagers use `W/S` for scrolling, `A`/Esc for Back, and `D`/PageDown for forward paging.
- Updated in-game help and UI documentation to teach the same navigation model everywhere.
- Added literal-Windows-ESC and WASD-only nested-flow regression tests.

## 1.0.0-rc3 — Navigation Stack

- Added retained `NavigationStack` / `RouteState` UI architecture.
- Fixed ESC so one press pops one UI layer instead of jumping to a root or gameplay unexpectedly.
- Preserved menu selection and pager scroll across child screens.
- Refactored World Console, World Ledger, settings, action hub, inventory and storage onto stack semantics.
- Refactored crafting, component selection, building, equipment/health, magic and market cancellation paths to return to their immediate parent.
- Added breadcrumbs and explicit `Esc back` copy.
- Added simulated-key navigation regression tests.


## 1.0.0-rc2 — Interface Overhaul

- Rebuilt terminal presentation around strict responsive layout modes.
- Fixed stale-screen/modal overlap by clearing unused alternate-screen content after every presentation.
- Added arrow/Enter menus with paging, Home/End, Esc/Q back and optional numeric quick selection.
- Reorganized the World Console into eight semantic categories instead of one long flat list.
- Added the Enter-driven Action Hub so core play no longer requires memorizing dozens of hotkeys.
- Centralized global key routing and permanently protected WASD from feature-key collisions.
- Added a navigable Inventory Hub with item details, storage, equipment and books.
- Routed legacy shortcut screens through the same responsive pager.
- Reduced HUD clutter by showing only severe alerts and actors genuinely near the player.
- Added terminal-size regression tests and UI observational tests.
- Added `UI_GUIDE.md` with architecture and future-agent rules.
- Save schema remains 3 and worldgen remains 2; RC1 worlds are compatible.

## 1.0.0-rc1 — Living World release candidate

- Fixed `D` movement shadowing; moved dismantle to `U` and reserved WASD structurally.
- Added formal simulation LOD tiers and unrealized-world boundary.
- Added offline event-boundary fast-forward and SAFE/FULL policies.
- Added hierarchical region/chunk/local routing and sparse trade networks.
- Added century-scale archival/pruning maintenance.
- Added robust World Console, World Ledger, alerts, pagers and UI settings.
- Added save schema 3 metadata boundary, rotating backups, recovery and cross-record validation.
- Added deterministic data-mod manifests/dependencies/content hashing.
- Expanded anatomy, armor, wounds, treatment and individual durable equipment.
- Expanded metallurgy and component-selected craft designs.
- Added storage capacity, soil nutrients/rotation/disease pressure and structural roofs.
- Added persistent interactive dungeon locks/traps/occupants/clearance state.
- Expanded labor/production, property/rent, migration/refugees and military supply.
- Added rulers, dynasties, succession, claims, graves/tombs and artifact provenance.
- Added libraries, languages, knowledge prerequisites, religious institutions and schisms.
- Expanded generated magic with constraints, rituals, contamination and myths.
- Added hybrid epidemiology, named infections, immunity, sanitation, medicine, quarantine and pathogen transport.

## 0.40 alpha

- Broad first living-world implementation across ecology, settlements, NPCs, trade, history, cultures, knowledge, magic, underground exploration and persistent character succession.

## 0.001

- Deterministic infinite terrain, chunk streaming, movement, basic gathering and SQLite persistence foundation.

## 1.0.0-rc8 — Hybrid Renderer Foundation
- Added pygame-ce custom window backend while preserving ANSI fallback.
- Local world now supports layered terrain/resource/structure/item/carcass/crop/creature/NPC sprites.
- Added complete data-driven visual registry and sprite coverage audit.
- Added 296 generated sprite PNGs, 4 variants per authored animal, 32 NPC variants, crop growth stages and sprite atlases.
- Renderer remains observational; simulation/save/worldgen contracts are unchanged.


## RC14 Embodied World Dev2
- Decluttered generated ground resources while preserving ecological pockets and pickup opportunities.
- Replaced dead-zone camera scrolling with player-centered local camera behavior.
- Added mouse-wheel local zoom; `+`/`-` and `0` remain available.
- Added RC14 world-presentation regression tests.

## RC14 Dev7 - local terrain integration and readability
- Added eight-direction local terrain autotiling with discovery-safe neighbor blending.
- Integrated generated high-detail surface terrain textures into gameplay rendering.
- Improved resource and ground-loot differentiation and fixed transparent tint artifacts.
- Added project-relative source-art import tools and visual-readability tests.

## RC14 Dev13
- Reauthored all major water terrain families with smoother, less pixelated 128x128 tiles across ocean, river, freshwater, estuary, and generic water variants.
- Updated fallback base water textures (`water_hd.png`, `river_hd.png`, `river_shallow_hd.png`) to match the smoother art direction.
- Reauthored `nettles.png` and `resources/nettle_patch.png` to remove stray dark line artifacts and improve readability.

## RC14 Dev14
- Fixed gameplay Q/Q crash-like termination: Q was incorrectly routed to the same immediate quit path as the OS window-close event.
- Pygame window close now emits a dedicated `QUIT` token; ordinary Q/q is inert in gameplay.
- Quit remains available through Esc -> Pause -> Save & quit, preserving safe save behavior.

---

## Source: `RC10_TRAVERSABLE_WORLD_REPORT.md`

# WORLDSEED v1.0 RC10 — Traversable World Completion Report

## Problem addressed

The RC9 graphical map made a long-standing generation flaw obvious: several tree/boulder definitions independently rolled high placement probabilities over the same biome. Their collision probabilities compounded, producing rows and carpets of blockers that made ordinary grassland and forest difficult to traverse. Pygame key repeat also allowed stale movement events to accumulate, and RC9 mapped mouse buttons to Enter/Escape, causing accidental menu actions.

## Generation architecture

RC10 introduces **worldgen v4** and **resourcegen v3**.

1. Broad deterministic elevation, moisture and temperature fields establish coherent environmental regions.
2. Terrain/biome classification is derived from those fields.
3. Natural resources remain a separate deterministic overlay.
4. Each biome receives a total ground-resource and structural-blocker budget.
5. Habitat-eligible definitions compete for the budget instead of independently rolling full placement chances.
6. Structural candidates use deterministic minimum-spacing thinning; cardinally adjacent blockers cannot both survive.
7. Cave mouths and narrow terrain necks reject optional blockers.
8. Spawn selection validates connected walkable area and primitive-resource/timber opportunity.

This preserves the core WORLDSEED rule that terrain is deterministic potential and only player/world deltas are persisted.

## Compatibility

- Engine: `1.0.0-rc10`
- Save schema: `3` (unchanged)
- New-world terrain generator: `4`
- New-world natural-resource generator: `3`
- Existing saves keep their recorded terrain generator, preventing coastline/biome drift.
- Saves without a recorded natural-resource generator (including RC9-era saves) migrate to resourcegen v3.

## Input and movement performance

- Left/right mouse buttons no longer synthesize Enter/Escape.
- Hover inspection and wheel zoom remain presentation-only.
- Duplicate repeated movement KEYDOWN events are coalesced.
- Scanline/fluid overlay surfaces are cached.
- Settlement/institution/economy realization runs when the 512-tile coarse region changes rather than after every step.
- Ecology materialization runs on a 256-tile spatial boundary; dungeon activation runs on chunk/z boundaries.

## Final validation

- Python compilation: PASS
- Automated tests: **169 PASS**
- Content audit: PASS (`105 items`, `52 recipes`, `23 structures`, `8 crops`, `22 resources`, `17 authored species`, `4 cooking methods`)
- Visual audit: PASS (`32 NPC variants`; complete current visual coverage)
- Traversability audit: 10/10 PASS, radius 25
  - minimum resource-induced connectivity: **99.9574%**
  - median resource-induced connectivity: **100%**
  - minimum walkable-ground retention: **90.3114%**
  - maximum blocker occupancy: **9.6886%**
  - cardinally adjacent blocker pairs: **0**
- Early-game balance: 20/20 starts PASS, 0 weak starts, all empty
- Zero-item bootstrap: 10/10 PASS through fire, timber, carcass work, cooking and diet history
- Replay deterministic hash: `0749845df344a785c256e7558af6c2e6662ecd17`
- Worldgen benchmark: **17.80 ms / 32×32 chunk** (100 chunks)
- Movement benchmark: **0.657 ms / step**, **3.505 ms / step + render** (400 steps)
- 25-year FULL soak: 3/3 worlds, zero invariant errors
- 100-year FULL soak: 1/1 world, zero invariant errors, ~1.95 MB state

## Research basis

The implementation is original to WORLDSEED, informed by three established procedural-generation ideas:

- multi-scale elevation/moisture fields for coherent biome regions: https://www.redblobgames.com/maps/terrain-from-noise/
- minimum-distance/blue-noise placement for natural-looking separated samples: https://www.cs.ubc.ca/~rbridson/docs/bridson-siggraph07-poissondisk.pdf
- explicit flood-fill/reachability validation for generated traversable spaces: https://chizaruu.github.io/roguebasin/cellular_automata_method_for_generating_random_cave-like_levels

## Next milestone

RC11 should return to the art pipeline: terrain autotiling/ecotones, higher-detail replacement sprites, equipment layers and directional NPC/animal presentation. Worldgen/resource-placement density should now be treated as guarded infrastructure and changed only alongside traversability + bootstrap audits.

---

## Source: `RC11_ITEM_ASSET_AND_PERFORMANCE_REPORT.md`

# RC11 Item Asset and Performance Report

## Summary

This RC11 pass tackled three things the latest feedback called out:

1. individual item art quality
2. delayed tile-hover inspection updates
3. lingering pygame window lag

## Item art pass

Because the image pipeline available in-chat can only emit ten finished images per batch, this release focuses on the first curated item-art wave rather than all 105 items at once. The following item sprite files were replaced with better standalone assets:

- `worldseed/assets/sprites/items/stone.png`
- `worldseed/assets/sprites/items/wood.png`
- `worldseed/assets/sprites/items/brush.png`
- `worldseed/assets/sprites/items/fiber.png`
- `worldseed/assets/sprites/items/berries.png`
- `worldseed/assets/sprites/items/stone_flake.png`
- `worldseed/assets/sprites/items/plant_cordage.png`
- `worldseed/assets/sprites/items/stone_knife.png`
- `worldseed/assets/sprites/items/stone_axe.png`
- `worldseed/assets/sprites/items/wooden_spear.png`

All ten are standalone transparent PNG sprites; no sheet-only authoring was introduced. Atlases were rebuilt only as a packaging convenience for existing tooling.

## Hover-box delay fix

The pygame backend previously absorbed `MOUSEMOTION` events without requesting a redraw, so the hover box often updated only after the next keyboard/gameplay event. RC11 changes that behavior so mouse movement now returns an internal hover event immediately and the current frame redraws right away.

## Optimization work

### Render-side improvements

- Added a cached terrain/discovery base layer in `worldseed/ui/pygame_terminal.py` so repeated redraws do not repaint every static tile from scratch.
- Reduced per-frame indexing cost by building object lookup tables only for the visible viewport, instead of every global object in the simulation state.
- Reused resolved NPC/species special sprite collections within the frame instead of repeatedly re-fetching them in the inner tile loop.
- Cleared the terrain cache on resize/zoom changes to keep the cache coherent.
- Limited the base-layer cache size to prevent unbounded growth.

### Input-side improvement

- Hover motion is now coalesced by draining queued `MOUSEMOTION` events and using only the newest position, which prevents stale box movement when the mouse is moved quickly.

## Validation

Commands run:

```bash
python -m compileall worldseed
PYTHONPATH=. python tools/audit_visuals.py
PYTHONPATH=. python tools/build_sprite_atlases.py
PYTHONPATH=. python tools/bench_movement.py
```

Observed movement benchmark after the RC11 changes:

- `move_ms`: `0.639`
- `move_plus_render_ms`: `3.54`

## Next recommended pass

Continue the individual item-art overhaul in batches, prioritizing the rest of the primitive survival loop, then common food/resources, then crafted gear.

---

## Source: `RC12_RESPONSIVE_RENDERER_REPORT.md`

# RC12 Responsive Renderer Report

## Problem reproduced in code

RC11 still routed every mouse-tile change back through `run_game()`. That made a hover update pay for a complete `present_game()` even though simulation state had not changed. On a busy viewport this meant rebuilding/rendering terrain, natural resources, object dictionaries, sidebar text and the whole display simply to move the inspection box.

## Hover architecture fix

RC12 keeps hover entirely inside `PygameTerminal.read_key()`. Mouse-motion events are coalesced to the newest pointer position. When the pointer crosses into a different map tile, the backend:

1. restores only the old tooltip/highlight damage rectangle from a clean map snapshot;
2. looks up information for the new tile;
3. draws a one-tile highlight and tooltip;
4. calls `pygame.display.update()` only for the union of the old/new damaged rectangles;
5. continues waiting for actual gameplay input without returning to the application/simulation loop.

Movement inside the same tile produces no redraw at all. Menus explicitly clear the gameplay hover snapshot so stale map pixels cannot be repainted over menu screens.

## Renderer optimizations

- Terrain/discovery cache is keyed by viewport + world revision and patches only cells newly discovered since the prior frame.
- Natural-resource cache is keyed by viewport + resource revision/day and patches only newly visible cells. Harvesting/regrowth invalidates the cache through a resource revision counter.
- Terrain edits invalidate through a monotonic world revision counter rather than `dirty_tiles` length.
- Main sprite pass builds a union of occupied overlay cells and renders those in y/x order; empty viewport cells are no longer visited by the dynamic overlay loop.
- NPC/species path pools and known-NPC IDs are resolved once per frame.
- Nearby sidebar entries reuse viewport-local entity dictionaries.
- Full-window alpha scanline blending is disabled by default because it added a large blended surface operation every frame without gameplay value.

## Simulation-side optimization

Discovery LOS was the dominant movement cost in profiling. `_discover()` now creates a per-pass occlusion cache shared across Bresenham rays. Repeated rays reuse whether intermediate cells block sight instead of repeating terrain, natural-resource and building queries.

Built-in 400-step benchmark:

- RC11 documented movement: ~0.639 ms/step
- RC12 movement: ~0.351 ms/step
- RC11 documented movement + terminal render: ~3.54 ms/step
- RC12 movement + terminal render: ~3.125 ms/step

The container does not include pygame-ce and has no package-network access, so a reliable pygame FPS benchmark cannot be executed here. The pygame fast path is covered structurally by RC12 regression tests, while existing visual, worldgen, system, persistence and replay suites remain passing.

## Compatibility

- Save schema: unchanged (`3`)
- Worldgen: unchanged (`4`)
- Natural-resource generation: unchanged (`3`)
- Existing RC10/RC11 saves remain compatible.

---

## Source: `RC13_SEEDED_WORLD_PREPARATION_REPORT.md`

# RC13 Seeded World Preparation Report

## Goal

Move expensive first-contact terrain/resource generation out of moment-to-moment movement and into an explicit seeded-world loading phase.

## Research conclusion

Open-world chunk pre-generation is a proven way to exchange startup time and disk space for smoother exploration. Chunky, a widely used Minecraft pre-generator, specifically recommends preparing chunks before players enter so generation does not affect gameplay, while also warning that preparation cost grows rapidly with radius. Modern chunk systems still retain streaming/caching because an actually infinite procedural world cannot be fully materialized. WORLDSEED therefore uses a hybrid: prepare the likely opening exploration envelope, persist it, and keep deterministic expansion beyond it.

## Implementation

### Persistent prepared terrain

SQLite now contains a `generated_chunks` table keyed by chunk coordinate, z-level and world-generator version. Each prepared chunk stores a compressed array of terrain content IDs rather than registry indexes, so content ordering cannot silently reinterpret an old prepared chunk. If an ID no longer exists, runtime falls back to deterministic generation. Player terrain changes remain in `tile_deltas` and are applied after the prepared base chunk loads.

### Persistent prepared natural resources

`generated_resource_chunks` stores compressed current-season base placement keyed by chunk, resource-generator version and season. Harvesting/depletion/regrowth are not baked into this data; they remain living simulation overlays. Structures/crops/soil continue to suppress underlying natural features at read time.

### New-game preparation envelope

Default: radius 8 chunks around the selected spawn = 17×17 = 289 surface chunks = 544×544 cells.

Loading phases:

1. read content and seed rules
2. select a viable starting region
3. shape/persist terrain chunks
4. place/persist current-season natural resources
5. realize nearby ecology/settlements/living-world systems
6. enter gameplay

### Existing saves

Existing saves warm a 5×5 chunk neighborhood around the player while the normal load screen is visible. Missing prepared data can be generated there rather than during the first movement after loading.

### Memory discipline

- terrain LRU raised to 384 chunks, enough to retain the 289-chunk opening envelope plus working margin
- resource prepared-chunk LRU capped at 384 chunks
- large interpolation/candidate scratch dictionaries are cleared after preparation
- deterministic prepared data lives in SQLite, so cache eviction does not lose generation work

## Benchmarks

`PYTHONPATH=. python tools/bench_pregeneration.py` on the validation environment produced approximately:

- cold first terrain tile in a new chunk: 20.350 ms
- prepared first terrain tile: 0.303 ms
- cold 1,024-cell resource chunk lookup: 77.595 ms
- prepared 1,024-cell resource chunk lookup: 3.454 ms

The exact numbers vary by CPU, but the architectural change removes generator work from the movement path inside the prepared envelope.

A full radius-8 new-world preparation on the validation environment took roughly 20–25 seconds and produced only a few hundred KB of prepared chunk data in SQLite. Subsequent loading around the same spawn was effectively immediate because it read prepared data instead of recomputing it.

## Compatibility

- save schema remains 3; the cache tables are additive
- worldgen remains version 4
- resourcegen remains version 3
- existing worlds remain loadable
- WORLDSEED remains unbounded and deterministic outside the prepared region

## Validation

RC13 adds tests proving that prepared terrain reloads without calling the procedural generator, prepared resource chunks reload without raw placement work, and the graphical loading-screen/progeneration contract is present.

---

## Source: `RC7_COMPLETION_REPORT.md`

# WORLDSEED v1.0 RC7 Completion Report

## Release theme

**Empty Hands** - early-game survival, crafting, hunting, food, farming and useful infrastructure.

## Completed

- Hard zero-supply character start.
- Fair-but-undisclosed spawn opportunity scoring.
- Primitive stone/fiber/branch tool chain without circular dependencies.
- Data-driven tool qualities.
- Expanded item descriptions/flavor/stats.
- Expanded natural resources/forage with climate/season/habitat rules.
- Expanded authored fauna with attacks, habitat, mass and carcass profiles.
- Persistent carcasses with staged field processing and decay.
- Timed drying/tanning/preservation jobs.
- Dynamic ingredient-composed cooking.
- Seven-day nutrition/diet history and food effects in Health UI.
- Eight data-driven crops with N/P/K and disease-family differences.
- Mechanically useful primitive furniture and workstations.
- Environmental shelter/warmth/rest/work bonuses.
- Ranged primitive hunting path.
- Categorized crafting/construction UI with readiness/missing requirements.
- Automated anti-clutter content audit.
- Automated start-balance audit.
- Automated end-to-end zero-item bootstrap smoke test.
- Serialization coverage for carcasses/jobs/meals/diet.

## Validation

- 156 automated tests: all passed.
- RC7 bootstrap: 10/10 independent seeds passed.
- Start balance: 20/20 empty, bootstrap-capable starts; 0 weak starts.
- Content audit: passed (105 items, 52 recipes, 23 structures, 8 crops, 22 resources, 17 authored species, 4 cooking methods).
- Deterministic replay hash after RC7 generation boundary: `f65ea5583575a883f45195a78c6f86d7c5ed64dc` (final packaged run must match or be documented if archive metadata changes it).
- Worldgen benchmark: ~15.11 ms/chunk.
- Movement benchmark: ~1.62 ms/step; ~3.97 ms with full render.
- 3x 25-year soak: zero invariant errors.
- 1x 100-year soak: zero invariant errors; ~1.96 MB state.

## Remaining after RC7

RC7 completes the requested opening-system overhaul, but WORLDSEED remains an evolving sandbox. High-value future depth:

1. trapping, fishing and tracking/sign systems;
2. deeper butchery cuts, cooking vessels, smoking/salting/fermentation and cold storage;
3. livestock/domestication/breeding;
4. advanced textiles, weaving and clothing construction;
5. more detailed shelter microclimate and fuel smoke/ventilation;
6. broader seasonal phenology and plant propagation;
7. recipe discovery/proficiency rather than universal recipe knowledge;
8. animal territorial/social behavior and nesting/denning;
9. agriculture pests, composting, manure and irrigation networks;
10. balance telemetry from actual play sessions;
11. accessibility/keybinding customization and searchable craft/build menus;
12. deeper aesthetic/comfort/prestige systems so decorative furniture has systemic value.

These are post-RC7 expansions, not unfinished requirements of the user's current early-game task.

---

## Source: `RC8_VISUAL_COMPLETION_REPORT.md`

# WORLDSEED v1.0 RC8 — Visual Foundation Completion Report

## Completed

- Selected pygame-ce as the primary custom-window renderer.
- Added a resizable WORLDSEED game window independent of the OS terminal.
- Preserved the ANSI terminal backend with `--terminal`.
- Added hybrid local-world rendering using sprite layers while keeping dense menus text-first.
- Added deterministic visual manifest and runtime resolver.
- Generated sprite coverage for every current item, terrain, natural resource, structure/furniture asset and crop.
- Generated four variants for each of 17 authored animal species.
- Generated 32 NPC appearance variants.
- Added crop growth-stage sprites.
- Added category atlases and atlas metadata for future batching.
- Added visual coverage/audit tooling and automated tests.
- Added Windows launcher dependency bootstrap and legacy-terminal launcher.
- Kept save schema, worldgen and simulation determinism unchanged.

## Asset counts

- 105 item sprites
- 19 terrain tiles
- 22 natural resource sprites
- 23 structure/furniture sprites
- 24 crop stage sprites (8 crops x 3 stages)
- 68 authored animal sprites (17 species x 4 variants)
- 32 NPC variants
- special player/cursor/fog assets

There are 304 individual sprite PNGs before atlas/preview files.

## Validation

All 163 automated tests passed module-by-module after the renderer transition, including RC8 visual coverage tests. `tools/audit_visuals.py` passes with complete registry coverage.

## Deliberately deferred

The renderer transition has started but is not considered the final graphical form. The next visual milestone should focus on animation, tooltip/hit-test interaction, equipment overlays, terrain autotiling, lighting/weather effects and modular visuals for procedural species.

---

## Source: `RC9_VISUAL_INTERACTION_REPORT.md`

# WORLDSEED v1.0 RC9 — Visual Interaction Pass

## Purpose

RC9 continues the RC8 renderer transition without touching simulation authority, save format, world generation or deterministic RNG.

## Added

- presentation-only zoom presets through `+`, `-`, and `0`;
- sprite-cache invalidation when zoom changes;
- mouse hover hit-testing over the local map;
- contextual hover tooltips for terrain, resources, crops, structures, items, animals and known/unknown NPCs;
- unexplored-cell tooltip behavior that does not reveal hidden state;
- updated control strip documenting zoom controls.

## Invariants

- Hovering does not advance time.
- Hovering does not realize undiscovered regions.
- Hovering does not roll RNG.
- Zooming changes only presentation scale.
- ANSI terminal fallback remains intact.

## Next visual milestone

The next pass should replace the deterministic placeholder art with the detailed WORLDSEED art direction while preserving stable visual IDs and the manifest. That allows every sprite to be upgraded independently without changing gameplay data or saves.

---

## Source: `RELEASE_NOTES.md`

# Release Notes

## RC14 Development 16 — Terrain Meshing, Geological Caves & Discovery Crafting

Dev16 makes local terrain presentation data-driven instead of maintaining a growing list of hand-authored terrain-pair exceptions. The renderer now builds its blend catalog from terrain tags, allowing grassland and floodplain to feather together naturally and giving future/modded ground terrain the same transition system automatically. Hard topology/content features such as shafts, ore veins and loot remain intentionally crisp. Cave-mouth art is now a transparent contextual overlay, so the same entrance can sit naturally on grass, floodplain, sand, rock or other ground without bringing a square baked background with it.

New worlds use **WORLDGEN_VERSION 7**. v7 preserves Dev15's v6 ocean/river geography but replaces the old natural-cave column placement with terrain-aware entrance planning. Entrances prefer exposed relief and uplands, persist deterministic connector depths, open protected landing chambers and feed into vertically correlated cave fields rather than unrelated noise sheets at each z level. Underground geology is split into shallow caverns, sedimentary caves, deep fracture caves and deep crystalline caves. Coal and aquifers favor shallower layers, copper clusters at mid-depth, and iron becomes progressively more important deeper underground. Existing v1-v6 saves retain their recorded cave geography.

Crafting now has an opt-in persisted discovery model enabled for new worlds. Merely carrying/handling a new material type records it as discovered. Simple one-material techniques can reveal themselves immediately; recipes requiring combinations of discovered components become experiments that consume time but not output materials, and successfully testing one records the recipe permanently. The crafting screen exposes Discovered Recipes, Experiment, Materials, Tech Tree and Component Designs. The tree is derived from actual recipe input/output relationships, so crafted components naturally open later branches instead of relying on a second hand-maintained technology graph.

The pygame UI also gains a native graphical menu/document layer. Inventory, crafting and the rest of the retained menu system render as card panels rather than raw ASCII inside the window, with dedicated inventory/crafting tab bars, state badges and preserved W/S/D/A + arrow/Enter/Escape parity. The renderer remains observational: opening or browsing these panels cannot unlock recipes, advance time or mutate inventory.

See `RC14_DEV16_HANDOFF.md`, `DEV16_VALIDATION.md`, `artifacts/dev16-terrain-meshing-audit.txt`, `artifacts/dev16-cave-audit.txt`, and `artifacts/dev16-cave-mouth-variants.png`.

## RC14 Development 5 — Regional World Blocks & Responsive Movement

Dev5 changes WORLDSEED's strategic geography from isolated macro checks into deterministic **512×512 explorable regional blocks**. Each block carries a lightweight generated plan for broad biome character, relief, settlement siting, wilderness character, symmetric road exits, and prepared authoritative water connections. Settlement presence still follows the existing simulation contract, but its anchor is now selected from deterministic environmental candidates instead of an unrelated random coordinate. Settlement regions retain a 64-tile rural margin so villages and towns remain embedded in countryside rather than filling an entire block.

The graphical `M` map reads these plans through player discovery only. It shows broad terrain, known settlements, connected roads/trails and prepared rivers without exposing hidden bandit/site/wildlife potential. Road and water exits use stable edge offsets, so neighboring blocks meet at the same visual boundary point. Continuous world coordinates provide directional entry naturally: crossing south enters the next block from its north side, crossing east enters from its west side, and so on.

Movement input was rebuilt around explicit key-down/key-up state. pygame key repeat is disabled; WORLDSEED emits at most one paced held-movement intent per interval and never catches up missed repeats after a slow frame. The terrain renderer can scroll/reuse the previous one-tile viewport and redraw only exposed strips, while natural-resource projection is cached by absolute cell. These changes target the held-key overshoot/lag reported in Dev4.

This checkpoint does **not** claim full RC14 route or settlement physicalization. Regional road exits are strategic connections; terrain-aware local road corridors, bridges/fords, parcels, structure footprints and persistent settlement skeletons remain the next physicalization work. See `RC14_DEV5_HANDOFF.md`.

## RC14 Development 4 — Environmental Geography

Phase 4 adds slope, relief, natural fertility, wetness, drainage, flood risk, farmland potential, and forage/timber/stone/freshwater opportunity. Look mode explains local ground conditions once survival or naturalism reaches 4. These are natural site read models for Phase 5 planning; they do not duplicate mutable soil state, spawn extra items, or place settlements.

The camera now stays centered across zoom levels, footer hints fit the 800×520 window, and hydrology plans already in memory correctly honor later persistence requests. Startup Escape suppression and the reduced loose-item density remain in place.

Extract the archive into its own folder and use the existing launchers. Existing saves use their recorded worldgen version. See `RC14_DEV4_HANDOFF.md` and `artifacts/phase4/` for the contracts, audit maps, and validation record.

## RC14 Development 3 — Worldgen v5 Physical Geography

RC14 Phase 3 now makes hydrology physically authoritative for **new** worlds. `WORLDGEN_VERSION = 5` projects the prepared drainage plan into shallow/deep rivers, deterministic fords, contiguous lake basins, wetlands and floodplains, while exposing crossing cost, depth, water access and flood-risk read values for the settlement and route systems that follow. Legacy v1-v4 saves continue using their recorded geography and are never retroactively cut by RC14 rivers.

The Dev2 seam blocker is resolved inside prepared regions by solving every needed hydrology domain in one larger Priority-Flood lattice and slicing the common result into per-domain cache records. Startup resolves this watershed plan before terrain/resource pregeneration. A Phase-3 audit over four prepared domains and 147,456 cells reports zero overlap seam issues; the ten-seed traversability audit remains green.

The graphical startup transition also now clears queued loading keys and temporarily disables key repeat until the first fresh gameplay press. This prevents a stale or physically held Escape from sending a newly started game directly into the PAUSED menu.

Dev2's decluttered ground resources, player-centered camera and local zoom controls remain included.

## RC14 Development 1 — Embodied World Foundation

This development checkpoint begins the RC14 architecture without claiming the final Embodied World release. RC13 worldgen v4 remains the live geography contract while a deterministic hydrology layer is developed and audited separately. New independent version contracts cover hydrology, settlement plans and route generation; SQLite now has rebuildable generated-cache tables for those plans plus a separate authoritative physical-plan delta table for mutations that must survive cache deletion.

The first hydrology prototype uses an aligned 16-cell lattice, 64×64 core-node domains with an 8-node halo, Priority-Flood-style depression handling, deterministic D8 drainage, climate-moisture runoff, accumulation, watershed IDs, river hierarchy and floodplain strength. `tools/audit_hydrology.py` exports CSV/PNG/JSON debug artifacts and `tools/bench_hydrology.py` measures generation/cache cost. The layer is observational only in this checkpoint: it does not alter terrain or movement. Worldgen v5 is intentionally deferred until Phase 3 can project hydrology into physical geography without violating seam and legacy-save rules.

## RC13 Seeded World Preparation

New games now prepare a 17×17 surface-chunk exploration envelope around the chosen spawn during a dedicated progress/loading screen. Generated terrain and current-season natural-resource placement are persisted in SQLite and retained in bounded runtime caches. This moves first-time chunk work out of ordinary movement for the area where a new character is most likely to spend the opening game.

WORLDSEED remains deterministically unbounded rather than imposing a hard world border. Beyond the prepared envelope, generation still falls back to the seed-driven chunk system. Existing saves warm a 5×5 neighborhood on load. Prepared generation scratch caches are cleared after the loading phase to keep memory bounded.

A new benchmark compares cold generation with prepared reads; on the release validation machine, a cold first terrain access was about 20.35 ms versus 0.303 ms prepared, while 1,024 resource lookups for a chunk were about 77.60 ms cold versus 3.45 ms prepared.

## RC12 Responsive Renderer

RC12 replaces the RC11 hover implementation with a true renderer-side fast path. `MOUSEMOTION` is coalesced and handled inside the pygame backend; crossing into a new tile restores only the previous tooltip/highlight rectangles from a clean map snapshot and redraws only the new tile highlight + tooltip. Mouse movement therefore no longer forces terrain generation, resource queries, entity indexing, sidebar drawing, simulation dispatch, or a full-window flip.

The main game frame is also lighter. Terrain/discovery surfaces patch only newly discovered frontier cells, natural-resource overlays patch only newly revealed cells until a real resource revision/regrowth invalidates them, and the overlay pass visits only occupied cells rather than every tile in the viewport. Full-window alpha scanlines are disabled by default. Discovery line-of-sight shares an occlusion cache within each visibility pass, reducing repeated terrain/resource sight checks.

Save schema, worldgen version, and resourcegen version are unchanged from RC10/RC11.

Benchmark on the built-in 400-step movement workload after these changes: ~0.351 ms simulation movement and ~3.125 ms movement + terminal renderer, compared with RC11's documented ~0.639 ms / ~3.54 ms. pygame-specific frame timing must be measured on a machine with pygame-ce installed, but the expensive hover path is structurally removed.

## RC11 Item Polish & Hover Fix

RC11 focuses on responsiveness and asset quality. The pygame client now triggers an immediate redraw when the mouse moves so hover inspection updates in real time instead of waiting for the next gameplay key. Rendering also avoids rebuilding large off-screen/global lookup tables each frame, and the terrain/discovery base layer is cached so repeated redraws (especially hover refreshes) are cheaper.

This build also starts a curated individual item-sprite overhaul. The first batch replaces ten core items with higher-detail standalone sprites: stone, wood log, brush, cordage fiber, berries, stone flake, plant cordage, stone knife, stone axe, and wooden spear.

## RC10 Traversable World



RC10 fixes the terrain/resource-density problem exposed by the graphical renderer. New worlds use worldgen v4 with broad climate fields and natural-resource generation v3 with biome budgets plus deterministic spacing. Trees and boulders remain meaningful physical objects, but optional blockers can no longer pack into orthogonal walls or consume cave mouths and narrow terrain necks. Spawn selection now checks connected walkable space as well as primitive progression opportunities.

The pygame input path no longer turns left/right clicks into Enter/Escape. Movement repeat events are coalesced, scanline/fluid overlays are cached, and coarse settlement/ecology refresh work is boundary-triggered instead of repeated after every tile step.

Compatibility: save schema remains 3. Existing worlds keep their recorded terrain generator. Pre-versioned RC9 resource layers adopt the v3 safer placement protocol.

Release validation: 169 automated tests passed; content and visual audits passed; 10-seed traversability audit reached 99.957% minimum resource connectivity with 0 adjacent blocker pairs; 20/20 early-game starts passed; 10/10 zero-item bootstraps passed; 25-year FULL soak 3/3 and 100-year FULL soak 1/1 completed with zero invariant errors. Current benchmark: ~17.80 ms/chunk and ~0.657 ms/movement step (~3.505 ms with render).

## RC7 Empty Hands

RC7 is the early-game depth release. It changes the opening from "already equipped survivor" to a true zero-supply sandbox and extends primitive crafting, ecology, hunting, carcass work, cooking, nutrition, preservation, farming and useful furniture.

## Headline changes

### Start with nothing

New characters receive no items of any kind. Spawn selection only ensures the surrounding landscape contains a fair *possibility* of primitive progression; it does not reveal resources or grant a kit.

### Primitive progression

Loose stone, branches, brush/fiber and bark support flakes, cordage, knives, axes, picks, hammers, digging/tilling tools and primitive ranged/melee weapons. Circular early dependencies were removed.

### Hunting is a process

Kills leave persistent carcasses. Skin, butcher and debone separately. Carcass quality is affected by damage and age. Skinning first protects hide value. Timed drying/tanning turns fresh products into durable materials.

### Dynamic meals and diet

Roast, stew, porridge and broth build meals from selected ingredients. Nutrition is calculated from the ingredients and stored with the meal. The Health pane now includes seven-day macros/diet-group history and active food effects.

### More ecology and agriculture

Forage and natural resources are climate/terrain/season aware. Authored fauna have habitat, attacks and carcass profiles. Farming includes eight crops with distinct N/P/K demands, water/temperature envelopes and disease families.

### Furniture has a job

Primitive and advanced furniture declare real functions: shelter, warmth, rest, storage, work speed, processing stations, structural support, cooking, metallurgy, etc. Decorative-only objects are deferred until aesthetics/prestige can consume them.

### Anti-clutter content validation

`tools/audit_content.py` checks descriptions/flavor, references, functional furniture and item sinks. RC7 content: 105 items, 52 recipes, 23 structures, 8 crops, 22 natural resource types, 17 authored species and 4 dynamic cooking methods.

## Final engineering gates

- 156 automated tests passed.
- 10/10 independent zero-item bootstrap seeds passed.
- 20/20 sampled starts were empty and bootstrap-capable; 0 weak starts.
- Content audit passed.
- Deterministic replay hash: `f65ea5583575a883f45195a78c6f86d7c5ed64dc`.
- Worldgen ~15.11 ms per 32x32 chunk in the final release benchmark.
- Movement ~1.62 ms/step; ~3.97 ms including a full 100x30 render.
- Three 25-year FULL worlds completed with zero invariant failures.
- One 100-year FULL world completed with zero invariant failures and ~1.96 MB persistent state.

## Compatibility boundary

Engine version is `1.0.0-rc7`. Save schema remains 3. World terrain generation remains version 3. Natural-resource generation is now protocol/version 2 to make the expanded forage/resource layer explicitly reproducible.

## RC8 Visual Foundation
Normal play now prefers a dedicated pygame-ce WORLDSEED window. Menus retain the terminal-style information model, while the local map can render layered sprites. Use `RUN_WORLDSEED.bat` for the graphical window or `RUN_WORLDSEED_TERMINAL.bat` / `--terminal` for the original ANSI backend. See `VISUAL_ARCHITECTURE.md` and `SPRITE_STYLE_GUIDE.md`.


## RC9 Visual Interaction Pass

- Added presentation-only local-map zoom with `+`, `-`, and `0`.
- Added mouse hover hit-testing and contextual map tooltips.
- Kept undiscovered information hidden.
- Preserved simulation/render separation and ANSI fallback.
- Added regression checks for zoom and hover contracts.

---

# Validation and Test Records

---

## Source: `DEV15_VALIDATION.md`

# Dev15 validation

- Full unittest suite: 257 tests passed (416.920 seconds).
- Water/swimming and pygame focused suite: 21 passed.
- Current/rendering/UI regression suite: 37 passed.
- Final pygame checks after render caching and sidebar fit adjustments: 7 passed.
- Python compileall: passed.
- Golden replay completed successfully: d8efc89dfd69f808877c39788846d392b7ac27b0.
- Hydrology audit: 4,096 core nodes, 6,400 total nodes, zero issues; worldgen v6 / hydrology v1.
- Rendered actual generated coast and river scenes in headless pygame; checked idle animation changes pixels without changing simulation state and stops on console screens.
- Saved preview-world state passed the database verifier with zero issues.
- Warm coastal render benchmark improved from about 294 ms to 74 ms after caching prepared currents. Idle water redraw was about 2.5 ms. These are headless container timings, not Windows frame-rate guarantees.

The first full run found three outdated assertions (generator version, depth blending, and Dev14 window-close token) and a metallurgy fixture that placed its forge underwater. Assertions were aligned with the intended contracts and the workshop fixture was explicitly placed on dry ground. The full rerun passed.

The final renderer-only optimizations were also checked separately after the full suite started. Tests, rebuild scripts, source, terrain assets and handoff notes are included. Saves and platform-specific test dependencies are excluded from the release archive.

Start a new world to see v6 geography. Existing saves retain their original terrain.

---

## Source: `DEV16_VALIDATION.md`

# WORLDSEED RC14 Dev16 Validation

## Static/data checks

- `python -m compileall -q worldseed tools` — PASS
- visual registry/readability/terrain variant tests — PASS
- copper vein, ore, ingot and smelting process load through the content registry — PASS
- v7 cave-mouth assets retain alpha transparency and are referenced by `visuals.json` — PASS

## New Dev16 regression coverage

`tests/test_dev16_caves_crafting.py` verifies:

- future tagged ground terrain automatically joins the mesher while ore remains excluded
- deterministic terrain-aware v7 cave mouth + reciprocal shaft depth
- shallow/sedimentary/fracture/crystalline level metadata
- shallow coal/aquifer, mid-depth copper, deeper iron bias
- material discovery -> simple auto recipe -> compound experiment progression
- discovery-tree browsing is observational
- discovery state survives serialization round-trip
- copper has a mine-to-smelt content chain

`tests/test_local_terrain_transitions.py` now explicitly requires grass/floodplain blending and keeps authored hard features crisp.

## Deterministic audits

### Terrain meshing

Command:

`PYTHONPATH=. python tools/audit_terrain_meshing.py`

Result:

- 30 blendable terrain IDs
- 435 pair profiles validated
- grass <-> floodplain: blend
- PASS

### Caves/geology

Command:

`PYTHONPATH=. python tools/audit_caves_v7.py`

Frozen seed: `dev16-cave-audit`

Result:

- 27 natural entrances in an 11x11 cave-macro-cell window
- entrance connector depth range 3..10
- z -1: cave floor 6015, wall 2819, aquifer 290, coal 284
- z -3: cave floor 5839, wall 2893, coal 351, aquifer 248, copper 47, iron 30
- z -6: cave floor 4603, wall 4231, iron 382, aquifer 192
- z -10: cave wall 5635, floor 3346, iron 428; no coal/copper leakage
- PASS

## Regression cohorts run green

Affected/regression cohorts were run individually because the complete historical suite exceeds the sandbox's single-command timeout. Green cohorts include:

- local terrain transitions + Dev16 caves/crafting
- contextual water/world presentation/terrain variants/assets
- systems
- RC5 gameplay
- RC6 sandbox
- RC14 hydrology
- legacy v0.4.1 compatibility
- v6 water/swimming
- persistence + deterministic replay
- RC10 worldgen + RC13 pregeneration
- core worldgen
- inventory retained-navigation flow and crafting action-hub backtracking

No failing affected test remains in the packaged tree.

## Environment limitation

`pygame-ce` is a declared runtime dependency but is not installed in the execution sandbox, and network installation is unavailable. Therefore SDL-specific tests that require a real pygame import remain skipped/unavailable here. The graphical menu methods compile successfully and the shared widget/navigation layer was exercised through fake terminal adapters. A final live-window visual pass should be performed on the target Windows environment.

---

## Source: `DEV19_VALIDATION.md`

# Dev19 Validation

## Static / unit validation

- `python -m compileall -q worldseed` — PASS
- Feature presentation-hook tests — PASS
- Player appearance persistence/assets — PASS
- Asset readability — PASS
- RC14 world presentation source checks — PASS
- RC12 renderer source checks — PASS
- Inventory retained-navigation regression — PASS
- Dev16 cave/crafting discovery regressions — PASS

## UI contract checks

- Pygame feature UIs are presentation-only.
- ANSI terminal fallback remains functional through the same widgets.
- Recipe/material browsing does not mutate discovery state.
- Crafting actions still execute via simulation commands.
- Inventory mutations still execute via drop/eat/equip/store commands.
- No worldgen or save-schema version changed.

## Environment note

The workspace does not contain pygame-ce. An attempted installation could not reach PyPI because outbound package-network resolution is disabled. Therefore Dev19 was compile-validated and exercised through widget/navigation tests rather than a live SDL render in this environment.

---

## Source: `DEV20_VALIDATION.md`

# Dev20 validation

- Compile: PASS (`python -m compileall -q worldseed`).
- Targeted appearance, feature widgets, real SDL draws, navigation, cave/discovery suite: **37 passed** (237.87s). Log: artifacts/dev20_targeted_tests.txt.
- Startup/appearance + RC10 worldgen: **8 passed** (57.17s). Log: artifacts/dev20_startup_tests.txt.
- New-character no-guiding-leads regression: **1 passed** (7.26s).
- Additional startup follow-up: **2 passed, 1 failed**. The remaining RC7 zero-supply bootstrap harness harvests directly through `sim.resources.harvest` and attempts a locked recipe without the normal discovery command path. It reports “You have not discovered that recipe yet.” This is not a graphical crash and was not hidden by changing recipe-discovery rules.
- Real pygame-ce 2.5.8/SDL dummy video rendering reproduced the original keyword-only icon-scale TypeError before the fix. Post-fix actual draws passed for every affected crafting/inventory route. Simulation state and inventory are unchanged by these draws.
- 20 player assets checked for RGBA transparency, shared 160x256 canvas, unclipped bounds and loadability at multiple display sizes. Gallery and recipe screenshots visually reviewed.
- Deterministic replay: PASS; hash afdea05778f084b1e708795ad9020e470548f063.
- The initial broad unittest run began before the startup NameError was discovered and repaired. It completed 263 tests: 256 passed and seven startup NameErrors. After repair, six formerly failing cases passed; the seventh reached the separate bootstrap discovery assertion described above. Its failures and subsequent targeted results are retained separately; this release does not claim an entirely green broad suite.

No Windows desktop playthrough performed. Source atlas, import script, regression tests and screenshots are included.

---

## Source: `DEV21_VALIDATION.md`

# Dev21 validation

- Compile: PASS.
- Real SDL pointer tests: **10 passed** in 7.38s (artifacts/dev21_mouse_tests.txt).
- Navigation/shared widgets and updated control-contract regressions: **34 passed** in 137.96s (artifacts/dev21_navigation_tests.txt).
- Existing pygame behavior, crafting/inventory render and feature-hook regressions: **11 passed** in 18.72s (artifacts/dev21_renderer_tests.txt).
- Deterministic replay: PASS, afdea05778f084b1e708795ad9020e470548f063.
- Visual review: clickable HUD and crafting screenshot; all menu-card hit regions checked at 800x520 and 1600x900. Existing pygame suite checks centered observational world rendering at zoom limits and map hover isolation.

The broad unittest run completed 265 tests: 262 passed, with two failures and one error. It started before two old control assertions were updated: one demanded inert mouse buttons, the other used D to confirm the main menu. Both contradict the requested controls; their updated replacements passed in the focused navigation run. The remaining known RC7 bootstrap discovery failure (`test_zero_supply_bootstrap_reaches_food_and_fire`) reports that the stone-flake recipe has not been discovered. It remains separate from UI controls and is not fixed in this release. The entire broad suite was not rerun after updating the obsolete assertions.

SDL dummy-driver tests were run here; a Windows desktop playthrough was not performed.

---

## Source: `DEV22_VALIDATION.md`

# Dev22 validation

- Focused atlas + Dev21 pointer + legacy region helper suite: 22 passed.
- Pointer + terrain transitions + Dev16 cave/crafting regressions: 21 passed.
- Pregeneration, world generation and hydrology regressions: 18 passed.
- Python compilation passed.
- Exact terrain identity checked for every cell of a negative-coordinate chunk
  across three seeds and all seven generator versions (21,504 cell comparisons).
- Actual v7 prepared hydrology tested through loaded chunks, eviction, stored
  cache reload and comparison to local tile reads.
- Read-only assertions forbid chunk generation/cache loads and verify unchanged
  simulation state, database change count and LRU ordering.
- Real SDL dummy-backend tests cover 800x520, 1280x800 and 2560x1392, hit rectangles,
  zoom/pan, terrain inspection and hover not restoring the gameplay image.
- Golden replay: afdea05778f084b1e708795ad9020e470548f063 (unchanged).
- Full unittest discovery completed 282 tests in 431.819 seconds: 279 passed,
  three failed. Two failures exposed the live-catalog ruin-wall blending issue;
  the subsequent fix passed the 21-test focused regression run above (including
  both previously failing tests after renderer catalog configuration). The
  remaining pre-existing RC7 bootstrap failure is a stone-flake recipe-discovery
  assertion, unrelated to cartography. The full suite was not rerun after the
  fix; two additional atlas tests were included in the later focused run.

Screenshots were visually reviewed at 1280x800 and 800x520. POI positions in the
preview tool are QA fixtures, not a claim about settlements generated by that
seed. No native Windows desktop playthrough was performed.

---

## Source: `DEV23_VALIDATION.md`

# RC14 Dev23 — WORLDGEN v8 Phase-1 validation

Scope: non-authoritative geological landform prototype only.

- Added a standalone deterministic landform sampler with fixed namespaces and integer generation math.
- Prototype fields: continentalness, tectonic uplift, mountain-chain strength, basin strength, plateau strength, roughness, elevation and province.
- WORLDGEN_VERSION remains 7. No save schema, hydrology version, terrain IDs, spawn rules, resource rules or live v7 terrain path changed.
- The WorldGenerator integration is read-only through prototype_landform_at(); sample_fields()/terrain_at() remain authoritative for v1-v7.
- Draft module, audit utility and test module passed Python syntax compilation in the development environment.
- Standalone deterministic smoke used the repository's exact hash protocol over four seeds. Repeated coordinate samples matched exactly; all sampled field values stayed within 0..65535.
- A 49x49 sample window (2,401 samples/seed) across four smoke seeds produced all six prototype province classes on each seed. Observed elevation extrema across those windows ranged from 8,424 to 64,106.
- Negative-coordinate samples were included in deterministic checks.
- Full repository unittest discovery was not available from the GitHub connector environment in this work session. A repository test module was added so the next executable checkout can run the integration gate directly.

Next executable validation command:

```bash
python -m unittest tests.test_worldgen_v8_landforms
python tools/audit_worldgen_v8_landforms.py --seed worldgen-v8-audit
```

Do not promote WORLDGEN_VERSION to 8 until the visual/debug exports for multiple golden seeds are reviewed and Phase-2 gates in WORLDGEN_V8_ROADMAP.md pass.

---

## Source: `DEV24_VALIDATION.md`

# RC14 Dev24 — WORLDGEN v8 Phase-1 iteration-2 validation

Scope: non-authoritative geological landform prototype and Phase-0 comparison tooling.

## Implemented

- Promoted the prototype landform algorithm to `worldgen-v8-landforms-prototype-v2`.
- Added a slowly varying tectonic-stress orientation field.
- Added 4,096-cell major mountain systems, smaller aligned branch ranges, and deterministic bends along major range centerlines.
- Added structural/rift-valley corridors that lower prototype elevation and are exposed as a first-class field.
- Added continental-support scaling for uplift so deep-ocean areas receive much less mountain/plateau elevation.
- Added coast-detail perturbation only near the continental land/ocean threshold.
- Expanded the audit exporter with separate province/elevation/mountain/valley PPMs and gradient/coast-edge metrics.
- Added `tools/compare_worldgen_v7_v8.py` to sample frozen v7 and prototype v8 elevation over identical coordinates.
- Kept `WORLDGEN_VERSION = 7`; no live geography/persistence contract was changed.

## Validation performed in this work session

An isolated deterministic harness using WORLDSEED's exact `hash_u64` protocol was used to exercise the new landform module.

- Python compilation passed for the v2 landform module, expanded audit tool, comparison tool and targeted landform tests.
- Three standalone deterministic/diversity/connectivity tests passed in 12.722 seconds.
- The `v8-province-diversity` 97x97 sample window contained oceanic plain, lowland, upland, mountain chain, basin, plateau and rift-valley provinces; its ocean fraction was approximately 0.3766.
- The `v8-range-coherence` 129x129 sample window found 1,878 high-strength mountain samples; 1,877 had a cardinal high-strength neighbor, showing the new ranges form belts rather than isolated high points.
- A 96x96 / 64-cell-spacing visual audit for `worldgen-v8-audit` produced deterministic fingerprint `842324ce31ab044a96703a5cfaa9036daf595799`, ocean fraction 0.7265, mountain-strength fraction 0.1242, structural-valley fraction 0.0177, mean sampled gradient 679 and p95 sampled gradient 2,008. This is a local macro-window diagnostic, not a global target.
- Negative-coordinate coordinates remain present in the deterministic test set.

## Remaining validation

The GitHub connector does not expose a full executable checkout, so the repository-level integration test that imports the complete content registry/WorldGenerator was not executed here. Run on the next executable checkout:

```bash
python -m unittest tests.test_worldgen_v8_landforms
python tools/audit_worldgen_v8_landforms.py --seed worldgen-v8-audit
python tools/compare_worldgen_v7_v8.py --seed worldgen-v8-compare
```

Do not promote `WORLDGEN_VERSION` to 8 until multi-seed visual review, golden v7 capture and the Phase-2 compatibility gates pass.

---

## Source: `DEV25_VALIDATION.md`

# RC14 Dev25 — WORLDGEN v8 Phase-2 authority staging

Scope: authoritative elevation/version boundary for explicit v8 preview contexts.

## Implemented

- Added `WORLDGEN_PREVIEW_VERSION = 8` while keeping `WORLDGEN_VERSION = 7`.
- Split `WorldGenerator.sample_fields()` at the compatibility boundary:
  - v1-v3 keep their original fractal fields.
  - v4-v7 keep the exact established regional elevation/moisture/temperature path.
  - explicit v8 uses `LandformSampler.elevation` as authoritative elevation.
- v8 continues to use the frozen v4 moisture and broad temperature driver during
  Phase 2; altitude cooling and fertility respond to the new elevation.
- Added `WorldGenerator.landform_at()` as an authoritative read only for v8
  surface worlds; legacy worlds return `None`.
- Added a v8-aware spawn search that scans broad fields out to multi-thousand-cell
  scales before exact terrain/resource refinement. The old v4-v7 576-cell spawn
  search is untouched for legacy/explicit-v7 contexts.
- Added a hard-coded representative v7 field fixture test so later v8 work cannot
  accidentally mutate the legacy field contract.
- Added `tools/audit_worldgen_v8_phase2.py` for eight-seed elevation/ocean/start
  suitability/gradient/province calibration.

## Validation available in this session

The representative v7 fixture values in the new test were independently
recomputed from the repository's current hash and v7 regional-field equations
for five coordinates, including negative coordinates.

The GitHub connector does not provide an executable checkout of the current
private repository, so the complete registry/WorldGenerator test suite was not
run here. Before promotion of ordinary new worlds to v8, run:

```bash
python -m unittest tests.test_worldgen_v8_landforms tests.test_worldgen_v8_phase2
python tools/audit_worldgen_v8_phase2.py
python tools/audit_worldgen_v8_landforms.py --seed worldgen-v8-audit
python tools/compare_worldgen_v7_v8.py --seed worldgen-v8-compare
```

## Promotion gate still closed

Dev25 intentionally does **not** set `WORLDGEN_VERSION = 8`. Promotion requires
the repository-level tests above, multi-seed calibration review, spawn-fairness
checks with resources enabled, and confirmation that v7 golden terrain remains
unchanged. This prevents an unvalidated generator from becoming the default for
new player saves.

---

## Source: `DEV26_VALIDATION.md`

# RC14 Dev26 — WORLDGEN v8 topography and cave siting

Scope: continue Phase 2 without promoting ordinary new worlds to v8.

## Implemented

- Added `worldseed/world/topography.py` as a deterministic read model over
  authoritative v8 geological elevation.
- Added topographic fields for:
  - signed X/Y slope
  - normalized slope
  - raw and normalized local relief
  - ridge exposure
  - valley depth
  - ruggedness
- Added `WorldGenerator.topography_at()` and `World.topography_at()`.
  Legacy v1-v7 worlds return no authoritative v8 topography.
- Added `CaveGeneratorV8`, used only by explicit v8 worlds.
- v8 cave mouths now prefer exposed slopes, relief, ridges, mountain belts and
  plateaus rather than reusing the v7 entrance-placement rule.
- Deep valley-floor candidates are mildly penalized so cave mouths favor
  exposed walls/rock instead of flat depressions.
- v8 entrance depth can increase in strongly rugged/tectonically uplifted sites.
- Underground chamber/ore generation remains on the v7 contract for now. The
  later underground-geology phase will replace that separately.
- Added `tools/audit_worldgen_v8_topography.py` to measure slope, relief,
  ruggedness, ridges, valleys and generated cave-mouth characteristics.
- Added targeted topography/cave tests, including legacy-v7 planner isolation.

## Compatibility boundary

`WORLDGEN_VERSION` remains 7 and `WORLDGEN_PREVIEW_VERSION` remains 8.

No existing save changes geography. No v7 cave entrance namespace, v7 terrain
field, hydrology version, resource version or save schema changed.

## Validation notes

Representative v7 field fixtures added in Dev25 were independently recomputed
from the repository's exact `hash_u64` and v7 interpolation equations in this
work session; all five expected tuples match exactly, including negative
coordinates.

The connected GitHub environment still does not expose a full executable
checkout, so repository-level integration tests were not claimed as executed.
Run on the next executable checkout:

```bash
python -m unittest \
  tests.test_worldgen_v8_landforms \
  tests.test_worldgen_v8_phase2 \
  tests.test_worldgen_v8_topography \
  tests.test_dev16_caves_crafting

python tools/audit_worldgen_v8_phase2.py
python tools/audit_worldgen_v8_topography.py
```

The v8 promotion gate remains closed until these pass together with multi-seed
spawn/resource/traversability checks and legacy golden-terrain verification.

---

## Source: `DEV27_VALIDATION.md`

# RC14 Dev27 — WORLDGEN v8 promotion

Scope: promote WORLDGEN v8 from staged preview to the default generator for all
newly created worlds while preserving every existing world's recorded geography.

## Promotion changes

- `WORLDGEN_VERSION = 8`.
- `WORLDGEN_PREVIEW_VERSION` remains as an alias to the current v8 contract so
  existing audit tooling does not need a flag rename.
- `WorldDatabase.create()` now records worldgen version 8 for new saves through
  the existing version metadata contract.
- `WorldDatabase.open()` still reads and preserves the version already stored
  in the save. There is no v7 -> v8 geography migration.
- The generator's explicit `version <= 7` field path remains frozen.
- Default `WorldGenerator(...)` instances now use:
  - v8 geological elevation,
  - v8 derived topography,
  - v8 geological cave-mouth siting,
  - the existing independently versioned hydrology/coast projection,
  - the existing v4-derived moisture/temperature fields until Phase 3.
- The v8-aware large-scale spawn search from Dev25 is now the normal new-world
  startup path.
- Added a startup audit that uses the real default generator/resource/hydrology
  stack and reports final spawn dryness, passability, local reachability and
  landform type across deterministic seeds.
- Updated project agent/system/readme contracts so future work treats v8 as the
  current new-world generator and v1-v7 as immutable legacy geography.

## Regression coverage added/updated

- `tests/test_worldgen_v8_phase2.py` now requires default WORLDGEN v8 while
  continuing to hard-code representative v7 field tuples.
- `tests/test_worldgen_v8_promotion.py` verifies:
  - new databases record v8,
  - a stored v7 save remains v7 after reopen,
  - default generators are v8 while explicit v7 generators remain legacy.
- `tests/test_rc14_hydrology.py` now expects the current new-world version to
  be 8 while retaining the frozen RC13/v4 terrain fingerprint gate.
- Existing v7 cave tests continue to instantiate `version=7` explicitly, so
  v8 promotion does not rewrite their contract.

## Required executable validation

The connected GitHub environment can read/write the private repository but does
not provide a full executable checkout, so the full suite is not claimed as run
in this work session. Run:

```bash
python -m unittest \
  tests.test_worldgen_v8_landforms \
  tests.test_worldgen_v8_phase2 \
  tests.test_worldgen_v8_topography \
  tests.test_worldgen_v8_promotion \
  tests.test_rc14_hydrology \
  tests.test_rc13_pregeneration \
  tests.test_rc10_worldgen \
  tests.test_dev16_caves_crafting

python tools/audit_worldgen_v8_phase2.py
python tools/audit_worldgen_v8_topography.py
python tools/audit_worldgen_v8_startup.py
python tools/audit_traversability.py
python tools/bench_pregeneration.py
```

## Compatibility statement

Dev27 intentionally changes geography only for worlds created after the
promotion. A save whose metadata says worldgen 7 continues to instantiate
`WorldGenerator(..., version=7)` and therefore keeps its old elevation, climate,
coasts and v7 cave entrances. Generated chunk caches remain keyed by each save's
recorded worldgen version and authoritative tile/player/history deltas remain
separate.

## Next phase

Phase 3 should replace the temporary v4 moisture/temperature driver for v8 with
physical climate circulation: broad climate bands, prevailing winds, maritime
moderation, continentality, orographic precipitation and rain shadows. That
phase must retain the same explicit `version <= 7` compatibility boundary.

---

## Source: `DEV28_VALIDATION.md`

# RC14 Dev28 — WORLDGEN v8 physical climate and weather presentation

Scope: Phase 3 physical climate circulation plus climate-driven local weather,
wet terrain, cloud shadows, rain animation and day/night presentation.

## Implemented

- Added `worldseed/world/climate_v8.py`.
- V8 temperature/precipitation now derive from latitude-style climate belts,
  maritime influence, continentality, prevailing winds, altitude, orographic
  lift and leeward rain shadow.
- Added humidity and wind-strength read fields.
- V8 `sample_fields()` now consumes physical climate directly; v1-v7 remains
  on the frozen legacy path.
- Existing hydrology/environment/resource consumers therefore see v8 physical
  precipitation without a second climate authority.
- Reworked v8 weather into moving deterministic two-hour weather cells driven
  by local physical climate and prevailing wind.
- Added cloud cover, rain, storm intensity, fog, humidity, recent-rain wetness,
  wind vector and wind speed.
- Rain now waters crops and suppresses realized fire.
- Added season-aware dawn/day/dusk/night lighting read model.
- Added procedural pygame weather art: terrain-group wet textures, soft cloud
  shadow masks, animated rain streaks, ground splashes, fog haze, dark night
  grading and local fire glow.
- Weather visual animation is wall-clock-only presentation; authoritative
  weather remains seed + game-time + coordinate derived.
- Added weather status to the local sidebar.
- Added deterministic climate/weather/lighting tests and a multi-seed climate
  audit utility.

## Compatibility

- `WORLDGEN_VERSION` remains 8 for new worlds.
- Explicit v1-v7 generators retain their old moisture/temperature/elevation
  paths and existing saves remain pinned to their stored `worldgen_version`.
- Save schema is unchanged.
- Hydrology remains version 1 until Phase 4.
- Renderer weather effects are observational and never modify terrain,
  discovery, weather or clock state.

## Required executable validation

The connected GitHub environment does not provide the full executable private
checkout, so the complete test/render suite is not claimed as run here.

```bash
python -m unittest \
  tests.test_worldgen_v8_phase2 \
  tests.test_worldgen_v8_topography \
  tests.test_worldgen_v8_climate_weather \
  tests.test_worldgen_v8_promotion \
  tests.test_rc14_hydrology \
  tests.test_rc14_environment \
  tests.test_rc14_pygame_behavior

python tools/audit_worldgen_v8_climate.py
python tools/audit_worldgen_v8_phase2.py
python tools/audit_worldgen_v8_startup.py
python tools/audit_traversability.py
python tools/bench_pregeneration.py
```

Visual validation should explicitly inspect clear/cloudy/rain/storm/fog states
at dawn, midday, dusk and night, including zoom changes, hover redraw and idle
rain animation.

---

## Source: `DEV29_VALIDATION.md`

# RC14 Dev29 — WORLDGEN v8 Hydrology v2 foundation

Scope: begin Phase 4 by promoting hydrology v2 for new saves while preserving
legacy river geography and extending the drainage/read-model contract.

## Implemented

- Promoted `HYDROLOGY_VERSION` to 2 for newly created saves.
- Existing saves continue to use the hydrology version stored in metadata.
- Saves missing hydrology metadata are inferred as legacy v1; they are never
  silently assigned the newest river algorithm during open.
- `World` and the application startup path now instantiate hydrology from the
  save's recorded hydrology contract.
- Added version-aware hydrology algorithm IDs so v1 cache rows remain readable
  while v2 uses `worldgen-v8-hydrology-v2`.
- V2 generated domains persist:
  - local climate-driven runoff contribution,
  - downstream channel gradient,
  - existing elevation/fill/flow/accumulation/watershed/river/floodplain fields.
- V2 runoff consumes authoritative Phase-3 precipitation. Wet high terrain gets
  bounded headwater support; arid/rain-shadow areas contribute less because
  precipitation already carries that climate effect.
- River classes remain discharge/accumulation driven with v2 source thresholds.
- Channel midpoint refinement is now gradient-sensitive:
  - steep headwaters remain direct,
  - low-gradient rivers can meander farther.
- Tributary confluences widen from actual upstream river count.
- Ford candidates are physically gated by river class, gradient, bank slope,
  discharge and floodplain context. Stable hashing only breaks ties among
  physically suitable reaches.
- Rapids and gorge labels derive from channel gradient plus ruggedness.
- Added first-pass read-model signals for:
  - braided reaches,
  - meandering/oxbow potential,
  - low-gradient delta candidates.
  These do not yet invent separate terrain outside the hydrology authority.
- Expanded hydrology audit CSV/JSON output with runoff and channel-gradient
  statistics.

## Compatibility boundary

Hydrology is independently versioned from WORLDGEN.

- new v8 save: worldgen 8 + hydrology 2
- existing v8/hydrology-1 save: remains hydrology 1
- existing v5-v7/hydrology-1 save: remains hydrology 1
- missing historical hydrology metadata: inferred as v1
- generated v1 and v2 hydrology cache rows may coexist because version is part
  of the SQLite primary key

V1 serialization/fingerprints omit the new v2 arrays so the old payload
contract is preserved.

## Regression coverage added/updated

`tests/test_rc14_hydrology.py` now covers:

- current version constants,
- v1/v2 algorithm mapping,
- v2 runoff and channel-gradient arrays,
- v1 cache compatibility,
- v2 multi-domain seam checks including derived arrays,
- physical channel morphology reads,
- v1 and v2 generated cache coexistence,
- new-save hydrology v2 metadata,
- existing-save hydrology v1 pinning,
- World auto-hydrology respecting save metadata,
- existing RC13/v4 geography fingerprints.

## Required executable validation

The connected GitHub environment still does not expose a full executable private
checkout, so the suite below is not claimed as run in this work session.

```bash
python -m unittest \
  tests.test_rc14_hydrology \
  tests.test_worldgen_v8_climate_weather \
  tests.test_worldgen_v8_phase2 \
  tests.test_worldgen_v8_topography \
  tests.test_worldgen_v8_promotion \
  tests.test_rc13_pregeneration \
  tests.test_rc10_worldgen

python tools/audit_hydrology.py --seed v8-hydro-dev29
python tools/audit_worldgen_v8_climate.py
python tools/audit_worldgen_v8_startup.py
python tools/audit_traversability.py
python tools/bench_pregeneration.py
```

## Phase-4 work still open

- multi-point terrain-aware channel splines,
- explicit sediment transport proxy,
- natural river islands / fully materialized braided channels,
- oxbow lake/meander-scar materialization,
- delta distributary terrain,
- stronger valley-confined gorge shaping,
- dedicated v2 river/coast art where morphology needs new visual classes,
- multi-seed discharge/class calibration and performance profiling.

---

## Source: `DEV30_VALIDATION.md`

# RC14 Dev30 — Hydrology v2 morphology materialization

Scope: continue WORLDGEN v8 Phase 4 without changing the persisted Hydrology v2
drainage solve. This work versions and upgrades the local river projection layer.

## Implemented

- Added `HYDROLOGY_MORPHOLOGY_VERSION = 2` for newly created saves.
- Saves created during Dev29 with hydrology v2 but no morphology metadata infer
  morphology v1, preserving their single-midpoint river projection.
- Added a dedicated `generated_surface_chunks` cache keyed by:
  - worldgen version,
  - hydrology version,
  - morphology version.
  This closes the old ambiguity where surface terrain could depend on hydrology
  while the cache key recorded worldgen only.
- Existing underground/pre-hydrology chunk caches remain worldgen-keyed.
- Morphology v2 replaces the single midpoint with deterministic multi-point
  centerlines. Low-gradient reaches can form broader S-curves; steep reaches
  remain comparatively direct.
- Suitable medium/major reaches now physically split into a secondary channel
  and rejoin at the downstream node. Base terrain remains between threads,
  creating natural deterministic river islands without renderer-owned geometry.
- Mature low-gradient floodplains can materialize detached shallow-water oxbow
  scars. The oxbow contract is deterministic from the parent flow edge.
- Oxbow ellipses orient their long axis with the dominant channel direction.
- Steep, rugged near-channel cells can materialize as rocky gorge banks.
- River current lookup now consumes the same morphology centerlines as terrain,
  including secondary braided threads.
- Channel/oxbow geometry helpers are bounded LRU caches to keep repeated
  per-tile projection inexpensive during chunk generation.
- No new terrain IDs were required:
  - braid threads use the existing stream/river water family,
  - islands use the authoritative underlying terrain,
  - oxbows use freshwater lake shallows,
  - gorge banks use existing rock terrain.
  Existing water animation/autotiling therefore applies automatically.

## Compatibility boundary

Drainage and morphology are separate contracts.

- Dev29/newer hydrology domain solve: `hydrology_version = 2`
- Dev29 projection: `hydrology_morphology_version = 1`
- Dev30 projection: `hydrology_morphology_version = 2`
- older saves missing hydrology metadata: hydrology v1 + morphology v1
- existing saves are never assigned a newer morphology contract on open

Generated hydrology-domain fingerprints do not change in Dev30 because the
Priority-Flood/runoff/discharge arrays are unchanged. Only local materialization
changes behind the new morphology version.

## Regression coverage

`tests/test_rc14_hydrology.py` now also checks:

- current morphology version constant,
- deterministic four-point morphology-v2 centerlines,
- braid split/rejoin endpoint invariants,
- deterministic detached oxbow geometry,
- Dev29 morphology-v1 single-midpoint compatibility,
- current lookup on braided water,
- new-save morphology metadata,
- missing morphology metadata -> v1,
- save-pinned morphology during World auto-hydrology,
- surface chunk cache isolation by hydrology/morphology version.

## Audit tooling

Added `tools/audit_hydrology_morphology.py` to report:

- channel style counts,
- braided / gorge / ford / delta / oxbow samples,
- terrain override distribution,
- crossing-cost distribution,
- domain fingerprint/invariant results.

`tools/audit_hydrology.py` now reports the active morphology version too.

## Required executable validation

The connected GitHub environment still does not provide an executable checkout,
so these commands are documented rather than claimed as executed:

```bash
python -m unittest \
  tests.test_rc14_hydrology \
  tests.test_worldgen_v8_climate_weather \
  tests.test_worldgen_v8_phase2 \
  tests.test_worldgen_v8_topography \
  tests.test_worldgen_v8_promotion \
  tests.test_rc13_pregeneration

python tools/audit_hydrology.py --seed v8-hydro-dev30
python tools/audit_hydrology_morphology.py --seed v8-hydro-dev30 --domain-x 0 --domain-y 0
python tools/audit_hydrology_morphology.py --seed v8-hydro-dev30-b --domain-x -1 --domain-y 1
python tools/audit_traversability.py
python tools/bench_pregeneration.py
```

Visual validation should inspect at least one braided reach, one mature
low-gradient floodplain, one steep rapid/gorge reach, and a legacy
morphology-v1 save to confirm the old local river path does not move.

## Phase-4 work still open

- sediment transport/deposition proxy,
- stronger deterministic alluvial-island shaping inside large braids,
- oxbow infill succession / abandoned meander scars beyond open water,
- delta distributary materialization (candidate signal remains only),
- broader gorge/valley-wall interaction,
- multi-seed discharge/morphology calibration,
- performance profiling of very large prepared hydrology windows.

---

## Source: `DEV32_VALIDATION.md`

# RC14 Dev32 — WORLDGEN v8 Phase 5 coastal morphology foundation

Scope: resume the staged WORLDGEN v8 roadmap after the Dev31 playtest/visual
correction work. Phase 4 hydrology v2 + morphology v2 remains the current
drainage authority. Dev32 starts Phase 5 without replacing the recently updated
rain, cloud, tree, morel or cave presentation.

## Implemented

- Added `worldseed/world/coast_v8.py` with a deterministic
  `CoastV8Sampler` / `CoastMorphology` read model.
- Bathymetric shelf depth combines raw sea depth with horizontal distance to
  opposite land, so continental geometry matters instead of local slope alone.
- Added coast geometry reads for land fraction, open-sea exposure, shelter,
  bay/headland tendency and near-coast detection.
- Added first-pass physical coast classes: beach, rocky coast, cliff, headland,
  tidal flat, marsh, protected bay and nearshore/open ocean.
- Added shore-material tendency (sand/gravel/rock/mud) from relief/slope,
  shelter and exposure. Phase 6 substrate remains the future material authority.
- Added tidal-flat, marsh and lagoon potential.
- Added sediment, estuary and delta potential that consume prepared hydrology
  when available. Missing/unprepared drainage is not generated by inspection.
- Exposed coast reads through `WorldGenerator.coast_at()` and
  `World.coast_at()`.
- Added `tests/test_worldgen_v8_coast.py`.
- Added `tools/audit_worldgen_v8_coast.py` for multi-seed calibration.

## Compatibility

- `WORLDGEN_VERSION` remains 8.
- `HYDROLOGY_VERSION` remains 2.
- `HYDROLOGY_MORPHOLOGY_VERSION` remains 2.
- Save schema is unchanged.
- Existing terrain IDs and generated surface-chunk cache keys are unchanged.
- This first Phase-5 slice is intentionally terrain-neutral: it cannot move an
  existing coast or rewrite a save.
- Legacy v1-v7 generators return no v8 coast read model.

## Validation gates for this slice

```bash
python -m compileall worldseed
python -m unittest tests.test_worldgen_v8_coast
python -m unittest tests.test_rc14_hydrology tests.test_worldgen_v8_climate_weather tests.test_worldgen_v8_phase2 tests.test_worldgen_v8_topography tests.test_worldgen_v8_promotion tests.test_rc13_pregeneration tests.test_dev22_atlas tests.test_dev31_playtest_fixes tests.test_worldgen_v8_coast
python tools/audit_worldgen_v8_coast.py --seeds 4 --radius 2048 --step 128
python tools/audit_hydrology.py --seed v8-dev30-test-build
python tools/audit_hydrology_morphology.py --seed v8-dev30-test-build --domain-x 0 --domain-y 0
python tools/audit_content.py
python tools/audit_visuals.py
```

The GitHub Dev32 build workflow is the executable gate for this work session.
Do not claim the phase slice validated until that run completes successfully.

## Next Phase-5 slice

1. Calibrate the coast-class distribution across more seeds and negative
   coordinates.
2. Introduce the explicit save-pinned coast materialization/version boundary
   before any terrain IDs change.
3. Materialize varied shoreline classes from the approved read model.
4. Couple major river mouths to stable distributary/estuary geometry.
5. Add seam tests for coast materialization and then update atlas/local terrain
   presentation using the same authority.

---

## Source: `DEV33_VALIDATION.md`

# RC14 Dev33 — WORLDGEN v8 Phase 5 coastline materialization

Scope: convert the approved Dev32 coastal morphology read model into a
save-visible physical coastline for new worlds without rewriting existing v8
saves or replacing the recent atmosphere/tree/morel/cave visual work.

## What changed in the game

New worlds with coast morphology v1 can now physically contain:
- sandy shore;
- coastal gravel;
- rocky shore;
- impassable coastal cliffs;
- tidal flats;
- salt marshes;
- coastal wading water;
- shallow ocean;
- continental shelf water;
- deep ocean.

These are authoritative terrain IDs, not renderer-only decorations. They can
therefore affect collision, inspection, atlas output and later ecology/resource/
settlement/route systems. Dedicated new coast artwork is deferred; Dev33 reuses
approved rock, riverbank, floodplain and wetland art families.

Bathymetric terrain now consumes the Phase-5 continental-geometry shelf model
instead of deriving all ocean depth solely from the old local-slope distance
approximation.

## Compatibility

- WORLDGEN_VERSION remains 8.
- HYDROLOGY_VERSION remains 2.
- HYDROLOGY_MORPHOLOGY_VERSION remains 2.
- COAST_MORPHOLOGY_VERSION is 1 for new v8 saves.
- Existing saves missing coast metadata infer coast version 0.
- Coast version 0 keeps the pre-Dev33 shoreline materialization.
- Surface cache identity now includes coast version.
- The new cache table is additive; old surface cache rows remain readable only
  for coast version 0.
- Save schema remains 3.

## Performance

Detailed coast analysis is reused on an absolute 8-cell materialization lattice.
Exact geological elevation still determines land versus water per tile, so this
optimization does not snap the coastline into 8x8 blocks.

A regression test asserts that a 16x16 materialization window produces at most
four expensive coast-classifier misses after cache reset.

## Validation

Fast Dev33 gate:
- compileall;
- Phase-5 coast regression suite;
- pregeneration/surface-cache compatibility tests;
- atlas drag regression;
- content audit;
- visual audit;
- multi-seed coast audit.

The standard Dev33 workflow additionally runs the existing WORLDGEN v8,
Hydrology v2, climate, topography, promotion, atlas and playtest regression
suite and packages the build.

## Still open in Phase 5

- physical river-mouth distributaries/delta lobes;
- expanded estuary geometry from discharge + shelter/tidal context;
- spits and barrier-island candidates/materialization;
- dedicated visual art for rocky coast/cliff/gravel/tidal flat/salt marsh;
- larger multi-seed coast distribution calibration;
- explicit coast seam audit around prepared-domain boundaries;
- later Phase-6 substrate/soil refinement of shore material.

---

## Source: `TEST_BUILD_CHECKLIST_DEV30.md`

# WORLDSEED RC14 Dev30 Test Build Checklist

Build target: **WORLDGEN v8 / Hydrology v2 / Hydrology Morphology v2**

Build source commit: **67b2d3d0c7c5279f9a59c959f2cfb0916c5cd864**

This checklist is the manual acceptance gate before WORLDSEED moves deeper into
Phase 4 and then Phase 5. Test on a **new world first** so the build uses the
current v8/v2/v2 generation contracts.

## 1. Startup and basic stability

- [ ] Launch `RUN_WORLDSEED.bat` and confirm the graphical client opens.
- [ ] Create a brand-new world with a seed you can record.
- [ ] Confirm the world-generation/loading screen completes without crashing.
- [ ] Confirm the game does **not** open directly into the pause/Esc menu.
- [ ] Move with WASD for several minutes and verify there is no movement queue,
      overshoot, major hitching, or input lag.
- [ ] Zoom the local view in and out repeatedly.
- [ ] Open/close Inventory, Crafting, Build, Health, Map, Actions, World, Look,
      Help and Pause using mouse controls.
- [ ] Save, quit, reopen the same world and verify your character position and
      visible terrain are unchanged.

## 2. WORLDGEN v8 geography

Test at least **3 new seeds**.

- [ ] Continents/coasts look irregular rather than like noise blobs or grids.
- [ ] Mountain chains appear as connected ranges instead of isolated circular hills.
- [ ] Valleys, basins, plateaus and uplands are visually distinguishable.
- [ ] Terrain transitions do not form obvious straight chunk/domain seams.
- [ ] Caves appear in terrain that makes physical sense.
- [ ] Spawn locations are on traversable land with useful nearby resources.
- [ ] No obviously impossible inland ocean strips, square lakes, or repeated geometric patterns are visible.

Record seeds that produce especially good or bad geography.

## 3. Physical climate and rain shadows

Explore opposite sides of mountain ranges when possible.

- [ ] Wet/windward mountain regions generally support wetter terrain.
- [ ] Some leeward regions are visibly drier, demonstrating rain-shadow effects.
- [ ] Coastal regions feel more moderate/moist than deep continental interiors.
- [ ] Climate transitions are broad and gradual rather than changing every tile.
- [ ] Forest/scrub/grass/tundra placement looks compatible with local climate.
- [ ] No obvious climate seams appear at chunk boundaries.

## 4. Dynamic weather visuals

Play long enough to observe multiple weather states.

### Clouds
- [ ] Partly cloudy conditions cast irregular moving shadow patches over terrain.
- [ ] Cloud shadows are soft and organic, not hard circles/squares.
- [ ] Cloud movement direction looks coherent.
- [ ] Heavy cloud cover darkens the world more than light cloud cover.
- [ ] Clouds do not darken menus/UI to the point of poor readability.

### Rain
- [ ] Rain streaks are visibly animated while gameplay waits for input.
- [ ] Wind changes the apparent slant/direction of rainfall.
- [ ] Rain produces visible ground splash effects.
- [ ] Vegetation, soil, sand/floodplain and stone respond differently to wetness.
- [ ] Ground remains damp for a while after rain ends instead of instantly becoming dry.
- [ ] Wet stone has a subtle damp sheen without looking metallic.
- [ ] Rain over water does not apply inappropriate land-wetness shading.
- [ ] Heavy rain/storms reduce visibility appropriately.
- [ ] Weather animation does not cause noticeable input lag or frame hitching.

### Fog/storms
- [ ] Fog produces visible haze but the game remains playable.
- [ ] Storm conditions look darker/heavier than normal rain.
- [ ] Rain visually and mechanically suppresses active fires when you can test that interaction.

## 5. Dawn, day, dusk and night

- [ ] Dawn transitions into daylight without a sudden brightness jump.
- [ ] Dusk gradually darkens the local world.
- [ ] Night is meaningfully dark.
- [ ] Night uses a cooler blue/black appearance rather than a flat black screen.
- [ ] UI/menu text remains readable at night.
- [ ] Campfires/light-producing scenes visually stand out at night.
- [ ] Cloudy daytime is dimmer than clear daytime.
- [ ] Rain/storm darkness combines correctly with time-of-day lighting.
- [ ] Water, terrain overlays, character sprites and hover highlights do not become strangely bright after night/weather overlays.

## 6. Hydrology v2 — rivers and drainage

Explore rivers on at least **3 different seeds**.

- [ ] Small streams appear upstream of larger rivers where appropriate.
- [ ] Tributaries visibly merge into larger channels.
- [ ] River size generally increases downstream.
- [ ] Rivers follow valleys/low terrain rather than climbing ridges.
- [ ] Wet regions produce more convincing headwaters than dry rain-shadow areas.
- [ ] Major rivers are less common and wider than small streams.
- [ ] Rivers do not abruptly stop at chunk/domain boundaries.
- [ ] No obvious straight grid-aligned river networks dominate the map.
- [ ] Floodplains/wetlands appear near suitable low-gradient rivers.
- [ ] Riverbanks look distinct from coastlines and open-water shores.
- [ ] Rapids appear on steeper river reaches.
- [ ] Rapids do not appear excessively on flat floodplains.
- [ ] Fords appear on physically reasonable shallow/narrow reaches rather than obviously random positions.
- [ ] Deep/major river cores remain meaningfully harder to cross.

## 7. Hydrology Morphology v2 — new Dev30 features

These are the most important Phase-4 visual checks.

### Multi-point/meandering channels
- [ ] Mature low-gradient rivers form broad curves/S-bends.
- [ ] Steep mountain streams stay tighter/straighter.
- [ ] Curves are continuous and do not create broken water pixels.

### Braided rivers and islands
- [ ] Find at least one braided reach across your test seeds if possible.
- [ ] A braided river visibly splits into two water threads.
- [ ] The threads rejoin naturally downstream.
- [ ] Land between braid threads appears as a believable river island.
- [ ] The island uses surrounding/base terrain rather than a fake overlay.
- [ ] Water current animation follows both braid geometry and downstream flow.
- [ ] Braid entrances/exits do not create blocked one-cell artifacts.

### Oxbows/meander scars
- [ ] Find a mature floodplain with an oxbow if possible.
- [ ] Oxbow water is detached from the active river channel.
- [ ] The oxbow shape curves/orients with the parent river rather than always appearing horizontal.
- [ ] Oxbow shallows blend correctly into surrounding floodplain/wetland.
- [ ] Oxbows do not appear in steep mountain terrain.

### Gorges
- [ ] Steep rugged river reaches can produce rocky gorge margins.
- [ ] Gorge banks visually read as confined terrain.
- [ ] Gorge rivers/rapids remain continuous through the confined reach.
- [ ] Gorge rock does not create impossible isolated walls or trap the player in otherwise traversable terrain.

## 8. Water animation/current consistency

- [ ] River animation flows generally downstream.
- [ ] Braided threads do not visually flow against their terrain path.
- [ ] Rapids animate differently/intensely enough to read as faster water.
- [ ] Ocean/coastal current animation still works.
- [ ] River/ocean meeting areas do not flicker between incompatible visuals.
- [ ] Zooming does not reverse or break water animation.

## 9. World map / atlas consistency

- [ ] Open the world map after exploring several terrain types.
- [ ] Terrain shown on the map corresponds to what is actually present locally.
- [ ] Rivers/lakes/coasts visible locally are represented coherently on the map.
- [ ] Moving the cursor over the map never reveals or flashes the gameplay screen.
- [ ] Pan and zoom repeatedly without corruption or major lag.
- [ ] Known villages/cities/camps/caves/sites remain in sensible locations.
- [ ] Unexplored terrain is not falsely revealed.

## 10. Save/load and compatibility

### Current test world
- [ ] Save beside a river/braid/oxbow/gorge.
- [ ] Reopen the save.
- [ ] Confirm the exact river path and surrounding terrain did not move.
- [ ] Cross chunk boundaries after reload and confirm river continuity.
- [ ] Confirm explored map terrain remains consistent after reload.

### Older save, if available
- [ ] Back up the save first.
- [ ] Open a pre-Dev30 world.
- [ ] Confirm it loads without regeneration errors.
- [ ] Confirm existing river/coast geography has not visibly shifted.
- [ ] Save/reopen once and verify it remains stable.

## 11. Performance / regression checks

- [ ] Hold movement across several prepared chunks and watch for stutter.
- [ ] Travel alongside a large animated river during rain.
- [ ] Zoom while rain/cloud shadows/wetness/night effects are active.
- [ ] Hover many tiles rapidly and confirm no map/gameplay flashing.
- [ ] Leave the game open during animated rain for several minutes and look for memory growth or progressively worse performance.
- [ ] Open crafting and inventory repeatedly; confirm neither crashes.
- [ ] Press Q only when you intend to save/quit; confirm it no longer crashes.
- [ ] Generate another new world in the same session and confirm startup remains reliable.

## 12. What to report back

For every problem, record:

- seed;
- save name;
- approximate world coordinates if visible;
- screenshot;
- what you were doing immediately before the issue;
- whether it reproduces after save/reload;
- whether it occurs at all zoom levels;
- whether it is graphical only or affects movement/gameplay.

### Phase-4 acceptance

Do **not** move to the next major world-generation phase if any of these are repeatable:

- rivers break or jump at chunk/domain seams;
- saved river geography changes after reload;
- new weather/night rendering causes movement or UI regressions;
- rain/cloud/night overlays make important gameplay unreadable;
- braids create impassable accidental walls;
- oxbows or gorge banks appear in physically absurd locations at high frequency;
- world-map terrain contradicts local terrain;
- new-world generation crashes or regularly creates invalid spawns.

Minor art tuning, rare morphology calibration issues and missing delta
distributaries can be logged for later work without blocking basic Dev30 testing.

---

## Source: `TEST_BUILD_CHECKLIST_DEV31.md`

# WORLDSEED RC14 Dev31 Playtest Checklist

This build is a correction pass based on the first Dev30 hands-on test. Focus on
long exploration, atlas behavior, weather presentation, time pacing and dynamic
visibility before continuing world-generation Phase 4.

## Highest-priority checks

### Long exploration / performance
- [ ] Explore continuously for at least 15–20 minutes.
- [ ] Cross several chunk and 512-cell region boundaries.
- [ ] Confirm movement/rendering does not progressively slow as more regions are realized.
- [ ] Watch the 40-turn autosave interval. Autosave may briefly report itself,
      but it should no longer perform a rotating full-database backup or cause a long freeze.
- [ ] Open/close the atlas repeatedly after substantial exploration and verify it remains responsive.
- [ ] If the game appears to crash/freeze again, record the seed, coordinates,
      approximate turn/time, and whether it recovers without restarting.

## Time pacing
- [ ] One ordinary movement step advances exactly **1 game minute**.
- [ ] 60 movement steps advance about one in-game hour, not several hours.
- [ ] Longer activities such as crafting/resting still use their authored durations.
- [ ] A full day should no longer pass after only a few dozen movement steps.
- [ ] Hunger/thirst/weather/day-night cadence feels compatible with the slower travel clock.

## Circular visibility
- [ ] Newly visible terrain has a genuinely circular boundary instead of a square.
- [ ] Previously explored terrain outside current sight remains remembered but visibly dimmed.
- [ ] NPCs/resources/creatures outside current sight are not visible through exploration memory.
- [ ] Clear daylight produces a noticeably larger radius than night.
- [ ] Fog/heavy weather contracts the radius.
- [ ] Perception / Survival / Keen Senses improve the radius.
- [ ] Sidebar "View radius" matches the apparent radius.
- [ ] Trees/walls/other sight blockers still obstruct cells inside the circle.

## Cloud shadows
- [ ] Cloud shadows look like irregular multi-lobed cloud banks, not circles.
- [ ] Stand still for 30–60 seconds and confirm clouds continue moving.
- [ ] Walk around and confirm the shadow field does **not** stay attached to the player/camera.
- [ ] Cloud drift direction remains coherent with wind.
- [ ] Partly cloudy conditions show separated cloud banks; heavy cloud cover feels broader.
- [ ] Cloud animation does not create significant frame stutter.

## Dawn / dusk / night
- [ ] Dawn begins gradually and uses light amber/orange tones.
- [ ] Dusk uses warmer, lighter orange/gold before cooling into night.
- [ ] Transition lasts long enough to read as a transition rather than a sudden filter swap.
- [ ] Night remains dark/blue-black and playable.
- [ ] Weather/cloud darkness combines naturally with twilight.
- [ ] Campfire glow and UI readability remain intact.

## Terrain atlas / world map
- [ ] Left-click and **drag directly on the map** to pan.
- [ ] Mouse wheel zoom works while the atlas is open.
- [ ] A simple click without dragging inspects a cell.
- [ ] "Center on player" works.
- [ ] Old directional/zoom button clutter is gone.
- [ ] Only actually discovered cells are shown; one explored tile must not reveal a huge square region.
- [ ] Panning after a long exploration session remains responsive.
- [ ] The atlas never generates new terrain or reveals undiscovered POIs.
- [ ] Local terrain and atlas terrain match after save/reload.

## River appearance on atlas
- [ ] Inland rivers read as clean continuous channels rather than thick "intestine" outlines.
- [ ] Floodplain/riverbank colors no longer dominate distant atlas pixels around every river.
- [ ] Tributaries are still visible enough to follow.
- [ ] River mouths/estuaries remain legible.
- [ ] Braids and oxbows do not turn into oversized blobs at distant zoom.
- [ ] At close/native atlas zoom, exact local terrain identity is preserved.

## Existing weather/hydrology regression
- [ ] Rain streaks and splashes animate.
- [ ] Ground wetness persists after rain and dries later.
- [ ] Rapids/gorges/braids/oxbows still render correctly.
- [ ] Water current direction remains consistent.
- [ ] Save beside a river, reload, and confirm geometry is unchanged.

## Mountain follow-up test
Use the included `DEV31_TEST_LOCATIONS.json` with seed:

`dev31-mountain-test`

It contains deterministic high-relief mountain candidates generated by the same
WORLDGEN v8 code as the build.

- [ ] Create a world using that seed.
- [ ] Reach or inspect at least one listed mountain candidate.
- [ ] Confirm mountain chains look connected rather than circular noise hills.
- [ ] Compare windward/leeward sides for rain-shadow differences.
- [ ] Check river headwaters and gorge/rapid behavior in the mountains.
- [ ] Check circular sight range under mountain weather/night conditions.

## Bug report format

For anything repeatable, record:
- seed;
- save name;
- x/y/z coordinates;
- screenshot;
- in-game date/time and weather;
- approximate minutes played;
- whether the issue appeared near an autosave;
- whether save/reload reproduces it;
- whether it is visual-only or affects movement/simulation.

Do not advance to the next major world-generation phase if progressive
exploration lag, atlas instability, save/reload terrain movement, broken circular
visibility, or weather presentation regressions remain repeatable.

---

## Source: `TEST_BUILD_TRIGGER_DEV30.md`

# Dev30 test build trigger

This file exists only to trigger the first validation/package workflow after the workflow was added.

---

## Source: `UI_INVENTORY_VALIDATION.md`

# WORLDSEED Unified Inventory Validation

Parallel UI Track 1 redesigns the pygame inventory without changing inventory ownership or simulation authority.

## Player-facing contract

- I opens one inventory surface.
- Carried items are visible as clickable icon cards.
- Selection updates the detail pane in place.
- Use, Drop, Split and Store are available directly beside the selected item when legal.
- Split only changes the selected action quantity; it does not create a second persistent stack representation.
- Executing an action keeps the inventory open.
- Terminal mode keeps the previous hierarchical fallback.

## Authority contract

The renderer only emits pointer/keyboard intent tokens. Item mutations remain in existing simulation commands:

- EatCommand
- EquipCommand
- ReadBookCommand
- DropCommand
- StoreCommand

No pygame callback mutates Inventory, world piles, equipment or time directly.

## Targeted regression coverage

- Structured feature-menu data still reaches the pygame renderer.
- UI_ACTION tokens pass through the shared menu widget to the inventory owner.
- Unified inventory item cards remain pointer-selectable at small and large window sizes.
- A real pygame flow selects a four-item Wood stack, chooses Split (2), drops that amount, stays inside the inventory flow, and leaves two Wood in the authoritative Inventory.
- Existing terminal navigation tests remain unchanged and continue to exercise the fallback inventory.

## Manual checks

1. Open inventory with I and confirm there is no Pack/Browse duplication.
2. Click several item icons and confirm the grid never disappears while details update.
3. For food, confirm Use is labeled as Eat and consumes one item.
4. For equippable gear, confirm Use equips the item through the existing equipment command.
5. With a stack larger than one, click Split and verify Drop/Store uses the displayed half-stack amount.
6. Adjust quantity with - / + / All and verify the selected amount never exceeds the carried count.
7. Stand near a storage container and verify Store becomes enabled; move away and verify it is disabled.
8. Resize to 800x520 and 1600x900 and confirm cards/actions remain inside the window and above the footer.
9. Verify Esc returns directly to gameplay from the graphical inventory.

---

# Development Handoffs and Progress Records

---

## Source: `docs/DYNAMIC_ATMOSPHERE_HANDOFF.md`

# Dynamic atmosphere foundation

## Scope

Clouds now have independently composed silhouettes rather than copies of one rotated image. Each identity uses three to seven irregular textured pieces with independent rotation, aspect, placement and opacity. A shared composited alpha field projects the same silhouette as a softened shadow. Wisps and banks have different proportions; per-particle widths/heights span small puffs through large banks.

Two world-anchored `FieldEmitter`s create deterministic, seed-specific visual particles with different wind advection rates. They form and dissipate over long, staggered lifetimes (6-12 minutes of wall time depending on layer), fading to zero before their next identity appears. Wall time affects only presentation; weather, sunlight and game time remain authoritative frozen samples. Clouds are visual, not persistent simulation entities.

## Modules / extension contract

- `presentation/atmosphere.py`: immutable `WeatherSample` and `EffectFrame`; stateless bounded `FieldEmitter`; ordered `EffectStack` with duplicate-name rejection and clip restoration even on errors.
- `presentation/clouds.py`: cloud shape composition, matching shadows, two layers, bounded source/shape/stamp/frame caches.
- `presentation/weather_fx.py`: existing fog, cloud and rain passes registered in one stack. Both full gameplay and idle rendering call the same `draw_atmosphere` entry point. Lighting and local fire glows keep their previous position before atmosphere composition.
- `ui/pygame_terminal.py`: idle animation asks the registered effects whether a repaint is needed instead of hardcoding each weather type.
- `tools/preview_weather_visuals.py`: G toggles a gallery of twelve distinct shapes; `--gallery --capture <path>` supports headless inspection.

A future effect registers a named ordered callback receiving an `EffectFrame` and returning surfaces (or an empty tuple), plus an animation predicate reading `WeatherSample`. Use a separate emitter namespace and explicit count/lifetime limits for each particle type. This is the extension point for fog motion, hail, lightning/light overlays and smoke; those new phenomena are **not** simulated or activated by this change.

Future weather phenomena must first come from authoritative simulation samples. Smoke must receive immutable samples of known nearby emitters, not scan the world or invent fires. Do not pass Simulation/World into an effect callback. Extend the copied frame/sample contract when additional authoritative inputs are needed. Registration is configuration-time, capped at 32 named passes. Normal layer order is fog 10, clouds/shadows 20, rain 30.

## Determinism / persistence / budgets

No schema, terrain, visibility, worldgen or save changes. No simulation RNG use. New presentation namespaces: `weather-art:cloud-low`, `weather-art:cloud-high`, `weather-art:cloud-piece`. Stable cell/lifetime hashes determine particle identity; viewport movement does not reroll overlapping particles. Render reconstruction does not depend on which screen was opened first.

Each emitter visits at most a 32x32 cell window and emits at most 256 particles; no history is accumulated. Cloud shapes use a 48-entry LRU, scaled cloud/shadow stamps a 64 MiB pixel budget, and composited frames two entries. At close zoom the soft atmospheric field is rendered at half resolution and upscaled once, preserving world footprint without large per-cloud cache churn. In synthetic 1280x720 checks, warm cloud frames averaged 3.5-5.9 ms across tile sizes 16-56; initial source/shape loading measured about 68 ms. This is not a full-game FPS measurement.

## Validation

New tests cover distinct silhouettes, shadow support, reconstructable particle identities, camera-independent placement, lifespan renewal, emitter bounds, immutable samples, composition order, clipping, duplicate registration and exception cleanup. Existing weather/cave/resource visual regressions remain in the targeted gate.

Validation on Python 3.13: 27 targeted atmosphere/weather/art/terrain/render tests passed; the full gameplay frame observational and centered rendering test passed across all zoom limits. Compileall and the visual coverage audit passed. Golden replay passed with hash `0b369fbd04f8fab3ce6a7b295ee942ac369f000d`. The twelve-shape gallery was rendered and visually inspected.

The preceding complete suite ran 330 tests with six failures and one error outside the edited visual logic (not all independently established as baseline). This iteration's full-suite attempt stopped at its 300-second limit, so no complete clean gate is claimed. The earlier run took 97 minutes. Changes remain on the draft branch; no main-branch merge or interactive gameplay verification is claimed.

Known limitation: a changed wind sample changes the analytic drift field immediately; interpolation of changing wind vectors is a future presentation refinement. No fog/hail/lightning/smoke behavior is invented by the rendering foundation.

---

## Source: `docs/VISUAL_REWORK_HANDOFF.md`

# Cloud, resource and cave visual repair

## Root causes

The reported cave stripes were sprite-sheet extraction errors, not cave generation: `dev17_cave_floor_*` and `dev17_cave_wall_*` contained transparent margins, partial tiles and fragments of other terrain. The manifest randomly selected these alongside intact variants, producing the patchwork in the screenshot. The manifest now uses only the intact ten cave-floor and six cave-wall materials. Existing saves retain their terrain IDs, topology, mining state and visibility.

The old pine sprite included adjacent tree fragments, and the morel sprite included unrelated vegetation. Both are replaced with newly generated transparent single-subject artwork, with explicit display sizes and smooth downsampling in the visual manifest. Pine saplings scale below mature trees. Other resource sizing remains unchanged.

## Weather system

`worldseed/presentation/clouds.py` owns the presentation cloud field. A new overhead cloud-bank texture replaces all ellipse/ring primitives. A shared density map supplies the cloud canopy and softened shadow, so their shapes agree. Two deterministic world-space layers provide varied bank sizes and wind drift. Coverage and storm intensity control density; sampled daylight controls shadow strength; sampled game time and sunrise/sunset control projection direction and length. Night clouds are subdued. No weather or time is generated by the renderer.

Cloud textures are referenced through `VisualRegistry.special('cloud_bank')`. `resource_rendering` in the manifest controls resource width/height in tile units and smooth scaling. No persistent fields, migration, worldgen version or view-distance changes.

New deterministic namespace: `weather-art:textured-cloud` (presentation only). The stamp LRU has a 64 MiB pixel budget; only two composited frame pairs are retained. Source/density textures are loaded once. Frame output depends on the provided samples and visual phase, not world queries.

## Artwork provenance

The cloud bank, pine tree and morel cluster were generated with the built-in image-generation tool for this task and copied into the repository with their original alpha channels. Source output names: `exec-39f6c7d0-b314-499c-992d-fdb91aeff64d.png`, `exec-42ae0349-e585-4aec-adb4-76ec6f70f963.png`, `exec-11b74b16-e531-4fab-b9a4-977ee4566a7c.png`. Existing cave textures were reused rather than regenerating geography or inventing underground features.

## Verification and preview

19 focused visual tests pass. Visual coverage/alpha audit and compileall pass. New regressions check all cave material variants for opaque full-tile coverage, pine/morel display size, textured density detail, deterministic cloud output, light-dependent shadows, bounded caches and frozen weather inputs. SDL smoothscale may return alpha 253 from an opaque source; tests require fully opaque source art and tolerate this harmless resampling roundoff.

Run `python tools/preview_weather_visuals.py` for an interactive synthetic scene using the actual renderer and shipped assets. Controls: 1 day, 2 dusk, 3 night, 4 dawn, C cloud, R rain, S storm, V cave, Esc exit. This tool neither opens nor writes a save. `--capture <path>` produces a headless PNG; add `--cave` or `--storm` to select those conditions. Surface and cave captures were inspected.

Full serial suite completed on Python 3.13: 330 tests in 5827 seconds, six failures and one error. Failing cases: atlas pointer target, prepared-region lookup, underground discovery, two tree/resource-location assumptions, bootstrap recipe discovery, and gather/save fixture target selection with SQLite cleanup error. These are outside the changed visual logic but are not all independently proven baseline failures; the PR remains draft.

The complete game-frame test at all zoom limits passed (including observational state checks). Replay completed with hash `0b369fbd04f8fab3ce6a7b295ee942ac369f000d`. A live check in the user's saved cave remains distinct from these automated and synthetic rendering checks.

---

## Source: `docs/WEATHER_ANIMATION_HANDOFF.md`

# Weather animation handoff

## Scope and behavior

- `worldseed/presentation/weather_fx.py`: world-anchored cloud shadows now drift at pixel resolution with softer layered edges; rain uses stable particle identities, continuous wind-slanted falls and expanding/fading impact rings. Rain phase no longer wraps at 16 frames.
- `worldseed/ui/pygame_terminal.py`: sample lighting targets only on a gameplay render, then interpolate presentation colors over 650 ms. Idle redraw restores an ungraded snapshot before lighting, fire glow, fog, clouds and rain. The final transition frame is painted even in clear weather; viewport borders are restored.
- Initial lighting and returning from underground snap to the current authoritative sample. Interrupted fades start from the current displayed colors.

## Contracts

No simulation, geography, discovery, visibility-radius, save-schema or persistent-field changes. No migration. Wall time drives only visual phase; weather/lighting samples stay frozen between gameplay renders. Existing `weather-art:cloud-field`, `weather-art:cloud-lobe` and `weather-art:rain` deterministic namespaces remain presentation-only. Rain particle identity no longer includes animation phase; splash position comes from the matching drop.

`draw_lighting` keeps immediate rendering by default; optional `elapsed_ms` renders the interpolated colors. `rain_surface` phase is now an unwrapped 33 ms tick.

Cloud and rain caches retain at most two full-size frames each. Synthetic cloud/rain layer cost averaged 5.7 ms at 1280x720 over 30 frames on the development host (not a complete-game FPS measurement).

## Validation

- Four new regression tests cover sub-tile cloud movement and exact camera translation, deterministic rain without the old 16-frame repeat, interrupted/completed lighting fades, and idle clear-weather fading from frozen inputs without world access.
- New tests pass on Python 3.14.2 / pygame-ce 2.5.8 and Python 3.13.5 / pygame 2.6.1.
- Compileall passed. Replay command completed: `0b369fbd04f8fab3ce6a7b295ee942ac369f000d`.
- Synthetic terrain contact sheet reviewed for day/dusk/night/dawn. A live saved-world playtest is still needed for subjective animation pacing.
- Six focused animation/cloud/idle-water tests pass on Python 3.13 (four new tests also pass on 3.14).
- Full discovery contains 326 tests. Broad parallel module runs on 3.14 and 3.13 were not clean: interpreter crashes/SystemErrors occurred in world generation, and the atlas mouse test returned `ATLAS_POI:0` where it expected `ATLAS:drag_start`. These failures are outside the modified code, but are not all proven baseline failures.
- Serial full-suite attempts were stopped before completion after the unreliable broad runs; no full-suite pass is claimed. The Python 3.13 replay module passed both determinism tests.
- Work is synchronized on a separate branch for review, not merged into main. Full clean validation and a live playtest remain release gates.

## Limitations / next dependency

Idle water animation retains its existing weather/night restrictions. This patch changes no water behavior. Rain is a viewport presentation effect and does not introduce roof occlusion or authoritative puddles. Test the effects in a playable world with movement, zoom and repeated wait actions before a release.

---

## Source: `docs/WORLD_MAP_FIX_HANDOFF.md`

# RC14 Dev5 regional map and hover fix

- Scope: `pygame_terminal.py` clears hover ownership on full-screen redraws and delegates M to `ui/region_map.py`. The map now follows the attached Dev5 handoff: 512 x 512 regional blocks, not a zoomed local exploration map. The obsolete local overview module and its unused chunk-read helpers were removed.
- Public contracts: `RegionBlockPlanner.read_prepared(rx, ry)` returns a validated in-memory or persisted plan, or None. It cannot generate, write, or populate caches. Existing `plan()` retains preparation behavior and reuses this validation. `regional_grid()` owns bounded viewport geometry in `ui/layout.py`.
- Persistence / migration: no schema, generation versions, persistent fields, or authoritative state changes. Prepared-plan payload format is unchanged.
- RNG namespaces: regional planning remains unchanged. The subsequent procedural artwork pass uses an isolated presentation RNG; see `REGIONAL_TERRAIN_ASSETS.md` for its version, namespace, bounded cache and validation.
- Tests: existing plan determinism and road symmetry; missing/corrupt prepared reads with generation forbidden; discovery filtering; hidden information; exact shared pixel endpoints; regional biome/water/road rendering; simulated hover pixel equality at 800x520, 1280x800 and 2560x1392; bounded grid geometry.
- Performance: at most 13 x 9 visible regions; one read per discovered visible plan; no local tile reads or regional generation. Temporary view data is discarded after each full render; hover does no work on this screen.
- UI exposure: dominant biome color, rugged relief, planned road/trail exits and prepared water exits, known settlements, current-region outline and player dot. Unknown regions remain opaque. Only broad terrain and known town information appears in the sidebar; latent bandit/site/wildlife data remains hidden.
- Known limitations: Dev5 stores edge connections rather than full physical corridors; the map represents those regional connections schematically. Unprepared plans stay uncharted. This pass does not implement the document's proposed Dev6 route graph, crossings, or village skeleton.
- Next dependency: Dev6 physical route corridors and crossing IDs are required before the region map can trace exact locally materialized routes.
- Visual verification: `artifacts/region-map-fixed.png` was rendered from the existing save through SQLite read-only access, with terrain and regional generation forbidden and zero database writes. This was an offscreen pygame render, not live gameplay.
- Validation: all 219 repository tests passed with pygame enabled (348.124 seconds). Compilation and golden replay passed; replay fingerprint remains `f3d99472e2e97f97dc09b4603f06d71bf20dc2a1`. Regional rendering tests also passed after adding explicit road/water pixel assertions. The compact 800x520 fixture was visually inspected for sidebar and legend fit.

---

## Source: `RC14_BASELINE_RC13.md`

# RC14 Phase 0 — Frozen RC13 Baseline

Baseline archive: `WORLDSEED v1.0 RC13 - Seeded World Preparation`.

This file freezes the RC13 reference before the Embodied World architecture changes. It is intentionally based on worldgen v4 / resourcegen v3; RC14 Phase 2 hydrology remains observational so these terrain fingerprints must continue to match until Phase 3 deliberately promotes new-world geography to v5.

## Golden seeds

The fingerprint is BLAKE2b-128 over terrain content IDs for the 3×3 surface chunk square centered on chunk `(0,0)`, iterated chunk rows `-1..1`, then local chunk array order. Personalization string: `WS-RC13-BASE`.

| Seed | RC13 v4 terrain fingerprint |
|---|---|
| rc14-golden-00 | `6d36ad680a8672589485deea15faa001` |
| rc14-golden-01 | `d4a87ae513f76f135f1c508d2697e75e` |
| rc14-golden-02 | `b429b73f991db55f65e023e36ea934c3` |
| rc14-golden-03 | `d4a87ae513f76f135f1c508d2697e75e` |
| rc14-golden-04 | `1f6c7dd3253896314e08d69c62c484a0` |
| rc14-golden-05 | `d1b7b0ed88a03ec0bd74c25aadd1154d` |
| rc14-golden-06 | `d4a87ae513f76f135f1c508d2697e75e` |
| rc14-golden-07 | `5f92a259c9def3d9688054d7bf67a137` |
| rc14-golden-08 | `dcdcd19ce3e378068fd83acadbe3ed60` |
| rc14-golden-09 | `125c9cce4f0d2afd248f4b1fefb6d6c3` |

## Baseline versions

- save schema: 3
- worldgen: 4
- resourcegen: 3
- RC13 automated tests collected in this archive: 176

## Baseline performance in this handoff environment

- `tools/bench_worldgen.py`: 100 chunks in 1.851 s, ~18.51 ms/chunk
- `tools/bench_movement.py`: 400 warm-cache steps, ~0.387 ms movement and ~3.372 ms movement + 100×30 render

The original RC13 report records startup preparation at roughly 20–25 seconds for the radius-8 / 17×17 opening envelope on its validation machine. Cross-machine wall-clock numbers are observational; deterministic fingerprints and invariants are the compatibility gate.

---

## Source: `RC14_DEV10_HANDOFF.md`

# WORLDSEED RC14 Embodied World Dev10 handoff

This bounded work unit focused on **shoreline quality** and **water-context differentiation**. The request was to make coastlines prettier and clearly distinguish:
- river beds
- shorelines
- river edges / banks
- freshwater shallow vs deep
- ocean shallow vs deep
- mixed water where fresh and ocean meet

## Summary
Dev10 keeps the world/sim terrain IDs authoritative, but upgrades the **presentation layer** so water and adjacent terrain render differently based on context. This avoids risky simulation churn while making the map read much more like a natural world.

## Delivered

### 1) Context-sensitive water tile families
Added new contextual presentation terrain families with **10 variants each**:
- `render:ocean_deep`
- `render:ocean_shallow`
- `render:estuary_mix`
- `render:freshwater_deep`
- `render:freshwater_shallow`

These are render-only terrain visuals stored in `visuals.json` and resolved by the pygame local renderer.

### 2) New water art assets
Created `tools/build_contextual_water_assets.py` to generate new runtime tileable water materials.

Visual intent:
- **ocean deep**: darker blue open water
- **ocean shallow**: brighter shallower coastal water with sandy undertones
- **estuary mix**: greener/brackish transitional water where river and ocean meet
- **freshwater deep**: cooler inland channel water
- **freshwater shallow**: lighter water with visible bed hints for shallows / riverbed feel

Preview artifact:
- `artifacts/contextual-water-preview.png`

### 3) Context-aware water display selection
Updated `worldseed/presentation/local_terrain.py` with presentation helpers:
- `contextual_display_id(...)`
- `edge_overlay_kind(...)`
- `edge_overlay_signature(...)`

Rules now used by the renderer:
- `core:river_shallow` -> freshwater shallow visuals
- `core:river` -> freshwater deep visuals
- `core:water` next to land -> ocean shallow visuals
- `core:water` next to river -> estuary mix visuals
- `core:water` surrounded by water -> ocean deep visuals

### 4) Prettier coasts and riverbanks
Updated `worldseed/ui/pygame_terminal.py` to apply directional **edge overlays** after terrain composition.

Overlay types include:
- `water_ocean_shore`
- `water_estuary`
- `water_river_edge`
- `land_beach`
- `land_shore`
- `land_rock_shore`
- `land_riverbank_bare`
- `land_riverbank_soft`

This gives better visual separation between:
- open water edge vs bank edge
- beach vs grassy shoreline vs rocky shoreline
- ocean shore vs river bank
- water-body edge vs interior water tile

### 5) Existing blending retained
Dev9's terrain blending remains in place, but Dev10 now layers context-specific shoreline/bank presentation on top of it instead of treating all water contacts the same.

## Validation
Focused regression pass completed successfully:
- `tests/test_contextual_water_rendering.py`
- `tests/test_terrain_variants.py`
- `tests/test_local_terrain_transitions.py`
- `tests/test_asset_readability.py`
- `tests/test_rc8_visuals.py`
- `tests/test_region_map.py`
- `tests/test_regional_terrain_assets.py`
- `tests/test_rc12_renderer.py`
- `tests/test_rc14_world_presentation.py`

Result:
- **31 passed**
- **7 skipped**
- **40 subtests passed**

## Changed files
Primary files changed this work unit:
- `tools/build_contextual_water_assets.py`
- `worldseed/presentation/local_terrain.py`
- `worldseed/ui/pygame_terminal.py`
- `tests/test_contextual_water_rendering.py`
- regenerated `worldseed/assets/visuals.json`
- regenerated water-related terrain assets under `worldseed/assets/sprites/terrain/`
- regenerated atlases under `worldseed/assets/atlases/`

## Suggested next work unit
The best next short pass would be one of:
1. tune the shoreline overlays against a live gameplay screenshot so the effect is stronger/weaker where needed
2. add dedicated muddy-bank / reed-bank overlays for wetlands and floodplains
3. if simulation expansion is desired later, introduce explicit sim terrain IDs for estuary / coast shallows rather than only presentation-layer distinctions

---

## Source: `RC14_DEV11_HANDOFF.md`

# WORLDSEED RC14 Embodied World Dev11 handoff

This bounded work unit focused on two follow-up visual issues from Dev10:
1. **floodplains looked too grassy / strange near water**
2. **water looked too static**

## Summary
Dev11 retunes floodplain terrain so it reads more like **silty, sandy river-adjacent ground**, and adds a lightweight **animated water shimmer overlay** so rivers, shallows, estuaries, and ocean water no longer feel completely still.

## Delivered

### 1) Floodplain retune: sandier / more alluvial
Updated `tools/build_terrain_variant_set.py` for `core:floodplain`.

Changes:
- shifted the floodplain palette away from grassy green and toward **sandy alluvial silt**
- reduced dense grass-blade decoration
- added subtle sand/silt ripple language and damp patch variation
- kept the texture seamless and compatible with Dev8/Dev9's 10-variant terrain system

Result:
- floodplain now sits visually closer to sand and river margins
- it reads better as a transitional terrain near water rather than ordinary grassland

### 2) Water-material tuning
Updated `tools/build_contextual_water_assets.py`.

Changes:
- made shallow and mixed water a bit sandier / bed-driven
- improved differentiation in:
  - `render:freshwater_shallow`
  - `render:freshwater_deep`
  - `render:ocean_shallow`
  - `render:ocean_deep`
  - `render:estuary_mix`
- increased visible current / ripple language in the generated tile art

### 3) Animated water motion overlay
Updated `worldseed/ui/pygame_terminal.py`.

Added a lightweight cached presentation overlay:
- `_animated_water_overlay(display_id, tile_px, phase)`

Behavior:
- only applies to contextual water display IDs
- phase is derived from the in-game clock for subtle motion variation
- adds moving shimmer / current lines over water tiles during rendering
- does **not** change simulation data or terrain IDs

This keeps the world-authoritative terrain system intact while making water feel less static.

## Validation
Focused regression suite completed successfully:
- `tests/test_contextual_water_rendering.py`
- `tests/test_terrain_variants.py`
- `tests/test_local_terrain_transitions.py`
- `tests/test_asset_readability.py`
- `tests/test_rc8_visuals.py`
- `tests/test_region_map.py`
- `tests/test_regional_terrain_assets.py`
- `tests/test_rc12_renderer.py`
- `tests/test_rc14_world_presentation.py`

Result:
- **31 passed**
- **7 skipped**
- **40 subtests passed**

## Useful artifacts
- `artifacts/contextual-water-preview.png`
- `artifacts/dev11-water-floodplain-preview.png`

## Changed files
Primary files changed in this work unit:
- `tools/build_terrain_variant_set.py`
- `tools/build_contextual_water_assets.py`
- `worldseed/ui/pygame_terminal.py`
- regenerated terrain sprites under `worldseed/assets/sprites/terrain/`
- regenerated atlases under `worldseed/assets/atlases/`
- regenerated `worldseed/assets/visuals.json`

## Suggested next work unit
If you want another short visual pass after testing this build in motion, the best next step would be:
1. tune water shimmer strength from live screenshots/video
2. add special muddy-bank / reed-bank overlays for wetlands and floodplains
3. introduce optional directional river-current hints tied to neighboring river cells

---

## Source: `RC14_DEV12_HANDOFF.md`

# WORLDSEED RC14 Embodied World Dev12 handoff

This bounded work unit extends the earlier water polish with a **world-generation current field** and **directional current visuals**.

## Goals addressed
1. Add **river currents**
2. Add **ocean/coastal currents**
3. Improve the **visual readability** of moving water
4. Surface this information in both the **local view** and the **regional map**

## Summary
Dev12 introduces a deterministic current-sampling layer that reads from the existing world and hydrology authorities instead of inventing random visual motion.

- **Rivers** now expose a directional current derived from the hydrology flow graph.
- **Ocean/coastal water** now exposes a deterministic large-scale circulation field, with extra along-shore bias near coasts.
- The pygame renderer now draws **direction-aware animated water overlays** instead of generic shimmer only.
- Hover tooltips and regional planning now expose **current direction / strength** metadata.

## Delivered

### 1) Surface current model
Updated `worldseed/world/generator.py`.

Added:
- `SurfaceCurrent` read model
- `WorldGenerator.current_at(...)`
- internal helpers for:
  - `_river_current_at(...)`
  - `_ocean_current_at(...)`

Behavior:
- **River current** is derived from the RC14 hydrology flow network and river segment dominance around a queried cell.
- **Ocean current** is derived from a stable large-scale deterministic vector field with coastal alignment bias near shorelines.
- Output includes:
  - current kind
  - flow vector (`dx`, `dy`)
  - speed
  - heading label
  - strength band

### 2) World wrapper support
Updated `worldseed/world/world.py`.

Added:
- `World.current_at(...)`

This keeps current sampling accessible to presentation / planning code without making the UI a generation authority.

### 3) Regional planning now records water-current metadata
Updated `worldseed/world/region_blocks.py`.

`RegionWaterExit` now includes:
- `current_heading`
- `current_strength`
- `water_kind`

Planner changes:
- river exits now record current direction / strength
- coastal/ocean-facing edges can now be represented as water exits when a region edge has sustained ocean exposure

This is the main **world-generation/planning update** for the feature.

### 4) Local renderer: directional animated currents
Updated `worldseed/ui/pygame_terminal.py`.

Changes:
- animated water overlay now accepts current vector + speed
- current streaks now align with sampled water flow
- water motion is no longer only decorative shimmer; it now reflects generated current direction
- hover tooltips now show entries such as:
  - `River current: moderate southeast`
  - `Ocean current: gentle west`

### 5) Regional map current visualization
Updated `worldseed/ui/region_map.py`.

Changes:
- water links now draw **cyan arrow markers** showing current direction
- sidebar includes short **water current summaries** for the current region
- legend updated to explain current arrows

## Validation
Focused regression suite completed successfully:
- `tests/test_contextual_water_rendering.py`
- `tests/test_terrain_variants.py`
- `tests/test_local_terrain_transitions.py`
- `tests/test_asset_readability.py`
- `tests/test_rc8_visuals.py`
- `tests/test_region_map.py`
- `tests/test_regional_terrain_assets.py`
- `tests/test_rc12_renderer.py`
- `tests/test_rc14_world_presentation.py`
- `tests/test_rc14_region_blocks.py`
- `tests/test_rc14_environment.py`
- `tests/test_water_currents.py`

Result:
- **48 passed**
- **7 skipped**
- **40 subtests passed**

## New / updated tests
Added:
- `tests/test_water_currents.py`

This verifies:
- directional river current samples exist
- directional ocean current samples exist
- regional plans encode current metadata

## Primary changed files
- `worldseed/world/generator.py`
- `worldseed/world/world.py`
- `worldseed/world/region_blocks.py`
- `worldseed/ui/pygame_terminal.py`
- `worldseed/ui/region_map.py`
- `tests/test_water_currents.py`

## Suggested next work unit
Best next bounded follow-up after you test this build in motion:
1. give **major rivers** stronger visual hierarchy than minor streams
2. add **foam / breaker visuals** where ocean currents meet coastlines
3. optionally let fish / floating debris / boats read current direction for immersion

---

## Source: `RC14_DEV13_HANDOFF.md`

# WORLDSEED RC14 Embodied World Dev13 handoff

This bounded art pass focuses on two issues you flagged in the latest build:

1. **Water still looked too pixelated**
2. **Nettle art had a stray dark/black line artifact**

## Summary
Dev13 is a focused terrain-art and sprite-cleanup update.

### Water terrain revision
I reauthored the major water families so the surface reads as smoother, more natural, and less noisy at gameplay scale.

Updated families:
- `water_hd_v00..v09`
- `ocean_deep_hd_v00..v09`
- `ocean_shallow_hd_v00..v09`
- `estuary_mix_hd_v00..v09`
- `freshwater_deep_hd_v00..v09`
- `freshwater_shallow_hd_v00..v09`
- `river_hd_v00..v09`
- `river_shallow_hd_v00..v09`

Art changes:
- softer painterly base texture
- reduced harsh pixel-noise patterning
- smoother tonal blending
- more restrained highlight flecks
- shallow water now has gentler caustic-style variation
- river families retain some directional feel while staying visually cleaner

Fallback/base textures were also updated so non-variant reads stay consistent:
- `water_hd.png`
- `river_hd.png`
- `river_shallow_hd.png`

### Nettle sprite cleanup
Reauthored:
- `worldseed/assets/sprites/items/nettles.png`
- `worldseed/assets/sprites/resources/nettle_patch.png`

Fixes:
- removed stray dark/black artifacting
- improved silhouette readability
- clearer leaf shapes
- cleaner transparency edges

## Validation
Focused validation run:
- `tests/test_asset_readability.py`
- `tests/test_contextual_water_rendering.py`
- `tests/test_terrain_variants.py`
- `tests/test_local_terrain_transitions.py`
- `tests/test_rc8_visuals.py`
- `tests/test_rc12_renderer.py`
- `tests/test_rc14_world_presentation.py`
- `tests/test_water_currents.py`

Result:
- **32 passed**
- **40 subtests passed**

## Art preview
Generated preview artifact:
- `artifacts/dev13-water-nettle-preview.png`

## Primary changed files
- `worldseed/assets/sprites/terrain/water_hd_v00.png` ... `water_hd_v09.png`
- `worldseed/assets/sprites/terrain/ocean_deep_hd_v00.png` ... `ocean_deep_hd_v09.png`
- `worldseed/assets/sprites/terrain/ocean_shallow_hd_v00.png` ... `ocean_shallow_hd_v09.png`
- `worldseed/assets/sprites/terrain/estuary_mix_hd_v00.png` ... `estuary_mix_hd_v09.png`
- `worldseed/assets/sprites/terrain/freshwater_deep_hd_v00.png` ... `freshwater_deep_hd_v09.png`
- `worldseed/assets/sprites/terrain/freshwater_shallow_hd_v00.png` ... `freshwater_shallow_hd_v09.png`
- `worldseed/assets/sprites/terrain/river_hd_v00.png` ... `river_hd_v09.png`
- `worldseed/assets/sprites/terrain/river_shallow_hd_v00.png` ... `river_shallow_hd_v09.png`
- `worldseed/assets/sprites/terrain/water_hd.png`
- `worldseed/assets/sprites/terrain/river_hd.png`
- `worldseed/assets/sprites/terrain/river_shallow_hd.png`
- `worldseed/assets/sprites/items/nettles.png`
- `worldseed/assets/sprites/resources/nettle_patch.png`
- `CHANGELOG.md`

## Recommended next bounded work unit
If you still want the water to feel richer after testing Dev13 in motion, the best next step would be:
1. add **shore foam / breaker overlays**
2. add **river surface streak masks** for stronger flow readability
3. add **bank wetness gradients** where water meets sand / floodplain

---

## Source: `RC14_DEV14_HANDOFF.md`

# WORLDSEED RC14 Embodied World Dev14 handoff

This bounded maintenance pass fixes the reported issue where pressing **Q** appeared to crash/close the game.

## Root cause
The pygame backend used the exact same raw key token (`"q"`) for two unrelated events:

1. an actual **Q/q keyboard press**
2. the operating-system **window close** (`pygame.QUIT`) event

`worldseed/ui/router.py` then classified `q` as `Intent('quit')`.

As a result, pressing Q during gameplay did not hit an exception in the renderer or simulation. It entered the immediate quit path:

- `_save(ctx)`
- return `'quit'`
- close database
- restore terminal/window
- exit application

From the player's perspective this looked like a crash because the game disappeared immediately with no confirmation.

## Fix
### `worldseed/ui/pygame_terminal.py`
- `pygame.QUIT` now returns the dedicated token `"QUIT"` instead of `"q"`.
- This separates a real OS close request from ordinary keyboard input.

### `worldseed/ui/router.py`
- only the dedicated `"QUIT"` token maps to `Intent('quit')`.
- ordinary `q` / `Q` is now inert during gameplay.
- quitting remains available through the existing safe flow:
  - **Esc -> Pause -> Save & quit WORLDSEED**
- clicking the window close button still performs the normal save-and-quit path.

## Regression coverage
Updated tests now explicitly verify:
- `classify_key('q')` -> `none`
- `classify_key('Q')` -> `none`
- `classify_key('QUIT')` -> `quit`
- pygame's window-close handler returns `"QUIT"`, not `"q"`
- the old direct-q quit mapping is absent

## Validation
Focused validation completed:
- Python compile pass for `worldseed/`
- `tests/test_rc14_world_presentation.py`
- Q/router regression in `tests/test_ui_rc2.py`
- `tests/test_rc5_gameplay.py::RC5GameplayTests::test_mouse_and_paste_tokens_are_never_gameplay_commands`
- `tests/test_contextual_water_rendering.py`
- `tests/test_water_currents.py`
- `tests/test_asset_readability.py`

Result:
- **14 passed**
- **9 subtests passed**

## Changed files
- `worldseed/ui/pygame_terminal.py`
- `worldseed/ui/router.py`
- `tests/test_ui_rc2.py`
- `tests/test_rc14_world_presentation.py`
- `CHANGELOG.md`

No world-generation, save-schema, terrain, or simulation-state formats were changed in this maintenance pass.

---

## Source: `RC14_DEV15_HANDOFF.md`

# WORLDSEED RC14 Dev15 - physical water and swimming

Based on Dev14, including the Q-key and map-hover fixes.

## Play
Extract the ZIP into a new folder and run RUN_WORLDSEED.bat. Use a new world
for the new geography. Move normally into water to wade or swim. Choose
Swimming during character creation, or improve it by swimming. Endurance
reduces exertion. Travel light; swimming against currents costs more.

Deep water is hazardous: strokes and treading consume stamina. Below 20
stamina, entry from dry/shallow ground is refused. Exhausted swimmers can
still move toward safety, but suffer health damage. Resting in swimming
depth does not replenish stamina. Reach wading water, land or a bridge.
Menus and idle visual animation do not advance time.

## Scope and authority
- Worldgen v6 retains v4 continental/climate fields and hydrology v1 drainage.
- Shore distance is estimated from elevation relative to sea level and local
  slope. Ordered zones: wet sandy shore, coastal wading water, shallow ocean,
  shelf, deep ocean. The shelf spans multiple physical cells.
- River classes continue to come from prepared discharge/flow accumulation.
  Streams, wading margins, deeper channels, slope-driven rapids and sandy
  gravel banks materialize from that same plan. Existing fords remain.
- Lakes get freshwater shallow/deep terrain. River mouths have explicit
  brackish nearshore terrain; offshore shelf/deep water stays marine.
- No per-frame or movement drainage solving. Current lookup for swimming is
  prepared-only. River currents affect stroke cost; ocean currents do likewise.
- 12 new terrain IDs are appended; all old content indices stay in place.
- 120 new code-authored terrain textures, smooth depth transitions, restrained
  wavelets, wet shore/gravel bank materials and submerged player/wake rendering.
- Idle waves redraw only cached water rectangles clear of sprites at 6.25 Hz;
  animation is disabled on console/menu screens. No simulation time advance.

## State and compatibility
WORLDGEN_VERSION=6, HYDROLOGY_VERSION=1, SAVE_SCHEMA_VERSION=3.
All v1-v5 saves retain recorded terrain. New art and swimming apply to them;
legacy generic water retains its ambiguous fresh/salt identity. To get the
new physical ocean shelf and river/lake types, create a new world.

Swimming rules live in systems/swimming.py; command effects and vitals remain
in sim/engine.py. Existing player_skills gains swimming (0 when absent).
player_swimming_xp is one bounded optional integer, default 0 for old saves.
Successful strokes grant practice; threshold is 20 + 10 * current level,
maximum skill 10. Round-trip serialization and verifier cover the new field.
No save-schema migration is needed for this additive, defaulted field.
No new simulation RNG namespace: shelf/slope/materialization is deterministic.

## Visual and UI exposure
Terrain names and hover identify water types and wading/swimming; hover shows
estimated stroke effort. Sidebar shows Swimming and Endurance while in water.
The player appears partly submerged with a small wake. Existing character
skill screens and point-buy include Swimming. No new movement hotkeys.
Water-current render metadata is cached with a bounded 8,192-cell limit, keyed
by seed, worldgen version and prepared-domain fingerprint. This avoids stale
currents when prepared plans change.
Art source: tools/build_water_v6.py. Preview source: tools/preview_water_v6.py.
The renderer still uses cells; transitions are feathered, not a polygon mesh.
Headless 1600x900 coastal test: warm rendering improved from about 294 ms
to 74 ms after current caching; idle animation was about 2.5 ms per update.
These are container timings, not Windows GPU/frame-rate guarantees.

## Validation
See DEV15_VALIDATION.md for final results. Focused tests cover ordered coastal
zones, deterministic generation order, legacy water, material coverage,
nearshore-only estuaries, stroke/current costs, practice, exhaustion escape,
rest/wait consequences, bridge safety, blockers, state roundtrip/defaults,
verifier bounds, idle animation and menu isolation. Existing hydrology tests
exercise repeatability, cache rebuilding, prepared-domain seams and legacy
fingerprints. Real rendered previews are in artifacts/dev15-*.png.

## Limitations and next dependency
Depth is categorical rather than a meter-accurate bathymetry simulation.
Sea-level height divided by local slope approximates shelf distance; this is
not an erosion solver. Salinity is categorical, with no tidal mixing cycle.
Currents affect effort and visual flow; they do not physically displace actors.
No boats, diving or buoyant equipment are implemented. Swimming progression
currently belongs to the player, not autonomous NPC navigation. The riverbed
is represented by shallow-water material, not an independently excavatable
underwater elevation layer. Next useful work: continuous shoreline contours,
water-aware NPC pathfinding and buoyancy/equipment support.

---

## Source: `RC14_DEV16_HANDOFF.md`

# WORLDSEED RC14 Dev16 Handoff

## Scope completed

Dev16 is a coherent presentation/worldgen/crafting checkpoint built on Dev15. It addresses four connected player-facing gaps without introducing a second simulation authority:

1. **Data-driven terrain meshing.** `worldseed/presentation/local_terrain.py` now configures blendable ground from the live terrain registry. Any current or future/modded terrain tagged `surface` or `underground` participates automatically unless it is a hard feature (`shaft`, `ore`, `loot`). Grassland and floodplain are explicitly the same visual family and now use a wide, low-alpha ecotone instead of a staircase boundary. Water/shore edge overlays also query the dynamic ground catalog rather than a frozen land list.
2. **Worldgen-v7 caves.** `worldseed/world/caves.py` owns terrain-aware natural entrance selection, reciprocal depth spans, protected landing chambers, vertically correlated cave topology, depth bands and stratified wall resources. `WORLDGEN_VERSION=7`. v1-v6 generation code paths are preserved. Surface cave mouths remain authoritative terrain, not renderer decorations.
3. **Discovery crafting.** New worlds enable persisted material/recipe discovery. Handling an item type records material knowledge on the authoritative simulation path. Simple techniques unlock automatically; compound techniques become trial-and-error experiments once all clue materials have been handled. Experimenting consumes time and records the recipe but creates no output. The discovery tree is derived from real recipe inputs/outputs rather than maintained as a contradictory second graph.
4. **Graphical retained UI.** `ui/widgets.py` now hands structured menu/document data to pygame when the backend supports it. `PygameTerminal.present_menu()` and `present_document()` draw cards, tab bars, badges, breadcrumbs and footer controls. Inventory and crafting get dedicated tab vocabulary while the terminal backend keeps the same ASCII widgets and keyboard parity. UI code remains observational.

## Cave/geology contract

`CaveGeneratorV7` divides natural underground geography into readable depth bands:

- depth 1-2: shallow caverns / weathered limestone; coal, aquifer, some copper potential
- depth 3-5: sedimentary caves; coal, aquifer, copper and early iron
- depth 6-9: deep fracture caves / metamorphic rock; copper + increasing iron
- depth 10+: deep crystalline caves; iron-dominant, no shallow coal/copper placement

Natural cavities become much rarer below the modeled band, while player excavation remains possible through sparse world deltas. Aquifers use a broad moisture-influenced field, coal uses seam/ridge structure, copper uses clustered mid-depth fields, and iron thresholds relax with depth. Copper now has a complete content chain: `core:copper_vein -> core:copper_ore -> core:copper_ingot`, including metallurgy handling and visuals.

Natural entrance candidates are sampled within deterministic 36x36 macro-cells. Candidate score is dominated by local relief and upland elevation; deterministic jitter only resolves otherwise similar sites. This removes the old visual impression of cave holes appearing as arbitrary flat-world dots.

## Cave presentation

Eight v7 cave-mouth sprites are transparent overlays. The pygame renderer selects the most common neighboring blendable land material as a presentation-only base and composites the rock opening above it. This lets the same authoritative cave-mouth terrain inherit grass, floodplain, sand, rock, etc. visually without changing world data. New wall/iron/coal/aquifer/copper cave textures are also included.

Asset build script: `tools/build_caves_v7.py`.

## Crafting discovery rules

Persisted fields in `LivingWorldState`:

- `player_crafting_discovery_enabled`
- `player_discovered_items`
- `player_discovered_recipes`
- `player_crafting_experiments`

Compatibility rule: old saves leave discovery disabled and retain the legacy visible-recipe behavior. New worlds enable it.

Authoritative mutation points:

- `CraftingSystem.sync_discoveries()` is called on initialization/command paths after inventory changes.
- `ExperimentRecipeCommand` is dispatched through `Simulation` and advances time.
- Crafting/query screens call only read methods (`discovered_recipes`, `researchable_recipes`, `discovery_tree_rows`, `discovery_requirements`). Opening the UI cannot unlock anything.

Default discovery behavior is data-driven:

- recipe with knowledge requirement -> knowledge-gated
- recipe with <=1 clue input -> auto discovery after that material/item type is handled
- recipe with >1 clue input -> trial-and-error experiment after every clue type has been handled
- future recipes may override with `discovery_items` and `discovery_mode` in JSON

This naturally creates an early chain: stone reveals simple stone processing, brush/bark reveals cordage, branches reveal primitive one-material tools, and crafted/handled components expose compound tool experiments.

## UI architecture

The existing `select_menu` and `view_text` widgets remain the navigation authority. If the active terminal object implements the graphical presentation hooks, widgets pass structured rows to those hooks; otherwise they render the existing responsive text panel. Therefore menu behavior, retained selection, ESC/back semantics and commands are shared rather than forked.

Crafting tabs: Recipes / Experiment / Materials / Tech Tree / Designs.
Inventory tabs: Pack / Items / Storage / Equipment / Read.

The pygame dependency is not available inside this execution sandbox, so the graphical methods were compile-validated and their shared widget/fake-terminal navigation path was regression tested, but a live SDL screenshot could not be captured here. The Windows launcher still installs/uses the repository's existing `pygame-ce` dependency.

## Versioning

- `ENGINE_VERSION = 1.0.0-rc14-dev16`
- `WORLDGEN_VERSION = 7`
- `HYDROLOGY_VERSION = 1`
- save schema remains 3; the new crafting fields are additive/defaulted
- project package version `1.0.0rc14.dev16`

v7 deliberately retains v6 climate/hydrology/coast fields; the worldgen bump is for natural cave geography. Existing worldgen v1-v6 saves use their recorded generator version, so cave entrances do not move underneath old characters/bases.

## Validation

See `DEV16_VALIDATION.md`. Key deterministic audits are in:

- `artifacts/dev16-terrain-meshing-audit.txt`
- `artifacts/dev16-cave-audit.txt`
- `artifacts/dev16-cave-mouth-variants.png`

The terrain audit validates 30 blendable terrain IDs and 435 pair profiles, including grass/floodplain. The cave audit on the frozen Dev16 audit seed reports 27 entrances across 11x11 cave macro-cells, reciprocal depths 3-10, and the expected shallow-to-deep ore stratification.

## Continuation recommendations

1. Run the graphical client on Windows/pygame-ce and visually inspect inventory/crafting at 800x520, 1280x800 and a large desktop resolution; adjust card density only in presentation code.
2. Continue the RC15 interaction path by adding mouse hit targets/context menus to the same structured widget model instead of bypassing commands.
3. If future cave gameplay needs branching vertical passages beyond same-cell descend/ascend, add stable cave route/entrance-plan IDs rather than re-rolling local tunnels on load.
4. Keep expanding recipe discovery through JSON `discovery_items`/`discovery_mode`; do not maintain a separate hard-coded technology tree.
5. Profile the terrain transition cache on a pygame-capable machine after adding many mod terrains. The catalog itself is configured only when the registry token changes, not each frame.

---

## Source: `RC14_DEV17_HANDOFF.md`

# WORLDSEED RC14 Dev17 — Asset Integration / Character Appearance Pass

## What changed
- Imported the new generated art into the project tree through `tools/import_dev17_generated_assets.py`.
- Added **10 male** and **10 female** selectable player sprites under `worldseed/assets/sprites/player/`.
- Added **12 new grounded NPC variants** and wired them into the presentation manifest.
- Added broader **cave floor**, **cave wall**, and **cave entrance** variant pools.
- Replaced the core **coal**, **copper ore**, and **iron ore** item art from the new ore atlas.
- Updated animal/monster presentation so key species prefer the new grounded wildlife/monster art first.
- Added `player_sex` and `player_sprite_index` to `LivingWorldState` save data.
- Added survivor creation flow support for:
  - character name
  - sex selection
  - appearance selection (10 looks per sex)
- Updated the pygame renderer to draw the selected player sprite in-world.
- Added `requirements-pygame-ce.txt` and kept `requirements.txt` aligned with `pygame-ce`.
- Bumped the build marker to **`1.0.0-rc14-dev17`**.

## Validation
- `PYTHONPATH=. pytest -q tests/test_player_appearance.py tests/test_asset_readability.py`
  - **5 passed, 4 subtests passed**
- `python -m compileall -q worldseed tools/import_dev17_generated_assets.py`
- `VisualRegistry.coverage_issues(...)` returned **0 issues**.

## Important notes
- The new appearance selection is currently menu-driven in the startup flow; it is functional and persistent.
- Imported source sheets remain in `/mnt/data` for this workspace run, while the game-ready extracted assets are now committed inside the project tree.
- `tools/import_dev17_generated_assets.py` can be rerun if you want to regenerate the cropped in-game asset files from the source sheets.

---

## Source: `RC14_DEV18_HANDOFF.md`

# WORLDSEED RC14 Dev18 — Graphical Survivor Appearance Picker

## This pass focused on
Adding a true graphical character appearance preview screen so players can visually choose from the new male/female survivor sprite sets instead of picking from a plain text list.

## Implemented
- Added a new startup helper: `_appearance_menu(term)` in `worldseed/ui/startup.py`.
- Added a pygame-native visual picker: `PygameTerminal.present_sprite_gallery(...)`.
- The new picker now:
  - shows a graphical gallery of the survivor sprites
  - supports **male/female toggling** on the same screen
  - shows **10 looks per sex**
  - highlights the currently selected sprite
  - shows a larger preview card for the active selection
  - lets the user navigate with **arrows or WASD**
  - confirms with **Enter/Space** and backs out with **Esc**
- Kept the old text-menu path as a fallback for non-pygame terminals.
- Updated the startup wizard to use the new combined appearance selection flow.
- Bumped build version to `1.0.0-rc14-dev18`.

## Controls on the new screen
- `Left / Right / A / D` → move across appearance choices
- `Up / Down / W / S` → move between rows
- `Tab` (also `Q` / `E`) → toggle Male / Female set
- `Enter` or `Space` → confirm
- `Esc` → back

## Validation
- `PYTHONPATH=. pytest -q tests/test_player_appearance.py tests/test_asset_readability.py`
  - **5 passed, 4 subtests passed**
- `python -m compileall -q worldseed tools/import_dev17_generated_assets.py`

## Notes
- Save persistence for `player_sex` and `player_sprite_index` remains intact from Dev17.
- The visual gallery is presentation-only and does not change the build/point-buy logic.
- The fallback text selection path is retained to preserve compatibility with the ANSI terminal backend.

---

## Source: `RC14_DEV19_HANDOFF.md`

# WORLDSEED RC14 Dev19 — Graphical Inventory & Discovery Crafting UI

## Scope completed

Dev19 redesigns the pygame inventory and crafting interfaces around the actual game systems instead of presenting terminal-style text inside a window. The ANSI terminal path remains available and retains the same navigation/command authority.

### Inventory

- New **Pack dashboard** with the selected player sprite, total carried mass, estimated volume, stack/item counts, category distribution, and graphical section cards.
- New **Items grid** with real item sprites, stack counts, carried mass, pagination, and a selected-item preview pane.
- New **Item action screen** with a large item preview plus context actions such as inspect, drop, eat, equip, and store.
- New **graphical item detail view** using the real item sprite, pack statistics, description, uses, tags, and legacy detail text as a secondary information area.
- Storage/equipment/read actions still route through their existing authoritative gameplay systems; the redesign is presentation-only.

### Crafting

- New **Discovery Workbench dashboard** showing recipe discovery progress, ready experiments, examined materials, experiments completed, and crafting skill.
- New **recipe category cards** instead of plain text category rows.
- New **graphical recipe browser** with output sprites, READY/NEEDS state, result summaries, time, selected-recipe description, material counts, station, and skill information.
- New **recipe detail / craft confirmation screen** with output art and full material requirements.
- New **trial-and-error experiment browser** that reuses the graphical recipe presentation while highlighting material-clue discovery and experiment time.
- New **Material Discoveries grid** showing the actual sprites of handled material/item types.
- New **Discovery Tech Tree renderer**. It derives dependency depth from the real recipe graph, lays recipes into tier columns, draws visible parent/child connectors, and color-codes known / experiment-ready / locked states.
- New **Component Design browser** and graphical material-choice screen for modular sword, pick, helmet, and future data-defined component designs.

## Architecture

`ui/widgets.py` now supports optional structured presentation hooks:

- `presentation`
- `presentation_data`

The same `select_menu()` / `view_text()` widgets still own keyboard navigation, paging, ESC semantics, and terminal fallback. Pygame receives only observational structured data through `present_feature_menu()` / `present_feature_document()`.

The simulation remains authoritative. Browsing inventory, recipes, materials, or the tech tree does not advance time, discover recipes, consume items, or realize world state.

## Versioning

- Engine: `1.0.0-rc14-dev19`
- Package: `1.0.0rc14.dev19`
- Worldgen remains **7**. No geography/save-schema bump was required.

## Validation

Validated in this workspace:

- `python -m compileall -q worldseed`
- `tests/test_dev19_feature_ui.py`
- `tests/test_player_appearance.py`
- `tests/test_asset_readability.py`
- `tests/test_rc14_world_presentation.py`
- `tests/test_rc12_renderer.py`
- targeted inventory retained-navigation flows
- `tests/test_dev16_caves_crafting.py`

Combined targeted result before packaging: **24 tests passed** plus asset-readability subtests.

A live pygame screenshot could not be captured in this sandbox because pygame-ce is not installed and the environment cannot reach PyPI. The build already declares `pygame-ce` in both `requirements.txt` and `requirements-pygame-ce.txt` for the Windows/runtime environment.

---

## Source: `RC14_DEV20_HANDOFF.md`

# Dev20 — clean survivor art and crafting crash repair

Scope: pygame feature renderers, character atlas import, visual manifest, graphical regression tests.

Root cause: Dev19 introduced ten calls passing a positional scale to the keyword-only `_draw_item_icon(..., *, scale=...)` helper. Recipe inputs, recipe details, experiments, component designs, the tech tree and inventory details could raise TypeError. Reproduced using real SDL rendering and fixed all ten callers with `scale=`. No broad exception swallowing or changes to crafting rules.

Art: 20 selectable appearances (10 male / 10 female), 24 NPC variations from an authored RGBA atlas. Consistent front-facing stance, adult proportions, clothing silhouettes and baseline. Sprites are 160x256 RGBA with 240px figure height. Manifest references connect the artwork to both the picker and world actors. Character images use cached smooth scaling; preview is vertically centered. Existing sex/index saves continue to select the corresponding new artwork.

Source: artifacts/source-art/dev20_survivors.png. Reimport with `python tools/import_dev20_characters.py` (pygame-ce). Generated with the built-in image tool. Prompt: professional clean hand-painted grounded wilderness RPG adult survivors, varied skin tones/hair/practical clothing, consistent full-body front-facing pose, isolated silhouettes and transparent background. Final extraction source retained generated alpha. Atlas delivered 24 figures in 6x4; explicit cell bounds preserve complete silhouettes.

Public contracts: unchanged. Persistent fields, schema and worldgen versions: unchanged. RNG: none introduced. Performance: scaled images remain cached; 24 bounded NPC alternatives. UI browsing remains observational.

Tests: real pygame regression covers home/categories/recipes/experiments/details/designs/components/materials/tree and inventory home/items/actions/details; verifies simulation and inventory unchanged. Alpha/canvas checks cover all 20 player sprites. Existing persistence and navigation tests retained.

Also repaired a pre-existing new-game NameError: `_load_context(sel)` referenced undefined `selection` for appearance. Reads now use `sel` with defaults for legacy tuple callers; regression verifies female/index 8.

Limitations: static character sprites, not directional walk-cycle animation. SDL dummy-driver verification does not replace a Windows desktop playthrough. See DEV20_VALIDATION.md for exact outcomes and broader-suite findings.

---

## Source: `RC14_DEV21_HANDOFF.md`

# Dev21 — Mouse-driven controls

Scope: shared widgets, pygame input/presentation, pointer target helper, startup controls, regional-map close control, HUD route definitions, bounded targeting and app close/save handling.

Controls:
- WASD moves the character in the world only. It cannot change menu selection or activate a menu action.
- Ten persistent HUD buttons: Inventory, Crafting, Build, Health, Map, Actions, World, Look, Help, Pause. World and Actions expose the remaining systems; Pause contains save/quit and access to the console.
- Menu cards activate on left-click. Hover selects without activation. Wheel and Previous/Next page lists; Back, right-click or Escape returns. Arrow/Enter navigation and numeric shortcuts remain optional.
- Wheel zooms only in world mode. UI/text/target modes never change world zoom.
- Appearance tabs/cards, character point-buy +/- controls, talents and confirmation buttons are clickable. Names/seeds still use keyboard text entry; WASD letters are accepted normally there.
- Direction prompts are clickable menus. Look, gather and hunting target modes accept map tile clicks and Confirm/Cancel buttons, with existing range/discovery limits preserved.

Contracts: `ui/router.py` owns HUD shortcut mappings. `ui/pointer.py` owns transient screen-space hit regions, mode changes, button rendering and page capacity; no simulation mutations occur there. Shared widgets interpret page-relative UI_SELECT/UI_HOVER tokens and retain selected route state. Hit targets rebuild every frame and invalidate on resize. Backend page capacity prevents invisible selectable cards. Static decorative tabs were replaced by location labels so they no longer appear to be dead buttons.

Safety: entering a modal screen or losing window focus clears held movement. Window close inside UI raises a typed request to the app boundary, which saves the active world and closes its database. Startup window close exits cleanly. Rendering/hover/scroll are observational.

Look detail also used an undefined width variable; it now derives width from the active display.

Persistence/RNG: no new persistent fields, migrations, generation versions or RNG streams. No new runtime dependencies beyond the existing pygame-ce.

Validation: see DEV21_VALIDATION.md and artifacts/dev21_* logs/screenshots. Tests cover actual SDL mouse events, exact hit selection, hover-only behavior, paging/selection retention, small-window bounds, stale targets after resize, typing, mouse creation controls, nested crafting/inventory routes, held-key clearing and modal close/save.

Limitations: keyboard text entry remains required for names/seeds; terminal fallback uses arrows/Enter/Escape. Existing gameplay/recipe discovery rules and static art remain unchanged. The old zero-supply bootstrap harness still bypasses normal discovery and attempts a locked recipe.

---

## Source: `RC14_DEV22_HANDOFF.md`

# Dev22 — authoritative terrain atlas

## Scope and root cause

The old gameplay region map converted a regional biome summary into decorative
terrain art and joined river exits to region centers. Those pictures were not
the local terrain. The graphical Map route now uses `world/atlas.py` and
`ui/atlas_map.py`, projecting actual stored/local tiles. The former schematic
renderer is retained only as a compatibility/tooling helper, not used by gameplay.

## Controls and presentation

- Map HUD button / M opens a 512-cell-wide surface atlas around the player.
- Mouse wheel or Zoom buttons select 128, 256, 512, 1024 or 2048-cell views.
- Click pan buttons or use arrows; Center returns to the player. WASD is unchanged.
- Click terrain to inspect its exact cell ID/name/coordinates; click POIs or their
  list entries for names, location and type. The list is pageable. Overlapping
  icon buckets suppress visual clutter without dropping list records.
- Back, right-click, Esc, M or Enter closes. Resize preserves center/zoom.
- Small and large window screenshots and a reproducible QA preview script are
  included. Preview settlements are explicitly labeled synthetic fixtures;
  their terrain comes from the real v7 generator.

## Authority and public API

`read_atlas(sim, center=None, span=512)` returns a bounded `AtlasSnapshot` with
chunk terrain and known `AtlasMarker` records. `terrain_at(x,y)` is exact for
available surface cells. Negative coordinates use the same floor division as
local chunks. Source priority: loaded local chunk, otherwise version-matching
stored base plus saved deltas, then current dirty edits.

No atlas read loads/generates chunks, advances time, realizes settlements,
invokes hydrology, changes LRU ordering, writes the database, or advances simulation RNG.
One paused UI snapshot/raster is cached per map session and replaced on pan/zoom;
opening the map again refreshes live state. Maximum span 2048 bounds chunk probes
to 65 x 65 and the render raster to 512 x 512. At distant zoom, cell colors are
area-averaged; terrain inspection still reads exact cells.

Known settlement records provide village/city markers (population >=1000 is a
presentation size class, not a newly simulated city). Camps are existing known
campfires/shelters, grouped per 8-cell block. Cave icons require a discovered
surface cave tile. Historical site archetypes are read from known site records;
underground markers explicitly show depth and approximate chunk-center location,
not an invented surface entrance. No POI exists merely because art was supplied.

## Persistence, compatibility and limits

Save schema stays 3, worldgen stays 7, no new simulation fields or RNG namespaces.
Versions 1–7 read their own tiles without migrating geography. Generated chunks
are now retained in the existing rebuildable database cache when first locally
materialized, before authoritative terrain deltas are applied. This prevents
explored coverage from disappearing after LRU eviction. Normal save/commit owns
durability; inspection never writes. Cache growth follows generated/explored space.

Uncharted regions and unavailable/deleted base caches remain dark. The atlas does
not fabricate a full region from a few samples or regenerate an old save on open.
Revisiting missing terrain through normal play restores coverage. This is an
honest partial survey, not a claim that every possible infinite seed is exhaustively
tested or that all ungenerated regions are visible. Roads are not drawn as fake
straight-line connections; a future overlay should consume authoritative route
geometry. Underground floor mapping remains a future feature; this is a surface
atlas with known underground-site projections. Terminal mode retains its report.

Future/modded terrain IDs use the registry tags and a visible fallback color;
all surface core terrain IDs have explicit palette coverage in atlas_styles.json.
The full suite also exposed an existing catalog-dependent ruin-wall blending
inconsistency. The dynamic catalog now excludes authored ruin masonry from
terrain feathering, matching the existing hard-edge tests.

## Art

Nine new built-in image-generation POI illustrations are packaged in
`worldseed/assets/atlas_poi.png`, with a data-driven 3x3 layout in
`worldseed/assets/atlas_styles.json`. The renderer slices and alpha-trims cells
at load time; no Pillow or other runtime dependency was added.

Generation prompt: a transparent-background square atlas, exactly nine isolated
icons in an equally spaced 3x3 grid: village (three timber thatched cottages),
walled city (slate roofs inside stone walls), camp (canvas tents and fire), cave
(natural rocky arch), ruined fortress, temple, timber mine mouth with pickaxe,
ancient archive with scroll emblem, crypt mausoleum. Cohesive professional
hand-painted cartographic miniatures, elevated three-quarter view, readable at
32 pixels, moss green/ochre/ivory/slate/brown, top-left lighting, fine dark contour,
large cell padding, no labels, grid lines, lettering, scenery or framing,
genuine transparent alpha. Asset creation used the built-in image tool.

## Validation

See `DEV22_VALIDATION.md` and artifacts/dev22_* test logs. Includes seed/version
tile identity, negative coordinates, discovery filtering, generated-cache reload,
delta precedence, observational checks, mod fallback, real SDL clicks/hover,
paging/zoom/pan/inspection and narrow/large window coverage.

---

## Source: `RC14_DEV4_HANDOFF.md`

# WORLDSEED RC14 Dev4 — Phase 4 handoff

## Scope and outcome

Continues the supplied RC14 Embodied World Dev3 source. Phase 4 environmental derived fields are complete. Phase 5 settlement suitability/placement is next. This remains a development checkpoint, not final RC14.

### Player-facing changes

- Look (`L`) now describes natural fertility, wetness, drainage, slope, relief, flood risk and land/resource potential when survival or naturalism is at least 4.
- Graphical camera uses an odd, centered tile grid at every zoom level. This removes the half-tile displacement that occurred with even viewport dimensions.
- The footer wraps all control hints within the 800×520 minimum window and constrains long event text to its own panel.
- Dev3 startup Escape suppression and Dev2 resource decluttering are retained and verified. This update does not add ground clutter.

### Code fix

`HydrologyGenerator.load_or_generate(..., persist=True)` now stores an already-cached in-memory plan. Dev3 returned early on a memory-cache hit and silently ignored that persistence request. The extracted cached-plan reader also verifies that payload coordinates match the requested domain.

## APIs and ownership

- `World.environment_at(WorldPos)` / `WorldGenerator.environment_at(WorldPos)` return immutable `EnvironmentalFields` or `None`.
- `EnvironmentalFields`: `slope`, `relief`, `soil_fertility`, `wetness`, `drainage`, `flood_risk`, `farmland`, `open_water`, `version`, and `resources`.
- `ResourceOpportunity`: `forage`, `timber`, `stone`, `freshwater`; `resource_opportunity` exposes a weighted summary. These are habitat/site scores, not guaranteed pickups, stock quantities, mineral deposits, or crop yields.
- `HydrologyGenerator.cached_domain(...)` loads an existing memory/SQLite plan only. `surface_at(..., prepared_only=True)` refuses a missing plan instead of solving regional drainage.
- Environmental reads never call chunk realization, settlement planning, RNG streams, or simulation mutation. A v5 area without prepared hydrology returns `None`; underground locations also return `None`.
- All indices use integer 0–100 game scales. Slope is **not degrees**, relief is **not meters**, and flood risk is a relative geographical index, not a calibrated annual probability.

## Derivation contract

Environmental version 1 uses centered elevation differences at ±8 cells for slope and a ±32-cell cross-shaped stencil for relief. All samples use absolute world coordinates, including negative coordinates. Depression, moisture, local relief and hydrology wetland/floodplain strength determine drainage and wetness. Natural fertility incorporates the existing climate fertility, alluvial influence, steepness, exposed high terrain and moisture extremes.

Farming potential combines fertility with slope, flood and temperature penalties. Forage/timber potential uses fertility, moisture, climate and exposed terrain; stone potential uses elevation and relief. Freshwater opportunity comes from hydrology water access and excludes the original ocean. Open water gets zero farmland, forage, timber and surface stone opportunity.

Look reports **natural** conditions. Mutable farm N/P/K, construction, player terrain edits and fluid simulation retain their existing owners. These base scores do not override that state.

## Compatibility, persistence and performance

- Engine: `1.0.0-rc14-dev4`; environmental model: `ENVIRONMENT_VERSION = 1`.
- Worldgen stays **5**; hydrology stays **1**; resourcegen stays **3**; save schema stays **3**.
- Continental/climate fields still use the approved v4 contract. Terrain, river geometry and resource placement are unchanged by environmental reads.
- Existing v1–v4 worlds sample their recorded generator fields with no v5 river influence. No geography migration is performed.
- Environmental data is a rebuildable 8,192-entry LRU per generator, keyed by version, coordinates and prepared hydrology fingerprint. It is not persisted and adds no save growth. A changed hydrology fingerprint cannot reuse stale environmental samples.
- No new random namespace or stateful RNG consumption.
- Three-seed audit measured approximately 0.27–0.30 ms per cold environmental-plus-terrain sample and 1.0–1.4 microseconds per cached environmental read on this Linux environment. These are observations, not hardware guarantees.

## Validation

- Full existing suite before final additions: **192 passed**.
- Full suite including environmental tests and initial graphical/UI additions: **208 passed**, 258.076 seconds.
- The subsequent footer correction and extra regression test passed the complete graphical behavior suite: **5/5**. The final source therefore contains **209 distinct tests**; the 208-test full run predates that final footer-only test.
- `python -m compileall -q worldseed tools/audit_environment.py`: passed.
- `tools/replay.py tests/fixtures/golden_replay.json`: `8bdc2f5783cab3ff8d48fc590b704480772a79b2`.
- Representative generated/saved game: `tools/verify_save.py` reports **Save integrity: OK**.
- Three-seed environmental audit: **12,288 samples**, four prepared domains per seed, **zero issues**. Maps and JSON reports are in `artifacts/phase4/`.
- Ten-seed traversability audit: **zero adjacent blocker pairs**, minimum walkable retention **0.903114186851211**, minimum connectivity **0.9995742869306088**.
- SDL dummy-display behavior checks cover stale Escape removal, fresh input, preserved window-close events, wheel limits/reset, zoom/resize rendering, exact camera centering, simulation observation, and footer containment. Actual rendered 1280×800 and 800×520 frames were visually inspected.
- Native Windows interactive play was not available in this environment.

Final clean extracted archive: compile check passed and all **31 RC14 tests passed** in 10.763 seconds. The log is in `artifacts/validation/clean_archive.txt`; other gate logs are alongside it.

## Modules and tooling changed

- New `worldseed/world/environmental_fields.py`.
- Updated `worldseed/world/{generator,world,hydrology}.py`.
- Updated `worldseed/ui/{screens,layout,pygame_terminal}.py`.
- Updated version constants/package metadata and release/roadmap documentation.
- New `tests/test_rc14_environment.py`, `tests/test_rc14_pygame_behavior.py`; updated `tests/test_ui_rc2.py`.
- New `tools/audit_environment.py` (standard library only). Re-run with:

```bash
python tools/audit_environment.py
python -m unittest discover -s tests -v
python tools/audit_traversability.py --seeds 10 --json
```

## Next dependency and known limits

Phase 5 must use these fields for causal settlement suitability, with stable plans linked to existing simulation settlements. Preserve existing settlement anchors until an explicit migration policy exists. Do not create a second decorative/economic settlement authority.

Background preparation at distant exploration margins remains Phase 11 work. The new environmental path never generates missing hydrology; pre-existing terrain/crossing fallback paths still can. Extending the prepared hydrology window can require a broader watershed solution and needs an explicit stability policy. Dev4 preserves Dev3's algorithm and does not claim to solve that frontier problem.

Resource/farming weights are initial game-design indices. Regional scoring and physical settlement footprints need Phase 5 integration and calibration; no settlements are moved or newly placed by this checkpoint.

---

## Source: `RC14_DEV5_HANDOFF.md`

# WORLDSEED RC14 Dev5 Handoff

Status: **development checkpoint — responsive movement + regional block architecture + Phase 5 settlement-siting foundation**. This is not the final RC14 release.

## Why this checkpoint exists

Dev4 completed deterministic environmental read models. Dev5 uses those fields to begin the next architecture layer while also fixing the held-movement latency/overshoot reported during normal play.

The governing contract remains:

**simulation state -> regional plan -> local materialization**

Regional blocks are generated planning data. They do not own a second population, economy, inventory, NPC list, or mutable settlement reality.

## 1. Held movement / latency fix

`worldseed/ui/pygame_terminal.py` no longer relies on pygame/SDL key repeat for gameplay movement.

- pygame key repeat is disabled;
- `KEYDOWN` and `KEYUP` are both tracked;
- held movement uses an explicit active-key state;
- initial delay: 165 ms;
- repeat interval: 72 ms;
- duplicate OS-generated `KEYDOWN` events for an already-held movement key are ignored;
- a slow frame never generates catch-up movement for intervals that were missed;
- release events clear the held direction before another synthetic repeat can be emitted;
- pending-input cleanup clears held state plus queued key-down/key-up events.

This prevents the former failure mode where many repeated movement events accumulated while rendering and were replayed after the player released the key.

### Renderer work paired with the input fix

The local pygame renderer now keeps a scrollable base-layer state. A normal one-tile camera move can shift the previous terrain surface and redraw only the newly exposed strip plus newly discovered cells instead of rebuilding the entire viewport.

Natural-resource presentation is also cached by **absolute world cell + resource revision/day state**, so moving the camera one cell reuses almost every resource projection rather than rebuilding a viewport-keyed result.

## 2. Regional world-block architecture

New module: `worldseed/world/region_blocks.py`

A strategic region is exactly:

`REGION_SIZE = CHUNK_SIZE * REGION_CHUNKS = 32 * 16 = 512 world cells`

`RegionBlockPlan` is reconstructable generated data containing:

- stable region UID / x / y / plan version;
- dominant biome and sampled biome mix;
- mean elevation, moisture, temperature and relief;
- settlement presence under the existing settlement-presence RNG contract;
- a deterministic settlement anchor, suitability score and archetype;
- coarse control potential (`settled`, `bandit_frontier`, `wild`);
- small wilderness-character tags;
- latent historical/site potential;
- symmetric regional road/trail exits;
- water exits read only from already-prepared authoritative RC14 hydrology;
- canonical fingerprint.

Plans are cached through the existing generated-regional-plan persistence table. They are safe to rebuild from seed/version. They do not replace authoritative state or physical-plan deltas.

## 3. Settlement siting

For settlement-bearing regions, Dev5 no longer chooses an unrelated random x/y anchor when a regional planner is active.

The planner samples a deterministic 6×6 candidate lattice with deterministic jitter and scores candidates from the approved RC14 environmental fields when available:

- soil fertility;
- farmland potential;
- freshwater opportunity;
- timber opportunity;
- stone opportunity;
- slope;
- flood risk;
- broad temperature suitability.

It selects an archetype from the same conditions (`river_market`, `agrarian`, `mining`, `forest`, `fishing`, `frontier`). Candidate evaluation is bounded instead of scanning every one of the 262,144 cells in a region.

Settlement anchors keep at least **64 cells of margin** from every regional boundary. A village/town block therefore remains mostly wilderness/farms/forest/other surrounding terrain instead of becoming a fully urban tile.

Important compatibility detail: Dev5 uses the exact same `derive_seed(..., "settlement-presence", rx, ry)` presence roll as `ProceduralSocietyGenerator`. A regression test verifies that the regional plan and the society generator agree on both settlement presence and anchor.

## 4. Roads and water on the strategic map

### Roads / trails

Regional road exits use a canonical unordered pair of adjacent region coordinates. Both neighboring blocks therefore derive:

- the same connection existence;
- the same edge offset;
- the same road class.

Road probability is higher when one or both endpoints contain settlements. This creates a sparse connected-looking strategic substrate without an all-to-all graph.

This is **not yet the final RC14 route system**. The next route phase must convert selected strategic connections into persistent terrain-aware corridors, crossings and route IDs using the existing hydrology/cost architecture.

### Rivers / waterways

The block planner never invents decorative river data. It only records water exits found in **prepared authoritative hydrology**. If hydrology for an area is not prepared, the strategic plan leaves the water exit unknown instead of generating an alternate river reality.

## 5. Directional region entry

WORLDSEED keeps continuous absolute local coordinates, so no teleport is needed at a block boundary.

`entry_side(old_x, old_y, new_x, new_y)` makes the contract explicit:

- move south -> enter destination from **north**;
- move north -> enter from **south**;
- move east -> enter from **west**;
- move west -> enter from **east**.

The movement log reports the destination region and entry side on a surface-region boundary crossing. Because the player position remains continuous, their exact boundary offset is naturally preserved.

## 6. Graphical region map

`M` on the pygame client opens `present_region_map()`.

The map intentionally remains quiet:

- unknown regions stay opaque;
- discovered regions show broad biome color and subtle relief only;
- prepared rivers/waterways are blue;
- roads/trails are gold;
- only known settlements are marked;
- hidden site/bandit/wildlife potential is not exposed;
- the current player region is highlighted;
- current-region details are limited to broad terrain character and already-known settlement information.

Road and water lines use their stable 0..511 edge offsets so adjacent region lines meet at the same boundary point instead of every line terminating at edge center.

## 7. Simulation integration

`Simulation` creates one `RegionBlockPlanner` and passes it to `ProceduralSocietyGenerator`.

On coarse nearby-world realization, regional plans are prepared before settlement society state is realized. Existing settlement/economy/NPC systems remain authoritative.

Normal movement within the same 512×512 region does not rerun nearby settlement/region realization. The existing region-boundary coarse-refresh rule remains in place.

## 8. Validation completed for Dev5

Compilation:

- `python -m compileall -q worldseed tools tests` — PASS

Focused regression set after the Dev5 changes:

- RC10 worldgen/input source contracts
- RC12 renderer contracts
- RC13 pregeneration
- RC14 environmental fields
- RC14 hydrology
- RC14 regional blocks
- RC14 world presentation
- living-world determinism/state
- persistence

Final focused result after all Dev5 changes: **49 tests passed in 22.04 s**, including the society/planner settlement-presence + anchor agreement test.

The pygame behavioral suite is present but is skipped on the build machine because pygame-ce is not installed there. The source compiles and the architecture-level input tests remain intact.

A complete repository-wide suite was attempted earlier in this work session but exceeded the 420-second execution window. The one source-contract failure observed before timeout was fixed and its test now passes. Dev5 therefore records the focused green gates above instead of claiming a full-suite pass.

## 9. Next work unit

Keep the next chat/work unit bounded. Recommended Dev6 scope:

1. replace probabilistic adjacency-road edges with the full sparse settlement route graph (candidate graph + connectivity backbone + limited redundant edges);
2. rasterize selected edges into terrain-aware persistent route corridors;
3. derive stable ford/bridge candidates from authoritative hydrology;
4. render those exact route corridors locally and on the region map;
5. begin the settlement skeleton: access road -> common -> functional seeds -> parcels -> footprints;
6. add plan/ledger consistency audits before advancing to settlement life.

Do not begin RC17 schedules/NPC life until the RC14 physical settlement plan exists.

---

## Source: `RC14_DEV6_HANDOFF.md`

# WORLDSEED RC14 Embodied World Dev6 handoff

This work unit stayed focused on one bounded art/presentation pass so it can be wrapped safely inside the user's preferred ~25 minute execution window.

## Delivered

### 1) Regional world-map terrain transitions
- `worldseed/presentation/regional_terrain.py`
  - bumped asset presentation version to `2`
  - added directional biome-transition support using neighboring prepared region plans
  - blends now support **north, south, east, west** plus **all four corners**
  - keeps determinism and never invents local geography beyond already-public neighboring region summaries
  - added internal caches for generated base terrain surfaces and transition masks
- `worldseed/ui/region_map.py`
  - now passes surrounding region plans into `RegionalTerrainAssets.surface(...)`
  - result: discovered map regions read as one connected landscape instead of isolated square swatches

### 2) Resource / loot sprite integration
- Added reproducible import script: `tools/import_generated_worldseed_assets.py`
- Rebuilt / replaced common resource and ground-loot visuals from the generated prompt sheets.
- Updated trees / flora / gatherables including:
  - `oak_tree`, `pine_tree`, `birch_tree`, `willow_tree`
  - `fallen_branches`, `surface_boulder`, `loose_stone`, `clay_bank`
  - `blueberry_bush`, `raspberry_cane`, `cattail_bed`, `reed_bed`
  - `yarrow_patch`, `plantain_patch`, `nettle_patch`, `dandelion_patch`
  - `wild_carrot_patch`, `wild_onion_patch`, `wild_grain_patch`
  - `bolete_patch`, `morel_patch`
- Updated common item / pile icons including:
  - `stout_branch`, `brush`, `wood`, `bark`, `stone`, `stone_flake`, `clay_lump`, `iron_ore`
  - `fiber`, `plant_cordage`, `berries`, `raspberries`, `blueberries`
  - `bolete`, `morel`, `bone`, `feather`
  - `hide`, `rawhide`, `fresh_hide`, `scraped_hide`
  - `wild_grain`, `yarrow`, `medicinal_herb`, `nettles`, `dandelion_greens`, `plantain_leaf`, `wild_onion`
- Rebuilt atlases with `tools/build_sprite_atlases.py`

## Validation
Focused regression pass completed:
- `tests/test_rc8_visuals.py`
- `tests/test_region_map.py`
- `tests/test_regional_terrain_assets.py`
- `tests/test_rc12_renderer.py`
- `tests/test_rc14_world_presentation.py`

Result: **16 passed, 7 skipped**

## Notes
- Pygame is optional in this environment, so the pygame-gated tests remained skipped, but the source-level and non-pygame contract coverage passed.
- The new world-map blending is presentation-only and does **not** change save schema, region generation, or strategic road/water authority.
- The import script makes the new art pass reproducible if later sheets are regenerated.

## Suggested next work unit
Keep the next chunk similarly bounded:
1. render-side preview / validation in a pygame-enabled environment
2. tune any sprites that read too similarly at small zoom
3. optionally add local-map terrain autotiling if you want the *playfield* terrain itself to blend directionally the same way the region map now does

---

## Source: `RC14_DEV7_HANDOFF.md`

# WORLDSEED RC14 Embodied World Dev7 handoff

This bounded work unit continues the visual pass from Dev6 while keeping gameplay/world authority unchanged.

## Delivered

### 1) Local-world terrain autotiling
- Added `worldseed/presentation/local_terrain.py`.
- Natural surface terrain now blends using all **8 directions**:
  - north / south / east / west
  - northwest / northeast / southwest / southeast
- Only discovered neighbors participate, so terrain blending cannot reveal fogged geography.
- Hard authored features such as ruin walls, shafts, ore veins and special terrain keep crisp edges.
- Related visual families such as river/water and grass/floodplain avoid unnecessary blur.
- The renderer caches composed transition tiles and transition masks.
- Scrolling still reuses the old terrain surface; only cells whose visible neighbor relationship changed are redrawn.

### 2) High-detail local terrain textures
The generated terrain atlas is now actually used by the local renderer instead of remaining reference art only.

Replaced / added high-detail textures for:
- grass
- forest
- scrub
- sand
- rock
- tundra/snow
- wetland
- water
- river
- shallow river
- floodplain
- tilled soil

Terrain uses smooth downsampling while resource/item sprites retain crisp scaling.

### 3) Ground-object readability cleanup
The Dev6 generated resource/loot sprites received another differentiation pass.

Notable cleanup:
- fixed tinting so transparent PNGs no longer gain colored rectangular backgrounds
- strawberry, raspberry and blueberry resources now read separately
- yarrow, nettles, dandelions, wild carrots, wild onions and wild grain have separate silhouettes/palette cues
- bolete and morel patches/items are visually differentiated
- willow was given a different silhouette/proportion from oak
- medicinal herb, nettles, yarrow and dandelion greens use distinct color treatment

### 4) Reproducible source art
Generated source sheets are included under:
- `artifacts/source-art/worldseed_terrain_texture_atlas.png`
- `artifacts/source-art/top_down_forest_asset_sprite_sheet.png`
- `artifacts/source-art/hand_painted_rpg_loot_sprite_sheet.png`

Import tools now use these project-relative assets:
- `tools/import_generated_terrain_textures.py`
- `tools/import_generated_worldseed_assets.py`

### 5) Validation
Final focused/broader regression set:

**66 passed + 4 subtests passed**

Coverage included persistence, living-world state, RC10 worldgen, RC12 renderer contracts, RC13 pregeneration, RC14 environment/hydrology/region blocks/world presentation, local autotile rules, visual asset coverage, and asset-readability checks.

Pygame runtime remains optional in this Linux build environment, so pygame-gated behavioral tests are not claimed here. The renderer source compiles and the non-pygame integration contracts pass.

## Preview
`artifacts/dev7-local-autotile-preview.png` shows one local terrain tile receiving eight different directional neighbor transitions using the same mask logic as the renderer.

## Suggested next bounded work unit
1. test the finished local renderer on a Windows pygame runtime and capture representative gameplay screenshots
2. tune transition depth if any terrain boundary reads too soft at 16px or too abrupt at 56px zoom
3. then return to physical roads / river banks / settlement-local materialization rather than continuing indefinite art-only work

---

## Source: `RC14_DEV8_HANDOFF.md`

# WORLDSEED RC14 Embodied World Dev8 handoff

This work unit focused on the terrain tiling complaint from the live screenshot: repeated single-texture cells, especially sand, still read like wallpaper. The goal was to stay within one bounded session and deliver a directly playable improvement.

## Research direction applied
Modern tile workflows generally combine two ideas:
1. **terrain-aware transitions / autotiling** so boundaries pick the correct connecting edge/corner treatment
2. **alternative tiles / weighted variants** so one terrain does not repeat the exact same image on every cell

WORLDSEED already had presentation-only 8-direction local blending from Dev7. Dev8 adds the second half: deterministic multi-variant terrain sets.

## Delivered

### 1) Ten-variant terrain sets for repeating surface terrain
Added a reproducible generator script:
- `tools/build_terrain_variant_set.py`

The script now builds **10 authored runtime variants** for each of these repeat-heavy terrain types:
- `core:grass`
- `core:forest`
- `core:scrub`
- `core:sand`
- `core:rock`
- `core:tundra`
- `core:wetland`
- `core:water`
- `core:river`
- `core:river_shallow`
- `core:floodplain`
- `core:tilled_soil`
- `core:cave_floor`
- `core:berry_thicket`

Each set uses the same base material language but introduces deterministic internal variation (tone, mottling, ripples, clumps, pebbles, etc.) so the world stops reading as a repeated single tile.

### 2) Visual manifest updated for alternative terrain tiles
- `worldseed/assets/visuals.json`
  - common natural terrains now map to **lists of 10 files**, not a single texture

### 3) Renderer integration
- `worldseed/ui/pygame_terminal.py`
  - added `_terrain_variant_index(...)`
  - terrain tiles now choose a **stable per-cell variant** based on terrain ID + world coordinates
  - transition-composition cache key now includes the actual selected neighbor paths, so edge-blended tiles do not accidentally reuse the wrong composed variant

This means:
- same world seed => same terrain tile choices
- no runtime flicker
- more visual variety without affecting simulation or save format

### 4) Atlases / artifacts
- rebuilt atlases with `tools/build_sprite_atlases.py`
- added preview artifact:
  - `artifacts/terrain-variant-preview.png`

## Validation
Focused regression pass completed:
- `tests/test_terrain_variants.py`
- `tests/test_asset_readability.py`
- `tests/test_local_terrain_transitions.py`
- `tests/test_rc8_visuals.py`
- `tests/test_region_map.py`
- `tests/test_regional_terrain_assets.py`
- `tests/test_rc12_renderer.py`
- `tests/test_rc14_world_presentation.py`

Result:
- **27 passed**
- **7 skipped**
- **35 subtests passed**

## Notes / limits
- This is a strong improvement over a single repeated tile, but it is still a lightweight runtime approach.
- A future higher-end step would be a true **terrain-set / Wang / blob tile** system for same-terrain internal edge motifs as well, especially if you want hand-authored micro-transitions within the same terrain family.
- Hard authored terrain features (ruin walls, seams, shafts, caches, etc.) were intentionally left as bespoke single-purpose tiles.

## Suggested next work unit
1. run the build in a pygame-enabled environment and visually tune any terrain whose 10 variants are still too subtle
2. add **weighted probabilities** so a few calmer base variants appear more often than the noisier ones
3. if desired, move toward a **47-tile blob / mixed terrain set** for the most common surfaces

---

## Source: `RC14_DEV9_HANDOFF.md`

# WORLDSEED RC14 Embodied World Dev9 handoff

This bounded work unit focused on **terrain realism and blending quality** after Dev8's first alternative-tile pass. The goal was to make repeated terrain read more like connected natural ground instead of visible wallpaper while keeping the renderer presentation-only.

## Summary
Dev9 replaces the main repeating surface materials with **new seamless terrain art assets** generated specifically for runtime tiling, then tunes the local renderer's blend behavior so different materials meet more naturally.

## Delivered

### 1) New seamless terrain material pass
Reworked `tools/build_terrain_variant_set.py` into a proper terrain material generator.

It now creates fresh seamless/tileable material art for the main natural terrains instead of only lightly modifying the prior texture files.

Terrains covered:
- `core:grass`
- `core:forest`
- `core:scrub`
- `core:sand`
- `core:rock`
- `core:tundra`
- `core:wetland`
- `core:water`
- `core:river`
- `core:river_shallow`
- `core:floodplain`
- `core:tilled_soil`
- `core:cave_floor`
- `core:berry_thicket`

For each terrain, the generator now produces:
- an updated primary base texture (for compatibility / inspection)
- **10 deterministic variants** used by the renderer

Visual goals of the new assets:
- remove obvious tile-edge repetition
- keep material language readable at small in-game tile sizes
- give each terrain a more realistic ground feel
- maintain enough shared palette structure for cross-terrain blending

### 2) Blend-profile tuning for more natural transitions
Updated `worldseed/presentation/local_terrain.py` and `worldseed/ui/pygame_terminal.py`.

Added terrain-aware transition tuning via `transition_profile(center_id, neighbor_id)`.

This means local presentation blends are no longer one-size-fits-all:
- **shorelines** (water/sand, water/wetland) use wider and stronger blends
- **soil/surface transitions** use medium blends
- **rock/cave contacts** stay tighter and crisper
- same-family materials still remain crisp to avoid muddy blur

### 3) Stable per-cell terrain variation retained
Kept Dev8's deterministic per-cell terrain variant selection so there is still:
- no flicker
- same look for the same world coordinates
- significantly less visible repetition on large surfaces

### 4) Atlases and artifacts refreshed
Rebuilt atlases and generated updated visual QA artifacts:
- `artifacts/terrain-variant-preview.png`
- `artifacts/terrain-tiling-preview.png`

`terrain-tiling-preview.png` is especially useful because it shows repeated copies of the new material tiles, making seam issues easy to inspect.

## Validation
Focused regression suite completed successfully:
- `tests/test_terrain_variants.py`
- `tests/test_asset_readability.py`
- `tests/test_local_terrain_transitions.py`
- `tests/test_rc8_visuals.py`
- `tests/test_region_map.py`
- `tests/test_regional_terrain_assets.py`
- `tests/test_rc12_renderer.py`
- `tests/test_rc14_world_presentation.py`

Result:
- **28 passed**
- **7 skipped**
- **35 subtests passed**

## Changed files
Primary files changed in this work unit:
- `tools/build_terrain_variant_set.py`
- `worldseed/presentation/local_terrain.py`
- `worldseed/ui/pygame_terminal.py`
- `tests/test_local_terrain_transitions.py`
- `tests/test_terrain_variants.py`
- regenerated terrain sprites under `worldseed/assets/sprites/terrain/`
- regenerated atlases under `worldseed/assets/atlases/`
- updated `worldseed/assets/visuals.json`

## Suggested next work unit
If you want another short pass, the next best visual improvement would be:
1. render a live gameplay screenshot from the Dev9 build and tune any terrain that still reads too flat in motion
2. add a small number of **edge-detail overlays** (shore foam, grassy fringe, muddy banks) for the most common transition pairs
3. optionally add **weighted terrain variants** so calm base textures appear more often than noisier alternates

---

## Source: `RC14_EMBODIED_WORLD_PROGRESS.md`

# RC14 Embodied World — Development Progress

Status: **development checkpoint / Dev5 regional block architecture and Phase 5 settlement-siting foundation complete**. This is not the final RC14 release.

## Phase 0 — baseline freeze

- Ten deterministic RC13 golden seeds remain the compatibility baseline.
- Legacy worldgen v4 terrain fingerprints are retained as regression contracts.
- Existing save/version boundaries remain loadable and must not be rewritten into new geography.

## Phase 1 — data contracts and versions

RC14 generator contracts remain independent:

- `HYDROLOGY_VERSION = 1`
- `SETTLEMENT_PLAN_VERSION = 1`
- `ROUTEGEN_VERSION = 1`
- stable regional physical-plan dataclasses/IDs in `worldseed/world/regional_plan.py`
- rebuildable SQLite generated caches for hydrology/regional/settlement/route plans
- authoritative `physical_plan_deltas` for mutations that must survive cache deletion/rebuild

## Phase 2 — hydrology prototype

`worldseed/world/hydrology.py` provides the deterministic causal drainage layer:

- 16-cell hydrology lattice;
- 64×64 core-node domains with 8-node halos;
- Priority-Flood-style depression handling;
- deterministic D8 flow and flat drainage;
- climate/moisture-derived runoff and accumulation;
- watershed IDs and river classes;
- floodplain strength and canonical fingerprints;
- generated-cache persistence plus invariant audits.

`tools/audit_hydrology.py` and `tools/bench_hydrology.py` remain available for isolated-domain debugging and profiling.

## Phase 3 — worldgen v5 physical geography

New worlds now use **`WORLDGEN_VERSION = 5`**. Existing v1-v4 saves continue using their recorded generator and are not retroactively given RC14 rivers.

### Seam-safe prepared hydrology

Dev2 identified that separately solved adjacent Priority-Flood domains could disagree in their overlapping halos. Dev3 resolves that for prepared regions by solving every hydrology domain required by the prepared envelope inside **one larger drainage lattice**, then slicing the result back into per-domain cache records. `audit_window_seams()` validates shared elevation, filled elevation, accumulation, watershed, river class, floodplain and flow information across the overlap.

The startup prepared envelope therefore receives one coherent watershed solution rather than independent per-chunk or per-domain river rolls.

### Physical projection

Worldgen v5 projects the hydrology plan into actual surface geography:

- deterministic meandering stream/river centerlines refined from the coarse lattice;
- `core:river_shallow` for minor streams, ford segments and shallow banks;
- `core:river` for deep medium/major channel cores;
- contiguous lake basins from interpolated depression fill depth rather than repeated circular node stamps;
- `core:wetland` and `core:floodplain` environmental overlays;
- game-readable `river_width`, `river_depth_class`, `wetland_probability`, `water_access_score`, `flood_risk` and `crossing_cost` read values;
- deterministic ford candidates on qualifying river segments.

The v5 generator intentionally reuses the approved v4 continental/climate field contract so the version bump changes physical hydrology rather than needlessly rerolling every broad biome. Underground generation remains unchanged.

### Startup/pregeneration integration

For v5 worlds, startup now:

1. selects a viable candidate region using cheap base geography;
2. resolves the complete prepared-envelope watershed plan;
3. attaches the prepared hydrology projection;
4. relocates the exact spawn locally if new physical water made the preliminary cell invalid;
5. carves/persists v5 terrain chunks;
6. prepares resources on the resulting physical geography.

This keeps regional hydrology work in the deliberate loading phase rather than normal opening movement/rendering.

### Terrain/content compatibility

The content registry now defines shallow river, deep river, wetland and floodplain terrains. Suitable existing natural resources were extended onto wetland/floodplain terrain so RC14 geography does not create sterile green zones. Existing sprites are reused as safe presentation fallbacks until the parallel art track adds dedicated bank/wetland/floodplain transitions.

## Dev2 world readability retained

- Ambient loose ground-resource coverage remains reduced so collectible items form readable pockets rather than carpeting the map.
- Structural trees/boulders retain their independent biome budget.
- Local camera remains centered on the player.
- Mouse wheel and `+`/`-` zoom the local view; `0` resets zoom.

The earlier 129×129 tuning sample reduced non-structural ambient ground resources from 7.57% to 4.04%, while structural scenery remained 1.68%.

## Dev3 startup-input fix

The pygame loading screen could leave startup key-repeat events queued long enough for gameplay to receive a stale `ESC`, immediately opening the pause menu. The loading-to-game transition now:

- clears queued `KEYDOWN` events;
- temporarily disables pygame key repeat;
- re-enables normal repeat on the first fresh gameplay key press.

This also prevents a held confirmation key from accidentally opening the Action Hub as soon as the world appears.

## Validation performed

Focused RC8/RC10/RC12/RC13/RC14 renderer, worldgen, pregeneration, hydrology and presentation suite: **36 passed** after Phase 3 integration.

Additional RC14 startup/hydrology contract run: **16 passed** after the held-key suppression hardening.

Ten-seed traversability audit passed with:

- `adjacent_blocker_pairs = 0`
- minimum resource connectivity ≈ `0.99957`
- minimum walkable retention ≈ `0.90311`
- maximum blocker occupancy ≈ `0.09689`

`tools/audit_phase3_geography.py --seed rc14-golden-00 --radius 192` inspected 147,456 surface cells across four prepared hydrology domains with **zero seam issues**. Physical RC14 hydrology occupied about **6.34%** of the inspected cells. The current preview contains contiguous lake shapes, branching rivers, floodplains and wetlands without the earlier node-circle/polka-dot lake artifact.

Current single-chunk pregeneration benchmark on this environment:

- fresh first terrain tile: about 208 ms (includes hydrology preparation/cache setup for an unprepared v5 area)
- prepared first terrain tile: about 0.31 ms
- fresh 1,024-cell resource chunk: about 26 ms
- prepared 1,024-cell resource chunk: about 3.19 ms

These are development measurements, not final release budgets.

A full repository-wide pytest run is not claimed for this checkpoint; the complete suite is substantially slower under v5 and exceeded the available long-run validation window without exposing a failure. Focused regression suites and required Phase-3 audits above are green.

## Phase 4 — Environmental derived fields (Dev4)

`worldseed/world/environmental_fields.py` derives immutable, 0–100 game indices for slope, relief, natural soil fertility, wetness, drainage, flood risk, farming suitability and resource opportunity. Resource potential separates forage, timber, stone and freshwater. The sampler uses the approved elevation/climate fields and prepared hydrology; it never solves regional drainage, creates settlements, or changes terrain/resource placement.

An 8,192-entry LRU is keyed by environmental version, generator version, hydrology fingerprint and absolute coordinates. It is reconstructable and writes no persistent state. Missing v5 hydrology produces an unavailable result rather than an invented dry-land score. Existing v1–v4 worlds retain their original fields and no new river influence; underground samples are deliberately unsupported.

Look mode shows natural ground signs at survival/naturalism 4+. Dynamic farm N/P/K and player changes remain with their existing simulation owners. `tools/audit_environment.py` writes exact environmental maps and machine-readable checks. See `RC14_DEV4_HANDOFF.md` for the validation record and formulas.

## Dev5 — Regional blocks and settlement-siting foundation

`worldseed/world/region_blocks.py` adds a deterministic 512×512 strategic block plan over the existing unbounded world. Blocks summarize broad landscape character, environmental settlement suitability, sparse symmetric road/trail exits and prepared authoritative water exits without duplicating simulation state. Settlement presence remains under the existing RNG contract, while settlement x/y now comes from a bounded deterministic suitability search using Phase-4 environmental fields. A regression test verifies planner/society presence and anchor agreement.

The pygame client now exposes a discovery-gated regional map that shows broad terrain, prepared waterways, road/trail connections and known settlements without revealing latent bandit/site/wildlife potential. Exact road/water edge offsets are used so neighboring regions meet at the same map boundary point. Cardinal boundary crossing keeps continuous coordinates and explicitly reports the side from which the destination was entered.

Dev5 also replaces pygame/SDL key-repeat movement with explicit key-down/key-up held-state pacing. Slow render frames no longer create a catch-up queue of movement intents. The terrain base layer can scroll-reuse a one-cell camera move and resource presentation is cached by absolute world cell.

## Next dependency

**Phase 6/7 — strategic route graph and terrain-aware route corridors.** Dev5's regional road exits are a strategic substrate, not final physical roads. The next work unit should build the sparse settlement graph/connectivity backbone, rasterize selected edges through terrain/hydrology cost, create stable crossings, and then feed those exact corridors to local materialization.

After route corridors are authoritative, continue Phase 8 with the settlement skeleton (access road/common, functional anchors, parcels and footprints). Existing saves must not relocate already-realized settlements.

Phase 11 still needs quiet-time/background planning for exploration-ring expansion. Dev5 does not make normal same-region movement generate regional plans, but crossing into a new coarse region can still realize the next nearby ring synchronously through the existing coarse-world refresh. That frontier preparation path should be moved out of latency-sensitive input before RC14 release.
