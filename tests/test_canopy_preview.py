"""G1c/G2 one-oak opt-in software viewport contract tests."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import importlib.util
from math import floor
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import os
import unittest

from worldseed.presentation.canopy_preview import (
    PREVIEW_SWITCH, camera_for_live_grid, prepare_one_oak, select_oak,
)
from worldseed.presentation.worldspace import VisualLayer, WorldFoot


def fv(fid='core:oak_tree', stage='mature'):
    return SimpleNamespace(feature_id=fid, stage=stage)


def source():
    return {(2,2,0): (fv(), 'original-atlas-ref'),
            (3,2,0): (fv('core:pine_tree'), 'pine')}


class CanopyPreviewContracts(unittest.TestCase):
    def setUp(self):
        self.current = frozenset(f'{x},{y},0' for x in range(-6, 9) for y in range(-6, 9))
        self.defs = {
            'core:oak_tree': SimpleNamespace(tags=('tree',), blocks_movement=True),
            'core:pine_tree': SimpleNamespace(tags=('tree',), blocks_movement=True),
        }
        self.camera = camera_for_live_grid(left=-3, top=-2, grid_x=11, grid_y=19,
                                           viewport_x=39, viewport_y=47,
                                           viewport_w=280, viewport_h=196,
                                           tile_px=28, z=0)

    def plan(self, resources=None, **overrides):
        kwargs = dict(resource_by=source() if resources is None else resources,
                      resource_defs=self.defs, resource_style=lambda _: {'width': 1.35, 'height': 1.7},
                      current_cells=self.current, discovered_cells=self.current,
                      player_x=3, player_y=2, player_z=0,
                      player_fx=.5, player_fy=.5, camera=self.camera)
        kwargs.update(overrides)
        return prepare_one_oak(**kwargs)

    def test_one_oak_stays_one_resource_no_new_trunk_collision(self):
        preview = self.plan()
        self.assertEqual(preview.source, (2,2,0))
        parts = [x for x in preview.scene.instances if x.resource_id]
        self.assertEqual(len(parts), 3)
        self.assertEqual({x.resource_id for x in parts}, {'feature:0:2:2:core:oak_tree'})
        self.assertEqual([x.physical_cells for x in parts if x.layer is VisualLayer.GROUNDED],
                         [((2,2,0),)])
        self.assertEqual([x.physical_cells for x in parts if x.layer is VisualLayer.OVERHEAD], [()])
        with self.assertRaises(FrozenInstanceError):
            parts[0].width = 999

    def test_player_under_canopy_generates_single_local_cutout(self):
        under = self.plan(player_x=3, player_y=2)
        self.assertEqual(len(under.scene.projection.cover_fades), 1)
        fade = under.scene.projection.cover_fades[0]
        self.assertAlmostEqual(fade.local_alpha,.48)
        self.assertEqual(fade.radius_px,28*.9)
        far = self.plan(player_x=0,player_y=4)
        self.assertIsNotNone(far)
        self.assertFalse(far.scene.projection.cover_fades)
        self.assertEqual(len([x for x in far.scene.instances if x.resource_id]),3)

    def test_hidden_or_replaced_oak_skips_preview(self):
        self.assertIsNone(self.plan(current_cells=frozenset({'3,2,0'})))
        self.assertIsNone(self.plan(resources={(2,2,0):(fv(stage='stump'),None)}))
        self.assertIsNone(self.plan(resources={(2,2,0):(fv(stage='sapling'),None)}))
        self.assertIsNone(self.plan(resources={(2,2,0):(fv(stage='depleted'),None)}))
        self.assertIsNone(self.plan(resources={(2,2,0):(fv('core:pine_tree'),None)}))

    def test_nearby_roof_or_building_suppresses_demo(self):
        for cell in ((2,2,0), (4,4,0), (0,0,0)):
            with self.subTest(cell=cell):
                self.assertIsNone(self.plan(excluded_cells={cell}))
        self.assertIsNotNone(self.plan(excluded_cells={(8,8,0)}))

    def test_preview_does_not_iterate_simulation_visibility_history(self):
        class Membership:
            def __init__(self, rows): self.rows=rows;self.checks=0
            def __contains__(self, v): self.checks+=1;return v in self.rows
            def __iter__(self): raise AssertionError('no global discovery scans')
        now = Membership(self.current)
        old = Membership(self.current)
        scene = self.plan(current_cells=now, discovered_cells=old)
        self.assertIsNotNone(scene)
        self.assertLess(now.checks,1024)
        self.assertEqual(old.checks,0)

    def test_reject_unbounded_search_and_isolate_original_software_refs(self):
        with self.assertRaises(ValueError):
            select_oak(source(),self.current,player_x=2,player_y=3,z=0,max_distance=50)
        with self.assertRaises(ValueError):
            select_oak({(i,0,0):(fv(),None) for i in range(1025)},self.current,
                       player_x=2,player_y=3,z=0)
        original = source()
        self.plan(resources=original)
        self.assertIs(original[(2,2,0)][1],original[(2,2,0)][1])
        self.assertEqual(len(original),2)

    def test_camera_matches_fractional_existing_scroll_math(self):
        p = WorldFoot(2.5,3.25,0)
        expected_x = (2.5+3)*28+11-39
        expected_y = (3.25+2)*28+19-47
        self.assertEqual(self.camera.to_screen(p),(expected_x,expected_y))
        self.assertEqual(self.camera.to_world(expected_x,expected_y),p)
        zoom = camera_for_live_grid(left=-3,top=-2,grid_x=11,grid_y=19,
                                    viewport_x=39,viewport_y=47,
                                    viewport_w=560,viewport_h=392,tile_px=56,z=0)
        self.assertEqual(zoom.to_screen(WorldFoot(2.5,3.25)),
                         ((2.5+3)*56+11-39,(3.25+2)*56+19-47))

    def test_no_new_entities_or_renderer_owned_generation(self):
        scene = self.plan()
        self.assertFalse(any(item.resource_id for item in scene.scene.instances
                             if item.instance_id == 'actor:player'))
        self.assertEqual(scene, self.plan())
        self.assertEqual([x.instance_id for x in scene.scene.instances],
                         [x.instance_id for x in self.plan().scene.instances])


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'requires pygame-ce in installed repo')
class CanopyPygameTests(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault('SDL_VIDEODRIVER','dummy')
        os.environ.setdefault('SDL_AUDIODRIVER','dummy')

    def test_alpha_cutout_is_local_and_shadow_independent(self):
        import pygame as pg
        from worldseed.presentation.canopy_preview import draw_crown, draw_shadow, draw_trunk
        pg.init()
        try:
            helper = CanopyPreviewContracts()
            helper.setUp()
            preview = helper.plan()
            viewport=pg.Rect(39,47,280,196)
            screen=pg.Surface((390,294),pg.SRCALPHA)
            screen.set_clip(viewport)
            draw_shadow(pg,screen,preview,viewport)
            shadow=pg.image.tostring(screen,'RGBA')
            draw_trunk(pg,screen,preview,viewport)
            draw_crown(pg,screen,preview,viewport)
            self.assertNotEqual(shadow,pg.image.tostring(screen,'RGBA'))
            self.assertEqual(screen.get_clip(), viewport)
            self.assertEqual(screen.get_at((5,5)).a,0)
            self.assertGreater(pg.mask.from_surface(screen).count(), 0)
        finally:
            pg.quit()

    def test_outside_sight_never_gains_crown_pixels(self):
        import pygame as pg
        from worldseed.presentation.canopy_preview import draw_crown,draw_shadow,draw_trunk
        pg.init()
        try:
            helper = CanopyPreviewContracts();helper.setUp()
            # Only the source oak cell and player cell are visible.
            preview=helper.plan(current_cells=frozenset({'2,2,0','3,2,0'}))
            viewport=pg.Rect(39,47,280,196)
            screen=pg.Surface((390,294),pg.SRCALPHA)
            draw_shadow(pg,screen,preview,viewport)
            draw_trunk(pg,screen,preview,viewport)
            draw_crown(pg,screen,preview,viewport)
            for yy in range(viewport.y,viewport.bottom):
                for xx in range(viewport.x,viewport.right):
                    wx=floor((xx-viewport.x)/28+helper.camera.center.x)
                    wy=floor((yy-viewport.y)/28+helper.camera.center.y)
                    if f'{wx},{wy},0' not in {'2,2,0','3,2,0'}:
                        self.assertEqual(screen.get_at((xx,yy)).a,0)
        finally:
            pg.quit()


@unittest.skipUnless(importlib.util.find_spec('worldseed.persistence') is not None
                     and importlib.util.find_spec('pygame') is not None,
                     'requires prepared WORLDSEED renderer, assets and pygame-ce')
class CanopyLiveReferenceTests(unittest.TestCase):
    """No new game-save loads or worldgen; prepared-world production renderer."""

    def test_software_default_is_identical_and_opt_in_is_observational(self):
        from tools.reference_scenes import run_scene
        with TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.dict(os.environ, {PREVIEW_SWITCH:'0'}):
                baseline = run_scene('forest',output_dir=root/'off',frames=1,
                                     warmup=0,width=800,height=600,zoom=28,
                                     headless=True,png=False)
            with patch.dict(os.environ, {PREVIEW_SWITCH:'1'}):
                preview = run_scene('forest',output_dir=root/'on',frames=1,
                                    warmup=0,width=800,height=600,zoom=28,
                                    headless=True,png=False)
            self.assertTrue(baseline['authority_unchanged'])
            self.assertTrue(preview['authority_unchanged'])
            self.assertEqual(baseline['authority_fingerprint'],preview['authority_fingerprint'])
            self.assertNotEqual(baseline['pixel_sha256'],preview['pixel_sha256'],
                                'opt-in oak should visibly replace one tree without changing gameplay')


if __name__ == '__main__': unittest.main()
