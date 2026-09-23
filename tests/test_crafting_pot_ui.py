import os
os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')

import unittest
from types import SimpleNamespace

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.entities.components import Inventory
from worldseed.entities.store import EntityStore
from worldseed.sim.engine import Simulation
from worldseed.sim.commands import DiscoveryPotCommand
from worldseed.systems.crafting import CraftingSystem
from worldseed.systems.state import LivingWorldState
from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.ui.widgets import MenuRow
from worldseed.app import _crafting_menu_graphical, UI_BACK


class PotRulesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=ContentRegistry.load(DATA_DIR)

    def make(self):
        state=LivingWorldState(player_crafting_discovery_enabled=True)
        inv=Inventory();inv.add('core:stone',3)
        return CraftingSystem(state,self.registry),state,inv

    def test_catalog_pool_and_browsing_are_observational(self):
        system,state,inv=self.make();before=state.to_dict();items=inv.items.copy()
        pool=system.recipe_pool_for_item('core:stone')
        self.assertIn('core:stone_flake',{r.id for r in pool})
        self.assertTrue(system.pot_candidates(('core:stone',),inv))
        self.assertEqual(state.to_dict(),before)
        self.assertEqual(inv.items,items)
        ok,_,_=system.experiment('core:stone_flake',inv)
        self.assertFalse(ok)
        self.assertEqual(state.to_dict(),before)

    def test_reproducible_result_consumes_only_placed_items_and_roundtrips(self):
        outcomes=[]
        for _ in range(2):
            system,state,inv=self.make()
            ok,msg,minutes=system.combine_in_pot(('core:stone',),inv,b'fixed-world')
            self.assertTrue(ok,msg)
            self.assertGreaterEqual(minutes,10)
            self.assertEqual(inv.count('core:stone'),2)
            restored=LivingWorldState.from_dict(state.to_dict())
            self.assertEqual(restored.player_discovered_recipes,state.player_discovered_recipes)
            self.assertEqual(restored.player_crafting_experiments,1)
            outcomes.append(state.player_discovered_recipes)
        self.assertEqual(outcomes[0],outcomes[1])

    def test_different_world_seeds_can_choose_different_results_from_one_item_pool(self):
        results=set()
        for value in range(12):
            system,state,inv=self.make()
            ok,_,_=system.combine_in_pot(('core:stone',),inv,f'world-{value}'.encode())
            self.assertTrue(ok)
            results.update(state.player_discovered_recipes)
        self.assertGreater(len(results),1)

    def test_invalid_and_exhausted_mixes_do_not_consume_items(self):
        system,state,inv=self.make()
        before=inv.items.copy()
        ok,_,_=system.combine_in_pot(('core:stone',)*4,inv,b'fixed-world')
        self.assertFalse(ok)
        self.assertEqual(inv.items,before)
        self.assertEqual(state.player_crafting_experiments,0)
        pool=system.pot_candidates(('core:stone',),inv)
        state.player_discovered_recipes=[r.id for r in pool]
        ok,_,_=system.combine_in_pot(('core:stone',),inv,b'fixed-world')
        self.assertFalse(ok)
        self.assertEqual(inv.items,before)

    def test_command_boundary_records_discovery_and_returns_action_time(self):
        system,state,_=self.make()
        entities=EntityStore();pid=entities.spawn(preferred_id=1)
        entities.add(pid,Inventory({'core:stone':2}))
        sim=Simulation.__new__(Simulation)
        sim.entities=entities;sim.crafting=system;sim.seed=b'pot-seed';sim.turn=0;sim.log=[]
        minutes=sim._discovery_pot(DiscoveryPotCommand(pid,('core:stone',)))
        self.assertEqual(len(state.player_discovered_recipes),1)
        self.assertEqual(entities.get(pid,Inventory).count('core:stone'),1)
        self.assertGreaterEqual(minutes,10)
        self.assertIn('discover',sim.log[-1].message.lower())

    def test_graphical_route_mixes_and_returns_to_tabs(self):
        system,state,inv=self.make()
        events=[]
        class FakeTerm:
            mouse_ui=True
            def __init__(self):
                self.keys=iter(('UI_ACTION:tab:discovery','UI_SELECT:0','UI_ACTION:mix','ESC'))
            def size(self):return 100,30
            def menu_page_size(self,presentation):return 5
            def present_feature_menu(self,*args,**kwargs):events.append(args[0])
            def read_key(self):return next(self.keys)
            def animate_discovery_pot(self,items,name):events.append(('animated',items,name))
        def execute(cmd):
            ok,msg,_=system.combine_in_pot(cmd.items,inv,b'fixed-world')
            sim.log.append(SimpleNamespace(message=msg))
        sim=SimpleNamespace(crafting=system,state=state,building=SimpleNamespace(nearby_station_ids=lambda p:set()),
                            player_pos=None,execute=execute,log=[])
        entities=SimpleNamespace(get=lambda actor,typ:inv)
        ctx=SimpleNamespace(sim=sim,registry=self.registry,player_id=1,entities=entities)
        self.assertEqual(_crafting_menu_graphical(ctx,FakeTerm()),UI_BACK)
        self.assertIn('discovery_pot',events)
        self.assertTrue(any(isinstance(e,tuple) and e[0]=='animated' for e in events))


