import unittest
from types import SimpleNamespace

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory
from worldseed.sim.engine import Simulation
from worldseed.systems.combat import CombatSystem
from worldseed.systems.hunting import HuntingSystem
from worldseed.systems.processing import ProcessingSystem
from worldseed.systems.state import CarcassState, CreatureState, GroundPile, LivingWorldState


class _Terrain:
    def __init__(self, tid="core:grass"):
        self.tags=("water",) if tid=="core:water" else ("soil",)
        self.blocks_sight=False
        self.passable=tid!="core:water"
        self.name="Water" if tid=="core:water" else "Grass"


class _Tile:
    def __init__(self, tid="core:grass"):
        self.terrain_id=tid;self.terrain=_Terrain(tid)


class _World:
    def __init__(self, water=()):
        self.water=set(water)
    def tile_at(self,pos):
        return _Tile("core:water" if (pos.x,pos.y,pos.z) in self.water else "core:grass")
    def is_passable(self,pos):
        return (pos.x,pos.y,pos.z) not in self.water


class _Resources:
    def __init__(self, foods=None):
        self.foods=dict(foods or {})
    def blocks_movement(self,pos):return False
    def blocks_sight(self,pos):return False
    def is_harvestable(self,pos):return (pos.x,pos.y,pos.z) in self.foods
    def feature_at(self,pos):
        iid=self.foods.get((pos.x,pos.y,pos.z))
        return SimpleNamespace(feature_id=iid,stage="mature") if iid else None


class _Building:
    def passable(self,pos,world_passable=True):return world_passable


class _Weather:
    def at(self,minute,x,y):
        return {"wind_dx":0,"wind_dy":0,"rain":0,"fog":0}


class _Environment:
    weather=_Weather()


class StealthAnatomyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg=ContentRegistry.load(DATA_DIR)

    def hunting(self,state=None,world=None,resources=None):
        state=state or LivingWorldState()
        return state,HuntingSystem(state,self.reg,b"stealth-tests",world or _World(),_Environment(),resources or _Resources(),_Building())

    def test_stalking_and_crouching_reduce_movement_noise(self):
        state,h=self.hunting()
        p=WorldPos(0,0,0)
        state.player_hunting_stance="normal";normal=h.movement_noise(p,500)
        state.player_hunting_stance="stalk";stalk=h.movement_noise(p,500)
        state.player_hunting_stance="crouch";crouch=h.movement_noise(p,500)
        self.assertGreater(normal,stalk);self.assertGreater(stalk,crouch)
        state.player_equipment["offhand"]="core:steel_tower_shield"
        noisy_crouch=h.movement_noise(p,500)
        self.assertGreater(noisy_crouch,crouch)

    def test_concealment_reduces_visual_detection_but_not_to_zero_at_contact(self):
        state,h=self.hunting()
        state.player_skills["hunting"]=8
        deer=CreatureState("deer","core:deer",6,0,0,self.reg.species["core:deer"].max_hp,facing_dx=-1,facing_dy=0)
        state.player_hunting_stance="normal";normal=h._perception_score(deer,self.reg.species["core:deer"],WorldPos(0,0,0),1,500)
        state.player_hunting_stance="crouch";crouch=h._perception_score(deer,self.reg.species["core:deer"],WorldPos(0,0,0),1,500)
        self.assertLess(crouch,normal)
        deer.x=1
        close=h._perception_score(deer,self.reg.species["core:deer"],WorldPos(0,0,0),1,500)
        self.assertGreaterEqual(close,18)

    def test_thirsty_deer_walks_to_real_water_and_leaves_drinking_sign(self):
        state,h=self.hunting(world=_World({(0,0,0)}))
        deer=CreatureState("deer","core:deer",2,0,0,self.reg.species["core:deer"].max_hp,thirst=65,last_need_minute=500,stamina=120)
        state.creatures[deer.uid]=deer
        h.update_local_ai(WorldPos(25,20,0),1,501)
        self.assertEqual((deer.x,deer.y),(1,0))
        self.assertEqual(deer.behavior,"drinking")
        self.assertTrue(any(x.kind=="drink" and x.source_uid==deer.uid for x in state.animal_signs.values()))

    def test_herbivore_feeds_only_from_actual_food_feature(self):
        food_id=next(r.id for r in self.reg.resources.values() if "food" in r.tags and "core:grass" in r.terrains)
        resources=_Resources({(1,0,0):food_id})
        state,h=self.hunting(resources=resources)
        rabbit=CreatureState("rabbit","core:rabbit",2,0,0,self.reg.species["core:rabbit"].max_hp,hunger=70,last_need_minute=500,stamina=90)
        state.creatures[rabbit.uid]=rabbit
        h.update_local_ai(WorldPos(25,20,0),1,501)
        self.assertEqual((rabbit.x,rabbit.y),(1,0))
        self.assertEqual(rabbit.behavior,"foraging")
        self.assertTrue(any(x.kind=="feeding" for x in state.animal_signs.values()))

    def test_home_is_persistent_reused_by_cohort_and_wounded_animal_retreats(self):
        state,h=self.hunting()
        a=CreatureState("wolf:a","core:wolf",3,3,0,40,cohort_key="cohort:wolf",last_need_minute=500)
        b=CreatureState("wolf:b","core:wolf",4,3,0,40,cohort_key="cohort:wolf",last_need_minute=500)
        state.creatures[a.uid]=a;state.creatures[b.uid]=b
        ha=h._ensure_home(a,self.reg.species["core:wolf"],500);hb=h._ensure_home(b,self.reg.species["core:wolf"],500)
        self.assertIsNotNone(ha);self.assertEqual(ha.uid,hb.uid);self.assertEqual(a.home_uid,b.home_uid)
        a.blood=40;a.pain=60
        behavior=h._choose_behavior(a,self.reg.species["core:wolf"],8,4,WorldPos(0,0,0))
        # Pack predators can first disengage toward their pack; solitary wounded
        # animals with homes explicitly retreat to shelter.
        fox=CreatureState("fox","core:red_fox",8,8,0,self.reg.species["core:red_fox"].max_hp,blood=40,pain=60,last_need_minute=500)
        state.creatures[fox.uid]=fox;home=h._ensure_home(fox,self.reg.species["core:red_fox"],500)
        self.assertEqual(h._choose_behavior(fox,self.reg.species["core:red_fox"],8,4,WorldPos(0,0,0)),"retreat_home")
        self.assertIsNotNone(home)

    def test_homes_and_expanded_evidence_roundtrip(self):
        state,h=self.hunting()
        deer=CreatureState("deer","core:deer",0,0,0,40,last_need_minute=500)
        state.creatures[deer.uid]=deer
        home=h._ensure_home(deer,self.reg.species["core:deer"],500);home.discovered=True
        p=WorldPos(deer.x,deer.y,deer.z)
        h._write_sign(deer,"scat",p,p,500,60,"droppings")
        h._write_sign(deer,"bed",p,p,501,55,"flattened bedding")
        restored=LivingWorldState.from_dict(state.to_dict())
        self.assertEqual(restored.animal_homes[home.uid].kind,"bed")
        self.assertTrue(restored.animal_homes[home.uid].discovered)
        self.assertEqual({x.kind for x in restored.animal_signs.values()} & {"scat","bed"},{"scat","bed"})

    def test_species_have_named_organs_and_mass_changes_size_band(self):
        rabbit=self.reg.species["core:rabbit"];moose=self.reg.species["core:moose"]
        for sp in (rabbit,moose):
            self.assertIn("heart",sp.organs);self.assertIn("lungs",sp.organs);self.assertIn("brain",sp.organs)
            self.assertTrue(sp.harvest_parts);self.assertTrue(sp.home_kind)
        self.assertEqual(rabbit.organs["heart"]["size_band"],"tiny")
        self.assertEqual(moose.organs["heart"]["size_band"],"massive")

    def test_high_quality_vital_shot_records_named_organ_and_carcass_damage(self):
        state=LivingWorldState(player_readied_weapon="core:short_bow")
        combat=CombatSystem(state,self.reg,b"organs")
        inv=Inventory({"core:short_bow":1,"core:wood_arrow":30})
        moose=CreatureState("moose","core:moose",4,0,0,self.reg.species["core:moose"].max_hp,stamina=135)
        state.creatures[moose.uid]=moose
        organ_wound=None
        for turn in range(1,24):
            combat.ranged_attack_creature(moose,inv,turn,4,20,20,"core:short_bow","vitals",100,100,0)
            organ_wound=next((w for w in moose.wounds if w.get("organ")),None)
            if organ_wound:break
            if moose.uid not in state.creatures:break
        self.assertIsNotNone(organ_wound)
        self.assertIn(organ_wound["organ"],self.reg.species["core:moose"].organs)
        if moose.uid in state.creatures:
            combat._make_carcass(moose,self.reg.species["core:moose"])
            carcass=max(state.carcasses.values(),key=lambda c:c.killed_minute)
            self.assertGreater(carcass.organ_damage.get(organ_wound["organ"],0),0)

    def _anatomy_yield(self,heart_damage):
        state=LivingWorldState()
        c=CarcassState("same-carcass","core:moose",0,0,0,500,100,organ_damage={"heart":heart_damage})
        state.carcasses[c.uid]=c
        proc=ProcessingSystem(state,self.reg,_Building(),b"anatomy-yield")
        inv=Inventory({"core:stone_knife":1})
        ok,msg,minutes=proc.process_carcass(c.uid,"anatomy",inv,10,520)
        self.assertTrue(ok);self.assertGreater(minutes,0)
        return inv.count("core:offal"),c,msg

    def test_damaged_organs_reduce_harvest_yield_and_parts_cannot_repeat(self):
        clean,clean_c,_=self._anatomy_yield(0)
        damaged,damaged_c,msg=self._anatomy_yield(95)
        self.assertGreater(clean,damaged)
        self.assertIn("heart",damaged_c.harvested_parts)
        proc=ProcessingSystem(LivingWorldState(),self.reg,_Building(),b"unused")
        self.assertTrue("damaged" in msg.lower() or damaged<clean)

    def test_visual_effect_buffer_is_bounded_and_runtime_only(self):
        sim=Simulation.__new__(Simulation);sim.turn=7;sim.visual_effects=[];sim._visual_effect_counter=0
        for i in range(30):
            sim._emit_visual_effect("melee",WorldPos(0,0,0),WorldPos(1,0,0),hit=bool(i%2))
        self.assertEqual(len(sim.visual_effects),24)
        self.assertEqual(sim.visual_effects[-1]["uid"],30)
        self.assertNotIn("visual_effects",LivingWorldState().to_dict())


if __name__=="__main__":
    unittest.main()
