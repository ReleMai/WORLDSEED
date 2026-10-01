import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from worldseed.core.coords import WorldPos
from worldseed.systems.ai import NPCSystem
from worldseed.systems.state import NPCState, SettlementState


class InteriorAITests(unittest.TestCase):
    def fixture(self):
        town=SettlementState("settlement:test","Millford",0,0,0,0,12,"culture:test","religion:test","")
        npc=NPCState("npc:resident","Ada",30,"farmer",[],3,4,0,town.uid,"")
        npc.home_id="home:ada"
        state=SimpleNamespace(npcs={npc.uid:npc},settlements={town.uid:town},interior_actors={})
        system=NPCSystem(state,b"interior-ai",None)
        interior=Mock()
        system.attach_interior_system(interior)
        return state,town,npc,system,interior

    def test_inside_npc_skips_outdoor_decisions_and_task_execution(self):
        state,town,npc,system,interior=self.fixture()
        state.interior_actors[npc.uid]={"space_id":"interior:home:ada","x":1250,"y":1750}
        npc.tasks=[{"kind":"move","x":7,"y":8}]
        original=[dict(task) for task in npc.tasks]
        system._choose_goal_and_plan=Mock()
        system.execute_tick=Mock()
        system.decision_update(600,WorldPos(3,4))
        system.tick_update(605,WorldPos(3,4))
        system._execute_task(npc,town,605,WorldPos(3,4))
        system.generate_plan(npc,town,605,"rest")
        system._choose_goal_and_plan.assert_not_called()
        system.execute_tick.assert_not_called()
        interior.tick_update.assert_called_once_with(605)
        self.assertEqual(npc.tasks,original)
        self.assertEqual((npc.x,npc.y,npc.hunger,npc.thirst),(3,4,0,0))

    def test_rest_plan_targets_stable_exterior_entrance(self):
        _,town,npc,system,_=self.fixture()
        interior_door=SimpleNamespace(uid="door:partition",role="interior_door",x=15,y=18,z=0)
        entrance=SimpleNamespace(uid="door:ada",role="entrance",x=10,y=12,z=0)
        system.property_security=SimpleNamespace(doors_for_property=lambda uid:(interior_door,entrance))
        system.generate_plan(npc,town,600,"rest")
        task=npc.tasks[0]
        self.assertEqual((task["x"],task["y"],task["z"]),(10,12,0))
        self.assertEqual(task["interior_home_door_uid"],"door:ada")
        self.assertTrue(task["exact"])
        self.assertTrue(task["physical_path"])

    def test_at_door_uses_shared_portal_and_not_outdoor_rest_effect(self):
        state,town,npc,system,interior=self.fixture()
        npc.tasks=[{"kind":"move","x":3,"y":4,"exact":True,"interior_home_door_uid":"door:ada"},
                   {"kind":"perform","action":"rest"}]
        npc.rest=80
        npc.inventory={"core:wheat":2}
        def enter(resident,door_uid):
            state.interior_actors[resident.uid]={"space_id":"interior:home:ada"}
            return True
        interior.enter_npc.side_effect=enter
        system.execute_tick(npc,town,605,WorldPos(3,4))
        interior.enter_npc.assert_called_once_with(npc,"door:ada")
        self.assertIn(npc.uid,state.interior_actors)
        self.assertFalse(npc.tasks)
        self.assertEqual(npc.rest,80)
        self.assertEqual(npc.inventory,{"core:wheat":2})

    def test_failed_portal_entry_keeps_task_and_cannot_rest_through_door(self):
        state,town,npc,system,interior=self.fixture()
        task={"kind":"move","x":3,"y":4,"exact":True,"interior_home_door_uid":"door:ada"}
        npc.tasks=[task,{"kind":"perform","action":"rest"}]
        npc.rest=80
        interior.enter_npc.return_value=False
        system.execute_tick(npc,town,605,WorldPos(3,4))
        self.assertEqual(npc.tasks[0],task)
        self.assertEqual(len(npc.tasks),2)
        self.assertFalse(state.interior_actors)
        self.assertEqual(npc.rest,80)

    def test_legacy_state_without_interior_records_retains_outdoor_execution(self):
        state,town,npc,system,_=self.fixture()
        del state.interior_actors
        system.interiors=None
        npc.tasks=[{"kind":"move","x":4,"y":4,"exact":True}]
        system.execute_tick(npc,town,605,WorldPos(3,4))
        self.assertEqual((npc.x,npc.y),(4,4))
        self.assertFalse(npc.tasks)

    def test_exterior_social_task_does_not_reach_person_inside(self):
        state,town,npc,system,_=self.fixture()
        other=NPCState("npc:inside","Bo",40,"cook",[],3,4,0,town.uid,"")
        state.npcs[other.uid]=other
        state.interior_actors[other.uid]={"space_id":"interior:home:bo"}
        npc.needs["social"]=80
        npc.tasks=[{"kind":"social","target":other.uid}]
        system.execute_tick(npc,town,605,WorldPos(3,4))
        self.assertEqual(npc.needs["social"],80)
        self.assertFalse(npc.memories)
        system.generate_plan(npc,town,605,"socialize")
        self.assertNotIn("target",npc.tasks[-1])


if __name__=="__main__":
    unittest.main()
