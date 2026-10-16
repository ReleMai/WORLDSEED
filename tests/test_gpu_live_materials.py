"""Live GPU content remains explicit, bounded and clipped to current sight."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase

from worldseed.presentation.gpu_scene_bridge import GpuMaterialSource, prepare_gpu_frame
from worldseed.presentation.visuals import VisualRegistry
from worldseed.presentation.worldspace import WorldCamera, WorldFoot
from worldseed.presentation.worldspace_adapter import MAX_PREPARED_ACTORS, PreparedActor


PIXELS=b'\x70\x90\x44\xff'*16


class FakeMaterials:
    def __init__(self):self.actor_reads=[]
    def asset(self,path):return (str(path),1,PIXELS,4,4)
    def player(self):return ('player',1,PIXELS,4,4)
    def tree(self,species,layer,season):return (f'{species}:{layer}:{season}',1,PIXELS,4,4)
    def actor(self,content_id):
        self.actor_reads.append(content_id)
        return (content_id,1,PIXELS,4,4)


class GPULiveMaterialsContracts(TestCase):
    def setUp(self):
        self.camera=WorldCamera(WorldFoot(0,0,3),192,192,32,elevation_px_per_cell=17)
        self.visible=frozenset((x,y,3) for x in range(-3,3) for y in range(-3,3))
        self.materials=FakeMaterials()

    def build(self,**changes):
        args=dict(camera=self.camera,terrain_by={},resource_by={},resource_defs={},
            resource_style=lambda fid:{'width':1.3,'height':1.9},
            visible_cells=self.visible,discovered_cells=self.visible,
            viewer=WorldFoot(.5,.5,3),materials=self.materials,show_player=False)
        args.update(changes)
        return prepare_gpu_frame(**args)

    def test_only_authorized_visible_outdoor_actors_read_materials(self):
        actors=(PreparedActor('npc','core:npc',WorldFoot(.5,.5,3),True),
            PreparedActor('creature','core:deer',WorldFoot(1.5,.5,3),True),
            PreparedActor('stealth','core:wolf',WorldFoot(.5,1.5,3),False),
            PreparedActor('private','core:cow',WorldFoot(.5,1.5,3),True,room_id='private'),
            PreparedActor('above','core:chicken',WorldFoot(.5,.5,4),True),
            PreparedActor('unknown','core:rabbit',WorldFoot(4.5,.5,3),True))
        frame=self.build(actors=actors)
        self.assertEqual({row.visual_id for row in frame.scenery},{'actor:npc','actor:creature'})
        self.assertEqual(set(self.materials.actor_reads),{'core:npc','core:deer'})
        self.assertTrue(all(row.clip_rects for row in frame.scenery))

    def test_explored_ground_is_dim_and_unknown_stays_undrawn(self):
        terrain={(0,0,3):'core:grass', (1,0,3):'core:sand',
                 (2,0,3):'core:rock'}
        current=frozenset({(0,0,3)})
        memory=frozenset({(1,0,3)})
        args=dict(terrain_by=terrain, visible_cells=current,
                  discovered_cells=memory)
        frame=self.build(**args)
        commands={row.visual_id:row for row in frame.ground}
        self.assertEqual(set(commands), {'ground:3:0:0', 'ground:3:1:0'})
        self.assertEqual(commands['ground:3:0:0'].opacity, 1.)
        self.assertAlmostEqual(commands['ground:3:1:0'].opacity, .42)
        self.assertEqual(frame.visible_ground_cells, 1)
        self.assertEqual(frame.scenery, ())
        blinded=self.build(**args, show_explored_memory=False)
        self.assertEqual([row.visual_id for row in blinded.ground],
                         ['ground:3:0:0'])
        self.assertEqual(blinded.visible_ground_cells, 1)

    def test_additional_actors_cannot_replace_viewer_or_exceed_budget(self):
        for actor in (PreparedActor('gpu-viewer','core:npc',WorldFoot(.5,.5,3),True),
                      PreparedActor('other','core:player',WorldFoot(.5,.5,3),True,is_viewer=True)):
            with self.assertRaises(ValueError):self.build(actors=(actor,))
        actors=tuple(PreparedActor(str(i),'core:npc',WorldFoot(.5,.5,3),True)
                     for i in range(MAX_PREPARED_ACTORS))
        with self.assertRaises(ValueError):self.build(actors=actors)

    def test_harvest_stages_have_distinct_art_and_keep_feature_identity(self):
        resources={(0,0,3):(SimpleNamespace(feature_id='core:oak_tree',stage='stump'),None),
                   (1,0,3):(SimpleNamespace(feature_id='core:pine_tree',stage='sapling'),None)}
        defs={fid:SimpleNamespace(tags=('tree',),blocks_movement=True)
              for fid in ('core:oak_tree','core:pine_tree')}
        frame=self.build(resource_by=resources,resource_defs=defs)
        self.assertEqual(len(frame.scenery),2)
        by_id={row.visual_id:row for row in frame.scenery}
        stump=by_id['feature:3:0:0:core:oak_tree:stump:base']
        sapling=by_id['feature:3:1:0:core:pine_tree:sapling:base']
        self.assertEqual(Path(stump.texture_id).name,'rotten_stump_cache.png')
        self.assertEqual(Path(sapling.texture_id).name,'logging_sapling.png')
        self.assertAlmostEqual(stump.bounds[3]-stump.bounds[1],self.camera.scale*.55)
        self.assertFalse(any(row.sway_px for row in frame.scenery))

    def test_fire_extent_clips_to_current_cells_at_camera_elevation(self):
        visible=frozenset({(0,0,3)})
        frame=self.build(visible_cells=visible,fire_cells=((0,0,3),(0,0,4),(2,0,3)))
        self.assertEqual(len(frame.scenery),1)
        fire=frame.scenery[0]
        self.assertEqual(fire.visual_id,'fire:3:0:0')
        x,y=self.camera.to_screen(WorldFoot(0,0,3))
        self.assertEqual(fire.clip_rects,((x,y,x+self.camera.scale,y+self.camera.scale),))
        # The artwork extends into unseen neighboring cells, but its mask does not.
        self.assertLess(fire.bounds[0],x)
        self.assertLess(fire.bounds[1],y)
        self.assertGreater(fire.bounds[2],x+self.camera.scale)

    def test_fire_uses_every_authorized_extent_cell_and_is_budgeted(self):
        frame=self.build(fire_cells=((0,0,3),))
        fire=frame.scenery[0]
        self.assertEqual(len(fire.clip_rects),6)
        for left,top,right,bottom in fire.clip_rects:
            cell=self.camera.to_world(left,top,ground_z=3).cell
            self.assertIn(cell,self.visible)
            self.assertEqual((right-left,bottom-top),(self.camera.scale,self.camera.scale))
        with self.assertRaises(ValueError):self.build(fire_cells=((0,0,3),)*33)

    def test_actor_content_resolution_reuses_existing_catalog_and_mod_fallback(self):
        visuals=VisualRegistry.load_default()
        materials=GpuMaterialSource(None,visuals=visuals)
        materials.asset=lambda path:path
        for content_id in ('core:npc','core:npc:male','core:npc:female','core:deer','mod:unknown'):
            path=materials.actor(content_id)
            self.assertTrue(path.is_file(),path)
            self.assertEqual(path,materials.actor(content_id))
        self.assertIn('/npc/female/',materials.actor('core:npc:female').as_posix())
        self.assertIn('/species/illustrated/',materials.actor('core:deer').as_posix())
        self.assertIn('/species/_dev17/',materials.actor('mod:unknown').as_posix())
