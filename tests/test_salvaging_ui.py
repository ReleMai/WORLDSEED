import copy
import os
import unittest
from dataclasses import replace
from types import SimpleNamespace

os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')

from worldseed.app import _crafting_menu_graphical, _salvaging_menu, _salvage_preview_ui_data, UI_BACK
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry, SalvageDef, SalvageRareYield
from worldseed.entities.components import Inventory
from worldseed.sim.commands import StartSalvageCommand, SalvageActionCommand
from worldseed.systems.crafting import CraftingSystem
from worldseed.systems.salvaging import SalvagingSystem
from worldseed.systems.state import LivingWorldState
from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.ui.widgets import MenuRow, select_menu


class SalvagingRoutesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.registry=ContentRegistry.load(DATA_DIR)

    def make(self):
        reg=copy.copy(self.registry)
        reg.salvage={
            'core:wood':SalvageDef('test:wood','core:wood',8,1,{'core:bark':(1,3)},
                                  (SalvageRareYield('core:iron_ore',1,1,5),),method='carve',description='Dry grain and a resin pocket.'),
            'core:stone':SalvageDef('test:stone','core:stone',8,1,{'core:stone_flake':(1,2)},method='crush',description='A brittle surface.'),
        }
        state=LivingWorldState(player_crafting_discovery_enabled=True)
        inv=Inventory({'core:wood':2,'core:stone':1})
        crafting=CraftingSystem(state,reg);salvaging=SalvagingSystem(state,reg)
        commands=[]
        sim=SimpleNamespace(state=state,crafting=crafting,salvaging=salvaging,log=[],
                            player_skill=lambda key:state.player_skills.get(key,0),
                            building=SimpleNamespace(nearby_station_ids=lambda pos:set()),player_pos=None)
        def execute(command):
            commands.append(command)
            if isinstance(command,StartSalvageCommand):ok,message,_=salvaging.begin(command.item_id,inv,b'ui-salvage')
            elif isinstance(command,SalvageActionCommand):ok,message,_=salvaging.act(command.choice_id,inv,b'ui-salvage')
            else:self.fail(type(command))
            self.assertTrue(ok,message);sim.log.append(SimpleNamespace(message=message))
        sim.execute=execute
        ctx=SimpleNamespace(sim=sim,registry=reg,player_id=1,entities=SimpleNamespace(get=lambda actor,typ:inv))
        return ctx,state,inv,commands

    def term(self,keys,graphical=False,legacy=False):
        class FakeTerm:
            def __init__(self):self.keys=iter(keys);self.frames=[];self.events=[];self.mouse_ui=graphical and not legacy
            def size(self):return 42,16
            def present(self,text):self.frames.append(text)
            def read_key(self):return next(self.keys)
        term=FakeTerm()
        if graphical:
            term.menu_page_size=lambda presentation:5
            term.present_feature_menu=lambda presentation,title,rows,selected,**kwargs:term.events.append((presentation,title,selected,kwargs.get('data',{})))
        return term

    def test_preview_back_preserves_catalogue_selection_and_does_not_mutate(self):
        ctx,state,inv,commands=self.make();before=state.to_dict();items=inv.items.copy()
        term=self.term(['DOWN','\r','ESC','ESC'],True,legacy=True)
        self.assertEqual(_salvaging_menu(ctx,term),UI_BACK)
        modes=[(event[3]['mode'],event[2]) for event in term.events]
        self.assertEqual(modes[-2:],[('preview',0),('catalogue',1)])
        self.assertEqual(state.to_dict(),before);self.assertEqual(inv.items,items);self.assertEqual(commands,[])

    def test_escape_preserves_active_work_and_each_parent_selection(self):
        ctx,state,inv,commands=self.make()
        term=self.term(['DOWN','\r','DOWN','\r','ESC','ESC','ESC'],True,legacy=True)
        _salvaging_menu(ctx,term)
        self.assertEqual(inv.count('core:wood'),1)
        self.assertEqual(len(commands),1)
        self.assertEqual(state.player_salvage_session['phase'],'inspection')
        preview=next(event for event in reversed(term.events) if event[3]['mode']=='preview')
        catalogue=term.events[-1]
        self.assertEqual(preview[2],1)
        # Resume is inserted above the selected item; preserve item identity.
        self.assertEqual(catalogue[3]['mode'],'catalogue')
        self.assertEqual(catalogue[2],2)
        self.assertEqual(LivingWorldState.from_dict(state.to_dict()).player_salvage_session,state.player_salvage_session)

    def test_resume_runs_three_decisions_and_result_escape_returns_one_level(self):
        ctx,state,inv,commands=self.make()
        ctx.sim.execute(StartSalvageCommand(1,'core:wood'))
        term=self.term([],True,legacy=True)
        def read():
            mode=term.events[-1][3]['mode']
            if mode=='catalogue':return '\r' if state.player_salvage_session else 'ESC'
            if mode=='result':return 'ESC'
            session=ctx.sim.salvaging.session_view()
            if session['phase']=='inspection':return 'UI_SELECT:0'
            correct=ctx.sim.salvaging._stage(state.player_salvage_session,ctx.registry.salvage['core:wood'])['correct']
            index=next(i for i,row in enumerate(session['choices']) if row['id']==correct)
            return f'UI_SELECT:{index}'
        term.read_key=read
        self.assertEqual(_salvaging_menu(ctx,term),UI_BACK)
        self.assertFalse(state.player_salvage_session)
        self.assertEqual(state.player_salvage_log[-1]['score'],6)
        self.assertGreater(inv.count('core:bark'),0)
        self.assertEqual(len(commands),5)
        self.assertEqual([event[3]['mode'] for event in term.events][-2:],['result','catalogue'])

    def test_preview_never_discloses_unknown_recipe_names(self):
        ctx,state,inv,_=self.make()
        data=_salvage_preview_ui_data(ctx.registry,ctx.sim,inv,'core:wood')
        self.assertTrue(data['rare'])
        self.assertTrue(all(not row['uses'] for row in data['guaranteed']+data['rare']))

    def test_terminal_full_minigame_cues_and_result_fit_with_long_item_name(self):
        ctx,state,inv,commands=self.make()
        ctx.registry.items=dict(ctx.registry.items)
        ctx.registry.items['core:wood']=replace(ctx.registry.items['core:wood'],name='Weathered Decorated Wagon Shoulder Bracket')
        term=self.term(['DOWN','\r','DOWN','\r','\r','\r','\r','\r','ESC','ESC','ESC'])
        self.assertEqual(_salvaging_menu(ctx,term),UI_BACK)
        self.assertEqual(len(commands),5)
        for frame in term.frames:
            self.assertLessEqual(len(frame.splitlines()),16,frame)
            self.assertTrue(all(len(line)<=42 for line in frame.splitlines()),frame)

    def test_salvaging_skill_is_available_in_character_point_buy(self):
        from worldseed.ui.startup import SKILL_DEFS, _random_build
        self.assertIn('salvaging',{key for key,_,_ in SKILL_DEFS})
        self.assertIn('salvaging',_random_build()['skills'])

    def test_terminal_search_and_inspection_fit_narrow_viewport(self):
        ctx,state,inv,commands=self.make();before=state.to_dict()
        term=self.term(['END','\r','w','o','o','d','\r','HOME','\r','ESC','ESC'])
        self.assertEqual(_salvaging_menu(ctx,term),UI_BACK)
        self.assertTrue(any('wood' in frame for frame in term.frames))
        for frame in term.frames:
            self.assertLessEqual(len(frame.splitlines()),16,frame)
            self.assertTrue(all(len(line)<=42 for line in frame.splitlines()),frame)
        self.assertEqual(state.to_dict(),before);self.assertEqual(commands,[])

    def test_graphical_salvaging_tab_escape_restores_recipe_surface(self):
        ctx,state,inv,commands=self.make();before=state.to_dict()
        term=self.term(['UI_ACTION:tab:salvaging','ESC','ESC'],True)
        self.assertEqual(_crafting_menu_graphical(ctx,term),UI_BACK)
        self.assertEqual([event[0] for event in term.events],['crafting_unified','salvaging_unified','crafting_unified'])
        self.assertEqual(state.to_dict(),before);self.assertEqual(commands,[])


