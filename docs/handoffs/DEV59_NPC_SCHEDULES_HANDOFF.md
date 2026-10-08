# RC14 Dev59 — Personal NPC schedules and faster simulation

Baseline: canonical `ReleMai/WORLDSEED` main at
`5a6e86a5588e3e4ad8e2a0d7b4d545c0332ca6ae`. Engine/package:
`1.0.0-rc14-dev59` / `1.0.0rc14.dev59`.

## Result

The game and isolated NPC/job lab consume the same derived personal schedule.
Adults have eight work hours split by a half-hour lunch, three meals, personal
time, leisure and eight sleep hours. Outdoor and food workers start earlier;
stable identity offsets stagger starts by 0/15/30 minutes. Guards receive one
of three eight-hour shifts and sleep outside duty, including daytime sleep for
night guards. Children have six school hours; unemployed/retired adults have
free time instead of fictional work.

Free time chooses existing executable activities: socializing, study, worship,
rest or recovery. Needs, skill proficiency, traits, age and occupation affect
that choice without moving work/sleep hours. Urgent hunger, thirst, exhaustion
and injury retain priority. Schedules are preferences rather than guarantees
that every destination or resource is available.

Safe AI routines reconsider their goal at phase boundaries. Reserved profession
batches, extraction trips, paid commerce, storage transfers, deliveries and
door-answer chains complete through their existing authorities before a
schedule can replace them. Cargo and reservations are never discarded by a
shift transition. Voluntary daytime rest recovers before releasing the actor;
a stale rest goal cannot keep a recovered resident indoors indefinitely.
An indoor exit consumes that tick's physical action.

## Timing

| Setting | Previous | Dev59 |
| --- | --- | --- |
| Real seconds per game minute | 1.0 | 0.5 |
| Local simulation tick, game minutes | 5 | 1 |
| Default lab speed, game minutes per second | 5 | 2 |

Game NPC movement updates are ten times more frequent in real time. Work and
other timed activities keep absolute game-minute durations, so their wall-time
progress doubles with the game clock. Hourly needs, daily aggregate production,
reservation completion and interior half-hour recovery remain on their existing
game-time boundaries; extra ticks do not mint extra goods, cash or learning.
The faster clock also advances other real-time game systems twice as quickly.

The lab's speed controls now explicitly use game minutes/second: 2, 8, 24 and
60. Its default matches the game; Right steps one game minute. Long experiment
limits, five-minute real-time catch-up cap, combat pause and bounded coarse
long waits are retained. Stall diagnostics measure sixty elapsed game minutes.

## Ownership and compatibility

- `systems/npc_schedule.py` derives immutable, gap-free daily blocks from existing
  NPC state. New deterministic RNG namespace: `npc-schedule`.
- AI tags newly generated task dictionaries with `schedule_goal`. Existing
  generic task serialization preserves it; legacy/unmarked plans finish before
  scheduled AI takes ownership. First observation after load preserves a pending
  plan until a boundary, except urgent safe replanning.
- No new persistent NPC fields, schema migration or geography changes. Save
  schema 3 and all generation versions remain unchanged. Transient schedule
  tokens are pruned for removed/dead actors and are not serialized.
- Known NPC profiles expose the current block and daily timeline through existing
  pageable screens. Unknown NPC identities retain their knowledge boundary.
- Lab snapshots and graphical inspector show the same timeline. Drawing and
  snapshotting remain observational.

## Validation

- Compile of `worldseed`, `tools`, `tests` and `git diff --check`: pass.
- Final game/schedule/cadence/interior/profession/conservation group: 157 tests,
  pass (30.2 seconds; 180-second bounded runner).
- Lab/UI group: 34 tests, pass (115.7 seconds; 180-second bounded runner).
- Replay determinism: both tests pass in separate 90-second bounded checks
  (31.5 seconds in-process, 43.2 seconds across processes). The initial combined
  replay check reached its 90-second deadline during the second test; repeated
  world initialization was the expensive step, so the checks were split without
  increasing the limit or changing simulation behavior.
- One-seed, one-year full-policy smoke: pass, 120 simulated days and no invariant
  errors. Offline advance used 604 meaningful boundaries rather than minute
  replay. Initialization plus validation took 36.5 seconds.
- Representative equipment, in-flight trade/delivery, interior and multi-floor
  SQLite save round trips and `verify_save.py` pass within the targeted suite.
- Actual graphical launcher child-process smoke under dummy SDL: pass. Small
  and large render surfaces remain observational, normal speed advances two game
  minutes per real second, and manual step advances one minute. The complete
  selected-worker timeline was visually inspected.
- Automatic fast gate now includes the new model and integration regressions.

193 targeted tests passed overall. This is development validation; the full
manual release/nightly gate was not run.

The previous main's automatic gate already failed
`InteriorPortalTests.test_real_stable_door_entry_preserves_stocks_and_containers`.
The failure was reproduced in a detached, unchanged baseline checkout. Dev58's
intentional furniture preparation registers new empty physical inventories,
while the old assertion required an identical container-key set. The regression
now checks every original container ID/items and aggregate stocks unchanged,
requires all newly registered inventories empty, and verifies repeated entry is
idempotent. Production/storage code was not changed to repair this old assertion.

## Follow-up boundaries

The laboratory remains a small prepared world and does not reproduce terrain
generation, player combat or full interior layouts. Schedules use existing job
and leisure execution paths; specialized leisure content, editable calendars,
weekends and holidays remain future work. Distant aggregate production keeps
its existing authority and does not become a minute-by-minute named-worker loop.
