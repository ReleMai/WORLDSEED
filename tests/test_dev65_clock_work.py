"""Clock ownership and successful-work duration integration regressions."""
from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from worldseed.content.registry import RecipeDef
from worldseed.entities.components import Inventory, Vitals
from worldseed.sim.commands import CraftCommand, StoreCommand, WaitCommand
from worldseed.sim.realtime import RealtimeSimulationDriver
from worldseed.sim.work_duration import adjusted_work_minutes


class MovingSimulation:
    def __init__(self):
        self.minutes=0
        self.in_combat=False

    def combat_active(self):return self.in_combat

    def advance_realtime(self,minutes):
        self.minutes+=minutes
        return minutes


class Dev65ClockTests(unittest.TestCase):
    def driver(self):
        simulation=MovingSimulation()
        driver=RealtimeSimulationDriver(simulation,seconds_per_game_minute=1,max_catchup_minutes=5)
        driver.resume(0)
        return simulation,driver

    def test_speed_pause_and_movement_keep_clock_ownership(self):
        simulation,driver=self.driver()
        driver.set_speed(2,0)
        self.assertEqual(driver.pump(1),2)
        driver.set_speed(3,1)
        self.assertEqual(driver.pump(2),3)
        self.assertTrue(driver.toggle_pause(2))
        driver.resume_for_movement(200)
        self.assertEqual(driver.speed,1)
        self.assertTrue(driver.paused)
        self.assertTrue(driver.effective_paused)
        self.assertEqual(driver.pump(900),0)
        self.assertFalse(driver.toggle_pause(900))
        self.assertEqual(driver.pump(901),1)
        self.assertEqual(simulation.minutes,6)

    def test_changing_speed_does_not_release_pause_or_nested_focus_holds(self):
        simulation,driver=self.driver()
        clock=SimpleNamespace(now=0)
        with patch('worldseed.sim.realtime.time.monotonic',side_effect=lambda:clock.now):
            with driver.pause_realtime():
                with driver.pause_realtime():
                    driver.set_speed(3,10)
                    self.assertTrue(driver.effective_paused)
                    self.assertEqual(driver.pump(600),0)
                    driver.pause()
                clock.now=900
            self.assertTrue(driver.paused)
            self.assertTrue(driver.effective_paused)
            self.assertEqual(simulation.minutes,0)
            driver.toggle_pause(900)
            self.assertFalse(driver.effective_paused)
            self.assertEqual(driver.pump(901),3)

    def test_repeated_walk_does_not_starve_realtime_or_retain_fast_backlog(self):
        simulation,driver=self.driver()
        driver.set_speed(3,0)
        self.assertEqual(driver.pump(.25),0)
        driver.resume_for_movement(.25)
        for now in (.5,.75,1,1.25):
            driver.resume_for_movement(now)
            driver.pump(now)
        self.assertEqual(simulation.minutes,1)
        self.assertEqual(driver.speed,1)

    def test_animation_baseline_and_combat_preserve_explicit_controls(self):
        simulation,driver=self.driver()
        driver.set_speed(3,0)
        driver.pause()
        driver.reset_baseline(600)
        self.assertTrue(driver.paused)
        self.assertEqual(driver.speed,3)
        driver.resume(600)
        simulation.in_combat=True
        self.assertTrue(driver.effective_paused)
        self.assertEqual(driver.pump(900),0)
        simulation.in_combat=False
        self.assertEqual(driver.pump(1200),0)
        self.assertEqual(driver.pump(1201),3)

    def test_bad_speed_values_rejected_without_changing_clock(self):
        _,driver=self.driver()
        for value in (0,4,-1,True,1.5,'2'):
            with self.subTest(value=value),self.assertRaises(ValueError):
                driver.set_speed(value,99)
        self.assertEqual(driver.speed,1)
        self.assertEqual(driver.pump(1),1)

    def test_speed_accumulation_is_partition_independent_and_stalls_bounded(self):
        direct,first=self.driver();split,second=self.driver()
        first.set_speed(3,0);second.set_speed(3,0)
        first.pump(1.5)
        for now in (.125,.25,.5,.75,1,1.25,1.5):second.pump(now)
        self.assertEqual(direct.minutes,split.minutes)
        self.assertEqual(first.pump(1000),5)


