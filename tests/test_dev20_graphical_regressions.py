"""Exercise real SDL draws: hook-only tests cannot catch renderer TypeErrors."""
import os
os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')
import unittest
from pathlib import Path
from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.ui.widgets import MenuRow
from worldseed.entities.components import Inventory

@unittest.skipUnless(PygameTerminal.available(), 'pygame-ce required for graphical tests')
class GraphicalRegressionTests(unittest.TestCase):
    def setUp(self):
        from tests.test_ui_rc2 import UIRC3FlowTests
        self.fixture=UIRC3FlowTests();self.fixture.setUp()
        self.term=PygameTerminal();self.term.enter()
    def tearDown(self):
        self.term.pg.quit();self.fixture.tearDown()
    def test_crafting_and_inventory_draws_with_real_content_are_observational(self):
        from worldseed.app import (_recipe_ui_data,_design_ui_data,_inventory_ui_data,
            _crafting_home_ui_data,_crafting_material_ui_data,_crafting_tree_ui_data)
        f=self.fixture;t=self.term;inv=f.entities.get(f.pid,Inventory)
        before=f.sim.state.to_dict();before_inv=dict(inv.items)
        recipes=list(f.reg.recipes.values());recipe=next(r for r in recipes if r.inputs and r.outputs)
        rd=_recipe_ui_data(f.reg,f.sim,inv,[recipe]);rd['recipe_id']=recipe.id
        rr=[MenuRow(recipe.id,recipe.name)]
        t._present_crafting_home('Crafting',rr,0,data=_crafting_home_ui_data(f.reg,f.sim,inv,recipes,[]))
        t._present_crafting_categories('Categories',[MenuRow('general','General')],0,data={'counts':{'general':1}})
        for method in (t._present_crafting_recipes,t._present_crafting_experiments,t._present_crafting_recipe_detail):
            method('Recipe',rr,0,data=rd)
        dd=_design_ui_data(f.reg,inv,list(f.reg.designs.values()));did=next(iter(dd['designs']))
        design=dd['designs'][did];slot=design['slots'][0];iid=slot['choices'][0]['id']
        dd.update(design_id=did,slot=slot['name'])
        t._present_crafting_designs('Designs',[MenuRow(did,design['name'])],0,data=dd)
        t._present_crafting_component_choices('Components',[MenuRow(iid,iid)],0,data=dd)
        t._present_crafting_materials('Materials',data=_crafting_material_ui_data(f.reg,f.sim))
        t._present_crafting_tree('Tree',data=_crafting_tree_ui_data(f.reg,f.sim,inv))
        data=_inventory_ui_data(f.reg,inv,f.sim);iid=next(iter(data['items']));data['item_id']=iid
        for method in (t._present_inventory_home,t._present_inventory_items,t._present_inventory_item_actions):
            method('Inventory',[MenuRow(iid,iid)],0,data=data)
        t._present_inventory_item_detail('Item',data=data)
        self.assertEqual(before,f.sim.state.to_dict());self.assertEqual(before_inv,inv.items)

@unittest.skipUnless(PygameTerminal.available(), 'pygame-ce required for graphical tests')
class GraphicalAssetTests(unittest.TestCase):
    # Asset loading/gallery checks do not need a generated simulation fixture.
    def setUp(self):
        self.term=PygameTerminal();self.term.enter()

    def tearDown(self):
        self.term.restore()

    def test_character_assets_have_alpha_and_supported_canvases(self):
        t=self.term
        paths=t._visuals.player_paths('male')+t._visuals.player_paths('female')
        self.assertEqual(len(paths),20)
        for path in paths:
            surf=t.pg.image.load(str(path)).convert_alpha()
            # The documented roster refresh replaces the first three looks
            # per sex with 100x144 NPC artwork; legacy looks remain 160x256.
            expected=(100,144) if 'npc_rework' in path.parts else (160,256)
            self.assertEqual(surf.get_size(),expected,str(path))
            self.assertEqual(surf.get_at((0,0)).a,0)
            bounds=surf.get_bounding_rect(min_alpha=16)
            self.assertGreater(bounds.top,0);self.assertLess(bounds.bottom,surf.get_height())
            for size in (28,56,240):
                rendered=t._load_sprite(path,size,size*2)
                self.assertIsNotNone(rendered)
        for sex in ('male','female'):
            t.present_sprite_gallery('Appearance',sex=sex,selected=8,labels=[f'Look {i+1:02}' for i in range(10)])
