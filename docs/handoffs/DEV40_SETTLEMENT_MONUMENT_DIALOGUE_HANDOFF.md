# Dev40 settlement, monument, atlas, and dialogue handoff

## Scope / modules changed

- Settlement plan v8 enlarges the residential program and assigns successful physical lodging parcels as inns, guard barracks, and outskirt camps.
- Claim monuments have four transparent authored sprites, local-world rendering, map markers, and a direct inspection panel.
- The M atlas replaces the square region grid with learned, deterministic irregular political shapes and knowledge-gated town/monument details.
- The existing dialogue storylet work is integrated into a retained conversation panel with selectable replies and an Inspect companion panel.

## Public APIs / contracts

- `LivingWorldState.learned_regions` stores bounded testimony snapshots keyed by `"region_x,region_y"`.
- `DialogueSystem.scene()` exposes area, casual chat, work, trade, inspect, attack, and goodbye options.
- `_learn_area_from_npc()` is the command-path knowledge transfer; atlas/render paths only read it.

## Persistent fields / migration

- Save schema remains 3. Missing `learned_regions` defaults to an empty dictionary.
- `SETTLEMENT_PLAN_VERSION` is 8 so old settlement layouts remain pinned to their recorded plan version.

## RNG namespaces

- `area-willingness` deterministically varies how guarded an inhabitant is.
- `atlas-region-shape` and `atlas-faction-color` make learned political overlays stable without creating simulation authority.

## Tests added / changed

- Dialogue options, willingness gating, learned-region round trip, movement token routing.
- Physical civic/lodging generation and representative town capacity.
- Monument atlas icon catalog and affected atlas/settlement/workshop regressions.

## Performance implications

- Atlas region overlays iterate only learned regions.
- Local monument rendering currently filters the prepared `claim_monuments` collection to the viewport; a spatial monument index is the next optimization if prepared networks become large.

## UI exposure

- Right-click a locally visible monument to inspect claim, owner/resources knowledge, condition, garrison/capture knowledge, and capture instructions.
- M shows learned irregular political regions, monument tier art, and faction/resource details on learned towns.
- Talking opens the retained conversation panel; Inspect shows worn items, visible injuries, and learned history.

## Known limitations

- The Attack dialogue option ends the conversation but named-NPC combat remains outside the current creature-only combat authority.
- Trade describes or redirects to the settlement market; direct person-to-person barter is not yet implemented.
- NPC-initiated conversations use the same panel contract but autonomous approach initiation is not yet scheduled.
- Regional resource testimony currently reports the settlement's leading real stock categories, not an omniscient geology scan.

## Next dependency

- Add named-NPC combat targets to combat authority, person-to-person barter, proactive social approach goals, and a spatial claim-monument index before widening prepared civilization envelopes.
