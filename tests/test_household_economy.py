import unittest

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.systems.economy import EconomySystem
from worldseed.systems.household_economy import HouseholdEconomySystem
from worldseed.systems.state import ContainerState, LivingWorldState, NPCState, SettlementState

class NullHistory:
    def record(self,*args,**kwargs):return None

class HouseholdEconomyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.registry=ContentRegistry.load(DATA_DIR)

    def fixture(self,wealth=40,stock=20):
        state=LivingWorldState();town=SettlementState(uid="town:1",name="Test",x=10,y=10,region_x=0,region_y=0,population=3,culture_id="",religion_id="",faction_id="faction:1",wealth=500,stocks={"core:wheat":stock,"core:wood":10,"core:soap":5,"core:herbal_tonic":2})
        state.settlements[town.uid]=town
        for i in range(3):
            n=NPCState(f"npc:{i}",f"N{i}",30,"farmer",[],10,10,0,town.uid,town.faction_id,wealth=wealth if i==0 else 0,family_uid="family:1",home_id="home:1");state.npcs[n.uid]=n
        c=ContainerState("storage:1",15,15,0,"npc:0",100000,100000,items={"core:wheat":1},kind="property",property_id="home:1")
        state.containers["15,15,0"]=c;economy=EconomySystem(state,self.registry,b"household",NullHistory());economy.update_prices();system=HouseholdEconomySystem(state,b"household",self.registry,economy)
        return state,town,c,economy,system

    def test_household_consumes_physical_home_storage_and_persists_shortage(self):
        state,town,c,economy,system=self.fixture(stock=0);system.daily_update(1440);h=state.households["family:1"]
        self.assertEqual(h.storage_uids,["storage:1"]);self.assertEqual(c.items,{});self.assertEqual(h.food_shortage,0);self.assertEqual(h.last_consumed_minute,1440)
        system.daily_update(2880);self.assertEqual(h.food_shortage,1);self.assertEqual(h.days_short,1);self.assertTrue(all(n.hunger>0 for n in state.npcs.values()))
        restored=LivingWorldState.from_dict(state.to_dict());self.assertEqual(restored.households["family:1"].food_shortage,1)

    def test_procurement_reserves_market_goods_cash_and_physical_delivery(self):
        state,town,c,economy,system=self.fixture(wealth=100,stock=20);system.daily_update(1440);h=state.households["family:1"]
        pending=[d for d in state.household_deliveries.values() if d.household_uid==h.uid]
        self.assertTrue(pending);delivery=next(d for d in pending if d.item_id=="core:wheat")
        self.assertLess(town.stocks["core:wheat"],20);self.assertLess(system.household_wealth(h),100);self.assertEqual(c.items.get("core:wheat",0),0)
        self.assertTrue(system.pickup_delivery(delivery.uid,delivery.carrier_uid,1500));self.assertEqual(delivery.status,"carried")
        self.assertTrue(system.dropoff_delivery(delivery.uid,delivery.carrier_uid,1510));self.assertEqual(delivery.status,"delivered");self.assertGreater(c.items.get("core:wheat",0),0)
        self.assertTrue(any(t.kind=="household_purchase" for t in state.market_transactions.values()))
        restored=LivingWorldState.from_dict(state.to_dict());self.assertEqual(restored.household_deliveries[delivery.uid].status,"delivered");self.assertTrue(restored.households[h.uid].ledger)

    def test_budget_and_market_stock_bound_procurement(self):
        state,town,c,economy,system=self.fixture(wealth=1,stock=1);system.daily_update(1440);h=state.households["family:1"]
        self.assertTrue(h.unmet_needs);self.assertGreaterEqual(system.household_wealth(h),0);self.assertGreaterEqual(town.stocks["core:wheat"],0)

    def test_prior_work_pays_real_wage_from_settlement_wealth(self):
        state,town,c,economy,system=self.fixture(wealth=0,stock=0);n=state.npcs["npc:0"];n.work_assignment_day=0;n.work_hours_today=8
        before=town.wealth;system.daily_update(1440);h=state.households["family:1"]
        self.assertGreater(n.wealth,0);self.assertLess(town.wealth,before);self.assertGreater(h.total_income,0);self.assertTrue(any(t.kind=="household_wage" for t in state.market_transactions.values()))

if __name__=="__main__":unittest.main()
