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
from worldseed.presentation.gl_worldspace import FrameReport
from worldseed.sim.commands import MoveCommand
from worldseed.ui.gpu_gameplay_input import GpuGameplayInput


class GPUWindowLoopTests(unittest.TestCase):
    def fake_backends(self, order, *, fail_draw=False):
        pg=ModuleType('pygame')
        names=('GL_CONTEXT_MAJOR_VERSION','GL_CONTEXT_MINOR_VERSION',
            'GL_CONTEXT_PROFILE_MASK','GL_CONTEXT_PROFILE_CORE','GL_DOUBLEBUFFER',
            'DOUBLEBUF','OPENGL','RESIZABLE','QUIT','WINDOWFOCUSLOST',
            'WINDOWFOCUSGAINED','VIDEORESIZE','KEYUP','KEYDOWN','MOUSEMOTION',
            'K_UP','K_DOWN','K_LEFT','K_RIGHT','K_w','K_a','K_s','K_d',
            'K_PERIOD','K_p','K_RETURN','K_TAB','K_ESCAPE','K_F12','KMOD_SHIFT')
        for index,name in enumerate(names,1):setattr(pg,name,1<<index)
        pg.init=Mock()
        pg.quit=Mock(side_effect=lambda:order.append('quit'))
        pg.display=SimpleNamespace(gl_set_attribute=Mock(),
            set_mode=Mock(side_effect=lambda *args:order.append('window')),
            set_caption=Mock(),flip=Mock())
        pg.key=SimpleNamespace(set_repeat=Mock(),get_mods=lambda:0)
        clock=SimpleNamespace(tick=Mock())
        pg.time=SimpleNamespace(Clock=lambda:clock)
        events=iter((
            [SimpleNamespace(type=pg.KEYDOWN,key=pg.K_d,repeat=False),
             SimpleNamespace(type=pg.KEYDOWN,key=pg.K_d,repeat=True),
             SimpleNamespace(type=pg.KEYDOWN,key=pg.K_d,repeat=False)],
            [SimpleNamespace(type=pg.KEYUP,key=pg.K_d)]))
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
        class Materials:
            def asset(self,path):return (str(path),1,b'\x70\x90\x44\xff',1,1)
            def player(self):return self.asset('player')
            def actor(self,content_id):return self.asset(content_id)
            def tree(self,species,layer,season):return self.asset(f'{species}:{layer}:{season}')
        return pg,gl,renderer,post,Materials(),clock

    def exercise_loop(self, *, fail_draw=False, report=None):
        order=[]
        pg,gl,renderer,post,materials,clock=self.fake_backends(order,fail_draw=fail_draw)
        observed=SimpleNamespace(fixture=None,controller=None,moves=[],updates=[],snapshots=[],
                                 fixture_closed=False)
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
        ticks=iter((0.,.1,.15,.2,.25))
        fake_time=SimpleNamespace(monotonic=lambda:next(ticks),perf_counter=time.perf_counter)
        with ExitStack() as stack:
            stack.enter_context(patch.dict(sys.modules,{'pygame':pg,'moderngl':gl}))
            stack.enter_context(patch.dict(gameplay.os.environ,{'SDL_VIDEODRIVER':'gpu-loop-test'}))
            stack.enter_context(patch.object(gameplay,'time',fake_time))
            stack.enter_context(patch.object(gameplay,'GLWorldspaceRenderer',return_value=renderer))
            stack.enter_context(patch.object(gameplay,'GLAtmospherePass',return_value=post))
            stack.enter_context(patch.object(gameplay,'GpuMaterialSource',return_value=materials))
            stack.enter_context(patch.object(gameplay,'GpuGameplayInput',side_effect=controller_factory))
            stack.enter_context(patch.object(gameplay,'capture_live_scene',side_effect=record_capture))
            stack.enter_context(patch('tools.reference_scene_fixtures.build_fixture',side_effect=fixture_factory))
            if fail_draw:
                with self.assertRaisesRegex(RuntimeError,'injected draw failure'):
                    gameplay.run(width=640,height=480,frames=2,prepared_scene='camp')
                result=None
            else:
                result=gameplay.run(width=640,height=480,frames=2,prepared_scene='camp',report=report)
        self.assertEqual(pg.display.set_mode.call_count,1)
        self.assertEqual(pg.init.call_count,1)
        self.assertEqual(pg.quit.call_count,1)
        self.assertEqual(gl.create_context.call_count,1)
        self.assertTrue(observed.fixture_closed)
        self.assertTrue(observed.controller.closed)
        self.assertFalse(observed.controller.sim.npcs.continuous_motion_enabled)
        post.close.assert_called_once()
        renderer.close.assert_called_once()
        self.assertEqual(order[-5:],['controller-close','post-close','renderer-close','quit','fixture-close'])
        return result,observed,order,pg,renderer,post,clock

    def test_two_frames_own_one_window_and_update_before_capture_and_draw(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'loop-report.json'
            result,observed,order,pg,renderer,post,clock=self.exercise_loop(report=path)
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')),result)
        self.assertEqual(pg.event.get.call_count,2)
        self.assertEqual(renderer.draw.call_count,2)
        self.assertEqual(post.present.call_count,2)
        self.assertEqual(pg.display.flip.call_count,3)  # startup plus two frames
        for call in renderer.draw.call_args_list:
            self.assertIs(call.kwargs['target'],post.scene_target)
        self.assertEqual(clock.tick.call_count,2)
        phases=[item for item in order if item in ('events','update','capture','draw','present')]
        self.assertEqual(phases,['events','update','capture','draw','present']*2)
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

    def test_draw_failure_closes_input_gpu_window_and_fixture(self):
        result,observed,order,pg,renderer,post,clock=self.exercise_loop(fail_draw=True)
        self.assertIsNone(result)
        self.assertEqual(pg.event.get.call_count,1)
        self.assertEqual(renderer.draw.call_count,1)
        self.assertEqual(len(observed.snapshots),1)
        post.present.assert_not_called()
        clock.tick.assert_not_called()

    def test_invalid_cli_bounds_fail_before_fixture_or_normal_world_startup(self):
        with patch.dict(gameplay.os.environ,{'SDL_VIDEODRIVER':'gpu-loop-test'}), \
             patch('tools.reference_scene_fixtures.build_fixture') as fixture, \
             patch('worldseed.app._load_context') as startup:
            for args in (('--size','639x480'),('--size','640x479'),
                         ('--size','1921x1080'),('--zoom','19'),('--zoom','57'),
                         ('--frames','-1'),('--frames','36001'),('--seed','')):
                with self.subTest(args=args),redirect_stdout(StringIO()) as output:
                    self.assertEqual(gameplay.main([*args,'--prepared-scene','camp']),1)
                    self.assertEqual(json.loads(output.getvalue())['status'],'gpu-gameplay-unavailable')
            fixture.assert_not_called()
            startup.assert_not_called()
