# Isolated NPC/job lab handoff

Baseline: `935e1260047ac4477b150b85b2831cc7829c0272` on canonical `main`.
Complete checkout preflight passed before edits. This work adds an optional
development entry point; game release, geography and save versions stay pinned.

## Scope and public APIs

- `worldseed/labs/npc_jobs.py`: `NPCJobLab(scenario, seed, workers)`, `step(ticks)`,
  `run(minutes)` and detached JSON-compatible `snapshot()`. Five authored finite
  scenarios exercise extraction/trade/craft, varied workshops/fields, missing
  inputs, disconnected work areas and exclusive station contention.
- `npc_job_viewer.py`: independent pygame inspection, pause/step/speed controls,
  scenario/reset and JSON export. Drawing is observational. `run_viewer` returns
  the final active lab so exports follow scenario/reset changes.
- `npc_job_cli.py`, root Python/Windows launchers: visual launch or seeded,
  bounded headless reports. Headless mode does not import pygame. CLI exits
  nonzero for invariant warnings and invalid arguments; expected path stalls are
  explanatory diagnostics.
- The guide, root README and documentation index expose the lab. The playtest
  packager includes both launchers; the automatic fast gate includes lab tests.

## Authority, state and timing

The map is explicit test geography. All actors, cargo, stores, labor and station
reservations use the existing `LivingWorldState` contracts. The shared NPC,
profession, activity, goods, storage and commerce implementations execute the
work. Observation subclasses count completed recipes/extraction/farming/meals
without replacing those algorithms. No anonymous economy production runs in the
lab. Physical goods totals also include ground piles.

Every instance begins at minute 420 with finite test capital, runs five-minute
fixed ticks and hourly needs/decisions, refreshes its fixed experiment assignments
daily, and stops after at most seven simulated days. At the limit the viewer
pauses and preserves the inspectable final state. Up to eight workers per job are
allowed. Shared reservation, transfer and transaction authorities control work,
carrying capacity, paid purchases and deposits.

No new game persistent fields or migration. No saved world is opened. JSON
snapshots are observations, not resumable saves. Existing RNG namespaces for
profiles, yields, goals and weather are reused; no global random source is added.
Event/history retention is bounded; completed reservations not referenced by
queued tasks retain at most 200 audit rows. The existing transfer/market log
limits continue to apply; lab counters retain cumulative counts.

## Validation

- Python compilation and whitespace checks.
- 22 lab regressions: autonomous tree/home/market/carpenter production chain;
  per-item/cash conservation and determinism across all five scenarios;
  scarce inputs with legitimate meal purchases; physical blockage; exclusive
  stations; detached read-only snapshots; valid bounded advances; worker spawning
  and every workshop job producing at one and eight workers; actual paid/unpaid
  meal accounting; headless JSON/pygame isolation; viewer pause/resize/limits,
  reset/scenario behavior and final export.
- 35 existing direct integration tests for NPC production/commerce, professions,
  workshop expansion and living routines.
- One-day scenario probes with two workers per job: zero invariant warnings.
- Seven-day workshop probe (`seed=review`, two workers per job): zero warnings,
  zero cash drift, 864 completed station/field activities.
- Dummy SDL render inspection at 320x240 and 1180x760, including selectable
  crop/ground-pile observations. No graphical tests skipped.

This is targeted development validation. The deliberate manual full-release
suite and long world soaks were not run for this separate developer tool.

## Limits and next dependency

The lab uses outdoor authored bindings, not a generated village. It does not
cover mining trips, continuous interiors, door security, regional transport or
distant aggregate production. Starter mature crops allow harvesting without
waiting for a whole growing season; trees and initial stores are finite. Crop
weather/growth reuse the bounded environment rules but do not establish full
generated-climate integration. Job choice is fixed by the experiment rather than
the daily settlement allocator.

The next useful work is to preserve a specific observed stall or supply/cash
imbalance as a new deterministic scenario, then fix the owning shared system.
Generated settlement/interior scenarios should be added deliberately and retain
the game's property, plan, storage and labor authorities.
