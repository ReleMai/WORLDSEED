"""Failed checkpoints retain a live world and provide a paused retry route."""
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from worldseed import app
from worldseed.config import AUTOSAVE_TURNS
from worldseed.ui.pointer import WindowCloseRequested
from worldseed.ui.terminal import Terminal


class RecoveryTerminal(Terminal):
    def __init__(self,keys=()):
        super().__init__()
        self.keys=iter(keys)
        self.enter=Mock()
        self.restore=Mock()
        self.present_loading=Mock()

    def size(self):return 100,30

    def read_key(self):
        key=next(self.keys)
        return key() if callable(key) else key


def context():
    sim=SimpleNamespace(turn=0,debug=Mock(),_message=Mock(),log=[],
                        interiors=SimpleNamespace(player_presence=lambda:None))
    sim.execute=Mock(side_effect=lambda command:setattr(sim,'turn',sim.turn+AUTOSAVE_TURNS))
    db=Mock()
    db.path=Path('/saves/recovery.db')
    return SimpleNamespace(sim=sim,db=db,registry=object(),player_id=1)


class SaveFailureUITests(unittest.TestCase):
    def setUp(self):self.failure_panels=[]

    def capture_failure_panel(self,term,text,**kwargs):
        # Assert after recovery returns: the production display is best effort
        # and intentionally catches exceptions, including assertion failures.
        self.failure_panels.append((getattr(term,'_realtime_pause_depth',0),term._pump_realtime(),text))

    def tearDown(self):
        for depth,pumped,text in self.failure_panels:
            self.assertGreater(depth,0)
            self.assertFalse(pumped)
            self.assertIn('SAVE FAILED',text)
            self.assertIn('Current changes remain in memory.',text)
            # Path displays use the host OS separator (Windows in the Fast Gate).
            self.assertIn(str(Path('/saves/recovery.db')),text)
            self.assertIn('disk full',text)
            self.assertIn('Save game',text)

    def test_failure_reports_path_and_error_without_running_the_clock(self):
        ctx=context();term=RecoveryTerminal();clock=Mock()
        term.set_realtime_callback(clock)
        with patch.object(app,'_save',side_effect=OSError('disk full')) as save, \
             patch.object(app,'_view_text',side_effect=self.capture_failure_panel) as view:
            self.assertFalse(app._try_save(ctx,term,backup=False))
        save.assert_called_once_with(ctx,backup=False)
        view.assert_called_once()
        clock.assert_not_called()
        ctx.sim.debug.exception.assert_called_once()
        ctx.sim._message.assert_called_once_with('Save failed. Current changes remain in memory.')
        ctx.db.close.assert_not_called()
        self.assertEqual(term._realtime_pause_depth,0)

    def test_optional_diagnostics_and_repeated_close_cannot_discard_failed_save(self):
        ctx=context();term=RecoveryTerminal()
        ctx.sim.debug.exception.side_effect=RuntimeError('log unavailable')
        ctx.sim._message.side_effect=RuntimeError('message unavailable')
        with patch.object(app,'_save',side_effect=OSError('disk full')), \
             patch.object(app,'_view_text',side_effect=WindowCloseRequested):
            self.assertFalse(app._try_save(ctx,term))
            self.assertFalse(app._try_save(ctx))
        ctx.db.close.assert_not_called()
        self.assertEqual(term._realtime_pause_depth,0)

    def test_success_does_not_show_a_failure_panel(self):
        ctx=context();term=RecoveryTerminal()
        with patch.object(app,'_save') as save,patch.object(app,'_view_text') as view:
            self.assertTrue(app._try_save(ctx,term))
        save.assert_called_once_with(ctx)
        view.assert_not_called()
        ctx.sim._message.assert_not_called()

    def test_pause_checkpoint_failures_allow_resume_or_retry(self):
        for choice,result in (('save','saved'),('menu','menu'),('quit','quit')):
            for retry in (False,True):
                with self.subTest(choice=choice,retry=retry):
                    ctx=context();term=RecoveryTerminal()
                    choices=[choice,choice if retry else 'resume']
                    effects=[OSError('disk full'),None] if retry else [OSError('disk full')]
                    with patch.object(app,'_select',side_effect=choices), \
                         patch.object(app,'_save',side_effect=effects) as save, \
                         patch.object(app,'_view_text',side_effect=self.capture_failure_panel):
                        self.assertEqual(app._pause_menu(ctx,term),result if retry else 'resume')
                    self.assertEqual(save.call_count,2 if retry else 1)
                    ctx.db.close.assert_not_called()

    def test_direct_quit_failure_keeps_playing_until_retry_succeeds(self):
        ctx=context();term=RecoveryTerminal(['QUIT','QUIT'])
        with patch.object(app,'Renderer'),patch.object(app,'_present_game_frame') as frame, \
             patch.object(app,'_save',side_effect=[OSError('disk full'),None]) as save, \
             patch.object(app,'_view_text',side_effect=self.capture_failure_panel):
            self.assertEqual(app.run_game(ctx,term),'quit')
        self.assertEqual(save.call_args_list,[call(ctx),call(ctx)])
        self.assertIn('Save failed.',frame.call_args_list[1].args[3])
        ctx.db.close.assert_not_called()
        self.assertIsNone(term._realtime_callback)

    def test_both_autosave_routes_rate_limit_failure_and_do_not_report_success(self):
        for command_path in (False,True):
            with self.subTest(command_path=command_path):
                ctx=context()
                def due_redraw():
                    ctx.sim.turn=AUTOSAVE_TURNS
                    return 'UI_REDRAW'
                term=RecoveryTerminal(['.' if command_path else due_redraw,'UI_REDRAW','QUIT'])
                with patch.object(app,'Renderer'),patch.object(app,'_present_game_frame') as frame, \
                     patch.object(app,'_save',side_effect=[OSError('disk full'),None]) as save, \
                     patch.object(app,'_view_text',side_effect=self.capture_failure_panel):
                    self.assertEqual(app.run_game(ctx,term),'quit')
                self.assertEqual(save.call_args_list,[call(ctx,backup=False),call(ctx)])
                messages=[row.args[3] for row in frame.call_args_list]
                self.assertTrue(any('Autosave failed.' in message for message in messages))
                self.assertNotIn('Autosaved.',messages)

    def test_autosave_retries_after_another_interval(self):
        ctx=context()
        def redraw_at(turn):
            def key():
                ctx.sim.turn=turn
                return 'UI_REDRAW'
            return key
        term=RecoveryTerminal([redraw_at(AUTOSAVE_TURNS),'UI_REDRAW',
                               redraw_at(2*AUTOSAVE_TURNS),'QUIT'])
        with patch.object(app,'Renderer'),patch.object(app,'_present_game_frame') as frame, \
             patch.object(app,'_save',side_effect=[OSError('disk full'),None,None]) as save, \
             patch.object(app,'_view_text',side_effect=self.capture_failure_panel):
            self.assertEqual(app.run_game(ctx,term),'quit')
        self.assertEqual(save.call_args_list,[call(ctx,backup=False),call(ctx,backup=False),call(ctx)])
        self.assertIn('Autosaved.',[row.args[3] for row in frame.call_args_list])

    def test_failed_modal_close_reuses_context_and_open_database(self):
        ctx=context();term=RecoveryTerminal();runs=0
        def run(live_ctx,live_term):
            nonlocal runs
            self.assertIs(live_ctx,ctx);self.assertIs(live_term,term)
            ctx.db.close.assert_not_called()
            runs+=1
            raise WindowCloseRequested()
        with patch.object(app,'_make_display_backend',return_value=term), \
             patch.object(app,'_choose_world',return_value=object()) as choose, \
             patch.object(app,'_load_context',return_value=ctx) as load, \
             patch.object(app,'run_game',side_effect=run), \
             patch.object(app,'_save',side_effect=[OSError('disk full'),None]) as save, \
             patch.object(app,'_view_text',side_effect=self.capture_failure_panel):
            self.assertEqual(app.main(),0)
        self.assertEqual(runs,2)
        choose.assert_called_once();load.assert_called_once()
        self.assertEqual(save.call_args_list,[call(ctx),call(ctx)])
        ctx.db.close.assert_called_once()
        term.restore.assert_called_once()

    def test_close_during_failure_panel_returns_to_same_live_world(self):
        ctx=context();term=RecoveryTerminal();runs=0
        def run(live_ctx,live_term):
            nonlocal runs
            ctx.db.close.assert_not_called()
            runs+=1
            if runs==1:raise WindowCloseRequested()
            return 'quit'
        with patch.object(app,'_make_display_backend',return_value=term), \
             patch.object(app,'_choose_world',return_value=object()), \
             patch.object(app,'_load_context',return_value=ctx), \
             patch.object(app,'run_game',side_effect=run), \
             patch.object(app,'_save',side_effect=OSError('disk full')), \
             patch.object(app,'_view_text',side_effect=WindowCloseRequested):
            self.assertEqual(app.main(),0)
        self.assertEqual(runs,2)
        ctx.db.close.assert_called_once()
        term.restore.assert_called_once()


if __name__=='__main__':unittest.main()
