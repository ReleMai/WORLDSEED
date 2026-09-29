from __future__ import annotations

import time

from worldseed.config import REALTIME_MAX_CATCHUP_MINUTES, REALTIME_SECONDS_PER_GAME_MINUTE


class RealtimeSimulationDriver:
    """Convert monotonic wall time into bounded authoritative game minutes.

    The UI owns neither the clock nor simulation effects.  It only asks this
    controller to pump; the controller calls the simulation's explicit
    real-time advancement API.  Supplying ``now`` keeps the conversion fully
    testable without sleeping.
    """

    def __init__(self, simulation, *, seconds_per_game_minute: float = REALTIME_SECONDS_PER_GAME_MINUTE,
                 max_catchup_minutes: int = REALTIME_MAX_CATCHUP_MINUTES):
        self.simulation = simulation
        self.seconds_per_game_minute = max(0.05, float(seconds_per_game_minute))
        self.max_catchup_minutes = max(1, int(max_catchup_minutes))
        self._last = None
        self._accumulator = 0.0
        self.paused = False

    def resume(self, now: float | None = None) -> None:
        self.paused = False
        self._last = time.monotonic() if now is None else float(now)
        self._accumulator = 0.0

    def pause(self) -> None:
        self.paused = True
        self._last = None
        self._accumulator = 0.0

    def pump(self, now: float | None = None) -> int:
        current = time.monotonic() if now is None else float(now)
        if self.paused:
            self._last = current
            return 0
        if self._last is None:
            self._last = current
            return 0
        elapsed = max(0.0, current - self._last)
        self._last = current
        self._accumulator += elapsed
        minutes = int(self._accumulator / self.seconds_per_game_minute)
        if minutes <= 0:
            return 0
        minutes = min(minutes, self.max_catchup_minutes)
        self._accumulator -= minutes * self.seconds_per_game_minute
        # Discard excess backlog after a stall.  Offline advancement owns long
        # absences; an unfocused window must not burst through hours on return.
        cap = self.seconds_per_game_minute * self.max_catchup_minutes
        self._accumulator = min(self._accumulator, cap)
        self.simulation.advance_realtime(minutes)
        return minutes
