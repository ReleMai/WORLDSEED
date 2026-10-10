"""Crafting expansion follows the existing cargo and labor authorities."""
from copy import copy
from dataclasses import replace
from types import SimpleNamespace
import json
import unittest

from tests import test_phase4_professions as fixtures
from worldseed.config import DATA_DIR
from worldseed.content.registry import RecipeDef, SettlementProcessDef
from worldseed.core.rng import hash_u64
from worldseed.systems.economy import EconomySystem
from worldseed.systems.household_economy import HouseholdEconomySystem, food_items
from worldseed.systems.salvaging import SalvagingSystem
from worldseed.systems.state import LaborReservationState, LivingWorldState


class CraftingExpansionEconomyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.Phase4ProfessionTests.setUpClass()

    def fixture(self,inputs=None,tools=None,catalysts=None):
        rows=fixtures.Phase4ProfessionTests().make("carpenter","core:authored_work",piece_id="core:carpenter_bench_piece")
        state,town,npc,world,physical,activities,goods,resources,professions,storage=rows
        registry=copy(professions.registry)
        registry.recipes=dict(registry.recipes);registry.settlement_processes=dict(registry.settlement_processes)
        recipe=RecipeDef("core:authored_recipe","Authored craft",inputs or {"core:wood":1},
                         {"core:wooden_bowl":1},32,station="core:workbench",skill="carpentry",
                         tool_qualities=tools or {},catalysts=catalysts or {})
        proc=SettlementProcessDef("core:authored_work","Authored work","carpenter",1,
                                  dict(recipe.inputs),dict(recipe.outputs),"core:wooden_bowl",
                                  recipe_id=recipe.id,station=recipe.station,minutes=recipe.minutes,
                                  skill=recipe.skill,market_target=4,consumption_days=7)
        registry.recipes[recipe.id]=recipe;registry.settlement_processes[proc.id]=proc
        professions.registry=registry;goods.registry=registry;activities.registry=registry
        professions.salvaging=SalvagingSystem(state,registry)
        economy=EconomySystem(state,registry,b"expanded-economy",SimpleNamespace(record=lambda *a,**kw:None))
        return SimpleNamespace(state=state,town=town,npc=npc,physical=physical,activities=activities,
                               professions=professions,storage=storage,registry=registry,economy=economy,proc=proc)

    def complete(self,f,task,minute=45):
        row=f.state.activity_reservations[task["reservation_uid"]]
        row.status="completed";row.completed_minute=minute
        return f.professions.complete_activity(f.npc,f.town,task,minute)

    def test_authored_recipe_uses_owned_tools_and_retains_catalyst(self):
        f=self.fixture(tools={"chop":1},catalysts={"core:stone":1})
        f.storage.items={"core:wood":1,"core:stone":1,"core:stone_axe":1}
        tasks=f.professions.plan_work(f.npc,f.town,10)
        self.assertTrue(tasks)
        withdrawal=next(t for t in tasks if t.get("action")=="profession_withdraw")
        self.assertEqual(withdrawal["items"],f.storage.items)
        work=next(t for t in tasks if t.get("on_complete")=="profession_process")
        f.npc.inventory=dict(f.storage.items);f.storage.items.clear()
        self.assertFalse(f.professions.complete_process(f.npc,f.town,work,20),"duration must finish")
        self.assertTrue(self.complete(f,work))
        self.assertEqual(f.npc.inventory,{"core:stone":1,"core:stone_axe":1,"core:wooden_bowl":1})
        self.assertEqual(f.npc.work_hours_today,1)
        xp=f.npc.skill_xp["carpentry"]
        f.npc.inventory["core:wood"]=1
        self.assertFalse(f.professions.complete_process(f.npc,f.town,work,50))
        self.assertEqual(f.npc.inventory["core:wood"],1)
        self.assertEqual(f.npc.skill_xp["carpentry"],xp)
        fresh={k:v for k,v in work.items() if k!="production_completed"}
        self.assertFalse(f.professions.complete_process(f.npc,f.town,fresh,55))
        f.npc.tasks=[fresh]
        restored=LivingWorldState.from_dict(f.state.to_dict())
        f.professions.state=restored
        npc=restored.npcs[f.npc.uid];before=dict(npc.inventory);xp=dict(npc.skill_xp)
        self.assertFalse(f.professions.complete_process(npc,restored.settlements[f.town.uid],npc.tasks[0],60))
        self.assertEqual(npc.inventory,before);self.assertEqual(npc.skill_xp,xp)

    def test_wrong_station_and_missing_tool_never_consume_materials(self):
        f=self.fixture(tools={"chop":3})
        f.storage.items={"core:wood":1}
        self.assertEqual(f.professions.plan_work(f.npc,f.town,10),[])
        self.assertEqual(f.storage.items,{"core:wood":1})
        f=self.fixture()
        f.storage.items={"core:wood":1}
        f.physical._skeleton.pieces[0].piece_id="core:forge_piece"
        self.assertFalse(f.professions.supports_physical_work(f.npc,f.town))
        self.assertEqual(f.professions.plan_work(f.npc,f.town,10),[])

    def test_named_batch_replaces_one_aggregate_labor_slot(self):
        f=self.fixture()
        uid=f"labor:{f.town.uid}:{f.proc.id}"
        f.state.labor_reservations[uid]=LaborReservationState(uid,f.town.uid,f.proc.id,"carpenter",2,0,True,[f.npc.uid])
        f.economy.attach_physical_labor_authority(f.professions)
        f.town.stocks={"core:wood":2};f.storage.items={"core:wood":1}
        self.assertEqual(f.economy._run_process(f.town,f.proc,2,0,10),1)
        self.assertEqual(f.town.stocks,{"core:wood":1,"core:wooden_bowl":1})
        tasks=f.professions.plan_work(f.npc,f.town,10)
        work=next(t for t in tasks if t.get("on_complete")=="profession_process")
        f.npc.inventory={"core:wood":1};f.storage.items.clear()
        self.assertTrue(self.complete(f,work))
        self.assertEqual(f.npc.inventory,{"core:wooden_bowl":1})
        self.assertEqual(f.town.stocks["core:wooden_bowl"]+f.npc.inventory["core:wooden_bowl"],2)

    def test_real_scrap_salvage_survives_save_and_cannot_repeat(self):
        f=self.fixture(inputs={"core:metal_scraps":2})
        f.npc.inventory={"core:bent_door_hinge":1}
        tasks=f.professions.plan_work(f.npc,f.town,10)
        salvage=next(t for t in tasks if t.get("on_complete")=="profession_salvage")
        self.assertTrue(self.complete(f,salvage))
        self.assertNotIn("core:bent_door_hinge",f.npc.inventory)
        self.assertGreaterEqual(f.npc.inventory["core:metal_scraps"],2)
        self.assertGreater(f.npc.skill_xp["salvaging"],0)
        f.npc.tasks=[salvage]
        restored=LivingWorldState.from_dict(f.state.to_dict())
        f.professions.state=restored;f.professions.salvaging.state=restored
        npc=restored.npcs[f.npc.uid];before=dict(npc.inventory)
        npc.inventory["core:bent_door_hinge"]=1
        self.assertFalse(f.professions.complete_salvage(npc,restored.settlements[f.town.uid],npc.tasks[0],55))
        self.assertEqual(npc.inventory,{**before,"core:bent_door_hinge":1})
        fresh={k:v for k,v in npc.tasks[0].items() if k!="production_completed"}
        self.assertFalse(f.professions.complete_salvage(npc,restored.settlements[f.town.uid],fresh,60))

    def test_market_demand_stops_surplus_and_consumes_actual_supplies(self):
        f=self.fixture();f.town.stocks={"core:wooden_bowl":4}
        # The legacy bowl target wins over a smaller authored target; use a
        # unique output to exercise the expansion's independently authored target.
        item=replace(f.registry.items["core:wooden_bowl"],id="core:authored_supply")
        f.registry.items=dict(f.registry.items);f.registry.items[item.id]=item
        proc=replace(f.proc,priority_good=item.id,outputs={item.id:1})
        f.registry.settlement_processes={proc.id:proc}
        f.economy=EconomySystem(f.state,f.registry,b"expanded-economy",SimpleNamespace(record=lambda *a,**kw:None))
        f.town.stocks={item.id:4}
        self.assertEqual(f.economy._shortage_score(f.town,proc),0)
        day=int(hash_u64(f.economy.seed,"goods-use",f.town.uid,item.id)%7)
        used=f.economy._consume_crafted_goods(f.town,day*1440,80)
        self.assertEqual(used,{item.id:1});self.assertEqual(f.town.stocks[item.id],3)
        self.assertEqual(next(iter(f.state.market_transactions.values())).requested,used)

    def test_authored_food_enters_real_household_consumption(self):
        f=self.fixture()
        item=replace(f.registry.items["core:bread"],id="core:authored_food")
        f.registry.items=dict(f.registry.items);f.registry.items[item.id]=item
        self.assertIn(item.id,food_items(f.registry))
        f.npc.family_uid="family:test";f.storage.property_id=f.npc.home_id;f.storage.items={item.id:2}
        household=HouseholdEconomySystem(f.state,b"foods",f.registry,f.economy)
        h=household.sync()[0];household._consume_food(h,1440)
        self.assertEqual(h.food_shortage,0);self.assertEqual(f.storage.items[item.id],1)

    def test_every_expansion_recipe_has_matching_profession_process(self):
        registry=fixtures.Phase4ProfessionTests.registry
        manifest=json.loads((DATA_DIR/"crafting_expansion.json").read_text())
        entries=manifest["recipes"]
        self.assertGreater(len(entries),200)
        self.assertEqual(len({row["profession"] for row in entries}),19)
        for entry in entries:
            recipe=registry.recipes[entry["recipe_id"]]
            proc=registry.settlement_processes["core:npc_expansion_"+recipe.id.split(":",1)[-1]]
            self.assertEqual((proc.occupation,proc.recipe_id,proc.inputs,proc.outputs,proc.station,proc.minutes),
                             (entry["profession"],recipe.id,recipe.inputs,recipe.outputs,recipe.station,recipe.minutes))

    def test_unavailable_recipe_catalog_cannot_take_staple_labor(self):
        f=self.fixture(inputs={"core:metal_scraps":2})
        unavailable=[replace(f.proc,id=f"core:unavailable_{i}") for i in range(240)]
        staple=SettlementProcessDef("core:staple_work","Staple work","carpenter",1,
                                    {"core:wood":1},{"core:wooden_bowl":1},"core:wooden_bowl")
        f.registry.settlement_processes={p.id:p for p in unavailable+[staple]}
        f.town.population=600;f.town.stocks={"core:wood":20}
        assigned=f.economy._reserve_labor(f.town,0)
        self.assertEqual(assigned,[(staple,f.town.labor_pool["carpenter"])])
        self.assertEqual(f.economy._run_process(f.town,staple,assigned[0][1],0),assigned[0][1])

    def test_unsupplied_tools_and_catalysts_cannot_reserve_anonymous_jobs(self):
        for requirements in ({"tools":{"chop":1}},{"catalysts":{"core:stone":1}}):
            with self.subTest(requirements=requirements):
                f=self.fixture(**requirements)
                f.town.stocks={"core:wood":20}
                self.assertEqual(f.economy._shortage_score(f.town,f.proc),0)
                self.assertEqual(f.economy._run_process(f.town,f.proc,10,0),0)
                self.assertEqual(f.town.stocks,{"core:wood":20})

    def test_owned_input_jobs_are_capped_and_bind_the_supplied_worker(self):
        f=self.fixture();f.npc.inventory={"core:wood":1};f.town.population=600
        unsupplied=replace(f.npc,uid="npc:aaa",home_id="home:2",workplace_id="work:2",inventory={})
        f.state.npcs[unsupplied.uid]=unsupplied
        processes=[replace(f.proc,id=f"core:owned_job_{i}") for i in range(12)]
        f.registry.settlement_processes={p.id:p for p in processes}
        f.economy.attach_physical_labor_authority(f.professions)
        # The reservation pass supplies bounded property inventories rather
        # than asking each recipe to scan the world container collection.
        f.professions._containers=lambda *args: (_ for _ in ()).throw(AssertionError("global container rescan"))
        assigned=f.economy._reserve_labor(f.town,0)
        self.assertEqual(sum(workers for _,workers in assigned),1)
        reservation=f.state.labor_reservations[f"labor:{f.town.uid}:{assigned[0][0].id}"]
        self.assertEqual(reservation.representative_uids,[f.npc.uid])
        self.assertEqual(unsupplied.assigned_process_id,"")
        restored=LivingWorldState.from_dict(f.state.to_dict())
        economy=EconomySystem(restored,f.registry,b"restore",SimpleNamespace(record=lambda *a,**kw:None))
        economy._bind_representative_labor(restored.settlements[f.town.uid],0)
        self.assertEqual(restored.labor_reservations[reservation.uid].representative_uids,[f.npc.uid])

    def test_water_drawing_requires_live_well_or_authoritative_freshwater(self):
        f=self.fixture();water=f.registry.settlement_processes["core:draw_settlement_water"]
        self.assertEqual(f.economy._run_process(f.town,water,1,0),0)
        f.economy.world=SimpleNamespace(environment_at=lambda pos:SimpleNamespace(resources=SimpleNamespace(freshwater=70)))
        self.assertEqual(f.economy._run_process(f.town,water,1,0),1)
        self.assertEqual(f.town.stocks["core:clean_water"],4)
        f.economy.world=SimpleNamespace(environment_at=lambda pos:SimpleNamespace(resources=SimpleNamespace(freshwater=0)))
        f.physical._skeleton.pieces.append(fixtures.fixture_piece("piece:well","core:stone_well_piece","water:1",3,3))
        f.economy.workplace_logistics=SimpleNamespace(physicalization=f.physical)
        f.physical.structure_by_id=lambda uid:SimpleNamespace(destroyed=True)
        self.assertFalse(f.economy.freshwater_available(f.town))
        f.physical.structure_by_id=lambda uid:SimpleNamespace(destroyed=False)
        self.assertTrue(f.economy.freshwater_available(f.town))


if __name__=="__main__":
    unittest.main()
