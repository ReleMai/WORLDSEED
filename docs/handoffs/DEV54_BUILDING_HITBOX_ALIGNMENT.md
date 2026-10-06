# Dev54 - building footprint and artwork alignment

## Scope and cause

Building movement collision was already shared by the player and nearby NPCs and owned by the exact `StructurePlanState.footprint`. The exterior renderer instead scaled each entire padded PNG and translated the whole sprite to align its painted doorway. Narrow and asymmetric exports could leave multiple visibly empty but solid columns beside a building. This made correctly planned perimeter/service paths appear blocked by invisible buildings.

The correction fits visible artwork to the immutable planned bounds and aligns the facade doorway within that fit. It does not shrink collision from image transparency, move stable doors, reroll layouts, or create renderer-only paths. Genuine transparent roof corners remain alpha-aware pointer gaps; a known solid footprint underneath such a corner is described as movement-blocking rather than advertised as a painted exterior interaction.

## Contracts and state

- `exterior_view._whole_surface` crops source alpha bounds once per cached fit and uses three horizontal facade bands plus a threshold-aligned vertical fit. The painted recess and separate upright door leaf share one geometry. Fitted pixels and facade rectangles have the same cache lifetime (96 entries); source-cache eviction cannot misalign a cached doorway.
- Simulation collision, sight obstruction and actor-aware property locks continue to consume the existing physicalization/BuildingSystem authority. Closed shell entrance cells remain solid; entering a building uses the existing door/interior portal workflow.
- Fitting is presentation-only. Source PNGs remain untouched, roofs and door leaves stay upright, and exterior/body pointer regions use the same fitted surface as the drawing.
- Stable structure/door IDs, footprints, road geometry, saved interiors, loot, reservations and ownership remain unchanged. Irregular footprint cutouts stay passable; a sprite's rectangular bounds do not become a second collider.
- Save schema, worldgen, settlement-plan and route-generation versions are unchanged. No migration, new persistent field or RNG namespace is required; existing saves receive the presentation fix immediately.
- Source, fitted-surface, door and alpha-mask caches are bounded. Rendering consumes already prepared local shells and does not generate terrain/plans or alter discovery/state.

## Validation

- **22 access/security tests passed in 74.235s** (75.1s bounded runner). Covers all 25 synthetic population/resource-layout cases, more than 100 local NPC road trips, no roads through enclosed bodies, connected/passable frontage, exact rectangular/L/chamfered footprint occupancy, solid entrance portals, destroyed/zero-condition shells, underground separation, frozen v10/v11 access-repair/cache behavior, representative state/database round-trips and shared stealth obstruction.
- **47 rendering/UI tests passed in 15.087s** (15.9s bounded runner). Covers all 57 exterior assets at 16/28/40/56-pixel zooms, pinned variant portals, painted recess/leaf agreement, source-cache eviction, complete fit-key inputs, genuine transparent silhouettes, hidden/discovered/remembered state, exterior and indoor pointer routing, unchanged interior HUD/panels and bounded caches. The initial pointer-only check also passed all 10 tests.
- Final `python -m compileall -q worldseed tools tests` and `git diff --check` passed.
- `tools/preview_dev54_exteriors.py` rendered six representative synthetic shells using the real exterior renderer, with clean and footprint/door-diagnostic views. Both were visually reviewed, including the asymmetric residence and narrow padded townhouse. Narrow source art is wider than before because it now depicts the full planned footprint rather than an invisible solid margin.
- The two new Dev54 test modules are included in the automatic fast gate. Publication/remote CI status is reported separately.

This is **69 targeted development tests plus offline visual evidence**, not a live playtest or full release-hardening run. No new item/art content or persistent state was added, so no content migration or geography audit is required.

## Limitations and next dependency

Collision remains tile-exact outside. Transparent architectural corners, roof overhangs and open cutouts are presentation features, not pixel-level collision. Legacy non-south doors retain their physical-side marker when the existing stable portal cannot be represented by south-facing art. This pass does not redesign terrain legality or relocate shoreline settlements.
