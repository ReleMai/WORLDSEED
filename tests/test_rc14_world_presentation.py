from pathlib import Path
import unittest


class RC14WorldPresentationContractTests(unittest.TestCase):
    def test_ground_resource_budget_is_decluttered_but_nonzero(self):
        src=Path('worldseed/systems/resources.py').read_text(encoding='utf-8')
        self.assertIn('"core:grass":125',src)
        self.assertIn('min(330,budget',src)
        self.assertIn('most ground is left clear',src)

    def test_graphical_camera_is_player_centered_and_mousewheel_zooms(self):
        src=Path('worldseed/ui/pygame_terminal.py').read_text(encoding='utf-8')
        self.assertIn('cx,cy,cz=pos.x,pos.y,pos.z',src)
        self.assertIn('Mouse wheel controls local-world zoom',src)
        self.assertIn("return 'RESIZE'",src)

    def test_gameplay_q_is_not_system_quit_and_window_close_is_distinct(self):
        pygame_src=Path('worldseed/ui/pygame_terminal.py').read_text(encoding='utf-8')
        router_src=Path('worldseed/ui/router.py').read_text(encoding='utf-8')
        self.assertIn('return "QUIT"',pygame_src)
        self.assertIn("if key == 'QUIT': return Intent('quit')",router_src)
        self.assertNotIn("if k == 'q': return Intent('quit')",router_src)

    def test_loading_transition_discards_stale_pygame_keypresses(self):
        pygame_src=Path('worldseed/ui/pygame_terminal.py').read_text(encoding='utf-8')
        app_src=Path('worldseed/app.py').read_text(encoding='utf-8')
        self.assertIn('def discard_pending_input',pygame_src)
        self.assertIn('event.clear(self.pg.KEYDOWN)',pygame_src)
        self.assertIn('self.pg.key.set_repeat()',pygame_src)
        self.assertIn('if not self._input_repeat_armed',pygame_src)
        self.assertIn("discard=getattr(term,'discard_pending_input',None)",app_src)
        self.assertLess(app_src.index("discard=getattr(term,'discard_pending_input',None)"),app_src.index('outcome=run_game(ctx,term)'))

if __name__=='__main__': unittest.main()
