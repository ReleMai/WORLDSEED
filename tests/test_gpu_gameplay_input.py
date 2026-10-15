"""W2 event/controller boundary, canonical motion and prepared-engine collision."""
from __future__ import annotations

from pathlib import Path
import tempfile
from types import MethodType
import unittest

from worldseed.core.coords import WorldPos
from worldseed.presentation.worldspace import WorldCamera, WorldFoot
from worldseed.sim.commands import MoveCommand, PickupCommand, WaitCommand
from worldseed.ui.gpu_gameplay_input import GpuGameplayInput, project_pointer


class InputSimulation:
    player_id = 1

    def __init__(self):
        self.calls = []
        self.combat = False

    def set_free_movement_enabled(self, enabled):
        self.calls.append(('enabled', enabled))

    def combat_active(self):
        return self.combat

    def execute(self, command):
        self.calls.append(('command', command))

    def update_free_movement(self, dt, dx, dy, sprint):
        self.calls.append(('move', dt, dx, dy, sprint))
        return bool(dx or dy)

    def advance_realtime(self, minutes):
        self.calls.append(('realtime', minutes))
        return minutes


class GpuGameplayInputTests(unittest.TestCase):
    def setUp(self):
        self.sim = InputSimulation()
        self.input = GpuGameplayInput(self.sim, now=0.)
        self.addCleanup(self.input.close)

    def test_held_motion_reuses_engine_once_and_release_precedes_update(self):
        self.input.press('D', now=0.)
        self.input.press('d', repeat=True, now=0.)
        self.input.press('d', now=0.)
        self.assertTrue(self.input.update(.1, sprint=True))
        self.assertEqual(self.sim.calls[-1], ('move', .1, 1, 0, True))
        self.assertFalse(any(row[0] == 'command' for row in self.sim.calls))
        self.input.release('d')
        self.assertFalse(self.input.update(.2))
        self.assertEqual(self.sim.calls[-1][2:4], (0, 0))

    def test_focus_loss_clears_held_input_and_drops_wall_time(self):
        self.input.press('w', now=0.)
        self.input.set_focus(False, now=.1)
        before = list(self.sim.calls)
        self.input.press('p', now=100.)
        self.assertFalse(self.input.update(100.))
        self.assertEqual(self.sim.calls, before)
        self.input.set_focus(True, now=100.)
        self.input.update(100.1)
        self.assertEqual(self.sim.calls[-1][2:4], (0, 0))
        self.assertFalse(any(row[0] == 'realtime' for row in self.sim.calls))

    def test_combat_uses_one_fresh_existing_move_command(self):
        self.sim.combat = True
        self.input.press('w', now=0.)
        self.input.press('w', now=.1)
        self.input.update(100.)
        commands = [row[1] for row in self.sim.calls if row[0] == 'command']
        self.assertEqual(commands, [MoveCommand(1, 0, -1)])
        self.assertFalse(any(row[0] in ('move', 'realtime') for row in self.sim.calls))
        self.input.release('w')
        self.input.press('w', now=100.)
        self.assertEqual(self.sim.calls[-1], ('command', MoveCommand(1, 0, -1)))

    def test_command_time_and_deferred_hub_do_not_double_charge(self):
        self.assertEqual(self.input.press('\r', now=1.), 'actions')
        self.assertEqual(self.input.press('\t', now=1.), 'console')
        self.input.press('.', now=20.)
        self.input.update(20.)
        self.input.release('.')
        self.input.press('p', now=21.)
        commands = [row[1] for row in self.sim.calls if row[0] == 'command']
        self.assertEqual(commands, [WaitCommand(1, 10), PickupCommand(1)])
        self.assertFalse(any(row[0] == 'realtime' for row in self.sim.calls))

    def test_opposite_keys_cancel_and_close_stops_updates(self):
        for key in ('w','s','d'):
            self.input.press(key, now=0.)
        self.input.update(.1)
        self.assertEqual(self.sim.calls[-1][2:4], (1, 0))
        self.input.close()
        before = list(self.sim.calls)
        self.input.update(50.)
        self.assertEqual(self.sim.calls, before)
        self.assertEqual(self.sim.calls[-1], ('enabled', False))

    def test_pointer_exact_camera_projection_is_read_only_and_bounded(self):
        camera = WorldCamera(WorldFoot(-2.3, 7.1, 0), 640, 480, 32)
        foot = WorldFoot(-1.2, 8.4, 0)
        self.assertEqual(project_pointer(camera, *camera.to_screen(foot)), WorldPos(-2, 8, 0))
        for x,y in ((-1,0),(640,0),(0,480),(float('nan'),0)):
            self.assertIsNone(project_pointer(camera,x,y))
        self.assertEqual(self.sim.calls, [('enabled', True)])

    def test_real_engine_trunk_collision_and_real_sight_survive_gpu_capture(self):
        from tools.reference_scene_fixtures import build_fixture
        from worldseed.config import DATA_DIR
        from worldseed.content.registry import ContentRegistry
        from worldseed.entities.components import Position
        from worldseed.presentation.live_gpu_scene import capture_live_scene, player_foot
        from worldseed.sim.engine import Simulation
        registry = ContentRegistry.load(DATA_DIR)
        with tempfile.TemporaryDirectory() as directory:
            fixture = build_fixture('forest', registry, Path(directory), width=640, height=480, zoom=36)
            try:
                sim = fixture.sim
                selected = None
                for y in range(251,262):
                    for x in range(251,262):
                        target = WorldPos(x,y,0)
                        feature = sim.resources.prepared_feature_at(target,sim.clock.minute)
                        if feature is None or feature.feature_id not in ('core:oak_tree','core:pine_tree'):
                            continue
                        for dx,dy,key in ((1,0,'d'),(-1,0,'a'),(0,1,'s'),(0,-1,'w')):
                            origin = target.moved(-dx,-dy)
                            if sim.world.is_passable(origin) and not sim.resources.blocks_movement(origin):
                                selected = target,origin,dx,dy,key,feature
                                break
                        if selected: break
                    if selected: break
                self.assertIsNotNone(selected)
                target,origin,dx,dy,key,feature = selected
                sim.entities.get(sim.player_id, Position).value = origin
                sim.state.player_fx = .95 if dx > 0 else .05 if dx < 0 else .5
                sim.state.player_fy = .95 if dy > 0 else .05 if dy < 0 else .5
                # Controlled prepared terrain, real production discovery/LOS.
                sim._discover = MethodType(Simulation._discover, sim)
                sim._discover(origin)
                control = GpuGameplayInput(sim,now=0.)
                try:
                    control.press(key,now=0.)
                    control.update(.1)
                    self.assertEqual(sim.player_pos,origin)
                    self.assertTrue(any('blocks your path' in row.message for row in sim.log))
                    logged = len(sim.log)
                    control.update(.2)
                    self.assertEqual(len(sim.log),logged)
                    before = fixture.authority_fingerprint()
                    camera = WorldCamera(player_foot(sim),640,480,36)
                    snapshot = capture_live_scene(sim,camera)
                    self.assertIn((target.x,target.y,target.z), snapshot.current_cells)
                    self.assertIn(((target.x,target.y,target.z),feature), snapshot.resources)
                    self.assertEqual(snapshot.viewer,player_foot(sim))
                    self.assertEqual(fixture.authority_fingerprint(),before)
                    self.assertEqual(sim.resources.prepared_feature_at(target,sim.clock.minute),feature)
                finally:
                    control.close()
            finally:
                fixture.close()


if __name__ == '__main__': unittest.main()
