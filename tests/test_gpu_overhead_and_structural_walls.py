"""Cover transparency and physical wall-finish regression checks.

All fade authorization is restricted to already admitted clips. Wall finish
classification changes visuals only, never collider/LOS/save authority.
"""
from __future__ import annotations

from unittest import TestCase

from worldseed.presentation.gpu_cover_fade import cover_fade
from worldseed.presentation.interior_wall_styles import wall_kind, wall_texture
from worldseed.presentation.worldspace import WorldCamera, WorldFoot
from worldseed.presentation.gpu_buildings import (
    PreparedBuildingShell, building_commands)
from worldseed.systems.building_shells import BuildingShell
from tests.test_gpu_buildings import FakeMaterials


class OverheadCoverAndWallsTests(TestCase):
    def test_roof_fades_like_tree_only_when_visible_cover_obscures_character(self):
        camera=WorldCamera(WorldFoot(3.,3.,0),640,480,30)
        player=WorldFoot(3.,3.,0)
        x,y=camera.to_screen(player)
        bounds=(x-50,y-80,x+70,y+40)
        clips=((x-20,y-45,x+25,y+25),)
        fade=cover_fade(camera,player,bounds,clips)
        self.assertGreater(fade['fade_radius'],camera.scale)
        self.assertAlmostEqual(fade['local_alpha'],.08)
        self.assertEqual(cover_fade(camera,player,bounds,()),{})
        self.assertEqual(cover_fade(camera,WorldFoot(30,30,0),bounds,clips),{})
        # A clip outside the player's body cannot cause local transparency
        self.assertEqual(cover_fade(camera,player,bounds,
            ((x+40,y+15,x+60,y+35),)),{})

    def test_real_structural_roof_command_uses_foot_local_fade_but_preserves_hit_cells(self):
        shell=BuildingShell('roof-alpha','','residence','core:residence',
            ((2,2),(3,2),(2,3),(3,3)),(2,3),'roof-alpha:door',0,
            'rectangular',(2,2,3,3))
        visible=frozenset((x,y,0) for x,y in shell.footprint)
        row=PreparedBuildingShell(shell,visible)
        camera=WorldCamera(WorldFoot(3,3,0),320,240,30)
        player=WorldFoot(2.5,3.,0)
        covered=building_commands((row,),camera,FakeMaterials(),viewer=player)[0]
        normal=building_commands((row,),camera,FakeMaterials())[0]
        self.assertEqual(covered.visual_id,normal.visual_id)
        self.assertEqual(covered.clip_rects,normal.clip_rects)
        self.assertEqual(covered.bounds,normal.bounds)
        self.assertGreater(covered.fade_radius,0.)
        self.assertEqual(normal.fade_radius,0.)
        self.assertLess(covered.local_alpha,.20)

    def test_perimeter_load_bearing_walls_and_room_partitions_are_distinct(self):
        width,height=12000,9000
        perimeter=((0,0,width,180),(0,0,180,height),
                   (width-180,0,width,height),(0,height-180,width,height))
        for wall in perimeter:
            self.assertEqual(wall_kind(wall,width,height),'structural')
        for wall in ((5000,250,5180,8100),(250,3000,11000,3180),
                     (180,2000,700,2200)):
            self.assertEqual(wall_kind(wall,width,height),'partition')
        self.assertEqual(wall_texture('core:interior_wall_stone','structural'),
                         'core:wall_fieldstone')
        self.assertEqual(wall_texture('core:interior_wall_timber','structural'),
                         'core:wall_oak_panel')
        self.assertEqual(wall_texture('core:interior_wall_plaster','structural'),
                         'core:wall_limewash')
        self.assertEqual(wall_texture('core:interior_wall_plaster','partition'),
                         'core:interior_wall_plaster')

    def test_structural_and_partition_finishes_resolve_to_authored_assets(self):
        from worldseed.presentation.visuals import VisualRegistry
        visuals=VisualRegistry.load_default()
        for base in ('core:interior_wall_plaster','core:interior_wall_timber',
                     'core:interior_wall_stone'):
            p=visuals.resolve(visuals.ref('interior_textures',wall_texture(base,'structural')))
            q=visuals.resolve(visuals.ref('interior_textures',wall_texture(base,'partition')))
            self.assertIsNotNone(p)
            self.assertIsNotNone(q)
            self.assertTrue(p.is_file())
            self.assertTrue(q.is_file())
            self.assertNotEqual(p,q)
