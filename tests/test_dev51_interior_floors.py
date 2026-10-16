from __future__ import annotations

import unittest
import subprocess
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from tests import test_interiors as fixtures
from worldseed.core.clock import GameClock
from worldseed.core.coords import WorldPos
from worldseed.persistence.database import WorldDatabase
from worldseed.persistence.validation import validate_sim_state
from worldseed.systems.ai import NPCSystem
from worldseed.systems.interior_floors import prepare_floors, residential_floor_count
from worldseed.systems.interior_state import InteriorActor, InteriorPlan
from worldseed.systems.interior_templates import profile_for
from worldseed.systems.interiors import InteriorSystem, position_clear
from worldseed.systems.npc_schedule import daily_schedule
from worldseed.systems.state import LivingWorldState
from worldseed.world.regional_plan import StructurePlanState


class InteriorFloorTests(unittest.TestCase):
    def fixture(self, size=8):
        structure = StructurePlanState("home:levels", "town", "core:house", "residence",
                                       footprint=[(x, y) for y in range(size) for x in range(size)], enclosed=True)
        ground = fixtures.sample_plan(structure.uid)
        state = LivingWorldState()
        state.interiors[ground.uid] = ground
        # Stair transfers record explored-room memory using the game clock.
        system = InteriorSystem(SimpleNamespace(state=state, clock=GameClock(minute=state.clock_minute)))
        return structure, state, system, prepare_floors(system, ground, structure, profile_for(structure))

    def test_floor_count_is_bounded_and_caused_by_real_building_size(self):
        for size, count in ((4, 1), (5, 2), (8, 3), (20, 3)):
            structure = StructurePlanState("house", "town", "core:house", "residence",
                                           footprint=[(x, y) for y in range(size) for x in range(size)])
            self.assertEqual(residential_floor_count(structure), count)
            structure.function = "market"
            self.assertEqual(residential_floor_count(structure), 1)

    def test_stairs_are_distinct_stable_reciprocal_without_rerolling_ground(self):
        structure, state, system, floors = self.fixture()
        self.assertEqual(len(floors), 3)
        geometry = deepcopy((floors[0].rooms, floors[0].walls, floors[0].furniture))
        before = state.to_dict()
        repeated = prepare_floors(system, floors[0], structure, profile_for(structure))
        self.assertEqual(state.to_dict(), before)
        self.assertEqual((repeated[0].rooms, repeated[0].walls, repeated[0].furniture), geometry)
        self.assertFalse(floors[1].stairs[0].rect.overlaps(floors[1].stairs[1].rect))
        for floor in floors:
            for stair in floor.stairs:
                target = state.interiors[stair.target_space_id]
                self.assertEqual(target.building_id, floor.building_id)
                self.assertEqual(target.door_uid, floor.door_uid)
                self.assertTrue(position_clear(target, stair.target_x, stair.target_y))
                self.assertTrue(any(s.target_space_id == floor.uid for s in target.stairs))

    def test_player_stairs_require_reach_update_space_index_and_cannot_exit_upstairs(self):
        _, _, system, floors = self.fixture(5)
        ground, upper = floors
        actor = InteriorActor(ground.uid, ground.entry_x, ground.entry_y)
        system._put_actor("player", actor)
        stair = ground.stairs[0]
        actor.x, actor.y = ground.width - 1000, ground.height - 1000
        self.assertIn("closer", system.use_stairs(stair.uid))
        actor.x, actor.y = stair.x + stair.w // 2, stair.y + stair.h - 300
        self.assertIn("floor 2", system.use_stairs(stair.uid))
        self.assertEqual(system.current_plan().uid, upper.uid)
        self.assertFalse(system.actors_in_space(ground.uid))
        self.assertEqual([uid for uid, _ in system.actors_in_space(upper.uid)], ["player"])
        self.assertIn("stairs down", system.exit())
        self.assertIn("floor 1", system.use_stairs(upper.stairs[0].uid))
        self.assertEqual(system.current_plan().uid, ground.uid)

    def test_floor_queries_are_observational_and_missing_targets_are_denied(self):
        _, state, system, floors = self.fixture(5)
        system._put_actor("player", InteriorActor(floors[0].uid, floors[0].entry_x, floors[0].entry_y))
        before = state.to_dict()
        self.assertIsNotNone(system.stairs_target(floors[0].stairs[0].uid))
        self.assertIsNone(system.stairs_target("unknown"))
        self.assertEqual(state.to_dict(), before)
        del state.interiors[floors[1].uid]
        self.assertIn("not in this interior", system.use_stairs(floors[0].stairs[0].uid))

    def test_one_way_persisted_stairs_are_rejected_and_cannot_strand_an_actor(self):
        _, state, system, floors = self.fixture(5)
        ground, upper = floors
        stair = ground.stairs[0]
        system._put_actor("player", InteriorActor(ground.uid, stair.x + stair.w // 2,
                                                  stair.y + stair.h - 300))
        raw = state.to_dict()
        raw["interiors"][upper.uid]["stairs"] = []
        self.assertTrue(any("missing reciprocal interior stair binding" in issue
                            for issue in validate_sim_state(raw)))
        # The runtime guard protects even a partially loaded/malformed state,
        # without changing the actor index or crossing to a one-way upper room.
        upper.stairs.clear()
        actor_before = system.player_presence().to_dict()
        self.assertIn("obstructed", system.use_stairs(stair.uid))
        self.assertEqual(system.player_presence().to_dict(), actor_before)
        self.assertEqual(system.current_plan().uid, ground.uid)
        self.assertEqual([uid for uid, _ in system.actors_in_space(ground.uid)], ["player"])

    def test_legacy_defaults_and_multi_floor_roundtrip_validate(self):
        legacy = fixtures.sample_plan().to_dict()
        for key in ("floor_index", "floor_count", "stairs"):
            legacy.pop(key)
        restored = InteriorPlan.from_dict(legacy)
        self.assertEqual((restored.floor_index, restored.floor_count, restored.stairs), (0, 1, []))
        _, state, _, floors = self.fixture()
        self.assertEqual(validate_sim_state(state.to_dict()), [])
        raw = state.to_dict()
        self.assertEqual(raw, LivingWorldState.from_dict(raw).to_dict())
        raw["interiors"][floors[0].uid]["stairs"][0]["target_space_id"] = "interior:other"
        self.assertTrue(any("stair binding" in issue for issue in validate_sim_state(raw)))

    def test_three_floor_sqlite_roundtrip_and_cli_verifier(self):
        _, state, system, floors = self.fixture()
        stair = floors[1].stairs[0]
        system._put_actor("player", InteriorActor(floors[1].uid, stair.x + 700, stair.y + 1600))
        with tempfile.TemporaryDirectory(prefix="worldseed-dev51-floors-") as folder:
            path = Path(folder) / "three-floors.db"
            database = WorldDatabase.create(path, "Three floor proof", "aa" * 32)
            try:
                database.save_state(turn=1, tile_deltas={}, player_id=1,
                                    position=WorldPos(1, 3), inventory={}, sim_state=state.to_dict())
                self.assertEqual(database.verify(), [])
            finally:
                database.close()
            loaded = WorldDatabase.open(path)
            try:
                self.assertEqual(loaded.load_sim_state(), state.to_dict())
            finally:
                loaded.close()
            proof = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "tools" / "verify_save.py"), str(path)],
                                   capture_output=True, text=True, timeout=30)
            self.assertEqual(proof.returncode, 0, proof.stdout + proof.stderr)
            self.assertIn("Save integrity: OK", proof.stdout)


class ScheduledHouseholdFloorsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.InteriorPortalTests.setUpClass()

    def test_fixed_tick_walk_home_portal_stairs_rest_and_morning_egress(self):
        sim, house, door = fixtures.InteriorPortalTests().fixture()
        npc = next(iter(sim.state.npcs.values()))
        town = sim.state.settlements[npc.settlement_id]
        npc.home_id, npc.rest, npc.hunger, npc.thirst = house.uid, 95, 0, 0
        npc.inventory = {"core:wood": 2}
        frontage = sim.settlement_physicalization.frontage_for(house.uid)
        npc.x, npc.y, npc.z = frontage.x, frontage.y + 4, frontage.z
        sim.world.is_passable = lambda p: True
        system = NPCSystem(sim.state, sim.seed, None, sim.world, sim.building)
        system.settlement_physicalization = sim.settlement_physicalization
        system.attach_property_security(sim.property_security)
        system.attach_interior_system(sim.interiors)
        system.generate_plan(npc, town, 1320, "rest")
        initial = npc.x, npc.y
        entered, upstairs = False, False
        for minute in range(1321, 1420):
            sim.clock.minute = minute
            system.tick_update(minute, sim.player_pos)
            actor = sim.state.interior_actors.get(npc.uid)
            entered |= actor is not None
            upstairs |= bool(actor and sim.state.interiors[actor.space_id].floor_index)
        self.assertNotEqual((npc.x, npc.y), initial)
        self.assertTrue(entered)
        self.assertTrue(upstairs)
        self.assertLess(npc.rest, 95)
        self.assertEqual(npc.inventory, {"core:wood": 2})
        npc.rest, npc.hunger, npc.thirst = 0, 0, 0
        # This merchant's own morning can begin later than the old universal
        # 07:00 wake time. Keep the same bounded stair/portal egress window,
        # anchored to the end of their actual overnight sleep block.
        morning_sleep = next(block for block in daily_schedule(npc, sim.seed)
                             if block.activity == "sleep" and block.start_minute == 0)
        wake_minute = 1440 + morning_sleep.end_minute
        for minute in range(wake_minute, wake_minute + 100):
            sim.clock.minute = minute
            sim.interiors.tick_update(minute)
            if npc.uid not in sim.state.interior_actors:
                break
        self.assertNotIn(npc.uid, sim.state.interior_actors)
        self.assertLessEqual(abs(npc.x - door.x) + abs(npc.y - door.y), 1)
        self.assertEqual(npc.inventory, {"core:wood": 2})

    def test_legacy_bedroom_walk_rebinds_home_approach_without_teleporting(self):
        sim, house, door = fixtures.InteriorPortalTests().fixture()
        npc = next(iter(sim.state.npcs.values()))
        town = sim.state.settlements[npc.settlement_id]
        npc.home_id = house.uid
        frontage = sim.settlement_physicalization.frontage_for(house.uid)
        npc.x, npc.y, npc.z = frontage.x, frontage.y + 8, frontage.z
        sim.world.is_passable = lambda p: True
        system = NPCSystem(sim.state, sim.seed, None, sim.world, sim.building)
        system.settlement_physicalization = sim.settlement_physicalization
        system.attach_property_security(sim.property_security)
        system.attach_interior_system(sim.interiors)
        npc.tasks = [{"kind": "move", "x": door.x - 20, "y": door.y - 20,
                      "_local_path": [[door.x - 21, door.y - 20]], "_local_path_goal": [door.x - 20, door.y - 20, 0]},
                     {"kind": "perform", "action": "rest"}]
        initial = npc.x, npc.y
        system.execute_tick(npc, town, 1320, sim.player_pos)
        self.assertEqual((npc.tasks[0]["x"], npc.tasks[0]["y"]), (frontage.x, frontage.y))
        self.assertEqual(npc.tasks[0]["interior_home_door_uid"], door.uid)
        self.assertLessEqual(abs(npc.x - initial[0]) + abs(npc.y - initial[1]), 3)
        self.assertNotIn(npc.uid, sim.state.interior_actors)


if __name__ == "__main__":
    unittest.main()
