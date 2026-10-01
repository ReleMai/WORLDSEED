# Dev45 farm compounds and farmer execution

## Scope / modules

The first farm-focused slice of stage 2 in the researched settlement/interior
plan. `systems/farm_compounds.py` supplies bounded pure geometry and shared crop
suitability. The settlement planner projects it into existing parcels, roads,
structures and pieces. No second building, resource, crop or economic authority.

New worlds have connected fields with chamfered edges, one perimeter fence,
one gate and a walking lane. Size scales from 18x16 homesteads to 60x50 cities;
villages are 40x34 and towns 50x42 before edge/lane deductions. Four crop blocks
share the compound. The barn, shed, well and stores occupy a separate court.
Livestock space is reserved before housing. Roads cannot cut the farm/court;
road-split lots without a usable building footprint are rejected and retried.

Physicalization now indexes field/pen fences, gates and worksite fixtures as real
collision/presentation objects. The settlement atlas preserves the land-use
colors of outdoor worksites instead of painting a field like a giant building.

Farmers bind to a room-backed barn, not a field without stores. Planting ignores
healthy growing crops, respects crop blocks and skips fences, lanes, pens and
other actors' reservations. Existing carried-inventory transfers withdraw seeds,
plant persistent CropPlots, harvest and deposit goods. Harvest also recovers real
seed cargo, consistent with the player harvest path. Exact labor continues to
replace its aggregate slot rather than minting a parallel production batch.

## Public APIs / persistence / RNG

`farm_compound(gate, away, rank, crop_count)` returns transient geometry;
`terrain_crop_ids(env, registry)` is shared suitability;
`starting_farm_seeds(stocks, crop_ids, registry)` only allocates NEW settlement
starting seed capital. It preserves the former wheat/turnip seed total and does
not refill existing stocks. Aggregate field assignments filter town crop IDs.

SETTLEMENT_PLAN_VERSION advances 9 -> 10 for new worlds. Old recorded versions
retain the previous planner branch, including exact v9 golden fingerprints.
No save-schema/worldgen/hydrology/route version changes or new persistent fields.
Existing NPC workplace bindings, CropPlot, SoilState, reservations and physical
containers own all runtime state. No new RNG namespace or RNG draw-order change.
No automatic old-world rebuild/migration; use a new world to see v10 layouts.

## Validation

15 new tests cover connected size/geometry, perimeter fencing, disjoint barn and
shed, physical gate/collision, reachable crop parcels, bounded water refusal,
generation order/cache round-trip/rebuild, preservation of authoritative delta
rows, v9 committed golden, farmer storage binding, two-worker reservations,
healthy-versus-stressed planting, real seed return and new-town seed conservation.
Fixed-tick execution moves a farmer and plants multiple real crops while the
player position remains unchanged; seed cargo plus planted plots is conserved.
The representative SQLite save runs `tools/verify_save.py` and passes integrity.

Targeted integration includes settlement foundations, yards/population, civic
services, exact professions, property access, economy and workplace logistics.
85 direct-integration tests passed before the additional fixed-tick test; the
15-test farm module passed separately. A bounded one-seed/year smoke soak had no
invariant errors, but that seed realized no settlements/NPCs and is NOT farm proof.
Compileall and `git diff --check` pass. The bounded runner on this Windows host
can print PASS after unittest failure: inspect the actual unittest summary.
Updated old tests only for intentionally moved farm sheds and current-version
pinning; lost civic/lodging capacity was fixed in the planner, not excused.

Headless real-map preview: `artifacts/dev45-farm-map-preview.png`, rendered with
`python -m tools.preview_dev45_farms` and visually inspected. This is presentation
and offline proof, not a live-play or full release-hardening claim.

## Performance / limitations / next dependency

Siting tries at most twelve rank-sized compounds inside one bounded prepared
region. Geometry is projected during preparation, never rendering/hover. The
largest field has fewer than 3,000 cells. Large fields bypass the legacy outdoor
site's quadratic medoid computation. Farmer candidates scan only active-town
plan pieces/fields on planning, not all world populations per presentation frame.

Fields still need available labor, seeds, growth time and successful physical
travel; they do not appear instantly planted. Crop varieties without an existing
exact profession process are not yet actively tended by named farmers. A site
without a fully dry/legal compound can remain without a v10 field; earthworks,
terrain-adaptive reduced compounds and an explicit old-world migration are
future work. Larger non-farm buildings, spaces/portals, six house assets, general
failed-path recovery, social learning, claim campaigns and construction remain
pending. Next dependency: finish non-farm parcel/site sizing, then persistent
space identity before exterior shells/interior transitions.
