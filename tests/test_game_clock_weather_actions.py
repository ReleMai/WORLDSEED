"""Dev65 clock controls, time modifiers, weather fronts and render budget."""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from worldseed.core.coords import WorldPos
from worldseed.entities.components import Vitals
from worldseed.sim.commands import CraftCommand, GatherCommand, StoreCommand
from worldseed.sim.engine import Simulation
from worldseed.sim.realtime import RealtimeSimulationDriver
from worldseed.systems.environment import WeatherSystem


class FakeSim:
    def __init__(self):self.minutes=0
    def advance_realtime(self,minutes):
        self.minutes+=minutes
        return minutes


class GameSpeedTests(unittest.TestCase):
    def test_speed_multipliers_pause_and_no_resume_catchup(self):
        simulation=FakeSim()
        driver=RealtimeSimulationDriver(simulation,seconds_per_game_minute=1,max_catchup_minutes=5)
        driver.resume(0.0)
        driver.set_speed(2,0.0)
        self.assertEqual(driver.pump(1.0),2)
        driver.set_speed(3,1.0)
        self.assertEqual(driver.pump(2.0),3)
        self.assertTrue(driver.toggle_pause(2.0))
        self.assertEqual(driver.pump(400.0),0)
        self.assertFalse(driver.toggle_pause(400.0))
        self.assertEqual(driver.pump(401.0),3)
        self.assertEqual(simulation.minutes,8)
        driver.resume_for_movement(401.0)
        self.assertEqual(driver.speed,1)
        self.assertEqual(driver.pump(402.0),1)

    def test_bad_speeds_rejected_and_pause_kept_during_movement(self):
        driver=RealtimeSimulationDriver(FakeSim(),seconds_per_game_minute=1)
        for speed in (0,4,1.5,-1):
            with self.subTest(speed=speed),self.assertRaises(ValueError):
                driver.set_speed(speed)
        driver.set_speed(3,0.0)
        driver.pause()
        driver.resume_for_movement(100.0)
        self.assertTrue(driver.paused)
        self.assertEqual(driver.speed,1)


class WorkDurationTests(unittest.TestCase):
    def duration(self,*,skill=0,wounds=(),stamina=80,rain=0,tool=0):
        from worldseed.entities.components import Inventory
        climate=SimpleNamespace(at=lambda *_:{
            'rain':rain,'wind_speed':75 if rain else 10})
        fake=SimpleNamespace(
            player_skill=lambda _:skill,
            state=SimpleNamespace(player_wounds=list(wounds)),
            entities=SimpleNamespace(try_get=lambda *_:SimpleNamespace(stamina=stamina),
                                     get=lambda *_:Inventory()),
            player_id=1,interiors=None,
            player_pos=WorldPos(0,0,0),
            resources=SimpleNamespace(tool_power=lambda *_:tool),
            environment=SimpleNamespace(weather=climate),
            clock=SimpleNamespace(minute=600),
        )
        return Simulation._work_minutes(fake,GatherCommand(1),60)

    def test_work_duration_factors_and_clamps(self):
        basic=self.duration()
        self.assertLess(self.duration(skill=8,tool=5),basic)
        self.assertGreater(self.duration(wounds=({'severity':90},),stamina=12),basic)
        self.assertGreater(self.duration(rain=9),basic)
        self.assertGreaterEqual(self.duration(skill=60,tool=20),1)

    def test_ordinary_commands_do_not_gain_modifiers(self):
        fake=SimpleNamespace()
        self.assertEqual(Simulation._work_minutes(fake,StoreCommand(1,'x',1),1),1)


class PersistentWeatherTests(unittest.TestCase):
    @staticmethod
    def model():
        climate=SimpleNamespace(
            prevailing_wind_dx=6,prevailing_wind_dy=-4,
            precipitation_potential=48000,humidity=52000,wind_strength=22000)
        generator=SimpleNamespace(version=8,climate_at=lambda _:climate)
        return WeatherSystem(b'front-sequence',generator)

    def test_dry_weather_predominates_and_rain_occurs_in_multi_hour_fronts(self):
        weather=self.model()
        rains=[weather.at(slot*120,0,0)['rain'] for slot in range(300)]
        self.assertLess(sum(v>0 for v in rains),len(rains)//3)
        self.assertTrue(any(a>0 and b>0 for a,b in zip(rains,rains[1:])))
        self.assertEqual(weather.at(12*120,0,0),weather.at(12*120,0,0))

    def test_front_is_deterministic_bounded_and_wetness_trails_rain(self):
        a=self.model();b=self.model()
        for minute in range(0,100*120,120):
            result=a.at(minute,-50,12)
            self.assertEqual(result,b.at(minute,-50,12))
            for key in ('rain','wetness','cloud_cover','fog','wind_speed','storm_intensity'):
                self.assertLessEqual(result[key],100)
                self.assertGreaterEqual(result[key],0)
            if result['rain']:
                self.assertGreater(result['wetness'],0)


if __name__=='__main__':
    unittest.main()
