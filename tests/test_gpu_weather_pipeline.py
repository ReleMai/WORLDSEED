"""G5/G6 Windows GPU shading contracts; no fake claim of hardware validation."""
from __future__ import annotations
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from struct import unpack
from types import SimpleNamespace
from unittest.mock import patch
import sys
import unittest

from worldseed.presentation.gl_atmosphere import (
    AtmosphereFrame,GLAtmospherePass,WorldLight,daylight,weather_frame,
    MAX_FRAMEBUFFER_BYTES,MAX_LIGHTS,
)
from worldseed.presentation.gl_worldspace import (
    GLWorldspaceRenderer,SpriteCommand,vertex_bytes,GPUBackendUnavailable,
)

class GPUAtmosphereContracts(unittest.TestCase):
    def test_sunrise_wrap_midnight_and_evening(self):
        self.assertAlmostEqual(daylight(0),daylight(1440))
        self.assertGreater(daylight(720),daylight(0))
        self.assertGreater(daylight(720),daylight(1080))
        self.assertAlmostEqual(daylight(960),daylight(-480))
        self.assertTrue(all(.18 <= daylight(m) <= 1 for m in range(-3600,3600,90)))

    def test_weather_is_visual_only_and_bounded(self):
        raw={'rain':70,'fog':43,'cloud_cover':89,'wind_dx':1,'wind_dy':-1,'kind':'storm'}
        copy=dict(raw)
        frame=weather_frame(raw,minute=800,elapsed_seconds=2.5)
        self.assertEqual(raw,copy)
        self.assertEqual((frame.rain,frame.fog,frame.cloud),(.7,.43,.89))
        winter=weather_frame(dict(raw,kind='snow'),minute=0,elapsed_seconds=9)
        self.assertEqual((winter.rain,winter.snow),(0,.7))
        with self.assertRaises(FrozenInstanceError):frame.rain=0.0

    def test_light_validation_no_overrun_or_bad_clock(self):
        for value in (float('nan'),float('inf'),-1,3000):
            with self.subTest(value=value),self.assertRaises(ValueError):WorldLight(0,0,value,.8)
        with self.assertRaises(ValueError):AtmosphereFrame(0,rain=1,snow=.5)
        with self.assertRaises(ValueError):AtmosphereFrame(0,wind_x=float('inf'))
        with self.assertRaises(ValueError):AtmosphereFrame(0,lights=(WorldLight(0,0,5,.2),)*(MAX_LIGHTS+1))
        with self.assertRaises(ValueError):AtmosphereFrame(0,elapsed_seconds=-1)
        with self.assertRaises(ValueError):daylight(0.2)

    def test_post_shaders_contain_actual_multiscale_world_weather(self):
        root=Path(__file__).resolve().parents[1]/'worldseed/assets/shaders'
        v=(root/'worldspace_post.vert').read_text()
        f=(root/'worldspace_post.frag').read_text()
        self.assertIn('#version 330',v)
        for marker in ('u_world_origin','u_sun','u_light_posrad[8]','u_light_color[8]',
                       'cloudField','rainStreak','snowFlake','u_fog','u_scene',
                       'smoothNoise','smoothstep'):
            self.assertIn(marker,f)
        self.assertNotIn('gl_FragColor',f)
        self.assertIn('u_sway_px',(root/'worldspace_sprite.vert').read_text())
        sprite=(root/'worldspace_sprite.frag').read_text()
        self.assertIn('texture(u_texture, v_uv)',sprite)
        self.assertNotIn('1.0 - v_uv.y',sprite)

class Uniform:
    def __init__(self):self.value=None;self.data=None
    def write(self,data):self.data=data
class Program(dict):
    def __missing__(self,key):self[key]=Uniform();return self[key]
    def release(self):pass
class Releasable:
    def __init__(self):self.count=0
    def write(self,data):self.data=data
    def release(self):self.count+=1
class Texture(Releasable):
    def __init__(self):super().__init__();self.uses=0
    def use(self,location):self.uses+=1
class Target(Releasable):
    def __init__(self):super().__init__();self.uses=0;self.clear_calls=[]
    def use(self):self.uses+=1
    def clear(self,*values):self.clear_calls.append(values)
class VAO(Releasable):
    def __init__(self):super().__init__();self.vertices=[]
    def render(self,vertices):self.vertices.append(vertices)
