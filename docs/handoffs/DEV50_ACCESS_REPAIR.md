# Dev50 settlement access repair

## Scope and public contract

`settlement_planner.py` pins new geometry to settlement-plan v12. Upright building
art now corresponds to a reachable southern exterior portal; service paths are
authoritative `RoadSegmentPlan` objects. Animal-pen gates require a cardinal step
both outside and into the unfenced interior, not a corner touching two fence arms.
Unbound regional exit potential creates a bounded local street, not an arbitrary
long road to the empty planning boundary. Real selected strategic-route gateways
and crossing identities retain their full corridors.

`settlement_access.py` prepares explicit access corrections for existing v10/v11
towns during physical activation. Read-only prepared-plan queries can apply an
already stored correction, but never compute or write one. The generated base
cache and its fingerprint remain unchanged. The overlay is stored in the existing
`physical_plan_deltas` table under the stable settlement plan UID, kind
`settlement_access`, repair revision 1; save schema remains 3.

## Persistence and conservation

Corrections retain building, room, door, gate, lock and container identities.
Door/gate coordinates move, replacing the old opening with its generated wall or
fence. Only generated blockers on the new short service approach may be cleared.
Player-built objects and all goods are outside this operation. Forced/picked lock
state, condition, NPC home/work bindings, interiors and capacity stay unchanged.

When an existing building's whole south edge touches another building, the repair
may inset only its outer south wall by one cell to create an apron inside the old
parcel. This requires at least a 4x4 exterior; independent larger interiors are
not resized. Removed exterior wall/floor/roof pieces do not remain as outdoor
ghost furniture. No town, terrain, resource district or room is re-rolled.

Only unused suffixes of unbound gateway roads are trimmed. Road identities,
intersections, parcel access, production paths and real route/crossing links stay.
The recorded correction survives deletion/rebuild of the generated cache.

## Verification and performance

`test_dev50_settlement_access` covers all five economies and five ranks for new
v12 plans and saved v11 repairs, frozen v10 output, real strategic gateways,
idempotent/read-only delta reapplication, cache deletion, stable locks/quantities/
residents/capacity, and a generated trough blocking the proposed pen inward step.
The existing v11 production tests also remain green.

`audit_settlement_layouts.py` additionally checks actual cardinal gate passage.
`audit_saved_settlement_access.py` opens the original save read-only, backs it up,
and runs repairs/audits only on that copy with raw hydrology generation disabled.
The reported `New_World_180a.db` town (`settlement:1:1`) passed: 21 entrance/gate
positions corrected, zero missing/disconnected/blocked approaches, all enclosed
portals southern, no footprint inset needed, unchanged base cache, clean save
verification. Its road-cell count fell from 781 to 683, including new service
paths. This is prepared-state/headless evidence, not a live play session.

Work is bounded to the currently activated settlement. One sparse repair row per
activated legacy town replaces repeated repairs; UI/hover do not plan access.
No new RNG state/domain is consumed. New service IDs use stable parent identity
and exact geometry.

## Known limitation

Two strict synthetic v11 fishing cases (population 45 and 110) have 5x4 shells
whose complete south frontage touches another intact building. Insetting would
violate the 4x4 minimum, so they retain their existing physically reachable side
portal and require the presentation's explicit selectable side-door leaf. New
v12 placement rejects this configuration. The user's reported town has no such
residual cases.
