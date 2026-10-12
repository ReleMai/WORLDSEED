# WORLDSEED salvaging crash / indoor work / Fast Gate handoff

## Reported crash and evidence
Debug file provided by player: `WORLDSEED_DEBUG_20261012_182906_7560.jsonl`. Logged indoor requests at game minutes 760 and 767 to `StartSalvageGameCommand` returned `That outdoor action is unavailable inside.` Upon leaving the building, the same command at minute 773 raised `TypeError: Unknown command: StartSalvageGameCommand` from `Simulation.execute`.

## Root causes
- Command dataclasses and UI were added without connecting all five new command types to `Simulation.execute`. The existing zero-minute return guard already listed these types, but the actual dispatcher did not.
- The indoor command allowlist omitted `StartSalvageGameCommand`, perk allocation/respec and workshop dossier research.
- `_quick_salvage` ignored the `QuickSalvageCommand.count` property, so the Scavenging batch perk was never applied through the live game command.
- Broader Fast Gate had two independent historical assumptions: `test_crafting_quality_progression` expected field discovery of a forge-required recipe to consume metal; `test_crafting_expansion` assumed every station-only recipe could be discovered without a station, contrary to the new physical-workshop discovery rules.

## Fix
- Register the tabletop start, perk purchase, respec, and dossier research commands in real simulation execution, with the same authenticated player-actor validation and indoor allowlist as legacy salvaging.
- Route quick work through `quick_batch` including the commanded count. Reject invalid commands without time or inventory mutation.
- Preserve the ability to finish a saved tabletop project even after crossing the indoor/outdoor boundary.
- Modernize stale crafting tests to invoke station-bound recipes at their actual workshop; preserve the field-hint versus workshop-discovery distinction.
- Extend the focused Salvage Tabletop workflow to cover the indoor engine and Fast Gate's two failing crafting suites.

## Verification
Run `.github/workflows/salvage-tabletop-check.yml` (targeted on validation branch) and `.github/workflows/fast-gate.yml` on `main`. Confirm the new outdoor crash and indoor blocking are both covered by `tests/test_salvaging.py` live Simulation tests. Confirm that the crafting tests verify actual material retirement instead of accepting a no-consumption field hint.

## Future
The current work is about correctness and regression gates, not a redesign of the three authored minigame layouts. Keep expanded world smoke and other unrelated regressions visible rather than claiming all tests are green without their run results.
