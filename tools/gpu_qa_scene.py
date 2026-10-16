"""Explicit synthetic QA setup; never applied to normal worlds or player saves."""
from __future__ import annotations
from dataclasses import dataclass
from worldseed.core.clock import DAYS_PER_SEASON, SEASONS

QA_WEATHER = ('clear','cloudy','rain','storm','snow','fog')
QA_TIMES = {'noon':720,'night':0,'sunrise':360,'sunset':1080}


def qa_minute(season=None, time_of_day=None):
    if season is not None and season not in SEASONS:
        raise ValueError('invalid synthetic season')
    if time_of_day is not None and time_of_day not in QA_TIMES:
        raise ValueError('invalid synthetic time')
    return SEASONS.index(season or 'spring')*DAYS_PER_SEASON*1440+QA_TIMES[time_of_day or 'noon']


@dataclass(frozen=True, slots=True)
class PreparedWeather:
    """Fixture-wide weather authority shared by rendering and command systems."""
    kind: str

    def __post_init__(self):
        if self.kind not in QA_WEATHER:
            raise ValueError('invalid synthetic weather')

    def at(self, minute, x, y):
        rain={'rain':6,'storm':10,'snow':7}.get(self.kind,0)
        fog={'fog':85,'rain':18,'storm':39,'snow':20}.get(self.kind,0)
        cloud={'clear':0,'cloudy':84,'rain':86,'storm':100,'snow':91,'fog':65}[self.kind]
        return dict(kind=self.kind,rain=rain,fog=fog,cloud_cover=cloud,
            storm_intensity=80 if self.kind=='storm' else 0,visibility=4 if fog>=55 else 6 if rain else 8,
            temp_delta=-15 if self.kind=='snow' else 0,wind=2,wind_dx=900,wind_dy=250,
            wind_speed=85 if self.kind=='storm' else 40,humidity=80 if rain or fog else 45,
            wetness=0 if self.kind=='snow' else rain*10)
