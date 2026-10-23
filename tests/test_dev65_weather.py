from __future__ import annotations

from types import SimpleNamespace
import unittest

from worldseed.systems.environment import WeatherSystem


class ClimateGenerator:
    def __init__(self,version=8,*,precipitation=48000,humidity=52000):
        self.version=version
        self.calls=0
        self.climate=SimpleNamespace(
            prevailing_wind_dx=1024,prevailing_wind_dy=-512,
            precipitation_potential=precipitation,humidity=humidity,
            wind_strength=22000)

    def climate_at(self,pos):
        self.calls+=1
        return self.climate


class Dev65WeatherTests(unittest.TestCase):
    def model(self,**kwargs):
        return WeatherSystem(b'dev65-weather',ClimateGenerator(**kwargs))

    def test_legacy_samples_are_unchanged_and_do_not_read_climate(self):
        generator=ClimateGenerator(version=7)
        weather=WeatherSystem(b'dev65-weather',generator)
        expected={'kind':'cloudy','temp_delta':0,'wind':3,'rain':0,
                  'visibility':8,'cloud_cover':65,'storm_intensity':0,
                  'humidity':45,'wetness':0,'fog':0,'wind_dx':0,
                  'wind_dy':0,'wind_speed':60}
        self.assertEqual(weather.at(0,0,0),expected)
        for minute,x,y in ((1440,-129,700),(3210,913,-1441),(90000,1200,-750)):
            self.assertEqual(weather.at(minute,x,y),
                             WeatherSystem(b'dev65-weather').at(minute,x,y))
        self.assertEqual(generator.calls,0)

    def test_rain_fronts_last_six_slots_even_at_advected_cell_boundaries(self):
        weather=self.model()
        rainy=0
        for front in range(120):
            rows=[weather.at((front*6+phase)*120,255,-1) for phase in range(6)]
            self.assertEqual(len({bool(row['rain']) for row in rows}),1)
            if rows[0]['rain']:
                rainy+=1
                self.assertGreaterEqual(rows[2]['rain'],rows[0]['rain'])
                self.assertEqual(rows[2]['rain'],rows[3]['rain'])
                self.assertEqual(rows[0]['rain'],rows[5]['rain'])
        self.assertGreater(rainy,0)
        self.assertLess(rainy,60)

    def test_climate_drives_rain_and_storms_are_uncommon(self):
        dry=self.model(precipitation=0,humidity=0)
        humid=self.model(precipitation=65535,humidity=65535)
        rows=[humid.at(slot*120,0,0) for slot in range(1800)]
        rain=sum(row['rain']>0 for row in rows)
        storms=sum(row['storm_intensity']>0 for row in rows)
        dry_rain=sum(dry.at(slot*120,0,0)['rain']>0 for slot in range(1800))
        self.assertGreater(rain,dry_rain)
        self.assertGreater(rain,0)
        self.assertLess(rain,len(rows)//2)
        self.assertLess(storms,rain//2)
        for row in rows:
            self.assertGreaterEqual(row['rain'],0)
            self.assertLessEqual(row['rain'],10)
            for key in ('cloud_cover','storm_intensity','humidity','wetness','fog','wind_speed'):
                self.assertGreaterEqual(row[key],0)
                self.assertLessEqual(row[key],100)

    def test_wetness_lingers_after_rain_ends(self):
        weather=self.model()
        previous=weather.at(0,0,0)
        for slot in range(1,1200):
            current=weather.at(slot*120,0,0)
            if previous['rain'] and not current['rain']:
                self.assertGreater(current['wetness'],current['humidity']//10)
                break
            previous=current
        else:
            self.fail('No wet-to-dry transition in the deterministic fixture')

    def test_cache_reuses_slot_but_returns_detached_values(self):
        weather=self.model()
        expected=weather.at(240,20,-40)
        first=weather.at(241,20,-40)
        first['rain']=999
        first['invented']='caller mutation'
        self.assertEqual(weather.at(359,20,-40),expected)
        self.assertEqual(weather.generator.calls,1)
        self.assertEqual(len(weather._sample_cache),1)
        weather.at(360,20,-40)
        self.assertEqual(weather.generator.calls,2)

    def test_query_order_eviction_and_generator_changes_do_not_change_results(self):
        weather=self.model()
        other=self.model()
        samples=[(slot*120,slot-300,17-slot) for slot in range(600)]
        expected=[weather.at(*sample) for sample in samples]
        self.assertEqual(len(weather._sample_cache),weather.MAX_CACHED_SAMPLES)
        for index in reversed(range(len(samples))):
            self.assertEqual(other.at(*samples[index]),expected[index])
        self.assertEqual(weather.at(*samples[0]),expected[0])
        replacement=ClimateGenerator(precipitation=0,humidity=0)
        weather.generator=replacement
        self.assertEqual(weather.at(*samples[0]),
                         WeatherSystem(b'dev65-weather',replacement).at(*samples[0]))
        self.assertEqual(len(weather._sample_cache),1)


if __name__=='__main__':
    unittest.main()
