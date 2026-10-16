"""Entered GPU interiors share engine sight, collision coordinates and light."""
from dataclasses import FrozenInstanceError, replace
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
        saved_cell = (3000//GRID)*cols + 4500//GRID
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
        self.assertTrue(all(c.opacity == .62 and c.remembered for c in remembered))
        self.assertFalse(any('visible-bed' in c.visual_id for c in frame.scenery))
        remembered_walls = [c for c in frame.scenery
                            if c.visual_id.startswith('interior-memory-wall:')]
        # Only remembered wall segments near remembered floor may be painted.
        self.assertTrue(remembered_walls)
        self.assertTrue(all(c.opacity == .62 and c.remembered and c.clip_rects
                            for c in remembered_walls))
        hidden = snapshot.gpu_frame(materials=Materials(), registry=self.registry,
                                    resource_style=lambda _: {},
                                    show_explored_memory=False)
        self.assertFalse(any(c.visual_id.startswith('interior-memory-floor:')
                             for c in hidden.ground))
        self.assertFalse(any(c.visual_id.startswith('interior-memory-wall:')
                             for c in hidden.scenery))
        self.assertEqual(plan.explored_cells, [saved_cell])

    def test_partly_seen_object_keeps_same_observed_art_across_live_memory_boundary(self):
        from worldseed.systems.interior_state import InteriorObservation
        sim,plan,player,_=self.fixture()
        obj=plan.furniture[0]
        plan.observed_objects=[InteriorObservation(obj.uid,'furniture',obj.piece_id,
            obj.x,obj.y,obj.w,obj.h)]
        live=(2000,4500,2500,5000)
        remembered=(2500,4500,3000,5000)
        with patch('worldseed.presentation.gpu_interiors.visible_floor_rects',
                   return_value=(live,)),patch(
                   'worldseed.presentation.gpu_interiors.remembered_floor_rects',
                   return_value=(remembered,)):
            snapshot=capture_live_scene(sim,self.camera(sim))
        scene=snapshot.interior_scene
        self.assertIn('visible-bed',{r.uid for r in scene.objects})
        self.assertIn('visible-bed',{r.uid for r in scene.memory_objects})
        self.assertEqual(next(r.content_id for r in scene.objects if r.uid=='visible-bed'),
                         next(r.content_id for r in scene.memory_objects if r.uid=='visible-bed'))
        frame=snapshot.gpu_frame(materials=Materials(),registry=self.registry,resource_style=lambda _: {})
        seen=next(c for c in frame.scenery if c.visual_id=='interior:visible-bed')
        frozen=next(c for c in frame.scenery if c.visual_id=='interior-memory-object:visible-bed')
        self.assertFalse(seen.remembered)
        self.assertTrue(frozen.remembered)
        self.assertFalse(any(a<x1 and c>x and b<y1 and d>y
            for a,b,c,d in seen.clip_rects for x,y,x1,y1 in frozen.clip_rects))

    def test_indoor_character_has_a_foot_anchored_contact_shadow(self):
        sim,plan,player,_=self.fixture()
        frame=capture_live_scene(sim,self.camera(sim)).gpu_frame(
            materials=Materials(),registry=self.registry,resource_style=lambda _: {})
        shadow=next(c for c in frame.scenery if c.visual_id=='interior-actor-contact:player')
        body=next(c for c in frame.scenery if c.visual_id=='interior-actor:player')
        self.assertLessEqual(shadow.bounds[1],body.bounds[3])
        self.assertGreaterEqual(shadow.bounds[3],body.bounds[3])
        self.assertTrue(shadow.clip_rects)

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
            if not command.visual_id.startswith(('interior-wall:', 'interior-memory-wall:')):
                # Sprite work is now cropped to its actual art rectangle;
                # each cropped clip must remain inside admitted sight.
                self.assertTrue(all(any(a <= x and b <= y and c >= x1 and d >= y1
                    for a,b,c,d in clips) for x,y,x1,y1 in command.clip_rects))
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

    def test_remembered_wall_and_visible_flat_stair_sort_without_crashing(self):
        from worldseed.presentation.gpu_interiors import prepare_interior_frame
        sim,_,_,_=self.fixture()
        snapshot=capture_live_scene(sim,self.camera(sim))
        scene=replace(snapshot.interior_scene,memory_walls=(
            ((5000,0,5200,8000),((5000,3000,5200,3500),)),))
        frame=prepare_interior_frame(scene,snapshot.camera,snapshot.viewer,Materials())
        self.assertTrue(any(c.visual_id.startswith('interior-memory-wall:') for c in frame.scenery))
        self.assertTrue(any(c.visual_id == 'interior:visible-stair' for c in frame.scenery))
        self.assertEqual(frame,prepare_interior_frame(scene,snapshot.camera,snapshot.viewer,Materials()))

    def test_observed_furniture_is_saved_as_last_seen_noninteractive_memory(self):
        from worldseed.systems.interiors import InteriorSystem
        sim,plan,player,actors=self.fixture()
        sim.state.interiors={plan.uid:plan}
        sim.state.interior_actors=dict(actors)
        sim.interiors=InteriorSystem(sim)
        sim.interiors.remember_player_sight(force=True)
        self.assertIn('visible-bed',{row.uid for row in plan.observed_objects})
        self.assertNotIn('private-cache',{row.uid for row in plan.observed_objects})
        original=next(row for row in plan.observed_objects if row.uid == 'visible-bed')
        player.x=7000
        # An unobserved rearrangement cannot update last-seen geometry.
        plan.furniture[0].x=3500
        sim.interiors.remember_player_sight(force=True)
        remembered=next(row for row in plan.observed_objects if row.uid == 'visible-bed')
        self.assertEqual(remembered,original)
        saved=plan.to_dict()
        self.assertEqual(saved,InteriorPlan.from_dict(saved).to_dict())
        snapshot=capture_live_scene(sim,self.camera(sim))
        scene=snapshot.interior_scene
        self.assertNotIn('visible-bed',{row.uid for row in scene.objects})
        self.assertIn('visible-bed',{row.uid for row in scene.memory_objects})
        self.assertIsNone(scene.hit_test(2.2,4.))
        frame=snapshot.gpu_frame(materials=Materials(),registry=self.registry,resource_style=lambda _: {})
        memory=[c for c in frame.scenery if c.visual_id == 'interior-memory-object:visible-bed']
        self.assertEqual(len(memory),1)
        self.assertTrue(memory[0].remembered)
        self.assertEqual(memory[0].opacity,.62)
        self.assertFalse(any('npc:visible' in c.visual_id for c in frame.scenery))
        self.assertEqual(saved,plan.to_dict())

    def test_fine_sight_edges_remember_wall_adjacent_floor_without_private_leaks(self):
        from worldseed.systems.interior_visibility import (
            visible_floor_rects,remember_floor_rects,remembered_floor_rects)
        sim,plan,player,_=self.fixture()
        plan.walls=[InteriorRect(5300,0,80,8000)]
        rects=visible_floor_rects(plan,player.x,player.y,720,65535)
        self.assertTrue(any(5000 < c <= 5300 for a,b,c,d in rects))
        self.assertTrue(all(c <= 5300 for a,b,c,d in rects))
        self.assertTrue(all(_rect_visible(player.x,player.y,rect,((5300,0,5380,8000),)) for rect in rects))
        remember_floor_rects(plan,rects)
        self.assertTrue(plan.explored_detail)
        self.assertTrue(all(c <= 5300 for a,b,c,d in remembered_floor_rects(plan)))
        self.assertEqual(plan.to_dict(),InteriorPlan.from_dict(plan.to_dict()).to_dict())
        legacy=plan.to_dict()
        legacy.pop('explored_detail')
        legacy.pop('observed_objects')
        loaded=InteriorPlan.from_dict(legacy)
        self.assertEqual(loaded.explored_detail,{})
        self.assertEqual(loaded.observed_objects,[])

    def test_hidden_wall_change_does_not_rewrite_last_observed_memory(self):
        from worldseed.systems.interiors import InteriorSystem
        sim,plan,player,actors=self.fixture()
        sim.state.interiors={plan.uid:plan}
        sim.state.interior_actors=dict(actors)
        sim.interiors=InteriorSystem(sim)
        sim.interiors.remember_player_sight(force=True)
        self.assertTrue(any(w.x == 5000 for w in plan.observed_walls))
        # A second opaque partition prevents observing the old wall's place.
        plan.walls=[InteriorRect(7000,0,200,8000)]
        player.x=8500
        sim.interiors.remember_player_sight(force=True)
        scene=capture_live_scene(sim,self.camera(sim)).interior_scene
        self.assertTrue(any(wall[0] == 5000 for wall,patches in scene.memory_walls))
        self.assertTrue(any(w.x == 5000 for w in plan.observed_walls))
        self.assertEqual(plan.to_dict(),InteriorPlan.from_dict(plan.to_dict()).to_dict())

    def test_wall_fragment_union_never_repaints_overlapping_alpha(self):
        from worldseed.presentation.gpu_interiors import _union_rects
        sources=((0,0,2,5),(0,3,2,8),(1,6,4,9))
        merged=_union_rects(sources)
        for y in range(10):
            for x in range(5):
                expected=any(a <= x < c and b <= y < d for a,b,c,d in sources)
                coverage=sum(a <= x < c and b <= y < d for a,b,c,d in merged)
                self.assertEqual(coverage,int(expected))

    def test_subcell_sight_and_floor_material_are_anchored_to_world_not_camera(self):
        sim,_,_,_=self.fixture()
        camera=self.camera(sim)
        first=capture_live_scene(sim,camera)
        moved_camera=replace(camera,center=WorldFoot(camera.center.x+.01,camera.center.y+.01,camera.center.z))
        second=capture_live_scene(sim,moved_camera)
        self.assertEqual(first.interior_scene.tiles,second.interior_scene.tiles)
        frame=first.gpu_frame(materials=Materials(),registry=self.registry,resource_style=lambda _: {})
        # Boundary refinements clip the same half-metre source instead of
        # squeezing the whole plank texture into each smaller fragment.
        self.assertTrue(all(abs((c.bounds[2]-c.bounds[0])-camera.scale*.5-.02) < 1e-8 for c in frame.ground))

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

    def test_actual_half_pixel_floor_sources_have_no_raster_cracks(self):
        try:
            import moderngl
        except ImportError:
            self.skipTest('optional ModernGL dependency unavailable')
        try:
            context=moderngl.create_standalone_context(require=330,backend='egl')
        except Exception as exc:
            self.skipTest('optional EGL unavailable: '+type(exc).__name__)
        from tests.test_gpu_visibility_shader import _OffscreenWindowContext
        from worldseed.presentation.gl_worldspace import GLWorldspaceRenderer,pixel_clip
        from worldseed.presentation.gpu_interiors import PreparedInterior,InteriorTile,prepare_interior_frame
        texture=target=renderer=None
        try:
            camera=WorldCamera(WorldFoot(.25,.5),641,481,48)
            scene=PreparedInterior('test','test','residence','','',0,1,
                (InteriorTile((0,0,500,500),32767),InteriorTile((0,500,500,1000),32767)),(),(),())
            materials=Materials()
            with patch.object(materials,'player',return_value=None):
                frame=prepare_interior_frame(scene,camera,camera.center,materials)
            texture=context.texture((641,481),4)
            target=context.framebuffer(color_attachments=[texture])
            renderer=GLWorldspaceRenderer(_OffscreenWindowContext(context,target),641,481,texture_budget=4096)
            renderer.draw(frame.commands,clear=(0,0,0,0))
            pixels=target.read(components=3,alignment=1)
            colors=set()
            for command in frame.ground:
                for clip in command.clip_rects:
                    x,y,w,h=pixel_clip(clip,641,481)
                    for py in range(y,y+h):
                        for px in range(x,x+w):
                            offset=(py*641+px)*3
                            self.assertNotEqual(pixels[offset:offset+3],b'\0\0\0',
                                f'floor raster crack at {(px,py)}')
                            colors.add(pixels[offset:offset+3])
            self.assertEqual(len(colors),1,'lighting must cover every admitted floor sample too')
        finally:
            if renderer is not None:renderer.close()
            if target is not None:target.release()
            if texture is not None:texture.release()
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
