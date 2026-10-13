# WORLDSEED timed actions — handoff

## User request
Crafting must advance the world while the work is taking place, not as a single
invisible time jump when the crafting interface is dismissed. Timed actions
should show a visual timer.

## Implementation
- `Simulation.execute` retains sole authority for command validation, success,
  costs, duration, and time. For committed positive-minute noncombat commands,
  the optional runtime-only `_action_progress_callback` advances the existing
  `_advance_time` clock in bounded slices; the normal single-advance path
  remains available for headless simulation/tests.
- The graphical backend redraws the world between simulation slices and paints
  an action name, progress percentage, and **actual elapsed game minutes**.
  Crafting and salvage panels remain visible as noninteractive overlays until
  the action finishes, then return to their normal retained UI.
- Work presentation lasts 0.35–5 seconds of wall time and never changes the
  in-game duration of recipes or waits. The realtime driver is re-baselined
  after the work animation to avoid charging the same real seconds again.
- Zero-time, read-only, combat/defense, and free-movement commands retain their
  existing immediate/continuous behavior. Holding a key/click during a timed
  action is ignored until the current transaction is complete.
- Indoor furniture resting uses the same UI progress path. No save schema,
  generation protocol, recipe database, or player inventory semantics changed.

## Tests
- `tests.test_action_progress`: fractional schedule monotonicity and exact
  minute conservation; graphical world redraw and retained craft window.
- `tests.test_salvaging.SalvagingCommandTests`: incremental authoritative
  engine minute accounting and no progress for rejected salvage.
- `WORLDSEED Fast Gate`: these tests run in the existing early diagnostics
  and Dev63 world-content suites.

## Follow-up considerations
- The current command transaction commits its recipe/material changes before
  showing work progression. Treat work as atomic: interrupting it halfway with
  a cancel button would require an explicit reservation/rollback system.
- The progress overlay deliberately avoids delaying movement and combat.
  They already have distinct real-time locomotion and attack animation.
