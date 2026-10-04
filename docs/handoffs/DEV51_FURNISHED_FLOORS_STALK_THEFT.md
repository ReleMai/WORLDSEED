# Dev51 — furnished interiors, household floors and Stalk theft

## Scope and baseline

Implemented from freshly fetched canonical main `04b1acf51709788f6559524917434f11589e2e32` in the attached settlement-interior-research worktree. Workspace preflight passed. The unrelated dirty canonical checkout was not edited or reset.

- Data-driven domestic furnishings and aspect-preserving upright artwork; painted silhouettes now select stable furniture IDs rather than relying on tiny floor footprints.
- Furnished bedrooms, living rooms, kitchens, studies, stores and workplaces; new inn/market plans use a central service gallery instead of enormous empty room strips.
- Casing is disabled. Private container and market theft require the exact Stalk stance; locks, real keys, reach, cargo limits, witnesses, crime and relationship consequences remain enforced.
- Size-derived household floors and usable stairs; residents physically walk home, enter, climb to beds, rest, descend and leave in the morning.
- New closed/open oak doorway, up/down stair and exact market-counter sprites. Existing authored furniture is retained, not substituted with another item's art.

## Modules and public contracts

`interior_furnishing.py` consumes `data/interior_furnishing.json`. `furniture_dimensions()` supplies physical widths/depths, `furniture_visual()` supplies presentation height/flatness, and `furnish_plan()` adds bounded non-economic fittings. Doorway aprons, stairs, fixtures and occupied actors remain clear.

`interior_floors.py` prepares stable connected floor plans during explicit interior preparation, never during rendering. Residences, inns and barracks receive one to three floors based on their real footprint. New beds may be distributed upstairs with their original IDs and total capacity unchanged.

`UseInteriorStairsCommand(actor, stair_uid)` resolves the current-space stair and validates reach, wall obstruction, target landing and reciprocal return stairs before updating presence/spatial indexes. Upper floors cannot exit directly outdoors.

`interior_view.pointer_object()` returns an observational painted-object region with a stable UID. Pygame emits `INTERIOR_OBJECT:<kind>:<uid>`; the app resolves it against the current plan and commands still enforce physical reach. Empty-floor coordinates remain continuous. Upright furniture and actors are depth-ordered; rugs stay below actors; soft contact shadows no longer paint solid rectangular footprints.

Exterior door presentation reads prepared visible security state to show an open door for forced/resident-answered entrances. It cannot reveal unseen door state or generate terrain.

NPC rest walks saved against old tiled bedrooms are rebound to the same authoritative home's current doorway/frontage. This changes the task approach, not the actor's position, cargo or home binding. Indoor locomotion remains simulation-tick driven; production cadence is unchanged.

## Persistence and authority

Save schema remains 3. No worldgen, hydrology, coast, route or settlement projection version is changed. New interior grammar is explicitly version 3; saved ground-floor walls and furniture are not rerolled.

New optional fields have legacy defaults: `floor_index=0`, `floor_count=1`, `stairs=[]`, `furnishing_version=0`. A stair stores its stable UID/rectangle, target space/landing and direction. Upper-space IDs are `interior:<building>:floor:<index>`; every floor shares the existing building/property/door identity.

Explicit preparation adds bounded furnishings once (`furnishing_version=1`) and available linked floors. Existing occupied furniture/walls and old beds remain in place. New floors are skipped if safe connected stairs cannot be placed. The save verifier rejects invalid identities, landings and missing reciprocal stairs; transfer also denies malformed one-way stairs before mutation.

Historical casing intel remains load-compatible but inert. An active legacy casing session is retired. No new goods ledger, residents roster, work capacity, loot container or inventory item is introduced by cosmetic furnishing. Original physical containers and workplace fixtures remain the authority.

## Determinism, LOD and performance

No new RNG namespace or global randomness. Added furniture IDs derive from plan, room and named slot identity. Each floor adds at most 24 domestic fittings; floors are bounded to three. Preparation is explicit and idempotent; rendering reads one prepared plan and local actor buckets. Artwork caches are bounded (96 sources, 128 scales, 64 contact-shadow sizes). Distant populations are not promoted by this feature.

## Validation

- `compileall -q worldseed tools tests`: passed.
- Final bounded integrated group: **132 tests passed in 20.940s** (runner limit 180s). Includes floors, furnishing, theft, painted-object targeting, engine, AI/knocking, interior security/projection/work, building art, HUD routing, item assets, activity/profession conservation and representative storage saves.
- Earlier focused security integration: 74 passed; focused UI/navigation/storage routing: 65 passed. These overlap the final group and are not a unique combined test count.
- Representative two/three-floor SQLite round trips and `tools/verify_save.py`: passed. The older Dev50 storage fixture now retains all linked floors rather than saving an intentionally orphaned ground-floor stair.
- Content audit: passed (154 items, 82 recipes, 35 structures, 10 crops, 34 resources, 27 species).
- Final visual audit: passed (755 unique assets).
- `preview_dev51_interiors.py`: production renderer generated five deterministic residence/inn/market frames with an unchanged-state assertion for every frame; visually reviewed after polishing shadows and counter artwork.
- `git diff --check`: passed.

An initial broader UI run hit its 180s bound in old full-world navigation setup; it was not retried with an increased deadline. Focused routing/UI checks were used instead. This is targeted development validation, not the full release-hardening suite or a human interactive playtest.

## Art and UI exposure

Built-in image generation produced five transparent PNGs under `assets/sprites/buildings/dev51/` and `assets/sprites/interiors/dev51/`. Original artwork remains available. Exact prompts, source paths, final destinations and generation mode are recorded in `DEV51_ART_MANIFEST.json`.

Right-click furniture/stairs, or use the existing action hub. The interior HUD shows floor number, free movement, room names, local known residents and bottom-right stance buttons. Stalk enables theft; Aggressive retains lockpicking/bashing. Casing is absent from active menus and overlays.

## Known limitations and next dependency

Legacy interiors preserve their existing geometry; newly prepared interiors receive the improved grammar. Their old ground-floor beds are deliberately not moved. Floor count is bounded and may remain lower when saved geometry cannot safely fit stairs. Cosmetic washbasins/desks/shelves do not invent hygiene, healing, water or economic output. Workstations retain their existing functioning command/UI uses. Broader human visual/behavior playtesting and deliberate full release validation remain outstanding.
