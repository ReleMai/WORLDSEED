"""W3 public exteriors never grant interior sight or physical authority."""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path
import tempfile
from unittest import TestCase
from unittest.mock import patch

from tools.reference_scene_fixtures import build_fixture
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.presentation.gpu_buildings import (BuildingArt, PreparedBuildingDoor,
    PreparedBuildingShell, building_commands, building_sort_keys, load_building_art)
from worldseed.presentation.live_gpu_scene import capture_live_scene
from worldseed.presentation.worldspace import WorldCamera, WorldFoot
from worldseed.systems.building_shells import BuildingShell
from worldseed.systems.interior_state import InteriorActor
from worldseed.systems.state import CreatureState, FireCell, NPCState, pos_key


def unexpected(*args, **kwargs):
    raise AssertionError('drawing may not scan, generate, open rooms or mutate')


class IndexedOnlyDict(dict):
    values = items = __iter__ = unexpected


class FakeMaterials:
    def asset(self, path):
        return (str(path), 1, b'\x70\x90\x44\xff'*4, 2, 2)

    def player(self):
        return ('player', 1, b'\xff'*16, 2, 2)

    def actor(self, content_id):
        return ('actor:'+content_id, 1, b'\xff'*16, 2, 2)

    def building(self, row):
        body = ('body', 1, b'\x80\x60\x30\xff'*4, 2, 2)
        door = ('door:'+str(row.door.opened if row.door else False), 1, b'\x60\x40\x20\xff'*4, 2, 2)
        return BuildingArt(body, door, (.3, .6, .25, .4))


