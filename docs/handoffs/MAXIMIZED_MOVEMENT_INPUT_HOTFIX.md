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

The normal fast gate now runs this exact pygame regression in the existing
Dev41 realtime/free-movement step, so future movement-input changes exercise the
release-starvation case on the Windows dummy-display runner before later suites.

## Follow-up: maximized-screen lag and remaining stuck input (2026-10-11)

The first fix did not cover two still-unbounded graphical workloads:
`_animate_idle_effects` always built weather layers *before* looking for a
queued keyboard event, and the continuous movement path still requested a
complete world paint for every 16-ms physics update.

This follow-up takes already-queued input before any idle weather composition,
renders continuous movement at a separate 30-Hz small-window / 20-Hz large-
window cadence without slowing simulation movement, and flushes final
fractional position on KEYUP. Window size changes are idempotent; SDL2
already-resized surfaces are reused rather than calling `set_mode` on an
unchanged dimension. Full-viewport lighting buffers are reused and skipped
when transparent. Animated weather is capped by map pixel area to avoid
eating the entire frame budget at native maximized resolutions.

Four targeted SDL dummy-display tests validate release-before-effects,
duplicate max-window events, redraw throttling without losing movement
updates, and final-frame release flushing. The existing queued-KEYUP regression
remains in the Windows fast gate.

Remaining verification: manual maximize/unmaximize gameplay on an actual
desktop/GPU; SDL dummy rendering cannot reproduce all native window-manager
and driver scheduling behavior. No change to save/worldgen/physics semantics.

The final render-priority pass also ensures no idle weather animation is
composited before a movement frame that is already due. When a movement key
is actively held, weather is rendered as part of that movement frame rather
than separately between physics updates. The dedicated Windows regression
asserts that due movement cannot invoke the expensive idle compositor first.
