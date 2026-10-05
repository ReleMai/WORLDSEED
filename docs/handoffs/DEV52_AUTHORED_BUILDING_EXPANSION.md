# Dev52 - authored building and furnishing expansion

## Scope and baseline

Started from freshly fetched canonical main `bab8c96a5fe71e9751d660361590873d1060a669` in the attached settlement-interior-research worktree. Workspace preflight passed. The unrelated dirty checkout at `D:\Codex Project\wsLIVING` was not edited or reset.

This expansion adds 30 independently authored exterior building styles, 20 independently authored functional furniture variants and 10 opaque interior materials (seven floors and three walls). Each new building has an independently measured full-image doorway rectangle and a genuinely different stock preference table. All artwork was created through the imagegen skill and built-in image generation, with individual exports for each asset and one transparency repair for the leatherworks. Installed exports remain byte-for-byte intact; the pre-repair original is preserved separately. Exact prompts, source paths, destinations and doorway measurements are recorded in the three `DEV52_*_ART.json` manifests beside this note.

The styles extend existing settlement functions rather than inventing 30 additional occupations, building-capacity authorities or goods ledgers. Residence, inn, barracks, smithy, workshop, bakery, brewery, weavery, tannery, mill, fishery, barn, clinic, market, archive, school and shrine structures select compatible styles from their stable physical-plan identity.

## Modules and public contracts

- `building_variants.py` consumes `data/building_variants.json`. `building_variant(structure, variant_id='')` and `variant_by_id()` expose read-only style metadata. IDs, functional profile references, interior dimensions/grammars and distinct loot item sets are validated. Unsupported functions retain their existing presentation.
- `interior_furnishing.py` consumes `data/interior_furniture_variants.json`. `furniture_variant(piece_id, stable_uid)` chooses a new fixture's authored style during explicit preparation; `furniture_base_piece()` retains existing use semantics. Variant footprints must equal their functional family's footprint. Existing furniture IDs, positions, sources and inventories remain untouched.
- `interior_templates.py` overlays authored room names/dimensions and one of four existing connected grammars for newly prepared interiors. Saved ground plans are not rebuilt. `profile_for(structure, variant_id='')` also pins missing upper-floor construction to the saved ground style if the content catalog later expands. Original profile/layout identities remain compatible with established building-form consumers.
- `interior_storage.py` matches variant furniture through its base family and binds the same original container. `container_profiles.py` supplies the building-specific primary stock preferences without replacing stable container slot/profile identities. Existing contents and picked/forced locks are not reseeded or repaired.
- Six new workstation appearances map to existing workbench, oven, forge, loom and brewery station APIs. They expose the established crafting UI and recipes using the real physical fixture source; they do not add anonymous production batches.
- Exterior rendering observes one saved ground-plan lookup per visible shell to freeze its authored style. Full-PNG doorway measurements align painted thresholds, selectable door leaves and authoritative entrance tiles. Buildings remain solid; roofs do not expose hidden live entities or promote terrain discovery.
- Interior rendering uses pinned materials and aspect-preserving upright furniture canvases. New container furniture uses its own authored silhouette while retaining the original container and theft/lock UI. Legacy container appearances retain existing art.

## Persistence and migration

Save schema remains 3. Geography, hydrology, coast, route and settlement projection versions are unchanged. Newly constructed interiors use explicit plan version 4. Optional `variant_id`, `floor_material` and `wall_material` fields default to empty strings for legacy saves; new upper floors inherit their building's saved style/materials. The verifier accepts v1-v4 plans and rejects malformed optional style identities.

Already-saved interiors retain their existing walls, geometry, furniture, goods and locks. The full new style/room/material combinations are visible in newly prepared interiors. No automatic legacy redecoration or loot refill occurs.

## Determinism, LOD and performance

New cosmetic hash namespaces are `building-variants-v1` / `building-variant` and `interior-furniture-variants-v1` / `fixture-style`, keyed by stable existing IDs. No global randomness is used. The catalogs are bounded to authored content. Furniture preparation retains the existing 24-addition budget per floor and three-floor limit. Renderer source/scale/mask caches retain existing bounds; no population-wide search, world realization or regional planning is added.

Loot tables choose only available real settlement stock. Withdrawal reduces the same stock ledger; an empty town does not receive spawned treasure. Furniture variants create no new inventory items, economic capacity or containers.

## Validation

Initial integrated regression group: 74 tests passed in 27.212 seconds under the 180-second bounded runner, including legacy furnishing, floors, engine/AI/knocking, real storage, property security and production shell presentation. SQLite save verification is included. Content audit passed with the unchanged 154 inventory items, 82 recipes and 35 structural definitions.

Final integrated regression group: **167 tests passed in 38.450 seconds** (39.2 seconds including the bounded runner). This covers all new content, all 30 measured door anchors at four zoom levels (120 rendered cases), genuine asset transparency, deterministic selection, saved facade/floor pinning under catalog growth, workstation recipes, rest actions, real stock conservation, storage identity/locks, Stalk theft, legacy furnishing preservation, physical NPC home entry/exit, stairs and representative SQLite save round-trips with the CLI verifier. Existing tests changed only for the intentional v4 plan contract and functional-family fixture matching; reach/wall/conservation assertions were preserved.

`compileall` passed. Content audit passed (0.3 seconds); the full visual decoder/coverage audit passed (4.1 seconds, 815 unique assets). All 30 exterior file hashes match their provenance manifests. A corner-alpha failure in the original leatherworks export was fixed using a native transparent-background image edit, not by relaxing its test.

Offline production QA passed in 11.0 seconds. `tools/preview_dev52_content.py` generated the 60-asset contact sheet, six actual interior screenshots (residence and inn on two floors, market and smithy), and all 30 production facades with selectable doors and diagnostic physical threshold marks. Screenshots assert that rendering does not mutate authoritative state. The root agent visually inspected the exterior doorway sheet, individual asset sheets and furnished room renders. The deterministic fixture has no generic workshop, which the preview reports rather than inventing one.

The fast gate includes the bounded Dev52-specific test modules. Validation is development-level targeted/offline evidence, not a live gameplay session or the manual full release-hardening suite. Automatic CI status is reported with publication rather than assumed from local tests.

## Known limitations and next dependency

These are authored variants of existing working buildings and furniture, not new professions or new crafting recipes. New decorative storage fittings have no independent goods inventory unless bound to an existing real container. New house materials are pinned per building; legacy room-specific material overrides remain unchanged. Future content may add styles to the JSON catalogs with matching authored art/anchors, without altering terrain or physical-plan authority.
