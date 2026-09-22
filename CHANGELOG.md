## RC14 Dev34 — Coast v2, continuous forest floor and measured performance

- Finish Phase-5 physical mouth projection: discharge/shelter-driven estuaries, connected delta distributaries, shallow deposits, sediment-fed barriers and lagoon pockets. Existing coast-v0/v1 saves retain their geography.
- Replace repeated forest cells with a world-anchored continuous litter/moss material; keep pine/morel/cloud artwork intact.
- Cache immutable geological hashes/samples, avoid cached-sprite disk stats and irrelevant land-neighbor reads, reuse rain identities, reduce large-screen cloud compositing cost.
- Correct obsolete validation fixtures (offshore resource searches, no-op corruption, stale discovery cache, bootstrap discovery bypass). Assertions remain active.
- Add mouth/seam/cache/version tests, real multi-seed audit, visual comparison and local-play benchmark. Details and validation limits: DEV34_VALIDATION.md.

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
