# WORLDSEED — Homestead & Solitary Survival Development Pass

**Status:** Design + isolated tested prototype. **Not integrated into the playable client.**

The current `BuildingSystem.place` only places one cell of `StructureInstance`, with `RoofState` tracked separately. Existing `ResourceSystem.harvest` handles tree-tool checks, yields, depletion and regrowth. `InteriorSystem.rearrange` moves furniture within a saved interior, but does not implement full player-built house placement, furniture packing, and pickup. The settlement plan / interior systems already provide stable multi-tile building shells and collision but are not yet connected to player construction.

## Five player-built residences

| Family ID | Home | Tile footprint | Walls | Roof |
|---|---|---|---|---|
| `log_cabin` | Primitive Log Cabin | 3x3 | Logs and clay chinking | Thatch |
| `timber_cottage` | Timber-Framed Cottage | 4x3 | Timber/wattle | Shingles |
| `stone_cottage` | Stone Cottage | 4x4 | Stone/mortar | Slate |
| `longhouse` | Frontier Longhouse | 5x4 | Heavy timber | Shingles |
| `fortified_homestead` | Fortified Homestead | 6x5 | Masonry | Slate |

An explicit numbered art catalog supplies 10 selectable styles per home (50 stable style IDs). Prototype supply totals and image file names are authored in `worldseed/data/homestead_catalog_v1.json`. The image paths are *targets for assets*, not claims that the images have been installed in the game. A separate first-pass art generator/source package is available from the development handoff, but its placeholder exteriors need more artistic variation before replacement-quality release.

## Survival loop and commands

1. Fell a tree via the existing `ResourceSystem.harvest` authority; retain axe prerequisites, item yields, stump and regrowth. Add real log/board/shingle processes as separate recipes, rather than inventing invisible resources.
2. Collect reeds, clay and stone. Process more sophisticated wood and mortar materials at appropriate stations.
3. `Build > Homes > Family > Style > Rotate > Place`: read-only placement ghost returns footprint, entrance, tile occupancy, external doorway access, terrain/water hazards, slope and item deficits.
4. Foundation, frame, roof and finishing are separate construction transactions with 20%, 40%, 30%, 10% of the material bill (integer-balanced exactly); only an authorized command spends materials. A saved unfinished shell occupies the whole footprint.
5. Completed residence gets one stable door UID and one persistent interior UID. Player homes start without free generated furniture/loot. Interior geometry and doors are derived from the same home plan, not from decorative render tiles.
6. Furniture can be placed, rearranged, rotated, picked up and stored subject to mass, owner, NPC occupancy, collision, station reservation and connected exit checks. Container contents/UID survive moves; moving a filled chest cannot duplicate or destroy its items.
7. Damage, repairs, shelter, insulation and dismantling are authoritative and persistent. Do not increment settlement house counts when a player builds a home.

## Module boundary

- `worldseed/systems/homestead_construction.py`: pure catalog/rotated footprint/door coordinates, materials, preview and atomic construction actions.
- `worldseed/systems/building.py`: existing world tile occupancy and simulation command bridge; use current world and resource caches, never run generation during hovering.
- `worldseed/systems/state.py`: versioned `homesteads` dict with backward-load default; stable home UIDs, explicit style and stage.
- `worldseed/systems/interiors.py`: reuse current room/wall collision, entrance/exit reachability and furniture rearrangement with a player-home construction path.
- `worldseed/ui/pygame_terminal.py`: mouse-first house style selector, rotation/ghost feedback and stage interaction; renderer is observation-only.
- `worldseed/presentation/visuals.py`: independent exterior/foundation/construction sprites indexed by immutable style asset ID.

Keep all changes separate from settlement production/building variants. Do **not** modify NPC settlement generation, regenerate occupied terrain, or introduce a second structure authority.

## Validation gates

- 5 home families, 10 unique style/asset IDs each; deterministic stable save-load.
- 50 styles × 4 orientations have a valid perimeter door and adjacent outside entry.
- Stage material invoices exactly conserve the bill; rejected or repeated commands spend nothing.
- Reject structure/tree/NPC/water/flood/grade/doorway and other homestead footprint collisions.
- Legacy saves without homestead records still load.
- Occupancy lookup is indexed by nearby chunk; hovering and drag previews do not mutate or generate.
- Furniture moves cannot strand NPCs, block the exit, or duplicate items.
- Real replay tests cover build→furnish→save→reload→dismantle; CI must identify failing assertions and keep performance stable.

## Validation performed for the isolated prototype

Seven targeted tests passed for style counts and asset path uniqueness, all rotations and doorway access, staged material conservation, rejected-site no-consumption, full construction and serialization round trip, entrance/grade rejection, and overlapping-plan rejection. This does **not** establish live client integration or full repository-suite green.
