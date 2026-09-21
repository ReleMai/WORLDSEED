"""Deterministic day/night lighting for WORLDSEED presentation.

Lighting is a read model: it depends on game time and current cloud/storm state
but does not mutate simulation. The renderer may consume the tint/darkness values
without becoming an authority over time or weather.
"""
from __future__ import annotations

from dataclasses import dataclass

from worldseed.core.clock import DAYS_PER_YEAR, MINUTES_PER_DAY

Q = 65535
LIGHTING_VERSION = 1


def _clamp_q(value: int) -> int:
    return max(0, min(Q, int(value)))


@dataclass(frozen=True, slots=True)
class LightingState:
    phase: str
    daylight: int
    ambient_light: int
    darkness_alpha: int
    tint_r: int
    tint_g: int
    tint_b: int
    sunrise_minute: int
    sunset_minute: int


class LightingSystem:
    """Season-aware surface illumination derived from the simulation clock."""

    def at(self, minute: int, cloud_cover: int = 0, storm_intensity: int = 0) -> LightingState:
        minute = max(0, int(minute))
        day = minute // MINUTES_PER_DAY
        tod = minute % MINUTES_PER_DAY
        day_of_year = day % DAYS_PER_YEAR

        # Smooth-ish four-season daylight cycle without floating-point astronomy.
        # Summer peaks around day 45, winter around day 105 in WORLDSEED's
        # 120-day year. Range is roughly 10.5h..13.5h.
        quarter = DAYS_PER_YEAR // 4
        if day_of_year < quarter:
            seasonal = day_of_year * 90 // quarter
        elif day_of_year < quarter * 2:
            seasonal = 90 - (day_of_year - quarter) * 90 // quarter
        elif day_of_year < quarter * 3:
            seasonal = -(day_of_year - quarter * 2) * 90 // quarter
        else:
            seasonal = -90 + (day_of_year - quarter * 3) * 90 // quarter

        sunrise = 360 - seasonal // 2
        sunset = 1080 + seasonal // 2
        dawn_start = sunrise - 60
        dusk_end = sunset + 60

        if tod < dawn_start or tod >= dusk_end:
            phase = "night"
            daylight = 6500
            tint = (24, 35, 58)
        elif tod < sunrise:
            phase = "dawn"
            t = (tod - dawn_start) * Q // max(1, sunrise - dawn_start)
            daylight = 6500 + t * 46000 // Q
            tint = (74, 61, 72)
        elif tod < sunset:
            phase = "day"
            # Midday is brightest; edges of the day stay slightly subdued.
            span = max(1, sunset - sunrise)
            progress = (tod - sunrise) * Q // span
            edge = abs(progress - Q // 2) * 2
            daylight = 61000 - edge * 8500 // Q
            tint = (255, 255, 255)
        else:
            phase = "dusk"
            t = (tod - sunset) * Q // max(1, dusk_end - sunset)
            daylight = 52500 - t * 46000 // Q
            tint = (79, 58, 75)

        cloud_cover = max(0, min(100, int(cloud_cover)))
        storm_intensity = max(0, min(100, int(storm_intensity)))
        daylight -= cloud_cover * 115
        daylight -= storm_intensity * 95
        ambient = _clamp_q(max(5000, daylight))

        # Darken only the world viewport. UI remains readable. Even at deep night
        # the floor is not absolute black so players can navigate before local
        # light-source gameplay is expanded.
        darkness_alpha = max(0, min(205, 205 - ambient * 205 // Q))
        return LightingState(
            phase,
            _clamp_q(daylight),
            ambient,
            darkness_alpha,
            int(tint[0]),
            int(tint[1]),
            int(tint[2]),
            sunrise,
            sunset,
        )
