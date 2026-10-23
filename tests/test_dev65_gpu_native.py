"""Optional real GPU-window action-overlay and retained-panel acceptance."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from tests import test_gpu_main_game as native
from worldseed.sim.commands import CraftCommand, GatherCommand


class GPUDev65NativeTests(unittest.TestCase):
    setUpClass = classmethod(native.GPUMainGameTests.setUpClass.__func__)
    setUp = native.GPUMainGameTests.setUp

    def present(self):
        native.GPUMainGameTests.present(self)

    def test_player_counter_retains_panel_and_never_changes_authority(self):
        self.present()
        term = self.term; pg = term.pg
        before = self.fixture.authority_fingerprint()
        # Exercise the actual GL departing-art branch using only the detached
        # captured view; no resource/terrain/simulation state is edited.
        cell, feature = next((cell,feature) for cell,feature in term._snapshot.resources
            if any(row.visual_id.startswith(f'feature:{cell[2]}:{cell[0]}:{cell[1]}:{feature.feature_id}:')
                   for row in term._world_commands))
        px,py,_ = term._snapshot.viewer.cell
        term._begin_action_progress(GatherCommand(1,cell[0]-px,cell[1]-py),20)
        self.assertIsNotNone(term._action_resource_fade)
        original_commands = term._world_commands
        fading_ids = {row.visual_id for row in term._action_resource_fade.commands}
        term._world_commands = tuple(row for row in original_commands if row.visual_id not in fading_ids)
        term._action_progress_fraction = .5
        with patch.object(term._world_renderer,'draw',wraps=term._world_renderer.draw) as draw:
            term._composite()
        rendered = draw.call_args.args[0]
        self.assertTrue(any(row.visual_id.startswith('action-fade:') for row in rendered))
        self.assertEqual(rendered[-1].visual_id,'actor:gpu-viewer')
        term._world_commands = original_commands
        term._end_action_progress()
        box = term._action_progress_rect()
        self.assertTrue(term._gpu_viewport.contains(box))
        x,y = term._snapshot.camera.to_screen(term._snapshot.viewer)
        self.assertLess(box.bottom, y+term._gpu_viewport.y)
        term._current_presentation='crafting_unified'
        term._floating_panels['crafting']={'x':640,'y':90,'w':220,'h':150}
        panel=pg.Rect(640,90,220,150)
        pg.draw.rect(term.screen,(75,65,42),panel)
        ticks=[]; counters=[]
        draw=term._draw_action_progress
        def record(command,label,elapsed,total,fraction):
            counters.append((elapsed,total,fraction,term._action_progress_rect()))
            return draw(command,label,elapsed,total,fraction)
        with patch('worldseed.ui.action_progress.visual_duration',return_value=.18), \
                patch.object(term,'_draw_action_progress',side_effect=record):
            term.present_timed_action(CraftCommand(1,'core:axe'),20,ticks.append,self.present)
        self.assertEqual(sum(ticks),20)
        self.assertTrue(counters)
        self.assertEqual(counters[-1][:3],(20,20,1.))
        self.assertEqual(tuple(term.screen.get_at((670,110)))[:3],(75,65,42))
        self.assertEqual(self.fixture.authority_fingerprint(),before)
        self.assertIsNone(term._action_resource_fade)
        # Projection follows a newly captured resized window, not old pixels.
        term._resize(640,480); self.present()
        self.assertTrue(term._gpu_viewport.contains(term._action_progress_rect()))


if __name__ == '__main__':
    unittest.main()
