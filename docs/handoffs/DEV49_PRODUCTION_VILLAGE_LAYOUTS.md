# Dev49 production village layouts and civilization siting

Baseline: canonical main `79f21b50d46476fa05deea8420a1ad4437c3c4d4`, fetched and
workspace-preflight verified before edits. Original dirty D: checkout preserved;
implementation uses the attached `settlement-interior-research` checkout.

## Scope / contracts

`systems/settlement_layouts.py` + frozen `data/settlement_layouts_v11.json` provide
12 resource/culture/terrain-driven declarative grammars and strict validation.
`choose_layout()` returns immutable planning hints; `resource_definition()`
provides physical worksite bounds/purpose/scoring. The existing skeleton planner
projects these into the same persistent roads/parcels/structures used by local
collision, NPC jobs, housing, economy and history. Separate production districts,
larger variable street networks and final prop clearance replace fixed industry
offsets. Existing huge farm compounds and terrain crops/animal limits remain.
Mining districts also prefer real, bounded cave-mouth candidates when a fully
legal unoccupied yard fits; the preference never invents an underground vein.

Regional civilization v11 now checks buildable candidate neighborhoods, respects
provisional-vs-prepared geography, and bases site competition on actual nearby
anchors. All previous siting/layout branches remain available. Atlas Local
Economy shows the layout; navigation and keys are unchanged.

## Persistence / RNG / performance

Settlement plan generation version advances 10 -> 11 for new saves only; schema
remains 3, terrain worldgen remains 8, hydrology/coast/route versions unchanged.
No new persistent fields. Missing settlement-version metadata freezes at 10 in
database/app loading; explicit versions remain untouched. Cached-plan reload
skips generation, and cache deletion preserves physical damage deltas.

New RNG domains: `settlement-production-layout-v11` and `civil-spacing-tie`.
All other namespaces preserved. Immutable catalog cache has one entry; scratch
district/clearance data belongs to a bounded single-town preparation pass.
Regional candidate fitness reads at most 126 cells per raw region and never
realizes chunks/people. No planning was added to render/hover/movement paths.

## Verification

Added catalog, production-layout and civilization-siting suites plus a bounded
25-case synthetic terrain audit. Legacy v9/v10 skeleton and v1–v10 civilization
goldens stay exact. Tests cover order/RNG isolation, cache reload/rebuild,
SQLite damage-delta preservation, save integrity, version pinning, water/flood/
slope rejection, actual road/gate/frontage passability and derived capacities.
Direct farm/workshop/population/shell/map/regional-route regressions are included
in targeted validation; the real hydrology-aware Village Start path is checked.
Compileall and the new CI step are included in the coherent publication.

Completed local checks: catalog/siting/production suites, direct physical-plan,
farm/workshop/job/population/shell/map/route regressions; two 25-case matrices
(default seed and `dev49-second-seed`) have zero geometry/access failures.
The final integrated 44-test batch passed in 23.002s; the post-cave-preference
production/workshop batch passed 13 tests in 22.204s. A separate representative
Dev49 generated-plan SQLite save passed `tools/verify_save.py`. Compileall and
`git diff --check` passed. Existing v9/v10 plan goldens remain exact.
Visual QA then exposed a farm squeezed out by the new local street web. V11 now
reserves farm/pasture compounds before neighborhood streets, routes around them,
and requires every declared resource district in the suitable-land matrix.
The final farm-priority/production/craft batch passed 21 tests in 32.425s.

This is development-level focused validation, not full manual release hardening
or a live graphical playthrough. See the development guide for extension rules
and known limits. Next dependency: broader prepared-geography morphology tuning
(coastal orientation/terraces/ports) and population-driven district expansion,
using these same authoritative plans rather than independent layout engines.
