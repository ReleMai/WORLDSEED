import unittest
from types import SimpleNamespace

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.systems.activities import ActivitySystem
from worldseed.systems.economy import EconomySystem
from worldseed.systems.physical_goods import SettlementPhysicalGoodsSystem
from worldseed.systems.professions import SettlementProfessionSystem
from worldseed.systems.resources import FeatureView
from worldseed.systems.state import (
    ContainerState, LaborReservationState, LivingWorldState, NPCState, SettlementState, pos_key,
)


class FakeWorld:
    def is_passable(self,pos):
        return True


class FakePhysicalization:
    def __init__(self,skeleton):
        self._skeleton=skeleton
    def skeleton_for(self,settlement_id):
        return self._skeleton
    def passable(self,pos,world_passable=True):
        return bool(world_passable)
    def destination_for(self,structure_id,room_id=""):
        return WorldPos(0,0,0)
    def cell_at(self,pos):
        return None


class FakeResources:
    def __init__(self,state,registry):
        self.state=state;self.registry=registry;self.revision=0
        self.tree=WorldPos(5,0,0)
    def feature_at(self,pos,minute=None):
        if (pos.x,pos.y,pos.z)!=(self.tree.x,self.tree.y,self.tree.z):
            return None
        if pos_key(pos.x,pos.y,pos.z) in self.state.resource_depletion:
            return FeatureView("core:oak_tree","stump")
        return FeatureView("core:oak_tree","mature")


def fixture_piece(uid,piece_id,structure_id,x,y):
    return SimpleNamespace(uid=uid,piece_id=piece_id,structure_plan_id=structure_id,x=x,y=y)


