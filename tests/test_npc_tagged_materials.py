"""Shared tagged recipes conserve physical inputs in player, NPC and aggregate work."""
from copy import copy
from types import SimpleNamespace
import json
from pathlib import Path
import unittest

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.entities.components import Inventory
from worldseed.systems.crafting import CraftingSystem
from worldseed.systems.crafting_ingredients import resolve_recipe_inputs, max_recipe_batches
from worldseed.systems.economy import EconomySystem
from worldseed.systems.state import LivingWorldState
from worldseed.systems.workplace_logistics import WorkplaceLogisticsSystem


class NPCTaggedMaterialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg=ContentRegistry.load(DATA_DIR)
        cls.manifest=json.loads((Path(DATA_DIR)/"crafting_expansion.json").read_text())

    def test_all_252_misc_find_materials_have_discoverable_recipes_and_npc_jobs(self):
        self.assertEqual(len(self.manifest["misc"]),252)
        tagged={r.id:r for r in self.reg.recipes.values() if r.input_tags}
        jobs={p.recipe_id for p in self.reg.settlement_processes.values() if p.recipe_id}
        self.assertLessEqual(set(tagged),jobs)
        for entry in self.manifest["misc"]:
            iid=entry["item_id"];item=self.reg.items[iid]
            tag=f"material_source_{entry['source']}_{entry['art_family']}"
            recipe_id=f"core:reclaim_{entry['source']}_{entry['art_family']}"
            with self.subTest(item=iid):
                self.assertIn(tag,item.tags)
                self.assertIn(iid,self.reg.salvage)
                self.assertIn(recipe_id,tagged)
                recipe=tagged[recipe_id]
                self.assertIn(tag,recipe.input_tags)
                self.assertTrue(self.reg.salvage[iid].yields)
                self.assertTrue(any(tag in r.input_tags for r in tagged.values()))
                self.assertLessEqual(
                    sum(self.reg.items[k].mass_g*q for k,q in recipe.outputs.items()),
                    item.mass_g,
                )
                self.assertTrue(CraftingSystem(
                    LivingWorldState(player_crafting_discovery_enabled=True),
                    self.reg,
                ).discovery_matches(recipe,(iid,)))

    def test_tagged_npc_aggregate_consumes_mixed_real_stock(self):
        recipe=self.reg.recipes["core:strip_fibrous_plants"]
        proc=self.reg.settlement_processes["core:npc_tagged_strip_fibrous_plants"]
        state=LivingWorldState()
        economy=EconomySystem.__new__(EconomySystem)
        economy.registry=self.reg;economy.state=state
        economy.physical_labor_authorities=[];economy.workplace_logistics=None
        town=SimpleNamespace(uid="test:town",culture_id="",religion_id="",knowledge=[],
                             stocks={"core:nettles":2,"core:reed_bundle":1})
        before=dict(town.stocks)
        self.assertEqual(max_recipe_batches(recipe,town.stocks,self.reg,4),1)
        self.assertEqual(economy._run_process(town,proc,4),1)
        self.assertEqual(town.stocks.get("core:fiber"),1)
        self.assertFalse(any(qty>0 for iid,qty in town.stocks.items() if iid!="core:fiber"))
        self.assertEqual(sum(before.values()),3)

    def test_tagged_aggregate_rejects_shortage_without_changing_stock(self):
        proc=self.reg.settlement_processes["core:npc_tagged_stone_knife"]
        state=LivingWorldState()
        econ=EconomySystem.__new__(EconomySystem)
        econ.registry=self.reg;econ.state=state
        econ.physical_labor_authorities=[];econ.workplace_logistics=None
        town=SimpleNamespace(uid="test:town",culture_id="",religion_id="",knowledge=[],
                             stocks={"core:stone_flake":1,"core:stout_branch":1})
        before=dict(town.stocks)
        self.assertEqual(econ._run_process(town,proc,1),0)
        self.assertEqual(town.stocks,before)

    def test_workplace_stock_buffer_reserves_and_spends_tagged_inputs_once(self):
        state=LivingWorldState()
        logistics=WorkplaceLogisticsSystem(state,self.reg,b"tagged-market")
        proc=self.reg.settlement_processes["core:npc_tagged_strip_fibrous_plants"]
        town=SimpleNamespace(uid="test:town",stocks={"core:nettles":1,"core:reed_bundle":2})
        self.assertEqual(logistics.run_process(town,proc,2,0,0,100),1)
        self.assertEqual(town.stocks.get("core:fiber"),1)
        self.assertFalse(any(qty>0 for iid,qty in town.stocks.items() if iid!="core:fiber"))
        self.assertEqual(logistics.run_process(town,proc,2,0,0,100),0)

    def test_tagged_exact_catalyst_and_overlap_reserves_distinct_units(self):
        from worldseed.content.registry import RecipeDef
        recipe=RecipeDef("test:stock","Stock",{"core:fiber":1},{"core:plant_cordage":1},1,
                         catalysts={"core:fiber":1},
                         input_tags={"prepared_fiber":1,"spinnable_plant_fiber":1},
                         discovery_tags=("prepared_fiber","spinnable_plant_fiber"))
        stock={"core:fiber":3,"core:pasture_fiber_bundle":1}
        costs=resolve_recipe_inputs(recipe,stock,self.reg)
        self.assertIsNotNone(costs)
        self.assertEqual(sum(costs.values()),3)
        self.assertIsNone(resolve_recipe_inputs(recipe,{"core:fiber":2},self.reg))
        self.assertIsNone(resolve_recipe_inputs(recipe,stock,self.reg,2))

    def test_npc_tagged_processes_match_source_catalog(self):
        for proc in self.reg.settlement_processes.values():
            if not proc.id.startswith("core:npc_tagged_"):continue
            with self.subTest(process=proc.id):
                recipe=self.reg.recipes[proc.recipe_id]
                self.assertTrue(recipe.input_tags)
                self.assertEqual(proc.inputs,recipe.inputs)
                self.assertEqual(proc.outputs,recipe.outputs)
                self.assertEqual(proc.station,recipe.station)
                self.assertTrue(proc.occupation)


if __name__ == "__main__":
    unittest.main()
