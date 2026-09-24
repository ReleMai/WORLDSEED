import unittest

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory, Vitals
from worldseed.entities.store import EntityStore
from worldseed.systems.combat import CombatSystem
from worldseed.systems.ecology import EcologySystem
from worldseed.systems.hunting import HuntingSystem
from worldseed.systems.projectiles import ProjectilePath
from worldseed.systems.state import AnimalSignState, CreatureState, LivingWorldState, pos_key
from worldseed.ui.combat_range import ranged_overlay, melee_overlay


class _Terrain:
    passable = True
    blocks_sight = False
    tags = ("soil",)


class _Tile:
    terrain_id = "core:grass"
    terrain = _Terrain()


class _OpenWorld:
    def tile_at(self, pos):
        return _Tile()

    def is_passable(self, pos):
        return True


class _OverlayProjectileView:
    def __init__(self,sim):self.sim=sim
    def preview(self,origin,target):
        blocked=target if not self.sim._visible_from(origin,target) else None
        return ProjectilePath((origin,target),blocked_at=blocked,cover_penalty=0,cover_notes=())


class _OverlaySim:
    def __init__(self,reg,*,hunting=0,melee=0,perception=5,agility=5,blocked=None):
        self.player_id=1;self.player_pos=WorldPos(0,0,0);self.state=LivingWorldState()
        self.state.player_skills["hunting"]=hunting;self.state.player_skills["melee"]=melee
        self.state.player_attributes["perception"]=perception;self.state.player_attributes["agility"]=agility
        self.entities=EntityStore();self.entities.spawn(preferred_id=1);self.entities.add(1,Vitals())
        self.combat=CombatSystem(self.state,reg,b"overlay")
        self._blocked=set(blocked or ())
        self.projectiles=_OverlayProjectileView(self)
        self.discovered_tiles_set={pos_key(x,y,0) for x in range(-12,13) for y in range(-12,13)}
    def player_attribute(self,key):return int(self.state.player_attributes.get(key,0))
    def player_skill(self,key):return int(self.state.player_skills.get(key,0))
    def _visible_from(self,origin,target):return (target.x,target.y,target.z) not in self._blocked


class CombatHuntingPhaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg = ContentRegistry.load(DATA_DIR)
        cls.world = _OpenWorld()

    def test_ranged_overlay_rotates_with_cursor_and_skill_changes_difficulty(self):
        bow=self.reg.items["core:short_bow"]
        novice=_OverlaySim(self.reg,hunting=0,perception=5)
        expert=_OverlaySim(self.reg,hunting=10,perception=10)
        east_n=ranged_overlay(novice,bow,WorldPos(5,0,0),"center")
        east_e=ranged_overlay(expert,bow,WorldPos(5,0,0),"center")
        self.assertTrue(east_n["cells"])
        self.assertTrue(all(c["x"]>0 for c in east_n["cells"]))
        novice_cell=next(c for c in east_n["cells"] if (c["x"],c["y"])==(5,0))
        expert_cell=next(c for c in east_e["cells"] if (c["x"],c["y"])==(5,0))
        self.assertGreater(expert_cell["chance"],novice_cell["chance"])
        north=ranged_overlay(expert,bow,WorldPos(0,-5,0),"center")
        self.assertTrue(all(c["y"]<0 for c in north["cells"]))

    def test_ranged_overlay_marks_blocked_cells_and_harder_aim_zones(self):
        bow=self.reg.items["core:short_bow"]
        sim=_OverlaySim(self.reg,hunting=6,perception=8,blocked={(4,0,0)})
        center=ranged_overlay(sim,bow,WorldPos(5,0,0),"center")
        head=ranged_overlay(sim,bow,WorldPos(5,0,0),"head")
        blocked=next(c for c in center["cells"] if (c["x"],c["y"])==(4,0))
        self.assertTrue(blocked["blocked"]);self.assertEqual(blocked["difficulty"],"blocked")
        center_far=next(c for c in center["cells"] if (c["x"],c["y"])==(5,0))
        head_far=next(c for c in head["cells"] if (c["x"],c["y"])==(5,0))
        self.assertGreater(center_far["chance"],head_far["chance"])

    def test_melee_overlay_uses_weapon_reach_and_skill(self):
        javelin=self.reg.items["core:wooden_spear"]
        novice=_OverlaySim(self.reg,melee=0,agility=5)
        expert=_OverlaySim(self.reg,melee=8,agility=9)
        low=melee_overlay(novice,javelin,WorldPos(2,0,0))
        high=melee_overlay(expert,javelin,WorldPos(2,0,0))
        coords={(c["x"],c["y"]) for c in low["cells"]}
        self.assertIn((2,0),coords);self.assertNotIn((3,0),coords)
        low_outer=next(c for c in low["cells"] if (c["x"],c["y"])==(2,0))
        high_outer=next(c for c in high["cells"] if (c["x"],c["y"])==(2,0))
        self.assertGreater(high_outer["chance"],low_outer["chance"])

    def test_primitive_combat_loadout_is_craftable_and_distinct(self):
        sling=self.reg.items["core:sling"];bow=self.reg.items["core:short_bow"];javelin=self.reg.items["core:wooden_spear"];club=self.reg.items["core:club"];knife=self.reg.items["core:stone_knife"]
        self.assertEqual(sling.weapon_class,"sling");self.assertEqual(sling.ammo_item,"core:sling_stone")
        self.assertEqual(bow.weapon_class,"bow");self.assertEqual(bow.ammo_item,"core:wood_arrow");self.assertTrue(bow.two_handed)
        self.assertEqual(javelin.weapon_class,"javelin");self.assertTrue(javelin.throwable);self.assertGreaterEqual(javelin.range,4);self.assertEqual(javelin.reach,2)
        self.assertEqual(club.weapon_class,"club");self.assertEqual(knife.weapon_class,"knife")
        for rid in ("core:sling","core:sling_stone","core:short_bow","core:wood_arrow","core:wooden_spear","core:club","core:stone_knife"):
            self.assertIn(rid,self.reg.recipes)

    def test_ready_weapon_is_explicit_and_aim_builds_steadiness(self):
        state=LivingWorldState();combat=CombatSystem(state,self.reg,b"aim")
        inv=Inventory({"core:short_bow":1,"core:wood_arrow":3})
        self.assertIsNone(combat.readied_weapon(inv))
        combat.ready_weapon("core:short_bow",inv)
        self.assertEqual(combat.readied_weapon(inv).id,"core:short_bow")
        deer=CreatureState("aim:deer","core:deer",4,0,0,self.reg.species["core:deer"].max_hp)
        first=combat.aim_at(deer,"vitals",8,6,4);q1=state.player_aim_quality
        second=combat.aim_at(deer,"vitals",8,6,4);q2=state.player_aim_quality
        self.assertGreater(q1,0);self.assertGreater(q2,q1);self.assertIn("aim",first.lower());self.assertIn("aim",second.lower())

    def test_targeted_head_and_leg_shots_use_requested_body_zone(self):
        for zone,expected in (("head",{"head","neck"}),("legs",{"legs","forelegs","hindlegs","fore_flippers","hind_flippers"})):
            state=LivingWorldState(player_readied_weapon="core:short_bow");combat=CombatSystem(state,self.reg,("zone-"+zone).encode())
            deer=CreatureState("target:"+zone,"core:deer",3,0,0,200)
            inv=Inventory({"core:short_bow":1,"core:wood_arrow":20})
            for turn in range(1,20):
                combat.ranged_attack_creature(deer,inv,turn,3,perception=14,hunting=14,weapon_id="core:short_bow",aim_zone=zone,aim_quality=100,stamina=100)
                if deer.wounds:break
            self.assertTrue(deer.wounds,zone);self.assertIn(deer.wounds[-1]["part"],expected)

    def test_save_roundtrip_preserves_ready_weapon_and_aim(self):
        state=LivingWorldState(player_readied_weapon="core:sling",player_aim_target="animal:1",player_aim_zone="head",player_aim_quality=73)
        restored=LivingWorldState.from_dict(state.to_dict())
        self.assertEqual(restored.player_readied_weapon,"core:sling")
        self.assertEqual((restored.player_aim_target,restored.player_aim_zone,restored.player_aim_quality),("animal:1","head",73))

    def test_tactical_species_profiles_are_data_driven_and_distinct(self):
        wolf=self.reg.species["core:wolf"];boar=self.reg.species["core:boar"];moose=self.reg.species["core:moose"];deer=self.reg.species["core:deer"];bear=self.reg.species["core:brown_bear"]
        self.assertEqual(wolf.combat_style,"pack_predator");self.assertGreaterEqual(wolf.pack_coordination,90)
        self.assertEqual(boar.combat_style,"charger");self.assertGreaterEqual(boar.charge_range,4);self.assertGreater(boar.charge_power,60)
        self.assertEqual(moose.combat_style,"territorial_charger");self.assertGreater(moose.charge_power,boar.charge_power)
        self.assertEqual(deer.combat_style,"herd_prey");self.assertGreaterEqual(deer.herd_cohesion,80)
        self.assertEqual(bear.combat_style,"solitary_predator");self.assertGreaterEqual(bear.display_range,3)

    def test_attacked_boar_commits_to_charge_and_builds_momentum(self):
        state=LivingWorldState()
        boar=CreatureState("tactic:boar","core:boar",4,0,0,self.reg.species["core:boar"].max_hp,stamina=105)
        state.creatures[boar.uid]=boar
        hunting=HuntingSystem(state,self.reg,b"boar-charge",self.world)
        hunting.notify_attack(boar,WorldPos(0,0,0),1,500,loudness=70,hit=True)
        attackers=hunting.update_local_ai(WorldPos(0,0,0),2,501)
        self.assertEqual(boar.behavior,"charge");self.assertGreaterEqual(boar.charge_momentum,1);self.assertGreaterEqual(boar.charge_committed_until_turn,3)
        self.assertNotIn(boar.uid,attackers)
        attackers=hunting.update_local_ai(WorldPos(0,0,0),3,502)
        self.assertIn(boar.uid,attackers);self.assertEqual(boar.behavior,"charge");self.assertGreaterEqual(boar.charge_momentum,2)
        self.assertEqual(abs(boar.x)+abs(boar.y),1)

    def test_uninjured_moose_can_threat_display_before_committing(self):
        state=LivingWorldState()
        moose=CreatureState("tactic:moose","core:moose",4,0,0,self.reg.species["core:moose"].max_hp,alertness=100,stamina=135,last_threat_turn=4)
        state.creatures[moose.uid]=moose
        hunting=HuntingSystem(state,self.reg,b"moose-display",self.world)
        hunting.update_local_ai(WorldPos(0,0,0),5,600)
        self.assertEqual(moose.behavior,"display")
        self.assertEqual((moose.x,moose.y),(4,0))
        self.assertEqual(moose.last_display_turn,5)

    def test_wolf_pack_assigns_anchor_and_flanking_roles(self):
        state=LivingWorldState()
        coords=((5,-1),(5,1),(6,0))
        wolves=[]
        for i,(x,y) in enumerate(coords):
            c=CreatureState(f"pack:{i}","core:wolf",x,y,0,self.reg.species["core:wolf"].max_hp,alertness=100,stamina=125,last_threat_turn=1)
            state.creatures[c.uid]=c;wolves.append(c)
        hunting=HuntingSystem(state,self.reg,b"wolf-pack",self.world)
        hunting.update_local_ai(WorldPos(0,0,0),2,700)
        roles={c.pack_role for c in wolves}
        self.assertIn("anchor",roles);self.assertIn("flank_left",roles);self.assertIn("flank_right",roles)
        self.assertEqual(sum(c.behavior=="pursue" for c in wolves),1)
        self.assertEqual(sum(c.behavior=="flank" for c in wolves),2)

    def test_wolf_with_low_stamina_disengages_toward_pack(self):
        state=LivingWorldState()
        tired=CreatureState("pack:tired","core:wolf",3,0,0,self.reg.species["core:wolf"].max_hp,alertness=100,stamina=20,last_threat_turn=1)
        mate=CreatureState("pack:mate","core:wolf",5,1,0,self.reg.species["core:wolf"].max_hp,alertness=100,stamina=125,last_threat_turn=1)
        state.creatures[tired.uid]=tired;state.creatures[mate.uid]=mate
        hunting=HuntingSystem(state,self.reg,b"wolf-disengage",self.world)
        hunting.update_local_ai(WorldPos(0,0,0),2,710)
        self.assertEqual(tired.behavior,"disengage")
        self.assertGreaterEqual(abs(tired.x)+abs(tired.y),3)

    def test_deer_herd_shares_panic_and_flees_as_group(self):
        state=LivingWorldState()
        deer=[]
        for i,(x,y) in enumerate(((5,2),(6,2),(5,3))):
            c=CreatureState(f"herd:{i}","core:deer",x,y,0,self.reg.species["core:deer"].max_hp,stamina=120)
            state.creatures[c.uid]=c;deer.append(c)
        deer[0].panic=100;deer[0].alertness=100;deer[0].last_threat_turn=1
        hunting=HuntingSystem(state,self.reg,b"deer-herd",self.world)
        hunting.update_local_ai(WorldPos(0,0,0),2,720)
        self.assertTrue(all(c.panic>=70 for c in deer))
        self.assertTrue(all(c.behavior=="herd_flee" for c in deer))
        spread=max(c.x for c in deer)-min(c.x for c in deer)+max(c.y for c in deer)-min(c.y for c in deer)
        self.assertLessEqual(spread,7)

    def test_key_hunting_species_have_distinct_behavior_profiles(self):
        rabbit = self.reg.species["core:rabbit"]
        deer = self.reg.species["core:deer"]
        boar = self.reg.species["core:boar"]
        wolf = self.reg.species["core:wolf"]
        self.assertLess(rabbit.flee_threshold, boar.flee_threshold)
        self.assertGreater(deer.scent, rabbit.scent)
        self.assertGreater(boar.defensive_aggression, deer.defensive_aggression)
        self.assertGreater(wolf.hearing, deer.hearing)
        self.assertGreater(wolf.herd_response, rabbit.herd_response)

    def test_wounded_deer_flees_and_leaves_real_blood_sign(self):
        state = LivingWorldState()
        deer = CreatureState(
            "hunt:deer", "core:deer", 3, 0, 0,
            self.reg.species["core:deer"].max_hp,
            wounds=[{"part": "legs", "tissue": "muscle", "type": "pierce", "severity": 55, "bleeding": 4, "fracture": False, "turn": 1}],
            blood=68, pain=55, stamina=120,
        )
        state.creatures[deer.uid] = deer
        hunting = HuntingSystem(state, self.reg, b"deer-blood", self.world)
        before = abs(deer.x) + abs(deer.y)
        hunting.notify_attack(deer, WorldPos(0, 0, 0), 1, 480, loudness=92, hit=True)
        attackers = hunting.update_local_ai(WorldPos(0, 0, 0), 2, 485)
        after = abs(deer.x) + abs(deer.y)
        self.assertNotIn(deer.uid, attackers)
        self.assertEqual(deer.behavior, "wounded_flee")
        self.assertGreater(after, before)
        blood = [s for s in state.animal_signs.values() if s.source_uid == deer.uid and s.kind == "blood"]
        self.assertTrue(blood)
        self.assertTrue(any(s.direction_x or s.direction_y for s in blood))

    def test_alert_boar_defends_when_player_is_adjacent(self):
        state = LivingWorldState()
        boar = CreatureState(
            "hunt:boar", "core:boar", 1, 0, 0,
            self.reg.species["core:boar"].max_hp, stamina=105,
        )
        state.creatures[boar.uid] = boar
        hunting = HuntingSystem(state, self.reg, b"boar-defense", self.world)
        hunting.notify_attack(boar, WorldPos(0, 0, 0), 4, 500, loudness=50, hit=False)
        attackers = hunting.update_local_ai(WorldPos(0, 0, 0), 5, 505)
        self.assertEqual(boar.behavior, "defend")
        self.assertIn(boar.uid, attackers)
        self.assertEqual((boar.x, boar.y), (1, 0))

    def test_ranged_hunting_uses_species_body_and_deep_wound_model(self):
        state = LivingWorldState()
        combat = CombatSystem(state, self.reg, b"ranged-body")
        deer = CreatureState("target:deer", "core:deer", 2, 0, 0, self.reg.species["core:deer"].max_hp)
        inv = Inventory({"core:sling": 1, "core:sling_stone": 20})
        state.player_readied_weapon="core:sling"
        before_ammo = inv.count("core:sling_stone")
        for turn in range(1, 16):
            combat.ranged_attack_creature(deer, inv, turn, 2, perception=12, hunting=12, weapon_id="core:sling")
            if deer.wounds:
                break
        self.assertTrue(deer.wounds)
        wound = deer.wounds[-1]
        self.assertIn(wound["part"], self.reg.species["core:deer"].body)
        self.assertIn(wound["tissue"], {"skin", "muscle", "bone", "organ"})
        self.assertEqual(wound["weapon"], "core:sling")
        self.assertGreaterEqual(wound["bleeding"], 1)
        self.assertLess(inv.count("core:sling_stone"), before_ammo)

    def test_animal_signs_and_behavior_survive_state_roundtrip(self):
        state = LivingWorldState()
        state.creatures["c"] = CreatureState(
            "c", "core:deer", 4, 5, 0, 20,
            behavior="wounded_flee", alertness=90, stamina=44,
            threat_x=0, threat_y=0, threat_z=0, last_threat_turn=9,
            charge_committed_until_turn=12, charge_momentum=2, pack_role="flank_left",
            panic=71, last_display_turn=8, last_attacked_turn=9,
        )
        state.animal_signs["s"] = AnimalSignState(
            "s", "core:deer", 4, 5, 0, "blood", 500,
            direction_x=1, strength=70, source_uid="c",
        )
        restored = LivingWorldState.from_dict(state.to_dict())
        self.assertEqual(restored.creatures["c"].behavior, "wounded_flee")
        self.assertEqual(restored.creatures["c"].threat_x, 0)
        self.assertEqual(restored.creatures["c"].charge_momentum,2)
        self.assertEqual(restored.creatures["c"].pack_role,"flank_left")
        self.assertEqual(restored.creatures["c"].panic,71)
        self.assertEqual(restored.creatures["c"].last_attacked_turn,9)
        self.assertEqual(restored.animal_signs["s"].kind, "blood")
        self.assertEqual(restored.animal_signs["s"].source_uid, "c")

    def test_active_wounded_animal_gets_extended_chase_envelope(self):
        state = LivingWorldState()
        deer = CreatureState(
            "hunt:far-deer", "core:deer", 600, 0, 0, 30,
            wounds=[{"part": "torso", "severity": 40, "bleeding": 2}],
            behavior="wounded_flee",
        )
        state.creatures[deer.uid] = deer
        ecology = EcologySystem(state, self.reg, b"chase-envelope")
        ecology.dematerialize_far(WorldPos(0, 0, 0), 420)
        self.assertIn(deer.uid, state.creatures)
        deer.x = 900
        ecology.dematerialize_far(WorldPos(0, 0, 0), 420)
        self.assertNotIn(deer.uid, state.creatures)

    def test_animal_attack_still_uses_player_armor_and_wounds(self):
        state = LivingWorldState()
        combat = CombatSystem(state, self.reg, b"armor")
        wolf = CreatureState("wolf", "core:wolf", 1, 0, 0, self.reg.species["core:wolf"].max_hp)
        naked = Vitals()
        combat.creature_attack_player(wolf, naked, 77)
        naked_damage = naked.max_hp - naked.hp

        state.player_wounds.clear()
        state.player_equipment = {
            "head": "core:leather_hood",
            "body": "core:leather_vest",
            "hands": "core:leather_bracers",
            "legs": "core:leather_leggings",
        }
        armored = Vitals()
        combat.creature_attack_player(wolf, armored, 77)
        self.assertLessEqual(armored.max_hp - armored.hp, naked_damage)
        self.assertTrue(state.player_wounds)


if __name__ == "__main__":
    unittest.main()
