# RC14 Dev39 — Territorial Sovereignty Foundation

## Scope / modules changed

- Added persistent generated claim monuments and regional control read models.
- Bound monument influence to the existing strategic route-cost propagation.
- Added sustained physical capture/defense presence from settlement guards.
- Added discovery-gated faction UI summaries for known control anchors.

Primary modules: `worldseed/systems/territory.py`, `state.py`, `route_planner.py`,
`ai.py`, `sim/engine.py`, `ui/screens.py`, and persistence validation.

## Public APIs / contracts

- `TerritorySystem.prepare_sites(plans)` prepares deterministic, spaced sites
  only inside the bounded settlement/route planning envelope.
- `record_presence()` contributes faction strength; `daily_update()` advances or
  reverses capture instead of allowing touch-to-capture.
- `damage()` and `repair()` mutate the same persistent monument authority.
- `RoutePlanner.refresh_territory_control()` recomputes settlement + monument
  influence through real route condition, blockage, and contested costs.
- `monument_effective_control()` derives power from integrity, supply, and
  garrison. A ruined monument contributes zero rather than erasing territory
  directly; neighboring anchors may fill the gap.

## Persistent fields / migration

- New `LivingWorldState.claim_monuments` and `territory_control` tables.
- Missing tables load as empty on legacy schema-3 saves; no schema bump.
- `TERRITORY_VERSION = 1` independently pins generated site identity.
- Save validation checks faction references, bounded metrics, reach, and region
  keys. Generated sites persist as state; damage/capture is not cache-owned.

## RNG namespaces

- `claim-monument-rank`
- `claim-monument-x`
- `claim-monument-y`
- `claim-monument-cell`

All identities derive from `stable_plan_uid` and sorted candidate processing.

## Tests added / changed

`tests/test_territory_claims.py` covers deterministic generation, generation
order independence, spacing, sustained capture, persistence, verifier errors,
route-cost influence, destruction, and physical guard participation.

## Performance implications

Generation is bounded to active route regions plus their cardinal neighbors.
Control propagation is bounded to the same prepared candidate graph. No render,
hover, atlas, or ordinary movement path generates monuments or regions.

## UI exposure

Only monuments personally discovered by the player appear in faction summaries
and faction detail screens. Hidden monuments and controllers do not leak.

## Known limitations

- Monument state owns an exact legal surface cell, but unique local structure
  art/collision and direct player interactions are not yet materialized.
- Guards can scout/capture/defend nearby sites through existing physical motion;
  dedicated supply caravans, builders, sabotage, siege combat, and multi-NPC
  mission groups remain future work.
- The atlas political overlay is not yet implemented; this work provides its
  knowledge-gated authoritative control data.

## Next dependency

Materialize each monument archetype into the local physical plan, then add
shared interaction affordances (inspect/capture/repair/sabotage), mission-group
logistics, and the discovery-aware political atlas overlay.
