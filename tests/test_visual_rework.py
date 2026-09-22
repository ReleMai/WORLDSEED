"""Regression checks for malformed art and textured cloud projection."""
import copy
import os
import unittest

os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')
from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.systems.resources import FeatureView


@unittest.skipUnless(PygameTerminal.available(),'pygame optional')
class VisualReworkTests(unittest.TestCase):
    def setUp(self):
        self.term=PygameTerminal()
        self.term.enter()
        self.pg=self.term.pg
        self.vis=self.term._visuals

    def tearDown(self):
        self.term.restore()

    def test_every_cave_material_variant_fills_its_tile(self):
        for tid in ('core:cave_floor','core:cave_wall'):
            ref=self.vis.ref('terrain',tid)
            for i in range(len(ref.paths)):
                path=self.vis.resolve(ref,i)
                with self.subTest(path=path.name):
                    source=self.pg.image.load(str(path))
                    self.assertEqual(source.get_width(),source.get_height())
                    self.assertEqual(set(self.pg.image.tobytes(source,'RGBA')[3::4]),{255})
                    tile=self.term._terrain_surface(tid,path,{}, {},28)
                    self.assertEqual(tile.get_size(),(28,28))
                    self.assertTrue(all(tile.get_at((x,y)).a>=250 for y in range(28) for x in range(28)))

    def test_pine_and_morel_have_transparency_and_correct_display_scale(self):
        bounds={}
        for tid in ('core:pine_tree','core:morel_patch'):
            path=self.vis.resolve(self.vis.ref('resources',tid))
            source=self.pg.image.load(str(path))
            self.assertEqual(source.get_at((0,0)).a,0)
            self.assertEqual(source.get_at((source.get_width()-1,source.get_height()-1)).a,0)
            self.term.screen.fill((0,0,0))
            self.term._draw_resource_feature(FeatureView(tid),path,self.pg.Rect(100,150,40,40))
            mask=self.pg.mask.from_threshold(self.term.screen,(0,0,0),(1,1,1,255))
            mask.invert()
            rects=mask.get_bounding_rects()
            self.assertTrue(rects)
            bounds[tid]=rects[0].unionall(rects)
        self.assertGreater(bounds['core:pine_tree'].height,65)
        self.assertLessEqual(bounds['core:morel_patch'].height,40)
        self.assertLessEqual(bounds['core:morel_patch'].width,40)

    def test_clouds_and_shadows_follow_weather_and_light_without_changing_inputs(self):
        weather=dict(cloud_cover=90,wind_dx=750,wind_dy=160,storm_intensity=80)
        before=copy.deepcopy(weather)
        renderer=self.term._weather_fx._clouds
        args=(640,360,b'rework',90,750,160,0,0,20,3000)
        day=renderer.layers(*args,storm=80,daylight=60000)
        dark=renderer.layers(*args,storm=80,daylight=5000)
        day_alpha=sum(self.pg.image.tobytes(day[0],'RGBA')[3::4])
        dark_alpha=sum(self.pg.image.tobytes(dark[0],'RGBA')[3::4])
        self.assertGreater(day_alpha,dark_alpha*3)
        self.assertGreater(sum(self.pg.image.tobytes(day[1],'RGBA')[3::4]),0)
        again=renderer.layers(*args,storm=80,daylight=60000)
        self.assertEqual(self.pg.image.tobytes(day[0],'RGBA'),self.pg.image.tobytes(again[0],'RGBA'))
        self.term._weather_fx.draw_cloud_shadows(self.term.screen,self.pg.Rect(0,0,640,360),b'rework',weather,
                                               world_left=0,world_top=0,tile_px=20,elapsed_ms=5000)
        self.assertEqual(weather,before)
        self.assertLessEqual(renderer._stamp_bytes,64*1024*1024)
        self.assertLessEqual(len(renderer.frames),2)
        self.assertEqual(renderer.layers(640,360,b'rework',0,750,160,0,0,20,3000),(None,None))

    def test_cloud_density_contains_soft_edges_and_internal_detail(self):
        renderer=self.term._weather_fx._clouds
        renderer._load()
        alphas=self.pg.image.tobytes(renderer._density,'RGBA')[3::4]
        self.assertGreater(len(set(alphas)),100)
        self.assertIn(0,alphas)
        self.assertGreater(max(alphas),160)
