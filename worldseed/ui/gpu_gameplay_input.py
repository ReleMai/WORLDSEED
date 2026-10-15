"""W2 input owner for the explicit GPU gameplay candidate.

This controller requests existing engine updates. Capture and GPU draw code never
own movement, collision, discovery, command effects or the simulation clock.
"""
from __future__ import annotations

from math import floor, isfinite
import time

from worldseed.core.coords import WorldPos
from worldseed.sim.commands import MoveCommand, PickupCommand, WaitCommand
from worldseed.sim.realtime import RealtimeSimulationDriver
from worldseed.ui.router import classify_key


def project_pointer(camera, x: float, y: float):
    """Project one window pixel without querying or changing the world."""
    if not all(isfinite(v) for v in (x, y)):
        return None
    if not 0 <= x < camera.width_px or not 0 <= y < camera.height_px:
        return None
    foot = camera.to_world(x, y, ground_z=camera.center.z)
    return WorldPos(floor(foot.x), floor(foot.y), int(foot.z))


class GpuGameplayInput:
    """Single event owner's held keys, focus and authoritative update boundary."""

    def __init__(self, simulation, *, now=None):
        self.sim = simulation
        self.realtime = RealtimeSimulationDriver(simulation)
        self.focused = True
        self.closed = False
        self._held = {}
        self._pressed = set()
        self._last = time.monotonic() if now is None else float(now)
        self.realtime.resume(self._last)
        self.sim.set_free_movement_enabled(True)

    @staticmethod
    def _key(key):
        return key.lower() if len(key) == 1 else key

    def press(self, key: str, *, repeat=False, now=None):
        """Reuse the sole global router; unsupported UI intents stay deferred."""
        key = self._key(key)
        intent = classify_key(key)
        if self.closed or not self.focused or repeat or key in self._pressed:
            return intent.kind
        self._pressed.add(key)
        command = None
        if intent.kind == 'move':
            if self.sim.combat_active():
                command = MoveCommand(self.sim.player_id, *intent.value)
            else:
                self._held[key] = intent.value
        elif intent.kind == 'wait':
            command = WaitCommand(self.sim.player_id, int(intent.value))
        elif intent.kind == 'pickup':
            command = PickupCommand(self.sim.player_id)
        if command is not None:
            self._held.clear()
            self.sim.execute(command)
            # Command time is already charged by execute. Discard presentation
            # or command wall time instead of charging it again on the next pump.
            self._last = time.monotonic() if now is None else float(now)
            self.realtime.resume(self._last)
        return intent.kind

    def release(self, key: str):
        key = self._key(key)
        self._pressed.discard(key)
        self._held.pop(key, None)

    def set_focus(self, focused: bool, *, now=None):
        self._held.clear()
        self._pressed.clear()
        self.focused = bool(focused)
        self._last = time.monotonic() if now is None else float(now)
        if self.focused and not self.closed:
            self.realtime.resume(self._last)
        else:
            self.realtime.pause()

    def update(self, now: float, *, sprint=False):
        """Call once after servicing queued releases/focus/window events."""
        now = float(now)
        if not isfinite(now):
            raise ValueError('input clock must be finite')
        dt = max(0., now-self._last)
        self._last = now
        if self.closed or not self.focused:
            return False
        advanced = bool(self.realtime.pump(now))
        if self.sim.combat_active():
            self._held.clear()
            return advanced
        directions = tuple(self._held.values())
        dx = int(any(x > 0 for x, _ in directions))-int(any(x < 0 for x, _ in directions))
        dy = int(any(y > 0 for _, y in directions))-int(any(y < 0 for _, y in directions))
        # Existing engine code owns dt clamping, normalization, actor fractions,
        # tile crossings, collision, stealth noise and local NPC interpolation.
        return bool(self.sim.update_free_movement(dt, dx, dy, bool(sprint)) or advanced)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self._held.clear()
        self._pressed.clear()
        self.realtime.pause()
        self.sim.set_free_movement_enabled(False)
