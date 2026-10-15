"""G4 art provenance + G8 shader backend pure contracts (no GL driver)."""
from __future__ import annotations
from collections import Counter
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from dataclasses import FrozenInstanceError
import struct
import sys
import unittest

from worldseed.presentation.gl_worldspace import (
    GLWorldspaceRenderer, SpriteCommand, TextureBank, GPUBackendUnavailable,
    commands_from_projected, pixel_clip, vertex_bytes,
)
from worldseed.presentation.tree_art import TREE_DIR, manifest,layer_png
from worldseed.presentation.worldspace import (
    WorldCamera,WorldFoot,VisualLayer,WorldVisualInstance,
    CoverRegion,SceneVisibility,project_scene,
)

RGBA=b'\xff\xa0\x10\xff'*16

def command(id='tree',clips=((0,0,4,4),),texid='oak',rev=1):
    return SpriteCommand(id,texid,rev,RGBA,4,4,(0,0,4,4),clips)

class TreeArtContract(unittest.TestCase):
    def test_layers_complete_rgba_transparent_and_hashed(self):
        catalog=manifest()
        self.assertEqual(len(catalog['entries']),12)
        self.assertEqual(catalog['premultiplied_alpha'],False)
        self.assertEqual({v['channel'] for v in catalog['entries'].values()}, {'trunk','crown','shadow'})
        unique=set()
        for species in ('oak','pine'):
            for channel in ('trunk','shadow'):
                with self.subTest(species=species,channel=channel):
                    self._inspect(layer_png(species,channel),catalog['entries'][species+':'+channel])
            for season in ('spring','summer','autumn','winter'):
                row=catalog['entries'][f'{species}:crown:{season}']
                data=layer_png(species,'crown',season)
                self._inspect(data,row)
                unique.add(sha256(data).hexdigest())
        self.assertEqual(len(unique),8)

    def _inspect(self,data,row):
        self.assertEqual(data[:8],b'\x89PNG\r\n\x1a\n')
        width,height,depth,mode=struct.unpack('>IIBB',data[16:26])
        self.assertEqual((width,height,depth,mode),(384,384,8,6))
        self.assertEqual(sha256(data).hexdigest(),row['sha256'])

    def test_invalid_channel_rejected_and_manifest_has_provenance(self):
        for triple in [('oak','../evil','summer'),('birch','trunk','summer'),('oak','crown','bad')]:
            with self.subTest(triple=triple),self.assertRaises(ValueError):
                layer_png(*triple)
        self.assertIn('build_worldspace_tree_art.py',manifest()['source'])
        self.assertIn('collision',manifest()['footprint_policy'])

class GPUContracts(unittest.TestCase):
    def test_invalid_sprite_bounds_memory_and_alpha_rejected(self):
        with self.assertRaises(ValueError):command(clips=[(0,0,4,4)])
        with self.assertRaises(ValueError):SpriteCommand('i','t',0,b'',4,4,(0,0,4,4),((0,0,4,4),))
        with self.assertRaises(ValueError):SpriteCommand('i','t',0,RGBA,4,4,(0,0,4,4),((0,0,4,4),),opacity=2)
        with self.assertRaises(ValueError):SpriteCommand('i','t',0,RGBA,4,4,(4,0,0,4),((0,0,4,4),))
        with self.assertRaises(FrozenInstanceError):command().revision=3

    def test_clipping_is_conservative_and_y_flipped(self):
        self.assertEqual(pixel_clip((1,1,8,5),10,10),(1,5,7,4))
        self.assertEqual(pixel_clip((-10,-10,2.9,2.9),10,10),(0,8,2,2))
        self.assertIsNone(pixel_clip((-3,2,0,9),10,10))
        self.assertIsNone(pixel_clip((3,4,3,9),10,10))
        # No FOW clips means no draw operations, even if material exists.
        self.assertEqual(command(clips=()).clip_rects,())

    def test_rectangle_vertices_exact_and_top_first(self):
        b=vertex_bytes((2,3,6,9))
        self.assertEqual(len(b),96)
        points=struct.unpack('<24f',b)
        self.assertEqual(points[:8],(2,3,0,0,6,3,1,0))
        self.assertEqual(points[-4:],(6,9,1,1))

    def test_shader_has_height_independent_screen_and_local_cutout(self):
        from worldseed.presentation.gl_worldspace import SHADER_DIR
        vert=(SHADER_DIR/'worldspace_sprite.vert').read_text()
        frag=(SHADER_DIR/'worldspace_sprite.frag').read_text()
        for key in ('#version 330','u_viewport','in_position','in_uv'):
            self.assertIn(key,vert)
        for key in ('#version 330','u_fade_center','u_local_alpha','texture(','smoothstep','u_opacity'):
            self.assertIn(key,frag)

    def test_authorized_projection_not_memory_is_adapted(self):
        vis=SceneVisibility(frozenset({(0,0,0),(1,0,0)}),frozenset({(2,0,0)}))
        c=WorldCamera(WorldFoot(1,1,0),100,100,30)
        items=[]
        for x in range(3):
            items.append(WorldVisualInstance(f'obj:{x}','core:oak_tree',WorldFoot(x+.5,.75),
                 .7,.75,.75,VisualLayer.GROUNDED,((x,0,0),) ))
        scene=project_scene(items,c,vis)
        cmds=commands_from_projected(scene,lambda v:(v.instance.content_id,1,RGBA,4,4))
        self.assertEqual(len(cmds),2)
        self.assertFalse(any(row.visual_id=='obj:2' for row in cmds))
        self.assertTrue(all(row.clip_rects for row in cmds))

