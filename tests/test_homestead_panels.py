"""Graphical, in-game homestead catalog and depot panels."""
import os
os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')
import unittest
from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.ui.homestead_panels import render_cabin_style
from worldseed.systems.homestead_blueprints import catalog

MATERIALS=[
    ('core:wood','Wood',5,28,7),
    ('core:reed_bundle','Reed bundle',0,12,0),
    ('core:clay_lump','Clay lump',6,9,9),
    ('core:stone','Stone',4,4,1),
    ('core:plant_cordage','Plant cordage',0,4,3),
]

@unittest.skipUnless(PygameTerminal.available(),'requires pygame-ce')
class HomesteadPanelsTests(unittest.TestCase):
    def setUp(self):
        self.term=PygameTerminal()
        self.term.enter()
        self.pg=self.term.pg
        self.pg.event.clear()
        self.term._draw_chrome('WORLDSEED // LOCAL')
    def tearDown(self):
        self.term.restore()
    def style(self,n=1):
        return catalog()[1][f'log_cabin_{n:02d}']
    def depot(self,stage=0,confirm=False):
        return {'site':{'stage':stage},
                'style_name':'Woodland','stage_name':'Foundation' if stage==0 else 'Complete',
                'materials':MATERIALS,'notice':'','confirm_cancel':confirm}

    def test_ten_style_images_are_distinct(self):
        surfaces=[render_cabin_style(self.pg,self.style(n)) for n in range(1,11)]
        signatures={self.pg.image.tostring(s,'RGBA') for s in surfaces}
        self.assertEqual(len(signatures),10)

    def test_style_carousel_is_a_world_overlay_with_clickable_arrows(self):
        before=self.term.screen.get_at((18,200))
        self.term.present_homestead_styles(self.style(1),0,10)
        actions={token for rect,token in self.term._pointer_targets}
        self.assertTrue({'UI_ACTION:cabin_prev','UI_ACTION:cabin_next',
                         'UI_ACTION:cabin_place','ESC','UI_ACTION:cabin_other'}<=actions)
        self.assertEqual(self.term._input_mode,'ui')
        self.assertEqual(self.term.screen.get_at((18,200)),before)
        self.assertEqual(self.term._floating_panel_id,'homestead_styles')
        arrow=next(rect for rect,token in self.term._pointer_targets if token=='UI_ACTION:cabin_next')
        self.assertEqual(self.term._hit_token(arrow.center),'UI_ACTION:cabin_next')

    def test_depot_panel_icons_and_commands_are_inline(self):
        icons=[]
        orig=self.term._draw_item_icon
        self.term._draw_item_icon=lambda iid,rect,**kwargs:icons.append(iid)
        try:self.term.present_homestead_depot(self.depot())
        finally:self.term._draw_item_icon=orig
        self.assertEqual(icons,[x[0] for x in MATERIALS])
        actions={token for rect,token in self.term._pointer_targets}
        self.assertTrue({'UI_ACTION:depot_item_one:core:wood',
                         'UI_ACTION:depot_item_all:core:wood',
                         'UI_ACTION:depot_all','UI_ACTION:depot_build',
                         'UI_ACTION:depot_cancel','ESC'}<=actions)
        self.assertNotIn('UI_ACTION:depot_item_one:core:reed_bundle',actions)
        self.assertEqual(self.term._floating_panel_id,'homestead_depot')

    def test_cancel_confirmation_stays_in_same_panel(self):
        self.term.present_homestead_depot(self.depot(confirm=True))
        actions={token for rect,token in self.term._pointer_targets}
        self.assertIn('UI_ACTION:depot_cancel_confirm',actions)
        self.assertIn('UI_ACTION:depot_cancel_back',actions)
        self.assertNotIn('UI_ACTION:depot_all',actions)

    def test_destructive_actions_are_visually_distinct_but_keep_tokens(self):
        self.term.present_homestead_depot(self.depot(confirm=True))
        targets={token:rect for rect,token in self.term._pointer_targets}
        target=targets['UI_ACTION:depot_cancel_confirm']
        self.assertEqual(tuple(self.term.screen.get_at((target.left,target.centery))[:3]),
                         self.term._theme['danger'])
        self.term.present_homestead_depot(self.depot(confirm=False))
        targets={token:rect for rect,token in self.term._pointer_targets}
        target=targets['UI_ACTION:depot_cancel']
        self.assertEqual(tuple(self.term.screen.get_at((target.left,target.centery))[:3]),
                         self.term._theme['danger'])

    def test_completed_blueprint_has_no_material_transfer_actions(self):
        self.term.present_homestead_depot(self.depot(stage=4))
        actions={token for rect,token in self.term._pointer_targets}
        self.assertFalse(any(token.startswith('UI_ACTION:depot_') for token in actions))

    def test_small_window_panels_keep_buttons_on_screen(self):
        self.term._resize(800,520)
        self.term._draw_chrome('WORLDSEED // LOCAL')
        self.term.present_homestead_styles(self.style(5),4,10)
        for rect,token in self.term._pointer_targets:
            self.assertTrue(self.term.screen.get_rect().contains(rect),(token,rect))
        self.term._draw_chrome('WORLDSEED // LOCAL')
        self.term.present_homestead_depot(self.depot())
        for rect,token in self.term._pointer_targets:
            self.assertTrue(self.term.screen.get_rect().contains(rect),(token,rect))

if __name__=='__main__':
    unittest.main()
