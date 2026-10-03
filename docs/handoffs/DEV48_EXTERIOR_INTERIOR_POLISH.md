# Dev48 exterior visibility and interior workstation polish

## Scope and modules

Baseline: freshly fetched canonical main `ba95d65d1b2d68ff3638551ec8e118eb649a3004`.
The original dirty `D:\Codex Project\wsLIVING` checkout is preserved. This work
uses the attached `settlement-interior-research` managed checkout.

`ui/exterior_view.py`, `ui/pygame_terminal.py` and `app.py` fix rotated shells,
misaligned doors and tile-sized fog holes in building art. Buildings retain
their upright source orientation; normalized per-art facade anchors include
the off-center doorway in the L-shaped house. Alpha-aware pointer hit regions
select the door independently from the body, including projected roof pixels
above unexplored ground. Door hit records resolve the same stable physical
entrance, not an invented door or new access permission. A small threshold
marker identifies road-facing access when it differs from the painted facade.

Whole observed static silhouettes are rendered after cell-exact terrain fog.
The physical footprint still controls collision. This does not discover any
ground, reveal indoor contents, or expand current actor/resource visibility.
Completely unknown buildings stay hidden; remembered buildings are uniformly
dim. Exterior hover/actions never query hidden terrain, actors, cargo or
resources. Water-animation redraw excludes painted roof bounds.

`ui/interior_view.py`, `presentation/visuals.py` and asset metadata provide
oak, flagstone and terracotta floors plus plaster, timber and stone walls.
Existing building functions choose appropriate decorative finishes; existing
room names refine flooring (kitchen, bedroom, forge, etc.). Keyword matching
uses word boundaries, so a private guest room does not become a vat room.
Saved walls, room geometry, furniture arrangements and collision are unchanged.
Furniture silhouettes aspect-fit their physical rectangles with a bounded
source cache; transparent export padding does not distort the art.

Built-in ImageGen created six new workstation cutouts: forge, carpenter bench,
millstone, bakery oven, loom and brewing vat. The six material textures and
six cutouts are preserved byte-for-byte under `assets/sprites/interiors/dev48/`.
Exact prompts, original paths and generation mode are recorded in
[DEV48_ART_PROVENANCE.md](DEV48_ART_PROVENANCE.md).

## Public APIs and UI

- `draw_shells(..., hit_regions=[])` emits stable body/door alpha hit regions.
  `shell_at_pointer()` prefers doors and rejects transparent gaps. Legacy
  tile-only callers remain supported.
- `UI_BUILDING_MENU:<body|door>:<stable-id>` routes through existing world
  context actions. Only known physical entrances offer door interactions.
  Criminal actions still require the bottom-right Aggressive Stance button;
  no stance shortcut has returned to the context menu.
- `VisualRegistry.interior_materials(function, room_name='')` is a pure
  decorative read model. The `interior_textures` manifest group is explicitly
  audited as opaque; furniture, shells and doors still require alpha.
- `InteriorSystem.furniture_use_status()` reports available, busy,
  out-of-reach or unavailable without advancing reservations. Existing local
  actor/task links identify physically present workers' reserved fixtures.
- `ui/interior_workstation.py` shows purpose, availability, learned recipes
  and real missing materials/tools/knowledge. Right-click use opens the shared
  workshop UI for all 12 existing workshop profiles. Recipe commands consume
  carried inventory and require reachable, unreserved fixtures, including
  wall/partition checks. No duplicate economy or recipe execution path exists.

## State, determinism and performance

No new persistent fields, schema migration, RNG namespace or generation-version
change. Existing stable plan/door/fixture/reservation IDs remain authoritative.
The engine/package presentation version advances to Dev48 only. Rendering does
not plan, tick, query hidden ground or write discovery/save state. Local station
refresh does not scan the world's NPC or activity-reservation collections.
Shell surfaces, masks, door surfaces and furniture source caches are bounded.

## Verification

- Complete source/tool/test compilation passes.
- Focused direct-integration batch: **97 tests passed in 25.047 seconds**.
  Includes real pygame pointer events, alpha/discovery gating, decorative
  materials, retained UI stances, actual forge/loom recipe handlers and input
  conservation, local work reservations, partitions, stealth/trespass,
  workstation-specific UI, weather animation and item asset catalog checks.
- Full visual decode/coverage audit passes: **753 unique registered assets**.
- Six generated-building interior previews and partially observed exterior
  preview pass observational checks; visually checked for complete upright
  roofs and distinct building/room finishes. Workstation profile QA uses explicit
  test plans when the generated city's economy lacks a given workshop type.
- An overbroad UI batch reached its fixed 180-second deadline while constructing
  unrelated full-world UI fixtures; it is not reported as passing. No deadline
  was increased and no assertion was weakened. A separate affected-path batch
  excludes that setup and passes. This is development/headless validation, not
  a full manual release gate or live gameplay playtest.

The automatic Fast Gate includes the three new focused regression modules.
Publication is one coherent commit to canonical main, with no force update.

### October 3 CI follow-through

The first Dev48 automatic run (`36959272856`) passed the Linux runner job and
the early Windows gameplay checks, then hit the unchanged 180-second Dev46
interior deadline. No assertion failed: `InteriorEngineTests` composed the
full-world UI fixture and regenerated unrelated surface regions per test.

The fixture now creates a fresh real database, World, registry, entities and
Simulation for every test, with a prepared indoor plan/player presence,
nonempty discovery sentinels and a dry anchor chunk. Only constructor regional
preparation is scoped out; real command dispatch, crafting, inventory,
clock advancement and post-action consequences remain covered. The original
assertions and deadline are unchanged; an added regression proves mutable
fixtures are isolated. One original local test took 9.147 seconds, while all
nine updated engine tests took 1.855 seconds. The exact Dev46 CI batch passes
**53 tests in 7.298 seconds**, including representative SQLite save round-trip
and `verify_save.py`. The exact Dev47-48 batch passes **77 tests in 7.681
seconds**. This follow-through changes tests/documentation only, not gameplay,
save contracts or generation versions. The repaired publication receives its
normal automatic Fast Gate; the first failed run is not treated as success.

## Limitations and next dependency

Timed process jobs and the separate meal-cooking menu remain outdoor-only;
workstation inspection says so explicitly. Basic recipe/component crafting
works indoors. Generated furnishing counts still reflect the original physical
plan, so sparsely furnished civic buildings are not silently given extra
stations, capacity or goods by a renderer. User-edited/legacy room geometry is
preserved. Editable walls, furniture rotation, full household storage and timed
indoor processing remain separate dependencies. Live-test building entry,
door knocking and workstation crafting from the managed build; existing saves
receive the new surface art without rebuilding their geography/interiors.
