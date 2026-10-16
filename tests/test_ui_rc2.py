import re
import tempfile
import unittest
from pathlib import Path

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory, Position, Vitals
from worldseed.entities.store import EntityStore
from worldseed.persistence.database import WorldDatabase
from worldseed.sim.engine import Simulation
from worldseed.systems.state import LivingWorldState
from worldseed.ui.layout import compute_layout, screen_width, regional_grid
from worldseed.ui.navigation import WORLD_CONSOLE_ROOT, ACTION_COMBAT
from worldseed.ui.renderer import Renderer
from worldseed.ui.router import classify_key, DIRECT_MENUS
from worldseed.ui.screens import help_screen
from worldseed.ui.widgets import panel, select_menu
from worldseed.world.generator import WorldGenerator
from worldseed.world.world import World

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


class AggressiveStanceRoutingTests(unittest.TestCase):
    def test_gpu_primary_hud_restores_bars_and_modal_help_preserves_navigation(self):
        import os
        from types import SimpleNamespace
        from unittest.mock import patch
        from worldseed.ui import gpu_hud
        from worldseed.ui.pygame_terminal import PygameTerminal
        from worldseed.ui.router import HUD_BUTTONS
        if not PygameTerminal.available():self.skipTest('pygame optional')
        with patch.dict(os.environ,{'SDL_VIDEODRIVER':'dummy','SDL_AUDIODRIVER':'dummy'}):
            term=PygameTerminal(800,520);term.enter()
            try:
                term._input_mode='world'
                sim=SimpleNamespace(state=SimpleNamespace(player_name='Wanderer',player_hunting_stance='stalk'),
                    clock=SimpleNamespace(label=lambda:'Y1 Spring 1, 08:25'),
                    player_pos=WorldPos(12,24,0))
                rect=term.pg.Rect(640,55,146,380)
                gpu_hud.draw_hud(term,rect,sim,Vitals())
                self.assertEqual([token for _,token in term._pointer_targets[:10]],
                                 [token for _,token in HUD_BUTTONS])
                self.assertEqual([name.split()[0] for _,name,_ in term._hud_tooltips[:4]],
                                 ['Health','Stamina','Hunger','Thirst'])
                self.assertTrue(all(rect.contains(target) for target,_ in term._pointer_targets))
                help_rect=next(area for area,token in term._pointer_targets if token=='?')
                self.assertTrue(gpu_hud.handle_hud_event(term,term.pg.event.Event(
                    term.pg.MOUSEBUTTONDOWN,button=1,pos=help_rect.center)))
                gpu_hud.draw_help_popup(term)
                self.assertEqual(term._gpu_help_window.navigation.depth,2)
                self.assertTrue(gpu_hud.handle_hud_event(term,term.pg.event.Event(
                    term.pg.KEYDOWN,key=term.pg.K_ESCAPE,unicode='')))
                self.assertFalse(gpu_hud.help_popup_open(term))
                self.assertEqual(term._input_mode,'world')
                for key in 'wasd':self.assertEqual(classify_key(key).kind,'move')
            finally:
                gpu_hud.close_help_popup(term)
                term.restore()

    def test_shared_indoor_outdoor_toolbar_tokens_and_narrow_geometry(self):
        import os
        from unittest.mock import patch
        from worldseed.ui.pygame_terminal import PygameTerminal
        from worldseed.ui.router import HUD_BUTTONS
        if not PygameTerminal.available():self.skipTest('pygame optional')
        with patch.dict(os.environ,{'SDL_VIDEODRIVER':'dummy','SDL_AUDIODRIVER':'dummy'}):
            term=PygameTerminal(800,520);term.enter()
            try:
                term._input_mode='world'
                for width,height in ((300,420),(146,240),(90,140)):
                    term._pointer_targets=[];term._hud_tooltips=[]
                    rect=term.pg.Rect(400,70,width,height)
                    bar=term._draw_hud_actions(rect,'stalk')
                    self.assertTrue(rect.contains(bar))
                    self.assertEqual([token for _,token in term._pointer_targets[:10]],
                                     [token for _,token in HUD_BUTTONS])
                    self.assertTrue(all(rect.contains(target) for target,_ in term._pointer_targets))
                    self.assertEqual(term.screen.get_clip(),term.screen.get_rect())
            finally:term.restore()

    def test_shared_hud_stance_controls_are_pointer_only_and_bounded(self):
        import os
        from unittest.mock import patch
        from worldseed.ui.pygame_terminal import PygameTerminal
        if not PygameTerminal.available():self.skipTest('pygame optional')
        with patch.dict(os.environ,{'SDL_VIDEODRIVER':'dummy','SDL_AUDIODRIVER':'dummy'}):
            term=PygameTerminal(800,520);term.enter()
            try:
                rect=term.pg.Rect(540,450,230,29)
                term._draw_stance_buttons(rect,'aggressive')
                controls=[(r,t) for r,t in term._pointer_targets if t.startswith('UI_STANCE:')]
                self.assertEqual([t for r,t in controls],['UI_STANCE:normal','UI_STANCE:stalk','UI_STANCE:crouch','UI_STANCE:aggressive'])
                self.assertTrue(all(rect.contains(r) for r,t in controls))
                for r,t in controls:self.assertEqual(classify_key(t).kind,'stance')
                hints=' '.join(detail for _,_,detail in term._hud_tooltips)
                self.assertIn('enables theft',hints)
                self.assertNotIn('casing',hints.lower())
            finally:term.restore()

    def test_interior_direction_tokens_preserve_wasd_movement_contract(self):
        from worldseed.ui.router import classify_key
        for key in ('w','a','s','d'):
            self.assertEqual(classify_key(key).kind,'move')
        # Cabin entry is offered by the same primary navigation as every other
        # player verb; adding a portal must not claim another global key table.
        self.assertEqual(classify_key('\r').kind,'actions')
        self.assertEqual(classify_key('\t').kind,'console')
    def test_aggressive_pointer_intent_preserves_movement_keys(self):
        intent = classify_key('UI_STANCE:aggressive')
        self.assertEqual(intent.kind, 'stance')
        self.assertEqual(intent.value, 'aggressive')
        for key in 'wasd':
            self.assertEqual(classify_key(key).kind, 'move')


