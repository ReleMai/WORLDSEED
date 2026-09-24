import unittest

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.systems.economy import EconomySystem
from worldseed.systems.state import ContainerState, LaborReservationState, LivingWorldState, NPCState, SettlementState
from worldseed.systems.workplace_logistics import WorkplaceLogisticsSystem


class NullHistory:
    def record(self,*args,**kwargs):return None


class WorkplaceLogisticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.registry=ContentRegistry.load(DATA_DIR)

    def fixture(self,occupation="smith",process_id="core:iron_smelt",workplace="shop:1",items=None,stocks=None,workers=None):
        state=LivingWorldState()
        town=SettlementState(
            uid="town:1",name="Test",region_x=0,region_y=0,x=10,y=10,population=20,
            culture_id="",religion_id="",faction_id="faction:1",wealth=500,stocks=dict(stocks or {}),
        )
        state.settlements[town.uid]=town
        npc=NPCState(
            "npc:1","Worker",30,occupation,[],12,12,0,town.uid,town.faction_id,
            workplace_id=workplace,assigned_process_id=process_id,work_assignment_day=1,
        )
        state.npcs[npc.uid]=npc
        proc=self.registry.settlement_processes[process_id]
        workers=workers if workers is not None else proc.workers
        state.labor_reservations[f"labor:{town.uid}:{proc.id}"]=LaborReservationState(
            f"labor:{town.uid}:{proc.id}",town.uid,proc.id,proc.occupation,workers,1,True,[npc.uid]
        )
        storage=ContainerState(
            "storage:1",13,13,0,npc.uid,200000,200000,items=dict(items or {}),
            name="Work Stores",kind="property",property_id=workplace,
        )
        state.containers["13,13,0"]=storage
        economy=EconomySystem(state,self.registry,b"workplace",NullHistory())
        logistics=WorkplaceLogisticsSystem(state,self.registry,b"workplace")
        economy.attach_workplace_logistics(logistics)
        return state,town,npc,storage,economy,logistics,proc

    def test_physical_batch_consumes_real_workplace_inputs_and_keeps_output(self):
        state,town,npc,storage,economy,logistics,proc=self.fixture(
            items={"core:iron_ore":2,"core:coal":1},stocks={"core:iron_ore":0,"core:coal":0}
        )
        made=economy._run_process(town,proc,proc.workers,1,1440)
        self.assertEqual(made,1)
        self.assertNotIn("core:iron_ore",storage.items);self.assertNotIn("core:coal",storage.items)
        self.assertEqual(storage.items.get("core:iron_bloom"),1)
        self.assertEqual(town.stocks.get("core:iron_bloom",0),0)
        row=next(iter(state.workplace_logistics.values()))
        self.assertEqual(row.physical_batches_total,1);self.assertEqual(row.retained_outputs_total.get("core:iron_bloom"),1)
        restored=LivingWorldState.from_dict(state.to_dict())
        self.assertEqual(restored.workplace_logistics[row.uid].physical_batches_total,1)

    def test_empty_workplace_runs_aggregate_then_stages_next_cycle_inputs(self):
        state,town,npc,storage,economy,logistics,proc=self.fixture(
            items={},stocks={"core:iron_ore":4,"core:coal":2}
        )
        made=economy._run_process(town,proc,proc.workers,1,1440)
        self.assertEqual(made,1)
        self.assertEqual(town.stocks.get("core:iron_bloom"),1)
        self.assertEqual(storage.items.get("core:iron_ore"),2);self.assertEqual(storage.items.get("core:coal"),1)
        self.assertEqual(town.stocks.get("core:iron_ore"),0);self.assertEqual(town.stocks.get("core:coal"),0)
        row=next(iter(state.workplace_logistics.values()))
        self.assertEqual(row.staged_inputs_total,{"core:iron_ore":2,"core:coal":1})
        state.labor_reservations[f"labor:{town.uid}:{proc.id}"].assigned_day=2
        made2=economy._run_process(town,proc,proc.workers,2,2880)
        self.assertEqual(made2,1);self.assertEqual(storage.items.get("core:iron_bloom"),1)

    def test_exact_and_aggregate_batches_conserve_original_process_output(self):
        state,town,npc,storage,economy,logistics,proc=self.fixture(
            occupation="carpenter",process_id="core:logging",workplace="workshop:1",items={},stocks={},workers=2
        )
        made=economy._run_process(town,proc,2,1,1440)
        self.assertEqual(made,2)
        total=storage.items.get("core:wood",0)+town.stocks.get("core:wood",0)+sum(
            s.quantity for s in state.workplace_shipments.values() if s.item_id=="core:wood" and s.status!="delivered"
        )
        self.assertEqual(total,6)

    def test_excess_workplace_stock_becomes_persistent_worker_carried_market_shipment(self):
        state,town,npc,storage,economy,logistics,proc=self.fixture(
            occupation="carpenter",process_id="core:logging",workplace="workshop:1",items={"core:wood":5},stocks={},workers=1
        )
        before=storage.items["core:wood"]
        economy._run_process(town,proc,1,1,1440)
        shipment=next(iter(state.workplace_shipments.values()))
        self.assertEqual(shipment.item_id,"core:wood");self.assertEqual(shipment.status,"assigned")
        self.assertEqual(storage.items.get("core:wood"),3)
        self.assertEqual(storage.items.get("core:wood",0)+shipment.quantity,before+3)
        self.assertTrue(all(t.get("shipment_uid")==shipment.uid for t in npc.tasks[-4:]))
        self.assertTrue(logistics.pickup_shipment(shipment.uid,npc.uid,1500));self.assertEqual(shipment.status,"carried")
        self.assertTrue(logistics.dropoff_shipment(shipment.uid,npc.uid,1510))
        self.assertEqual(shipment.status,"delivered");self.assertEqual(town.stocks.get("core:wood"),shipment.quantity)
        self.assertFalse(any(t.get("shipment_uid")==shipment.uid for t in npc.tasks))
        row=state.workplace_logistics[shipment.workplace_uid]
        self.assertEqual(row.market_outputs_total.get("core:wood"),shipment.quantity)
        restored=LivingWorldState.from_dict(state.to_dict());self.assertEqual(restored.workplace_shipments[shipment.uid].status,"delivered")

    def test_overdue_shipment_completes_coarsely_without_stranding_tasks(self):
        state,town,npc,storage,economy,logistics,proc=self.fixture(
            occupation="carpenter",process_id="core:logging",workplace="workshop:1",items={"core:wood":5},stocks={},workers=1
        )
        economy._run_process(town,proc,1,1,1440);shipment=next(iter(state.workplace_shipments.values()))
        logistics.hourly_update(shipment.coarse_due_minute)
        self.assertEqual(shipment.status,"delivered");self.assertGreater(town.stocks.get("core:wood",0),0)
        self.assertFalse(any(t.get("shipment_uid")==shipment.uid for t in npc.tasks))


if __name__=="__main__":unittest.main()
