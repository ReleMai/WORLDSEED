import unittest

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory, Vitals
from worldseed.systems.combat import CombatSystem
from worldseed.systems.ecology import EcologySystem
from worldseed.systems.hunting import HuntingSystem
from worldseed.systems.state import AnimalSignState, CreatureState, LivingWorldState


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


class CombatHuntingPhaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg = ContentRegistry.load(DATA_DIR)
        cls.world = _OpenWorld()

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
        before_ammo = inv.count("core:sling_stone")
        for turn in range(1, 16):
            combat.ranged_attack_creature(deer, inv, turn, 2, perception=12, hunting=12)
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
        )
        state.animal_signs["s"] = AnimalSignState(
            "s", "core:deer", 4, 5, 0, "blood", 500,
            direction_x=1, strength=70, source_uid="c",
        )
        restored = LivingWorldState.from_dict(state.to_dict())
        self.assertEqual(restored.creatures["c"].behavior, "wounded_flee")
        self.assertEqual(restored.creatures["c"].threat_x, 0)
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