class FakeGL:
    def __init__(self):
        self.program_obj=Program();self.vbo=Releasable();self.vao=VAO();self.texture_objs=[];self.targets=[]
        self.programs=[];self.vaos=[]
        self.screen=Target();self.viewport=None;self.scissor=None;self.disabled=[]
    def program(self,**kwargs):
        self.shaders=kwargs
        program=self.program_obj if not self.programs else Program()
        self.programs.append(program)
        return program
    def buffer(self,*args,**kwargs):return self.vbo
    def vertex_array(self,*args,**kwargs):
        vao=self.vao if not self.vaos else VAO()
        self.vaos.append(vao)
        return vao
    def texture(self,size,components,data=None):
        tex=Texture();tex.repeat_x=True;tex.repeat_y=True
        tex.components=components
        self.texture_objs.append((size,tex));return tex
    def framebuffer(self,*,color_attachments):
        tar=Target();self.targets.append(tar);return tar
    def disable(self,flag):self.disabled.append(flag)
    def enable_only(self,*args):pass
    def clear(self,*args):pass

class GPUTargetContracts(unittest.TestCase):
    def test_one_window_bounded_scene_and_cover_fbos_without_readback(self):
        gl=FakeGL()
        with patch.dict(sys.modules,{'moderngl':SimpleNamespace(BLEND=1,SRC_ALPHA=2,ONE_MINUS_SRC_ALPHA=3)}):
            post=GLAtmospherePass(gl,640,480)
            self.assertEqual(gl.texture_objs[0][0],(640,480))
            self.assertEqual(len(gl.targets),2)
            self.assertEqual([tex.components for _,tex in gl.texture_objs],[4,1])
            self.assertEqual(gl.targets[1].clear_calls,[(0.,0.,0.,0.)])
            self.assertEqual(len(gl.shaders),2)
            self.assertFalse(hasattr(gl,'read'))
            frame=AtmosphereFrame(1080,rain=.7,fog=.8,wind_x=.3,lights=(WorldLight(70,90,55,1.),))
            post.present(frame)
            p=gl.program_obj
            self.assertEqual(p['u_light_count'].value,1)
            self.assertEqual(len(p['u_light_posrad'].data),128)
            self.assertEqual(len(p['u_light_color'].data),96)
            self.assertEqual(unpack('<4f',p['u_light_posrad'].data[:16]),(70.,90.,55.,1.))
            self.assertEqual(gl.vao.vertices,[6])
            self.assertEqual(gl.screen.uses,1)
            self.assertFalse(p['u_cover_enabled'].value)
            self.assertEqual(p['u_cover'].value,1)
            post.clear_cover()
            self.assertEqual(gl.targets[1].uses,1)
            post.present(frame,cover_enabled=True)
            self.assertTrue(p['u_cover_enabled'].value)
            post.resize(800,600)
            self.assertEqual(gl.targets[0].count,1)
            self.assertEqual(gl.texture_objs[0][1].count,1)
            self.assertEqual(gl.targets[1].count,1)
            self.assertEqual(gl.texture_objs[1][1].count,1)
            self.assertEqual(gl.targets[-1].clear_calls,[(0.,0.,0.,0.)])
            post.close()
            self.assertTrue(all(item.count==1 for item in gl.targets))
            self.assertTrue(all(item.count==1 for _,item in gl.texture_objs))
            with self.assertRaises(GPUBackendUnavailable):post.present(frame)

    def test_fbo_rejects_giant_output_without_discarding_valid_state(self):
        gl=FakeGL();post=GLAtmospherePass(gl,1280,720)
        with self.assertRaises(ValueError):post.resize(4000,3000)
        self.assertEqual((post.width,post.height),(1280,720))
        with self.assertRaises(ValueError):post.resize(0,720)
        post.close()

    def test_sprite_pass_target_and_sway_do_not_change_existing_contract(self):
        gl=FakeGL()
        with patch.dict(sys.modules,{'moderngl':SimpleNamespace(BLEND=1,SRC_ALPHA=2,ONE_MINUS_SRC_ALPHA=3)}):
            renderer=GLWorldspaceRenderer(gl,640,480)
            target=Target()
            cmd=SpriteCommand('oak:crown','oak',1,b'\xff'*64,4,4,(10,20,30,40),((0,0,640,480),),sway_px=3.)
            report=renderer.draw((cmd,),target=target,frame_time_seconds=2.7)
            self.assertEqual((report.draw_calls,target.uses,gl.screen.uses),(1,1,0))
            self.assertEqual(gl.program_obj['u_sway_px'].value,3.)
            self.assertEqual(gl.program_obj['u_time'].value,2.7)
            with self.assertRaises(ValueError):SpriteCommand('i','t',1,b'\xff'*64,4,4,(0,0,4,4),((0,0,4,4),),sway_px=7.)
            renderer.close()

    def test_cover_pass_filters_memory_and_uses_separate_lazy_program(self):
        gl=FakeGL()
        with patch.dict(sys.modules,{'moderngl':SimpleNamespace(BLEND=1,SRC_ALPHA=2,ONE_MINUS_SRC_ALPHA=3)}):
            renderer=GLWorldspaceRenderer(gl,640,480)
            self.addCleanup(renderer.close)
            self.assertIsNone(renderer._cover_program)
            cover=SpriteCommand('oak:crown','oak',1,b'\xff'*64,4,4,(10,20,30,40),
                ((0,0,640,480),),opacity=.1,local_alpha=.08,fade_radius=30,
                precipitation_cover=True)
            rows=(cover,replace(cover,visual_id='remembered:crown',remembered=True),
                  replace(cover,visual_id='trunk',precipitation_cover=False))
            report=renderer.draw(rows,target=Target(),coverage_only=True)
            self.assertEqual((report.sprites,report.draw_calls),(1,1))
            self.assertIsNot(renderer._cover_program,renderer.program)
            self.assertEqual(set(renderer._cover_program),{'u_viewport','u_texture','u_time','u_sway_px'})
            self.assertNotIn('u_ground',renderer._cover_program)
            renderer.draw((cover,),target=Target())
            self.assertNotIn('u_coverage_only',renderer.program)
            self.assertEqual(len(gl.programs),2)
            with self.assertRaises(ValueError):replace(cover,precipitation_cover=1)
            with self.assertRaises(ValueError):renderer.draw(rows,coverage_only=1)

    def test_failed_cover_allocation_keeps_previous_targets_usable(self):
        gl=FakeGL();post=GLAtmospherePass(gl,640,480)
        self.addCleanup(post.close)
        previous=(post.scene_color,post.scene_target,post.cover_color,post.cover_target)
        allocate=gl.texture
        def fail_cover(size,components,data=None):
            if components==1:raise RuntimeError('cover allocation failed')
            return allocate(size,components,data)
        with patch.object(gl,'texture',side_effect=fail_cover):
            with self.assertRaises(GPUBackendUnavailable):post.resize(800,600)
        self.assertEqual((post.width,post.height),(640,480))
        self.assertEqual((post.scene_color,post.scene_target,post.cover_color,post.cover_target),previous)
        self.assertTrue(all(item.count==0 for item in previous))
        self.assertEqual(gl.texture_objs[-1][1].count,1)
        self.assertEqual(gl.targets[-1].count,1)

    def test_static_cover_fragments_batch_within_vbo_budget_but_sway_keeps_scissors(self):
        gl=FakeGL()
        with patch.dict(sys.modules,{'moderngl':SimpleNamespace(BLEND=1,SRC_ALPHA=2,ONE_MINUS_SRC_ALPHA=3)}):
            renderer=GLWorldspaceRenderer(gl,640,480)
            self.addCleanup(renderer.close)
            clips=tuple((float(x),0.,float(x+1),4.) for x in range(130))
            roof=SpriteCommand('roof','roof',1,b'\xff'*4,1,1,(0.,0.,130.,4.),clips,
                               precipitation_cover=True)
            static=renderer.draw((roof,),target=Target(),coverage_only=True)
            self.assertEqual((static.scissor_regions,static.draw_calls),(130,3))
            self.assertTrue(all(vertices<=6*64 for vertices in renderer._cover_vao.vertices))
            swaying=renderer.draw((replace(roof,sway_px=2.),),target=Target(),coverage_only=True)
            self.assertEqual((swaying.scissor_regions,swaying.draw_calls),(130,130))

    def test_failed_lazy_cover_vao_releases_partial_program_and_keeps_main_pass(self):
        gl=FakeGL()
        with patch.dict(sys.modules,{'moderngl':SimpleNamespace(BLEND=1,SRC_ALPHA=2,ONE_MINUS_SRC_ALPHA=3)}):
            renderer=GLWorldspaceRenderer(gl,640,480)
            self.addCleanup(renderer.close)
            failed=Releasable()
            with patch.object(gl,'program',return_value=failed), \
                    patch.object(gl,'vertex_array',side_effect=RuntimeError('cover VAO failed')):
                with self.assertRaises(GPUBackendUnavailable):renderer._ensure_cover_program()
            self.assertEqual(failed.count,1)
            self.assertIsNone(renderer._cover_program)
            self.assertIsNone(renderer._cover_vao)
            cmd=SpriteCommand('plain','t',1,b'\xff'*4,1,1,(0,0,4,4),((0,0,4,4),))
            self.assertEqual(renderer.draw((cmd,),target=Target()).draw_calls,1)

if __name__=='__main__':unittest.main()
