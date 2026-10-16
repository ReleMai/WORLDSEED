"""GPU indoor ground batching keeps the exact scissor admission and floor UV."""
from __future__ import annotations

from dataclasses import replace
from struct import unpack
from unittest import TestCase

from worldseed.presentation.gl_worldspace import (
    SpriteCommand, clipped_vertex_bytes, pixel_clip)


class InteriorFloorBatchTests(TestCase):
    def test_cropped_quad_uvs_remain_anchored_to_original_source(self):
        bounds=(12.,20.,52.,60.)
        region=pixel_clip((20.1,25.2,35.8,49.6),100,100)
        self.assertEqual(region,(20,50,16,25))
        vertices=unpack('<24f',clipped_vertex_bytes(bounds,region,100))
        a,b,c,d=20.,25.,36.,50.
        self.assertAlmostEqual(vertices[0],a)
        self.assertAlmostEqual(vertices[1],b)
        self.assertAlmostEqual(vertices[2],(a-bounds[0])/(bounds[2]-bounds[0]))
        self.assertAlmostEqual(vertices[3],(b-bounds[1])/(bounds[3]-bounds[1]))
        self.assertAlmostEqual(vertices[4],c)
        self.assertAlmostEqual(vertices[9],d)
        self.assertAlmostEqual(vertices[20],c)
        self.assertAlmostEqual(vertices[21],d)

    def test_empty_mesh_is_degenerate_and_never_paints_unrelated_cells(self):
        rect=clipped_vertex_bytes((1.,1.,2.,2.),(30,0,2,2),64)
        self.assertEqual(unpack('<24f',rect),(0.,)*24)

    def test_actual_gl_paints_same_pixels_with_fewer_floor_draw_calls(self):
        try:
            import moderngl
        except ImportError:
            self.skipTest('moderngl unavailable')
        try:
            context=moderngl.create_standalone_context(require=330,backend='egl')
        except Exception as exc:
            self.skipTest('optional EGL driver unavailable: '+type(exc).__name__)
        from tests.test_gpu_visibility_shader import _OffscreenWindowContext
        from worldseed.presentation.gl_worldspace import GLWorldspaceRenderer
        target=texture=renderer=None
        try:
            texture=context.texture((96,64),4)
            target=context.framebuffer(color_attachments=[texture])
            renderer=GLWorldspaceRenderer(_OffscreenWindowContext(context,target),96,64,
                                          texture_budget=4096)
            rgba=bytes((75,112,151,255))*4
            footprints=((11.125,8.25,31.125,28.25),
                        (35.125,8.25,55.125,28.25),
                        (59.125,8.25,79.125,28.25))
            masks=((12.1,10.1,30.9,26.7),
                   (36.3,9.7,53.8,27.2),
                   (60.7,10.9,77.3,26.8))
            original=tuple(SpriteCommand('unbatched:'+str(i),'floor-art',1,rgba,2,2,
                          bounds,(mask,)) for i,(bounds,mask) in enumerate(zip(footprints,masks)))
            baseline=renderer.draw(original,clear=(0.,0.,0.,0.))
            reference=target.read(components=4,alignment=1)
            batched=tuple(replace(command,visual_id='interior-floor:'+str(i))
                          for i,command in enumerate(original))
            result=renderer.draw(batched,clear=(0.,0.,0.,0.))
            self.assertEqual(reference,target.read(components=4,alignment=1))
            self.assertEqual(baseline.draw_calls,3)
            self.assertEqual(result.draw_calls,1)
        finally:
            if renderer is not None:renderer.close()
            if target is not None:target.release()
            if texture is not None:texture.release()
            context.release()