class GPUExteriorContracts(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)

    @contextmanager
    def fixture(self, name='village_street'):
        with tempfile.TemporaryDirectory() as directory:
            fixture = build_fixture(name, self.registry, Path(directory), width=640, height=480, zoom=28)
            try:
                yield fixture
            finally:
                fixture.close()

    def camera(self, sim):
        p = sim.player_pos
        return WorldCamera(WorldFoot(p.x+.5, p.y+.5, p.z), 640, 480, 28)

    def visible_shell(self, sim, camera):
        from worldseed.presentation.gpu_scene_bridge import cell_bounds
        left, top, right, bottom = cell_bounds(camera)
        return next((shell, (x, y, 0)) for shell in sim.settlement_physicalization._shells.values()
                    for x, y in shell.footprint if left <= x < right and top <= y < bottom)

    def test_real_village_closed_roofs_and_private_actors_are_read_only(self):
        with self.fixture() as fixture:
            sim, camera = fixture.sim, self.camera(fixture.sim)
            shell, cell = self.visible_shell(sim, camera)
            sim.state.npcs['secret'] = NPCState('secret', 'Private resident name', 30,
                'farmer', [], *cell, '', '')
            sim.state.interior_actors['secret'] = InteriorActor('interior:'+shell.uid, 100, 100)
            sim.state.creatures['secret-pet'] = CreatureState('secret-pet', 'core:deer', *cell, 50)
            sim.state.fires['secret-fire'] = FireCell(*cell, 70, 80)
            sim.npcs.rebuild_spatial_index()
            before = fixture.authority_fingerprint()
            physical = sim.settlement_physicalization
            physical._shells = IndexedOnlyDict(physical._shells)
            old_snapshot = physical._viewport_shell_snapshot
            queries = []
            fixture.db.connection.set_trace_callback(queries.append)
            try:
                with ExitStack() as guards:
                    for owner, name in ((physical, 'shells_in_bounds'), (sim.world, 'tile_at'),
                            (sim.resources, 'feature_at'), (sim.interiors, 'prepare_workplace'),
                            (sim.npcs, 'rebuild_spatial_index')):
                        guards.enter_context(patch.object(owner, name, unexpected))
                    snapshot = capture_live_scene(sim, camera)
                    frame = snapshot.gpu_frame(materials=FakeMaterials(), registry=self.registry,
                                               resource_style=lambda _: {})
            finally:
                fixture.db.connection.set_trace_callback(None)
            self.assertTrue(snapshot.buildings)
            self.assertTrue(any(command.visual_id == 'building:'+shell.uid for command in frame.scenery))
            self.assertNotIn(cell, snapshot.current_cells | snapshot.remembered_cells)
            self.assertNotIn(cell, dict(snapshot.terrain))
            self.assertFalse(any(actor.uid in {'npc:secret', 'creature:secret-pet'} for actor in snapshot.actors))
            self.assertFalse(any(fire.cell == cell for fire in snapshot.fires))
            self.assertNotIn('Private resident name', repr(snapshot))
            self.assertEqual(queries, [])
            self.assertIs(physical._viewport_shell_snapshot, old_snapshot)
            self.assertEqual(before, fixture.authority_fingerprint())

    def test_partial_sight_clips_shell_and_never_uses_discovery_as_current(self):
        with self.fixture() as fixture:
            sim, camera = fixture.sim, self.camera(fixture.sim)
            shell, cell = self.visible_shell(sim, camera)
            sim._visible_tile_set = {pos_key(*cell)}
            snapshot = capture_live_scene(sim, camera)
            self.assertEqual(len(snapshot.buildings), 1)
            row = snapshot.buildings[0]
            self.assertEqual(row.visible_cells, frozenset({cell}))
            commands = building_commands(snapshot.buildings, camera, FakeMaterials())
            px, py = camera.to_screen(WorldFoot(*cell))
            self.assertTrue(commands)
            self.assertTrue(all(command.clip_rects == ((px, py, px+camera.scale, py+camera.scale),)
                                for command in commands))
            self.assertTrue(all(command.opacity == 1 and command.fade_radius == 0
                                and command.local_alpha == 1 for command in commands))
            if shell.entrance != cell[:2]:
                self.assertIsNone(row.door)
            sim._visible_tile_set.clear()
            self.assertEqual(capture_live_scene(sim, camera).buildings, ())

    def test_door_state_is_detached_and_only_a_seen_physical_threshold_is_copied(self):
        with self.fixture() as fixture:
            sim, camera = fixture.sim, self.camera(fixture.sim)
            initial = capture_live_scene(sim, camera)
            row = next(row for row in initial.buildings if row.door is not None)
            state = sim.state.door_security[row.door.uid]
            state.forced = False
            state.answering_npc_uid = ''
            closed = capture_live_scene(sim, camera)
            state.forced = True
            opened = capture_live_scene(sim, camera)
            before_row = next(r for r in closed.buildings if r.shell.uid == row.shell.uid)
            after_row = next(r for r in opened.buildings if r.shell.uid == row.shell.uid)
            self.assertFalse(before_row.door.opened)
            self.assertTrue(after_row.door.opened)
            with self.assertRaises(FrozenInstanceError):
                before_row.door.opened = True
            self.assertTrue(any(c.texture_id == 'door:False' for c in building_commands((before_row,), camera, FakeMaterials())))
            self.assertTrue(any(c.texture_id == 'door:True' for c in building_commands((after_row,), camera, FakeMaterials())))
            sim._visible_tile_set.discard(pos_key(*row.door.cell))
            hidden = capture_live_scene(sim, camera)
            hidden_row = next(r for r in hidden.buildings if r.shell.uid == row.shell.uid)
            self.assertIsNone(hidden_row.door)
            self.assertNotIn(row.door.cell, hidden.current_cells)

    def test_entered_private_interior_retains_fail_closed_boundary(self):
        with self.fixture('interior') as fixture:
            sim = fixture.sim
            before = fixture.authority_fingerprint()
            with patch.object(sim.settlement_physicalization, 'shell_at', unexpected), \
                    patch.object(sim.world, 'prepared_tile_at', unexpected):
                snapshot = capture_live_scene(sim, self.camera(sim))
            self.assertTrue(snapshot.interior)
            self.assertEqual(snapshot.buildings, ())
            self.assertEqual(snapshot.current_cells, frozenset())
            self.assertEqual(before, fixture.authority_fingerprint())

    def test_courtyards_and_door_identity_cannot_be_approved_by_bounds(self):
        shell = BuildingShell('house', '', 'residence', 'core:house',
            ((3, 3), (4, 3), (3, 4)), (3, 4), 'door', 0, 'courtyard', (3, 3, 4, 4))
        row = PreparedBuildingShell(shell, frozenset({(3, 3, 0), (3, 4, 0)}),
                                    door=PreparedBuildingDoor('door', (3, 4, 0)))
        with self.assertRaisesRegex(ValueError, 'exact physical'):
            PreparedBuildingShell(shell, frozenset({(4, 4, 0)}))
        with self.assertRaisesRegex(ValueError, 'threshold'):
            PreparedBuildingShell(shell, row.visible_cells, door=PreparedBuildingDoor('other-door', (3, 4, 0)))
        camera = WorldCamera(WorldFoot(4, 4, 0), 128, 128, 16)
        commands = building_commands((row,), camera, FakeMaterials())
        self.assertEqual(len(commands), 2)
        self.assertEqual(len(commands[0].clip_rects), 2)
        self.assertLess(building_sort_keys((row,))[commands[0].visual_id],
                        building_sort_keys((row,))[commands[1].visual_id])
        # Art retains the physical extent and never grows a new hit/collision area.
        self.assertEqual(commands[0].bounds, (*camera.to_screen(WorldFoot(3, 3)),
                                             *camera.to_screen(WorldFoot(5, 5))))

    def test_real_authored_building_sources_are_bounded_cached_and_not_world_frames(self):
        try:
            import pygame
        except ImportError:
            self.skipTest('optional pygame image dependency unavailable')
        from worldseed.presentation.gpu_scene_bridge import GpuMaterialSource
        with self.fixture() as fixture:
            snapshot = capture_live_scene(fixture.sim, self.camera(fixture.sim))
            row = next(row for row in snapshot.buildings if row.door is not None)
            materials = GpuMaterialSource(pygame)
            first = load_building_art(materials, row)
            second = load_building_art(materials, row)
            self.assertIs(first.body, second.body)
            self.assertIs(first.door, second.door)
            self.assertLessEqual(max(first.body[3:]), 512)
            self.assertLessEqual(max(first.door[3:]), 128)
            self.assertEqual(len(first.body[2]), first.body[3]*first.body[4]*4)
            self.assertNotEqual(first.body[3:], (snapshot.camera.width_px, snapshot.camera.height_px))

    def test_actual_gl_building_pixels_never_paint_unseen_footprint_or_courtyard(self):
        try:
            import moderngl
        except ImportError:
            self.skipTest('optional ModernGL dependency unavailable')
        try:
            context = moderngl.create_standalone_context(require=330, backend='egl')
        except Exception as exc:
            self.skipTest(f'optional EGL driver unavailable: {type(exc).__name__}')
        from tests.test_gpu_visibility_shader import _OffscreenWindowContext
        from worldseed.presentation.gl_worldspace import GLWorldspaceRenderer
        texture = target = renderer = None
        try:
            shell = BuildingShell('house', '', 'residence', 'core:house',
                ((3, 3), (4, 3), (3, 4)), (3, 4), 'door', 0, 'courtyard', (3, 3, 4, 4))
            row = PreparedBuildingShell(shell, frozenset({(3, 4, 0)}))
            camera = WorldCamera(WorldFoot(4, 4, 0), 64, 64, 16)
            commands = building_commands((row,), camera, FakeMaterials())
            texture = context.texture((64, 64), 4)
            target = context.framebuffer(color_attachments=[texture])
            renderer = GLWorldspaceRenderer(_OffscreenWindowContext(context, target), 64, 64,
                                           texture_budget=4096)
            renderer.draw(commands, clear=(0, 0, 0, 0))
            pixels = target.read(components=3, alignment=1)
            visible = 0
            for gl_y in range(64):
                y = 63-gl_y
                for x in range(64):
                    rgb = pixels[(gl_y*64+x)*3:(gl_y*64+x)*3+3]
                    if 16 <= x < 32 and 32 <= y < 48:
                        self.assertNotEqual(rgb, b'\0\0\0')
                        visible += 1
                    else:
                        self.assertEqual(rgb, b'\0\0\0', f'building revealed {(x, y)}')
            self.assertEqual(visible, 256)
        finally:
            if renderer is not None:
                renderer.close()
            if target is not None:
                target.release()
            if texture is not None:
                texture.release()
            context.release()
