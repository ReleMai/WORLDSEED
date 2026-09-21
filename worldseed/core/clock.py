from __future__ import annotations
from dataclasses import dataclass

MINUTES_PER_DAY = 1440
DAYS_PER_SEASON = 30
DAYS_PER_YEAR = DAYS_PER_SEASON * 4
SEASONS = ("spring", "summer", "autumn", "winter")

@dataclass(slots=True)
class GameClock:
    minute: int = 8 * 60

    @property
    def day_index(self) -> int:
        return self.minute // MINUTES_PER_DAY

    @property
    def year(self) -> int:
        return self.day_index // DAYS_PER_YEAR + 1

    @property
    def day_of_year(self) -> int:
        return self.day_index % DAYS_PER_YEAR

    @property
    def season(self) -> str:
        return SEASONS[(self.day_of_year // DAYS_PER_SEASON) % 4]

    @property
    def day_of_season(self) -> int:
        return self.day_of_year % DAYS_PER_SEASON + 1

    @property
    def hour(self) -> int:
        return (self.minute % MINUTES_PER_DAY) // 60

    @property
    def minute_of_hour(self) -> int:
        return self.minute % 60

    def advance(self, minutes: int) -> tuple[int, int]:
        old = self.minute
        self.minute += max(0, int(minutes))
        return old, self.minute

    def label(self) -> str:
        return f"Y{self.year} {self.season.title()} {self.day_of_season}, {self.hour:02d}:{self.minute_of_hour:02d}"
