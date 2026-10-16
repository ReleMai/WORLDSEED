"""GPU HUD tracks and compact help preserve the shared command boundary."""
from __future__ import annotations

from copy import deepcopy
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from worldseed.entities.components import Vitals
from worldseed.sim.realtime import RealtimeSimulationDriver
from worldseed.ui import gpu_hud
from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.ui.router import HUD_BUTTONS, classify_key


class GPUHUDTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not PygameTerminal.available():
            raise unittest.SkipTest('optional pygame unavailable')

    def setUp(self):
        self.environment = patch.dict(os.environ, {'SDL_VIDEODRIVER': 'dummy', 'SDL_AUDIODRIVER': 'dummy'})
        self.environment.start(); self.addCleanup(self.environment.stop)
        self.term = PygameTerminal(960, 720); self.term.enter()
        self.addCleanup(self.term.restore)
        self.addCleanup(gpu_hud.close_help_popup, self.term)
        self.term._input_mode = 'world'
        self.sim = SimpleNamespace(state=SimpleNamespace(player_name='Wanderer', player_hunting_stance='normal'),
                                   clock=SimpleNamespace(minute=42, label=lambda: 'Y1 Spring 1, 08:25'),
                                   player_pos=SimpleNamespace(x=12, y=24, z=0))

    def test_vitals_show_health_and_remaining_food_water_not_inverted_danger(self):
        vitals = Vitals(hp=54, max_hp=108, hunger=20, thirst=65, stamina=25)
        bars = {bar.key: bar for bar in gpu_hud.vital_bars(vitals)}
        self.assertEqual(bars['health'].fraction, .5)
        self.assertEqual(bars['stamina'].fraction, .25)
        self.assertEqual(bars['hunger'].fraction, .8)
        self.assertAlmostEqual(bars['thirst'].fraction, .35)
        self.assertEqual(bars['health'].label, 'Health 54/108')
        self.assertIn('empties as hunger increases', bars['hunger'].detail)
        extreme = gpu_hud.vital_bars(Vitals(hp=999, max_hp=0, hunger=-3, thirst=150, stamina=200))
        self.assertTrue(all(0 <= bar.fraction <= 1 for bar in extreme))

    def test_art_toolbar_and_visible_meter_tracks_fit_sidebar_without_state_change(self):
        term = self.term
        before = deepcopy((vars(self.sim.state), vars(self.sim.player_pos), self.sim.clock.minute))
        for width, height in ((300, 630), (180, 430), (146, 380)):
            with self.subTest(width=width, height=height):
                term._pointer_targets.clear(); term._hud_tooltips.clear()
                rect = term.pg.Rect(960 - width, 55, width, height)
                with patch.object(gpu_hud, '_icon') as icons:
                    bar = gpu_hud.draw_hud(term, rect, self.sim, Vitals(hp=80, hunger=30, thirst=50))
                self.assertTrue(rect.contains(bar))
                self.assertEqual(icons.call_count, len(HUD_BUTTONS) + 4)
                self.assertEqual([token for _, token in term._pointer_targets[:10]], [token for _, token in HUD_BUTTONS])
                self.assertTrue(all(rect.contains(target) for target, _ in term._pointer_targets))
                meters = term._hud_tooltips[:4]
                self.assertEqual([name.split()[0] for _, name, _ in meters], ['Health', 'Stamina', 'Hunger', 'Thirst'])
                # The colored interior proves this is a graphical filled bar,
                # beyond its numeric label and empty background/border.
                for track, _, _ in meters:
                    self.assertGreaterEqual(track.height, 5)
                    self.assertNotEqual(tuple(term.screen.get_at((track.x + 3, track.centery)))[:3], (12, 16, 18))
                self.assertEqual(term.screen.get_clip(), term.screen.get_rect())
        self.assertEqual(before, (vars(self.sim.state), vars(self.sim.player_pos), self.sim.clock.minute))

    def test_question_button_opens_draggable_compact_help_and_esc_returns_to_world(self):
        term = self.term; pg = term.pg
        help_button = pg.Rect(700, 550, 36, 36)
        term._pointer_targets = [(help_button, '?')]
        term._held_movement[pg.K_d] = 12; term._active_movement_key = pg.K_d
        self.assertTrue(gpu_hud.handle_hud_event(term, pg.event.Event(pg.MOUSEBUTTONDOWN, button=1, pos=help_button.center)))
        self.assertFalse(term._held_movement)
        self.assertIsNone(term._active_movement_key)
        self.assertEqual(term._realtime_pause_depth, 1)
        gpu_hud.draw_help_popup(term)
        window = term._gpu_help_window
        self.assertEqual(window.navigation.snapshot(), (('world', 0, 0), ('keybindings', 0, 0)))
        self.assertLess(window.rect.width, term.width)
        self.assertLess(window.rect.height, term.height)
        original = window.rect.copy()
        point = (original.x + 15, original.y + 15)
        self.assertTrue(gpu_hud.handle_hud_event(term, pg.event.Event(pg.MOUSEBUTTONDOWN, button=1, pos=point)))
        self.assertTrue(gpu_hud.handle_hud_event(term, pg.event.Event(pg.MOUSEMOTION, pos=(point[0] + 25, point[1] + 31))))
        self.assertEqual(window.rect.topleft, (original.x + 25, original.y + 31))
        gpu_hud.handle_hud_event(term, pg.event.Event(pg.MOUSEBUTTONUP, button=1, pos=point))
        self.assertIsNone(window.drag)
        self.assertTrue(gpu_hud.handle_hud_event(term, pg.event.Event(pg.KEYDOWN, key=pg.K_ESCAPE, unicode='')))
        self.assertFalse(gpu_hud.help_popup_open(term))
        self.assertEqual(term._realtime_pause_depth, 0)
        self.assertEqual(window.navigation.snapshot(), (('world', 0, 0),))
        self.assertEqual(term._input_mode, 'world')
        self.assertFalse(gpu_hud.handle_hud_event(term, pg.event.Event(pg.KEYDOWN, key=pg.K_d, unicode='d')))

    def test_help_blocks_movement_realtime_and_click_through_without_advancing_clock(self):
        term = self.term; pg = term.pg
        advanced = []
        simulation = SimpleNamespace(combat_active=lambda: False, advance_realtime=lambda minutes: advanced.append(minutes))
        driver = RealtimeSimulationDriver(simulation)
        driver.resume(now=1)
        term.set_realtime_callback(driver.pump)
        minute = self.sim.clock.minute
        question = pg.event.Event(pg.KEYDOWN, key=pg.K_SLASH, unicode='?')
        self.assertTrue(gpu_hud.handle_hud_event(term, question))
        self.assertEqual(driver._pause_depth, 1)
        self.assertFalse(term._pump_realtime())
        self.assertEqual(driver.pump(now=1000), 0)
        for event in (pg.event.Event(pg.KEYDOWN, key=pg.K_w, unicode='w'),
                      pg.event.Event(pg.KEYUP, key=pg.K_w),
                      pg.event.Event(pg.MOUSEBUTTONDOWN, button=1, pos=(10, 10)),
                      pg.event.Event(pg.MOUSEWHEEL, y=-1, x=0)):
            self.assertTrue(gpu_hud.handle_hud_event(term, event))
        self.assertFalse(term._held_movement)
        self.assertEqual(advanced, [])
        self.assertEqual(self.sim.clock.minute, minute)
        self.assertTrue(gpu_hud.handle_hud_event(term, question))
        self.assertEqual(driver._pause_depth, 0)
        self.assertEqual(term._realtime_pause_depth, 0)
        self.assertEqual(advanced, [])

    def test_help_scroll_and_window_clamp_are_bounded_after_resize(self):
        term = self.term; pg = term.pg
        gpu_hud.open_help_popup(term); gpu_hud.draw_help_popup(term)
        for _ in range(100):
            gpu_hud.handle_hud_event(term, pg.event.Event(pg.MOUSEWHEEL, x=0, y=-100))
        gpu_hud.draw_help_popup(term)
        window = term._gpu_help_window
        self.assertLess(window.navigation.current.scroll, len(gpu_hud.keybinding_rows()))
        term.screen = pg.Surface((640, 480), pg.SRCALPHA)
        window.rect.topleft = (9000, -9000)
        gpu_hud.draw_help_popup(term)
        self.assertTrue(term.screen.get_rect().contains(window.rect))
        self.assertEqual(term.screen.get_clip(), term.screen.get_rect())
        for size in ((1, 1), (32, 20)):
            term.screen = pg.Surface(size, pg.SRCALPHA)
            gpu_hud.draw_help_popup(term)
            self.assertTrue(term.screen.get_rect().contains(window.rect))

    def test_existing_router_bindings_are_the_help_source_and_wasd_stays_movement(self):
        rows = dict(gpu_hud.keybinding_rows())
        for label, token in HUD_BUTTONS:
            key = {'\r': 'Enter', '\t': 'Tab', 'ESC': 'Esc'}.get(token, token.upper())
            self.assertEqual(rows[label], key)
        for key in 'wasd':
            self.assertEqual(classify_key(key).kind, 'move')
            self.assertIn(key.upper(), rows['Movement'])
        term = self.term; pg = term.pg
        term._input_mode = 'text'
        self.assertFalse(gpu_hud.handle_hud_event(term, pg.event.Event(pg.KEYDOWN, key=pg.K_SLASH, unicode='?')))

    def test_authored_art_draws_and_is_cached_across_hud_redraws(self):
        from worldseed.ui.gpu_control_art import load_icon
        term = self.term
        rect = term.pg.Rect(680, 50, 270, 640)
        with patch('worldseed.ui.gpu_control_art.load_icon', wraps=load_icon) as load:
            gpu_hud.draw_hud(term, rect, self.sim, Vitals())
            self.assertEqual(load.call_count, 14)
            term._pointer_targets.clear(); term._hud_tooltips.clear()
            gpu_hud.draw_hud(term, rect, self.sim, Vitals())
            self.assertEqual(load.call_count, 14)
        self.assertLessEqual(len(term._gpu_control_art_cache), 64)


if __name__ == '__main__':
    unittest.main()
