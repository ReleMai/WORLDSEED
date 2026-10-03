# Production-driven village generation (Dev49)

New worlds use settlement-plan contract 11. Terrain/hydrology/coasts/routes keep
their independently recorded versions. Existing worlds retain settlement
contracts 1–10; loading never rearranges their towns. Missing settlement metadata
retains the pre-Dev49 fallback of 10. Create a new world to test the new layouts.

## Planning pipeline

1. Regional civilization potential scores actual soil, freshwater, timber,
   stone, slopes, floods and transport opportunity. V11 checks a small buildable
   neighborhood around promising candidates and compares physically nearby
   competing anchors, rather than suppressing every neighboring region alike.
2. The authoritative settlement planner selects exactly two terrain-backed
   production systems. Crops/livestock still derive from their physical habitat.
3. The immutable v11 recipe catalog selects a production/culture/terrain grammar.
   Twelve recipes cover quarry fans/courts, timber webs/groves, field greens/
   ribbons, pasture loops/hamlets, shore ribbons/landing courts and mixed trade
   greens/crossroads. Normalized street targets rotate and scale with settlement
   rank; sparse secondary links connect districts without an all-to-all graph.
4. Farms reserve their large connected compound and separate barn court. Each
   mining/logging/fishing district gets its own scored, fully legal footprint,
   not a fixed offset from another industry. Resource-specific weights select
   dry work yards near the relevant natural opportunity.
5. Civic services, craft shops and housing consume remaining street frontage.
   Real service roads connect doorways without crossing another reserved lot.
   A final access pass relocates obstructing generated outdoor props within
   their own parcel. Housing/workplace capacity derives from these structures.

This is one physical-plan authority, not a second decorative village/economy.
The map's existing Local Economy section shows the selected layout. Generation
occurs during preparation, never drawing, hovering or moving.

## Extension points

`worldseed/data/settlement_layouts_v11.json` is the declarative catalog;
`systems/settlement_layouts.py` validates and selects immutable recipes. Each
recipe declares a namespaced ID, eligible resources, culture/physical preference
weights, six-to-ten normalized street targets, at most five secondary links,
rank target counts, frontage spacing and resource-district scoring overrides.
The resource definitions declare the supported worksite purpose, modest bounds
and physical-field weights. Inverse fields express slope/flood penalties without
negative scoring weights. Validation rejects bad references, duplicates,
unknown fields/ranks/resources, negative values and out-of-budget geometry.

To introduce another layout after release, create a new versioned catalog and
gate its planner path under the next settlement contract; do not edit v11 in
place. Keep old catalog/code paths so deleting a generated cache reproduces the
same town. A new production type also needs its real content, site realization,
worker/economy integration, habitat/access rules and tests before enabling its
catalog reference. Recipes cannot invent deposits, workers, stock or capacity.

Selection uses `settlement-production-layout-v11`; roads retain the independent
`settlement-road-bend` namespace. Region competition uses `civil-spacing-tie`.
Stable object/piece identities derive from parent IDs and final geometry.

## Verification and limits

Run the bounded catalog/siting/physical-plan tests through `run_ci_check.py`.
`tools/audit_settlement_layouts.py` checks five resource profiles across five
ranks, including solid-shell collision, final physical-road passability,
connected frontages/gates, parcel overlap, region margins, deposit restrictions
and exact derived capacity. Its default is explicitly a synthetic-terrain
matrix, not a live-world playtest. `tools/preview_dev49_layouts.py` renders actual
prepared settlement-map UI for visual review.

Siting checks a bounded civic core (six coarse and three fine finalists, at most
126 environment reads per raw region), not every possible world coordinate or
the full town footprint. The physical planner remains the final legality gate;
hostile terrain may leave lots undeveloped. This pass does not flatten oceans,
reroll strategic routes, introduce ports/terracing, or modify existing saves.