class Phase4ProfessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=ContentRegistry.load(DATA_DIR)

    def make(self,occupation,process_id,structure_id="work:1",piece_id=None):
        state=LivingWorldState()
        town=SettlementState(
            uid="settlement:test",name="Test",region_x=0,region_y=0,x=0,y=0,population=60,
            culture_id="culture:test",religion_id="religion:test",faction_id="faction:test",
        )
        state.settlements[town.uid]=town
        npc=NPCState(
            uid=f"npc:{occupation}",name=occupation.title(),age=32,occupation=occupation,traits=["patient"],
            x=0,y=0,z=0,settlement_id=town.uid,faction_id=town.faction_id,
            home_id="home:1",workplace_id=structure_id,work_room_id="room:work",
            work_assignment_day=0,assigned_process_id=process_id,
        )
        state.npcs[npc.uid]=npc
        pieces=[]
        if piece_id:
            pieces=[fixture_piece(f"piece:{occupation}",piece_id,structure_id,2,2)]
        parcels=[SimpleNamespace(uid="farm:1",kind="farm",cells=[(8,8),(9,8),(8,9),(9,9)])]
        skeleton=SimpleNamespace(pieces=pieces,parcels=parcels)
        world=FakeWorld();physical=FakePhysicalization(skeleton)
        activities=ActivitySystem(state,self.registry,physical,world)
        goods=SettlementPhysicalGoodsSystem(state,self.registry)
        resources=FakeResources(state,self.registry)
        professions=SettlementProfessionSystem(
            state,self.registry,b"profession-tests",world,physical,activities,goods,resources
        )
        storage=ContainerState(
            uid=f"storage:{structure_id}",x=1,y=0,z=0,owner=town.uid,
            capacity_mass_g=500000,capacity_volume_ml=500000,items={},
            name="Work Stores",kind="property",settlement_id=town.uid,
            property_id=structure_id,room_id="room:work",access="private",
        )
        state.containers[pos_key(storage.x,storage.y,storage.z)]=storage
        return state,town,npc,world,physical,activities,goods,resources,professions,storage

    def test_profession_catalog_splits_logging_and_adds_carpenter_cook(self):
        self.assertEqual(self.registry.settlement_processes["core:logging"].occupation,"lumberjack")
        self.assertEqual(self.registry.settlement_processes["core:woodcraft"].occupation,"carpenter")
        self.assertEqual(self.registry.settlement_processes["core:hearth_roast"].occupation,"cook")
        self.assertEqual(
            self.registry.settlement_pieces["core:house_hearth_piece"].workplace_role,
            "cook",
        )

    def test_aggregate_stock_materializes_once_into_physical_storage(self):
        state,town,npc,world,physical,activities,goods,resources,professions,storage=self.make(
            "carpenter","core:woodcraft",piece_id="core:carpenter_bench_piece"
        )
        town.stocks["core:wood"]=4
        row=goods.stage_from_settlement(town,storage,10,items={"core:wood":2})
        self.assertIsNotNone(row)
        self.assertEqual(town.stocks["core:wood"],2)
        self.assertEqual(storage.items["core:wood"],2)
        self.assertEqual(row.direction,"materialize")

    def test_blacksmith_plan_withdraws_real_inputs_uses_forge_and_deposits_output(self):
        state,town,npc,world,physical,activities,goods,resources,professions,storage=self.make(
            "smith","core:iron_smelt",piece_id="core:forge_piece"
        )
        storage.items.update({"core:iron_ore":2,"core:coal":1})
        tasks=professions.plan_work(npc,town,20)
        self.assertTrue(tasks)
        self.assertTrue(any(t.get("action")=="profession_withdraw" for t in tasks))
        self.assertTrue(any(t.get("kind")=="activity" for t in tasks))
        self.assertEqual(tasks[-1]["action"],"profession_deposit")
        activity=next(t for t in tasks if t.get("kind")=="activity" and t.get("on_complete")=="profession_process")
        npc.inventory={"core:iron_ore":2,"core:coal":1}
        self.assertTrue(professions.complete_process(npc,town,activity,60))
        self.assertEqual(npc.inventory.get("core:iron_ore",0),0)
        self.assertEqual(npc.inventory.get("core:coal",0),0)
        self.assertEqual(npc.inventory.get("core:iron_bloom",0),1)

    def test_carpenter_and_cook_use_physical_inputs_outputs(self):
        state,town,npc,world,physical,activities,goods,resources,professions,storage=self.make(
            "carpenter","core:woodcraft",piece_id="core:carpenter_bench_piece"
        )
        town.stocks["core:wood"]=1
        from worldseed.systems.npc_home_storage import NPCStorageAccess
        from worldseed.systems.npc_commerce import NPCCommerceSystem
        economy=EconomySystem(state,self.registry,b"trade-test",SimpleNamespace(record=lambda *a,**k:None))
        access=NPCStorageAccess(state,world,physical,None,goods)
        professions.storage_access=access
        professions.commerce=NPCCommerceSystem(state,self.registry,economy,goods,physical,access)
        npc.wealth=100
        tasks=professions.plan_work(npc,town,30)
        self.assertTrue(tasks)
        self.assertEqual(town.stocks["core:wood"],1)
        self.assertEqual(storage.items.get("core:wood",0),0)
        self.assertTrue(any(t.get('action')=='commerce_buy' for t in tasks))
        self.assertTrue(any(t.get("on_complete")=="profession_process" for t in tasks))

        state2,town2,npc2,world2,physical2,activities2,goods2,resources2,professions2,storage2=self.make(
            "cook","core:hearth_roast",piece_id="core:house_hearth_piece"
        )
        storage2.items["core:meat"]=1
        cook_tasks=professions2.plan_work(npc2,town2,30)
        self.assertTrue(any(t.get("on_complete")=="profession_process" for t in cook_tasks))

    def test_lumberjack_fells_real_tree_into_carried_inventory(self):
        state,town,npc,world,physical,activities,goods,resources,professions,storage=self.make(
            "lumberjack","core:logging",piece_id=None
        )
        tasks=professions.plan_work(npc,town,40)
        self.assertTrue(tasks)
        action=next(t for t in tasks if t.get("on_complete")=="profession_resource")
        npc.x,npc.y,npc.z=4,0,0
        self.assertTrue(professions.complete_resource(npc,town,action,80))
        self.assertIn(pos_key(5,0,0),state.resource_depletion)
        self.assertGreater(npc.inventory.get("core:wood",0),0)

    def test_farmer_plants_and_harvests_real_crop_plot(self):
        state,town,npc,world,physical,activities,goods,resources,professions,storage=self.make(
            "farmer","core:field_wheat",piece_id=None
        )
        storage.items["core:wheat_seed"]=1
        tasks=professions.plan_work(npc,town,50)
        self.assertTrue(tasks)
        plant=next(t for t in tasks if t.get("on_complete")=="profession_farm")
        reservation=state.activity_reservations[plant["reservation_uid"]]
        npc.inventory["core:wheat_seed"]=1
        npc.x,npc.y,npc.z=reservation.use_x,reservation.use_y,0
        self.assertTrue(professions.complete_farm(npc,town,plant,70))
        key=pos_key(reservation.use_x,reservation.use_y,0)
        self.assertIn(key,state.crops)
        state.crops[key].mature=True
        state.crops[key].health=100
        npc.inventory.pop("core:wheat_seed",None)
        npc.tasks=[]
        tasks2=professions.plan_work(npc,town,100)
        harvest=next(t for t in tasks2 if t.get("on_complete")=="profession_farm")
        self.assertEqual(harvest["farm_action"],"harvest")
        self.assertTrue(professions.complete_farm(npc,town,harvest,120))
        self.assertNotIn(key,state.crops)
        self.assertGreater(npc.inventory.get("core:wheat",0),0)

    def test_exact_profession_claim_replaces_aggregate_batch(self):
        state,town,npc,world,physical,activities,goods,resources,professions,storage=self.make(
            "carpenter","core:woodcraft",piece_id="core:carpenter_bench_piece"
        )
        proc=self.registry.settlement_processes["core:woodcraft"]
        reservation=LaborReservationState(
            uid=f"labor:{town.uid}:{proc.id}",settlement_id=town.uid,process_id=proc.id,
            occupation="carpenter",workers=1,assigned_day=0,active=True,
            representative_uids=[npc.uid],
        )
        state.labor_reservations[reservation.uid]=reservation
        history=SimpleNamespace(record=lambda *a,**k:None)
        economy=EconomySystem(state,self.registry,b"profession-tests",history)
        economy.attach_physical_labor_authority(professions)
        town.stocks["core:wood"]=10
        town.stocks["core:wooden_bowl"]=0
        batches=economy._run_process(town,proc,1,0,0)
        self.assertEqual(batches,0)
        self.assertEqual(town.stocks["core:wooden_bowl"],0)


if __name__=="__main__":
    unittest.main()