class Dev65WorkTests(unittest.TestCase):
    def test_work_factors_are_bounded_and_leave_instant_actions_instant(self):
        self.assertEqual(adjusted_work_minutes(60),60)
        self.assertLess(adjusted_work_minutes(60,skill=8,tool_quality=5),60)
        self.assertGreater(adjusted_work_minutes(60,stamina=10,wound_severity=100),60)
        self.assertGreater(adjusted_work_minutes(60,rain=8,wind_speed=80),60)
        for minutes in (0,1):
            self.assertEqual(adjusted_work_minutes(minutes,stamina=0,wound_severity=900,rain=10),minutes)
        self.assertEqual(adjusted_work_minutes(100,skill=100,tool_quality=100),63)
        self.assertEqual(adjusted_work_minutes(100,stamina=0,wound_severity=10000,rain=1000,wind_speed=1000),180)

    def fixture(self):
        from tests.test_interior_engine import InteriorEngineTests
        fixture=InteriorEngineTests()
        self.addCleanup(fixture.doCleanups)
        simulation,_=fixture.prepared_simulation()
        simulation.state.player_crafting_discovery_enabled=False
        simulation.registry.recipes['test:work']=RecipeDef(
            'test:work','Test wood work',{'core:wood':1},{'core:stone':1},60,None,None)
        return simulation

    def test_actual_successful_craft_charges_adjusted_time_once_and_conserves_goods(self):
        simulation=self.fixture()
        inventory=simulation.entities.get(simulation.player_id,Inventory)
        simulation.entities.get(simulation.player_id,Vitals).stamina=10
        before=(simulation.clock.minute,inventory.count('core:wood'),inventory.count('core:stone'))
        seen=[]
        def progress(command,minutes,advance):
            seen.append(minutes)
            self.assertEqual(inventory.count('core:wood'),before[1]-1)
            advance(minutes)
        simulation._action_progress_callback=progress
        simulation.execute(CraftCommand(simulation.player_id,'test:work'))
        self.assertEqual(seen,[69])
        self.assertEqual(simulation.clock.minute,before[0]+69)
        self.assertEqual(inventory.count('core:wood'),before[1]-1)
        self.assertEqual(inventory.count('core:stone'),before[2]+1)

    def test_failed_work_wait_and_instant_transfer_keep_existing_costs(self):
        simulation=self.fixture()
        simulation.entities.get(simulation.player_id,Vitals).stamina=1
        before=simulation.clock.minute
        simulation.execute(CraftCommand(simulation.player_id,'test:missing'))
        self.assertEqual(simulation.clock.minute,before+5)
        before=simulation.clock.minute
        simulation.execute(WaitCommand(simulation.player_id,12))
        self.assertEqual(simulation.clock.minute,before+12)
        before=simulation.clock.minute
        simulation.execute(StoreCommand(simulation.player_id,'core:wood',1,'missing:container'))
        self.assertEqual(simulation.clock.minute,before)

    def test_indoor_work_ignores_outdoor_weather_and_existing_skill_is_not_applied_twice(self):
        simulation=self.fixture()
        with patch.object(simulation.environment.weather,'at',side_effect=AssertionError('indoor weather read')):
            simulation.state.player_skills['crafting']=8
            self.assertEqual(simulation._work_minutes(60),60)
            self.assertEqual(simulation._work_minutes(60,skill='crafting'),46)

    def test_only_the_required_tool_quality_accelerates_work(self):
        simulation=self.fixture()
        inventory=simulation.entities.get(simulation.player_id,Inventory)
        inventory.add('core:crude_knife',1)
        baseline=simulation._work_minutes(60,tool_qualities=('pick',))
        self.assertEqual(baseline,60)
        self.assertLess(simulation._work_minutes(60,tool_qualities=('knife',)),baseline)

    def test_outdoor_exposure_adjusts_work_without_changing_state(self):
        simulation=self.fixture()
        simulation.state.interior_actors.pop('player')
        before=simulation.state.to_dict()
        with patch.object(simulation.environment.weather,'at',return_value={'rain':8,'wind_speed':80}) as sample:
            self.assertGreater(simulation._work_minutes(60),60)
            sample.assert_called_once()
        self.assertEqual(simulation.state.to_dict(),before)


if __name__=='__main__':
    unittest.main()
