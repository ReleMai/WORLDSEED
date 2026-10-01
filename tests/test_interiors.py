from __future__ import annotations

import unittest
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

from worldseed.core.coords import WorldPos
from worldseed.entities.components import Position, Vitals
from worldseed.entities.store import EntityStore
from worldseed.systems.state import LivingWorldState
from worldseed.persistence.validation import validate_sim_state
from worldseed.persistence.database import WorldDatabase

from worldseed.systems.interior_state import (
    InteriorActor, InteriorFurniture, InteriorPile, InteriorPlan, InteriorRect,
)
from worldseed.systems.interiors import (
    InteriorSystem, build_interior, exit_reachable, move_actor, placement_clear,
    position_clear,
)
from worldseed.world.regional_plan import RoomPlanState, StructurePiecePlan, StructurePlanState


def sample_plan(uid="house:1"):
    structure = StructurePlanState(uid, "town:plan", "core:house", "residence",
                                   footprint=[(x, y) for y in range(4) for x in range(4)],
                                   entrance=(1, 3), enclosed=True)
    door = SimpleNamespace(uid=uid + ":door", property_id=uid, x=1, y=3, z=0, owner_uid="player")
    room = RoomPlanState(uid + ":bedroom", uid, "sleeping", fixture_ids=[uid + ":bed"])
    pieces = [StructurePiecePlan(uid + ":bed", uid, "core:single_bed_piece", 1, 1, role="fixture")]
    return build_interior(structure, door, [room], pieces)


