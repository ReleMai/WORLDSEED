from __future__ import annotations

from worldseed.config import ACTIVE_TICK_REPLAY_LIMIT_MINUTES, SIMULATION_TICK_MINUTES


def crossed_simulation_ticks(start_minute: int, end_minute: int) -> range:
    """Return fixed WORLDSEED tick boundaries crossed by a time advance.

    The boundaries are anchored to absolute world minutes so identical command
    sequences produce identical execution points regardless of frame rate.
    """

    start = int(start_minute)
    end = int(end_minute)
    step = max(1, int(SIMULATION_TICK_MINUTES))
    if end <= start:
        return range(0)
    first = ((start // step) + 1) * step
    if first > end:
        return range(0)
    return range(first, end + 1, step)


def should_replay_active_ticks(delta_minutes: int) -> bool:
    """Whether an advance should replay exact nearby-NPC ticks.

    Large waits intentionally fall back to existing coarse/hourly simulation;
    this preserves bounded catch-up cost while normal gameplay remains exact.
    """

    delta = max(0, int(delta_minutes))
    return 0 < delta <= int(ACTIVE_TICK_REPLAY_LIMIT_MINUTES)
