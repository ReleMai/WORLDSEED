"""Interior pass-2 shadow, glow and GPU source budget contracts."""
from __future__ import annotations
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

from worldseed.presentation.interior_art_lighting import (
    GLOW_SIZE, SHADOW_SIZE, MAX_VISIBLE_HALO_SOURCES,
    light_halo_bounds, shadow_bounds, shadow_texture, warm_glow_texture,
    nearest_light)


class InteriorArtPass2Tests(TestCase):
    def test_soft_art_textures_are_bounded_rgba_and_feather_to_edges(self):
        for source,shape in ((shadow_texture(),SHADOW_SIZE),
                             (warm_glow_texture(),GLOW_SIZE)):
            self.assertEqual(source[3:],shape)
            self.assertEqual(len(source[2]),shape[0]*shape[1]*4)
            center=((shape[1]//2)*shape[0]+shape[0]//2)*4+3
            self.assertGreater(source[2][center],source[2][3])
        self.assertIs(shadow_texture(),shadow_texture())
        self.assertIs(warm_glow_texture(),warm_glow_texture())

    def test_projected_shadows_depend_on_nearest_visible_light_not_hidden_lights(self):
        class Light:
            def __init__(self,x,y,uid):
                self.x,self.y,self.uid=x,y,uid
        near=Light(4000,4000,'a')
        far=Light(10000,10000,'b')
        self.assertEqual(nearest_light(4,4,(far,near)),(4,4))
        rect=(100.,100.,140.,150.)
        a=shadow_bounds(rect,(100.,110.),40,height_ratio=1.5)
        b=shadow_bounds(rect,(170.,200.),40,height_ratio=1.5)
        self.assertGreater(a[0],b[0])
        self.assertLess(a[2]-a[0],42.)
        self.assertTrue(all(abs(value)<1e5 for value in a+b))
        bounds=light_halo_bounds(40,60,15000,40)
        self.assertEqual(bounds,(-100.,-80.,180.,200.))
        self.assertLessEqual(MAX_VISIBLE_HALO_SOURCES,8)

    def test_large_indoor_paintings_downsample_without_changing_outdoor_art(self):
        from worldseed.presentation.gpu_scene_bridge import GpuMaterialSource
        class FakeSurface:
            def __init__(self,size): self._size=size
            def get_size(self): return self._size
        class FakePygame:
            def __init__(self):
                self.image=Mock()
                self.image.load=Mock(return_value=FakeSurface((2048,1024)))
                self.image.tobytes=Mock(side_effect=lambda surf,fmt:b'')
                self.transform=Mock()
                self.transform.smoothscale=Mock(side_effect=lambda surf,size:FakeSurface(size))
        pg=FakePygame()
        materials=GpuMaterialSource(pg)
        home=Path('worldseed/assets/sprites/interiors/dev52/oak_armchair.png')
        outside=Path('worldseed/assets/sprites/resources/oak_tree.png')
        inside=materials.asset(home)
        self.assertEqual(inside[3:],(320,160))
        self.assertEqual(materials.asset(home),inside)
        self.assertEqual(pg.image.load.call_count,1)
        self.assertEqual(materials.asset(outside)[3:],(2048,1024))
        self.assertEqual(pg.transform.smoothscale.call_count,1)

    def test_art_review_assets_are_real_current_sprite_mappings(self):
        import json
        from tools.generate_interior_style_sheets import CATEGORIES,resolve_asset,MANIFEST
        manifest=json.loads(MANIFEST.read_text(encoding='utf-8'))
        self.assertEqual(len(CATEGORIES),4)
        self.assertGreaterEqual(sum(len(group) for group in CATEGORIES.values()),36)
        for group, ids in CATEGORIES.items():
            with self.subTest(group=group):
                self.assertGreaterEqual(len(ids),8)
                for uid in ids:
                    path=resolve_asset(manifest,uid)
                    self.assertIsNotNone(path)
                    self.assertTrue(path.is_file(),f'missing authored art: {uid}')
                    self.assertEqual(path.suffix.lower(),'.png')

    def test_hidden_lamps_never_enter_prepared_visibility_or_render_glow(self):
        from tests.test_gpu_interiors import GPUInteriorContracts,Materials
        from worldseed.systems.interior_state import InteriorFurniture
        from worldseed.presentation.live_gpu_scene import capture_live_scene
        suite=GPUInteriorContracts()
        from worldseed.config import DATA_DIR
        from worldseed.content.registry import ContentRegistry
        suite.registry=ContentRegistry.load(DATA_DIR)
        sim,plan,player,_=suite.fixture()
        before=plan.to_dict()
        snapshot=capture_live_scene(sim,suite.camera(sim))
        self.assertFalse(any(source.uid=='private-lamp'
            for source in snapshot.interior_scene.visible_lights))
        frame=snapshot.gpu_frame(materials=Materials(),registry=suite.registry,
                                 resource_style=lambda _: {})
        self.assertFalse(any('private-lamp' in cmd.visual_id for cmd in frame.commands))
        self.assertEqual(plan.to_dict(),before)
        plan.furniture.append(InteriorFurniture('public-lamp','core:lamp_stand_piece',
                                               1200,2600,500,500))
        scene=capture_live_scene(sim,suite.camera(sim))
        self.assertIn('public-lamp',tuple(s.uid for s in scene.interior_scene.visible_lights))
        lit=scene.gpu_frame(materials=Materials(),registry=suite.registry,
                            resource_style=lambda _: {})
        glow=next(c for c in lit.scenery if c.visual_id=='interior-glow:public-lamp')
        self.assertTrue(glow.clip_rects)
        self.assertLess(glow.opacity,1)
        self.assertFalse(glow.remembered)
