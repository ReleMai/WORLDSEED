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
