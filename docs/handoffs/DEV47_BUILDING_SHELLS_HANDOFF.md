# Dev47 solid building shells and differentiated interiors

## Scope and public behavior

Generated enclosed settlement buildings now present one solid roofed shell,
with a separately drawn and selectable stable entrance door. Outdoor movement
cannot enter the old floor cells even when a door is unlocked, picked or forced;
entry is an explicit portal action. Exterior inspection does not expose private
rooms, fixtures, stored goods or indoor actors. Casing, lockpicking and bashing
remain command-gated by Aggressive Stance, with no context-menu stance shortcut.
The shared bottom-right stance buttons are also available indoors.

Newly prepared interiors use 28 deterministic data-driven profiles: six house
forms, all 22 current enclosed functions, and one mod fallback. Front, side and
central halls connect distinct functional rooms. Original furniture/station IDs
and capacity remain authoritative. Existing saved v1 interiors are not rebuilt:
their geometry, loot and player-arranged furniture stay intact. New plans use
version 2 and an additive namespaced `layout_id`; save schema remains 3 and all
geography/settlement/route generation contracts are unchanged.

## Authority and public APIs

- `building_shells.py` derives immutable shells from existing structure plans.
  `physicalization.shell_at`, `shells_in_bounds`, `frontage_for` and
  `displace_shell_position` are bounded prepared-state queries; they never plan.
- Footprint collision and sight use the same shell authority for player/NPCs.
  Door frontage consumes existing plan road cells, not renderer-only paths.
- Household bindings retain their home/room/bed/property identity but start
  outside solid shells. Legacy trapped NPCs receive bounded activation rescue;
  saved indoor anchors are preserved. Player load recovery reads prepared dry,
  passable, unoccupied terrain and never sends the player to world origin.
- `PropertySecuritySystem.note_interior_entry/exit` uses existing permission,
  invitation, key, tampering, trespass and incident records. Indoor witnesses
  share the actual space and continuous wall-blocked line of sight; exterior
  NPC anchors cannot witness through roofs. Ongoing indoor responses run on
  the command/simulation path, never from rendering.
- `ActivitySystem.attach_interior_system` binds original fixture reservations
  to persistent `space_id`, `door_uid`, `interior_use_x/y` metadata. Workers
  withdraw inputs from the same service-court containers, enter through the
  real door, walk continuously to the original station, execute the existing
  profession callback exactly once, then leave and deposit the same output.
  Standing at the frontage or in a different space cannot progress work.
  Active/reserved fixtures cannot be rearranged; overflow stays in a real
  interior pile, not teleported exterior storage.
- Player basic recipe/component crafting and the existing workshop UI use
  continuous interior reach and partition checks, never exterior anchor
  stations or work bonuses. Timed process/cooking jobs remain outdoor-only.

## Persistence, determinism and performance

`InteriorPlan.layout_id` defaults to empty for legacy records. The verifier
accepts v1/v2 and validates namespaced layout IDs plus indoor reservation
space/door/fixture links and bounded integer use positions. Existing reservation
JSON metadata carries the new fields; legacy reservations rebind on execution.
There is no second stock ledger, capacity source or random settlement layout.
The `interior-template-v2` / `interior-profile` deterministic namespace selects
profiles from stable building identity; existing household routine namespaces
remain unchanged. Rooms, graph nodes, movement substeps, local shell indexes and
render caches are bounded. Existing exact labor reconciliation and offline
coarse advancement remain in place; domestic routines mint no goods.

## Art and UI

Built-in ImageGen authored 49 independent building, door, furniture and scribe
station PNGs, covering 27 shells, two doors, 19 new furnishings and a scribe desk;
the existing unique single bed completes all 20 core furniture definitions.
transparent alpha is retained unchanged on import. Final asset paths, subjects
and exact prompt templates are recorded in [DEV47_ART_PROVENANCE.md](DEV47_ART_PROVENANCE.md).
Eight existing decorative prop types use their established native artwork
indoors rather than letters; this does not invent fixtures, goods or capacity.
Whole-shell rendering clips discovery cell-exactly and uses bounded sprite
caches. Each door keeps its original ID and click cell. The M settlement view
continues to consume the same authoritative plan; no roads or terrain are
invented for a visual. Preview tools use actual generated settlement structures
and check that rendering is observational.

## Verification and known boundaries

Compilation passes. The coherent integration batch passed 165 tests in 134.3s,
including real command dispatch, NPC work reconciliation, stable shell/frontage
authority, security, deterministic profiles and representative SQLite save
round-trip plus `verify_save.py`. A focused UI/storage/crafting/atlas batch
passed 53 tests in 3.7s; presentation/diagnostics passed 26 tests in 6.0s and the
final native-prop presentation batch passed 17 tests. The final combined
diagnostics/building/interior presentation rerun passed 27 tests in 6.2s after
the last native-art change. Nine item/character asset tests, content audit and
full visual decode audit passed. Six actual generated
interior previews and an exterior preview were rendered observationally and
visually checked; catalog QA includes all 22 enclosed functions, six houses,
two doors and 20 unique furniture sprites. The final asset count is 741.

An additional overbroad UI batch hit its 120-second deadline in an unrelated
full-world HUD fixture; it was stopped, not reported as passing. Focused direct
integration cases were selected after inspecting the slow full-world startup
cost. No assertion was weakened or deadline enlarged. Windows validation also
exposed a pre-existing `os.execvp` gate quoting/exit bug: the assigned-job token
gate now runs the intact argv via `subprocess.call` and propagates child status.
All ten diagnostic tests pass, including failed-unittest status and descendant
timeout cleanup. Non-Windows execution remains unchanged; Linux proof is CI.
The image audit now accepts RGB only for the two explicitly resolved opaque
interior texture paths (or terrain); furniture/shell/door overlays require RGBA.

This is development validation, not full release-hardening or a manual live
playtest. The original dirty `D:\Codex Project\wsLIVING` checkout is preserved;
the coherent update is made from the attached clean managed worktree.

Full player-built building grouping, editable interior partitions, furniture
rotation, complete household indoor storage verbs and timed indoor processing
remain separate dependencies. Generated furnishing counts still reflect the
original plan: some civic buildings have a single shared fixture, rather than
inventing additional capacity or goods during layout projection. Permission
expiry while already indoors is not yet a new trespass trigger; entry and
ongoing recorded-intrusion responses are covered. Open fields/pens/mines/camps retain their existing outdoor assets
and interaction authority. Old visited interiors intentionally keep their
saved v1 layout; enter an unprepared building to see the new functional layouts.
When knocking, leave the one-cell outside threshold free for a resident to exit.