def visible_len(s):
    return len(ANSI_RE.sub('', s))


class UIRC2Tests(unittest.TestCase):
    def test_regional_grid_fits_viewport_and_centers_current_block(self):
        for width, height in ((1, 1), (80, 30), (450, 380), (950, 665), (2100, 1200)):
            cols, rows, cell, ix, iy = regional_grid(width, height)
            self.assertEqual(cols % 2, 1)
            self.assertEqual(rows % 2, 1)
            self.assertGreaterEqual(ix, 0)
            self.assertGreaterEqual(iy, 0)
            self.assertLessEqual(ix + cols * cell, width)
            self.assertLessEqual(iy + rows * cell, height)

    def setUp(self):
        self.reg = ContentRegistry.load(DATA_DIR)
        self.td = tempfile.TemporaryDirectory()
        self.seed = b'ui-rc2'
        self.db = WorldDatabase.create(Path(self.td.name)/'ui.db','ui',self.seed.hex())
        self.world = World(WorldGenerator(self.seed,self.reg),self.reg,self.db)
        self.entities = EntityStore(); self.pid = self.entities.spawn(preferred_id=1)
        self.entities.add(self.pid,Position(WorldPos(0,0,0)))
        self.entities.add(self.pid,Inventory({'core:copper_coin':30,'core:wood':4}))
        self.entities.add(self.pid,Vitals())
        self.sim = Simulation(self.world,self.entities,self.reg,0,LivingWorldState(),self.seed)
        self.sim._discover(WorldPos(0,0,0))

    def tearDown(self):
        self.db.close(); self.td.cleanup()

    def test_environment_look_is_observational_and_does_not_plan(self):
        from unittest.mock import patch
        from worldseed.ui.screens import look_screen
        before = self.sim.state.to_dict()
        minute, turn = self.sim.clock.minute, self.sim.turn
        with patch.object(self.sim, 'player_skill', return_value=6), \
             patch.object(self.world.generator.hydrology, 'generate', side_effect=AssertionError('inspection planned')):
            text = look_screen(self.sim, 80)
        self.assertIn('Ground signs:', text)
        self.assertEqual(before, self.sim.state.to_dict())
        self.assertEqual((minute, turn), (self.sim.clock.minute, self.sim.turn))
        for line in text.splitlines():
            self.assertLessEqual(visible_len(line), 80)

    def test_camera_grid_keeps_player_centered_at_every_zoom(self):
        from worldseed.ui.layout import centered_tile_grid
        for width, height in ((410, 300), (830, 600), (1221, 779)):
            for size in range(16, 57, 4):
                cols, rows, x, y = centered_tile_grid(width, height, size)
                self.assertEqual(cols % 2, 1)
                self.assertEqual(rows % 2, 1)
                self.assertLessEqual(abs(x + (cols // 2 + .5) * size - width / 2), .5)
                self.assertLessEqual(abs(y + (rows // 2 + .5) * size - height / 2), .5)
                self.assertLessEqual(x + cols * size, width)
                self.assertLessEqual(y + rows * size, height)

    def test_d_is_always_movement_intent(self):
        self.assertEqual(classify_key('d').kind,'move')
        self.assertEqual(classify_key('d').value,(1,0))
        self.assertEqual(classify_key('q').kind,'none')
        self.assertEqual(classify_key('Q').kind,'none')
        self.assertEqual(classify_key('QUIT').kind,'quit')
        self.assertNotIn('d',DIRECT_MENUS)

    def test_hud_stance_tokens_use_existing_simulation_intent(self):
        for stance in ('normal','stalk','crouch'):
            intent=classify_key('UI_STANCE:'+stance)
            self.assertEqual((intent.kind,intent.value),('stance',stance))
        self.assertEqual(classify_key('UI_STANCE:fly').kind,'none')

    def test_combat_action_hub_exposes_active_defense_without_new_global_keys(self):
        keys={key for key,_ in ACTION_COMBAT}
        for expected in ("dodge","parry","guard","brace","bash","disengage","arena"):
            self.assertIn(expected,keys)
        # These are Action Hub verbs, not global movement/router bindings.
        for key in ("dodge","parry","guard","brace","bash","disengage"):
            self.assertNotIn(key,DIRECT_MENUS)

    def test_primary_navigation_is_small_and_hierarchical(self):
        self.assertLessEqual(len(WORLD_CONSOLE_ROOT),9)
        labels=' '.join(label.lower() for _,label in WORLD_CONSOLE_ROOT)
        self.assertIn('character',labels)
        self.assertIn('society',labels)
        self.assertIn('records',labels)

    def test_layout_never_claims_more_than_terminal(self):
        for width,height in [(59,17),(60,18),(80,24),(100,30),(124,32),(160,45)]:
            layout=compute_layout(width,height,'dense')
            self.assertLessEqual(layout.width,width)
            self.assertLessEqual(layout.height,height)
            self.assertLessEqual(layout.map_width,max(1,width))
            self.assertLessEqual(layout.map_height,max(1,height))

    def test_combat_pause_indicator_is_observational_and_fits_narrow_hud(self):
        from unittest.mock import patch
        renderer=Renderer(self.reg,use_color=False)
        before=self.sim.state.to_dict()
        with patch.object(self.sim,'combat_active',return_value=True):
            for width,height in ((60,18),(80,24),(100,30),(124,32)):
                frame=renderer.render(self.world,self.entities,self.sim,self.pid,width,height)
                self.assertIn('COMBAT PAUSED',frame)
                self.assertLessEqual(len(frame.splitlines()),height)
                self.assertTrue(all(visible_len(line)<=width for line in frame.splitlines()))
        self.assertEqual(before,self.sim.state.to_dict())

    def test_renderer_never_relies_on_terminal_wrapping(self):
        r=Renderer(self.reg,use_color=True)
        before=self.sim.state.to_dict()
        for width,height in [(60,18),(80,24),(100,30),(124,32),(160,45)]:
            frame=r.render(self.world,self.entities,self.sim,self.pid,width,height)
            lines=frame.splitlines()
            self.assertLessEqual(len(lines),height,(width,height,len(lines)))
            for line in lines:
                self.assertLessEqual(visible_len(line),width,(width,height,visible_len(line),line))
        self.assertEqual(before,self.sim.state.to_dict())

    def test_panel_respects_requested_width(self):
        for width in (32,44,60,80):
            text=panel('TEST',['A very long line '+('word '*50)],width,'Esc back')
            for line in text.splitlines():
                self.assertLessEqual(visible_len(line),width)

    def test_arrow_enter_menu_navigation(self):
        class FakeTerm:
            def __init__(self,keys): self.keys=list(keys); self.frames=[]
            def size(self): return (80,24)
            def present(self,text): self.frames.append(text)
            def read_key(self): return self.keys.pop(0)
        term=FakeTerm(['DOWN','\r'])
        choice=select_menu(term,'TEST',[('a','Alpha'),('b','Beta'),('c','Gamma')])
        self.assertEqual(choice,'b')
        self.assertTrue(any('> 2. Beta' in frame for frame in term.frames))

    def test_numeric_menu_choice_is_optional_shortcut(self):
        class FakeTerm:
            def __init__(self): self.frames=[]
            def size(self): return (80,24)
            def present(self,text): self.frames.append(text)
            def read_key(self): return '3'
        self.assertEqual(select_menu(FakeTerm(),'TEST',[('a','Alpha'),('b','Beta'),('c','Gamma')]),'c')

    def test_help_teaches_primary_model(self):
        text=help_screen(screen_width(80,100))
        self.assertIn('Enter',text)
        self.assertIn('TAB',text)
        self.assertIn('MOVE',text)
        self.assertIn('Nothing requires a quest',text)


if __name__ == '__main__':
    unittest.main()

class UIRC3NavigationTests(unittest.TestCase):
    def setUp(self):
        self.reg = ContentRegistry.load(DATA_DIR)
        self.td = tempfile.TemporaryDirectory()
        self.seed = b'ui-rc3'
        self.db = WorldDatabase.create(Path(self.td.name)/'ui.db','ui',self.seed.hex())
        self.world = World(WorldGenerator(self.seed,self.reg),self.reg,self.db)
        self.entities = EntityStore(); self.pid = self.entities.spawn(preferred_id=1)
        self.entities.add(self.pid,Position(WorldPos(0,0,0)))
        self.entities.add(self.pid,Inventory({'core:copper_coin':30,'core:wood':4}))
        self.entities.add(self.pid,Vitals())
        self.sim = Simulation(self.world,self.entities,self.reg,0,LivingWorldState(),self.seed)
        self.sim._discover(WorldPos(0,0,0))

    def tearDown(self):
        self.db.close(); self.td.cleanup()
    def test_navigation_stack_pop_and_retained_state(self):
        from worldseed.ui.session import NavigationStack, RouteState
        nav=NavigationStack(RouteState('root','Root',selected=2,scroll=3))
        nav.push(RouteState('child','Child',selected=4,scroll=8))
        nav.push(RouteState('detail','Detail',selected=0,scroll=12))
        self.assertEqual(nav.depth,3)
        self.assertTrue(nav.back())
        self.assertEqual(nav.current.route_id,'child')
        self.assertEqual(nav.current.selected,4)
        self.assertEqual(nav.current.scroll,8)
        self.assertTrue(nav.back())
        self.assertEqual(nav.current.route_id,'root')
        self.assertEqual(nav.current.selected,2)
        self.assertEqual(nav.current.scroll,3)
        self.assertFalse(nav.back())

    def test_menu_state_restores_selected_row_after_child(self):
        from worldseed.ui.session import RouteState
        class FakeTerm:
            def __init__(self,keys): self.keys=list(keys); self.frames=[]
            def size(self): return (80,24)
            def present(self,text): self.frames.append(text)
            def read_key(self): return self.keys.pop(0)
        state=RouteState('menu','Menu')
        term=FakeTerm(['DOWN','DOWN','\r'])
        choice=select_menu(term,'TEST',[('a','Alpha'),('b','Beta'),('c','Gamma')],state=state)
        self.assertEqual(choice,'c'); self.assertEqual(state.selected,2)
        term2=FakeTerm(['ESC'])
        self.assertIsNone(select_menu(term2,'TEST',[('a','Alpha'),('b','Beta'),('c','Gamma')],state=state))
        self.assertIn('> 3. Gamma',term2.frames[0])

    def test_world_console_esc_pops_one_layer(self):
        from worldseed.app import GameContext, _world_console
        class FakeTerm:
            def __init__(self,keys): self.keys=list(keys); self.frames=[]
            def size(self): return (100,30)
            def present(self,text): self.frames.append(text)
            def read_key(self):
                if not self.keys: raise AssertionError('UI requested extra input')
                return self.keys.pop(0)
        # Root 8=System; submenu 3=Help; ESC leaves help, ESC leaves System,
        # ESC dismisses World Console back to gameplay.
        term=FakeTerm(['8','2','ESC','ESC','ESC'])
        ctx=GameContext(self.db,self.reg,self.world,self.entities,self.sim,self.pid)
        _world_console(ctx,term)
        joined='\n---FRAME---\n'.join(term.frames)
        self.assertGreaterEqual(joined.lower().count('world console'),2)
        self.assertIn('HELP',joined)
        # Parent menu should be rendered again after closing help.
        self.assertGreaterEqual(joined.upper().count('GAME & INTERFACE OPTIONS'),2)


def _fake_term(keys, size=(100,30)):
    class FakeTerm:
        def __init__(self): self.keys=list(keys); self.frames=[]
        def size(self): return size
        def present(self,text): self.frames.append(text)
        def read_key(self):
            if not self.keys: raise AssertionError('UI requested extra input')
            return self.keys.pop(0)
    return FakeTerm()


class UIRC3FlowTests(unittest.TestCase):
    def setUp(self):
        self.reg = ContentRegistry.load(DATA_DIR)
        self.td = tempfile.TemporaryDirectory(); self.seed=b'ui-flow'
        self.db = WorldDatabase.create(Path(self.td.name)/'ui.db','ui',self.seed.hex())
        self.world = World(WorldGenerator(self.seed,self.reg),self.reg,self.db)
        self.entities=EntityStore();self.pid=self.entities.spawn(preferred_id=1)
        self.entities.add(self.pid,Position(WorldPos(0,0,0)))
        self.entities.add(self.pid,Inventory({'core:copper_coin':30,'core:wood':4}))
        self.entities.add(self.pid,Vitals())
        self.sim=Simulation(self.world,self.entities,self.reg,0,LivingWorldState(),self.seed);self.sim._discover(WorldPos(0,0,0))
        from worldseed.app import GameContext
        self.ctx=GameContext(self.db,self.reg,self.world,self.entities,self.sim,self.pid)
    def tearDown(self): self.db.close();self.td.cleanup()

    def test_action_palette_escape_returns_one_level(self):
        from worldseed.app import _action_palette
        # Work -> Craft -> Esc to Work -> Esc to Actions -> Esc gameplay.
        term=_fake_term(['3','1','ESC','ESC','ESC'])
        _action_palette(self.ctx,term)
        joined='\n'.join(term.frames).lower()
        self.assertGreaterEqual(joined.count('work'),2)
        self.assertGreaterEqual(joined.count('actions'),2)
        self.assertIn('crafting mode',joined)

    def test_inventory_detail_escape_restores_item_then_list_then_root(self):
        from worldseed.app import _inventory_menu
        # Browse -> first item -> Inspect -> Esc detail -> Esc item actions ->
        # Esc carried list -> Esc inventory root.
        term=_fake_term(['2','1','1','ESC','ESC','ESC','ESC'])
        _inventory_menu(self.ctx,term)
        joined='\n'.join(term.frames).lower()
        self.assertIn('copper coin',joined)
        self.assertGreaterEqual(joined.count('carried items'),2)
        self.assertGreaterEqual(joined.count('inventory'),2)

class UIRC4InputTests(unittest.TestCase):
    def test_retained_inventory_hover_and_scroll_preserve_action_target(self):
        from worldseed.ui.session import RouteState
        class FakeTerm:
            def __init__(self):
                self.keys=iter(['UI_HOVER:0','UI_SCROLL:2','UI_HOVER:1','UI_ACTION:drop'])
                self.frames=[]
            def size(self):return (80,24)
            def menu_page_size(self,presentation):return 2
            def present_feature_menu(self,presentation,title,rows,selected,**kwargs):
                self.frames.append((selected,kwargs['page_start'],kwargs['data']['selected_key'],kwargs['data']['action_amount']))
            def read_key(self):return next(self.keys)
        term=FakeTerm()
        state=RouteState('inventory','Inventory',selected=1)
        rows=[('core:stone','Stone'),('core:wood','Wood'),('core:bark','Bark'),('core:flint','Flint')]
        choice=select_menu(term,'Inventory',rows,state=state,presentation='inventory_unified',
                           presentation_data={'action_amount':3})
        self.assertEqual(choice,'UI_ACTION:drop')
        self.assertEqual((state.selected,state.scroll),(1,2))
        self.assertEqual(term.frames[-1],(-1,2,'core:wood',3))
        self.assertTrue(all(key=='core:wood' and amount==3 for _,_,key,amount in term.frames))

    def test_large_crafting_catalogue_pages_wrapped_rows_within_narrow_terminal(self):
        term=_fake_term(['END','\r'],size=(42,16))
        rows=[(str(index),f'Workshop technique {index}: recover, shape and finish assorted components') for index in range(240)]
        self.assertEqual(select_menu(term,'CRAFTING // RECIPES',rows,subtitle='Learned techniques grouped by profession.'),'239')
        for frame in term.frames:
            self.assertLessEqual(len(frame.splitlines()),16,frame)
            self.assertTrue(all(visible_len(line)<=42 for line in frame.splitlines()),frame)
        self.assertIn('239',term.frames[-1])

    def test_windows_escape_character_normalizes_to_esc(self):
        from worldseed.ui.terminal import normalize_raw_key
        self.assertEqual(normalize_raw_key('\x1b'), 'ESC')
        self.assertEqual(normalize_raw_key('ESC'), 'ESC')

    def test_literal_windows_escape_exits_menu(self):
        class FakeTerm:
            def __init__(self): self.frames=[]
            def size(self): return (80,24)
            def present(self,text): self.frames.append(text)
            def read_key(self): return '\x1b'
        self.assertIsNone(select_menu(FakeTerm(),'TEST',[('a','Alpha'),('b','Beta')]))

    def test_wasd_is_ignored_and_arrows_navigate(self):
        class FakeTerm:
            def __init__(self,keys): self.keys=list(keys); self.frames=[]
            def size(self): return (80,24)
            def present(self,text): self.frames.append(text)
            def read_key(self): return self.keys.pop(0)
        self.assertEqual(select_menu(FakeTerm(['w','a','s','d','DOWN','\r']),'TEST',[('a','Alpha'),('b','Beta'),('c','Gamma')]),'b')
        self.assertEqual(select_menu(FakeTerm(['UP','\r']),'TEST',[('a','Alpha'),('b','Beta'),('c','Gamma')]),'c')

    def test_escape_backs_out_of_menu(self):
        class FakeTerm:
            def size(self): return (80,24)
            def present(self,text): pass
            def read_key(self): return 'ESC'
        self.assertIsNone(select_menu(FakeTerm(),'TEST',[('a','Alpha'),('b','Beta')]))

    def test_mouse_menu_footer_is_discoverable(self):
        class FakeTerm:
            def __init__(self): self.frames=[]
            def size(self): return (80,24)
            def present(self,text): self.frames.append(text)
            def read_key(self): return '\x1b'
        term=FakeTerm();select_menu(term,'TEST',[('a','Alpha')])
        frame=term.frames[-1]
        self.assertIn('Click',frame)
        self.assertIn('Enter',frame)
        self.assertIn('Esc',frame)

class UIRC4RealFlowTests(UIRC3FlowTests):
    def test_world_console_accepts_literal_windows_escape(self):
        from worldseed.app import _world_console
        # System -> Help, then literal Windows Escape backs Help -> System -> root -> gameplay.
        term=_fake_term(['8','2','\x1b','\x1b','\x1b'])
        _world_console(self.ctx,term)
        joined='\n'.join(term.frames).lower()
        self.assertIn('help',joined)
        self.assertGreaterEqual(joined.count('world console'),2)

    def test_action_hub_can_be_driven_with_pointer_tokens(self):
        from worldseed.app import _action_palette
        # Click Work then Craft; Back returns through each route.
        term=_fake_term(['UI_SELECT:2','UI_SELECT:0','ESC','ESC','ESC'])
        _action_palette(self.ctx,term)
        joined='\n'.join(term.frames).lower()
        self.assertIn('crafting mode',joined)
        self.assertGreaterEqual(joined.count('actions'),2)


class GPUPrimaryNavigationTests(unittest.TestCase):
    """GPU candidate retains the same global key and hierarchy contracts."""

    def test_gpu_main_backend_uses_existing_main_ui_and_explicit_launcher_route(self):
        import os
        import sys
        from unittest.mock import patch
        from worldseed import app
        from worldseed.ui.gpu_terminal import GpuTerminal
        from worldseed.ui.pygame_terminal import PygameTerminal
        self.assertTrue(issubclass(GpuTerminal, PygameTerminal))
        for name in ('present_feature_menu', 'present_timed_action', 'pause_realtime',
                     'set_free_movement_callback', 'set_realtime_callback'):
            self.assertIs(getattr(GpuTerminal, name), getattr(PygameTerminal, name))
        for arguments, setting in ((['worldseed', '--gpu'], ''), (['worldseed'], 'gpu')):
            with self.subTest(arguments=arguments, setting=setting), \
                 patch.object(sys, 'argv', arguments), \
                 patch.dict(os.environ, {'WORLDSEED_UI': setting}), \
                 patch('worldseed.ui.gpu_terminal.GpuTerminal') as factory:
                factory.available.return_value = True
                self.assertIs(app._make_display_backend(), factory.return_value)
                factory.assert_called_once_with()
        with patch.object(sys, 'argv', ['worldseed', '--window']), \
             patch.dict(os.environ, {'WORLDSEED_UI': ''}), \
             patch('worldseed.ui.pygame_terminal.PygameTerminal') as legacy:
            legacy.available.return_value = True
            self.assertIs(app._make_display_backend(), legacy.return_value)
            legacy.assert_called_once_with()

    def test_gpu_enter_tab_escape_and_modal_wasd_use_shared_routing(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from worldseed.ui.gpu_gameplay_session import GpuGameplaySession
        from worldseed.ui.session import NavigationStack
        controller = Mock()
        session = GpuGameplaySession(SimpleNamespace(),SimpleNamespace(),
                                     now=0.,input_controller=controller)
        for key in 'wasd':
            session.press(key,None,now=0.)
            controller.press.assert_called_with(key,repeat=False,now=0.)
        controller.reset_mock()
        session.press('\r',None,now=1.)
        self.assertIsInstance(session.nav,NavigationStack)
        self.assertEqual(session.nav.current.route_id,'actions')
        controller.set_focus.assert_called_with(False,now=1.)
        before = session.nav.snapshot()
        for key in 'wasd': session.press(key,None,now=1.)
        self.assertEqual(session.nav.snapshot(),before)
        controller.press.assert_not_called()
        session.press('ESC',None,now=2.)
        self.assertFalse(session.modal)
        controller.set_focus.assert_called_with(True,now=2.)
        session.press('\t',None,now=3.)
        self.assertEqual(session.nav.current.route_id,'console')
        self.assertEqual({row.key for row in session.rows(None)},
                         {'character','local','system'})
        session.activate('character',None,now=3.)
        session.activate('health',None,now=3.)
        self.assertEqual(session.nav.depth,3)
        session.press('ESC',None,now=4.)
        self.assertEqual(session.nav.current.route_id,'character')
        session.press('ESC',None,now=4.)
        self.assertEqual(session.nav.current.route_id,'console')
        session.press('ESC',None,now=4.)
        self.assertFalse(session.modal)
