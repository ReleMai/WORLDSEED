"""G4 tree art and multi-cover preview preserves G2 source/collision contracts."""
from __future__ import annotations
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from worldseed.presentation.canopy_preview import (
    camera_for_live_grid,prepare_tree_cluster,MAX_PREVIEW_TREES
)
from worldseed.presentation.worldspace import VisualLayer
from worldseed.presentation.tree_art import manifest,layer_png,TREE_DIR

class WorldspaceArtPreviewTests(unittest.TestCase):
    def setUp(self):
        self.visible=frozenset(f'{x},{y},0' for x in range(-8,14) for y in range(-8,14))
        self.resources={(x,y,0):(SimpleNamespace(feature_id=f'core:{species}_tree',stage=stage),None)
                 for x,y,species,stage in ((1,2,'oak','mature'),(2,2,'pine','mature'),(4,2,'oak','stump'),(5,2,'pine','depleted'))}
        self.defs={f'core:{species}_tree':SimpleNamespace(tags=('tree',),blocks_movement=True)
                   for species in ('oak','pine')}
        self.camera=camera_for_live_grid(left=-3,top=-3,grid_x=0,grid_y=0,
                    viewport_x=0,viewport_y=0,viewport_w=480,viewport_h=400,tile_px=28,z=0)
    def cluster(self,**overrides):
        params=dict(resource_by=self.resources,resource_defs=self.defs,resource_style=lambda _:{'width':1.25,'height':1.8},
                   current_cells=self.visible,discovered_cells=self.visible,
                   player_x=2,player_y=3,player_z=0,player_fx=.5,player_fy=.5,camera=self.camera)
        params.update(overrides)
        return prepare_tree_cluster(**params)

    def test_multiple_species_are_distinct_one_hitbox_each(self):
        previews=self.cluster()
        self.assertEqual(len(previews),2)
        self.assertEqual({p.source for p in previews},{(1,2,0),(2,2,0)})
        for p in previews:
            physical=[x for x in p.scene.instances if x.physical_cells]
            crowns=[x for x in p.scene.instances if x.layer is VisualLayer.OVERHEAD]
            shadows=[x for x in p.scene.instances if x.layer is VisualLayer.GROUND_SHADOW]
            self.assertEqual(len(physical),1)
            self.assertEqual(len(crowns),1)
            self.assertEqual(len(shadows),1)
            self.assertEqual(physical[0].physical_cells,(p.source,))
            self.assertEqual(crowns[0].physical_cells,())
            self.assertEqual({x.resource_id for x in physical+crowns+shadows},
                             {f'feature:0:{p.source[0]}:{p.source[1]}:'+physical[0].content_id})

    def test_single_cell_fow_and_roof_suppress_unapproved_coverage(self):
        self.assertEqual(len(self.cluster(current_cells=frozenset({'1,2,0','2,3,0'}))),1)
        self.assertEqual(len(self.cluster(excluded_cells={(3,4,0)})),0)
        self.assertEqual(len(self.cluster(excluded_cells={(1,1,0)})),0)

    def test_count_bounded_even_with_many_prepared_resources(self):
        data={(x,2,0):(SimpleNamespace(feature_id='core:pine_tree',stage='mature'),None) for x in range(20)}
        self.assertLessEqual(len(self.cluster(resource_by=data)),MAX_PREVIEW_TREES)
        with self.assertRaises(ValueError):self.cluster(max_trees=100)
        with self.assertRaises(ValueError):self.cluster(resource_by={(x,2,0):(SimpleNamespace(feature_id='core:pine_tree',stage='mature'),None) for x in range(1025)})

    def test_distinct_season_material_and_authoritative_source(self):
        self.assertNotEqual(layer_png('oak','crown','summer'),layer_png('oak','crown','winter'))
        self.assertEqual(manifest()['anchor_policy'].startswith('bottom-center'),True)
        self.assertEqual(self.cluster(),self.cluster())

@unittest.skipUnless(importlib.util.find_spec('pygame'),'pygame-ce required')
class PygameArtworkLayerTests(unittest.TestCase):
    def test_seasonal_png_layers_load_and_preserve_clip(self):
        import os,pygame as pg
        from worldseed.presentation.canopy_preview import draw_shadow,draw_trunk,draw_crown
        os.environ.setdefault('SDL_VIDEODRIVER','dummy')
        pg.init()
        try:
            t=WorldspaceArtPreviewTests();t.setUp()
            for season in ('summer','winter'):
                screen=pg.Surface((480,400),pg.SRCALPHA)
                viewport=pg.Rect(0,0,480,400)
                screen.set_clip(viewport)
                for part in t.cluster():
                    draw_shadow(pg,screen,part,viewport,season=season)
                    draw_trunk(pg,screen,part,viewport,season=season)
                    draw_crown(pg,screen,part,viewport,season=season)
                self.assertEqual(screen.get_clip(),viewport)
                self.assertGreater(pg.mask.from_surface(screen).count(),0)
        finally:pg.quit()

if __name__=='__main__':unittest.main()
