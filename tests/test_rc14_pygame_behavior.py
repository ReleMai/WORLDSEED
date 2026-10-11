"""Behavioral checks using SDL's dummy display; no real desktop required."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from worldseed.ui.pygame_terminal import PygameTerminal


@unittest.skipUnless(PygameTerminal.available(), 'pygame optional for terminal-only environments')
class PygameBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'SDL_VIDEODRIVER': 'dummy', 'SDL_AUDIODRIVER': 'dummy'})
        self.env.start()
        self.term = PygameTerminal(); self.term.enter()
        self.pg = self.term.pg
        self.pg.event.clear()

    def tearDown(self):
        self.pg.quit(); self.env.stop()

    def test_startup_flush_drops_stale_escape_but_accepts_fresh_input(self):
        pg = self.pg
        pg.event.post(pg.event.Event(pg.KEYDOWN, key=pg.K_ESCAPE, unicode='\x1b'))
        self.term.discard_pending_input()
        self.assertFalse(pg.event.peek(pg.KEYDOWN))
        self.assertEqual(pg.key.get_repeat(), (0, 0))
        pg.event.post(pg.event.Event(pg.KEYDOWN, key=pg.K_w, unicode='w'))
        self.assertEqual(self.term.read_key(), 'w')
        self.assertEqual(pg.key.get_repeat(), (0, 0))
        pg.event.post(pg.event.Event(pg.KEYDOWN, key=pg.K_ESCAPE, unicode='\x1b'))
        self.assertEqual(self.term.read_key(), 'ESC')

    def test_movement_repeat_queue_is_not_replayed_after_release(self):
        pg=self.pg
        pg.event.post(pg.event.Event(pg.KEYDOWN,key=pg.K_d,unicode='d'))
        for _ in range(100):
            pg.event.post(pg.event.Event(pg.KEYDOWN,key=pg.K_d,unicode='d',repeat=True))
        pg.event.post(pg.event.Event(pg.KEYUP,key=pg.K_d,unicode=''))
        pg.event.post(pg.event.Event(pg.KEYDOWN,key=pg.K_ESCAPE,unicode='\x1b'))
        self.assertEqual(self.term.read_key(),'d')
        # Duplicate presses are drained/ignored and KEYUP clears held state
        # before any synthetic repeat can be returned.
        self.assertEqual(self.term.read_key(),'ESC')
        self.assertIsNone(self.term._active_movement_key)

    def test_free_movement_services_queued_release_before_next_step(self):
        pg=self.pg;moves=[]
        self.term.set_free_movement_callback(
            lambda dt,dx,dy,sprint: moves.append((dx,dy,sprint)) or bool(dx or dy)
        )
        # Reproduce the maximized-window failure: a movement key is logically
        # held, enough wall time elapsed for another continuous step, but KEYUP
        # is already waiting in SDL's queue. The release must win before another
        # realtime movement callback can run.
        self.term._held_movement[pg.K_d]=1
        self.term._active_movement_key=pg.K_d
        self.term._free_movement_last_ms=-1000
        pg.event.post(pg.event.Event(pg.KEYUP,key=pg.K_d,unicode=''))
        pg.event.post(pg.event.Event(pg.KEYDOWN,key=pg.K_ESCAPE,unicode='\\x1b'))
        self.assertEqual(self.term.read_key(),'ESC')
        self.assertEqual(moves,[])
        self.assertNotIn(pg.K_d,self.term._held_movement)
        self.assertIsNone(self.term._active_movement_key)

    def test_queued_release_skips_expensive_weather_animation(self):
        pg=self.pg
        self.term._held_movement[pg.K_w]=pg.time.get_ticks()
        self.term._active_movement_key=pg.K_w
        pg.event.post(pg.event.Event(pg.KEYUP,key=pg.K_w,unicode=''))
        pg.event.post(pg.event.Event(pg.KEYDOWN,key=pg.K_ESCAPE,unicode='\\x1b'))
        with patch.object(self.term,'_animate_idle_effects') as animate:
            self.assertEqual(self.term.read_key(),'ESC')
            animate.assert_not_called()
        self.assertFalse(self.term._held_movement)

    def test_duplicate_maximize_resize_does_not_recreate_display(self):
        pg=self.pg
        self.term._resize(1920,1080)
        existing=pg.display.get_surface()
        with patch.object(pg.display,'set_mode',wraps=pg.display.set_mode) as set_mode:
            self.term._resize(1920,1080)
            set_mode.assert_not_called()
        self.assertIs(self.term.screen,existing)
        self.assertEqual(self.term.screen.get_size(),(1920,1080))

    def test_large_window_throttles_redraw_not_motion_or_release(self):
        pg=self.pg
        self.term._resize(1920,1080)
        samples=[]
        self.term.set_free_movement_callback(
            lambda dt,dx,dy,sprint: samples.append((dt,dx,dy)) or True
        )
        self.term._input_mode='world'
        self.term._held_movement[pg.K_d]=1
        self.term._active_movement_key=pg.K_d
        self.term._free_movement_last_ms=100
        self.assertTrue(self.term._pump_free_movement(116))
        self.assertFalse(self.term._pump_free_movement(132))
        self.assertFalse(self.term._pump_free_movement(148))
        self.assertTrue(self.term._pump_free_movement(166))
        self.assertEqual(len(samples),4)
        self.assertTrue(all(dx==1 and dy==0 for _,dx,dy in samples))
        self.assertTrue(all(0 < dt <= 0.1 for dt,_,_ in samples))

    def test_keyup_flushes_pending_fractional_frame(self):
        pg=self.pg
        self.term._held_movement[pg.K_a]=1
        self.term._active_movement_key=pg.K_a
        self.term._movement_redraw_pending=True
        pg.event.post(pg.event.Event(pg.KEYUP,key=pg.K_a,unicode=''))
        self.assertEqual(self.term.read_key(),'UI_REDRAW')
        self.assertFalse(self.term._held_movement)
        self.assertFalse(self.term._movement_redraw_pending)

    def test_due_movement_redraw_never_runs_idle_weather_first(self):
        pg=self.pg
        self.term.set_free_movement_callback(lambda dt,dx,dy,sprint: True)
        self.term._held_movement[pg.K_d]=1
        self.term._active_movement_key=pg.K_d
        self.term._free_movement_last_ms=pg.time.get_ticks()-100
        with patch.object(self.term,'_animate_idle_effects',
                          side_effect=AssertionError('idle weather rendered before player input')):
            self.assertEqual(self.term.read_key(),'UI_REDRAW')

    def test_startup_flush_preserves_window_close(self):
        self.pg.event.post(self.pg.event.Event(self.pg.QUIT))
        self.term.discard_pending_input()
        self.assertEqual(self.term.read_key(), 'QUIT')

    def test_combat_requires_fresh_movement_press_and_never_replays_hold(self):
        pg=self.pg;self.term.set_combat_callback(lambda:True)
        pg.event.post(pg.event.Event(pg.KEYDOWN,key=pg.K_d,unicode='d'))
        self.assertEqual(self.term.read_key(),'d')
        self.term._movement_next_repeat_ms=0
        events=[pg.event.Event(pg.NOEVENT),
                pg.event.Event(pg.KEYDOWN,key=pg.K_d,unicode='d',repeat=True),
                pg.event.Event(pg.KEYDOWN,key=pg.K_ESCAPE,unicode='\x1b')]
        with patch.object(pg.event,'wait',side_effect=events):
            self.assertEqual(self.term.read_key(),'ESC')
        self.assertIsNone(self.term._active_movement_key)
        pg.event.post(pg.event.Event(pg.KEYUP,key=pg.K_d,unicode=''))
        pg.event.post(pg.event.Event(pg.KEYDOWN,key=pg.K_d,unicode='d'))
        self.assertEqual(self.term.read_key(),'d')

    def test_long_footer_does_not_paint_outside_its_panel(self):
        pg = self.pg
        self.term.screen.fill((0, 0, 0))
        rect = pg.Rect(20, 400, 474, 86)
        original_clip = self.term.screen.get_clip()
        self.term._draw_footer(rect, 'Long event message ' * 80)
        self.assertEqual(self.term.screen.get_clip(), original_clip)
        # All pixels to the right belong to the sidebar, and must stay black.
        sidebar = self.term.screen.subsurface(pg.Rect(rect.right, 400, 280, 86))
        self.assertEqual(set(pg.image.tobytes(sidebar, 'RGB')), {0})
        self.assertNotEqual(set(pg.image.tobytes(self.term.screen.subsurface(rect), 'RGB')), {0})

    def test_mousewheel_zoom_bounds_and_keyboard_reset(self):
        pg = self.pg
        for direction, expected in ((1, 56), (-1, 16)):
            for _ in range(20):
                pg.event.post(pg.event.Event(pg.MOUSEWHEEL, x=0, y=direction))
                self.assertEqual(self.term.read_key(), 'RESIZE')
            self.assertEqual(self.term._tile_px, expected)
        pg.event.post(pg.event.Event(pg.KEYDOWN, key=pg.K_0, unicode='0'))
        self.assertEqual(self.term.read_key(), 'RESIZE')
        self.assertEqual(self.term._tile_px, 28)

    def test_render_at_all_zoom_limits_is_observational_and_centered(self):
        from worldseed.config import DATA_DIR
        from worldseed.content.registry import ContentRegistry
        from worldseed.core.coords import WorldPos
        from worldseed.entities.components import Inventory, Position, Vitals
        from worldseed.entities.store import EntityStore
        from worldseed.persistence.database import WorldDatabase
        from worldseed.sim.engine import Simulation
        from worldseed.systems.state import LivingWorldState
        from worldseed.world.generator import WorldGenerator
        from worldseed.world.world import World
        reg = ContentRegistry.load(DATA_DIR); seed = b'pygame-dev4'
        with tempfile.TemporaryDirectory() as td:
            db = WorldDatabase.create(Path(td) / 'test.db', 'test', seed.hex())
            world = World(WorldGenerator(seed, reg), reg, db)
            e = EntityStore(); pid = e.spawn(preferred_id=1)
            pos = WorldPos(0, 0, 0)
            e.add(pid, Position(pos)); e.add(pid, Inventory()); e.add(pid, Vitals())
            sim = Simulation(world, e, reg, 0, LivingWorldState(), seed)
            sim._discover(pos)
            before = sim.state.to_dict(); minute = sim.clock.minute
            for width, height in ((1280, 800), (800, 520)):
                self.term._resize(width, height)
                for size in (16, 28, 56):
                    self.term._tile_px = size
                    self.term.present_game(reg, world, e, sim, pid)
                    ctx = self.term._hover_context
                    cols, rows = ctx['used'].width // size, ctx['used'].height // size
                    self.assertEqual(ctx['left'] + cols // 2, pos.x)
                    self.assertEqual(ctx['top'] + rows // 2, pos.y)
            self.assertEqual(sim.state.to_dict(), before)
            self.assertEqual(sim.clock.minute, minute)
            # An open overview must relinquish the local map's damage snapshot.
            with patch.object(world.generator, 'generate_chunk', side_effect=AssertionError('map generated terrain')), patch.object(sim.region_planner, 'plan', side_effect=AssertionError('map planned regions')):
                for width, height in ((1280, 800), (800, 520)):
                    self.term._resize(width, height)
                    self.term.present_game(reg, world, e, sim, pid)
                    self.assertIsNotNone(self.term._hover_map_snapshot)
                    self.term.present_region_map(sim)
                    self.assertIsNone(self.term._hover_context)
                    self.assertIsNone(self.term._hover_map_snapshot)
                    pixels = self.pg.image.tobytes(self.term.screen, 'RGB')
                    for mouse in ((300, 200), (600, 400), (700, 300)):
                        self.pg.event.post(self.pg.event.Event(self.pg.MOUSEMOTION, pos=mouse, rel=(1, 1), buttons=(0, 0, 0)))
                        self.pg.event.post(self.pg.event.Event(self.pg.KEYDOWN, key=self.pg.K_ESCAPE, unicode='\x1b'))
                        self.assertEqual(self.term.read_key(), 'ESC')
                        self.assertEqual(self.pg.image.tobytes(self.term.screen, 'RGB'), pixels)
            self.assertEqual(sim.state.to_dict(), before)
            self.assertEqual(sim.clock.minute, minute)
            db.close()

    def test_terrain_loader_trims_bright_export_border_before_scaling(self):
        pg=self.pg
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"bordered.png"
            src=pg.Surface((32,32),pg.SRCALPHA)
            src.fill((245,245,245,255))
            pg.draw.rect(src,(34,45,37,255),(1,1,30,30))
            pg.image.save(src,str(path))
            out=self.term._load_terrain_sprite(path,28)
            self.assertIsNotNone(out)
            for point in ((0,0),(27,0),(0,27),(27,27),(14,0),(0,14)):
                rgb=out.get_at(point)[:3]
                self.assertLess(max(rgb),100,(point,rgb))

    def test_connected_roof_surface_has_no_shared_tile_frame(self):
        piece=type("Piece",(),{"id":"test:timber_roof","category":"roof","material":"timber","tags":()})()
        isolated=self.term._settlement_roof_surface(piece,28,0)
        connected=self.term._settlement_roof_surface(piece,28,15)
        self.assertIsNotNone(isolated);self.assertIsNotNone(connected)
        self.assertNotEqual(self.pg.image.tobytes(isolated,"RGBA"),self.pg.image.tobytes(connected,"RGBA"))
        # Connected roof pixels remain opaque all the way to each cell edge;
        # there is no transparent/white grid line between neighboring cells.
        for point in ((0,14),(27,14),(14,0),(14,27)):
            self.assertEqual(connected.get_at(point).a,255)

    def test_idle_water_animates_cached_pixels_and_stops_in_console(self):
        pg=self.pg;term=self.term
        used=pg.Rect(20,20,64,64)
        term._hover_context={'used':used,'tile_px':32,'left':0,'top':0}
        term._hover_map_snapshot=pg.Surface((64,64));term._last_mouse=(0,0)
        term._hover_rect=None;term._hover_tile_rect=None
        base=pg.Surface((32,32));base.fill((24,85,110))
        term._water_animation_cells=[(pg.Rect(20,20,32,32),base,'render:ocean_deep',1,0,40)]
        term._water_animation_phase=-1
        term._animate_idle_water(160)
        first=pg.image.tobytes(term.screen,'RGB')
        term._animate_idle_water(640)
        self.assertNotEqual(first,pg.image.tobytes(term.screen,'RGB'))
        term.present('WORLD CONSOLE')
        console=pg.image.tobytes(term.screen,'RGB')
        term._animate_idle_water(960)
        self.assertEqual(console,pg.image.tobytes(term.screen,'RGB'))
