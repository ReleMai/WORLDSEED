"""Integration contract for ten authored cabin PNGs and physical door projection."""
import os
os.environ.setdefault("SDL_VIDEODRIVER","dummy")
os.environ.setdefault("SDL_AUDIODRIVER","dummy")
import unittest
from pathlib import Path
from worldseed.systems.homestead_blueprints import catalog,doorway,footprint
from worldseed.ui.homestead_art import (
    cabin_asset_path,cabin_image_rect,doorway_pixel,doorway_edge_rect,
    draw_cabin_art,DOOR_IMAGE_X,DOOR_IMAGE_Y)
from worldseed.ui.pygame_terminal import PygameTerminal

class AuthoringContracts(unittest.TestCase):
    def test_each_catalog_style_references_distinct_packaged_png(self):
        from PIL import Image
        import hashlib
        signatures=set()
        for index in range(1,11):
            style=f"log_cabin_{index:02d}"
            path=cabin_asset_path(style)
            self.assertIsNotNone(path,style)
            self.assertEqual(path.suffix,'.png')
            with Image.open(path) as img:
                self.assertGreater(img.width,220)
                self.assertGreater(img.height,220)
                self.assertIn(img.mode,('P','RGBA'))
                self.assertLess(img.convert('RGBA').getpixel((0,0))[3],25)
                self.assertGreater(img.convert('RGBA').getchannel('A').getbbox()[2],180)
            signatures.add(hashlib.sha256(path.read_bytes()).digest())
        self.assertEqual(len(signatures),10)

    def test_door_anchors_and_asset_positions_are_catalog_complete(self):
        styles={key for key,value in catalog()[1].items() if value['home_id']=='log_cabin'}
        self.assertEqual(styles,set(DOOR_IMAGE_X))
        self.assertEqual(styles,set(DOOR_IMAGE_Y))
        for style in styles:
            self.assertGreater(DOOR_IMAGE_X[style],0)
            self.assertLess(DOOR_IMAGE_X[style],1)

    def test_all_rotations_have_one_enterable_footprint_edge(self):
        for sid,style in catalog()[1].items():
            if style['home_id']!='log_cabin':continue
            for rotation in range(4):
                site={'home_id':'log_cabin','style_id':sid,
                      'x':4,'y':7,'z':0,'orientation':rotation}
                inside,outside=doorway(site)
                self.assertIn(inside,footprint(site))
                self.assertNotIn(outside,footprint(site))
                px,py=doorway_pixel(site,200,250,0,0,24)
                self.assertAlmostEqual(px,200+(inside[0]+.5)*24)
                self.assertAlmostEqual(py,250+(inside[1]+.5)*24)

@unittest.skipUnless(PygameTerminal.available(),'requires pygame-ce')
class DrawnCabinTests(unittest.TestCase):
    def setUp(self):
        self.term=PygameTerminal()
        self.term.enter()
        self.pg=self.term.pg
    def tearDown(self):self.term.restore()

    def test_all_styles_draw_and_align_threshold_in_every_rotation(self):
        from worldseed.systems.homestead_blueprints import catalog
        rect=self.pg.Rect(0,0,self.term.screen.get_width(),self.term.screen.get_height())
        for sid,spec in catalog()[1].items():
            if spec['home_id']!='log_cabin':continue
            for facing in range(4):
                site={'home_id':'log_cabin','style_id':sid,
                      'x':10,'y':10,'z':0,'orientation':facing}
                result=draw_cabin_art(self.term,site,grid_x=0,grid_y=0,left=0,top=0,
                                     size=20,clip=rect,opacity=180)
                self.assertIsNotNone(result,(sid,facing))
                edge=doorway_edge_rect(self.pg,site,0,0,0,0,20)
                (dx,dy,dz),_=doorway(site)
                tile=self.pg.Rect(dx*20,dy*20,20,20)
                self.assertTrue(tile.contains(edge),(sid,facing,edge,tile))
                self.assertTrue(rect.colliderect(result))

    def test_build_carousel_loads_authored_sprite_not_placeholder(self):
        style=catalog()[1]['log_cabin_03']
        loads=[]
        original=self.term._load_sprite
        def record(path,*args,**kwargs):
            loads.append(str(path) if path else '')
            return original(path,*args,**kwargs)
        self.term._load_sprite=record
        try:
            self.term._draw_chrome('WORLDSEED // LOCAL')
            self.term.present_homestead_styles(style,2,10)
        finally:self.term._load_sprite=original
        self.assertTrue(any(path.endswith('log_cabin_03.png') for path in loads))

if __name__=='__main__':unittest.main()
