"""The GPU backend runs the existing main application, UI and save boundary.

SDL offscreen/Mesa checks exercise real shaders and menus when optional graphics
dependencies are installed. They do not establish Windows hardware acceptance.
"""
from __future__ import annotations

from contextlib import ExitStack
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools.reference_scene_fixtures import build_fixture, PreparedReferenceSimulation
from worldseed import app
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.entities.components import Inventory, Position, Vitals
from worldseed.presentation.gl_worldspace import GPUBackendUnavailable
from worldseed.sim.commands import WaitCommand
from worldseed.sim.realtime import RealtimeSimulationDriver
from worldseed.systems.state import pos_key
from worldseed.ui.gpu_terminal import GpuTerminal
from worldseed.ui.startup import StartSelection


class GPUMainGameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not GpuTerminal.available():
            raise unittest.SkipTest('optional pygame/ModernGL dependencies unavailable')
        cls.registry = ContentRegistry.load(DATA_DIR)

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        directory = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.directory = Path(directory)
        self.report = self.directory / 'gpu-main.json'
        environment = {'SDL_AUDIODRIVER': 'dummy', 'WORLDSEED_GPU_REPORT': str(self.report),
                       'WORLDSEED_GPU_SMOKE_FRAMES': '0', 'WORLDSEED_GPU_SIZE': '960x720'}
        if sys.platform != 'win32':
            environment['SDL_VIDEODRIVER'] = 'offscreen'
        self.stack.enter_context(patch.dict(os.environ, environment))
        self.term = GpuTerminal(960, 720)
        pg = self.term._native_pg
        self.set_mode = self.stack.enter_context(patch.object(pg.display, 'set_mode', wraps=pg.display.set_mode))
        try:
            self.term.enter()
        except GPUBackendUnavailable as exc:
            if 'current desktop OpenGL version' in str(exc):
                self.skipTest(f'host lacks required native OpenGL 3.3: {exc}')
            raise
        except pg.error as exc:
            self.skipTest(f'optional SDL OpenGL window unavailable: {exc}')
        self.addCleanup(self.term.restore)
        self.fixture = build_fixture('camp', self.registry, self.directory,
                                     width=960, height=720, zoom=28)
        self.addCleanup(self.fixture.close)
        sim = self.fixture.sim
        self.ctx = app.GameContext(self.fixture.db, self.registry, self.fixture.world,
                                  sim.entities, sim, sim.player_id)
        pg.event.clear()

    def present(self):
        ctx = self.ctx
        self.term.present_game(ctx.registry, ctx.world, ctx.entities, ctx.sim,
                               ctx.player_id, 'Full main-game test')

    def test_main_inventory_crafting_and_action_context_render_observationally_in_one_window(self):
        term, ctx = self.term, self.ctx
        before = self.fixture.authority_fingerprint()
        self.present()
        self.assertTrue(term._world_commands)
        self.assertTrue(term._snapshot.current_cells)
        self.assertIs(term.pg.display.get_surface(), term.screen)
        self.assertIsNot(term.screen, term._native_pg.display.get_surface())
        for method in (app._inventory_menu, app._crafting_menu,
                       app._action_palette, app._world_console):
            with self.subTest(menu=method.__name__), patch.object(term, 'read_key', return_value='ESC'):
                method(ctx, term)
            self.present()
        with patch.object(term, 'read_key', return_value='ESC'):
            app._world_context_menu(ctx, term, ctx.sim.player_pos)
        self.assertEqual(self.fixture.authority_fingerprint(), before)
        self.assertEqual(self.set_mode.call_count, 1)
        self.assertGreater(term._ui_gpu.uploads, 5)
        self.assertGreater(term._gpu_world_frames, 5)
        uploads = term._ui_gpu.uploads
        term._animate_idle_effects(term.pg.time.get_ticks() + 100)
        self.assertEqual(term._ui_gpu.uploads, uploads)
        term.restore()
        report = json.loads(self.report.read_text(encoding='utf-8'))
        self.assertEqual(report['backend'], 'gpu-main')
        self.assertEqual(report['source'], 'main-game')
        self.assertTrue(report['saved_world_support'])
        self.assertFalse(report['native_hardware_accepted'])

    def test_main_run_game_wait_uses_canonical_command_and_real_checkpoint_reload(self):
        ctx, term = self.ctx, self.term
        initial_minute = ctx.sim.clock.minute
        executed = []
        execute = ctx.sim.execute
        def record(command):
            executed.append(command)
            return execute(command)
        # The real run_game command dispatch, progress presentation, checkpoint,
        # database reopening and normal loader all remain active. Only startup
        # world realization is replaced by the prepared fixture subclass.
        with patch.object(term, 'read_key', side_effect=['.', 'QUIT']), \
             patch.object(ctx.sim, 'execute', side_effect=record):
            self.assertEqual(app.run_game(ctx, term), 'quit')
        self.assertEqual(len(executed), 1)
        self.assertIsInstance(executed[0], WaitCommand)
        self.assertEqual(ctx.sim.clock.minute, initial_minute + 10)
        self.assertIsNone(term._realtime_callback)
        self.assertIsNone(term._free_movement_callback)
        expected = {'position': asdict(ctx.entities.get(ctx.player_id, Position)),
                    'inventory': dict(ctx.entities.get(ctx.player_id, Inventory).items),
                    'vitals': asdict(ctx.entities.get(ctx.player_id, Vitals)),
                    'minute': ctx.sim.clock.minute, 'turn': ctx.sim.turn,
                    'name': ctx.sim.state.player_name,
                    'versions': {key: ctx.db.get_meta(key) for key in
                                 ('worldgen_version', 'resourcegen_version', 'hydrology_version')}}
        selection = StartSelection(ctx.db.path, False)
        with patch.object(app, 'Simulation', PreparedReferenceSimulation):
            loaded = app._load_context(selection, prepare_world=False)
        try:
            self.assertEqual(asdict(loaded.entities.get(loaded.player_id, Position)), expected['position'])
            self.assertEqual(loaded.entities.get(loaded.player_id, Inventory).items, expected['inventory'])
            self.assertEqual(asdict(loaded.entities.get(loaded.player_id, Vitals)), expected['vitals'])
            self.assertEqual(loaded.sim.clock.minute, expected['minute'])
            self.assertEqual(loaded.sim.turn, expected['turn'])
            self.assertEqual(loaded.sim.state.player_name, expected['name'])
            self.assertEqual({key: loaded.db.get_meta(key) for key in expected['versions']}, expected['versions'])
            self.assertEqual(loaded.db.verify(), [])
        finally:
            loaded.db.close()
        self.assertEqual(self.set_mode.call_count, 1)

    def test_native_input_modes_and_focus_loss_reuse_main_realtime_driver(self):
        term, pg = self.term, self.term.pg
        self.present()
        for key, expected in ((pg.K_RETURN, '\r'), (pg.K_TAB, '\t'), (pg.K_ESCAPE, 'ESC')):
            pg.event.clear()
            pg.event.post(pg.event.Event(pg.KEYDOWN, key=key, unicode=expected))
            self.assertEqual(term.read_key(), expected)
        driver = RealtimeSimulationDriver(self.ctx.sim)
        driver.resume()
        term.set_realtime_callback(driver.pump)
        term._held_movement[pg.K_d] = 1
        term._active_movement_key = pg.K_d
        term._filter_event(pg.event.Event(pg.WINDOWFOCUSLOST))
        self.assertTrue(driver.paused)
        self.assertFalse(term._held_movement)
        self.assertIsNone(term._active_movement_key)
        self.assertFalse(term._pump_realtime())
        rejected = term._filter_event(pg.event.Event(pg.KEYDOWN, key=pg.K_d, unicode='d'))
        self.assertEqual(rejected.type, pg.NOEVENT)
        term._filter_event(pg.event.Event(pg.WINDOWFOCUSGAINED))
        self.assertFalse(driver.paused)
        term.set_realtime_callback(None)
        self.assertEqual(self.set_mode.call_count, 1)

    def test_main_pointer_cannot_open_remembered_content_and_resize_preserves_window(self):
        term, sim, pg = self.term, self.ctx.sim, self.term.pg
        player = sim.player_pos
        sim._visible_tile_set.discard(pos_key(player.x, player.y, player.z))
        self.present()
        cell = (player.x, player.y, player.z)
        self.assertIn(cell, term._snapshot.remembered_cells)
        self.assertNotIn(cell, term._snapshot.current_cells)
        before = self.fixture.authority_fingerprint()
        context = term._hover_context
        point = (round(context['grid_x'] + (player.x + .5) * context['tile_px']),
                 round(context['grid_y'] + (player.y + .5) * context['tile_px']))
        self.assertTrue(context['used'].collidepoint(point))
        pg.event.clear()
        pg.event.post(pg.event.Event(pg.MOUSEBUTTONDOWN, button=3, pos=point))
        pg.event.post(pg.event.Event(pg.KEYDOWN, key=pg.K_ESCAPE, unicode=''))
        self.assertEqual(term.read_key(), 'ESC')
        self.assertEqual(self.fixture.authority_fingerprint(), before)
        term._resize(640, 480)
        self.present()
        self.assertEqual(term.screen.get_size(), (640, 480))
        self.assertEqual((term._ui_gpu.width, term._ui_gpu.height), (640, 480))
        self.assertTrue(term.screen.get_rect().contains(term._gpu_viewport))
        self.assertEqual(self.set_mode.call_count, 1)

    def test_entered_interior_uses_gpu_scene_and_main_context_ui_without_outdoor_reads(self):
        directory = self.directory / 'interior'
        directory.mkdir()
        fixture = build_fixture('interior', self.registry, directory,
                                width=960, height=720, zoom=28)
        self.addCleanup(fixture.close)
        sim, term = fixture.sim, self.term
        context = app.GameContext(fixture.db, self.registry, fixture.world,
                                  sim.entities, sim, sim.player_id)
        before = fixture.authority_fingerprint()
        def unexpected(*args, **kwargs):
            raise AssertionError('interior presentation queried outdoor terrain')
        with patch.object(fixture.world, 'tile_at', side_effect=unexpected), \
             patch.object(fixture.world, 'prepared_tile_at', side_effect=unexpected):
            term.present_game(context.registry, context.world, context.entities,
                              sim, context.player_id, 'Entered main-game interior')
        self.assertIsNotNone(term._snapshot.interior_scene)
        self.assertTrue(term._world_commands)
        self.assertIsNotNone(term._interior_context)
        self.assertIsNone(term._hover_context)
        fx = term._snapshot.atmosphere(1.)
        self.assertEqual((fx.rain, fx.snow, fx.fog, fx.cloud), (0., 0., 0., 0.))
        actor = sim.interiors.player_presence()
        with patch.object(term, 'read_key', return_value='ESC'):
            self.assertEqual(app._interior_context_menu(context, term, actor.x, actor.y), app.UI_BACK)
        self.assertEqual(fixture.authority_fingerprint(), before)
        self.assertEqual(self.set_mode.call_count, 1)

