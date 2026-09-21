# WORLDSEED RC14 Dev16 Validation

## Static/data checks

- `python -m compileall -q worldseed tools` — PASS
- visual registry/readability/terrain variant tests — PASS
- copper vein, ore, ingot and smelting process load through the content registry — PASS
- v7 cave-mouth assets retain alpha transparency and are referenced by `visuals.json` — PASS

## New Dev16 regression coverage

`tests/test_dev16_caves_crafting.py` verifies:

- future tagged ground terrain automatically joins the mesher while ore remains excluded
- deterministic terrain-aware v7 cave mouth + reciprocal shaft depth
- shallow/sedimentary/fracture/crystalline level metadata
- shallow coal/aquifer, mid-depth copper, deeper iron bias
- material discovery -> simple auto recipe -> compound experiment progression
- discovery-tree browsing is observational
- discovery state survives serialization round-trip
- copper has a mine-to-smelt content chain

`tests/test_local_terrain_transitions.py` now explicitly requires grass/floodplain blending and keeps authored hard features crisp.

## Deterministic audits

### Terrain meshing

Command:

`PYTHONPATH=. python tools/audit_terrain_meshing.py`

Result:

- 30 blendable terrain IDs
- 435 pair profiles validated
- grass <-> floodplain: blend
- PASS

### Caves/geology

Command:

`PYTHONPATH=. python tools/audit_caves_v7.py`

Frozen seed: `dev16-cave-audit`

Result:

- 27 natural entrances in an 11x11 cave-macro-cell window
- entrance connector depth range 3..10
- z -1: cave floor 6015, wall 2819, aquifer 290, coal 284
- z -3: cave floor 5839, wall 2893, coal 351, aquifer 248, copper 47, iron 30
- z -6: cave floor 4603, wall 4231, iron 382, aquifer 192
- z -10: cave wall 5635, floor 3346, iron 428; no coal/copper leakage
- PASS

## Regression cohorts run green

Affected/regression cohorts were run individually because the complete historical suite exceeds the sandbox's single-command timeout. Green cohorts include:

- local terrain transitions + Dev16 caves/crafting
- contextual water/world presentation/terrain variants/assets
- systems
- RC5 gameplay
- RC6 sandbox
- RC14 hydrology
- legacy v0.4.1 compatibility
- v6 water/swimming
- persistence + deterministic replay
- RC10 worldgen + RC13 pregeneration
- core worldgen
- inventory retained-navigation flow and crafting action-hub backtracking

No failing affected test remains in the packaged tree.

## Environment limitation

`pygame-ce` is a declared runtime dependency but is not installed in the execution sandbox, and network installation is unavailable. Therefore SDL-specific tests that require a real pygame import remain skipped/unavailable here. The graphical menu methods compile successfully and the shared widget/navigation layer was exercised through fake terminal adapters. A final live-window visual pass should be performed on the target Windows environment.
