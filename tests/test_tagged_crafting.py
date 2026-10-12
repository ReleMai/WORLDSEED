"""Tagged ingredients consume real alternatives without overlapping reservations."""
from copy import copy
from dataclasses import replace
import unittest

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry, RecipeDef
from worldseed.entities.components import Inventory
from worldseed.systems.crafting import CraftingSystem
from worldseed.systems.state import LivingWorldState


class TaggedCraftingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=ContentRegistry.load(DATA_DIR)

    def system(self,recipe=None,items=None,*,discovery=False):
        registry=copy(self.registry)
        registry.recipes=dict(registry.recipes)
        registry.items=dict(registry.items)
        if items:
            registry.items.update(items)
        if recipe:
            registry.recipes[recipe.id]=recipe
        state=LivingWorldState(player_crafting_discovery_enabled=discovery)
        return CraftingSystem(state,registry),state

    def test_mixed_plant_scraps_to_fiber_to_finished_fishing_line(self):
        system,_=self.system()
        inv=Inventory({'core:plant_scraps':3,'core:beachgrass':2,'core:sinew_cord':1,'core:stone':1})
        for rid in ('core:reclaim_plant_fiber','core:twist_prepared_fiber','core:twist_mixed_cord_line'):
            ok,message,_=system.craft(rid,inv,set())
            self.assertTrue(ok,message)
        self.assertEqual(inv.items,{'core:stone':1,'core:fiber_line':1})
        self.assertGreater(self.registry.items['core:fiber_line'].quality('line_quality'),0)

    def test_specific_and_broad_tags_are_authored_on_existing_assets(self):
        self.assertLessEqual({'plant','plant_material','plant_scrap','fiber_source'},set(self.registry.items['core:plant_scraps'].tags))
        self.assertLessEqual({'fiber','textile','prepared_fiber','spinnable_plant_fiber'},set(self.registry.items['core:fiber'].tags))
        self.assertIn('cordage',self.registry.items['core:sinew_cord'].tags)

    def test_generic_recipe_minimum_alternative_mass_covers_outputs(self):
        for recipe in self.registry.recipes.values():
            if not recipe.input_tags:continue
            exact_mass=sum(self.registry.items[iid].mass_g*n for iid,n in recipe.inputs.items())
            minimum=exact_mass+sum(min(item.mass_g for item in self.registry.items.values() if tag in item.tags)*n
                                   for tag,n in recipe.input_tags.items())
            output=sum(self.registry.items[iid].mass_g*n for iid,n in recipe.outputs.items())
            self.assertLessEqual(output,minimum,recipe.id)

    def test_overlap_flow_reassigns_scarce_material_and_is_order_independent(self):
        recipe=RecipeDef('test:overlap','Overlap',{}, {'core:stone':1},5,
                         input_tags={'broad':1,'narrow':1},discovery_tags=('broad','narrow'))
        items={'core:fiber':replace(self.registry.items['core:fiber'],tags=('broad','narrow'),base_value=1),
               'core:brush':replace(self.registry.items['core:brush'],tags=('broad',),base_value=2)}
        system,_=self.system(recipe,items)
        outputs=[]
        for entries in ({'core:fiber':1,'core:brush':1},{'core:brush':1,'core:fiber':1}):
            inv=Inventory(entries.copy());before=inv.items.copy()
            self.assertEqual(system.resolve_inputs(recipe,inv),{'core:brush':1,'core:fiber':1})
            self.assertEqual(inv.items,before)
            self.assertTrue(system.craft(recipe.id,inv,set())[0])
            outputs.append(inv.items)
        self.assertEqual(outputs,[{'core:stone':1}]*2)

    def test_exact_tag_and_catalyst_units_cannot_be_double_counted(self):
        recipe=RecipeDef('test:reserved','Reserved',{'core:fiber':1},{'core:plant_cordage':1},5,
                         catalysts={'core:fiber':1},input_tags={'prepared_fiber':1},discovery_tags=('prepared_fiber',))
        system,_=self.system(recipe)
        for count in (1,2):
            inv=Inventory({'core:fiber':count});before=inv.items.copy()
            self.assertIsNone(system.resolve_inputs(recipe,inv))
            self.assertFalse(system.can_craft(recipe.id,inv,set())[0])
            self.assertFalse(system.craft(recipe.id,inv,set())[0])
            self.assertEqual(inv.items,before)
        inv=Inventory({'core:fiber':3})
        self.assertEqual(system.resolve_inputs(recipe,inv),{'core:fiber':2})
        self.assertTrue(system.craft(recipe.id,inv,set())[0])
        self.assertEqual(inv.items,{'core:fiber':1,'core:plant_cordage':1})

    def test_overlapping_tag_demands_cannot_count_one_stack_twice(self):
        recipe=RecipeDef('test:overlap','Overlap',{}, {'core:stone':1},5,
                         input_tags={'fiber':1,'prepared_fiber':1},discovery_tags=('fiber','prepared_fiber'))
        system,_=self.system(recipe)
        inv=Inventory({'core:fiber':1})
        self.assertIsNone(system.resolve_inputs(recipe,inv))
        self.assertEqual(sum(row['have'] for row in system.ingredient_rows(recipe,inv)),1)
        self.assertTrue(system.missing_requirements(recipe.id,inv,set()))

    def test_tag_samples_match_physical_clues_and_are_consumed_on_discovery(self):
        recipe=self.registry.recipes['core:reclaim_plant_fiber']
        system,state=self.system(discovery=True)
        inv=Inventory({'core:plant_scraps':1})
        self.assertTrue(system.discovery_matches(recipe,('core:plant_scraps',)))
        self.assertIn(recipe,system.recipe_pool_for_item('core:plant_scraps'))
        self.assertIn(recipe,system.pot_candidates(('core:plant_scraps',),inv))
        ok,message,_=system.combine_in_pot(('core:plant_scraps',),inv,b'tag-discovery',minute=42)
        self.assertTrue(ok,message)
        self.assertEqual(inv.count('core:plant_scraps'),0)
        self.assertEqual(state.player_crafting_log[-1]['minute'],42)
        self.assertEqual(state.player_crafting_log[-1]['ingredients'],['core:plant_scraps'])

    def test_partial_discovery_matching_reserves_each_overlapping_clue(self):
        recipe=RecipeDef('test:clues','Clues',{}, {'core:stone':1},5,
                         discovery_items=('core:fiber',),discovery_tags=('fiber',))
        system,_=self.system(recipe)
        self.assertTrue(system.discovery_matches(recipe,('core:fiber',),partial=True))
        self.assertFalse(system.discovery_matches(recipe,('core:fiber',)))
        self.assertTrue(system.discovery_matches(recipe,('core:fiber','core:tough_fiber')))
        self.assertFalse(system.discovery_matches(recipe,('core:tough_fiber','core:tough_fiber')))

    def test_requirement_and_discovery_queries_are_observational(self):
        system,state=self.system(discovery=True)
        inv=Inventory({'core:plant_scraps':5});before=state.to_dict();carried=inv.items.copy()
        recipe=self.registry.recipes['core:reclaim_plant_fiber']
        system.ingredient_rows(recipe,inv);system.resolve_inputs(recipe,inv)
        system.recipe_pool_for_item('core:plant_scraps');system.pot_candidates(('core:plant_scraps',),inv)
        system.discovery_tree_rows(inv);system.missing_requirements(recipe.id,inv,set())
        self.assertEqual(state.to_dict(),before)
        self.assertEqual(inv.items,carried)

    def test_invalid_tag_definitions_and_discovery_signatures_are_rejected(self):
        base=RecipeDef('test:invalid','Invalid',{}, {'core:stone':1},5,discovery_tags=('fiber',))
        for changes in ({'input_tags':{'missing_material_tag':1}}, {'input_tags':{'fiber':0}},
                        {'input_tags':{'fiber':True}}, {'input_tags':{'fiber':1.5}},
                        {'discovery_tags':('missing_material_tag',)}, {'discovery_tags':('fiber',)*6}):
            with self.subTest(changes=changes):
                recipe=replace(base,**changes);system,_=self.system(recipe)
                with self.assertRaises(ValueError):system.registry._validate()

    def test_tagged_recipes_cannot_enter_exact_settlement_production(self):
        from worldseed.systems.economy import EconomySystem
        from worldseed.systems.professions import SettlementProfessionSystem
        recipe=RecipeDef('test:tagged_production','Tagged production',{'core:wood':1},{'core:plant_cordage':1},5,
                         input_tags={'prepared_fiber':1},discovery_tags=('prepared_fiber',))
        system,_=self.system(recipe)
        proc=replace(next(iter(self.registry.settlement_processes.values())),recipe_id=recipe.id,
                     inputs=recipe.inputs,outputs=recipe.outputs,station=None,occupation='carpenter')
        system.registry.settlement_processes=dict(system.registry.settlement_processes,**{proc.id:proc})
        with self.assertRaisesRegex(ValueError,'tagged ingredients'):
            system.registry._validate()
        economy=EconomySystem.__new__(EconomySystem);economy.registry=system.registry
        self.assertFalse(economy._recipe_prerequisites(None,proc))
        professions=SettlementProfessionSystem.__new__(SettlementProfessionSystem);professions.registry=system.registry
        self.assertFalse(professions._supports_process(proc))

    def test_existing_exact_recipe_signature_and_cost_are_unchanged(self):
        recipe=self.registry.recipes['core:plant_cordage'];system,_=self.system()
        self.assertEqual(recipe.inputs,{'core:brush':2})
        self.assertFalse(recipe.input_tags)
        self.assertEqual(system.discovery_signature(recipe),('core:brush','core:brush'))
        inv=Inventory({'core:brush':2})
        self.assertEqual(system.resolve_inputs(recipe,inv),recipe.inputs)
        self.assertTrue(system.craft(recipe.id,inv,set())[0])
        self.assertEqual(inv.items,{'core:plant_cordage':1})


if __name__=='__main__':unittest.main()
