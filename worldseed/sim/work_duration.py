"""Bounded duration adjustments for successfully committed player work.

Existing recipe/resource skill scaling remains with its owning system. Callers
can supply a skill only for work that does not already apply one. This module
has no simulation, rendering, RNG or persistence side effects.
"""
from __future__ import annotations


def adjusted_work_minutes(minutes: int, *, skill: int = 0, stamina: int = 100,
                          wound_severity: int = 0, tool_quality: int = 0,
                          rain: int = 0, wind_speed: int = 0) -> int:
    if minutes <= 1:
        return max(0, int(minutes))
    factor = 100 - min(25, max(0, int(skill)) * 3)
    factor += min(45, max(0, int(wound_severity)) // 5)
    factor += 15 if stamina < 25 else 7 if stamina < 50 else 0
    factor -= min(12, max(0, int(tool_quality)) * 2)
    factor += min(30, max(0, int(rain)) * 3)
    factor += min(10, max(0, int(wind_speed) - 30) // 7)
    factor = max(55, min(180, factor))
    return max(1, (int(minutes) * factor + 99) // 100)
