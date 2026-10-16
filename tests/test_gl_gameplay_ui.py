"""GPU UI stays bounded, observational and preserves the completed world pass."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from worldseed.presentation.gl_gameplay_ui import (
    GLGameplayUI, MAX_TEXT_CACHE, MAX_TEXT_CACHE_BYTES, MAX_UI_COMMANDS,
    MAX_UI_ROWS, OverlayModel, TextRun, UI_TEXTURE_BUDGET, build_layout,
)
from worldseed.ui.widgets import MenuRow
from tests.test_worldspace_gpu_art import FakeContext
from tests.test_gpu_visibility_shader import _OffscreenWindowContext


class GPUUILayoutContracts(unittest.TestCase):
    def model(self,**changes):
        value=OverlayModel(hud=('Day 3 12:00 | HP 80/100','Hunger 12 | Thirst 8'),
            target='Visible target: Oak tree',message='You gather fallen branches.',
            panel_title='Action Hub',rows=tuple(MenuRow(f'action:{i}',f'Action {i}') for i in range(100)))
        return replace(value,**changes)

    def test_supported_viewports_fit_with_explicit_hits_and_read_only_paging(self):
        model=self.model(scroll=30,selected=32)
        for width,height in ((640,480),(1280,720),(1920,1080)):
            with self.subTest(size=(width,height)):
                before=repr(model)
                layout=build_layout(width,height,model)
                self.assertEqual(repr(model),before)
                self.assertEqual(layout.page_start,30)
                self.assertGreater(layout.page_size,0)
                self.assertLessEqual(layout.page_size,16)
                self.assertLessEqual(len(layout.panels)+len(layout.texts),MAX_UI_COMMANDS)
                for row in (*layout.panels,*layout.texts,*layout.hitregions):
                    x,y,right,bottom=row.bounds
                    self.assertTrue(0<=x<right<=width,row)
                    self.assertTrue(0<=y<bottom<=height,row)
                clickable=[hit for hit in layout.hitregions if hit.uid]
                self.assertEqual(len(clickable),layout.page_size)
                for offset,hit in enumerate(clickable):
                    self.assertEqual(hit.uid,f'action:{30+offset}')
                    x,y,right,bottom=hit.bounds
                    self.assertEqual(layout.hit_test((x+right)/2,(y+bottom)/2),hit.uid)
                self.assertTrue(layout.blocks_world(width/2,height/2))
                self.assertIsNone(layout.hit_test(-1,-1))
                with self.assertRaises(FrozenInstanceError):layout.page_start=0

    def test_hud_does_not_block_uncovered_world_and_modal_captures_margins(self):
        plain=build_layout(640,480,self.model(panel_title='',rows=()))
        self.assertFalse(plain.blocks_world(320,200))
        self.assertTrue(plain.blocks_world(10,10))
        modal=build_layout(640,480,self.model())
        self.assertTrue(modal.blocks_world(1,200))
        self.assertIsNone(modal.hit_test(1,200))

    def test_records_reflow_and_detail_scroll_preserves_depth(self):
        details=tuple(f'Line {i}: complete authorized record' for i in range(100))
        model=self.model(details=details,detail_scroll=50)
        layout=build_layout(640,480,model)
        self.assertEqual(layout.total_detail_lines,100)
        self.assertEqual(layout.detail_start,50)
        self.assertGreater(layout.detail_page_size,0)
        self.assertTrue(any(run.text.startswith('Line 50:') for run in layout.texts))
        self.assertTrue(any(run.text.startswith('Line 99:')
            for run in build_layout(640,480,replace(model,detail_scroll=99)).texts))
        long_label='long authorized label '*60
        model=self.model(rows=(MenuRow('long',long_label),),selected=0,scroll=0,
                         details=(),detail_scroll=0)
        layout=build_layout(640,480,model)
        self.assertEqual(layout.page_size,1)
        self.assertGreater(layout.total_detail_lines,layout.detail_page_size)
        readout=self.model(rows=(),details=tuple(f'Help line {i}' for i in range(30)))
        page=build_layout(640,480,readout)
        self.assertGreater(page.detail_page_size,4)
        self.assertEqual(page.total_detail_lines,30)
        final=build_layout(640,480,replace(readout,detail_scroll=29))
        self.assertTrue(any(run.text=='Help line 29' for run in final.texts))

    def test_models_reject_mutable_unbounded_or_ambiguous_records(self):
        for fields in (dict(rows=[]),dict(hud=['mutable']),dict(rows=(MenuRow('x','one'),MenuRow('x','two'))),
                       dict(rows=tuple(MenuRow(str(i),'row') for i in range(MAX_UI_ROWS+1))),
                       dict(message='x'*4097),dict(scroll=-1)):
            with self.subTest(fields=tuple(fields)),self.assertRaises(ValueError):OverlayModel(**fields)
        for width,height in ((0,480),(640,0),(3841,480)):
            with self.assertRaises(ValueError):build_layout(width,height,OverlayModel())


class GPUUIRendererContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import pygame
        except ImportError:
            raise unittest.SkipTest('pygame font dependency unavailable')
        cls.pg=pygame

    def test_fake_gl_preserves_target_and_bounds_text_uploads_and_cleanup(self):
        context=FakeContext()
        fake_gl=SimpleNamespace(BLEND=1,SRC_ALPHA=2,ONE_MINUS_SRC_ALPHA=3)
        with patch.dict(sys.modules,{'moderngl':fake_gl}):
            overlay=GLGameplayUI(context,self.pg,640,480)
            self.addCleanup(overlay.close)
            model=OverlayModel(hud=('HP 90 | minute 720',),message='Ready',footer='')
            first=overlay.draw(model)
            uploads=overlay.renderer.bank.uploads
            overlay.draw(model)
            self.assertEqual(overlay.renderer.bank.uploads,uploads)
            self.assertEqual(first,build_layout(640,480,model))
            self.assertFalse(any(event[0]=='clear' for event in context.events))
            a=overlay._text_source(TextRun('one','Changed vitals',(0,0,200,22)))
            b=overlay._text_source(TextRun('two','Changed vitals',(0,0,200,22)))
            c=overlay._text_source(TextRun('one','Changed vitals 2',(0,0,200,22)))
            self.assertEqual(a,b)
            self.assertNotEqual(a[0],c[0])
            for index in range(350):
                overlay.draw(replace(model,message=(f'Update {index:04d} authorized message '*5)))
            self.assertLessEqual(len(overlay._cache),MAX_TEXT_CACHE)
            self.assertLessEqual(overlay.cache_bytes,MAX_TEXT_CACHE_BYTES)
            self.assertLessEqual(overlay.renderer.bank.bytes,UI_TEXTURE_BUDGET)
            self.assertGreater(overlay.renderer.bank.evictions,0)
            overlay.resize(800,600)
            self.assertEqual((overlay.width,overlay.height),(800,600))
            overlay.close();overlay.close()
            self.assertEqual(overlay.cache_bytes,0)
            self.assertTrue(all(texture.released==1 for texture in context.textures))
            with self.assertRaises(RuntimeError):overlay.draw(model)

    def test_actual_egl_overlay_draws_text_without_clearing_background(self):
        try:
            import moderngl
        except ImportError:
            self.skipTest('optional ModernGL dependency unavailable')
        try:
            context=moderngl.create_standalone_context(require=330,backend='egl')
        except Exception as exc:
            self.skipTest(f'optional EGL unavailable: {type(exc).__name__}')
        texture=target=overlay=None
        try:
            width,height=640,480
            texture=context.texture((width,height),4)
            target=context.framebuffer(color_attachments=[texture])
            target.use();target.clear(.1,.2,.3,1.)
            before=target.read(components=4,alignment=1)
            overlay=GLGameplayUI(_OffscreenWindowContext(context,target),self.pg,width,height)
            overlay.draw(OverlayModel(hud=('HP 80/100 | minute 720',),footer=''))
            after=target.read(components=4,alignment=1)
            center=((height//2)*width+width//2)*4
            self.assertEqual(after[center:center+4],before[center:center+4])
            self.assertNotEqual(after,before)
            # Read actual glyph pixels, not merely the dark panel rectangle.
            self.assertTrue(any(after[index]>150 and after[index+1]>150
                for index in range((height-30)*width*4,len(after),4)))
        finally:
            if overlay is not None:overlay.close()
            if target is not None:target.release()
            if texture is not None:texture.release()
            context.release()


    def test_actual_egl_screenshots_read_resized_viewport(self):
        import tempfile
        from pathlib import Path
        from tools.worldseed_gpu_gameplay import _screenshot as gameplay_capture
        from tools.worldseed_gpu_playtest import _screenshot as preview_capture
        try:
            import moderngl
        except ImportError:
            self.skipTest('optional ModernGL dependency unavailable')
        try:
            context=moderngl.create_standalone_context(require=330,backend='egl')
        except Exception as exc:
            self.skipTest(f'optional EGL unavailable: {type(exc).__name__}')
        target=None
        try:
            target=context.simple_framebuffer((640,480))
            target.use()
            target.clear(1,0,0,1)
            target.clear(0,1,0,1,viewport=(0,0,320,120))
            window=SimpleNamespace(screen=target)
            with tempfile.TemporaryDirectory() as directory:
                for name,capture in (
                    ('gameplay',lambda path:gameplay_capture(self.pg,window,(320,240),path)),
                    ('preview',lambda path:preview_capture(self.pg,window,320,240,path)),
                ):
                    with self.subTest(capture=name):
                        path=Path(directory)/f'{name}.png'
                        capture(path)
                        image=self.pg.image.load(str(path))
                        self.assertEqual(image.get_size(),(320,240))
                        self.assertEqual(tuple(image.get_at((160,10)))[:3],(255,0,0))
                        self.assertEqual(tuple(image.get_at((160,230)))[:3],(0,255,0))
        finally:
            if target is not None:target.release()
            context.release()
