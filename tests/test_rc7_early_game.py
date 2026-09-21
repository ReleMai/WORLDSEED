import tempfile
import unittest
from pathlib import Path

from worldseed.app import _load_context, _find_spawn
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory, Position, Vitals
from worldseed.entities.store import EntityStore
from worldseed.persistence.database import WorldDatabase
from worldseed.sim.commands import CookMealCommand, ProcessCarcassCommand, StartProcessingCommand, WaitCommand, RangedAttackCommand
from worldseed.sim.engine import Simulation
from worldseed.systems.resources import ResourceSystem
from worldseed.systems.state import LivingWorldState, CarcassState, StructureInstance, CreatureState, pos_key
from worldseed.ui.screens import health_screen
from worldseed.ui.startup import StartSelection
from worldseed.world.generator import WorldGenerator
from worldseed.world.world import World


class RC7EarlyGameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg = ContentRegistry.load(DATA_DIR)

    def make_sim(self, seed=b'rc7', inv=None, pos=WorldPos(0,0,0)):
        td=tempfile.TemporaryDirectory();db=WorldDatabase.create(Path(td.name)/'world.db','RC7',seed.hex())
        world=World(WorldGenerator(seed,self.reg),self.reg,db);entities=EntityStore();pid=entities.spawn(preferred_id=1)
        entities.add(pid,Position(pos));entities.add(pid,Inventory(dict(inv or {})));entities.add(pid,Vitals())
        state=LivingWorldState();state.player_skills['hunting']=5;state.player_skills['crafting']=4;state.player_skills['survival']=4
        sim=Simulation(world,entities,self.reg,0,state,seed)
        return td,db,world,entities,pid,sim

    def test_content_depth_and_prose(self):
        r=self.reg
        self.assertGreaterEqual(len(r.items),100);self.assertGreaterEqual(len(r.recipes),45)
        self.assertGreaterEqual(len(r.structures),20);self.assertGreaterEqual(len(r.crops),8)
        self.assertGreaterEqual(len(r.resources),20);self.assertGreaterEqual(len(r.species),15)
        self.assertGreaterEqual(len(r.cooking_methods),4)
        self.assertTrue(all(i.description.strip() and i.flavor.strip() for i in r.items.values()))
        self.assertTrue(all(s.description.strip() and s.uses for s in r.structures.values()))

    def test_new_character_starts_with_nothing(self):
        build={'attributes':{'strength':5,'agility':5,'endurance':5,'intellect':5,'perception':5,'will':5},
               'skills':{'athletics':0,'survival':0,'foraging':0,'woodcutting':0,'mining':0,'hunting':0,'melee':0,'crafting':0,'medicine':0,'scholarship':0,'persuasion':0,'trading':0,'naturalism':0,'arcana':0},'talents':[]}
        with tempfile.TemporaryDirectory() as td:
            sel=StartSelection(Path(td)/'empty.db',True,'Empty',b'empty-start'.hex(),'Nobody','custom',build)
            ctx=_load_context(sel,prepare_world=False)
            try:self.assertEqual(ctx.entities.get(ctx.player_id,Inventory).items,{})
            finally:ctx.db.close()

    def test_primitive_bootstrap_graph_has_no_wood_before_axe_dependency(self):
        r=self.reg
        axe=[x for x in r.recipes.values() if 'core:stone_axe' in x.outputs]
        self.assertEqual(len(axe),1)
        self.assertNotIn('core:wood',axe[0].inputs)
        self.assertIn('core:stone_flake',axe[0].inputs);self.assertIn('core:stout_branch',axe[0].inputs)
        self.assertTrue(any('core:plant_cordage' in x.outputs for x in r.recipes.values()))
        self.assertTrue(any('core:stone_flake' in x.outputs for x in r.recipes.values()))

    def test_dynamic_meal_inherits_ingredient_nutrition(self):
        td,db,world,e,pid,sim=self.make_sim(b'meal',{'core:raw_game_meat':1,'core:wild_carrot':1,'core:animal_fat':1,'core:clay_pot':1})
        try:
            p=sim.player_pos;sim.state.structures[pos_key(p.x+1,p.y,p.z)]=StructureInstance('core:campfire',p.x+1,p.y,p.z)
            sim.environment.add_water(p,100)
            sim.execute(CookMealCommand(pid,'core:stew',('core:raw_game_meat','core:wild_carrot','core:animal_fat')))
            meal=next(iter(sim.state.prepared_meals.values()))
            self.assertGreater(meal.calories,0);self.assertGreater(meal.protein,0);self.assertGreater(meal.fat,0)
            self.assertIn('protein',meal.food_groups);self.assertIn('vegetable',meal.food_groups);self.assertIn('fats',meal.food_groups)
        finally:db.close();td.cleanup()

    def test_broth_can_use_noncaloric_bone_and_herb(self):
        td,db,world,e,pid,sim=self.make_sim(b'broth',{'core:bone':1,'core:yarrow':1,'core:clay_pot':1})
        try:
            p=sim.player_pos;sim.state.structures[pos_key(p.x+1,p.y,p.z)]=StructureInstance('core:campfire',p.x+1,p.y,p.z);sim.environment.add_water(p,100)
            ok,why=sim.food.can_cook('core:broth',['core:bone','core:yarrow'],e.get(pid,Inventory),sim.building.nearby_station_ids(p),True)
            self.assertTrue(ok,why)
        finally:db.close();td.cleanup()

    def test_skinning_before_butchery_preserves_more_hide(self):
        def run(order):
            td,db,world,e,pid,sim=self.make_sim(b'carcass-'+order.encode(),{'core:stone_knife':1})
            c=CarcassState('c','core:deer',0,0,0,0,100);sim.state.carcasses[c.uid]=c;inv=e.get(pid,Inventory)
            for action in order.split(','):sim.processing.process_carcass('c',action,inv,5,0)
            got=inv.count('core:fresh_hide');db.close();td.cleanup();return got
        self.assertGreater(run('skin,butcher'),run('butcher,skin'))

    def test_timed_hide_drying_completes_into_ground_output(self):
        td,db,world,e,pid,sim=self.make_sim(b'dryhide',{'core:scraped_hide':1})
        try:
            p=sim.player_pos;sim.state.structures[pos_key(p.x+1,p.y,p.z)]=StructureInstance('core:drying_rack',p.x+1,p.y,p.z)
            sim.execute(StartProcessingCommand(pid,'dry_hide'));self.assertTrue(sim.state.processing_jobs)
            sim.execute(WaitCommand(pid,12*60+5))
            self.assertTrue(any(pile.items.get('core:rawhide',0)>0 for pile in sim.state.ground_piles.values()))
        finally:db.close();td.cleanup()

    def test_crop_soil_demands_are_not_all_identical(self):
        rows={(c.nitrogen,c.phosphorus,c.potassium,c.disease_family) for c in self.reg.crops.values()}
        self.assertGreaterEqual(len(rows),5)

    def test_authored_animals_have_attacks_carcass_and_description(self):
        for sp in self.reg.species.values():
            self.assertTrue(sp.description.strip(),sp.id);self.assertTrue(sp.attacks,sp.id);self.assertTrue(sp.carcass,sp.id)
            self.assertGreater(sp.mass_kg,0);self.assertGreater(sp.max_hp,0)

    def test_structures_have_declared_utility(self):
        for s in self.reg.structures.values():self.assertTrue(s.uses,s.id)
        self.assertGreater(self.reg.structures['core:sleeping_mat'].comfort,0)
        self.assertGreater(self.reg.structures['core:campfire'].warmth,0)
        self.assertGreater(self.reg.structures['core:crude_work_surface'].work_bonus,0)
        self.assertGreater(self.reg.structures['core:brush_lean_to'].shelter,0)

    def test_nutrition_visible_in_health_pane(self):
        td,db,world,e,pid,sim=self.make_sim(b'nutrition',{'core:blueberries':1})
        try:
            sim.nutrition.consume_item('core:blueberries',e.get(pid,Vitals),sim.clock.minute)
            text=health_screen(sim)
            self.assertIn('NUTRITION & DIET',text);self.assertIn('Protein',text);self.assertIn('Fruit',text);self.assertIn('Recent diet',text)
        finally:db.close();td.cleanup()

    def test_farming_requires_tilling_tool(self):
        td,db,world,e,pid,sim=self.make_sim(b'till')
        try:
            sim.world.set_terrain(sim.player_pos,'core:grass');sim.till();self.assertNotEqual(sim.world.tile_at(sim.player_pos).terrain_id,'core:tilled_soil')
            e.get(pid,Inventory).add('core:digging_stick',1);sim.till();self.assertEqual(sim.world.tile_at(sim.player_pos).terrain_id,'core:tilled_soil')
        finally:db.close();td.cleanup()

    def test_ranged_hunting_consumes_ammo(self):
        td,db,world,e,pid,sim=self.make_sim(b'ranged',{'core:sling':1,'core:sling_stone':5})
        try:
            c=CreatureState('target','core:rabbit',1,0,0,20);sim.state.creatures[c.uid]=c;before=e.get(pid,Inventory).count('core:sling_stone')
            sim.execute(RangedAttackCommand(pid,c.uid));self.assertEqual(e.get(pid,Inventory).count('core:sling_stone'),before-1)
        finally:db.close();td.cleanup()

    def test_environmental_furniture_bonuses_are_mechanical(self):
        td,db,world,e,pid,sim=self.make_sim(b'furniture')
        try:
            p=sim.player_pos
            sim.state.structures[pos_key(p.x+1,p.y,p.z)]=StructureInstance('core:campfire',p.x+1,p.y,p.z)
            sim.state.structures[pos_key(p.x,p.y+1,p.z)]=StructureInstance('core:brush_lean_to',p.x,p.y+1,p.z)
            sim.state.structures[pos_key(p.x-1,p.y,p.z)]=StructureInstance('core:sleeping_mat',p.x-1,p.y,p.z)
            b=sim.building.environmental_bonuses(p);self.assertGreater(b['warmth'],0);self.assertGreater(b['shelter'],0);self.assertGreater(b['comfort'],0)
        finally:db.close();td.cleanup()

    def test_rc7_state_roundtrip_preserves_food_processing_and_diet(self):
        from worldseed.systems.state import LivingWorldState, CarcassState, ProcessingJobState, PreparedMealState
        st=LivingWorldState()
        st.carcasses["c1"]=CarcassState("c1","core:rabbit",1,2,0,100,88)
        st.processing_jobs["j1"]=ProcessingJobState("j1","dry_meat","1,2,0","player",100,820,{"core:raw_small_game":1},{"core:dried_meat":1})
        st.prepared_meals["m1"]=PreparedMealState("m1","Rabbit Roast","core:roast","player",100,["core:raw_small_game"],1,30,0,180,24,0,8,0,{"protein":2},{"recovery":1},1540)
        st.player_diet_history=[{"minute":100,"name":"Rabbit Roast","calories":180,"groups":{"protein":2}}]
        clone=LivingWorldState.from_dict(st.to_dict())
        self.assertIn("c1",clone.carcasses)
        self.assertIn("j1",clone.processing_jobs)
        self.assertEqual(clone.prepared_meals["m1"].protein,24)
        self.assertEqual(clone.player_diet_history[-1]["name"],"Rabbit Roast")

    def test_resource_yields_reference_defined_items(self):
        for f in self.reg.resources.values():
            for iid in f.yields:self.assertIn(iid,self.reg.items,f'{f.id}->{iid}')