@unittest.skipUnless(PygameTerminal.available(),'requires pygame-ce')
class CraftingWindowTests(unittest.TestCase):
    def setUp(self):
        self.term=PygameTerminal(1280,800);self.term.enter()
        self.pg=self.term.pg;self.pg.event.clear()

    def tearDown(self):self.term.restore()

    def target(self,token):
        return next(rect for rect,value in self.term._pointer_targets if value==token)

    def test_tabs_share_a_floating_window_and_missing_material_is_visible(self):
        missing={'name':'Stone Axe','ready':False,'missing':['Stone Flake 0/2'],
                 'inputs':[{'name':'Stone Flake','id':'core:stone_flake','have':0,'need':2}],
                 'outputs':[{'name':'Stone Axe','id':'core:stone_axe','qty':1}],
                 'minutes':35,'skill':'crafting','description':'A sharp axe.'}
        rows=[MenuRow('core:stone_axe','Stone Axe')]
        self.term.present_feature_menu('crafting_unified','CRAFTING',rows,0,data={
            'recipes':{'core:stone_axe':missing},'categories':['primitive_tools'],'category':'primitive_tools'})
        self.assertLess(self.term._floating_panels['crafting']['w'],1280)
        self.assertNotIn('UI_ACTION:craft',{token for _,token in self.term._pointer_targets})
        tab=self.target('UI_ACTION:tab:discovery')
        self.pg.event.post(self.pg.event.Event(self.pg.MOUSEBUTTONDOWN,button=1,pos=tab.center))
        self.assertEqual(self.term.read_key(),'UI_ACTION:tab:discovery')
        self.term.present_feature_menu('discovery_pot','DISCOVERY POT',[MenuRow('core:stone','Stone')],0,data={
            'items':{'core:stone':{'name':'Stone','count':2,'pool_count':2}},
            'selected_items':('core:stone',),'candidates':2})
        self.assertIn('UI_ACTION:mix',{token for _,token in self.term._pointer_targets})
        self.assertEqual(self.term._floating_panel_id,'crafting')

    def test_ready_recipe_has_craft_button_and_category_pages_fit_small_window(self):
        self.term._floating_panels['crafting']={'x':12,'y':12,'w':820,'h':540}
        cats=[f'category_{i}' for i in range(14)]
        ready={'name':'Stone Flake','ready':True,'missing':[],
               'inputs':[{'name':'Stone','id':'core:stone','have':2,'need':1}],
               'outputs':[{'name':'Stone Flake','id':'core:stone_flake','qty':2}],
               'minutes':8,'skill':'crafting','description':'Strike sharp edges.'}
        self.term.present_feature_menu('crafting_unified','CRAFTING',[MenuRow('core:stone_flake','Stone Flake')],0,
            subtitle='Recipe list',data={'recipes':{'core:stone_flake':ready},'categories':cats,
                                     'category':cats[0],'category_page':0})
        self.assertIsNotNone(self.target('UI_ACTION:craft'))
        next_page=self.target('UI_ACTION:category_page:next')
        self.pg.event.post(self.pg.event.Event(self.pg.MOUSEBUTTONDOWN,button=1,pos=next_page.center))
        self.assertEqual(self.term.read_key(),'UI_ACTION:category_page:next')

    def test_five_ingredient_pot_controls_fit_minimum_panel(self):
        self.term._floating_panels['crafting']={'x':12,'y':12,'w':740,'h':500}
        data={'items':{'core:stone':{'name':'Stone','count':5,'pool_count':2}},
              'selected_items':('core:stone',)*5,'candidates':1}
        self.term.present_feature_menu('discovery_pot','DISCOVERY POT',[MenuRow('core:stone','Stone')],0,
                                       subtitle='Pot',data=data)
        panel=self.term._floating_panels['crafting']
        mix=self.target('UI_ACTION:mix')
        self.assertGreater(mix.y,panel['y']+200)
        self.assertLess(mix.bottom,panel['y']+panel['h']-38)


if __name__=='__main__':unittest.main()
