import tempfile
import unittest
from pathlib import Path

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory, Position, Vitals
from worldseed.entities.store import EntityStore
from worldseed.persistence.database import WorldDatabase
from worldseed.sim.commands import WaitCommand
from worldseed.sim.engine import Simulation
from worldseed.systems.hunting import HuntingSystem
from worldseed.systems.state import AnimalSignState, CreatureState, LivingWorldState
from worldseed.world.generator import WorldGenerator
from worldseed.world.world import World


class CombatHuntingPhaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg = ContentRegistry.load(DATA_DIR)

    def make_sim(self, seed=b"combat-hunting"):
        td = tempfile.TemporaryDirectory()
        db = WorldDatabase.create(Path(td.name) / "combat.db", "combat", seed.hex())
        world = World(WorldGenerator(seed, self.reg), self.reg, db)
        entities = EntityStore()
        pid = entities.spawn(preferred_id=1)
        entities.add(pid, Position(WorldPos(0, 0, 0)))
        entities.add(pid, Inventory({"core:sling": 1, "core:sling_stone": 20, "core:wooden_spear": 1}))
        entities.add(pid, Vitals())
        sim = Simulation(world, entities, self.reg, 0, LivingWorldState(), seed)
        return td, db, world, entities, pid, sim

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
        td, db, world, entities, pid, sim = self.make_sim(b"deer-blood")
        try:
            sim.state.creatures.clear()
            sim.state.animal_signs.clear()
            for x in range(-2, 9):
                for y in range(-4, 5):
                    world.set_terrain(WorldPos(x, y, 0), "core:grass")
            deer = CreatureState(
                "hunt:deer", "core:deer", 3, 0, 0,
                self.reg.species["core:deer"].max_hp,
                wounds=[{"part": "legs", "tissue": "muscle", "type": "pierce", "severity": 55, "bleeding": 4, "fracture": False, "turn": 1}],
                blood=68, pain=55, stamina=120,
            )
            sim.state.creatures[deer.uid] = deer
            hunting = HuntingSystem(sim.state, self.reg, b"deer-blood", world)
            before = abs(deer.x) + abs(deer.y)
            hunting.notify_attack(deer, WorldPos(0, 0, 0), 1, 480, loudness=92, hit=True)
            attackers = hunting.update_local_ai(WorldPos(0, 0, 0), 2, 485)
            after = abs(deer.x) + abs(deer.y)
            self.assertNotIn(deer.uid, attackers)
            self.assertEqual(deer.behavior, "wounded_flee")
            self.assertGreater(after, before)
            blood = [s for s in sim.state.animal_signs.values() if s.source_uid == deer.uid and s.kind == "blood"]
            self.assertTrue(blood)
            self.assertTrue(any(s.direction_x or s.direction_y for s in blood))
        finally:
            db.close()
            td.cleanup()

    def test_alert_boar_defends_when_player_is_adjacent(self):
        td, db, world, entities, pid, sim = self.make_sim(b"boar-defense")
        try:
            sim.state.creatures.clear()
            world.set_terrain(WorldPos(0, 0, 0), "core:grass")
            world.set_terrain(WorldPos(1, 0, 0), "core:grass")
            boar = CreatureState("hunt:boar", "core:boar", 1, 0, 0, self.reg.species["core:boar"].max_hp, stamina=105)
            sim.state.creatures[boar.uid] = boar
            hunting = HuntingSystem(sim.state, self.reg, b"boar-defense", world)
            hunting.notify_attack(boar, WorldPos(0, 0, 0), 4, 500, loudness=50, hit=False)
            attackers = hunting.update_local_ai(WorldPos(0, 0, 0), 5, 505)
            self.assertEqual(boar.behavior, "defend")
            self.assertIn(boar.uid, attackers)
            self.assertEqual((boar.x, boar.y), (1, 0))
        finally:
            db.close()
            td.cleanup()

    def test_ranged_hunting_uses_species_body_and_deep_wound_model(self):
        state = LivingWorldState()
        combat_sim = None
        td, db, world, entities, pid, sim = self.make_sim(b"ranged-body")
        try:
            deer = CreatureState("target:deer", "core:deer", 2, 0, 0, self.reg.species["core:deer"].max_hp)
            inv = Inventory({"core:sling": 1, "core:sling_stone": 20})
            for turn in range(1, 16):
                sim.combat.ranged_attack_creature(deer, inv, turn, 2, perception=12, hunting=12)
                if deer.wounds:
                    break
            self.assertTrue(deer.wounds)
            wound = deer.wounds[-1]
            self.assertIn(wound["part"], self.reg.species["core:deer"].body)
            self.assertIn(wound["tissue"], {"skin", "muscle", "bone", "organ"})
            self.assertEqual(wound["weapon"], "core:sling")
            self.assertGreaterEqual(wound["bleeding"], 1)
        finally:
            db.close()
            td.cleanup()

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
        td, db, world, entities, pid, sim = self.make_sim(b"chase-envelope")
        try:
            sim.state.creatures.clear()
            deer = CreatureState(
                "hunt:far-deer", "core:deer", 600, 0, 0, 30,
                wounds=[{"part": "torso", "severity": 40, "bleeding": 2}],
                behavior="wounded_flee",
            )
            sim.state.creatures[deer.uid] = deer
            sim.ecology.dematerialize_far(WorldPos(0, 0, 0), 420)
            self.assertIn(deer.uid, sim.state.creatures)
            deer.x = 900
            sim.ecology.dematerialize_far(WorldPos(0, 0, 0), 420)
            self.assertNotIn(deer.uid, sim.state.creatures)
        finally:
            db.close()
            td.cleanup()

    def test_simulation_post_action_uses_defensive_animal_ai(self):
        td, db, world, entities, pid, sim = self.make_sim(b"combat-loop")
        try:
            sim.state.creatures.clear()
            p = sim.player_pos
            world.set_terrain(p, "core:grass")
            world.set_terrain(p.moved(1, 0), "core:grass")
            boar = CreatureState(
                "hunt:combat-boar", "core:boar", p.x + 1, p.y, p.z,
                self.reg.species["core:boar"].max_hp,
                behavior="defend", alertness=100, threat_x=p.x, threat_y=p.y, threat_z=p.z,
                last_threat_turn=sim.turn, stamina=105,
            )
            sim.state.creatures[boar.uid] = boar
            vitals = entities.get(pid, Vitals)
            before = vitals.hp
            sim.execute(WaitCommand(pid, 10))
            self.assertLess(vitals.hp, before)
            self.assertTrue(sim.state.player_wounds)
        finally:
            db.close()
            td.cleanup()


if __name__ == "__main__":
    unittest.main()
