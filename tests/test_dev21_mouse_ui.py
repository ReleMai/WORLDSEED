"""Real pointer events through the renderer, shared widgets and route owners."""
import os
os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')
import unittest
from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.ui.widgets import MenuRow, select_menu, prompt_text

@unittest.skipUnless(PygameTerminal.available(),'requires pygame-ce')
class MouseUITests(unittest.TestCase):
    def setUp(self):
        self.t=PygameTerminal();self.t.enter();self.pg=self.t.pg;self.pg.event.clear()
    def tearDown(self):self.t.restore()
    def click(self,token):
        r=next(r for r,k in reversed(self.t._pointer_targets) if k==token)
        self.pg.event.post(self.pg.event.Event(self.pg.MOUSEBUTTONDOWN,button=1,pos=r.center))
    def test_menu_click_activates_exact_row_and_hover_does_not_confirm(self):
        rows=[MenuRow('a','Alpha'),MenuRow('b','Beta')]
        self.t.present_menu('Test',rows,0)
        r=next(r for r,k in self.t._pointer_targets if k=='UI_SELECT:1')
        self.pg.event.post(self.pg.event.Event(self.pg.MOUSEMOTION,pos=r.center,rel=(0,0),buttons=(0,0,0)))
        self.click('UI_SELECT:1')
        self.assertEqual(self.t.read_key(),'UI_HOVER:1')
        self.assertEqual(self.t.read_key(),'UI_SELECT:1')
    def test_modal_clears_held_movement_and_ignores_wasd(self):
        self.pg.event.post(self.pg.event.Event(self.pg.KEYDOWN,key=self.pg.K_w,unicode='w'))
        self.assertEqual(self.t.read_key(),'w')
        self.t.present_menu('Menu',[MenuRow('a','Alpha')],0)
        self.assertIsNone(self.t._active_movement_key)
        for key in 'wasd':self.pg.event.post(self.pg.event.Event(self.pg.KEYDOWN,key=ord(key),unicode=key))
        self.click('UI_SELECT:0')
        self.assertEqual(self.t.read_key(),'UI_SELECT:0')
        self.t._draw_chrome('WORLDSEED // LOCAL')
        self.assertIsNone(self.t._active_movement_key)
        self.assertEqual(self.t._pointer_targets,[])
    def test_menu_wheel_pages_without_world_zoom_and_resize_drops_targets(self):
        self.t.present_menu('Menu',[MenuRow('a','Alpha')],0)
        zoom=self.t._tile_px
        self.pg.event.post(self.pg.event.Event(self.pg.MOUSEWHEEL,x=0,y=-1))
        self.assertEqual(self.t.read_key(),'PGDN');self.assertEqual(self.t._tile_px,zoom)
        self.t._resize(800,520);self.assertEqual(self.t._pointer_targets,[])
    def test_mouse_paging_reaches_offscreen_items_and_retains_state(self):
        from worldseed.ui.session import RouteState
        state=RouteState('test','Test');sequence=iter(['PGDN','UI_SELECT:1'])
        read=self.t.read_key
        def pointer_input():
            self.click(next(sequence));return read()
        self.t.read_key=pointer_input
        capacity=self.t.menu_page_size()
        rows=[(str(i),f'Item {i}') for i in range(capacity+4)]
        self.assertEqual(select_menu(self.t,'Test',rows,state=state),str(capacity+1))
        self.assertEqual(state.selected,capacity+1)
    def test_text_entry_accepts_wasd_and_mouse_confirmation(self):
        read=self.t.read_key;count=0
        def input_event():
            nonlocal count
            if count<4:
                key='wasd'[count];self.pg.event.post(self.pg.event.Event(self.pg.KEYDOWN,key=ord(key),unicode=key))
            else:self.click('\r')
            count+=1;return read()
        self.t.read_key=input_event
        self.assertEqual(prompt_text(self.t,'Name','Name',default=''),'wasd')
    def test_feature_hit_targets_fit_small_and_large_windows(self):
        for size in ((800,520),(1600,900)):
            self.t._resize(*size)
            for kind in ('inventory_items','crafting_categories','crafting_recipes','crafting_designs','crafting_component_choices','crafting_home'):
                count=self.t.menu_page_size(kind)
                rows=[MenuRow(str(i),f'Row {i}') for i in range(count)]
                self.t.present_feature_menu(kind,'Test',rows,0)
                targets=[r for r,k in self.t._pointer_targets if k.startswith('UI_SELECT:')]
                self.assertEqual(len(targets),count,kind)
                for rect in targets:
                    self.assertTrue(self.t.screen.get_rect().contains(rect),(kind,size,rect))
                    self.assertLessEqual(rect.bottom,size[1]-56,(kind,size,rect))
    def test_hud_and_nested_crafting_inventory_are_clickable_and_observational(self):
        from test_ui_rc2 import UIRC3FlowTests
        from worldseed.app import _crafting_menu,_inventory_menu
        from worldseed.ui.router import HUD_BUTTONS,classify_key
        f=UIRC3FlowTests();f.setUp()
        try:
            before=f.sim.state.to_dict()
            self.t.present_game(f.reg,f.world,f.entities,f.sim,f.pid)
            self.pg.image.save(self.t.screen,'artifacts/dev21_hud.png')
            for _,token in HUD_BUTTONS:
                self.click(token);self.assertEqual(self.t.read_key(),token)
                self.assertNotEqual(classify_key(token).kind,'none')
            read=self.t.read_key
            for menu,steps in ((_inventory_menu,['UI_SELECT:1','UI_SELECT:0','ESC','ESC','ESC']),(_crafting_menu,['UI_SELECT:0','UI_SELECT:0','UI_SELECT:0','ESC','ESC','ESC','ESC'])):
                sequence=iter(steps)
                def input_event():
                    token=next(sequence);self.click(token);return read()
                self.t.read_key=input_event
                menu(f.ctx,self.t)
            from worldseed.app import _look_mode
            sequence=iter(['tile','\r','ESC','ESC'])
            def look_input():
                token=next(sequence)
                if token=='tile':
                    self.pg.event.post(self.pg.event.Event(self.pg.MOUSEBUTTONDOWN,button=1,pos=self.t._hover_context['used'].center))
                else:self.click(token)
                return read()
            self.t.read_key=look_input
            _look_mode(f.ctx,self.t)
            self.assertEqual(before,f.sim.state.to_dict())
        finally:f.tearDown()
    def test_window_close_unwinds_modal_and_focus_loss_clears_movement(self):
        from worldseed.ui.pointer import WindowCloseRequested
        self.pg.event.post(self.pg.event.Event(self.pg.KEYDOWN,key=self.pg.K_w,unicode='w'))
        self.assertEqual(self.t.read_key(),'w')
        self.pg.event.post(self.pg.event.Event(self.pg.WINDOWFOCUSLOST))
        self.pg.event.post(self.pg.event.Event(self.pg.KEYDOWN,key=self.pg.K_ESCAPE,unicode='\x1b'))
        self.assertEqual(self.t.read_key(),'ESC');self.assertIsNone(self.t._active_movement_key)
        self.t.present_menu('Menu',[MenuRow('a','Alpha')],0)
        self.pg.event.post(self.pg.event.Event(self.pg.QUIT))
        with self.assertRaises(WindowCloseRequested):self.t.read_key()
    def test_appearance_and_point_buy_can_be_completed_by_mouse(self):
        from worldseed.ui.startup import _appearance_menu,_allocate_values
        read=self.t.read_key
        for action,steps in ((lambda:_appearance_menu(self.t),['UI_SEX:female','UI_APPEARANCE:8','\r']),
                             (lambda:_allocate_values(self.t,'Test',[('test','Test','Hint')],{'test':0},1,3),['UI_PLUS:0','\r'])):
            sequence=iter(steps)
            def input_event():self.click(next(sequence));return read()
            self.t.read_key=input_event
            result=action()
            self.assertIn(result,[('female',8),{'test':1}])
    def test_modal_window_close_saves_and_closes_active_world(self):
        from unittest.mock import Mock,patch
        from worldseed import app
        from worldseed.ui.pointer import WindowCloseRequested
        ctx=Mock();term=Mock()
        with patch.object(app,'_make_display_backend',return_value=term), patch.object(app,'_choose_world',return_value=object()), patch.object(app,'_load_context',return_value=ctx), patch.object(app,'run_game',side_effect=WindowCloseRequested), patch.object(app,'_save') as save:
            self.assertEqual(app.main(),0)
            save.assert_called_once_with(ctx)
            ctx.db.close.assert_called_once()
            term.restore.assert_called_once()
