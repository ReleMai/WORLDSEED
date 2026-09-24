import unittest
from types import SimpleNamespace

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.core.rng import PCG32
from worldseed.entities.components import Inventory
from worldseed.systems.combat import CombatSystem
from worldseed.systems.hunting import HuntingSystem
from worldseed.systems.processing import ProcessingSystem
from worldseed.systems.state import AnimalDenState, CreatureState, GroundPile, LivingWorldState
from worldseed.ui.combat_animation import combat_animation_frames


class _Terrain:
    blocks_sight=False
    passable=True
    tags=("soil",)
    name="Grass"
    def __init__(self,tid="core:grass"):
        self.name=tid.split(":")[-1].replace("_"," ").title()
        if "forest" in tid:self.tags=("soil","forest")
        elif "water" in tid:self.tags=("water",)
        else:self.tags=("soil",)


class _Tile:
    def __init__(self,tid="core:grass"):
        self.terrain_id=tid;self.terrain=_Terrain(tid)


class _World:
    def __init__(self,water=()):
        self.water=set(water)
    def tile_at(self,pos):
        return _Tile("core:river_shallow" if (pos.x,pos.y,pos.z) in self.water else "core:forest")
    def is_passable(self,pos):
        return (pos.x,pos.y,pos.z) not in self.water


class _Resources:
    def __init__(self,food=()):
        self.food=set(food)
    def is_harvestable(self,pos):return (pos.x,pos.y,pos.z) in self.food
    def blocks_movement(self,pos):return False
    def blocks_sight(self,pos):return False
    def feature_at(self,pos):
        if (pos.x,pos.y,pos.z) in self.food:return SimpleNamespace(feature_id="core:blueberry_bush")
        return None


class _Weather:
    def at(self,minute,x,y):
        return {"wind_dx":-1,"wind_dy":0,"wind_speed":0,"rain":0,"visibility":8}


class _Environment:
    def __init__(self):self.weather=_Weather()
    def fluid_at(self,pos):return None


class _Building:
    def passable(self,pos,world_passable=True):return world_passable
    def blocks_sight(self,pos):return False


class HuntingStealthAnatomyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg=ContentRegistry.load(DATA_DIR)

    def hunting(self,state=None,world=None,resources=None):
        state=state or LivingWorldState()
        return HuntingSystem(state,self.reg,b"phase7",world or _World(),_Environment(),resources or _Resources(),_Building())

    def test_stalking_reduces_noise_and_visual_detection_in_cover(self):
        state=LivingWorldState();state.player_skills["hunting"]=10;state.player_attributes["agility"]=11
        hunting=self.hunting(state)
        pos=WorldPos(0,0,0)
        normal=hunting.movement_noise(pos,500)
        state.player_stance="stalk"
        quiet=hunting.movement_noise(pos,500)
        self.assertLess(quiet,normal)
        deer=CreatureState("deer","core:deer",5,0,0,self.reg.species["core:deer"].max_hp,facing_dx=-1,facing_dy=0)
        state.player_stance="normal";seen=hunting._perception_score(deer,self.reg.species["core:deer"],pos,2,500)
        state.player_stance="stalk";hidden=hunting._perception_score(deer,self.reg.species["core:deer"],pos,2,500)
        self.assertLess(hidden,seen)

    def test_drinking_feeding_and_resting_write_real_evidence(self):
        state=LivingWorldState();world=_World(water={(1,0,0)});resources=_Resources(food={(0,1,0)})
        hunting=self.hunting(state,world,resources);sp=self.reg.species["core:deer"]
        deer=CreatureState("deer","core:deer",0,0,0,sp.max_hp,stamina=120,thirst=80,last_need_minute=500)
        state.creatures[deer.uid]=deer
        den=AnimalDenState("den:test","core:deer",0,0,0,"bed",500,last_used_minute=500,detail="flattened bedding site")
        state.animal_dens[den.uid]=den;deer.home_den_uid=den.uid

        self.assertTrue(hunting._activity_tick(deer,sp,WorldPos(30,30,0),1,500))
        if deer.activity=="to_water":
            self.assertTrue(hunting._activity_tick(deer,sp,WorldPos(30,30,0),2,501))
        self.assertEqual(deer.activity,"drinking")
        self.assertTrue(any(x.kind=="drink" for x in state.animal_signs.values()))

        deer.activity="";deer.thirst=0;deer.hunger=80
        self.assertTrue(hunting._activity_tick(deer,sp,WorldPos(30,30,0),3,510))
        self.assertIn(deer.activity,("to_food","feeding"))
        if deer.activity=="to_food":
            hunting._activity_tick(deer,sp,WorldPos(30,30,0),4,511)
        if deer.activity=="feeding":
            self.assertTrue(any(x.kind=="feeding" for x in state.animal_signs.values()))
            self.assertTrue(state.resource_depletion)

        deer.activity="";deer.hunger=0;deer.stamina=20
        self.assertTrue(hunting._activity_tick(deer,sp,WorldPos(30,30,0),5,520))
        if deer.activity=="to_den":hunting._activity_tick(deer,sp,WorldPos(30,30,0),6,521)
        self.assertIn(deer.activity,("resting","to_den"))
        if deer.activity=="resting":self.assertTrue(any(x.kind=="bed" for x in state.animal_signs.values()))

    def test_den_is_stable_bounded_physical_state_and_roundtrips(self):
        state=LivingWorldState();hunting=self.hunting(state);sp=self.reg.species["core:wolf"]
        wolf=CreatureState("wolf","core:wolf",3,4,0,sp.max_hp,cohort_key="0,0:core:wolf:0")
        state.creatures[wolf.uid]=wolf
        a=hunting._ensure_den(wolf,sp,600);b=hunting._ensure_den(wolf,sp,610)
        self.assertIsNotNone(a);self.assertEqual(a.uid,b.uid);self.assertEqual(wolf.home_den_uid,a.uid)
        a.stored_items["core:bone"]=2
        restored=LivingWorldState.from_dict(state.to_dict())
        self.assertEqual(restored.creatures["wolf"].home_den_uid,a.uid)
        self.assertEqual(restored.animal_dens[a.uid].stored_items["core:bone"],2)

    def test_predator_cache_moves_existing_food_instead_of_inventing_loot(self):
        state=LivingWorldState();hunting=self.hunting(state);sp=self.reg.species["core:wolf"]
        wolf=CreatureState("wolf","core:wolf",0,0,0,sp.max_hp,cohort_key="pack",hunger=80)
        state.creatures[wolf.uid]=wolf
        den=AnimalDenState("den:wolf","core:wolf",0,0,0,"den",500,cohort_key="pack",last_used_minute=500,detail="sheltered den")
        state.animal_dens[den.uid]=den;wolf.home_den_uid=den.uid
        state.ground_piles["0,0,0"]=GroundPile(0,0,0,{"core:raw_game_meat":1})
        wolf.activity="feeding";wolf.activity_until_turn=2
        hunting._activity_tick(wolf,sp,WorldPos(20,20,0),1,500)
        self.assertEqual(wolf.carried_item_id,"core:raw_game_meat")
        self.assertNotIn("core:raw_game_meat",state.ground_piles["0,0,0"].items)
        hunting._activity_tick(wolf,sp,WorldPos(20,20,0),3,503)
        hunting._activity_tick(wolf,sp,WorldPos(20,20,0),4,504)
        self.assertEqual(den.stored_items.get("core:raw_game_meat"),1)
        self.assertEqual(wolf.carried_item_id,"")

    def test_anatomy_scales_with_species_mass_and_records_damage(self):
        state=LivingWorldState();combat=CombatSystem(state,self.reg,b"anatomy")
        rabbit_sp=self.reg.species["core:rabbit"];deer_sp=self.reg.species["core:deer"]
        rabbit=CreatureState("r","core:rabbit",0,0,0,rabbit_sp.max_hp)
        deer=CreatureState("d","core:deer",0,0,0,deer_sp.max_hp)
        name,extra,bleed=combat._injure_anatomy(deer,deer_sp,"torso","organ",8,PCG32(12345))
        self.assertTrue(name);self.assertGreater(deer.organ_damage[name],0);self.assertGreaterEqual(bleed,0)
        state.creatures[rabbit.uid]=rabbit;state.creatures[deer.uid]=deer
        combat._make_carcass(rabbit,rabbit_sp);combat._make_carcass(deer,deer_sp)
        carcasses={c.species_id:c for c in state.carcasses.values()}
        self.assertGreater(carcasses["core:deer"].anatomy_mass_g["heart"],carcasses["core:rabbit"].anatomy_mass_g["heart"])
        self.assertLess(carcasses["core:deer"].anatomy_condition[name],100)

    def test_species_have_real_body_regions_and_specialized_parts(self):
        deer=self.reg.species["core:deer"];boar=self.reg.species["core:boar"];turkey=self.reg.species["core:turkey"]
        for sp in (deer,boar,turkey):
            self.assertIn("neck",sp.body);self.assertIn("heart",sp.anatomy);self.assertIn("liver",sp.anatomy)
        self.assertIn("antlers",deer.anatomy);self.assertEqual(deer.anatomy["antlers"]["harvest"],"bone")
        self.assertIn("tusks",boar.anatomy)
        self.assertIn("wings",turkey.body);self.assertEqual(turkey.anatomy["feathers"]["harvest"],"feather")

    def test_anatomy_processing_converts_named_parts_to_real_existing_materials(self):
        state=LivingWorldState();combat=CombatSystem(state,self.reg,b"process-anatomy")
        deer_sp=self.reg.species["core:deer"];deer=CreatureState("d","core:deer",0,0,0,deer_sp.max_hp)
        deer.organ_damage["liver"]=90
        state.creatures[deer.uid]=deer;combat._make_carcass(deer,deer_sp)
        carcass=next(iter(state.carcasses.values()))
        processing=ProcessingSystem(state,self.reg,_Building());inv=Inventory({"core:stone_knife":1})
        ok,msg,minutes=processing.process_carcass(carcass.uid,"anatomy",inv,8,500)
        self.assertTrue(ok);self.assertGreater(minutes,0);self.assertIn("heart",msg.lower())
        self.assertGreater(inv.count("core:offal"),0);self.assertGreater(inv.count("core:bone"),0)
        self.assertTrue(carcass.harvested_anatomy)

    def test_combat_animation_frames_are_presentation_only_and_bounded(self):
        cells=(WorldPos(0,0,0),WorldPos(1,0,0),WorldPos(2,0,0),WorldPos(3,0,0))
        frames=combat_animation_frames("ranged",cells)
        self.assertGreaterEqual(len(frames),2);self.assertLessEqual(len(frames),6)
        self.assertTrue(all(frame["cells"] for frame in frames))
        melee=combat_animation_frames("melee",(WorldPos(0,0,0),WorldPos(1,0,0)))
        self.assertEqual(len(melee),2)


if __name__=="__main__":
    unittest.main()
