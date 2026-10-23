"""GPU time/work feedback stays detached from simulation and visibility authority."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
import os
import unittest
from unittest.mock import patch

from worldseed.presentation.action_resource_fade import (
    capture_resource_fade, resource_fade_commands, merge_resource_fade,
)
from worldseed.presentation.gl_worldspace import SpriteCommand
from worldseed.presentation.worldspace import WorldCamera, WorldFoot
from worldseed.sim.commands import CraftCommand, GatherCommand


def viewport(x=10, y=20, width=200, height=200):
    return SimpleNamespace(x=x, y=y, left=x, top=y, right=x+width,
                           bottom=y+height, topleft=(x, y))


class DetachedHarvestFadeTests(unittest.TestCase):
    def setUp(self):
        self.camera = WorldCamera(WorldFoot(.5, .5), 200, 200, 40)
        self.viewport = viewport()
        self.cell = (1, 0, 0)
        self.snapshot = SimpleNamespace(interior=False, viewer=WorldFoot(.5, .5),
            camera=self.camera, current_cells=frozenset((self.cell, (0,0,0))),
            resources=((self.cell, SimpleNamespace(feature_id='core:oak_tree')),))
        # x=1..2, y=0..1 in the pre-action screen/viewport coordinates.
        self.command = SpriteCommand('feature:0:1:0:core:oak_tree:mature:base',
            'oak', 1, b'\xff'*4, 1, 1, (130.,100.,170.,140.),
            ((130.,100.,170.,140.),))

    def test_only_committed_target_art_fades_and_source_is_immutable(self):
        unrelated = replace(self.command, visual_id='actor:hidden-npc')
        before = deepcopy(self.snapshot)
        fade = capture_resource_fade(GatherCommand(1,1,0), self.snapshot,
                                     (self.command, unrelated), self.viewport)
        self.assertEqual(fade.commands, (self.command,))
        output = resource_fade_commands(fade, self.snapshot, self.viewport, .5, ())
        self.assertEqual(len(output), 1)
        self.assertEqual(output[0].opacity, .5)
        self.assertEqual(output[0].clip_rects, self.command.clip_rects)
        self.assertEqual(self.command.opacity, 1.)
        self.assertEqual(before, self.snapshot)
        self.assertEqual(resource_fade_commands(fade,self.snapshot,self.viewport,1.,()), ())
        self.assertEqual(resource_fade_commands(fade,self.snapshot,self.viewport,.5,(self.command,)), ())

    def test_resize_zoom_reprojects_cached_pixels_and_never_expands_sight(self):
        fade = capture_resource_fade(GatherCommand(1,1,0), self.snapshot,
                                     (self.command,), self.viewport)
        camera = replace(self.camera, width_px=400, height_px=300, tile_px=56)
        updated = SimpleNamespace(**{**vars(self.snapshot), 'camera':camera})
        changed = viewport(30,40,400,300)
        output = resource_fade_commands(fade, updated, changed, .25, ())
        self.assertEqual(len(output), 1)
        a,b = camera.to_screen(WorldFoot(1,0))
        c,d = camera.to_screen(WorldFoot(2,1))
        self.assertEqual(output[0].bounds, (a+30,b+40,c+30,d+40))
        updated.current_cells = frozenset(((0,0,0),))
        self.assertEqual(resource_fade_commands(fade,updated,changed,.25,()), ())
        self.assertIsNone(capture_resource_fade(CraftCommand(1,'core:axe'),self.snapshot,
                                               (self.command,),self.viewport))

    def test_fading_art_keeps_depth_neighbors_and_player_last(self):
        npc = replace(self.command, visual_id='actor:neighbor')
        player = replace(self.command, visual_id='actor:gpu-viewer')
        fade = capture_resource_fade(GatherCommand(1,1,0), self.snapshot,
                                     (self.command,npc,player),self.viewport)
        ghosts = resource_fade_commands(fade,self.snapshot,self.viewport,.5,(npc,player))
        output = merge_resource_fade((npc,player),ghosts,fade)
        self.assertEqual(output,(*ghosts,npc,player))

    def test_wide_old_art_loses_pixels_when_neighbor_leaves_current_sight(self):
        wide = replace(self.command,bounds=(90.,100.,170.,140.),
                       clip_rects=((90.,100.,170.,140.),))
        fade = capture_resource_fade(GatherCommand(1,1,0),self.snapshot,(wide,),self.viewport)
        current = SimpleNamespace(**{**vars(self.snapshot),'current_cells':frozenset((self.cell,))})
        output = resource_fade_commands(fade,current,self.viewport,.4,())
        self.assertEqual(output[0].clip_rects,((130.,100.,170.,140.),))


class GPUTimeControlsTests(unittest.TestCase):
    def setUp(self):
        from worldseed.ui.pygame_terminal import PygameTerminal
        if not PygameTerminal.available():
            self.skipTest('optional pygame unavailable')
        environment = patch.dict(os.environ, {'SDL_VIDEODRIVER':'dummy','SDL_AUDIODRIVER':'dummy'})
        environment.start(); self.addCleanup(environment.stop)
        self.term = PygameTerminal(960,720); self.term.enter()
        self.addCleanup(self.term.restore)
        self.term._input_mode = 'world'

    def test_clickable_states_match_driver_and_fit_all_sidebar_sizes(self):
        from worldseed.ui import gpu_hud
        from worldseed.entities.components import Vitals
        term = self.term
        driver = SimpleNamespace(paused=False, effective_paused=False, speed=3)
        term.set_time_controls(driver)
        sim = SimpleNamespace(state=SimpleNamespace(player_name='Wanderer',player_hunting_stance='normal'),
            clock=SimpleNamespace(label=lambda:'Spring 1, 08:25'), player_pos=SimpleNamespace(x=1,y=2,z=0))
        before = deepcopy(vars(driver))
        for width,height in ((300,630),(180,430),(146,380)):
            term._pointer_targets.clear(); term._hud_tooltips.clear()
            rect = term.pg.Rect(960-width,55,width,height)
            with patch.object(gpu_hud,'_icon'):
                gpu_hud.draw_hud(term,rect,sim,Vitals())
            targets = [(box,token) for box,token in term._pointer_targets if token.startswith('UI_TIME:')]
            self.assertEqual([token for _,token in targets],['UI_TIME:pause','UI_TIME:1','UI_TIME:2','UI_TIME:3'])
            self.assertTrue(all(rect.contains(box) for box,_ in targets))
            self.assertTrue(all(term._hit_token(box.center)==token for box,token in targets))
        self.assertEqual(vars(driver),before)
        driver.paused=True; driver.effective_paused=True
        self.assertEqual(term.read_time_controls(),{'paused':True,'held':True,'speed':3})
        term._pointer_targets.clear(); term._input_mode='busy'
        gpu_hud.draw_time_controls(term,term.pg.Rect(600,80,180,39))
        self.assertFalse(term._pointer_targets)


if __name__ == '__main__':
    unittest.main()
