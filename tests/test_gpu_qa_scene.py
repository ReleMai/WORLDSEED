"""Synthetic environment selection stays outside normal-world rendering."""
from pathlib import Path
import tempfile
import unittest
from tools.gpu_qa_scene import PreparedWeather, qa_minute
from tools.reference_scene_fixtures import build_fixture
from tools.worldseed_gpu_gameplay import run
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.presentation.live_gpu_scene import capture_live_scene, player_foot
from worldseed.presentation.worldspace import WorldCamera


class GPUQASceneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=ContentRegistry.load(DATA_DIR)

    def test_qa_controls_require_prepared_scene_and_validate_before_window(self):
        for fields in (dict(qa_weather='snow'),dict(qa_season='winter'),dict(qa_time='night'),
                       dict(prepared_scene='forest',qa_weather='invalid'),
                       dict(prepared_scene='forest',qa_season='invalid'),
                       dict(prepared_scene='forest',qa_time='invalid')):
            with self.subTest(fields=fields),self.assertRaises(ValueError):run(**fields)

    def test_seasonal_preparation_and_observation_use_same_minute(self):
        for season in ('spring','summer','autumn','winter'):
            with self.subTest(season=season),tempfile.TemporaryDirectory() as directory:
                fixture=build_fixture('forest',self.registry,Path(directory),width=640,height=480,
                    game_minute=qa_minute(season,'night'))
                try:
                    fixture.sim.environment.weather=PreparedWeather('snow')
                    before=fixture.authority_fingerprint()
                    snapshot=capture_live_scene(fixture.sim,WorldCamera(player_foot(fixture.sim),640,480,36))
                    self.assertEqual(snapshot.season,season)
                    self.assertEqual(snapshot.minute%1440,0)
                    self.assertTrue(snapshot.resources)
                    _,lighting=fixture.sim.environment.visual_conditions(snapshot.minute,fixture.sim.player_pos)
                    self.assertEqual(snapshot.atmosphere().sun,lighting.ambient_light/65535.)
                    self.assertGreater(snapshot.atmosphere().snow,0)
                    self.assertEqual(snapshot.atmosphere().rain,0)
                    self.assertEqual(before,fixture.authority_fingerprint())
                finally:fixture.close()

    def test_weather_is_detached_and_uses_engine_precipitation_units(self):
        for kind in ('clear','cloudy','rain','storm','snow','fog'):
            source=PreparedWeather(kind)
            sample=source.at(720,256,256)
            sample['rain']=1000
            self.assertLessEqual(source.at(720,256,256)['rain'],10)
        self.assertEqual(qa_minute(),720)
