"""The same command consumes physical parts and preserves their resulting grade."""
from copy import deepcopy
from types import SimpleNamespace
import unittest

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.entities.components import Inventory
from worldseed.systems.artifacts import ArtifactSystem
from worldseed.systems.crafting import CraftingSystem
from worldseed.systems.crafting_ingredients import resolve_recipe_inputs, max_recipe_batches
from worldseed.systems.metallurgy import MetallurgySystem
from worldseed.systems.state import LivingWorldState


class CraftingQualityProgressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.registry=ContentRegistry.load(DATA_DIR)

    def system(self):
        state=LivingWorldState(player_knowledge=['tech:smelting'])
        artifacts=ArtifactSystem(state,self.registry,b'quality-progression')
        metallurgy=MetallurgySystem(state,self.registry,b'quality-progression')
        return state,CraftingSystem(state,self.registry,artifacts,metallurgy)

    def test_same_recipe_refined_stock_uses_fewer_pieces_and_improves_every_stat(self):
        outputs=[]
        for stock in ({'core:metal_scraps':25,'core:wood_pieces':25,'core:hide':1},
                      {'core:iron_bloom':1,'core:wood':1,'core:hide':1}):
            state,crafting=self.system();bag=Inventory(stock.copy())
            preview=crafting.preview('core:iron_sword',bag)
            before=deepcopy(state.to_dict())
            self.assertEqual(preview['consumed'],stock)
            self.assertEqual(state.to_dict(),before)
            ok,reason,_=crafting.craft('core:iron_sword',bag,{'core:forge'})
            self.assertTrue(ok,reason)
            artifact=next(iter(state.artifacts.values()))
            effects=crafting.artifact_system.describe_effects(artifact)
            self.assertEqual(artifact.quality,preview['outputs'][0]['quality'])
            self.assertEqual(artifact.material,'core:iron')
            self.assertEqual(bag.items,{'core:iron_sword':1})
            self.assertEqual(state.metal_batches,{})
            outputs.append((artifact,effects))
        recovered,refined=outputs
        self.assertGreater(refined[0].quality,recovered[0].quality)
        self.assertGreater(refined[1]['damage_percent'],recovered[1]['damage_percent'])
        self.assertGreater(refined[1]['value_percent'],recovered[1]['value_percent'])
        self.assertLess(refined[1]['wear_rate_percent'],recovered[1]['wear_rate_percent'])

    def test_preference_changes_actual_counts_and_quality_and_mixed_parts_supplement(self):
        state,crafting=self.system()
        stock={'core:metal_scraps':25,'core:wood_pieces':25,'core:iron_bloom':1,'core:wood':1,'core:hide':1}
        bag=Inventory(stock.copy())
        refined=crafting.preview('core:iron_sword',bag,preference='refined')
        recovered=crafting.preview('core:iron_sword',bag,preference='recovered')
        self.assertNotIn('core:metal_scraps',refined['consumed'])
        self.assertNotIn('core:iron_bloom',recovered['consumed'])
        self.assertGreater(refined['material_quality'],recovered['material_quality'])
        mixed=crafting.preview('core:iron_sword',Inventory({'core:metal_scraps':3,'core:steel_billet':1,'core:wood':1,'core:hide':1}))
        self.assertEqual(mixed['consumed']['core:metal_scraps'],3)
        self.assertEqual(mixed['consumed']['core:steel_billet'],1)
        self.assertEqual(mixed['source'],'mixed')
        self.assertEqual(bag.items,stock)
        self.assertEqual(state.artifacts,{})

    def test_metal_preview_and_consumption_use_the_same_real_batch(self):
        state,crafting=self.system();metal=crafting.metallurgy
        low=metal._create_batch('core:iron_bloom','player','core:iron',2000,25,3,60,35,0,[])
        high=metal._create_batch('core:iron_bloom','player','core:iron',2000,25,3,90,95,1,[])
        bag=Inventory({'core:iron_bloom':2,'core:wood':1,'core:hide':1})
        preview=crafting.preview('core:iron_sword',bag)
        row=next(row for row in preview['ingredients'] if row['id']=='core:iron_bloom')
        self.assertEqual(row['quality'],35)
        self.assertTrue(crafting.craft('core:iron_sword',bag,{'core:forge'})[0])
        self.assertNotIn(low.uid,state.metal_batches)
        self.assertIn(high.uid,state.metal_batches)

    def test_intermediate_grade_roundtrips_and_is_used_in_downstream_recipe(self):
        state,crafting=self.system();bag=Inventory({'core:cloth_scraps':30})
        self.assertTrue(crafting.craft('core:craft_spun_yarn',bag,{'core:loom'})[0])
        yarn=[a for a in state.artifacts.values() if a.base_item=='core:spun_yarn']
        self.assertEqual(len(yarn),2)
        self.assertLess(yarn[0].quality,self.registry.items['core:spun_yarn'].crafting_quality)
        restored=LivingWorldState.from_dict(state.to_dict())
        from worldseed.systems.crafting_quality import ingredient_quality
        grade=ingredient_quality(restored,self.registry,{'core:spun_yarn':1})
        self.assertEqual(grade['material_quality'],yarn[0].quality)
        self.assertEqual(len(grade['artifact_uids']),1)

    def test_cutting_or_experimenting_spends_metal_metadata_once(self):
        for experiment in (False,True):
            with self.subTest(experiment=experiment):
                state,crafting=self.system();metal=crafting.metallurgy
                batch=metal._create_batch('core:iron_bloom','player','core:iron',2000,25,3,90,95,0,[])
                bag=Inventory({'core:iron_bloom':1})
                if experiment:
                    state.player_crafting_discovery_enabled=True
                    ok,reason,_=crafting.combine_in_pot(('core:iron_bloom',),bag,b'quality-experiment')
                else:
                    ok,reason,_=crafting.craft('core:craft_shear_iron_offcuts',bag,{'core:forge'})
                self.assertTrue(ok,reason)
                self.assertNotIn(batch.uid,state.metal_batches)
                # A later generic unit cannot reuse the grade of spent stock.
                from worldseed.systems.crafting_quality import ingredient_quality
                grade=ingredient_quality(state,self.registry,{'core:iron_bloom':1},metallurgy=metal)
                self.assertEqual(grade['material_quality'],50)

    def test_auto_prefers_usable_quality_after_condition_loss(self):
        state,crafting=self.system()
        damaged=crafting.artifact_system.create('core:spun_yarn','maker',0,quality_hint=80,
            components_override={'crafting':{'quality_version':1}})
        damaged.condition=10
        intact=crafting.artifact_system.create('core:spun_yarn','maker',1,quality_hint=60,
            components_override={'crafting':{'quality_version':1}})
        from worldseed.systems.crafting_quality import ingredient_quality
        preview=ingredient_quality(state,self.registry,{'core:spun_yarn':1})
        self.assertEqual(preview['artifact_uids'],[intact.uid])
        self.assertEqual(preview['material_quality'],60)

    def test_invalid_quality_and_conversion_content_is_rejected(self):
        from dataclasses import replace
        for fields in ({'crafting_quality':True},{'crafting_quality':101},{'crafting_source':'imaginary'}):
            registry=deepcopy(self.registry)
            registry.items['core:wood']=replace(registry.items['core:wood'],**fields)
            with self.assertRaises(ValueError):registry._validate()
        for fields in ({'input_units':{'core:wood':0}},
                       {'input_units':{'core:wood':101}},
                       {'input_units':{'core:wood':True}},
                       {'input_units':{'core:berries':5}},
                       {'material_quality':False},{'material_quality':1}):
            registry=deepcopy(self.registry)
            registry.recipes['core:iron_sword']=replace(registry.recipes['core:iron_sword'],**fields)
            with self.assertRaises(ValueError):registry._validate()

    def test_old_content_and_saved_instances_keep_safe_defaults(self):
        from worldseed.content.registry import ItemDef,RecipeDef
        item=ItemDef('mod:plain','Plain stock',10,10,1)
        recipe=RecipeDef('mod:plain','Plain recipe',{'mod:plain':1},{'mod:plain':1},1)
        self.assertEqual((item.crafting_quality,item.crafting_source),(50,''))
        self.assertEqual((recipe.input_units,recipe.material_quality),({},False))
        state=LivingWorldState.from_dict({})
        self.assertEqual(state.artifacts,{})

    def test_weighted_overlapping_roles_round_physical_pieces_once(self):
        item=SimpleNamespace(tags=('broad','narrow'),crafting_source='refined',crafting_quality=80,base_value=1)
        registry=SimpleNamespace(items={'core:stock':item})
        recipe=SimpleNamespace(inputs={},catalysts={},input_tags={'broad':3,'narrow':2},input_units={'core:stock':5},material_quality=True)
        stock={'core:stock':2}
        self.assertEqual(resolve_recipe_inputs(recipe,stock,registry),{'core:stock':1})
        self.assertEqual(resolve_recipe_inputs(recipe,stock,registry,2),{'core:stock':2})
        self.assertIsNone(resolve_recipe_inputs(recipe,stock,registry,3))
        self.assertEqual(max_recipe_batches(recipe,stock,registry,100),2)
        recipe.catalysts={'core:stock':1}
        self.assertEqual(resolve_recipe_inputs(recipe,stock,registry),{'core:stock':1})
        self.assertIsNone(resolve_recipe_inputs(recipe,stock,registry,2))

    def test_skill_bonus_preview_matches_output_and_invalid_preference_is_read_only(self):
        state,crafting=self.system();bag=Inventory({'core:cloth_scraps':30})
        preview=crafting.preview('core:craft_spun_yarn',bag,skill_level=3,work_bonus=4)
        self.assertTrue(crafting.craft('core:craft_spun_yarn',bag,{'core:loom'},skill_level=3,work_bonus=4)[0])
        self.assertEqual(next(iter(state.artifacts.values())).quality,preview['outputs'][0]['quality'])
        before=(deepcopy(state.to_dict()),bag.items.copy())
        self.assertFalse(crafting.craft('core:craft_spun_yarn',bag,{'core:loom'},preference='anything')[0])
        self.assertEqual((state.to_dict(),bag.items),before)


if __name__=='__main__':unittest.main()
