# Maximized-window movement input hotfix

Date: 2026-10-11

Baseline: canonical `ReleMai/WORLDSEED` main at
`e8df00d847bb7946fda08691ba65063a22540f08`.

## Reproduced root cause

WORLDSEED's continuous movement pump ran before the pygame event queue was
serviced. In a smaller window, rendering commonly returned to `read_key()`
quickly enough that the next pass saw the queued `KEYUP`. In a maximized
window, a frame can take longer than the 16 ms free-movement cadence. That made
`_pump_free_movement()` advance the player and immediately return
`UI_REDRAW` on every pass before pygame could consume the release event.

The result exactly matched the reported symptom: after releasing W/A/S/D or an
arrow key, the internal held-direction state could remain active and continue
moving until collision caused the movement callback to return false. Only then
did the event loop reach the waiting `KEYUP`.

## Fix

`worldseed/ui/pygame_terminal.py::read_key()` now polls one already-queued
pygame event before realtime simulation or continuous movement is advanced.
Queued keyboard releases, focus changes, resize events, mouse input and quit
events therefore cannot be starved by a render/movement redraw loop. When no
event is pending, the existing realtime and movement timing behavior is
unchanged.

The fix deliberately preserves event order. It does not drain `KEYUP` events
out of order, which would make a quick KEYDOWN+KEYUP pair look like a new held
press.

## Regression coverage

`tests/test_rc14_pygame_behavior.py` now seeds a held D key, makes another
continuous movement step immediately due, then queues D `KEYUP` followed by
Escape. The expected behavior is that the queued release/escape are processed
before any additional movement callback. The test also asserts that the held
movement state is cleared.

No save schema, world generation, simulation authority, movement speed or input
bindings changed. This is an event-priority/input-latency correction only.
