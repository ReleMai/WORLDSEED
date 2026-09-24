import unittest
from types import SimpleNamespace

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory, Position, Vitals
from worldseed.entities.store import EntityStore
from worldseed.sim.commands import DisengageCommand
from worldseed.sim.engine import Simulation
from worldseed.systems.combat import CombatSystem
from worldseed.systems.hunting import HuntingSystem
from worldseed.systems.state import CreatureState, LivingWorldState


class _Terrain:
    blocks_sight=False
    tags=("soil",)
    name="Grass"
    def __init__(self,blocked=False):
        self.passable=not blocked


class _Tile:
    def __init__(self,blocked=False):
        self.terrain_id="core:rock" if blocked else "core:grass"
        self.terrain=_Terrain(blocked)


class _World:
    def __init__(self,blocked=()):
        self.blocked=set(blocked)
    def tile_at(self,pos):
        return _Tile((pos.x,pos.y,pos.z) in self.blocked)
    def is_passable(self,pos):
        return (pos.x,pos.y,pos.z) not in self.blocked


class _Resources:
    def blocks_movement(self,pos):return False
    def blocks_sight(self,pos):return False
    def is_harvestable(self,pos):return False


class _Building:
    def passable(self,pos,world_passable=True):return world_passable
    def blocks_sight(self,pos):return False


class _Environment:
    def fluid_passable(self,pos):return True


class _HuntingStub:
    def movement_noise(self,pos):return 26
    def note_player_noise(self,*args,**kwargs):pass
    def notify_attack(self,*args,**kwargs):pass


class CombatSpacingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg=ContentRegistry.load(DATA_DIR)

    def make_sim(self,blocked=()):
        sim=Simulation.__new__(Simulation)
        sim.registry=self.reg;sim.state=LivingWorldState();sim.seed=b"combat-spacing"
        sim.entities=EntityStore();sim.entities.spawn(preferred_id=1)
        sim.entities.add(1,Position(WorldPos(0,0,0)));sim.entities.add(1,Inventory());sim.entities.add(1,Vitals())
        sim.world=_World(blocked);sim.resources=_Resources();sim.building=_Building();sim.environment=_Environment()
        sim.combat=CombatSystem(sim.state,self.reg,sim.seed);sim.hunting=_HuntingStub()
        sim.turn=10;sim.clock=SimpleNamespace(minute=500);sim.log=[]
        return sim

    def test_disengage_creates_space_marks_exchange_and_spends_stamina(self):
        sim=self.make_sim()
        wolf=CreatureState("wolf","core:wolf",1,0,0,self.reg.species["core:wolf"].max_hp,alertness=100,stamina=125)
        sim.state.creatures[wolf.uid]=wolf
        v=sim.entities.get(1,Vitals)
        sim._disengage(DisengageCommand(1,-1,0))
        self.assertEqual(sim.player_pos,WorldPos(-1,0,0))
        self.assertEqual(v.stamina,95)
        self.assertEqual(sim.state.player_disengage_turn,11)
        self.assertIn("disengage",sim.log[-1].message.lower())

    def test_disengage_rejects_toward_threat_or_blocked_retreat(self):
        sim=self.make_sim(blocked={(-1,0,0)})
        wolf=CreatureState("wolf","core:wolf",1,0,0,self.reg.species["core:wolf"].max_hp)
        sim.state.creatures[wolf.uid]=wolf
        sim._disengage(DisengageCommand(1,1,0))
        self.assertEqual(sim.player_pos,WorldPos(0,0,0))
        self.assertIn("create space",sim.log[-1].message.lower())
        sim._disengage(DisengageCommand(1,-1,0))
        self.assertEqual(sim.player_pos,WorldPos(0,0,0))
        self.assertIn("clear retreat",sim.log[-1].message.lower())

    def test_open_knockback_physically_moves_creature(self):
        sim=self.make_sim()
        boar=CreatureState("boar","core:boar",1,0,0,self.reg.species["core:boar"].max_hp,stamina=105)
        sim.state.creatures[boar.uid]=boar
        msgs=sim._push_creature_from(boar,WorldPos(0,0,0),1,30)
        self.assertEqual((boar.x,boar.y),(2,0))
        self.assertTrue(any("driven back" in m.lower() for m in msgs))
        self.assertLess(boar.stamina,105)

    def test_blocked_knockback_becomes_collision_injury(self):
        sim=self.make_sim(blocked={(2,0,0)})
        boar=CreatureState("boar","core:boar",1,0,0,self.reg.species["core:boar"].max_hp,stamina=105)
        sim.state.creatures[boar.uid]=boar
        hp=boar.hp
        msgs=sim._push_creature_from(boar,WorldPos(0,0,0),1,45)
        self.assertEqual((boar.x,boar.y),(1,0))
        self.assertLess(boar.hp,hp)
        self.assertTrue(boar.wounds)
        self.assertGreaterEqual(boar.staggered_until_turn,sim.turn+1)
        self.assertTrue(any("solid terrain" in m.lower() for m in msgs))

    def test_player_charge_knockback_moves_until_obstacle_then_injures(self):
        sim=self.make_sim(blocked={(-2,0,0)})
        v=sim.entities.get(1,Vitals);hp=v.hp
        msgs=sim._push_player_from(WorldPos(1,0,0),2,60)
        self.assertEqual(sim.player_pos,WorldPos(-1,0,0))
        self.assertLess(v.hp,hp)
        self.assertTrue(sim.state.player_wounds)
        self.assertTrue(any("solid terrain" in m.lower() for m in msgs))

    def test_prepared_reach_weapon_can_stop_normal_closing_approach(self):
        state=LivingWorldState(player_readied_weapon="core:wooden_spear",player_defense_mode="parry")
        state.player_skills["melee"]=20;state.player_attributes["agility"]=18;state.player_attributes["strength"]=12
        combat=CombatSystem(state,self.reg,b"reach-control");inv=Inventory({"core:wooden_spear":1})
        wolf=CreatureState("wolf","core:wolf",1,0,0,self.reg.species["core:wolf"].max_hp,behavior="pursue",stamina=125)
        state.creatures[wolf.uid]=wolf
        stopped=False
        for turn in range(1,60):
            attempted,stopped,msg=combat.intercept_approach(wolf,inv,turn,100)
            self.assertTrue(attempted)
            if stopped:
                self.assertIn("stop the approach",msg.lower())
                break
        self.assertTrue(stopped)
        if wolf.uid in state.creatures:self.assertLess(wolf.stamina,125)

    def test_disengage_spacing_grace_prevents_immediate_normal_reengagement(self):
        state=LivingWorldState(player_disengage_turn=2)
        wolf=CreatureState("wolf","core:wolf",2,0,0,self.reg.species["core:wolf"].max_hp,alertness=100,stamina=125,last_threat_turn=1)
        state.creatures[wolf.uid]=wolf
        hunting=HuntingSystem(state,self.reg,b"spacing-grace",_World())
        attackers=hunting.update_local_ai(WorldPos(0,0,0),2,600)
        self.assertEqual(abs(wolf.x)+abs(wolf.y),1)
        self.assertNotIn(wolf.uid,attackers)

    def test_committed_charge_ignores_disengage_spacing_grace(self):
        state=LivingWorldState(player_disengage_turn=2)
        boar=CreatureState("boar","core:boar",2,0,0,self.reg.species["core:boar"].max_hp,behavior="charge",alertness=100,stamina=105,last_threat_turn=1,charge_committed_until_turn=4,charge_momentum=1)
        state.creatures[boar.uid]=boar
        hunting=HuntingSystem(state,self.reg,b"charge-grace",_World())
        attackers=hunting.update_local_ai(WorldPos(0,0,0),2,600)
        self.assertIn(boar.uid,attackers)
        self.assertEqual(abs(boar.x)+abs(boar.y),1)


if __name__=="__main__":
    unittest.main()