class FakeTexture:
    def __init__(self):self.released=0;self.uses=[];self.repeat_x=True;self.repeat_y=True
    def use(self,location):self.uses.append(location)
    def release(self):self.released+=1
class FakeBuffer:
    def __init__(self):self.writes=[];self.released=0
    def write(self,data):self.writes.append(data)
    def release(self):self.released+=1
class FakeVAO:
    def __init__(self):self.rendered=[];self.released=0
    def render(self,vertices):self.rendered.append(vertices)
    def release(self):self.released+=1
class FakeUniform:
    def __init__(self):self.value=None
class FakeProgram(dict):
    def __missing__(self,key):self[key]=FakeUniform();return self[key]
    def release(self):pass
class FakeContext:
    def __init__(self):
        self.textures=[];self.viewport=None;self.scissor=None;self.screen=SimpleNamespace(use=lambda:None)
        self.program_obj=FakeProgram();self.buffer_obj=FakeBuffer();self.vao_obj=FakeVAO()
        self.events=[]
    def texture(self,size,components,rgba):
        self.events.append(('texture',size,components,len(rgba)))
        t=FakeTexture();self.textures.append(t);return t
    def program(self,**kw):return self.program_obj
    def buffer(self,**kw):return self.buffer_obj
    def vertex_array(self,*args):return self.vao_obj
    def enable_only(self,*args):pass
    def clear(self,*args):self.events.append(('clear',args))

class FakeRendererContracts(unittest.TestCase):
    def test_shader_draw_scissor_restore_and_cached_second_frame(self):
        ctx=FakeContext()
        with patch.dict(sys.modules,{'moderngl':SimpleNamespace(BLEND=1,SRC_ALPHA=2,ONE_MINUS_SRC_ALPHA=3)}):
            render=GLWorldspaceRenderer(ctx,200,100,texture_budget=4096)
            c=command(clips=((0,0,4,4),(1,1,4,4)))
            report=render.draw([c])
            self.assertEqual((report.draw_calls,report.textures_uploaded,report.textures_reused),(2,1,1))
            self.assertEqual(ctx.scissor,None)
            self.assertEqual(ctx.vao_obj.rendered,[6,6])
            report2=render.draw([c])
            self.assertEqual(report2.textures_uploaded,0)
            self.assertEqual(report2.textures_reused,2)
            render.resize(640,480)
            self.assertEqual(ctx.viewport,(0,0,200,100))  # deferred until next draw
            render.draw([c])
            self.assertEqual(ctx.viewport,(0,0,640,480))
            render.close()
            self.assertEqual(ctx.textures[0].released,1)
            with self.assertRaises(GPUBackendUnavailable):render.draw([c])

    def test_invalid_before_partial_frame_and_unseen_no_textures(self):
        ctx=FakeContext()
        with patch.dict(sys.modules,{'moderngl':SimpleNamespace(BLEND=1,SRC_ALPHA=2,ONE_MINUS_SRC_ALPHA=3)}):
            render=GLWorldspaceRenderer(ctx,100,100,texture_budget=4096)
            a=render.draw([command(clips=())]);self.assertEqual(a.draw_calls,0)
            self.assertEqual(len(ctx.textures),0)
            with self.assertRaises(ValueError):render.draw([command()]*4097)
            self.assertEqual(len(ctx.textures),0)
            render.close()

    def test_bounded_texture_bank_revisions_evict_and_release(self):
        c=FakeContext();b=TextureBank(c,4096)
        one=command(texid='oak',rev=1)
        t=b.texture_for(one)
        self.assertIs(t,b.texture_for(one))
        self.assertEqual(b.reuses,1)
        t2=b.texture_for(command(texid='oak',rev=2))
        self.assertIsNot(t2,t)
        self.assertEqual(b.uploads,2)
        b.close()
        self.assertEqual((t.released,t2.released),(1,1))

if __name__=='__main__':unittest.main()
