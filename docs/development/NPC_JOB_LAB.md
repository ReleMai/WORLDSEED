# Separate NPC/job simulation lab

The lab runs the existing NPC decision, pathfinding, activity reservation,
profession, carried-goods, home-storage and market systems on a small authored
test map. It is a separate entry point with fresh in-memory state. It does not
launch the game, read a saved world, create a game database or change world
generation. Changes to shared job logic are exercised here automatically.

Install from the repository root using the usual dependencies:

```sh
python -m pip install -e . "Pillow>=10,<12"
python run_npc_job_lab.py
```

On Windows, `RUN_NPC_JOB_LAB.bat` opens the same viewer. The installed-package
entry point is `python -m worldseed.labs.npc_job_cli`.

## Experiments

| Scenario | Purpose |
| --- | --- |
| `supply_chain` | Lumberjacks extract wood, carry it to storage and sell surplus; carpenters buy inputs and make bowls. |
| `workshops` | Exercise several real workshop jobs with finite starter inputs. |
| `scarcity` | Observe work planning when the required inputs are unavailable. |
| `blocked_path` | Observe physical movement when a wall disconnects the work area. |
| `station_contention` | Observe multiple carpenters competing for a shared bench reservation. |

Use `--list-scenarios` for current descriptions. `--workers 1..8` controls workers
per job; contention ensures multiple workers. `--seed` fixes the deterministic
worker profiles. The map and starter inventory are fixed test fixtures, so seed
changes do not imply a different procedural village.

```sh
python run_npc_job_lab.py --scenario workshops --workers 2 --seed trial-01
python run_npc_job_lab.py --scenario station_contention --workers 4
python run_npc_job_lab.py --headless --scenario supply_chain --minutes 720 --output logs/npc-chain.json
python run_npc_job_lab.py --headless --scenario scarcity --minutes 1440 --seed trial-01
```

Headless mode does not import pygame. It prints the final snapshot as JSON and
optionally writes that same snapshot to `--output`. Exit status is nonzero for
reported invariant violations or invalid arguments. Waiting for supplies is
expected in scarcity experiments and is not itself a conservation failure.

The lab begins at 07:00. Each worker follows the same personal daily schedule
used in the game: meals, work, leisure and sleep vary with the worker's profile,
skills and needs. Urgent needs can interrupt planned activities. Advances use
the configured one-minute simulation tick anchored to game time, with hourly
needs updates and schedule changes on the fixed tick. Every job keeps its real
duration and reservation; changing viewer speed changes how quickly ticks are
requested, rather than producing extra work per frame.
Experiments are limited to seven simulated days per lab instance. Reset starts
the original scenario and seed again.

## Observation and controls

The viewer starts paused. Space pauses/resumes, Right advances one tick and R
resets. The toolbar selects scenarios and speed, expressed in game minutes per
real second. Normal speed is two game minutes per second, matching the game's
new default. The higher settings are 8, 24 and 60 game minutes per second.
Click a worker to inspect its goal, personal timeline, current schedule block,
queue, cargo, skills, needs and money; click stations/storage for their records.
Scroll the detail panel for longer queues and inventories. Escape
closes the lab. The map, inspector and event log read detached snapshots.
Resizing and inspecting do not advance simulation time.

Reports contain worker timelines, current schedule blocks, task queues,
inventories, skills and needs; container
contents; market goods and cash; station reservation records; totals and recent
events. Goods totals count each current inventory, container and market ledger
once. Transfers and transactions are audit records, not additional cargo.
Cash drift, negative quantities and overlapping exclusive stations are checked.
Recipe inputs/outputs, extraction and actual meal completions reconcile the
goods totals. Nonfatal path-stall diagnostics appear separately from invariant
warnings, so the deliberately blocked scenario still exits successfully.
History and reports are bounded, so event/counter metrics should be used when
comparing longer runs instead of relying on every historical record remaining.

For a useful experiment, keep scenario, seed, worker count and elapsed minutes
identical across two revisions. Compare completed activities, market outputs,
carried or stored goods, cash and queued actions. A stalled worker's queue and
reservation help distinguish missing inputs from an unreachable destination or
an occupied station. First observe the cause, then improve the owning system
and preserve the reproduced behavior as a regression test.

## Extending the lab

`worldseed/labs/npc_jobs.py` owns scenario setup and finite-world adapters.
`npc_job_viewer.py` owns observation and controls; `npc_job_cli.py` owns launch
and JSON export. Scenarios must create real `NPCState`, containers, plan
fixtures and resources, then let shared systems plan and execute. Do not import
test fixtures, copy a profession algorithm into the lab, grant goods each tick
or bypass physical transfers to make an experiment appear successful.

The first lab focuses on outdoor job loops. It does not validate generated
village geometry, locked doors, continuous interiors, mining trips, weather,
the full generated climate/ecology or the distant aggregate economy. Starter goods are explicit test
capital and are finite. Farming harvest fixtures do not model a full growing
season. These wider integration cases remain covered by the game tests and can
be added as separate lab scenarios later.

Run focused validation under a deadline:

```sh
python -m compileall -q worldseed tools tests
python -u tools/run_ci_check.py --name npc-job-lab --timeout 180 -- python -u -m unittest -v tests.test_npc_job_lab tests.test_npc_production_economy tests.test_phase4_professions tests.test_phase4_workshop_expansion tests.test_npc_living_routines
```

Graphical tests require pygame-ce, including in dummy SDL mode. The automatic
fast gate includes the lab regression module. This development check does not
replace the manual full-release suite.
