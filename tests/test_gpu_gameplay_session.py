"""GPU primary navigation over real prepared gameplay state and command owners."""
from __future__ import annotations

from pathlib import Path
import tempfile
from types import MethodType
import unittest
from unittest.mock import patch

from tools.reference_scene_fixtures import build_fixture
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory, Position
from worldseed.presentation.live_gpu_scene import capture_live_scene, player_foot
from worldseed.presentation.worldspace import WorldCamera
from worldseed.sim.commands import GatherCommand, WaitCommand
from worldseed.sim.engine import Simulation
from worldseed.systems.state import pos_key
from worldseed.ui.gpu_gameplay_session import GpuGameplaySession
from worldseed.ui.session import NavigationStack


class GpuGameplaySessionTests(unittest.TestCase):
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
                        selected = target,origin
                        break
                if selected: break
            if selected: break
        self.assertIsNotNone(selected)
        self.target,self.origin = selected
        self.cell = (self.target.x,self.target.y,self.target.z)
        self.sim.entities.get(self.sim.player_id,Position).value = self.origin
        self.sim._discover = MethodType(Simulation._discover,self.sim)
        self.sim._discover(self.origin)
        self.snapshot = capture_live_scene(self.sim,WorldCamera(player_foot(self.sim),640,480,36))
        self.session = GpuGameplaySession(self.sim,self.registry,now=0.)
        self.addCleanup(self.session.close)

    def press(self,key,now=0.):
        return self.session.press(key,self.snapshot,now=now)

    def test_hud_console_inventory_health_inspection_and_actions_are_observational(self):
        before = self.fixture.authority_fingerprint()
        with patch.object(self.sim,'execute',side_effect=AssertionError('browsing issued command')):
            hud = self.session.observe(self.snapshot)
            self.assertTrue(any('HP ' in line for line in hud.hud))
            self.assertEqual(hud.panel_title,'')
            self.press('\t')
            self.assertEqual({row.key for row in self.session.observe(self.snapshot).rows},
                             {'character','local','system'})
            self.session.activate('character',self.snapshot,now=0.)
            for key in ('inventory','health','character_sheet'):
                self.session.activate(key,self.snapshot,now=0.)
                model = self.session.observe(self.snapshot)
                self.assertTrue(model.rows or model.details)
                self.press('ESC')
            self.press('ESC')
            self.session.activate('local',self.snapshot,now=0.)
            self.session.activate('inspect',self.snapshot,now=0.)
            self.assertTrue(any('Cell ' in line for line in self.session.observe(self.snapshot).details))
            self.press('ESC');self.press('ESC')
            self.session.activate('system',self.snapshot,now=0.)
            self.session.activate('help',self.snapshot,now=0.)
            self.assertTrue(any('Enter' in line for line in self.session.observe(self.snapshot).details))
            self.press('ESC');self.press('ESC');self.press('ESC')
            self.assertFalse(self.session.modal)
            self.session.select_cell(self.cell,self.snapshot)
            self.press('\r');self.press('\r');self.press('\r')
            self.assertEqual(self.session.nav.current.route_id,'harvest')
            self.assertTrue(self.session.observe(self.snapshot).rows)
        self.assertEqual(self.fixture.authority_fingerprint(),before)

    def test_nested_escape_restores_inventory_selection_scroll_and_parent_routes(self):
        inventory = self.sim.entities.get(self.sim.player_id,Inventory)
        for iid in sorted(self.registry.items)[:24]: inventory.add(iid,1)
        before = self.fixture.authority_fingerprint()
        self.session.page_size = 3
        self.press('\t');self.press('\r')
        self.press('DOWN');self.press('DOWN');self.press('\r')
        self.assertIsInstance(self.session.nav,NavigationStack)
        self.assertEqual(self.session.nav.current.route_id,'inventory')
        for _ in range(8): self.press('DOWN')
        self.session.observe(self.snapshot)
        selected,scroll = self.session.nav.current.selected,self.session.nav.current.scroll
        self.assertEqual(selected,8)
        self.assertGreater(scroll,0)
        self.press('\r')
        self.assertEqual(self.session.nav.current.route_id,'item')
        self.assertEqual(self.session.nav.depth,4)
        self.assertTrue(self.session.observe(self.snapshot).details)
        self.press('ESC')
        self.session.observe(self.snapshot)
        self.assertEqual(self.session.nav.current.route_id,'inventory')
        self.assertEqual((self.session.nav.current.selected,self.session.nav.current.scroll),(selected,scroll))
        self.press('ESC')
        self.assertEqual((self.session.nav.current.route_id,self.session.nav.current.selected),('character',2))
        self.press('ESC')
        self.assertEqual(self.session.nav.current.route_id,'console')
        self.press('ESC')
        self.assertFalse(self.session.modal)
        self.assertEqual(self.fixture.authority_fingerprint(),before)

    def test_wasd_only_moves_world_and_never_selects_menu_rows(self):
        self.press('\r')
        before = self.fixture.authority_fingerprint()
        state = self.session.nav.snapshot()
        for key in 'wasdWASD': self.press(key)
        self.assertEqual(self.session.nav.snapshot(),state)
        self.assertEqual(self.session.input._held,{})
        self.assertEqual(self.fixture.authority_fingerprint(),before)
        self.press('DOWN')
        self.assertEqual(self.session.nav.current.selected,1)
        self.press('ESC')
        fx = self.sim.state.player_fx
        self.press('d')
        self.session.update(.05)
        self.assertGreater(self.sim.state.player_fx,fx)
        self.session.release('d')
        fx = self.sim.state.player_fx
        self.session.update(.1)
        self.assertEqual(self.sim.state.player_fx,fx)

    def test_opening_ui_clears_held_motion_and_reading_never_catches_up_time(self):
        self.press('d')
        self.session.update(.1)
        self.assertTrue(self.session.input._held)
        self.press('\r',now=.1)
        self.assertFalse(self.session.input.focused)
        self.assertEqual(self.session.input._held,{})
        before = self.fixture.authority_fingerprint()
        for now in (100.,900.,3600.):
            self.assertFalse(self.session.update(now))
            self.session.observe(self.snapshot)
        self.assertEqual(self.fixture.authority_fingerprint(),before)
        minute = self.sim.clock.minute
        self.press('ESC',now=3600.)
        self.session.update(3600.1)
        self.assertEqual(self.sim.clock.minute,minute)
        self.assertEqual(self.fixture.authority_fingerprint(),before)
        self.session.update(3601.6)
        self.assertEqual(self.sim.clock.minute,minute+1)

    def test_focus_loss_clears_motion_and_keeps_modal_pause_until_dismissed(self):
        self.press('w')
        self.session.set_focus(False,now=.1)
        self.assertFalse(self.session.input.focused)
        self.assertEqual(self.session.input._held,{})
        before = self.fixture.authority_fingerprint()
        self.session.update(100.)
        self.press('\r',now=100.)
        self.assertFalse(self.session.modal)
        self.session.set_focus(True,now=100.)
        self.press('\t',now=100.)
        self.session.set_focus(False,now=101.)
        self.session.set_focus(True,now=900.)
        self.assertFalse(self.session.input.focused)
        self.press('ESC',now=900.)
        self.assertTrue(self.session.input.focused)
        self.session.update(900.1)
        self.assertEqual(self.fixture.authority_fingerprint(),before)

    def test_queued_pointer_activation_after_focus_loss_cannot_dispatch(self):
        self.press('\r')
        self.session.set_focus(False,now=.1)
        before = self.fixture.authority_fingerprint()
        with patch.object(self.sim,'execute') as execute:
            self.assertFalse(self.session.activate('wait',self.snapshot,now=.2))
            execute.assert_not_called()
        self.assertEqual(self.fixture.authority_fingerprint(),before)

    def test_visible_selection_never_commands_and_unknown_selection_is_rejected(self):
        before = self.fixture.authority_fingerprint()
        with patch.object(self.sim,'execute') as execute:
            self.assertFalse(self.session.select_cell((100000,100000,0),self.snapshot))
            self.assertTrue(self.session.select_cell(self.cell,self.snapshot))
            self.assertEqual(self.session.selected_cell,self.cell)
            self.session.observe(self.snapshot)
            execute.assert_not_called()
        self.assertEqual(self.fixture.authority_fingerprint(),before)
        self.sim.visible_tiles_set.discard(pos_key(*self.cell))
        fresh = capture_live_scene(self.sim,self.snapshot.camera)
        self.session.observe(fresh)
        self.assertIsNone(self.session.selected_cell)

    def test_enter_confirmed_harvest_routes_one_existing_command(self):
        self.sim.entities.get(self.sim.player_id,Inventory).add('core:stone_axe',1)
        self.session.select_cell(self.cell,self.snapshot)
        before = self.fixture.authority_fingerprint()
        self.press('\r');self.press('\r');self.press('\r')
        self.assertEqual(self.fixture.authority_fingerprint(),before)
        with patch.object(self.sim,'execute',wraps=self.sim.execute) as execute:
            self.press('\r')
            execute.assert_called_once_with(GatherCommand(self.sim.player_id,
                self.target.x-self.origin.x,self.target.y-self.origin.y))
        self.assertFalse(self.session.modal)
        self.assertIn('You harvest',self.session.message)
        self.assertEqual(self.sim.resources.prepared_feature_at(self.target,self.sim.clock.minute).stage,'stump')

    def test_explicit_pointer_harvest_rechecks_stale_sight_and_keeps_route_on_rejection(self):
        self.session.select_cell(self.cell,self.snapshot)
        self.press('\r')
        self.session.activate('interact',self.snapshot,now=0.)
        self.session.activate('g',self.snapshot,now=0.)
        key = self.session.rows(self.snapshot)[0].key
        self.sim.visible_tiles_set.discard(pos_key(*self.cell))
        before = self.fixture.authority_fingerprint()
        with patch.object(self.sim,'execute') as execute:
            self.assertTrue(self.session.activate(key,self.snapshot,now=1.))
            execute.assert_not_called()
        self.assertEqual(self.session.nav.current.route_id,'harvest')
        self.assertIn('no longer available',self.session.message)
        self.assertEqual(self.fixture.authority_fingerprint(),before)

    def test_action_hub_wait_is_one_canonical_command_and_dismisses(self):
        minute = self.sim.clock.minute
        self.press('\r');self.press('DOWN')
        with patch.object(self.sim,'execute',wraps=self.sim.execute) as execute:
            self.press('\r',now=10.)
            execute.assert_called_once_with(WaitCommand(self.sim.player_id,10))
        self.assertFalse(self.session.modal)
        self.assertEqual(self.sim.clock.minute,minute+10)
        self.assertIn('You wait',self.session.message)
        self.session.update(10.1)
        self.assertEqual(self.sim.clock.minute,minute+10)

    def test_large_owned_inventory_pages_without_truncating_records(self):
        inventory = self.sim.entities.get(self.sim.player_id,Inventory)
        inventory.items = {f'qa:item:{index:04}':1 for index in range(2100)}
        before = self.fixture.authority_fingerprint()
        self.press('i')
        found = set()
        while True:
            model = self.session.observe(self.snapshot)
            self.assertLessEqual(len(model.rows),22)
            found.update(row.key for row in model.rows if row.key.startswith('item:'))
            if not any(row.key == 'next-page' for row in model.rows):
                break
            self.assertTrue(self.session.activate('next-page',self.snapshot,now=0.))
        self.assertEqual(found,{'item:'+iid for iid in inventory.items})
        self.assertEqual(self.fixture.authority_fingerprint(),before)


if __name__ == '__main__': unittest.main()
