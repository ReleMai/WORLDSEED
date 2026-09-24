import unittest

from worldseed.systems.household_economy import HouseholdEconomySystem
from worldseed.systems.state import ContainerState, LivingWorldState, NPCState, SettlementState

class HouseholdEconomyTests(unittest.TestCase):
    def test_household_consumes_physical_home_storage_and_persists_shortage(self):
        state=LivingWorldState();town=SettlementState(uid="town:1",name="Test",x=0,y=0,region_x=0,region_y=0,population=3)
        state.settlements[town.uid]=town
        for i in range(3):
            n=NPCState(f"npc:{i}",f"N{i}",30,"farmer",[],0,0,0,town.uid,"faction:1",family_uid="family:1",home_id="home:1");state.npcs[n.uid]=n
        c=ContainerState("storage:1",0,0,0,"npc:0",1000,1000,items={"core:wheat":1},kind="property",property_id="home:1")
        state.containers["0,0,0"]=c;system=HouseholdEconomySystem(state,b"household")
        system.daily_update(1440);h=state.households["family:1"]
        self.assertEqual(h.storage_uids,["storage:1"]);self.assertEqual(c.items,{});self.assertEqual(h.food_shortage,0);self.assertEqual(h.last_consumed_minute,1440)
        system.daily_update(2880);self.assertEqual(h.food_shortage,1);self.assertEqual(h.days_short,1);self.assertTrue(all(n.hunger>0 for n in state.npcs.values()))
        restored=LivingWorldState.from_dict(state.to_dict());self.assertEqual(restored.households["family:1"].food_shortage,1)

if __name__=="__main__":unittest.main()