@unittest.skipUnless(PygameTerminal.available(),'requires pygame-ce')
class SalvagingGraphicalTests(unittest.TestCase):
    def setUp(self):self.term=PygameTerminal(800,520);self.term.enter()
    def tearDown(self):self.term.restore()

    def test_salvage_controls_and_every_paged_recipe_stay_inside_small_panel(self):
        self.term._floating_panels['crafting']={'x':12,'y':12,'w':740,'h':500}
        data={'mode':'session','phase':'disassembly','name':'Old Chair','step':1,'score':2,
              'cue':'The grain marks clean cuts; split along it to preserve the wood.',
              'prompt':'Disassemble the material','choices':[{'id':str(i),'label':label,'description':'Choose carefully.'} for i,label in enumerate(('Carve along grain','Strip layers','Crush carefully'))]}
        rows=[MenuRow(row['id'],row['label']) for row in data['choices']]
        self.term.present_feature_menu('salvaging','SALVAGING',rows,0,data=data)
        panel=self.term._floating_panels['crafting'];bounds=self.term.pg.Rect(panel['x'],panel['y'],panel['w'],panel['h'])
        self.assertEqual(len([t for _,t in self.term._pointer_targets if t.startswith('UI_SELECT:')]),3)
        self.assertTrue(all(bounds.contains(rect) for rect,_ in self.term._pointer_targets))
        capacity=self.term.menu_page_size('crafting_unified')
        ready={'name':'Test','ready':False,'outputs':[],'inputs':[],'missing':[]}
        recipe_rows=[MenuRow(str(i),'Test') for i in range(capacity)]
        self.term.present_feature_menu('crafting_unified','CRAFTING',recipe_rows,0,subtitle='Browse learned recipes',
                                       data={'recipes':{str(i):ready for i in range(capacity)},'categories':[str(i) for i in range(20)],'category':'0'})
        self.assertEqual(len([t for _,t in self.term._pointer_targets if t.startswith('UI_SELECT:')]),capacity)
        self.assertIn('UI_ACTION:tab:salvaging',{t for _,t in self.term._pointer_targets})
        self.assertIn('UI_ACTION:search',{t for _,t in self.term._pointer_targets})


if __name__=='__main__':unittest.main()
