"""Shared action-timing checks; no world-clock authority in presentation."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from worldseed.sim.commands import CraftCommand, MoveCommand, RestCommand, WaitCommand
from worldseed.ui.action_progress import action_title, elapsed_minutes, visual_duration


class ActionProgressScheduleTests(unittest.TestCase):
    def test_labels_are_derived_from_real_commands(self):
        self.assertEqual(action_title(CraftCommand(1, "core:axe")), "Crafting")
        self.assertEqual(action_title(RestCommand(1, 120)), "Resting")
        self.assertEqual(action_title(WaitCommand(1, 10)), "Waiting")
        self.assertEqual(action_title(MoveCommand(1, 1, 0)), "Move")

    def test_full_elapsed_minutes_exactly_once_with_partial_ticks(self):
        for total in (1, 5, 17, 120, 1440):
            with self.subTest(total=total):
                advanced = 0
                portions = []
                for fraction in (0.0, 0.08, 0.25, 0.49, 0.75, 0.95, 1.0):
                    due = elapsed_minutes(total, fraction, advanced)
                    self.assertGreaterEqual(due, advanced)
                    portions.append(due - advanced)
                    advanced = due
                self.assertEqual(sum(portions), total)
                self.assertEqual(elapsed_minutes(total, 0.0, advanced), total)
                self.assertEqual(elapsed_minutes(total, 1.5, advanced), total)

    def test_visual_duration_is_bounded_and_not_world_duration(self):
        self.assertGreater(visual_duration(30), visual_duration(5))
        self.assertLessEqual(visual_duration(24 * 60), 5.0)
        self.assertGreaterEqual(visual_duration(1), .35)


class ActionProgressPygameTests(unittest.TestCase):
    def test_pygame_action_progress_advances_before_panel_returns(self):
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        from worldseed.ui.pygame_terminal import PygameTerminal
        if not PygameTerminal.available():
            self.skipTest("pygame-ce not installed")
        term = PygameTerminal(800, 520)
        term.enter()
        try:
            term._input_mode = "ui"
            events = []
            def advance(delta):
                self.assertGreater(delta, 0)
                events.append(("tick", delta))
            def redraw():
                events.append(("world", sum(n for kind,n in events if kind == "tick")))
                term.screen.fill((20, 22, 24))
                term.pg.display.flip()
            with patch("worldseed.ui.action_progress.visual_duration", return_value=0.22):
                term.present_timed_action(CraftCommand(1, "core:axe"), 20, advance, redraw)
            self.assertEqual(sum(n for kind,n in events if kind == "tick"), 20)
            self.assertTrue(any(kind == "world" and 0 < n < 20 for kind,n in events), events)
            self.assertEqual(term._input_mode, "ui")
            self.assertIsNone(term._floating_backdrop)
        finally:
            term.restore()


if __name__ == "__main__":
    unittest.main()
