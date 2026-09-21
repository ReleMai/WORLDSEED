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
