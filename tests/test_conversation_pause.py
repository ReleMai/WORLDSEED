"""Conversation clock holds freeze actors and discard time spent reading."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from worldseed.sim.realtime import RealtimeSimulationDriver
from worldseed.ui.pointer import WindowCloseRequested
from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.ui.terminal import Terminal


class MovingSimulation:
    def __init__(self):
        self.minute = 600
        self.npc_x = 10
        self.advances = []
        self.in_combat = False

    def advance_realtime(self, minutes):
        self.advances.append(minutes)
        self.minute += minutes
        self.npc_x += minutes
        return minutes

    def combat_active(self):
        return self.in_combat


class ConversationPauseTests(unittest.TestCase):
    def backends(self):
        # Clock adapters do not need an SDL window or optional pygame install.
        return (Terminal(), PygameTerminal.__new__(PygameTerminal))

    def fixture(self, term):
        clock = SimpleNamespace(now=0.0)
        sim = MovingSimulation()
        driver = RealtimeSimulationDriver(sim, seconds_per_game_minute=1)
        driver.resume(clock.now)
        term.set_realtime_callback(driver.pump)
        return clock, sim, driver

    def test_entire_conversation_and_nested_panels_freeze_actor_and_clock(self):
        for term in self.backends():
            with self.subTest(backend=type(term).__name__):
                clock, sim, driver = self.fixture(term)
                with patch('worldseed.sim.realtime.time.monotonic', side_effect=lambda: clock.now):
                    clock.now = 2.4
                    self.assertTrue(term._pump_realtime())
                    frozen = (sim.minute, sim.npc_x, tuple(sim.advances))
                    with term.pause_realtime():
                        clock.now = 600
                        self.assertFalse(term._pump_realtime())
                        # The driver is held even if something bypasses the UI.
                        self.assertEqual(driver.pump(), 0)
                        with term.pause_realtime():
                            clock.now = 900
                            self.assertFalse(term._pump_realtime())
                        clock.now = 1200
                        self.assertFalse(term._pump_realtime())
                        self.assertEqual((sim.minute, sim.npc_x, tuple(sim.advances)), frozen)
                    self.assertFalse(term._pump_realtime())
                    clock.now = 1200.5
                    self.assertFalse(term._pump_realtime())
                    clock.now = 1201
                    self.assertTrue(term._pump_realtime())
                    self.assertEqual(sim.advances, [2, 1])
                    self.assertEqual((sim.minute, sim.npc_x), (603, 13))

    def test_scope_without_any_pumps_discards_paused_wall_time(self):
        clock = SimpleNamespace(now=0.0)
        sim = MovingSimulation()
        driver = RealtimeSimulationDriver(sim, seconds_per_game_minute=1)
        driver.resume(0)
        with patch('worldseed.sim.realtime.time.monotonic', side_effect=lambda: clock.now):
            with driver.pause_realtime():
                clock.now = 3600
            self.assertEqual(driver.pump(), 0)
            self.assertEqual(driver.pump(3601), 1)
        self.assertEqual(sim.advances, [1])

    def test_existing_explicit_pause_survives_conversation_and_nested_exit(self):
        for term in self.backends():
            with self.subTest(backend=type(term).__name__):
                clock, sim, driver = self.fixture(term)
                driver.pause()
                with patch('worldseed.sim.realtime.time.monotonic', side_effect=lambda: clock.now):
                    with term.pause_realtime():
                        with term.pause_realtime():
                            clock.now = 600
                    self.assertTrue(driver.paused)
                    self.assertFalse(term._pump_realtime())
                    self.assertEqual(sim.advances, [])
                    driver.resume()
                    clock.now = 601
                    self.assertTrue(term._pump_realtime())
                    self.assertEqual(sim.advances, [1])

    def test_explicit_pause_and_resume_do_not_override_active_scope(self):
        clock = SimpleNamespace(now=0.0)
        sim = MovingSimulation()
        driver = RealtimeSimulationDriver(sim, seconds_per_game_minute=1)
        driver.resume(0)
        with patch('worldseed.sim.realtime.time.monotonic', side_effect=lambda: clock.now):
            with driver.pause_realtime():
                driver.pause()
                clock.now = 300
                driver.resume()
                self.assertEqual(driver.pump(600), 0)
                driver.pause()
                clock.now = 900
            self.assertTrue(driver.paused)
            self.assertEqual(driver.pump(1200), 0)
        self.assertEqual(sim.advances, [])

    def test_exception_and_window_close_release_all_scopes(self):
        for term in self.backends():
            for exception in (RuntimeError, WindowCloseRequested):
                with self.subTest(backend=type(term).__name__, exception=exception.__name__):
                    clock, sim, driver = self.fixture(term)
                    with patch('worldseed.sim.realtime.time.monotonic', side_effect=lambda: clock.now):
                        with self.assertRaises(exception):
                            with term.pause_realtime():
                                with term.pause_realtime():
                                    clock.now = 1800
                                    raise exception('leave conversation')
                        self.assertEqual(term._realtime_pause_depth, 0)
                        self.assertEqual(driver._pause_depth, 0)
                        self.assertFalse(driver.paused)
                        self.assertFalse(term._pump_realtime())
                        clock.now = 1801
                        self.assertTrue(term._pump_realtime())
                        self.assertEqual(sim.advances, [1])

    def test_combat_pause_still_holds_after_conversation(self):
        for term in self.backends():
            with self.subTest(backend=type(term).__name__):
                clock, sim, driver = self.fixture(term)
                sim.in_combat = True
                with patch('worldseed.sim.realtime.time.monotonic', side_effect=lambda: clock.now):
                    self.assertFalse(term._pump_realtime())
                    with term.pause_realtime():
                        clock.now = 600
                    self.assertFalse(term._pump_realtime())
                    clock.now = 900
                    self.assertFalse(term._pump_realtime())
                    sim.in_combat = False
                    clock.now = 1200
                    self.assertFalse(term._pump_realtime())
                    clock.now = 1201
                    self.assertTrue(term._pump_realtime())
                    self.assertEqual(sim.advances, [1])

    def test_no_clock_and_custom_callbacks_are_safe_and_nested(self):
        for term in self.backends():
            with self.subTest(backend=type(term).__name__):
                term.set_realtime_callback(None)
                with term.pause_realtime():
                    self.assertFalse(term._pump_realtime())
                callback = Mock(return_value=1)
                term.set_realtime_callback(callback)
                with term.pause_realtime():
                    with term.pause_realtime():
                        self.assertFalse(term._pump_realtime())
                    self.assertFalse(term._pump_realtime())
                callback.assert_not_called()
                self.assertTrue(term._pump_realtime())
                callback.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
