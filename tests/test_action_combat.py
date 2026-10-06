from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.clock import GameClock
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory, Position, Vitals
from worldseed.entities.store import EntityStore
from worldseed.sim.commands import (
    CraftCommand, DodgeCommand, MoveCommand, RangedAttackCommand, RestCommand, TalkCommand, WaitCommand,
)
from worldseed.sim.engine import Simulation
from worldseed.sim.realtime import RealtimeSimulationDriver
from worldseed.systems.combat import CombatSystem
from worldseed.systems.hunting import HuntingSystem
from worldseed.systems.projectiles import ProjectileSystem
from worldseed.systems.state import CreatureState, LivingWorldState


class FlatWorld:
    def tile_at(self, pos):
        return SimpleNamespace(terrain_id='core:grass', terrain=SimpleNamespace(
            passable=True, blocks_sight=False, tags=('soil',), name='Grass'))

    def is_passable(self, pos):
        return True


class ActionCombatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=ContentRegistry.load(DATA_DIR)

    def setUp(self):
        # Exercise the production command, wildlife and combat pipeline against
        # prepared flat terrain. Regional generation is irrelevant to timing.
        sim=Simulation.__new__(Simulation)
        sim.registry=self.registry;sim.seed=b'action-combat';sim.state=LivingWorldState(clock_minute=600)
        sim.entities=EntityStore();sim.entities.spawn(preferred_id=1)
        sim.entities.add(1,Position(WorldPos(0,0,0)))
        sim.entities.add(1,Inventory({'core:wood':4}))
        sim.entities.add(1,Vitals(hp=1000,max_hp=1000))
        sim.clock=GameClock(600);sim.turn=10;sim.log=[];sim.debug=Mock()
        sim.visual_effects=[];sim._visual_effect_counter=0
        sim.world=FlatWorld()
        sim.resources=SimpleNamespace(blocks_sight=lambda p:False, blocks_movement=lambda p:False,
                                      is_harvestable=lambda p:False,feature_at=lambda p:None)
        sim.environment=SimpleNamespace(weather=SimpleNamespace(at=lambda *a:{}),
                                        fluid_at=lambda p:None, fluid_passable=lambda p:True)
        sim.building=SimpleNamespace(passable=lambda p,passed:passed, blocks_sight=lambda p:False,structure_at=lambda p:None)
        sim.settlement_physicalization=SimpleNamespace(border_post_at=lambda p:None,
            crossing_at=lambda p:None, clears_natural_feature=lambda p:False)
        sim.property_security=SimpleNamespace(blocks_player=lambda p:False,
            note_player_step=lambda *a:[],update_response=lambda *a:[])
        sim.dungeons=SimpleNamespace(is_locked=lambda p:False,trigger_trap=lambda *a:None,
                                     update_cleared=lambda minute:None)
        sim.interiors=SimpleNamespace(player_presence=lambda:None)
        sim.ecology=SimpleNamespace(dematerialize_far=lambda p:None)
        sim.disease=SimpleNamespace(local_player_exposure=lambda *a:[],tick_player=lambda *a:[])
        sim.crafting=Mock();sim.stealth=Mock()
        sim.combat=CombatSystem(sim.state,self.registry,sim.seed)
        sim.projectiles=ProjectileSystem(sim.state,self.registry,sim.seed,sim.world,sim.resources,sim.building)
        sim.hunting=HuntingSystem(sim.state,self.registry,sim.seed,sim.world,
                                 sim.environment,sim.resources,sim.building)
        sim._ensure_nearby_world=Mock();sim._discover=Mock()
        self.time_advances=[]
        def advance(minutes):
            self.time_advances.append(minutes);sim.clock.advance(minutes);sim.state.clock_minute=sim.clock.minute
        sim._advance_time=advance
        self.sim=sim

    def bear(self, *, x=1, behavior='calm'):
        sp=self.registry.species['core:brown_bear']
        bear=CreatureState('bear:test',sp.id,x,0,0,sp.max_hp,
                           alertness=100,stamina=sp.stamina,behavior=behavior,last_threat_turn=self.sim.turn)
        self.sim.state.creatures[bear.uid]=bear
        self.sim._refresh_combat_candidates()
        return bear

    def test_idle_contact_pauses_before_first_bear_strike_and_discards_catchup(self):
        self.bear();sim=self.sim;v=sim.entities.get(1,Vitals)
        driver=RealtimeSimulationDriver(sim,seconds_per_game_minute=1,max_catchup_minutes=5)
        driver.resume(0)
        with patch.object(sim.combat,'creature_attack_player',wraps=sim.combat.creature_attack_player) as attack:
            self.assertEqual(driver.pump(60),1)
            self.assertTrue(sim.combat_active());self.assertEqual(v.hp,1000)
            frozen=(sim.clock.minute,sim.turn,sim.state.to_dict())
            self.assertEqual(driver.pump(120),0)
            self.assertEqual(driver.pump(900),0)
            self.assertEqual((sim.clock.minute,sim.turn,sim.state.to_dict()),frozen)
            attack.assert_not_called()
        self.assertIn('Combat paused',sim.log[-1].message)

    def test_player_movement_into_first_contact_gives_warning_before_response(self):
        self.bear(x=2)
        with patch.object(self.sim.combat,'creature_attack_player') as attack:
            self.sim.execute(MoveCommand(1,1,0))
            self.assertEqual(self.sim.player_pos,WorldPos(1,0,0))
            self.assertTrue(self.sim.combat_active());attack.assert_not_called()

    def test_wait_is_one_tick_and_one_bear_response(self):
        self.bear(behavior='defend');sim=self.sim
        with patch.object(sim.combat,'creature_attack_player',return_value='Bear attacks.') as attack:
            sim.execute(WaitCommand(1,1440))
            attack.assert_called_once()
        self.assertEqual(self.time_advances,[1]);self.assertEqual(sim.clock.minute,601)
        self.assertEqual(sim.turn,11)

    def test_combat_movement_advances_game_minute_and_one_ai_response(self):
        self.bear(behavior='pursue');sim=self.sim
        with patch.object(sim.hunting,'update_local_ai',wraps=sim.hunting.update_local_ai) as ai:
            sim.execute(MoveCommand(1,0,1))
            ai.assert_called_once()
        self.assertEqual(sim.player_pos,WorldPos(0,1,0));self.assertEqual(self.time_advances,[1])

    def test_active_defense_survives_one_response_then_clears(self):
        self.bear(behavior='defend');sim=self.sim
        seen=[]
        def incoming(*args):
            seen.append(sim.state.player_defense_mode)
            return 'You evade the bear.'
        with patch.object(sim.combat,'creature_attack_player',side_effect=incoming):
            sim.execute(DodgeCommand(1))
        self.assertEqual(seen,['dodge']);self.assertEqual(sim.state.player_defense_mode,'')
        self.assertEqual(self.time_advances,[1])

    def test_long_work_and_rest_reject_before_effects_or_time(self):
        self.bear(behavior='defend');sim=self.sim
        before=sim.state.to_dict();carried=dict(sim.entities.get(1,Inventory).items)
        with patch.object(sim,'_craft') as craft,patch.object(sim,'_rest') as rest:
            sim.execute(CraftCommand(1,'core:wooden_spear'));sim.execute(RestCommand(1,1440))
            craft.assert_not_called();rest.assert_not_called()
        self.assertEqual(self.time_advances,[]);self.assertEqual(sim.turn,10)
        self.assertEqual(sim.state.to_dict(),before);self.assertEqual(sim.entities.get(1,Inventory).items,carried)

    def test_dialogue_is_free_and_does_not_provoke_wildlife(self):
        self.bear(behavior='defend');sim=self.sim
        with patch.object(sim,'_talk') as talk,patch.object(sim.hunting,'update_local_ai') as ai:
            sim.execute(TalkCommand(1,1,0))
            talk.assert_called_once();ai.assert_not_called()
        self.assertEqual(self.time_advances,[]);self.assertEqual(sim.turn,10)

    def test_resuming_after_threat_leaves_has_no_suspended_time_burst(self):
        bear=self.bear(behavior='pursue');sim=self.sim
        driver=RealtimeSimulationDriver(sim,seconds_per_game_minute=1,max_catchup_minutes=5)
        driver.resume(0);self.assertEqual(driver.pump(900),0)
        bear.x=50
        self.assertFalse(sim.combat_active())
        self.assertEqual(driver.pump(1800),0)
        self.assertEqual(driver.pump(1801),1)
        self.assertEqual(self.time_advances,[1]);self.assertEqual(sim.clock.minute,601)

    def test_pause_query_is_observational_local_and_excludes_domestic_or_other_level(self):
        bear=self.bear(behavior='charge');sim=self.sim
        before=sim.state.to_dict()
        with patch.object(sim.world,'tile_at',side_effect=AssertionError('query generated terrain')):
            self.assertTrue(sim.combat_active())
        self.assertEqual(sim.state.to_dict(),before)
        bear.domestic=True;self.assertFalse(sim.combat_active())
        bear.domestic=False;bear.z=-1;self.assertFalse(sim.combat_active())
        bear.z=0;bear.x=43;self.assertFalse(sim.combat_active())

    def test_peaceful_new_or_legacy_creature_does_not_pause_at_turn_zero(self):
        bear=self.bear();sim=self.sim;sim.turn=0
        self.assertFalse(sim.combat_active())
        bear.last_attacked_turn=-1
        self.assertFalse(sim.combat_active())
        bear.last_attacked_turn=0
        self.assertTrue(sim.combat_active())

    def test_actual_self_bow_shot_enters_action_driven_combat(self):
        bear=self.bear(x=9);sim=self.sim
        inv=sim.entities.get(1,Inventory);inv.add('core:short_bow',1);inv.add('core:wood_arrow',2)
        sim.state.player_readied_weapon='core:short_bow'
        sim.execute(RangedAttackCommand(1,bear.uid))
        self.assertEqual(inv.count('core:wood_arrow'),1)
        self.assertEqual(bear.last_attacked_turn,10)
        self.assertTrue(sim.combat_active());self.assertEqual(self.time_advances,[1])
        frozen=(sim.clock.minute,sim.turn)
        self.assertEqual(sim.advance_realtime(5),0)
        self.assertEqual((sim.clock.minute,sim.turn),frozen)

    def test_pursuit_and_recent_ranged_attack_pause_across_full_local_envelope(self):
        bear=self.bear(x=20,behavior='pursue');sim=self.sim
        self.assertTrue(sim.combat_active())
        bear.behavior='calm';self.assertFalse(sim.combat_active())
        # Notify the real hunting authority as a future/modded long-range shot
        # would. Current stock ranged definitions have a maximum range of nine.
        sim.hunting.notify_attack(bear,sim.player_pos,sim.turn,sim.clock.minute,loudness=92,hit=False)
        self.assertTrue(sim.combat_active())
        bear.x=42;self.assertTrue(sim.combat_active())
        bear.x=43;self.assertFalse(sim.combat_active())

    def test_loaded_hostile_intent_retains_pause_without_new_save_fields(self):
        self.bear(behavior='charge');sim=self.sim
        sim.state=LivingWorldState.from_dict(sim.state.to_dict())
        sim._refresh_combat_candidates()
        self.assertTrue(sim.combat_active());self.assertEqual(sim.advance_realtime(5),0)
        self.assertEqual(self.time_advances,[])


if __name__=='__main__':unittest.main()
