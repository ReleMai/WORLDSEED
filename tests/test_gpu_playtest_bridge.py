"""G8 prepared, sight-gated GPU outdoor scene + bounded playable visual arena."""
from __future__ import annotations
from types import SimpleNamespace
from unittest import TestCase
from worldseed.presentation.worldspace import WorldCamera, WorldFoot
from worldseed.presentation.gpu_scene_bridge import cell_bounds,prepare_gpu_frame,GpuMaterialSource
from worldseed.presentation.gl_worldspace import MAX_COMMANDS
from tools.worldseed_gpu_playtest import bounded_camera,WEATHER,fire_lights

PIXELS=b'\x70\x90\x44\xff'*16
class FakeAssets:
    def asset(self,path):return ('terrain:'+path.name,1,PIXELS,4,4)
    def tree(self,species,layer,season):return (f'{species}:{layer}:{season}',1,PIXELS,4,4)
    def player(self):return ('player',1,PIXELS,4,4)

class GPUSceneBridgeContracts(TestCase):
    def setUp(self):
        self.camera=WorldCamera(WorldFoot(12.,12.,0),640,480,32)
        a,b,c,d=cell_bounds(self.camera)
        self.terrain={(x,y,0):'core:forest' for y in range(b,d) for x in range(a,c)}
        self.resources={(11,12,0):(SimpleNamespace(feature_id='core:oak_tree',stage='mature'),None),
                        (13,12,0):(SimpleNamespace(feature_id='core:pine_tree',stage='mature'),None)}
        self.defs={'core:oak_tree':SimpleNamespace(tags=('tree',),blocks_movement=True),
                   'core:pine_tree':SimpleNamespace(tags=('tree',),blocks_movement=True)}
        self.visible=frozenset(self.terrain)

    def build(self,**kw):
        return prepare_gpu_frame(camera=self.camera,terrain_by=kw.get('terrain_by',self.terrain),
            resource_by=kw.get('resource_by',self.resources),resource_defs=self.defs,
            resource_style=lambda x:{'width':1.3,'height':1.9},
            visible_cells=kw.get('visible_cells',self.visible),discovered_cells=self.visible,
            viewer=WorldFoot(11.8,12.2,0),materials=FakeAssets(),show_player=False)

    def test_two_species_all_three_layers_and_no_new_source_targets(self):
        p=self.build()
        self.assertEqual(len(p.ground),len(self.terrain))
        self.assertEqual(len(p.scenery),6)
        self.assertEqual({c.texture_id.split(':')[0] for c in p.scenery},{'oak','pine'})
        self.assertTrue(any('shadow' in c.texture_id for c in p.scenery))
        self.assertTrue(any(c.sway_px>0 for c in p.scenery))
        self.assertEqual(len({c.visual_id for c in p.scenery}),6)
        self.assertLess(len(p.commands),MAX_COMMANDS)

    def test_fow_never_uploads_remembered_or_hidden_ground_and_tree(self):
        current=self.visible-{(11,12,0)}
        p=self.build(visible_cells=current)
        self.assertFalse(any(c.visual_id=='ground:0:11:12' for c in p.ground))
        self.assertFalse(any('oak' in c.texture_id for c in p.scenery))
        self.assertTrue(any('pine' in c.texture_id for c in p.scenery))

    def test_camera_boundaries_and_zoom_rejections(self):
        camera=bounded_camera(12,12,640,480,28,(0,0,64,64))
        self.assertGreater(camera.center.x,0)
        self.assertLess(camera.center.x,64)
        with self.assertRaises(ValueError):bounded_camera(10,10,1920,1080,20,(0,0,64,64))
        with self.assertRaises(ValueError):bounded_camera(10,10,640,480,5,(0,0,64,64))
        self.assertEqual(len(WEATHER),6)
        with self.assertRaises(ValueError):bounded_camera(256,256,1920,1080,20,(0,0,512,512))

    def test_trunk_foot_not_changed_by_art_sway_or_shadow_and_fire_budget(self):
        p=self.build()
        self.assertTrue(all(c.sway_px==0 for c in p.scenery if ':trunk:' in c.texture_id))
        self.assertTrue(all(c.sway_px==0 for c in p.scenery if ':shadow:' in c.texture_id))
        sim=SimpleNamespace(state=SimpleNamespace(fires={'0':SimpleNamespace(x=12,y=12,z=0,fuel=50,intensity=65)}))
        light=fire_lights(sim,self.camera,self.visible,torch=True)
        self.assertEqual(len(light),2)
        self.assertGreater(light[1].radius,100)

class PreparedReferenceGPUContracts(TestCase):
    def test_real_prepared_forest_preserves_sim_authority(self):
        try:
            from pathlib import Path
            import tempfile
            from tools.reference_scene_fixtures import build_fixture
            from worldseed.content.registry import ContentRegistry
            from worldseed.config import DATA_DIR
            from tools.worldseed_gpu_playtest import visible_prepared_window
        except ImportError as exc:
            self.skipTest(f'full WORLDSEED checkout required: {exc}')
        registry=ContentRegistry.load(DATA_DIR)
        with tempfile.TemporaryDirectory() as tmp:
            f=build_fixture('forest',registry,Path(tmp),width=1280,height=720,zoom=28)
            try:
                before=f.authority_fingerprint()
                camera=bounded_camera(256.5,256.5,1280,720,28,f.bounds)
                terrain,res,vis=visible_prepared_window(f,camera)
                self.assertGreater(len(terrain),700)
                self.assertGreater(len(res),10)
                model=prepare_gpu_frame(camera=camera,terrain_by=terrain,
                    resource_by=res,resource_defs=registry.resources,
                    resource_style=lambda fid:{'width':1.3,'height':1.9},
                    visible_cells=vis,discovered_cells=vis,
                    viewer=WorldFoot(256.5,256.5),materials=FakeAssets())
                self.assertTrue(model.ground)
                self.assertTrue(model.scenery)
                self.assertEqual(before,f.authority_fingerprint())
            finally:f.close()
