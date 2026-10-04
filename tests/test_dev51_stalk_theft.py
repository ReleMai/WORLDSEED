"""Theft requires Stalk, physical access, and real goods, not casing intel."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory
from worldseed.sim.commands import StartCasingCommand, StealContainerCommand, StealMarketCommand
from worldseed.sim.engine import Simulation
from worldseed.systems.economy import EconomySystem
from worldseed.systems.property_intrusion import CasingSystem, PropertyStorageSystem
from worldseed.systems.state import CasingIntelState, ContainerState, LivingWorldState, NPCState, SettlementState
from worldseed.systems.stealth import StealthSystem


class StalkTheftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=ContentRegistry.load(DATA_DIR)

    def fixture(self,*,locked=False,witnesses=()):
        state=LivingWorldState(player_hunting_stance="stalk",player_stealth_mode=True)
        town=SettlementState("settlement:test","Testford",0,0,10,10,20,"culture:test","religion:test","faction:test",stocks={"core:wheat":20})
        state.settlements[town.uid]=town
        guard=NPCState("npc:guard","Guard",30,"guard",[],10,10,0,town.uid,town.faction_id)
        state.npcs[guard.uid]=guard
        container=ContainerState("storage:test",10,10,0,"npc:owner",100000,100000,
                                 items={"core:wheat":5},name="Household chest",kind="property",
                                 property_id="house:test",settlement_id=town.uid,locked=locked,lock_level=20)
        state.containers[container.uid]=container
        history=SimpleNamespace(record=Mock())
        economy=EconomySystem(state,self.registry,b"dev51-stalk-theft",history)
        storage=PropertyStorageSystem(state,self.registry,b"dev51-stalk-theft",SimpleNamespace(),SimpleNamespace())
        storage.keys.ensure_lock(container)
        inv=Inventory()
        messages=[]
        harness=SimpleNamespace(state=state,registry=self.registry,economy=economy,
                                property_storage=storage,civics=SimpleNamespace(),
                                entities=SimpleNamespace(get=lambda *_:inv),player_pos=WorldPos(10,11),
                                clock=SimpleNamespace(minute=600),
                                stealth=SimpleNamespace(witnesses=lambda *_:witnesses),
                                _command_container=lambda uid:container if uid==container.uid else None,
                                _message=messages.append)
        return harness,container,inv,messages

    def steal(self,harness,container,amount=1,item_id="core:wheat"):
        Simulation._steal_container(harness,StealContainerCommand(1,container.uid,item_id,amount))

    def test_stalk_theft_needs_no_casing_and_conserves_goods(self):
        sim,container,inv,messages=self.fixture()
        stocks=dict(sim.state.settlements[container.settlement_id].stocks)
        self.steal(sim,container,2)
        self.assertEqual(container.items["core:wheat"],3)
        self.assertEqual(inv.count("core:wheat"),2)
        self.assertEqual(sim.state.settlements[container.settlement_id].stocks,stocks)
        self.assertFalse(sim.state.casing_intel)
        self.assertFalse(sim.state.player_casing_property_id)
        theft=next(iter(sim.state.theft_records.values()))
        self.assertEqual(theft.quantity,2)
        self.assertEqual(theft.property_id,container.property_id)
        self.assertFalse(theft.witnessed)
        self.assertIn("No witness",messages[-1])

    def test_non_stalk_modes_reject_even_when_generic_stealth_flag_is_true(self):
        for stance in ("normal","crouch","aggressive"):
            with self.subTest(stance=stance):
                sim,container,inv,messages=self.fixture()
                sim.state.player_hunting_stance=stance
                before=sim.state.to_dict()
                self.steal(sim,container)
                self.assertEqual(before,sim.state.to_dict())
                self.assertEqual(inv.count("core:wheat"),0)
                self.assertIn("Stalk",messages[-1])

    def test_real_locked_container_still_rejects_theft(self):
        sim,container,inv,messages=self.fixture(locked=True)
        before=sim.state.to_dict()
        self.steal(sim,container)
        self.assertEqual(before,sim.state.to_dict())
        self.assertEqual(inv.count("core:wheat"),0)
        self.assertIn("locked",messages[-1])

    def test_real_physical_key_is_honored_without_keyholder_roster_entry(self):
        sim,container,inv,_=self.fixture(locked=True)
        sim.property_storage.keys.ensure_key(container,"player","Chest key",599)
        self.assertNotIn("player",container.keyholder_uids)
        self.steal(sim,container)
        self.assertTrue(container.locked)
        self.assertEqual(inv.count("core:wheat"),1)

    def test_picked_container_can_be_stolen_from_without_casing(self):
        sim,container,inv,_=self.fixture()
        container.picked=True
        self.steal(sim,container)
        self.assertEqual(inv.count("core:wheat"),1)
        self.assertTrue(container.picked)

    def test_reach_and_quantity_failures_do_not_move_goods(self):
        for failure in ("reach","quantity","invalid"):
            with self.subTest(failure=failure):
                sim,container,inv,_=self.fixture()
                if failure=="reach":sim._command_container=lambda _:None
                if failure=="invalid":container.items["missing:item"]=1
                before=sim.state.to_dict()
                self.steal(sim,container,amount=99 if failure=="quantity" else 1,
                           item_id="missing:item" if failure=="invalid" else "core:wheat")
                self.assertEqual(before,sim.state.to_dict())
                self.assertEqual(inv.count("core:wheat"),0)

    def test_market_theft_also_requires_stalk(self):
        for stance in ("normal","crouch","aggressive"):
            with self.subTest(stance=stance):
                sim,container,inv,messages=self.fixture()
                sim.state.player_hunting_stance=stance
                before=sim.state.to_dict()
                Simulation._steal_market(sim,StealMarketCommand(1,container.settlement_id,"core:wheat",1))
                self.assertEqual(sim.state.to_dict(),before)
                self.assertEqual(inv.count("core:wheat"),0)
                self.assertIn("Stalk",messages[-1])

    def test_witnessed_theft_keeps_crime_and_relationship_response(self):
        sim,container,inv,_=self.fixture(witnesses=("npc:guard",))
        self.steal(sim,container)
        theft=next(iter(sim.state.theft_records.values()))
        self.assertEqual(inv.count("core:wheat"),1)
        self.assertEqual(theft.witness_uids,["npc:guard"])
        self.assertEqual(sim.state.player_crime_heat[container.settlement_id],25)
        self.assertLess(sim.state.npcs["npc:guard"].relationships["player"]["trust"],0)

    def test_legacy_casing_alarm_does_not_amplify_new_theft_or_sight(self):
        sim,container,_,_=self.fixture(witnesses=("npc:guard",))
        sim.state.player_casing_property_id=container.property_id
        intel=CasingIntelState(container.property_id,container.settlement_id,alarm_level=3,
                              owner_uid="npc:guard",suspicion=100)
        sim.state.casing_intel[container.property_id]=intel
        stealth=StealthSystem(sim.state,b"test",None,None,None,None,None)
        self.assertEqual(stealth.observer_range(sim.state.npcs["npc:guard"],600),10)
        self.steal(sim,container)
        self.assertEqual(sim.state.player_crime_heat[container.settlement_id],25)
        restored=LivingWorldState.from_dict(sim.state.to_dict())
        self.assertEqual(restored.casing_intel[container.property_id].suspicion,100)

    def test_legacy_start_and_movement_do_not_generate_intel_or_change_stance(self):
        sim,container,_,messages=self.fixture()
        sim.state.player_casing_property_id=container.property_id
        Simulation._start_casing(sim,StartCasingCommand(1,container.property_id))
        self.assertFalse(sim.state.player_casing_property_id)
        self.assertEqual(sim.state.player_hunting_stance,"stalk")
        self.assertIn("disabled",messages[-1])
        casing=CasingSystem(sim.state,SimpleNamespace(),SimpleNamespace(),sim.property_storage)
        before=sim.state.to_dict()
        self.assertFalse(casing.start(container.property_id,sim.player_pos,600,sim.stealth)[0])
        self.assertEqual(casing.observe_step(sim.player_pos,600,sim.stealth),[])
        self.assertEqual(before,sim.state.to_dict())

    def test_loaded_casing_session_is_retired_without_losing_historical_intel(self):
        sim,container,_,_=self.fixture()
        sim.state.player_casing_property_id=container.property_id
        sim.state.casing_intel[container.property_id]=CasingIntelState(container.property_id,container.settlement_id,sessions=4,suspicion=27)
        restored=LivingWorldState.from_dict(sim.state.to_dict())
        CasingSystem(restored,SimpleNamespace(),SimpleNamespace(),sim.property_storage)
        self.assertFalse(restored.player_casing_property_id)
        self.assertEqual(restored.casing_intel[container.property_id].sessions,4)
        self.assertEqual(restored.casing_intel[container.property_id].suspicion,27)
        self.assertEqual(restored.player_hunting_stance,"stalk")


if __name__=="__main__":unittest.main()