if __name__=='__main__':unittest.main()

# RC7 preservation regression tests appended during release hardening.
class RC7PreservationTests(unittest.TestCase):
    def test_prepared_meals_have_finite_shelf_life(self):
        reg=ContentRegistry.load(DATA_DIR)
        from worldseed.systems.state import LivingWorldState
        from worldseed.systems.food import NutritionSystem, CookingSystem
        from worldseed.entities.components import Inventory
        st=LivingWorldState(); inv=Inventory({'core:raw_game_meat':1})
        cook=CookingSystem(st,reg,NutritionSystem(st,reg))
        ok,msg,minutes,uid=cook.cook('core:roast',['core:raw_game_meat'],inv,{'core:campfire'},False,100)
        self.assertTrue(ok,msg)
        self.assertGreater(st.prepared_meals[uid].spoil_minute,100)
        self.assertLessEqual(st.prepared_meals[uid].spoil_minute,100+48*60)

    def test_old_carcass_loses_processing_value(self):
        reg=ContentRegistry.load(DATA_DIR)
        from worldseed.systems.state import LivingWorldState, CarcassState
        from worldseed.systems.processing import ProcessingSystem
        from worldseed.entities.components import Inventory
        class Buildings:
            pass
        st=LivingWorldState(); st.carcasses['old']=CarcassState('old','core:deer',0,0,0,0,70)
        inv=Inventory({'core:stone_knife':1})
        proc=ProcessingSystem(st,reg,Buildings())
        ok,msg,_=proc.process_carcass('old','butcher',inv,0,4*1440)
        self.assertFalse(ok)
        self.assertIn('spoiled',msg.lower())
