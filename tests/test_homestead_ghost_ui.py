"""World HUD blueprint placement is a scoped pointer mode, not a floor menu."""
import os
os.environ.setdefault("SDL_VIDEODRIVER","dummy")
os.environ.setdefault("SDL_AUDIODRIVER","dummy")
import unittest
from worldseed.ui.pygame_terminal import PygameTerminal

@unittest.skipUnless(PygameTerminal.available(),"requires pygame-ce")
class HomesteadGhostUITests(unittest.TestCase):
    def setUp(self):
        self.terminal=PygameTerminal()
        self.terminal.enter()
        self.pg=self.terminal.pg
        self.pg.event.clear()
        self.terminal._input_mode='world'
        self.terminal._hover_context={
            'used':self.pg.Rect(40,60,320,320),
            'grid_x':40,'grid_y':60,
            'left':-5,'top':-4,'tile_px':32}
    def tearDown(self):self.terminal.restore()

    def mouse(self,button,pos):
        self.pg.event.post(self.pg.event.Event(self.pg.MOUSEBUTTONDOWN,button=button,pos=pos))

    def test_world_click_returns_exact_tile_and_orientation(self):
        self.terminal.begin_homestead_placement('log_cabin_03')
        self.mouse(1,(40+32*4+2,60+32*3+2))
        self.assertEqual(self.terminal.read_key(),'UI_BLUEPRINT_PLACE:-1:-1:0')
        self.assertEqual(self.terminal._homestead_placement['style_id'],'log_cabin_03')

    def test_right_click_cancels_instead_of_opening_floor_menu(self):
        self.terminal.begin_homestead_placement('log_cabin_01')
        self.mouse(3,(40+50,60+50))
        self.assertEqual(self.terminal.read_key(),'UI_BLUEPRINT_CANCEL')
        self.assertIsNone(self.terminal._homestead_placement)

    def test_escape_cancels(self):
        self.terminal.begin_homestead_placement('log_cabin_01')
        self.pg.event.post(self.pg.event.Event(self.pg.KEYDOWN,key=self.pg.K_ESCAPE,unicode=''))
        self.assertEqual(self.terminal.read_key(),'UI_BLUEPRINT_CANCEL')
        self.assertIsNone(self.terminal._homestead_placement)

    def test_rotate_is_scoped_and_does_not_submit_room_menu_key(self):
        self.terminal.begin_homestead_placement('log_cabin_09')
        self.pg.event.post(self.pg.event.Event(self.pg.KEYDOWN,key=self.pg.K_r,unicode='r'))
        self.mouse(1,(42,62))
        self.assertEqual(self.terminal.read_key(),'UI_BLUEPRINT_PLACE:-5:-4:1')
        self.assertEqual(self.terminal._homestead_placement['orientation'],1)

    def test_click_outside_world_does_not_place(self):
        self.terminal.begin_homestead_placement('log_cabin_01')
        self.mouse(1,(20,20))
        self.mouse(3,(20,20))
        self.assertEqual(self.terminal.read_key(),'UI_BLUEPRINT_CANCEL')

    def test_preview_render_keeps_world_hit_targets_and_state(self):
        self.terminal.begin_homestead_placement('log_cabin_01')
        self.assertEqual(self.terminal._homestead_placement['orientation'],0)
        # A missing snapshot must not trigger a simulation write or crash.
        self.terminal._refresh_homestead_ghost(force=True)
        self.assertEqual(self.terminal._homestead_placement['orientation'],0)

if __name__=="__main__":unittest.main()
