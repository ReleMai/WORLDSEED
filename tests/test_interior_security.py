import unittest
from types import SimpleNamespace

from worldseed.core.coords import WorldPos
from worldseed.systems.interior_state import InteriorActor, InteriorPlan, InteriorRect
from worldseed.systems.property_intrusion import PropertySecuritySystem
from worldseed.systems.state import LivingWorldState, DoorSecurityState, NPCState, TrespassState
from worldseed.systems.stealth import StealthSystem


class InteriorSecurityTests(unittest.TestCase):
    def fixture(self):
        state=LivingWorldState(clock_minute=600)
        plan=InteriorPlan("interior:home:test","home:test","door:test",10,10,0,12000,12000)
        state.interiors[plan.uid]=plan
        state.interior_actors["player"]=InteriorActor(plan.uid,4000,4000)
        resident=NPCState("npc:resident","Ada",30,"guard",[],10,10,0,"settlement:test","",home_id=plan.building_id,facing_dx=1,facing_dy=0)
        outside=NPCState("npc:outside","Bo",40,"farmer",[],10,10,0,"settlement:test","",facing_dx=1,facing_dy=0)
        other=NPCState("npc:other","Cy",35,"guard",[],10,10,0,"settlement:test","",facing_dx=1,facing_dy=0)
        state.npcs={resident.uid:resident,outside.uid:outside,other.uid:other}
        state.interior_actors[resident.uid]=InteriorActor(plan.uid,3000,4000)
        state.interior_actors[other.uid]=InteriorActor("interior:other",3000,4000)
        def actors(space):
            return tuple((uid,actor) for uid,actor in state.interior_actors.items() if actor.space_id==space)
        interiors=SimpleNamespace(player_presence=lambda:state.interior_actors.get("player"),current_plan=lambda:plan,
                                  actors_in_space=actors,room_at=lambda *_:None)
        world=SimpleNamespace(tile_at=lambda *_:self.fail("Interior sight must not inspect exterior terrain"))
        physical=SimpleNamespace(cell_at=lambda *_:None,structure_by_id=lambda *_:SimpleNamespace(entrance=(10,10)),
                                 clears_natural_feature=lambda *_:False)
        stealth=StealthSystem(state,b"indoor-security",world,None,None,physical,None)
        stealth.attach_interior_system(interiors)
        door=DoorSecurityState("door:test","settlement:test",plan.building_id,10,10,owner_uid=resident.uid,locked=False)
        state.door_security[door.uid]=door
        security=PropertySecuritySystem(state,SimpleNamespace(),b"indoor-security",physical,None)
        return state,plan,resident,stealth,security,door

    def test_indoor_witnesses_are_same_space_and_observational(self):
        state,plan,resident,stealth,_,_=self.fixture()
        before=state.to_dict()
        snap=stealth.snapshot(WorldPos(10,10),600)
        self.assertEqual(snap["space_id"],plan.uid)
        self.assertEqual(snap["seen_by"],(resident.uid,))
        self.assertEqual(stealth.witnesses(WorldPos(10,10),600,"settlement:test"),(resident.uid,))
        self.assertEqual(state.to_dict(),before)

    def test_interior_walls_block_witness_sight(self):
        _,plan,_,stealth,_,_=self.fixture()
        plan.walls=[InteriorRect(3450,0,180,12000)]
        self.assertFalse(stealth.witnesses(WorldPos(10,10),600))

    def test_portal_entry_records_trespass_response_then_exit_clears_it(self):
        state,plan,resident,stealth,security,_=self.fixture()
        messages=security.note_interior_entry(plan,600,stealth)
        self.assertTrue(messages)
        self.assertEqual(state.player_trespass_property_id,plan.building_id)
        row=state.trespass_states[plan.building_id]
        self.assertTrue(row.active)
        self.assertEqual(row.witness_uids,[resident.uid])
        self.assertTrue(security.update_response(WorldPos(10,10),605,stealth))
        self.assertTrue(row.warned)
        self.assertTrue(security.note_interior_exit(plan,610))
        self.assertFalse(row.active)
        self.assertFalse(state.player_trespass_property_id)
        self.assertEqual(LivingWorldState.from_dict(state.to_dict()).trespass_states[plan.building_id].active,False)

    def test_guest_and_public_entry_do_not_create_trespass(self):
        state,plan,_,stealth,security,door=self.fixture()
        door.guest_access_until["player"]=720
        self.assertFalse(security.note_interior_entry(plan,600,stealth))
        self.assertFalse(state.trespass_states)
        door.guest_access_until.clear();door.access="public"
        self.assertFalse(security.note_interior_entry(plan,600,stealth))
        self.assertFalse(state.trespass_states)

    def test_authorized_entry_clears_a_stale_other_property_trespass(self):
        state,plan,_,stealth,security,door=self.fixture()
        previous=TrespassState("home:previous","settlement:test",active=True)
        state.trespass_states[previous.property_id]=previous
        state.player_trespass_property_id=previous.property_id
        door.keyholder_uids=["player"]
        self.assertFalse(security.note_interior_entry(plan,600,stealth))
        self.assertFalse(previous.active)
        self.assertFalse(state.player_trespass_property_id)


if __name__=="__main__":unittest.main()
