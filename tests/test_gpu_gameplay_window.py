"""Single GPU window ownership with real prepared gameplay and fake SDL/GL.

These loop tests deliberately provide no native GPU or performance evidence.
"""
from __future__ import annotations

from contextlib import ExitStack, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import time
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tools import worldseed_gpu_gameplay as gameplay
from tools.reference_scene_fixtures import build_fixture
from worldseed.presentation.gl_gameplay_ui import build_layout
from worldseed.presentation.gl_worldspace import FrameReport
from worldseed.sim.commands import MoveCommand
from worldseed.ui.gpu_gameplay_input import GpuGameplayInput


class GPUWindowLoopTests(unittest.TestCase):
    def fake_backends(self, order, *, fail_draw=False, event_frames=None):
        import pygame as raster
        pg=ModuleType('pygame')
        # Sight-mask preparation now uses real CPU pixels. Keep the window,
        # events and GL context fake while exercising those raster operations.
        for name in ('Surface', 'SRCALPHA', 'draw', 'transform', 'image'):
            setattr(pg, name, getattr(raster, name))
        names=('GL_CONTEXT_MAJOR_VERSION','GL_CONTEXT_MINOR_VERSION',
            'GL_CONTEXT_PROFILE_MASK','GL_CONTEXT_PROFILE_CORE','GL_DOUBLEBUFFER',
            'DOUBLEBUF','OPENGL','RESIZABLE','QUIT','WINDOWFOCUSLOST',
            'WINDOWFOCUSGAINED','VIDEORESIZE','KEYUP','KEYDOWN','MOUSEMOTION',
            'K_UP','K_DOWN','K_LEFT','K_RIGHT','K_w','K_a','K_s','K_d',
            'K_PERIOD','K_p','K_RETURN','K_TAB','K_ESCAPE','K_F12','KMOD_SHIFT',
            'K_g','K_i','K_f','K_PAGEUP','K_PAGEDOWN','MOUSEWHEEL','MOUSEBUTTONDOWN')
        for index,name in enumerate(names,1):setattr(pg,name,1<<index)
        pg.init=Mock()
        pg.quit=Mock(side_effect=lambda:order.append('quit'))
        pg.display=SimpleNamespace(gl_set_attribute=Mock(),
            set_mode=Mock(side_effect=lambda *args:order.append('window')),
            set_caption=Mock(),flip=Mock())
        pg.key=SimpleNamespace(set_repeat=Mock(),get_mods=lambda:0)
        clock=SimpleNamespace(tick=Mock())
        pg.time=SimpleNamespace(Clock=lambda:clock)
        default_events=(
            [SimpleNamespace(type=pg.KEYDOWN,key=pg.K_d,repeat=False),
             SimpleNamespace(type=pg.KEYDOWN,key=pg.K_d,repeat=True),
             SimpleNamespace(type=pg.KEYDOWN,key=pg.K_d,repeat=False)],
            [SimpleNamespace(type=pg.KEYUP,key=pg.K_d)])
        events=iter(event_frames(pg) if event_frames is not None else default_events)
        def event_get():
            order.append('events')
            return next(events)
        pg.event=SimpleNamespace(get=Mock(side_effect=event_get))
        ctx=SimpleNamespace(info={'GL_VENDOR':'fake','GL_RENDERER':'test-double',
                                  'GL_VERSION':'3.3-fake'},
                            screen=SimpleNamespace(clear=Mock()))
        gl=ModuleType('moderngl')
        gl.create_context=Mock(return_value=ctx)
        report=FrameReport(1,1,2,1,0,4,1)
        def draw(commands,**kwargs):
            order.append('draw')
            self.assertTrue(commands)
            self.assertEqual(kwargs['clear'],(0.,0.,0.,0.))
            if fail_draw:raise RuntimeError('injected draw failure')
            return report
        renderer=SimpleNamespace(draw=Mock(side_effect=draw),resize=Mock(),
            close=Mock(side_effect=lambda:order.append('renderer-close')))
        post=SimpleNamespace(scene_target=object(),resize=Mock(),
            present=Mock(side_effect=lambda fx:order.append('present')),
            close=Mock(side_effect=lambda:order.append('post-close')))
        overlay_models=[]
        def overlay_draw(model):
            order.append('overlay')
            overlay_models.append(model)
            return build_layout(640,480,model)
        overlay=SimpleNamespace(draw=Mock(side_effect=overlay_draw),resize=Mock(),models=overlay_models,
            close=Mock(side_effect=lambda:order.append('overlay-close')))
        class Materials:
            def asset(self,path):return (str(path),1,b'\x70\x90\x44\xff',1,1)
            def player(self):return self.asset('player')
            def actor(self,content_id):return self.asset(content_id)
            def tree(self,species,layer,season):return self.asset(f'{species}:{layer}:{season}')
        return pg,gl,renderer,post,Materials(),clock,overlay

    def exercise_loop(self, *, fail_draw=False, report=None, event_frames=None, frames=2):
        order=[]
        pg,gl,renderer,post,materials,clock,overlay=self.fake_backends(
            order,fail_draw=fail_draw,event_frames=event_frames)
        observed=SimpleNamespace(fixture=None,controller=None,moves=[],updates=[],snapshots=[],
                                 commands=[],fixture_closed=False,overlay=overlay)
        def fixture_factory(*args,**kwargs):
            fixture=build_fixture(*args,**kwargs)
            observed.fixture=fixture
            sim=fixture.sim
            # One held update crosses a real prepared tile; release must prevent
            # a second move, rather than merely leaving both frames in one tile.
            sim.state.player_fx=.95
            move=sim._move
            def record_move(command,*args,**kwargs):
                observed.moves.append(command)
                return move(command,*args,**kwargs)
            sim._move=record_move
            execute=sim.execute
            def record_execute(command,*args,**kwargs):
                observed.commands.append(command)
                return execute(command,*args,**kwargs)
            sim.execute=record_execute
            close=fixture.close
            def record_fixture_close():
                observed.fixture_closed=True
                order.append('fixture-close')
                close()
            fixture.close=record_fixture_close
            return fixture
        def controller_factory(sim):
            control=GpuGameplayInput(sim,now=0.)
            observed.controller=control
            update=control.update
            close=control.close
            def record_update(now,**kwargs):
                order.append('update')
                result=update(now,**kwargs)
                observed.updates.append((sim.player_pos,sim.state.player_fx))
                return result
            def record_close():
                order.append('controller-close')
                close()
            control.update=record_update
            control.close=record_close
            return control
        capture=gameplay.capture_live_scene
        def record_capture(sim,camera):
            order.append('capture')
            snapshot=capture(sim,camera)
            observed.snapshots.append(snapshot)
            return snapshot
        ticks=iter([0.,*(value for index in range(frames)
                        for value in (.1+index*.1,.15+index*.1))])
        fake_time=SimpleNamespace(monotonic=lambda:next(ticks),perf_counter=time.perf_counter)
        with ExitStack() as stack:
            stack.enter_context(patch.dict(sys.modules,{'pygame':pg,'moderngl':gl}))
            stack.enter_context(patch.dict(gameplay.os.environ,{'SDL_VIDEODRIVER':'gpu-loop-test'}))
            stack.enter_context(patch.object(gameplay,'time',fake_time))
            stack.enter_context(patch.object(gameplay,'GLWorldspaceRenderer',return_value=renderer))
            stack.enter_context(patch.object(gameplay,'GLAtmospherePass',return_value=post))
            stack.enter_context(patch.object(gameplay,'GLGameplayUI',return_value=overlay))
            observed.context_loader=stack.enter_context(patch.object(gameplay,'create_sdl_context',
                side_effect=lambda pg,**kwargs:gl.create_context(require=330)))
            stack.enter_context(patch.object(gameplay,'GpuMaterialSource',return_value=materials))
            stack.enter_context(patch.object(gameplay,'GpuGameplayInput',side_effect=controller_factory))
            stack.enter_context(patch.object(gameplay,'capture_live_scene',side_effect=record_capture))
            stack.enter_context(patch('tools.reference_scene_fixtures.build_fixture',side_effect=fixture_factory))
            if fail_draw:
                with self.assertRaisesRegex(RuntimeError,'injected draw failure'):
                    gameplay.run(width=640,height=480,frames=frames,prepared_scene='camp')
                result=None
            else:
                result=gameplay.run(width=640,height=480,frames=frames,prepared_scene='camp',report=report)
        self.assertEqual(pg.display.set_mode.call_count,1)
        self.assertEqual(pg.init.call_count,1)
        self.assertEqual(pg.quit.call_count,1)
        self.assertEqual(gl.create_context.call_count,1)
        observed.context_loader.assert_called_once_with(pg,
            diagnostics=Path(report).with_suffix('.context.json') if report else None)
        self.assertTrue(observed.fixture_closed)
        self.assertTrue(observed.controller.closed)
        self.assertFalse(observed.controller.sim.npcs.continuous_motion_enabled)
        post.close.assert_called_once()
        renderer.close.assert_called_once()
        overlay.close.assert_called_once()
        self.assertEqual(order[-6:],['controller-close','overlay-close','post-close','renderer-close','quit','fixture-close'])
        return result,observed,order,pg,renderer,post,clock

    def test_two_frames_own_one_window_and_update_before_capture_and_draw(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'loop-report.json'
            result,observed,order,pg,renderer,post,clock=self.exercise_loop(report=path)
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')),result)
        self.assertEqual(pg.event.get.call_count,2)
        self.assertEqual(renderer.draw.call_count,2)
        self.assertEqual(post.present.call_count,2)
        self.assertEqual(observed.overlay.draw.call_count,2)
        self.assertEqual(pg.display.flip.call_count,3)  # startup plus two frames
        for call in renderer.draw.call_args_list:
            self.assertIs(call.kwargs['target'],post.scene_target)
        self.assertEqual(clock.tick.call_count,2)
        phases=[item for item in order if item in ('events','update','capture','draw','present','overlay')]
        self.assertEqual(phases,['events','update','capture','draw','present','overlay']*2)
        self.assertEqual(len(observed.moves),1)
        self.assertIsInstance(observed.moves[0],MoveCommand)
        self.assertEqual((observed.moves[0].dx,observed.moves[0].dy),(1,0))
        self.assertEqual(observed.updates[0],observed.updates[1])
        for snapshot,(pos,fraction) in zip(observed.snapshots,observed.updates):
            self.assertAlmostEqual(snapshot.viewer.x,pos.x+fraction)
        self.assertEqual(result['frames'],2)
        self.assertEqual(result['source'],'prepared-synthetic-camp')
        self.assertFalse(result['player_saves_opened'])
        self.assertEqual(result['final_position']['x'],result['initial_position']['x']+1)
        self.assertEqual(result['final_minute'],result['initial_minute'])
        self.assertEqual(result['gpu']['GL_RENDERER'],'test-double')
        self.assertGreater(result['current_cells'],0)
        self.assertEqual(result['last_frame']['draw_calls'],1)
        self.assertIsNotNone(result['render_submit_p95_ms'])
        self.assertIn('not-production',result['status'])
        self.assertIn('not GPU completion',result['limitations'])
        self.assertTrue(all(model.hud and model.target for model in observed.overlay.models))

    def test_mouse_selects_admitted_cell_then_opens_action_hub_without_commands(self):
        def events(pg):
            return ([],[SimpleNamespace(type=pg.MOUSEBUTTONDOWN,button=1,pos=(320,240))],
                    [SimpleNamespace(type=pg.MOUSEBUTTONDOWN,button=3,pos=(320,240))])
        result,observed,order,pg,renderer,post,clock=self.exercise_loop(event_frames=events,frames=3)
        self.assertEqual(pg.event.get.call_count,3)
        self.assertEqual(renderer.draw.call_count,3)
        self.assertEqual(observed.overlay.draw.call_count,3)
        self.assertEqual(observed.commands,[])
        self.assertEqual(observed.moves,[])
        self.assertEqual(result['initial_position'],result['final_position'])
        self.assertEqual(result['initial_minute'],result['final_minute'])
        first,selected,actions=observed.overlay.models
        self.assertEqual(first.panel_title,'')
        self.assertEqual(first.target,'Select a visible cell')
        self.assertEqual(selected.target,'Selected (256, 256, 0)')
        self.assertIn((256,256,0),observed.snapshots[0].current_cells)
        self.assertEqual(actions.panel_title,'Actions')
        self.assertTrue(actions.rows)
        self.assertEqual(actions.target,selected.target)
        # Opening a modal stops the controller update; its draw remains after
        # the authorized world and atmosphere in the same presentation frame.
        self.assertEqual(len(observed.updates),2)
        phases=[item for item in order if item in ('events','update','capture','draw','present','overlay')]
        self.assertEqual(phases,['events','update','capture','draw','present','overlay']*2+
            ['events','capture','draw','present','overlay'])

    def test_draw_failure_closes_input_gpu_window_and_fixture(self):
        result,observed,order,pg,renderer,post,clock=self.exercise_loop(fail_draw=True)
        self.assertIsNone(result)
        self.assertEqual(pg.event.get.call_count,1)
        self.assertEqual(renderer.draw.call_count,1)
        self.assertEqual(len(observed.snapshots),1)
        post.present.assert_not_called()
        observed.overlay.draw.assert_not_called()
        clock.tick.assert_not_called()

    def test_close_event_stops_queued_commands_and_simulation_before_draw(self):
        def events(pg):
            return ([SimpleNamespace(type=pg.QUIT),
                     SimpleNamespace(type=pg.KEYDOWN,key=pg.K_PERIOD,repeat=False),
                     SimpleNamespace(type=pg.KEYDOWN,key=pg.K_p,repeat=False)],)
        result,observed,order,pg,renderer,post,clock=self.exercise_loop(event_frames=events)
        self.assertEqual(result['frames'],0)
        self.assertEqual(observed.commands,[])
        self.assertEqual(observed.updates,[])
        self.assertEqual(result['initial_minute'],result['final_minute'])
        self.assertEqual(pg.event.get.call_count,1)
        renderer.draw.assert_not_called()
        post.present.assert_not_called()

    def test_resize_uses_actual_small_viewport_without_a_second_window(self):
        def events(pg):
            return ([],[SimpleNamespace(type=pg.VIDEORESIZE,w=320,h=240)])
        result,observed,order,pg,renderer,post,clock=self.exercise_loop(event_frames=events)
        self.assertEqual(result['size'],[320,240])
        renderer.resize.assert_called_once_with(320,240)
        post.resize.assert_called_once_with(320,240)
        observed.overlay.resize.assert_called_once_with(320,240)
        self.assertEqual((observed.snapshots[-1].camera.width_px,
                          observed.snapshots[-1].camera.height_px),(320,240))
        self.assertEqual(pg.display.set_mode.call_count,1)

    def test_invalid_cli_bounds_fail_before_fixture_or_normal_world_startup(self):
        with patch.dict(gameplay.os.environ,{'SDL_VIDEODRIVER':'gpu-loop-test'}), \
             patch('tools.reference_scene_fixtures.build_fixture') as fixture, \
             patch('worldseed.app._load_context') as startup, \
             patch.object(gameplay,'create_sdl_context') as gl_startup:
            for args in (('--size','639x480'),('--size','640x479'),
                         ('--size','1921x1080'),('--zoom','19'),('--zoom','57'),
                         ('--frames','-1'),('--frames','36001'),('--seed','')):
                with self.subTest(args=args),redirect_stdout(StringIO()) as output:
                    self.assertEqual(gameplay.main([*args,'--prepared-scene','camp']),1)
                    self.assertEqual(json.loads(output.getvalue())['status'],'gpu-gameplay-unavailable')
            fixture.assert_not_called()
            startup.assert_not_called()
            gl_startup.assert_not_called()
