from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from worldseed.core.coords import WorldPos
from worldseed.sim.realtime import RealtimeSimulationDriver
from worldseed.sim.engine import Simulation
from worldseed.systems.dialogue import DialogueSystem
from worldseed.systems.property_intrusion import PropertySecuritySystem
from worldseed.systems.state import DoorSecurityState, LivingWorldState, NPCState, SettlementState


class FakeSimulation:
    def __init__(self):self.advances=[]
    def advance_realtime(self,minutes):self.advances.append(minutes)


class FakePhysicalization:
    def __init__(self,property_id):self.property_id=property_id
    def structure_by_id(self,uid):
        return SimpleNamespace(function='residence') if uid==self.property_id else None
    def cell_at(self,pos):return SimpleNamespace(structure_id=self.property_id)


class SocialRealtimePhaseTests(unittest.TestCase):
    def fixture(self):
        state=LivingWorldState(clock_minute=600)
        town=SettlementState('settlement:test','Millford',0,0,0,0,80,'culture:test','religion:test','faction:test')
        state.settlements[town.uid]=town
        npc=NPCState('npc:resident','Eda',35,'healer',[],10,10,0,town.uid,town.faction_id,home_id='home:test',property_id='home:test')
        state.npcs[npc.uid]=npc
        door=DoorSecurityState('door:test',town.uid,'home:test',10,9,owner_uid=npc.uid,locked=True,lock_level=24)
        state.door_security[door.uid]=door
        return state,town,npc,door

    def test_realtime_driver_advances_without_input_and_caps_stalls(self):
        sim=FakeSimulation();driver=RealtimeSimulationDriver(sim,seconds_per_game_minute=1,max_catchup_minutes=5)
        driver.resume(10.0)
        self.assertEqual(driver.pump(12.4),2)
        self.assertEqual(sim.advances,[2])
        self.assertEqual(driver.pump(40.0),5)
        self.assertEqual(sim.advances,[2,5])
        driver.pause();self.assertEqual(driver.pump(50.0),0)

    def test_one_minute_heartbeats_accumulate_vitals_on_absolute_boundaries(self):
        vitals=SimpleNamespace(hunger=0,thirst=0,stamina=50,hp=100,blood=100,body_temp=50)
        sim=SimpleNamespace(
            clock=SimpleNamespace(minute=44),entities=SimpleNamespace(try_get=lambda *_:vitals),player_id=1,
            state=SimpleNamespace(player_food_effects={},player_wounds=[],player_body_parts={},player_equipment={}),
            player_pos=WorldPos(0,0,0),
        )
        # Isolate the periodic counters from environment/exposure consumers.
        sim.clock.minute=45
        with patch('worldseed.systems.swimming.exposure',return_value=SimpleNamespace(mode='walking')):
            Simulation._update_vitals(sim,1)
        self.assertEqual(vitals.hunger,1)

    def test_dialogue_topics_and_social_effects_are_bounded(self):
        state,_,npc,_=self.fixture();dialogue=DialogueSystem(state,b'social-test')
        vitals=SimpleNamespace(hp=100,max_hp=100,pain=0,blood=100,hunger=10,thirst=10)
        root=dialogue.scene(npc,600,vitals,topic='root')
        self.assertEqual(next(o for o in root.options if o.key=='relations').next_topic,'relations')
        relations=dialogue.scene(npc,600,vitals,topic='relations')
        listen=next(o for o in relations.options if o.key=='listen')
        self.assertTrue(dialogue.apply_option(npc,listen,600))
        first=dict(npc.relationships['player'])
        self.assertFalse(dialogue.apply_option(npc,listen,601))
        self.assertEqual(npc.relationships['player'],first)
        self.assertTrue(dialogue.apply_option(npc,listen,780))

    def test_conversation_familiarity_gain_is_time_bounded(self):
        state,_,npc,_=self.fixture()
        sim=SimpleNamespace(state=state,clock=SimpleNamespace(minute=600),_message=lambda *_:None)
        # Exercise only the relationship prelude by making this the first meeting.
        Simulation.begin_conversation(sim,npc.uid)
        first=dict(npc.relationships['player'])
        Simulation.begin_conversation(sim,npc.uid)
        self.assertEqual(npc.relationships['player'],first)

    def test_knocking_requires_present_resident_and_grants_temporary_invitation(self):
        state,_,npc,door=self.fixture();npc.relationships['player']={'trust':40,'affection':20,'familiarity':30}
        security=PropertySecuritySystem(state,SimpleNamespace(),b'knock-test',FakePhysicalization('home:test'),SimpleNamespace())
        result=security.knock_on_door(door.uid,WorldPos(10,8,0),600,persuasion=2)
        self.assertEqual(result['outcome'],'invited')
        self.assertTrue(security.authorized_player(door))
        self.assertFalse(door.locked)
        restored=LivingWorldState.from_dict(state.to_dict())
        self.assertEqual(restored.door_security[door.uid].guest_access_until['player'],720)
        state.clock_minute=721;security.update_scheduled_locks(721)
        self.assertFalse(security.authorized_player(door))
        self.assertTrue(door.locked)

    def test_guarded_resident_talks_at_threshold_without_inviting(self):
        state,_,npc,door=self.fixture();npc.traits=['suspicious'];npc.relationships['player']={'trust':-10,'affection':0,'familiarity':4}
        security=PropertySecuritySystem(state,SimpleNamespace(),b'knock-test',FakePhysicalization('home:test'),SimpleNamespace())
        result=security.knock_on_door(door.uid,WorldPos(10,8,0),600,persuasion=0)
        self.assertEqual(result['outcome'],'door_talk')
        self.assertFalse(security.authorized_player(door))


if __name__=='__main__':unittest.main()
