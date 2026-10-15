"""Optional real-GL FOW shader regression; EGL is not native Windows proof."""
from __future__ import annotations

import unittest

from worldseed.presentation.gl_atmosphere import (
    AtmosphereFrame, GLAtmospherePass, WorldLight,
)
from worldseed.presentation.gl_worldspace import GLWorldspaceRenderer, SpriteCommand


class _OffscreenWindowContext:
    """Route the compositor's window target to an owned test framebuffer."""
    def __init__(self,context,screen):
        object.__setattr__(self,'_context',context)
        object.__setattr__(self,'screen',screen)

    def __getattr__(self,name):
        return getattr(self._context,name)

    def __setattr__(self,name,value):
        setattr(self._context,name,value)


class GPUVisibilityShaderTests(unittest.TestCase):
    def test_atmosphere_preserves_unknown_black_pixels(self):
        try:
            import moderngl
        except ImportError:
            self.skipTest('optional ModernGL dependency unavailable')
        try:
            context=moderngl.create_standalone_context(require=330,backend='egl')
        except Exception as exc:
            self.skipTest(f'optional EGL OpenGL 3.3 driver unavailable: {type(exc).__name__}')

        width=height=64
        target=texture=atmosphere=renderer=None
        try:
            texture=context.texture((width,height),4)
            target=context.framebuffer(color_attachments=[texture])
            window=_OffscreenWindowContext(context,target)
            # These compile the actual repository shaders. A compile/draw
            # failure on an available GL context must fail this regression.
            atmosphere=GLAtmospherePass(window,width,height)
            renderer=GLWorldspaceRenderer(window,width,height,texture_budget=4096)
            tile=(20,16,36,28)
            command=SpriteCommand('authorized-tile','test:tile',1,
                                  b'\x60\xa0\x40\xff',1,1,tile,(tile,))
            for weather in ('rain','snow'):
                with self.subTest(weather=weather):
                    renderer.draw((command,),clear=(0,0,0,0),
                                  target=atmosphere.scene_target)
                    atmosphere.present(AtmosphereFrame(
                        minute=0,rain=float(weather=='rain'),
                        snow=float(weather=='snow'),fog=1.,cloud=1.,
                        wind_x=3.,wind_y=-2.,elapsed_seconds=17.25,
                        lights=(WorldLight(4.,4.,128.,2.),)))
                    pixels=target.read(components=4,alignment=1)
                    visible_pixels=0
                    for gl_y in range(height):
                        y=height-1-gl_y
                        for x in range(width):
                            offset=(gl_y*width+x)*4
                            rgb=pixels[offset:offset+3]
                            if tile[0]<=x<tile[2] and tile[1]<=y<tile[3]:
                                self.assertNotEqual(rgb,b'\0\0\0')
                                visible_pixels+=1
                            else:
                                self.assertEqual(rgb,b'\0\0\0',
                                                 f'{weather} revealed unknown pixel {(x,y)}')
                    self.assertEqual(visible_pixels,16*12)
        finally:
            if renderer is not None:renderer.close()
            if atmosphere is not None:atmosphere.close()
            if target is not None:target.release()
            if texture is not None:texture.release()
            context.release()


if __name__=='__main__':unittest.main()
