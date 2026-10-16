"""GPU Action Hub browsing and fresh authoritative command authorization."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import tempfile
from types import MethodType, SimpleNamespace
import unittest
from unittest.mock import patch

from tools.reference_scene_fixtures import build_fixture
from worldseed.config import CHUNK_SIZE, DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos, split_world
from worldseed.entities.components import Inventory, Position
from worldseed.presentation.live_gpu_scene import capture_live_scene, player_foot
from worldseed.presentation.worldspace import WorldCamera
from worldseed.sim.commands import GatherCommand, MoveCommand, PickupCommand, WaitCommand
from worldseed.sim.engine import Simulation
from worldseed.systems.state import GroundPile, pos_key
from worldseed.ui.gpu_gameplay_actions import (
    MAX_GPU_ACTION_ROWS, action_rows, dispatch_action,
)


class GpuGameplayActionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.fixture = build_fixture('forest',self.registry,Path(directory.name),
                                     width=640,height=480,zoom=36)
        self.addCleanup(self.fixture.close)
        self.sim = self.fixture.sim
        selected = None
        for y in range(251,262):
            for x in range(251,262):
                target = WorldPos(x,y,0)
                feature = self.sim.resources.prepared_feature_at(target,self.sim.clock.minute)
                if feature is None or feature.feature_id not in ('core:oak_tree','core:pine_tree'):
                    continue
                for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
                    origin = target.moved(-dx,-dy)
                    if self.sim.world.is_passable(origin) and not self.sim.resources.blocks_movement(origin):
                        selected = target,origin,feature
                        break
                if selected: break
            if selected: break
        self.assertIsNotNone(selected)
        self.target,self.origin,self.feature = selected
        self.cell = (self.target.x,self.target.y,self.target.z)
        self.sim.entities.get(self.sim.player_id,Position).value = self.origin
        # Real production LOS/discovery over synthetic prepared QA terrain.
        self.sim._discover = MethodType(Simulation._discover,self.sim)
        self.sim._discover(self.origin)
        self.snapshot = self.capture()
        self.row = next(row for row in action_rows(self.snapshot,self.registry,self.target)
                        if row.kind == 'gather')

    def capture(self):
        return capture_live_scene(self.sim,WorldCamera(player_foot(self.sim),640,480,36))

    def assert_rejected_read_only(self,row=None,snapshot=None):
        before = self.fixture.authority_fingerprint()
        with patch.object(self.sim,'execute') as execute, patch.object(
                self.sim.world,'tile_at',side_effect=AssertionError('hidden or unprepared tile load')):
            result = dispatch_action(self.sim,row or self.row,snapshot or self.snapshot)
        self.assertFalse(result.dispatched)
        execute.assert_not_called()
        self.assertEqual(before,self.fixture.authority_fingerprint())

    def test_action_browsing_is_immutable_bounded_and_observational(self):
        before = self.fixture.authority_fingerprint()
        with patch.object(self.sim,'execute') as execute:
            for selected in (None,self.target,(100000,100000,0),self.origin):
                rows = action_rows(self.snapshot,self.registry,selected)
                self.assertIsInstance(rows,tuple)
                self.assertLessEqual(len(rows),MAX_GPU_ACTION_ROWS)
            execute.assert_not_called()
        self.assertEqual(before,self.fixture.authority_fingerprint())
        with self.assertRaises(FrozenInstanceError):
            self.row.label = 'changed'
        self.assertEqual(self.row.feature,self.feature)
        self.assertEqual(self.row.target,self.cell)

    def test_explicit_step_uses_engine_collision_then_harvest_opens_same_cell(self):
        rows = action_rows(self.snapshot,self.registry,self.target)
        move = next(row for row in rows if row.kind == 'move')
        delta = (self.target.x-self.origin.x,self.target.y-self.origin.y)
        with patch.object(self.sim,'execute',wraps=self.sim.execute) as execute:
            result = dispatch_action(self.sim,move,self.snapshot)
            execute.assert_called_once_with(MoveCommand(self.sim.player_id,*delta))
        self.assertTrue(result.dispatched)
        self.assertIn('blocks your path',result.message)
        self.assertEqual(self.sim.player_pos,self.origin)
        # QA equipment is set outside the controller; no gameplay starter kit.
        inventory = self.sim.entities.get(self.sim.player_id,Inventory)
        inventory.add('core:stone_axe',1)
        wood = inventory.count('core:wood')
        terrain = self.sim.world.prepared_tile_at(self.target).terrain_id
        snapshot = self.capture()
        gather = next(row for row in action_rows(snapshot,self.registry,self.target) if row.kind == 'gather')
        minute = self.sim.clock.minute
        with patch.object(self.sim,'execute',wraps=self.sim.execute) as execute:
            result = dispatch_action(self.sim,gather,snapshot)
            execute.assert_called_once_with(GatherCommand(self.sim.player_id,*delta))
        self.assertTrue(result.dispatched)
        self.assertIn('You harvest',result.message)
        self.assertGreater(inventory.count('core:wood'),wood)
        self.assertEqual(self.sim.state.resource_depletion[pos_key(*self.cell)],minute)
        self.assertEqual(self.sim.world.prepared_tile_at(self.target).terrain_id,terrain)
        feature = self.sim.resources.prepared_feature_at(self.target,self.sim.clock.minute)
        self.assertEqual((feature.feature_id,feature.stage),(self.feature.feature_id,'stump'))
        self.assertFalse(self.sim.resources.blocks_movement(self.target))
        self.assert_rejected_read_only(gather,snapshot)
        snapshot = self.capture()
        rows = action_rows(snapshot,self.registry,self.target)
        self.assertFalse(any(row.kind == 'gather' for row in rows))
        move = next(row for row in rows if row.kind == 'move')
        self.assertTrue(dispatch_action(self.sim,move,snapshot).dispatched)
        self.assertEqual(self.sim.player_pos,self.target)

    def test_missing_tool_is_rejected_by_existing_command_without_inventory_grant(self):
        before = dict(self.sim.entities.get(self.sim.player_id,Inventory).items)
        result = dispatch_action(self.sim,self.row,self.snapshot)
        self.assertTrue(result.dispatched)
        self.assertIn('need a suitable',result.message)
        self.assertEqual(dict(self.sim.entities.get(self.sim.player_id,Inventory).items),before)
        self.assertEqual(self.sim.resources.prepared_feature_at(self.target,self.sim.clock.minute),self.feature)

    def test_current_sight_cannot_be_replaced_by_discovery_memory(self):
        self.sim.visible_tiles_set.discard(pos_key(*self.cell))
        self.assertIn(pos_key(*self.cell),self.sim.discovered_tiles_set)
        self.assert_rejected_read_only()

    def test_stale_depletion_stage_and_feature_identity_are_rejected(self):
        self.sim.state.resource_depletion[pos_key(*self.cell)] = self.sim.clock.minute
        self.assert_rejected_read_only()
        self.sim.state.resource_depletion.pop(pos_key(*self.cell))
        key,lx,ly = split_world(self.target)
        cache_key = (key.x,key.y,self.snapshot.season)
        values = list(self.sim.resources._feature_chunk_cache[cache_key])
        values[ly*CHUNK_SIZE+lx] = 'core:pine_tree' if self.feature.feature_id == 'core:oak_tree' else 'core:oak_tree'
        self.sim.resources._cache_feature_chunk(cache_key,tuple(values))
        self.assert_rejected_read_only()

    def test_private_roof_shell_and_plan_room_are_rechecked(self):
        physical = self.sim.settlement_physicalization
        cases = (
            (self.sim.building,'roof_at',SimpleNamespace(condition=100)),
            (physical,'shell_at',object()),
            (physical,'cell_at',SimpleNamespace(room_id='private',roof_piece_id='')),
        )
        for owner,name,value in cases:
            original = getattr(owner,name)
            with self.subTest(gate=name), patch.object(owner,name,
                    side_effect=lambda pos,original=original,value=value: value if pos == self.target else original(pos)):
                self.assert_rejected_read_only()

    def test_changed_terrain_and_player_elevation_are_rejected(self):
        self.sim.world.set_terrain(self.target,'core:sand')
        self.assert_rejected_read_only()
        self.sim.entities.get(self.sim.player_id,Position).value = self.origin.moved(0,0,-1)
        self.assert_rejected_read_only()

    def test_unprepared_cell_and_changed_player_position_are_rejected_without_loading(self):
        key,_,_ = split_world(self.target)
        self.sim.world.cache._chunks.pop(key)
        self.assert_rejected_read_only()
        self.sim.entities.get(self.sim.player_id,Position).value = self.origin.moved(2,0)
        self.assert_rejected_read_only()

    def test_unknown_distant_other_elevation_and_forged_rows_cannot_dispatch(self):
        for cell in ((self.origin.x+20,self.origin.y,0),(self.target.x,self.target.y,-1)):
            rows = action_rows(self.snapshot,self.registry,cell)
            self.assertFalse(any(row.kind in ('gather','move') for row in rows))
            self.assert_rejected_read_only(replace(self.row,target=cell))
        self.assert_rejected_read_only(replace(self.row,kind='enter_private_interior'))
        self.assert_rejected_read_only(replace(self.row,uid='forged-resource'))

    def test_new_interior_presence_rejects_old_outdoor_row(self):
        with patch.object(self.sim.interiors,'player_presence',return_value=object()):
            self.assert_rejected_read_only()
        self.assertEqual(action_rows(replace(self.snapshot,interior=True),self.registry,self.target),())

    def test_pickup_and_wait_use_existing_commands_and_do_not_consume_click_selection(self):
        self.sim.state.ground_piles[pos_key(*self.cell)] = GroundPile(*self.cell,{'core:stone':2})
        before = self.fixture.authority_fingerprint()
        rows = action_rows(self.snapshot,self.registry,self.target)
        self.assertEqual(before,self.fixture.authority_fingerprint())
        pickup = next(row for row in rows if row.kind == 'pickup')
        delta = (self.target.x-self.origin.x,self.target.y-self.origin.y)
        with patch.object(self.sim,'execute',wraps=self.sim.execute) as execute:
            self.assertTrue(dispatch_action(self.sim,pickup,self.snapshot).dispatched)
            execute.assert_called_once_with(PickupCommand(self.sim.player_id,*delta))
        self.assertNotIn(pos_key(*self.cell),self.sim.state.ground_piles)
        snapshot = self.capture()
        wait = next(row for row in action_rows(snapshot,self.registry) if row.kind == 'wait')
        with patch.object(self.sim,'execute',wraps=self.sim.execute) as execute:
            self.assertTrue(dispatch_action(self.sim,wait,snapshot).dispatched)
            execute.assert_called_once_with(WaitCommand(self.sim.player_id,10))


if __name__ == '__main__': unittest.main()
