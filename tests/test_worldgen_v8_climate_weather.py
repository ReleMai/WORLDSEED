from __future__ import annotations

import unittest

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.systems.environment import WeatherSystem
from worldseed.world.generator import WorldGenerator
from worldseed.world.lighting import LightingSystem


class WorldgenV8ClimateWeatherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)
        cls.seed = b"v8-climate-weather"
        cls.gen = WorldGenerator(cls.seed, cls.registry, version=8)

    def test_climate_is_deterministic_bounded_and_authoritative(self):
        coords = (
            (-8192, -6144), (-4097, 1025), (-1, -1), (0, 0),
            (913, -1441), (4096, 2048), (12288, 8192),
        )
        other = WorldGenerator(self.seed, self.registry, version=8)
        for x, y in coords:
            pos = WorldPos(x, y, 0)
            a = self.gen.climate_at(pos)
            b = other.climate_at(pos)
            self.assertEqual(a, b)
            fields = self.gen.sample_fields(pos)
            self.assertEqual(fields.moisture, a.precipitation_potential)
            self.assertEqual(fields.temperature, a.mean_temperature)
            for value in (
                a.mean_temperature, a.precipitation_potential, a.humidity,
                a.maritime_influence, a.continentality, a.wind_strength,
                a.orographic_lift, a.rain_shadow, a.latitude_heat,
            ):
                self.assertGreaterEqual(value, 0)
                self.assertLessEqual(value, 65535)
            self.assertGreaterEqual(a.prevailing_wind_dx, -1024)
            self.assertLessEqual(a.prevailing_wind_dx, 1024)
            self.assertGreaterEqual(a.prevailing_wind_dy, -1024)
            self.assertLessEqual(a.prevailing_wind_dy, 1024)

    def test_orography_produces_lift_and_rain_shadow_somewhere(self):
        max_lift = 0
        max_shadow = 0
        for y in range(-8192, 8193, 256):
            for x in range(-8192, 8193, 256):
                climate = self.gen.climate_at(WorldPos(x, y, 0))
                max_lift = max(max_lift, climate.orographic_lift)
                max_shadow = max(max_shadow, climate.rain_shadow)
        self.assertGreater(max_lift, 2000)
        self.assertGreater(max_shadow, 2000)

    def test_weather_is_climate_driven_and_tracks_recent_wetness(self):
        weather = WeatherSystem(self.seed, self.gen)
        seen = set()
        rainy = None
        for minute in range(0, 7 * 1440, 120):
            row = weather.at(minute, 913, -1441)
            seen.add(row["kind"])
            for key in ("cloud_cover", "storm_intensity", "humidity", "wetness", "fog", "wind_speed"):
                self.assertGreaterEqual(int(row[key]), 0)
                self.assertLessEqual(int(row[key]), 100)
            self.assertGreaterEqual(int(row["rain"]), 0)
            self.assertLessEqual(int(row["rain"]), 10)
            if row["rain"] > 0 and rainy is None:
                rainy = (minute, row)
        self.assertTrue(seen & {"clear", "cloudy", "rain", "storm", "fog", "wind"})
        if rainy is not None:
            minute, row = rainy
            self.assertGreater(row["wetness"], 0)
            after = weather.at(minute + 120, 913, -1441)
            self.assertGreaterEqual(after["wetness"], 0)

    def test_lighting_makes_night_darker_and_clouds_dim_day(self):
        lighting = LightingSystem()
        day = lighting.at(12 * 60, 0, 0)
        cloudy_day = lighting.at(12 * 60, 90, 0)
        night = lighting.at(1 * 60, 0, 0)
        self.assertEqual(day.phase, "day")
        self.assertEqual(night.phase, "night")
        self.assertGreater(day.ambient_light, night.ambient_light)
        self.assertGreater(night.darkness_alpha, day.darkness_alpha)
        self.assertLess(cloudy_day.ambient_light, day.ambient_light)


if __name__ == "__main__":
    unittest.main()
