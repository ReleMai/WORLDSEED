"""Semantic precipitation cover stays detached, current and exact-clipped."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import unittest

from worldseed.presentation.gl_worldspace import MAX_COMMANDS, SightMask, SpriteCommand
from worldseed.presentation.gpu_buildings import (
    BuildingArt, PreparedBuildingDoor, PreparedBuildingShell, building_commands,
)
from worldseed.presentation.gpu_objects import PreparedObject
from worldseed.presentation.gpu_scene_bridge import prepare_gpu_frame
from worldseed.presentation.precipitation_cover import MAX_PRECIPITATION_COVERS, cover_commands
from worldseed.presentation.worldspace import VisualLayer, WorldCamera, WorldFoot
from worldseed.systems.building_shells import BuildingShell


PIXELS = b'\x70\x90\x44\xff'*3 + b'\x00\x00\x00\x00'


class Visuals:
    def ref(self,*args):return args
    def resolve(self,*args):return Path('detached-art.png')
    def special(self,*args):return Path('detached-art.png')


class Materials:
    _visuals = Visuals()

    def asset(self,path):return ('asset:'+str(path),1,PIXELS,2,2)
    def tree(self,species,layer,season):return (f'{species}:{layer}:{season}',1,PIXELS,2,2)
    def player(self):return ('player',1,PIXELS,2,2)
    def building(self,row):
        return BuildingArt(('building-art',1,PIXELS,2,2),
                           ('door-art',1,PIXELS,2,2),(.25,.5,.3,.5))


class PrecipitationSelectionTests(unittest.TestCase):
    def command(self,uid='semantic',**kwargs):
        return SpriteCommand(uid,'same-art-is-not-cover-authority',1,PIXELS,2,2,
                             (0.,0.,16.,16.),((0.,0.,16.,16.),),**kwargs)

    def test_only_explicit_current_cover_tags_enter_the_immutable_snapshot(self):
        chosen=self.command(precipitation_cover=True)
        rows=(self.command('roof:guessed-name'),chosen,
              replace(chosen,visual_id='remembered',remembered=True),
              replace(chosen,visual_id='memory:roof',remembered=False),
              replace(chosen,visual_id='action-fade:old-crown'),
              replace(chosen,visual_id='not-admitted',clip_rects=()))
        selected=cover_commands(iter(rows))
        self.assertEqual(selected,(chosen,))
        self.assertIs(selected[0],chosen)
        self.assertEqual(rows[3].precipitation_cover,True)

    def test_cosmetic_fade_and_source_holes_remain_available_to_separate_gpu_pass(self):
        mask=SightMask('cosmetic-edge',1,b'\x00'*4,1,1,(0.,0.,16.,16.))
        row=self.command(precipitation_cover=True,opacity=.1,fade_center=(8.,8.),
                         fade_radius=16.,local_alpha=.08,sway_px=2.5,sight_mask=mask)
        selected=cover_commands((row,))
        self.assertIs(selected[0],row)
        self.assertEqual(selected[0].rgba[-4:],bytes(4))
        self.assertEqual(selected[0].sway_px,2.5)
        self.assertEqual(selected[0].clip_rects,row.clip_rects)
        self.assertIs(selected[0].sight_mask,mask)

    def test_source_and_selected_command_limits_fail_before_silent_dropping(self):
        row=self.command(precipitation_cover=True)
        self.assertEqual(len(cover_commands((row,)*MAX_PRECIPITATION_COVERS)),MAX_PRECIPITATION_COVERS)
        with self.assertRaisesRegex(ValueError,'overhead budget'):
            cover_commands((row,)*(MAX_PRECIPITATION_COVERS+1))
        with self.assertRaisesRegex(ValueError,'frame budget'):
            cover_commands((replace(row,precipitation_cover=False),)*(MAX_COMMANDS+1))
        with self.assertRaisesRegex(ValueError,'detached sprite'):
            cover_commands((object(),))


class PrecipitationProducerTests(unittest.TestCase):
    def setUp(self):
        self.camera=WorldCamera(WorldFoot(2.5,2.5),192,160,24)
        self.visible=frozenset((x,y,0) for y in range(-2,8) for x in range(-2,8))
        self.defs={uid:SimpleNamespace(tags=('tree',),blocks_movement=True)
                   for uid in ('core:oak_tree','core:pine_tree')}

    def frame(self,**kwargs):
        params=dict(camera=self.camera,terrain_by={},resource_by={},resource_defs=self.defs,
            resource_style=lambda _:dict(width=1.3,height=1.9),visible_cells=self.visible,
            discovered_cells=self.visible,viewer=self.camera.center,materials=Materials(),show_player=False)
        params.update(kwargs)
        return prepare_gpu_frame(**params)

    def test_only_current_mature_tree_crowns_get_tagged(self):
        resources={cell:(SimpleNamespace(feature_id=uid,stage=stage),None)
                   for cell,uid,stage in (((1,2,0),'core:oak_tree','mature'),
                                          ((3,2,0),'core:pine_tree','mature'),
                                          ((4,3,0),'core:oak_tree','sapling'),
                                          ((1,3,0),'core:pine_tree','stump'))}
        frame=self.frame(resource_by=resources)
        selected=cover_commands(frame.commands)
        self.assertEqual(len(selected),2)
        self.assertTrue(all(row.visual_id.endswith(':mature:crown') for row in selected))
        self.assertTrue(all(not row.precipitation_cover for row in frame.scenery
                            if not row.visual_id.endswith(':mature:crown')))

    def test_independent_roofs_are_tagged_but_ordinary_overhead_props_are_not(self):
        roof=PreparedObject('roof:0:2:2','roof','core:roof_thatch',WorldFoot(2.5,2.999),
                            1.,1.,VisualLayer.OVERHEAD)
        prop=PreparedObject('raised-prop','structure','core:chest',WorldFoot(3.5,2.999),
                            1.,1.,VisualLayer.OVERHEAD)
        frame=self.frame(objects=(roof,prop))
        self.assertEqual(tuple(row.visual_id for row in cover_commands(frame.commands)),
                         ('object:roof:0:2:2',))
        self.assertFalse(next(row for row in frame.scenery
                              if row.visual_id=='object:raised-prop').precipitation_cover)

    def test_building_cover_retains_disjoint_footprint_clips_and_door_is_excluded(self):
        shell=BuildingShell('split-roof','','residence','core:residence',
                            ((1,1),(3,1)),(1,1),'door',0,'courtyard',(1,1,3,1))
        row=PreparedBuildingShell(shell,frozenset(((1,1,0),(3,1,0))),
                                   door=PreparedBuildingDoor('door',(1,1,0)))
        commands=building_commands((row,),self.camera,Materials(),viewer=WorldFoot(1.5,1.5))
        selected=cover_commands(commands)
        self.assertEqual(len(selected),1)
        self.assertTrue(commands[0].precipitation_cover)
        self.assertFalse(commands[1].precipitation_cover)
        self.assertGreater(selected[0].fade_radius,0.)
        self.assertEqual(selected[0].rgba,PIXELS)
        self.assertEqual(len(selected[0].clip_rects),2)
        courtyard=self.camera.to_screen(WorldFoot(2.5,1.5))
        self.assertFalse(any(a<=courtyard[0]<c and b<=courtyard[1]<d
                             for a,b,c,d in selected[0].clip_rects))

    def test_current_projection_never_promotes_last_seen_roofs_or_crowns(self):
        cell=(1,2,0)
        feature=SimpleNamespace(feature_id='core:oak_tree',stage='mature')
        shell=BuildingShell('past-roof','','residence','core:residence',
                            ((3,3),),(3,3),'door',0,'rectangular',(3,3,3,3))
        building=PreparedBuildingShell(shell,frozenset(((3,3,0),)))
        roof=PreparedObject('past-independent-roof','roof','core:roof_thatch',
                            WorldFoot(4.5,3.999),1.,1.,VisualLayer.OVERHEAD)
        current=self.visible-{cell,(3,3,0),(4,3,0)}
        frame=self.frame(terrain_by={cell:'core:forest'},visible_cells=current,
            remembered_resources=((cell,feature),),remembered_buildings=(building,),
            remembered_objects=(roof,))
        memory=tuple(row for row in frame.scenery if row.remembered)
        self.assertTrue(any(':crown' in row.visual_id for row in memory))
        self.assertTrue(any('past-roof' in row.visual_id for row in memory))
        self.assertTrue(any('past-independent-roof' in row.visual_id for row in memory))
        self.assertTrue(all(not row.precipitation_cover for row in memory))
        self.assertEqual(cover_commands(frame.commands),())


if __name__=='__main__':
    unittest.main()
