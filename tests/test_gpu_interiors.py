"""Entered GPU interiors share engine sight, collision coordinates and light."""
from dataclasses import FrozenInstanceError
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import patch

from tools.reference_scene_fixtures import build_fixture
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.presentation.gpu_interiors import _rect_visible
from worldseed.presentation.live_gpu_scene import capture_live_scene, player_foot
from worldseed.presentation.worldspace import WorldCamera, WorldFoot
from worldseed.systems.interior_state import (InteriorActor, InteriorFurniture,
    InteriorPlan, InteriorRect, InteriorRoom, InteriorStair)


def unexpected(*args, **kwargs):
    raise AssertionError('interior presentation must not read/generate exterior state')


class Materials:
    def interior(self, category, uid):
        return (category+':'+uid, 1, b'\xa0\x80\x60\xff'*4, 2, 2)

    def player(self):
        return ('player', 1, b'\xff'*16, 2, 2)

    def actor(self, uid):
        return ('actor:'+uid, 1, b'\xff'*16, 2, 2)


class GPUInteriorContracts(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)

    def fixture(self):
        plan = InteriorPlan('interior:home', 'home', 'door:home', 300, 400, 0,
            10000, 8000, name='Entered home', function='house', entry_x=2500, entry_y=7000,
            walls=[InteriorRect(5000, 0, 200, 8000)],
            rooms=[InteriorRoom('public', 'Common room', InteriorRect(0, 0, 5000, 8000)),
                   InteriorRoom('secret', 'Private vault name', InteriorRect(5200, 0, 4800, 8000))],
            furniture=[InteriorFurniture('visible-bed', 'core:bed_piece', 2000, 3500, 1000, 1500),
                       InteriorFurniture('private-cache', 'core:large_table_piece', 6500, 3500, 1000, 1000),
                       InteriorFurniture('private-lamp', 'core:lamp_stand_piece', 6500, 2500, 500, 500)],
            stairs=[InteriorStair('visible-stair', 1000, 2500, 800, 1000, 'upstairs', 1000, 2500)],
            floor_count=2)
        player = InteriorActor(plan.uid, 2500, 3000)
        actors = [('player', player), ('visible', InteriorActor(plan.uid, 2200, 3100)),
                  ('private-person', InteriorActor(plan.uid, 7000, 3000)),
                  ('dead', InteriorActor(plan.uid, 2300, 3100))]
        state = NS(player_fx=.5, player_fy=.5,
            npcs={uid: NS(alive=uid != 'dead', hp=100, sex='female')
                  for uid, _ in actors if uid != 'player'})
        sim = NS(player_pos=WorldPos(300, 400), state=state, clock=NS(minute=720),
            interiors=NS(player_presence=lambda: player, current_plan=lambda: plan,
                         actors_in_space=lambda space: tuple(actors)),
            environment=None)
        return sim, plan, player, actors

    def camera(self, sim):
        return WorldCamera(player_foot(sim), 640, 480, 40)

    def test_hidden_rooms_props_and_actors_never_cross_detached_boundary(self):
        sim, plan, player, actors = self.fixture()
        before = plan.to_dict(), player.to_dict()
        snapshot = capture_live_scene(sim, self.camera(sim))
        scene = snapshot.interior_scene
        self.assertTrue(snapshot.interior)
        self.assertTrue(scene.tiles)
        self.assertTrue(scene.walls)
        self.assertEqual({a.uid for a in scene.actors}, {'npc:visible'})
        self.assertIn('visible-bed', {o.uid for o in scene.objects})
        self.assertIn('visible-stair', {o.uid for o in scene.objects})
        self.assertNotIn('private-cache', repr(scene))
        self.assertNotIn('private-lamp', repr(scene))
        self.assertNotIn('private-person', repr(scene))
        self.assertNotIn('Private vault name', repr(scene))
        self.assertTrue(all(tile.bounds[2] <= 5000 for tile in scene.tiles))
        self.assertEqual(snapshot.viewer, WorldFoot(2.5, 3., 0))
        self.assertEqual(snapshot.camera.center, snapshot.viewer)
        self.assertEqual(snapshot.current_cells, frozenset())
        self.assertEqual(before, (plan.to_dict(), player.to_dict()))

    def test_remembered_interior_floor_is_dim_but_live_contents_do_not_leak(self):
        from worldseed.systems.interior_visibility import GRID, grid_columns
        sim, plan, player, _ = self.fixture()
        cols = grid_columns(plan)
        # Remember a cell in the common room after standing there.
        saved_cell = (3000//GRID)*cols + 2500//GRID
        plan.explored_cells = [saved_cell]
        player.x, player.y = 7000, 3000  # visit the separate room
        snapshot = capture_live_scene(sim, self.camera(sim))
        scene = snapshot.interior_scene
        self.assertTrue(scene.memory_tiles)
        self.assertFalse(any(tile.bounds[0] >= 5000 for tile in scene.memory_tiles))
        self.assertFalse(any(obj.uid == 'visible-bed' for obj in scene.objects))
        frame = snapshot.gpu_frame(materials=Materials(), registry=self.registry,
                                   resource_style=lambda _: {})
        remembered = [c for c in frame.ground
                      if c.visual_id.startswith('interior-memory-floor:')]
        self.assertTrue(remembered)
        self.assertTrue(all(c.opacity == .42 for c in remembered))
        self.assertFalse(any('visible-bed' in c.visual_id for c in frame.scenery))
        hidden = snapshot.gpu_frame(materials=Materials(), registry=self.registry,
                                    resource_style=lambda _: {},
                                    show_explored_memory=False)
        self.assertFalse(any(c.visual_id.startswith('interior-memory-floor:')
                             for c in hidden.ground))
        self.assertEqual(plan.explored_cells, [saved_cell])

    def test_sight_rectangles_do_not_sample_thin_wall_away(self):
        # Every corner ray misses this tiny wall, but it lies in the full fan.
        wall = (1500, 1450, 1501, 1451)
        self.assertFalse(_rect_visible(0, 0, (2000, 1000, 3000, 3000), (wall,)))
        self.assertTrue(_rect_visible(0, 0, (2000, 1000, 3000, 3000), ()))
        # A rectangle in front of the same wall remains visible.
        self.assertTrue(_rect_visible(0, 0, (100, 100, 200, 200), (wall,)))

    def test_frame_is_detached_and_floor_clips_apply_to_every_private_sprite(self):
        sim, plan, player, actors = self.fixture()
        snapshot = capture_live_scene(sim, self.camera(sim))
        frame = snapshot.gpu_frame(materials=Materials(), registry=self.registry,
                                   resource_style=lambda _: {})
        clips = {clip for command in frame.ground for clip in command.clip_rects}
        self.assertTrue(frame.ground)
        self.assertTrue(any(c.visual_id == 'interior:visible-bed' for c in frame.scenery))
        self.assertTrue(any(c.visual_id == 'interior-shadow:visible-bed' for c in frame.scenery))
        self.assertTrue(any(c.visual_id == 'interior-actor:player' for c in frame.scenery))
        self.assertTrue(any(c.visual_id.startswith('interior-light:') for c in frame.scenery))
        for command in frame.scenery:
            if not command.visual_id.startswith('interior-wall:'):
                self.assertLessEqual(set(command.clip_rects), clips)
        plan.furniture.clear()
        plan.walls.clear()
        actors.clear()
        player.x += 1000
        self.assertEqual(frame, snapshot.gpu_frame(materials=Materials(),
            registry=self.registry, resource_style=lambda _: {}))
        with self.assertRaises(FrozenInstanceError):
            snapshot.interior_scene.name = 'changed'

    def test_selecting_objects_is_observational_and_requires_visible_floor(self):
        sim, plan, player, _ = self.fixture()
        scene = capture_live_scene(sim, self.camera(sim)).interior_scene
        self.assertEqual(scene.hit_test(2.2, 4.).uid, 'visible-bed')
        self.assertIsNone(scene.hit_test(7., 4.))
        self.assertEqual(scene.hit_test(1.2, 3.).direction, 'up')
        self.assertEqual(scene.hit_test(1.2, 3.).x, 1000)
        self.assertEqual(player.x, 2500)
        self.assertEqual(len(plan.furniture), 3)

    def test_wall_removal_and_player_motion_follow_authoritative_state(self):
        sim, plan, player, _ = self.fixture()
        closed = capture_live_scene(sim, self.camera(sim))
        plan.walls.clear()  # engine-authorized physical edit, outside rendering
        opened = capture_live_scene(sim, self.camera(sim))
        self.assertNotIn('private-cache', repr(closed.interior_scene))
        self.assertIn('private-cache', repr(opened.interior_scene))
        self.assertIn('npc:private-person', {a.uid for a in opened.interior_scene.actors})
        player.x, player.y = 3650, 4125
        moved = capture_live_scene(sim, self.camera(sim))
        self.assertEqual(moved.viewer, WorldFoot(3.65, 4.125, 0))
        self.assertEqual(closed.viewer, WorldFoot(2.5, 3., 0))

    def test_weather_is_sheltered_and_large_plan_fails_closed(self):
        sim, plan, _, _ = self.fixture()
        snapshot = capture_live_scene(sim, self.camera(sim))
        fx = snapshot.atmosphere(2.)
        self.assertEqual((fx.rain, fx.snow, fx.fog, fx.cloud, fx.sun), (0., 0., 0., 0., 1.))
        plan.walls *= 257
        self.assertIsNone(capture_live_scene(sim, self.camera(sim)).interior_scene)

    def test_private_lamp_cannot_light_through_the_authoritative_wall(self):
        sim, plan, _, _ = self.fixture()
        lit = capture_live_scene(sim, self.camera(sim))
        plan.furniture = [row for row in plan.furniture if row.uid != 'private-lamp']
        unlit = capture_live_scene(sim, self.camera(sim))
        self.assertEqual(lit.interior_scene.tiles, unlit.interior_scene.tiles)

    def test_actual_gpu_pixels_leave_hidden_room_black(self):
        try:
            import moderngl
        except ImportError:
            self.skipTest('optional ModernGL dependency unavailable')
        try:
            context = moderngl.create_standalone_context(require=330, backend='egl')
        except Exception as exc:
            self.skipTest('optional EGL unavailable: '+type(exc).__name__)
        from tests.test_gpu_visibility_shader import _OffscreenWindowContext
        from worldseed.presentation.gl_worldspace import GLWorldspaceRenderer
        texture = target = renderer = None
        try:
            sim, _, _, _ = self.fixture()
            snapshot = capture_live_scene(sim, self.camera(sim))
            frame = snapshot.gpu_frame(materials=Materials(), registry=self.registry,
                                       resource_style=lambda _: {})
            texture = context.texture((640, 480), 4)
            target = context.framebuffer(color_attachments=[texture])
            renderer = GLWorldspaceRenderer(_OffscreenWindowContext(context, target),
                                           640, 480, texture_budget=4096)
            renderer.draw(frame.commands, clear=(0, 0, 0, 0))
            pixels = target.read(components=3, alignment=1)
            private_x = round(snapshot.camera.to_screen(WorldFoot(5.2, 0))[0])+1
            self.assertTrue(any(pixels))
            for row in range(480):
                hidden = pixels[(row*640+private_x)*3:((row+1)*640)*3]
                self.assertEqual(hidden, bytes(len(hidden)), f'private room exposed in row {row}')
        finally:
            if renderer is not None:
                renderer.close()
            if target is not None:
                target.release()
            if texture is not None:
                texture.release()
            context.release()

    def test_actual_entered_plan_never_queries_outdoor_geometry_or_mutates(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = build_fixture('interior', self.registry, Path(directory),
                                    width=640, height=480, zoom=28)
            try:
                sim = fixture.sim
                before = fixture.authority_fingerprint()
                queries = []
                fixture.db.connection.set_trace_callback(queries.append)
                with patch.object(sim.world, 'prepared_tile_at', unexpected), \
                        patch.object(sim.world, 'tile_at', unexpected), \
                        patch.object(sim.npcs, 'indexed_npcs_in_rect', unexpected), \
                        patch.object(sim.interiors, '_prepare', unexpected), \
                        patch.object(sim.settlement_physicalization, 'shell_at', unexpected):
                    snapshot = capture_live_scene(sim, self.camera(sim))
                    frame = snapshot.gpu_frame(materials=Materials(), registry=self.registry,
                                               resource_style=lambda _: {})
                fixture.db.connection.set_trace_callback(None)
                self.assertTrue(snapshot.interior_scene.tiles)
                self.assertTrue(frame.commands)
                self.assertEqual(queries, [])
                self.assertEqual(before, fixture.authority_fingerprint())
            finally:
                fixture.close()
