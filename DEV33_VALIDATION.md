# RC14 Dev33 — WORLDGEN v8 Phase 5 coastline materialization

Scope: convert the approved Dev32 coastal morphology read model into a
save-visible physical coastline for new worlds without rewriting existing v8
saves or replacing the recent atmosphere/tree/morel/cave visual work.

## What changed in the game

New worlds with coast morphology v1 can now physically contain:
- sandy shore;
- coastal gravel;
- rocky shore;
- impassable coastal cliffs;
- tidal flats;
- salt marshes;
- coastal wading water;
- shallow ocean;
- continental shelf water;
- deep ocean.

These are authoritative terrain IDs, not renderer-only decorations. They can
therefore affect collision, inspection, atlas output and later ecology/resource/
settlement/route systems. Dedicated new coast artwork is deferred; Dev33 reuses
approved rock, riverbank, floodplain and wetland art families.

Bathymetric terrain now consumes the Phase-5 continental-geometry shelf model
instead of deriving all ocean depth solely from the old local-slope distance
approximation.

## Compatibility

- WORLDGEN_VERSION remains 8.
- HYDROLOGY_VERSION remains 2.
- HYDROLOGY_MORPHOLOGY_VERSION remains 2.
- COAST_MORPHOLOGY_VERSION is 1 for new v8 saves.
- Existing saves missing coast metadata infer coast version 0.
- Coast version 0 keeps the pre-Dev33 shoreline materialization.
- Surface cache identity now includes coast version.
- The new cache table is additive; old surface cache rows remain readable only
  for coast version 0.
- Save schema remains 3.

## Performance

Detailed coast analysis is reused on an absolute 8-cell materialization lattice.
Exact geological elevation still determines land versus water per tile, so this
optimization does not snap the coastline into 8x8 blocks.

A regression test asserts that a 16x16 materialization window produces at most
four expensive coast-classifier misses after cache reset.

## Validation

Fast Dev33 gate:
- compileall;
- Phase-5 coast regression suite;
- pregeneration/surface-cache compatibility tests;
- atlas drag regression;
- content audit;
- visual audit;
- multi-seed coast audit.

The standard Dev33 workflow additionally runs the existing WORLDGEN v8,
Hydrology v2, climate, topography, promotion, atlas and playtest regression
suite and packages the build.

## Still open in Phase 5

- physical river-mouth distributaries/delta lobes;
- expanded estuary geometry from discharge + shelter/tidal context;
- spits and barrier-island candidates/materialization;
- dedicated visual art for rocky coast/cliff/gravel/tidal flat/salt marsh;
- larger multi-seed coast distribution calibration;
- explicit coast seam audit around prepared-domain boundaries;
- later Phase-6 substrate/soil refinement of shore material.
