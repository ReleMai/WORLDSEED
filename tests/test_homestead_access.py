"""Completed cabins share persistent doors and existing isolated interiors."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from tests.test_homestead_safety import npc_at, prepared_engine
from worldseed.core.coords import ChunkKey, WorldPos
from worldseed.entities.components import Inventory, Position, Vitals
from worldseed.entities.store import EntityStore
from worldseed.persistence.database import WorldDatabase
from worldseed.sim.engine import Simulation
from worldseed.systems.homestead_access import ensure_access
from worldseed.systems.homestead_blueprints import catalog, doorway, door_uid, footprint
from worldseed.systems.interiors import exit_reachable, position_clear
from worldseed.systems.state import LivingWorldState
from worldseed.world.chunk import Chunk
from worldseed.world.cache import ChunkCache
from worldseed.world.generator import WorldGenerator
from worldseed.world.world import World


def finish_cabin(test_case, sim, style_id="log_cabin_01", orientation=0):
    sim.entities.get(sim.player_id, Position).value = WorldPos(9, 9, 0)
    ok, message = sim.homestead.place(style_id, 10, 10, orientation)
    test_case.assertTrue(ok, message)
    site = next(iter(sim.state.homesteads.values()))
    site["stored"] = dict(catalog()[0]["log_cabin"]["materials"])
    sim.entities.get(sim.player_id, Position).value = WorldPos(*doorway(site)[1])
    for _ in range(4):
        ok, message = sim.homestead.advance(site["uid"])
        test_case.assertTrue(ok, message)
    return site


def reload_engine(test_case, original, database):
    """Save to SQLite, reopen it, then attach saved state to the real engine."""
    path = Path(database.path)
    database.save_state(turn=original.turn, tile_deltas={}, player_id=original.player_id,
                        position=original.player_pos,
                        inventory=dict(original.entities.get(original.player_id, Inventory).items),
                        sim_state=original.state.to_dict())
    test_case.assertEqual(database.verify(), [])
    database.close()
    loaded = WorldDatabase.open(path)
    test_case.addCleanup(loaded.close)
    state = LivingWorldState.from_dict(loaded.load_sim_state())
    world = World(WorldGenerator(b"cabin-safety", original.registry), original.registry, loaded)
    chunk = Chunk.empty(ChunkKey(0, 0, 0))
    grass = original.registry.terrain_index("core:grass")
    for index in range(len(chunk.terrain)):
        chunk.terrain[index] = grass
    world.cache.put(chunk.key, chunk)
    entities = EntityStore()
    player_id = entities.spawn(preferred_id=1)
    p = loaded.load_component(player_id, "Position")
    entities.add(player_id, Position(WorldPos(p["x"], p["y"], p["z"])))
    entities.add(player_id, Inventory(loaded.load_component(player_id, "Inventory")["items"]))
    entities.add(player_id, Vitals())
    with patch.object(Simulation, "_ensure_nearby_world") as prepare:
        sim = Simulation(world, entities, original.registry, original.turn, state, b"cabin-safety")
    prepare.assert_called_once_with(WorldPos(p["x"], p["y"], p["z"]), force=True)
    return sim, loaded


class HomesteadAccessTests(unittest.TestCase):
    def test_every_rotation_and_offset_door_enters_and_exits_exact_same_landing(self):
        for style_id in ("log_cabin_01", "log_cabin_02"):
            for rotation in range(4):
                with self.subTest(style=style_id, rotation=rotation):
                    sim, _ = prepared_engine(self)
                    site = finish_cabin(self, sim, style_id, rotation)
                    inside, outside = doorway(site)
                    door = sim.property_security.door_by_id(door_uid(site))
                    self.assertIsNotNone(door)
                    self.assertEqual((door.x, door.y, door.z), inside)
                    self.assertEqual(door.property_id, site["uid"])
                    self.assertEqual(door.owner_uid, "player")
                    self.assertIs(sim.property_security.door_at(WorldPos(*inside)), door)
                    self.assertEqual(sim.property_security.doors_for_property(site["uid"]), (door,))
                    self.assertFalse(sim.building.passable(WorldPos(*inside), True))
                    self.assertTrue(sim.building.passable(WorldPos(*outside), True))
                    inventory = dict(sim.entities.get(sim.player_id, Inventory).items)
                    self.assertIn("You enter", sim.interiors.enter(door.uid))
                    plan = sim.interiors.current_plan()
                    self.assertEqual(plan.building_id, site["uid"])
                    self.assertEqual(plan.door_uid, door.uid)
                    self.assertEqual((plan.exterior_x, plan.exterior_y, plan.exterior_z), inside)
                    self.assertTrue(position_clear(plan, plan.entry_x, plan.entry_y))
                    self.assertTrue(exit_reachable(plan, plan.entry_x, plan.entry_y))
                    self.assertEqual(plan.furniture, [])
                    self.assertEqual(sim.state.containers, {})
                    self.assertEqual(sim.entities.get(sim.player_id, Inventory).items, inventory)
                    self.assertIn("outside", sim.interiors.exit())
                    self.assertEqual(sim.player_pos, WorldPos(*outside))
                    self.assertIsNone(sim.interiors.player_presence())

    def test_side_and_rear_adjacency_cannot_enter_through_wall(self):
        for rotation in range(4):
            with self.subTest(rotation=rotation):
                sim, _ = prepared_engine(self)
                site = finish_cabin(self, sim, orientation=rotation)
                inside, outside = doorway(site)
                door = sim.property_security.door_by_id(door_uid(site))
                alternatives = [WorldPos(inside[0] + dx, inside[1] + dy, inside[2])
                                for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1))
                                if (inside[0] + dx, inside[1] + dy, inside[2]) != outside]
                for wrong_side in alternatives:
                    sim.entities.get(sim.player_id, Position).value = wrong_side
                    self.assertNotIn("You enter", sim.interiors.enter(door.uid))
                    self.assertFalse(sim.state.interior_actors)
                    self.assertFalse(sim.state.interiors)
                sim.entities.get(sim.player_id, Position).value = WorldPos(*outside)
                self.assertIn("You enter", sim.interiors.enter(door.uid))

    def test_unfinished_marker_has_no_door_or_interior(self):
        sim, _ = prepared_engine(self)
        ok, message = sim.homestead.place("log_cabin_01", 10, 10, 0)
        self.assertTrue(ok, message)
        site = next(iter(sim.state.homesteads.values()))
        for stage in range(4):
            site["stage"] = stage
            self.assertIsNone(ensure_access(sim, site))
            self.assertIsNone(sim.homestead.completed(site["uid"]))
            self.assertNotIn("You enter", sim.interiors.enter(door_uid(site)))
            self.assertEqual(sim.state.door_security, {})
            self.assertEqual(sim.state.interiors, {})

    def test_cabin_access_queries_are_observational_and_never_prepare_regions(self):
        sim, _ = prepared_engine(self)
        site = finish_cabin(self, sim)
        before = sim.state.to_dict()
        with patch.object(sim.region_planner, "plan", side_effect=AssertionError("Read prepared a region")), \
             patch.object(sim.world.generator, "generate_chunk", side_effect=AssertionError("Read generated terrain")):
            door = sim.property_security.door_by_id(door_uid(site))
            self.assertIs(sim.property_security.door_at(WorldPos(*doorway(site)[0])), door)
            self.assertEqual(sim.property_security.doors_for_property(site["uid"]), (door,))
            self.assertIs(sim.homestead.completed(site["uid"]), site)
            self.assertIsNone(sim.interiors.current_plan())
        self.assertEqual(sim.state.to_dict(), before)

    def test_locked_door_access_query_does_not_create_a_missing_lock_identity(self):
        sim, _ = prepared_engine(self)
        site = finish_cabin(self, sim)
        door = sim.property_security.door_by_id(door_uid(site))
        door.locked = True
        door.lock_uid = ""
        before = sim.state.to_dict()
        self.assertTrue(sim.property_security.blocks_actor(WorldPos(*doorway(site)[0]), "npc:visitor"))
        self.assertEqual(sim.state.to_dict(), before)
        self.assertEqual(door.lock_uid, "")

    def test_blocked_or_unprepared_exact_landing_cannot_exit_elsewhere(self):
        for blocker in ("flood", "npc", "creature", "unprepared"):
            with self.subTest(blocker=blocker):
                sim, _ = prepared_engine(self)
                site = finish_cabin(self, sim)
                self.assertIn("You enter", sim.interiors.enter(door_uid(site)))
                outside = doorway(site)[1]
                actor = sim.interiors.player_presence()
                if blocker == "flood":
                    from worldseed.systems.state import FluidCell
                    sim.state.fluids[",".join(map(str, outside))] = FluidCell(*outside, "water", 255)
                elif blocker == "npc":
                    sim.state.npcs["npc:visitor"] = npc_at("npc:visitor", outside)
                elif blocker == "creature":
                    from worldseed.systems.state import CreatureState
                    sim.state.creatures["animal:visitor"] = CreatureState("animal:visitor", "core:deer", *outside, 100)
                else:
                    sim.world.cache = ChunkCache(1, lambda key: self.fail("Exit generated an unprepared chunk"))
                before = actor.to_dict()
                self.assertIn("blocked", sim.interiors.exit())
                self.assertEqual(sim.interiors.player_presence().to_dict(), before)

    def test_exit_at_chunk_edge_requires_prepared_cardinal_resource_neighbors(self):
        sim, _ = prepared_engine(self)
        site = finish_cabin(self, sim)
        # Relocate this legacy site to the prepared chunk's western edge. Its
        # exact landing is loaded, while resource lookup's x=-1 halo is absent.
        site["x"] = 0
        door = ensure_access(sim, site)
        outside = WorldPos(*doorway(site)[1])
        self.assertEqual(outside, WorldPos(0, 13, 0))
        self.assertIsNotNone(sim.world.cache.peek(ChunkKey(0, 0, 0)))
        self.assertIsNone(sim.world.cache.peek(ChunkKey(-1, 0, 0)))
        sim.entities.get(sim.player_id, Position).value = outside
        self.assertIn("You enter", sim.interiors.enter(door.uid))
        before = sim.interiors.player_presence().to_dict()
        with patch.object(sim.resources, "blocks_movement", side_effect=AssertionError("Exit queried an unprepared resource halo")), \
             patch.object(sim.world.generator, "generate_chunk", side_effect=AssertionError("Exit generated neighboring terrain")):
            self.assertIsNone(sim.interiors._exterior_landing(sim.interiors.current_plan()))
            self.assertIn("blocked", sim.interiors.exit())
        self.assertEqual(sim.interiors.player_presence().to_dict(), before)

    def test_npc_uses_same_portal_and_keeps_authoritative_cargo(self):
        sim, _ = prepared_engine(self)
        site = finish_cabin(self, sim, "log_cabin_02", 3)
        door = sim.property_security.door_by_id(door_uid(site))
        outside = doorway(site)[1]
        sim.entities.get(sim.player_id, Position).value = WorldPos(9, 9, 0)
        npc = npc_at("npc:resident", outside, home_id=site["uid"], inventory={"core:wood": 4})
        sim.state.npcs[npc.uid] = npc
        self.assertTrue(sim.interiors.enter_npc(npc, door.uid))
        actor = sim.state.interior_actors[npc.uid]
        self.assertEqual(actor.space_id, "interior:" + site["uid"])
        self.assertEqual(npc.inventory, {"core:wood": 4})
        plan = sim.state.interiors[actor.space_id]
        self.assertEqual(sim.interiors._exterior_landing(plan, npc.uid), WorldPos(*outside))
        self.assertEqual((npc.x, npc.y, npc.z), doorway(site)[0])

    def test_saved_cabin_door_interior_and_fractional_presence_survive_sqlite_reload(self):
        sim, database = prepared_engine(self)
        site = finish_cabin(self, sim, "log_cabin_02", 2)
        uid = door_uid(site)
        self.assertIn("You enter", sim.interiors.enter(uid))
        plan = sim.interiors.current_plan()
        actor = sim.interiors.player_presence()
        actor.x += 127
        actor.y -= 127
        door = sim.property_security.door_by_id(uid)
        door.locked = True
        door.picked = True
        door.last_tampered_minute = 42
        before = (deepcopy(site), plan.to_dict(), actor.to_dict())
        restored, loaded = reload_engine(self, sim, database)
        self.assertEqual(restored.state.homesteads[site["uid"]], before[0])
        self.assertEqual(restored.interiors.current_plan().to_dict(), before[1])
        self.assertEqual(restored.interiors.player_presence().to_dict(), before[2])
        reloaded_door = restored.property_security.door_by_id(uid)
        self.assertTrue(reloaded_door.locked)
        self.assertTrue(reloaded_door.picked)
        self.assertEqual(reloaded_door.last_tampered_minute, 42)
        self.assertEqual(restored.entities.get(restored.player_id, Inventory).items,
                         sim.entities.get(sim.player_id, Inventory).items)
        self.assertEqual(loaded.verify(), [])
        # Owning the cabin allows exit through its unchanged locked threshold.
        actor = restored.interiors.player_presence()
        actor.x, actor.y = plan.entry_x, plan.entry_y
        self.assertIn("outside", restored.interiors.exit())
        self.assertEqual(restored.player_pos, WorldPos(*doorway(site)[1]))
        loaded.save_state(turn=restored.turn, tile_deltas={}, player_id=restored.player_id,
                          position=restored.player_pos,
                          inventory=dict(restored.entities.get(restored.player_id, Inventory).items),
                          sim_state=restored.state.to_dict())
        proof = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "tools" / "verify_save.py"), str(loaded.path)],
                               capture_output=True, text=True, timeout=30)
        self.assertEqual(proof.returncode, 0, proof.stdout + proof.stderr)
        self.assertIn("Save integrity: OK", proof.stdout)

    def test_legacy_completed_site_gets_stable_door_without_free_furniture_on_load(self):
        sim, database = prepared_engine(self)
        site = finish_cabin(self, sim)
        uid = door_uid(site)
        sim.state.door_security.clear()
        self.assertEqual(sim.state.interiors, {})
        restored, _ = reload_engine(self, sim, database)
        door = restored.property_security.door_by_id(uid)
        self.assertIsNotNone(door)
        self.assertEqual(door.property_id, site["uid"])
        self.assertEqual(restored.state.interiors, {})
        self.assertEqual(restored.state.containers, {})
        self.assertIn("You enter", restored.interiors.enter(uid))
        self.assertEqual(restored.interiors.current_plan().furniture, [])

    def test_legacy_player_inside_solid_shell_recovers_to_rotated_door_on_reload(self):
        for stage in (2, 4):
            for rotation in range(4):
                with self.subTest(stage=stage, rotation=rotation):
                    sim, database = prepared_engine(self)
                    site = finish_cabin(self, sim, "log_cabin_02", rotation)
                    site["stage"] = stage
                    if stage == 2:
                        sim.state.door_security.clear()
                    sim.entities.get(sim.player_id, Position).value = WorldPos(*footprint(site)[4])
                    sim.state.player_fx, sim.state.player_fy = 0.37, 0.61
                    goods = dict(sim.entities.get(sim.player_id, Inventory).items)
                    saved_site = deepcopy(site)
                    restored, _ = reload_engine(self, sim, database)
                    self.assertEqual(restored.player_pos, WorldPos(*doorway(site)[1]))
                    self.assertEqual((restored.state.player_fx, restored.state.player_fy), (0.5, 0.5))
                    self.assertEqual(restored.state.homesteads[site["uid"]], saved_site)
                    self.assertEqual(restored.entities.get(restored.player_id, Inventory).items, goods)
                    self.assertFalse(restored.state.interior_actors)

    def test_legacy_recovery_uses_safe_apron_when_exact_door_is_occupied_or_has_tree(self):
        for blocker in ("npc", "tree"):
            with self.subTest(blocker=blocker):
                sim, database = prepared_engine(self)
                site = finish_cabin(self, sim)
                outside = doorway(site)[1]
                sim.entities.get(sim.player_id, Position).value = WorldPos(*footprint(site)[4])
                if blocker == "npc":
                    sim.state.npcs["npc:visitor"] = npc_at("npc:visitor", outside, inventory={"core:stone": 3})
                else:
                    # A prepared mature tree is physical cache authority. Drop
                    # its depletion delta so reload sees the real obstruction.
                    sim.state.resource_depletion.pop(",".join(map(str, outside)), None)
                    features = [None] * (32 * 32)
                    features[outside[1] * 32 + outside[0]] = "core:oak_tree"
                    database.store_generated_resource_chunk(ChunkKey(0, 0, 0), sim.resources.version,
                                                            sim.resources._season(), features)
                    database.commit_generated()
                goods = dict(sim.entities.get(sim.player_id, Inventory).items)
                saved_site = deepcopy(site)
                restored, _ = reload_engine(self, sim, database)
                pos = restored.player_pos
                self.assertNotIn((pos.x, pos.y, pos.z), footprint(site))
                self.assertNotEqual(pos, WorldPos(*outside))
                self.assertLessEqual(abs(pos.x - 11) + abs(pos.y - 11), 6)
                self.assertTrue(restored.building.passable(pos, True))
                self.assertFalse(restored.resources.blocks_movement(pos))
                self.assertTrue(restored.environment.fluid_passable(pos))
                self.assertEqual(restored.state.homesteads[site["uid"]], saved_site)
                self.assertEqual(restored.entities.get(restored.player_id, Inventory).items, goods)
                if blocker == "npc":
                    self.assertEqual(restored.state.npcs["npc:visitor"].inventory, {"core:stone": 3})


if __name__ == "__main__":
    unittest.main()
