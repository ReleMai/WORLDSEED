"""Main-loop time control ownership and committed-action integration."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from worldseed import app
from worldseed.sim.commands import MoveCommand
from worldseed.sim.realtime import RealtimeSimulationDriver
from worldseed.ui.router import classify_key


class Dev65MainLoopTests(unittest.TestCase):
    def test_pause_survives_menus_speed_selection_and_blocks_held_motion(self):
        sim = SimpleNamespace(turn=0, log=[], combat_active=lambda: False,
            interiors=SimpleNamespace(player_presence=lambda: None),
            set_free_movement_enabled=Mock(), update_free_movement=Mock(return_value=True),
            execute=Mock(), debug=SimpleNamespace(event=Mock(), flush=Mock()),
            advance_realtime=Mock(), clock=SimpleNamespace(minute=0))
        ctx = SimpleNamespace(sim=sim, registry=None, player_id=1)
        term = SimpleNamespace(set_realtime_callback=Mock(), set_combat_callback=Mock())
        def install_time(driver):term.driver=driver
        def install_free(callback):term.free=callback
        term.set_time_controls=install_time
        term.set_free_movement_callback=install_free
        tokens=iter(['UI_TIME:3',' ','ESC','UI_TIME:2',' ','INTERIOR_MOVE:1:0','QUIT'])
        step=[0]
        def read_key():
            driver=term.driver
            if step[0]==1:self.assertEqual(driver.speed,3)
            if step[0] in (2,3,4):
                self.assertTrue(driver.paused)
                self.assertFalse(term.free(.05,1,0,False))
                sim.update_free_movement.assert_not_called()
            if step[0]==4:self.assertEqual(driver.speed,2)
            if step[0]==5:
                self.assertFalse(driver.paused)
                self.assertTrue(term.free(.05,1,0,False))
                self.assertEqual(driver.speed,1)
            step[0]+=1
            return next(tokens)
        term.read_key=read_key
        def pause_menu(*_):
            self.assertTrue(term.driver.paused)
            self.assertTrue(term.driver.effective_paused)
            return 'saved'
        with patch.object(app,'_present_game_frame'), patch.object(app,'_try_save',return_value=True), \
             patch.object(app,'_pause_menu',side_effect=pause_menu):
            self.assertEqual(app.run_game(ctx,term),'quit')
        self.assertIsNone(term.driver)
        self.assertIsNone(term.free)
        self.assertIsInstance(sim.execute.call_args.args[0],MoveCommand)
        sim.update_free_movement.assert_called_once_with(.05,1,0,False)
        term.set_realtime_callback.assert_called_with(None)

    def test_router_keeps_movement_and_menu_pause_separate_from_world_pause(self):
        self.assertEqual(classify_key(' ').kind,'time_pause')
        self.assertEqual(classify_key('ESC').kind,'pause')
        for speed in (1,2,3):
            intent=classify_key(f'UI_TIME:{speed}')
            self.assertEqual((intent.kind,intent.value),('time_speed',speed))
        for bad in ('0','4','nan','2.0'):
            self.assertEqual(classify_key('UI_TIME:'+bad).kind,'none')
        for key in 'wasd':self.assertEqual(classify_key(key).kind,'move')

    def test_retained_panel_space_pauses_instead_of_activating_selected_action(self):
        from worldseed.ui.pygame_terminal import PygameTerminal
        from worldseed.ui.widgets import select_menu
        driver=RealtimeSimulationDriver(SimpleNamespace(combat_active=lambda:False))
        class Panel:
            mouse_ui=True
            _time_driver=driver
            _floating_backdrop=None
            _menu_backdrop_cache={}
            handle_time_control=PygameTerminal.handle_time_control
            def size(self):return 100,30
            def present_feature_menu(self,*args,**kwargs):pass
            def read_key(self):return next(self.keys)
        for presentation in ('inventory_unified','container_inventory','crafting_unified'):
            driver.resume(0)
            term=Panel();term.keys=iter([' ','ESC'])
            result=select_menu(term,'Inventory',[('consume','Consume selected item')],presentation=presentation)
            self.assertIsNone(result)
            self.assertTrue(driver.paused)

    def test_retained_panel_walking_obeys_pause_and_cancels_fast_forward(self):
        sim=SimpleNamespace(log=[],execute=Mock())
        driver=RealtimeSimulationDriver(SimpleNamespace(combat_active=lambda:False))
        term=SimpleNamespace(_time_driver=driver,_floating_panel_stack=[object()])
        ctx=SimpleNamespace(sim=sim,player_id=1)
        driver.set_speed(3,0);driver.pause()
        self.assertIn('paused',app._live_panel_world_move(ctx,term,'UI_WORLD_MOVE:d'))
        sim.execute.assert_not_called()
        driver.resume(1)
        app._live_panel_world_move(ctx,term,'UI_WORLD_MOVE:d')
        self.assertEqual(driver.speed,1)
        sim.execute.assert_called_once()


if __name__=='__main__':unittest.main()
