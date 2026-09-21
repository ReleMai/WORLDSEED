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
