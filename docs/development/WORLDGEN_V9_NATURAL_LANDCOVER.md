# WORLDGEN v9: natural terrestrial land cover

New worlds now pin `worldgen_version=9`. Existing saves keep their recorded
version; opening a v8 database does not migrate its terrain or other generation
contracts. A new world is required to exercise the new cover classification.

`worldseed/world/surface_v9.py` classifies terrestrial habitat using the existing
v8 geological elevation, physical temperature/precipitation, fertility and
topographic exposure. The elevation, climate, drainage, coastline and cave
solvers are unchanged. Wet sheltered hollows favor woodland; exposed slopes
favor meadow or rocky upland. Cold/dry habitat remains tundra/scrub. All output
terrain IDs already have passable ground, resource habitats and visual coverage.

Broad, smoothly interpolated grove/clearing fields give the ecotones connected
shapes. A small domain warp bends their margins. These fields only modulate
cover suitability: they cannot move water, rivers, mountains, cave mouths or
roads, and they do not become an independent rainfall authority. There is no
per-cell biome coin flip. The technique follows the continuous multiscale and
domain-warping approaches described by [Red Blob Games](https://www.redblobgames.com/maps/terrain-from-noise/)
and [de Carpentier](https://www.decarpentier.nl/scape-procedural-extensions),
applied here to cover over WORLDSEED's existing physical fields.

Absolute world coordinates, including negative coordinates, determine every
sample. Habitat topography is interpolated from a 16-cell lattice with at most
8192 cached nodes; existing noise/geology caches retain their existing limits.
Cache contents and query/chunk generation order do not determine outputs.
Sampling does not realize world regions or write persistence. Rendering should
consume prepared terrain snapshots, not invoke this sampler.

Projection priority remains cave mouth -> prepared coast/ocean -> terrestrial
cover -> prepared hydrology override -> stable site/settlement/route projection.
Natural resource identity and depletion remain owned by the resource system.
No new persistent fields, schema migration, resourcegen version, hydrology
version, coast version, route version or settlement-plan version are introduced.

Focused tests freeze a pre-change v8 surface/physical-fields SHA256 over 81
positive/negative coordinates, preserve v7 field snapshots, reopen pinned v8
saves, and round-trip new v9 metadata. Twelve seeds check unchanged physical
sources and absolute-coordinate/cache/order independence. Separate checks cover
actual adjacent negative/positive chunk materialization, connected ecotones,
physical habitat response, protected water/coast/cave priorities, passability
and existing resource habitat coverage. Primitive-production audit outcomes are
recorded in the associated engine/graphics handoff.

This phase improves cover arrangement; it does not replace geology with a new
height generator or claim complete world-generation validation. Hydrology,
civilization/route hardening and native GPU visual/performance acceptance retain
their existing release gates.

## Development validation

- 37 distinct focused tests passed: 18 surface/version/compatibility checks and
  19 direct hydrology/cache/coast/topography checks. Compileall and whitespace
  checks passed. These do not constitute the complete release suite.
- Twelve actual production `_load_context(..., prepare_world=False)` starts,
  seeds `rc7-balance-0` through `rc7-balance-11`, began with empty inventories.
  Within radius 14 they had 27–49 stone features, 19–80 branch features,
  19–65 fiber features, 7–79 trees and 7–59 edible features. Nine additional
  breadth-first checks (seeds 3–11) found all three primitive materials on
  reachable cells and 756–818 walkable cells out of the 841-cell window.
  No new starter supplies were added. This is a bounded resource/start audit,
  not full startup pre-generation or water-survival acceptance.
- `balance_early_game.py --seeds 3 --json` passed in 98.5 seconds under a
  180-second bound. Two additional production-start batches passed in 62.9 and
  128.1 seconds under separate 180-second bounds.
- The required `bootstrap_smoke.py --seeds 3` was attempted and failed on its
  first seed: the existing tool treats the discovery ingredient token
  `tag:binding_material` as a literal harvest item. An explicit-v8 baseline
  reproduced the identical failure. Both reached stone/branch/brush collection,
  stone-flake and cordage production before the tool failed at the knife
  discovery helper. Full bootstrap is therefore **not** claimed as passing.
- A natural scene source is seed `natural-v9-0` (hex
  `6e61747572616c2d76392d30`), center `(-448, 832, 0)`: direct physical
  `terrain_at` reads in its 25×17 window returned 168 forest and 257 grass cells,
  with no fixture painting. Prepare the world before capturing it in the GPU
  renderer; rendering must not generate the source terrain.