class InteriorGeometryTests(unittest.TestCase):
    def test_expanded_rooms_deterministic_and_original_fixtures(self):
        first, second = sample_plan(), sample_plan()
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertGreater(first.width, 4 * 1000)
        self.assertGreaterEqual(len(first.rooms), 3)
        self.assertEqual(first.furniture[0].uid, "house:1:bed")
        self.assertEqual(first.furniture[0].source_uid, "house:1:bed")
        self.assertTrue(position_clear(first, first.entry_x, first.entry_y))
        self.assertNotEqual(first.furniture[0].x % 1000, 0)

    def test_generation_order_does_not_change_layout(self):
        structure = StructurePlanState("house:stable", "town", "core:house", "residence", footprint=[(0, 0), (8, 8)])
        door = SimpleNamespace(uid="door", x=4, y=8, z=0, owner_uid="owner")
        pieces = [StructurePiecePlan("p:2", structure.uid, "core:chair_piece", 1, 1, role="fixture"), StructurePiecePlan("p:1", structure.uid, "core:small_table_piece", 3, 3, role="fixture")]
        self.assertEqual(build_interior(structure, door, [], pieces).to_dict(), build_interior(structure, door, [], list(reversed(pieces))).to_dict())

    def test_round_trip_preserves_fractions_rooms_and_loot(self):
        plan = sample_plan()
        plan.piles.append(InteriorPile("death:1", 1483, 3297, {"core:stone": 3}))
        self.assertEqual(plan.to_dict(), InteriorPlan.from_dict(plan.to_dict()).to_dict())
        actor = InteriorActor(plan.uid, 3179, 2911, waypoints=[[3456, 2345]])
        self.assertEqual(actor.to_dict(), InteriorActor.from_dict(actor.to_dict()).to_dict())

    def test_free_movement_does_not_snap(self):
        plan = sample_plan()
        actor = InteriorActor(plan.uid, plan.entry_x, plan.entry_y)
        self.assertTrue(move_actor(plan, actor, 127, -127))
        self.assertEqual(actor.x, plan.entry_x + 127)
        self.assertEqual(actor.y, plan.entry_y - 127)
        self.assertNotEqual(actor.x % 1000, 0)

    def test_thin_wall_cannot_be_tunnelled_through(self):
        plan = InteriorPlan("interior:test", "test", "door", 0, 0, 0, 9000, 9000,
                            walls=[InteriorRect(3000, 0, 80, 9000)])
        actor = InteriorActor(plan.uid, 1000, 1000)
        move_actor(plan, actor, 4000, 0)
        self.assertLessEqual(actor.x + 180, 3000)

    def test_collision_slides_along_wall(self):
        plan = InteriorPlan("interior:test", "test", "door", 0, 0, 0, 9000, 9000,
                            walls=[InteriorRect(3000, 0, 80, 9000)])
        actor = InteriorActor(plan.uid, 2800, 1000)
        move_actor(plan, actor, 180, 180)
        self.assertEqual(actor.x, 2800)
        self.assertEqual(actor.y, 1180)

    def test_exit_apron_and_overlap_placement_rejected(self):
        plan = sample_plan()
        self.assertFalse(placement_clear(plan, InteriorRect(plan.entry_x, plan.entry_y, 800, 800)))
        self.assertFalse(placement_clear(plan, plan.furniture[0].rect))
        self.assertFalse(placement_clear(plan, InteriorRect(0, 0, 800, 800)))

    def test_every_room_has_continuous_exit_route(self):
        plan = sample_plan()
        for room in plan.rooms:
            self.assertTrue(exit_reachable(plan, room.rect.x + room.rect.w // 2, room.rect.y + room.rect.h - 400))

    def test_identical_local_coordinates_are_isolated(self):
        first, second = sample_plan("house:one"), sample_plan("house:two")
        state = SimpleNamespace(interiors={first.uid: first, second.uid: second}, interior_actors={
            "player": InteriorActor(first.uid, 1000, 1000), "other": InteriorActor(second.uid, 1000, 1000)})
        system = InteriorSystem(SimpleNamespace(state=state))
        self.assertEqual([uid for uid, _ in system.actors_in_space(first.uid)], ["player"])
        self.assertEqual(system.current_plan().uid, first.uid)
        state.interior_actors["player"].x = 1001
        self.assertEqual(state.interior_actors["other"].x, 1000)

    def test_inspection_does_not_prepare_or_mutate(self):
        plan = sample_plan()
        state = SimpleNamespace(interiors={plan.uid: plan}, interior_actors={"player": InteriorActor(plan.uid, 1000, 1000)})
        system = InteriorSystem(SimpleNamespace(state=state))
        before = plan.to_dict()
        system.current_plan()
        system.hit_test(900, 900)
        system.room_at(1000, 1000)
        system.actors_in_space(plan.uid)
        self.assertEqual(plan.to_dict(), before)

    def test_validator_rejects_float_orphan_duplicate_and_negative_goods(self):
        plan = sample_plan()
        plan.piles.append(InteriorPile("pile", 1001, 1002, {"core:stone": 2}))
        raw = {"interiors": {plan.uid: plan.to_dict()}, "interior_actors": {"player": InteriorActor(plan.uid, 3333, 4444).to_dict()}}
        self.assertEqual(validate_sim_state(raw), [])
        raw["interior_actors"]["player"]["x"] = 3333.5
        self.assertTrue(any("position out of bounds" in issue for issue in validate_sim_state(raw)))
        raw["interior_actors"]["player"]["space_id"] = "interior:missing"
        raw["interiors"][plan.uid]["furniture"].append(dict(raw["interiors"][plan.uid]["furniture"][0]))
        raw["interiors"][plan.uid]["piles"][0]["items"]["core:stone"] = -1
        issues = validate_sim_state(raw)
        self.assertTrue(any("orphan interior actor" in issue for issue in issues))
        self.assertTrue(any("duplicate interior furniture" in issue for issue in issues))
        self.assertTrue(any("interior pile goods" in issue for issue in issues))
        self.assertEqual(validate_sim_state({"clock_minute": 0}), [])

    def test_representative_sqlite_save_roundtrip_and_cli_verification(self):
        plan = sample_plan()
        plan.piles.append(InteriorPile("death:real", 1237, 4793, {"core:stone": 2}))
        state = LivingWorldState()
        state.interiors[plan.uid] = plan
        state.interior_actors["player"] = InteriorActor(plan.uid, plan.entry_x + 127, plan.entry_y - 127)
        with tempfile.TemporaryDirectory(prefix="worldseed-interior-save-") as folder:
            path = Path(folder) / "interior.db"
            db = WorldDatabase.create(path, "Interior save proof", "aa" * 32)
            db.save_state(turn=1, tile_deltas={}, player_id=1, position=WorldPos(1, 3, 0), inventory={}, sim_state=state.to_dict())
            self.assertEqual(db.verify(), [])
            db.close()
            loaded = WorldDatabase.open(path)
            rebuilt = LivingWorldState.from_dict(loaded.load_sim_state())
            self.assertEqual(rebuilt.interiors[plan.uid].to_dict(), plan.to_dict())
            self.assertEqual(rebuilt.interior_actors["player"].x, plan.entry_x + 127)
            loaded.close()
            proof = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "tools" / "verify_save.py"), str(path)], capture_output=True, text=True, timeout=30)
            self.assertEqual(proof.returncode, 0, proof.stdout + proof.stderr)
            self.assertIn("Save integrity: OK", proof.stdout)
            print(proof.stdout.strip())


class InteriorPortalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_property_storage_casing import PropertyStorageCasingTests
        PropertyStorageCasingTests.setUpClass()
        cls.source = PropertyStorageCasingTests()
        cls.registry = PropertyStorageCasingTests.registry

    def fixture(self):
        base, security = self.source._security_fixture()
        state, town, physical, _, _, _, _, building, _, _, _ = base
        house = next(s for s in physical.skeleton_for(town.uid).structures if s.function == "residence" and s.enclosed)
        door = next(d for d in security.doors_for_property(house.uid) if d.role == "entrance")
        entities = EntityStore()
        player_id = entities.spawn()
        entities.add(player_id, Position(WorldPos(door.x, door.y, door.z)))
        entities.add(player_id, Vitals(stamina=60, pain=20))
        ground_id = next(t.id for t in self.registry.terrains.values() if t.passable and "water" not in t.tags)
        chunk = SimpleNamespace(get=lambda x, y: self.registry.terrain_index(ground_id))
        class FixtureSim(SimpleNamespace):
            @property
            def player_pos(self):
                return self.entities.get(self.player_id, Position).value
        sim = FixtureSim(state=state, entities=entities, player_id=player_id,
                         registry=self.registry, seed=b"interior-real-fixture",
                         clock=SimpleNamespace(minute=22 * 60),
                         settlement_physicalization=physical, property_security=security,
                         world=SimpleNamespace(cache=SimpleNamespace(peek=lambda key: chunk)),
                         building=building, resources=SimpleNamespace(blocks_movement=lambda p: False),
                         environment=SimpleNamespace(fluid_passable=lambda p: True))
        sim.interiors = InteriorSystem(sim)
        return sim, house, door

    def test_real_stable_door_entry_preserves_stocks_and_containers(self):
        sim, house, door = self.fixture()
        stocks = {uid: dict(t.stocks) for uid, t in sim.state.settlements.items()}
        containers = {uid: dict(c.items) for uid, c in sim.state.containers.items()}
        door.locked = False
        self.assertIn("You enter", sim.interiors.enter(door.uid))
        self.assertEqual(sim.interiors.current_plan().building_id, house.uid)
        self.assertEqual(stocks, {uid: dict(t.stocks) for uid, t in sim.state.settlements.items()})
        self.assertEqual(containers, {uid: dict(c.items) for uid, c in sim.state.containers.items()})
        restored = LivingWorldState.from_dict(sim.state.to_dict())
        self.assertEqual(restored.interiors["interior:" + house.uid].to_dict(), sim.interiors.current_plan().to_dict())
        self.assertEqual(restored.interior_actors["player"].to_dict(), sim.interiors.player_presence().to_dict())

    def test_locked_entry_denied_before_preparing_space(self):
        sim, house, door = self.fixture()
        door.locked = True
        door.owner_uid = "npc:unfriendly"
        door.keyholder_uids = []
        door.guest_access_until = {}
        self.assertIn("locked", sim.interiors.enter(door.uid))
        self.assertEqual(sim.state.interiors, {})
        self.assertEqual(sim.state.interior_actors, {})

    def test_explicit_invitation_allows_same_locked_portal(self):
        sim, house, door = self.fixture()
        door.locked = True
        door.guest_access_until["player"] = 1440
        sim.state.clock_minute = 1320
        self.assertIn("You enter", sim.interiors.enter(door.uid))
        self.assertEqual(sim.interiors.current_plan().building_id, house.uid)

    def test_exit_does_not_generate_missing_landing(self):
        sim, house, door = self.fixture()
        door.locked = False
        sim.interiors.enter(door.uid)
        sim.world.cache.peek = lambda key: None
        self.assertIn("not prepared", sim.interiors.exit())
        self.assertIsNotNone(sim.interiors.player_presence())

    def test_exit_rejects_occupied_or_flooded_landing(self):
        sim, house, door = self.fixture()
        door.locked = False
        sim.interiors.enter(door.uid)
        sim.environment.fluid_passable = lambda p: False
        self.assertIn("blocked", sim.interiors.exit())
        sim.environment.fluid_passable = lambda p: True
        self.assertIn("outside", sim.interiors.exit())
        self.assertIsNone(sim.interiors.player_presence())

    def test_npc_enters_same_room_walks_freely_and_keeps_real_cargo(self):
        sim, house, door = self.fixture()
        npc = next(iter(sim.state.npcs.values()))
        npc.home_id = house.uid
        npc.x, npc.y, npc.z = door.x, door.y, door.z
        npc.rest = 80
        npc.inventory = {"core:wood": 2}
        self.assertTrue(sim.interiors.enter_npc(npc, door.uid))
        actor = sim.state.interior_actors[npc.uid]
        initial = actor.x, actor.y
        sim.interiors.tick_update(1321)
        self.assertNotEqual(initial, (actor.x, actor.y))
        self.assertNotEqual(actor.x % 1000, 0)
        self.assertEqual(npc.inventory, {"core:wood": 2})
        after = actor.to_dict()
        sim.interiors.tick_update(1321)
        self.assertEqual(actor.to_dict(), after)

    def test_rearrange_requires_actual_ownership(self):
        sim, house, door = self.fixture()
        door.locked = False
        sim.interiors.enter(door.uid)
        plan = sim.interiors.current_plan()
        furnishing = plan.furniture[0]
        self.assertIn("owner", sim.interiors.rearrange(furnishing.uid, 4000, 4000))

    def test_npc_rest_and_knock_walks_to_portal_before_exiting(self):
        sim, house, door = self.fixture()
        npc = next(iter(sim.state.npcs.values()))
        npc.home_id = house.uid
        npc.x, npc.y, npc.z = door.x, door.y, door.z
        npc.rest = 95
        sim.interiors.enter_npc(npc, door.uid)
        actor = sim.state.interior_actors[npc.uid]
        for minute in range(1321, 1382):
            sim.interiors.tick_update(minute)
        self.assertLess(npc.rest, 95)
        self.assertNotEqual((actor.x, actor.y), (sim.interiors.state.interiors[actor.space_id].entry_x, sim.interiors.state.interiors[actor.space_id].entry_y))
        npc.tasks = [{"kind": "move", "door_answer_uid": door.uid}, {"kind": "perform", "action": "answer_door", "door_uid": door.uid}]
        sim.interiors.tick_update(1382)
        self.assertIn(npc.uid, sim.state.interior_actors)
        for minute in range(1383, 1460):
            sim.interiors.tick_update(minute)
            if npc.uid not in sim.state.interior_actors:
                break
        self.assertNotIn(npc.uid, sim.state.interior_actors)
        self.assertEqual(npc.tasks[-1]["action"], "answer_door")


if __name__ == "__main__":
    unittest.main()
