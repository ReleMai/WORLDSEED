# Dev53 - semantic furnishing, gameplay illumination and indoor HUD

## Scope and player changes

Newly prepared interiors project original furniture into finite room-purpose slots: beds belong in bedrooms, stations in work rooms, storage against suitable walls, and chairs beside actual tables/desks. Named slots reserve entry/stair space and an accessible standing edge. No random scatter or dense fallback search is used. Existing real source fixture/container IDs, housing capacities, reservations and goods remain authoritative.

Three new transparent carpet assets (hearth rug, bedside runner and hall carpet) occupy deliberate flat, non-solid slots. They are decoration, not beds, workstations, inventory goods or independent storage. Rest and household sleep use functional bed families instead of substring matching, so a bedside runner cannot become a sleeping target. Artwork was generated using the built-in imagegen skill and copied without pixel editing; exact prompts and paths are in `DEV53_DECORATION_ART.json`.

Opaque room-name, stair and outside-door tags render after furniture and darkness. Room tags use viewport space rather than splitting words to fit a narrow room; overlapping tags shift vertically. Tags do not change the existing physical door or furniture pointer targets. The indoor sidebar shows room/floor, four vitals, light level, trespass/stealth status and all ten existing exterior toolbar buttons. Retained inventory/crafting panels preserve indoor movement and stacked-panel behavior. Indoor Look observes visible furniture rather than the outside anchor; exterior construction from inside is denied with a clear explanation. Owned furniture still uses the existing reposition command.

## Modules and public APIs

- `interior_furnishing.py` / `interior_furnishing.json` v2: `fixture_slot_candidates`, `place_source_fixture`, `slot_placement_clear`, `room_furnishing_style`, and `is_bed_piece`. Source projection, new upper-floor beds and missing storage bindings use the same finite slots and circulation checks. Decorative additions remain capped at 24 per floor.
- `illumination.py` / `illumination.json` v1: `indoor_sources`, `indoor_light`, `interior_ambient`, `indoor_line_clear`, `outdoor_sources`, `outdoor_light`, `source_strength`, `detection_scale`, `light_description` and `indoor_actor_visible`. Integer light is 0..65535; sources have finite quadratic falloff. Weather/game-clock ambient is authoritative; walls occlude indoor emitters. Lamp stands, braziers, domestic hearths and mine lamps are actual fixture sources; outdoor light consumes fueled `FireCell` state.
- `stealth.py`: recognition depends on target illumination, stance/skill, range/cone and the same physical obstruction authority. Darkness reduces reach but never grants invisibility. Player indoor NPC visibility follows wall/light rules; hidden residents/names are not exposed by the sidebar. Indoor hearing now measures actual continuous actor positions rather than shared exterior building anchors.
- `NPCSystem.nearby_npcs` supplies a transient, by-reference actor locator to stealth. Existing decision/tick iterations update buckets incrementally; startup, settlement activation and offline completion rebuild the derived index explicitly. Render snapshots never scan world population. Isolated legacy test fixtures have a capped 64-actor fallback. No scheduler order or production cadence changes.
- `interior_view.py` samples at most a 30x22 light field for shading; art/camera geometry remains separate from collision and ownership. `weather_fx.py` uses the same source falloff/radius for bounded cached warm fire halos. RGB intensity is encoded explicitly for additive blending, avoiding opaque bright discs from zero-alpha pixels.
- `interior_inspection.py` is an observational discovery-safe Look read model. `app.py` only adds indoor dispatch guards; the shared router and NavigationStack remain authoritative.

## Persistence, RNG, LOD and migration

Save schema remains 3. No geography/hydrology/coast/route/settlement version changes and no new persistent lighting/NPC state. Furnishing preparation version 2 is accepted by the save verifier; old missing values remain 0. Explicit entry/workplace preparation safely adds missing decorations to v0/v1 plans and pins v2. Saved walls, furniture positions, source IDs, inventories, picked locks and reservations are not moved or replenished. Optional additions can be skipped if occupants or old furnishings block a slot; there is no compulsory saved-room repack.

New placement is deterministic over sorted stable room/fixture identities; no new RNG namespace is needed. Existing `interior-furniture-variants-v1` appearance selection is retained. Maximum light sources: 64. Outdoor queries use bounded keyed fire cells, never an infinite/global scan. Indoor queries consume one prepared plan/local actor index. Source, art and glow caches are bounded. The NPC index holds references to authoritative actors, not duplicate actor records, goods or history.

## Validation and evidence

- Integrated furnishing/storage/lighting/security/content/AI regressions: **115 tests passed in 47.284s** (48.2s including bounded runner). Includes representative SQLite save round-trips and CLI `verify_save.py` checks. The first attempt contained an incorrect synthetic fixture identity and a nonexistent test-module name; both were corrected, not weakened assertions.
- Final UI/weather/carpet/pointer/retained/HUD routing group: **49 tests passed in 7.873s** (8.6s bounded). Includes the full-name narrow-room correction and finite fire-glow regression.
- Agent-owned lighting/security/AI group: 62 tests passed in 25.988s; focused realtime/activity group: 17 tests passed. New tests forbid distant NPC mapping iteration during render queries and prove movement updates the simulation-owned buckets.
- Final root lighting/realtime/activity/interior-AI group: **35 tests passed in 0.029s** (0.7s bounded), after the simulation-owned indexing and offline-boundary hooks were complete.
- Compilation passed. Content audit passed (154 items, 82 recipes, 35 structures; no new inventory items). Visual audit passed: 818 unique assets.
- Offline production QA passed in 5.4s: 12 real day/night room renders, a three-carpet contact sheet, and authoritative-state equality checks around every rendered frame. Reviewed day/night residence, inn and carpet art; the corrected service-gallery tag is fully readable. The deterministic fixture has no generic workshop and the tool reports this rather than inventing one.
- An isolated full `test_ui_rc2` attempt exceeded its 180s deadline in repeated worldgen setup after 22 preceding tests passed. An earlier mixed graphical/worldgen attempt hit a native pygame crash in hydrology setup. Focused affected UI/retained tests pass; no larger timeout or weakened contract was used. This is targeted development/offline evidence, not full release hardening or a live playtest.

The fast gate includes the four Dev53 test modules. Publication/automatic CI result is reported separately; local checks do not imply completed GitHub Actions.

## Limitations and next dependency

Installed indoor lamps/hearths are steady sources in this pass: no switches, fuel inventory or extinguish command for those fixtures. Outdoor fueled fires are supported; additional outdoor lamps/windows can extend the same data/API later. Warm outdoor fire halos are presentation, not the tactical recognition boundary; physical occlusion is enforced by gameplay sight/light sampling. Carpet noise effects are not added. Legacy rooms are not automatically repacked, so newly prepared buildings best demonstrate the new source-furniture layout. Exterior construction is not an indoor construction tool; use existing repositioning for owned furnishings.

Next dependency: optional explicit light fixture state/toggles and bounded prepared outdoor emitter indexes, without introducing a second clock, terrain generator or economic inventory authority.
