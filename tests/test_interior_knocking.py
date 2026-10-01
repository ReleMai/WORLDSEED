import unittest
from types import SimpleNamespace

from worldseed.core.coords import WorldPos
from worldseed.systems.interior_state import InteriorActor, InteriorPlan
from worldseed.systems.property_intrusion import PropertySecuritySystem
from worldseed.systems.state import DoorSecurityState, LivingWorldState, NPCState


class InteriorKnockingTests(unittest.TestCase):
    def fixture(self):
        state=LivingWorldState(clock_minute=600)
        npc=NPCState("npc:resident","Ada",30,"farmer",[],10,9,0,"settlement:test","",home_id="home:test")
        npc.relationships["player"]={"trust":40,"affection":20,"familiarity":30}
        door=DoorSecurityState("door:test","settlement:test","home:test",10,9,owner_uid=npc.uid,locked=True)
        state.npcs[npc.uid]=npc
        state.door_security[door.uid]=door
        plan=InteriorPlan("interior:home:test","home:test",door.uid,10,9,0,10000,10000)
        state.interiors[plan.uid]=plan
        state.interior_actors[npc.uid]=InteriorActor(plan.uid,2400,3200)
        physical=SimpleNamespace(structure_by_id=lambda uid:SimpleNamespace(function="residence"),cell_at=lambda pos:None)
        security=PropertySecuritySystem(state,SimpleNamespace(),b"interior-knock",physical,SimpleNamespace())
        return state,npc,door,security

    def test_knock_requests_physical_exit_before_answering(self):
        state,npc,door,security=self.fixture()
        result=security.knock_on_door(door.uid,WorldPos(10,8),600,2)
        self.assertEqual(result["outcome"],"approaching")
        self.assertEqual(npc.tasks[0]["door_answer_uid"],door.uid)
        self.assertEqual(npc.tasks[1]["action"],"answer_door")
        self.assertIn(npc.uid,state.interior_actors)
        self.assertTrue(door.locked)
        self.assertFalse(security.complete_door_answer(door.uid,npc.uid,605))
        self.assertNotIn("player",door.guest_access_until)
        state.interior_actors.pop(npc.uid)
        self.assertTrue(security.complete_door_answer(door.uid,npc.uid,610))
        self.assertFalse(door.locked)
        self.assertIn("player",door.guest_access_until)

    def test_resident_inside_another_space_cannot_answer_via_anchor(self):
        state,npc,door,security=self.fixture()
        plan=InteriorPlan("interior:other","home:other","door:other",10,9,0,10000,10000)
        state.interiors[plan.uid]=plan
        state.interior_actors[npc.uid].space_id=plan.uid
        self.assertEqual(security.knock_on_door(door.uid,WorldPos(10,8),600)["outcome"],"unanswered")
        self.assertTrue(door.locked)
        self.assertFalse(npc.tasks)

    def test_player_inside_cannot_knock_on_exterior_anchor(self):
        state,_,door,security=self.fixture()
        state.interior_actors["player"]=InteriorActor("interior:home:test",3500,4000)
        self.assertEqual(security.knock_on_door(door.uid,WorldPos(10,8),600)["outcome"],"inside")
        self.assertTrue(door.locked)


if __name__=="__main__":
    unittest.main()
