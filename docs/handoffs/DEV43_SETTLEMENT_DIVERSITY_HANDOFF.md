# Dev43 diverse living settlements handoff

## Scope / modules changed

- `settlement_planner.py` now derives exactly two primary resource systems from bounded local terrain samples, varies morphology/orientation and dwelling footprints, bends roads through deterministic control points, and creates persistent open work sites.
- Settlement population/economy/profession systems bind miners, farmers, herders and lumberjacks to those physical sites and gate raw production by the settlement's selected resources.
- Property security makes a knock enqueue an exact resident walk to the door. The door opens only after that NPC reaches its stable door tile; dialogue remains a separate player action.
- The atlas detail panel exposes local resources, crops and livestock. Soil inspection uses the farming skill: broad fertility at level 1, crop condition at 3 and exact analysis at 5.
- Added corn and pumpkin crop/item art, bean/corn/pumpkin field processes, four domestic species, and authored art for mines, fields, logging camps, managed trees and animal pens.

## Public APIs / contracts

- `SettlementPlanState.resource_specializations` contains exactly two terrain-backed values for Dev43 plans. `crop_ids` and `livestock_species_ids` are derived from those values and terrain.
- `LandUseParcel` carries `resource_deposit`, `crop_id` and up to two `livestock_species_ids`.
- `StructurePlanState.building_form` identifies cottages, chamfered cottages, L-houses, longhouses, workshop blocks and open worksites.
- `PropertySecuritySystem.complete_door_answer(door_uid, npc_uid, minute)` is the physical completion boundary for queued knock responses.

## Persistent fields / migration

- `SETTLEMENT_PLAN_VERSION` is 9. Generated settlement plans rebuild under the new contract; authoritative deltas remain separate.
- New plan, parcel, structure, creature, settlement and door-answer fields all have safe defaults for older schema-3 saves. No save-schema or worldgen-version bump was required.

## RNG namespaces

- `settlement-road-bend` controls stable road curvature.
- `settlement-building-form` controls stable dwelling shapes.
- Existing stable settlement-plan IDs and `settlement-livestock` own worksite and domestic-animal identity.

## Authored/generated artwork

- Built-in ImageGen mode was used with transparent atlases matching WORLDSEED's detailed semi-top-down survival-game style: a 4x4 workshop/fence atlas, a 5x2 corn/pumpkin atlas, a 4x2 livestock atlas, and a 2x1 managed logging-tree atlas.
- Source atlases are retained in `artifacts/source-art/dev43_*_atlas.png`; `tools/import_dev43_settlement_assets.py` deterministically slices and normalizes them into package assets.
- Every new item has a unique matching item sprite and sprite tag. Direct settlement-piece mappings live in `assets/visuals.json`.

## Tests added / changed

- `test_dev43_settlement_diversity.py` covers two-resource limits, terrain-derived crops/animals, varied forms, road curvature, cache round-trip and distinct RGBA assets.
- Existing settlement generation, profession-yard, population binding, real-time social and animal sprite tests now cover open worksites, communal lodging, physical door answering and domestic sprite sets.
- Direct targeted integration: 68 tests passed across settlement generation, profession yards, population binding, exact professions, social/door behavior, physical property/crime, atlas UI, economy cadence, animal art and biome atlas.
- Final asset slice: 14 item/Dev43/animal tests passed. `compileall`, content audit and visual audit passed.
- Bounded simulation smoke passed for one seed / one year policy run (120 simulated days, no invariant errors).
- Local wheel construction could not run because this host lacks both the `build` and `setuptools` modules; GitHub's fast gate installs the package and is the package verification boundary for this publication.

## Performance implications

- Resource scoring samples a fixed 5x5 terrain window. Curved roads add only one bounded control point. Worksite placement and livestock materialization are bounded by active settlement parcels and never scan global population.
- Mine siting uses the existing bounded cave-entrance query and therefore reuses authoritative multi-layer caves, depth-dependent ores and cave ecology instead of creating a parallel mine world.

## UI exposure

- Settlement atlas details show learned plan economy data for the selected settlement.
- Looking at farm soil exposes increasing detail through the farming skill.
- Knocking returns an approach message; the resident becomes available for normal interaction only after physically answering.

## Known limitations

- Crop visuals remain three growth stages, matching the current farming renderer contract.
- Livestock husbandry is settlement-scale production; individual breeding, pen depletion and animal ownership trading remain later systems.
- Managed logging trees are persistent plan pieces that establish the plantation layout; exact regrowth/depletion still uses the existing natural-resource authority.

## Next dependency

- A later work unit can connect individual domestic-animal products and managed-tree regrowth to exact profession actions without duplicating aggregate economy output.
