from __future__ import annotations

import unittest
from types import SimpleNamespace

from tests import test_interiors as interior_fixtures
from worldseed.core.coords import WorldPos
from worldseed.systems.activities import ActivitySystem
from worldseed.systems.ai import NPCSystem
from worldseed.systems.interior_state import InteriorRect
from worldseed.systems.physical_goods import SettlementPhysicalGoodsSystem
from worldseed.systems.professions import SettlementProfessionSystem
from worldseed.systems.state import LivingWorldState


class NullHistory:
    def record(self, *args, **kwargs):
        pass


class InteriorWorkshopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        interior_fixtures.InteriorPortalTests.setUpClass()

    def fixture(self):
        sim, _, _ = interior_fixtures.InteriorPortalTests().fixture()
        physical = sim.settlement_physicalization
        town = next(iter(sim.state.settlements.values()))
        workshop = next(s for s in physical.skeleton_for(town.uid).structures if s.function == "smithy")
        npc = sim.state.npcs["npc:owner"]
        npc.occupation = "smith"
        npc.workplace_id = workshop.uid
        npc.inventory = {}
        npc.tasks = []
        npc.assigned_process_id = "core:iron_smelt"
        npc.work_assignment_day = 0
        npc.hunger = npc.thirst = npc.rest = 0
        frontage = physical.frontage_for(workshop.uid)
        npc.x, npc.y, npc.z = frontage.x, frontage.y, frontage.z
        sim.world.is_passable = lambda pos: True
        sim.clock.minute = 600
        activities = ActivitySystem(sim.state, sim.registry, physical, sim.world)
        activities.attach_interior_system(sim.interiors)
        goods = SettlementPhysicalGoodsSystem(sim.state, sim.registry)
        professions = SettlementProfessionSystem(sim.state, sim.registry, sim.seed, sim.world, physical, activities, goods, sim.resources)
        ai = NPCSystem(sim.state, sim.seed, NullHistory(), sim.world, sim.building)
        ai.attach_settlement_population(physical, SimpleNamespace(bind_settlement=lambda town: None))
        ai.attach_property_security(sim.property_security)
        ai.attach_activity_system(activities)
        ai.attach_profession_system(professions)
        ai.attach_interior_system(sim.interiors)
        sim.npcs = ai
        storage = professions._work_storage(npc, town)
        storage.items["core:iron_ore"] = 2
        storage.items["core:coal"] = 1
        return sim, town, npc, workshop, activities, professions, storage

    @staticmethod
    def total(sim, item_id):
        return (sum(t.stocks.get(item_id, 0) for t in sim.state.settlements.values())
                + sum(c.items.get(item_id, 0) for c in sim.state.containers.values())
                + sum(n.inventory.get(item_id, 0) for n in sim.state.npcs.values())
                + sum(p.items.get(item_id, 0) for plan in sim.state.interiors.values() for p in plan.piles))

    def test_real_worker_enters_walks_works_and_hauls_same_batch_out(self):
        sim, town, npc, workshop, activities, professions, storage = self.fixture()
        before = {iid: self.total(sim, iid) for iid in ("core:iron_ore", "core:coal", "core:iron_bloom")}
        tasks = professions.plan_work(npc, town, 600)
        self.assertTrue(tasks)
        npc.tasks = tasks
        rows = [sim.state.activity_reservations[t["reservation_uid"]] for t in tasks if t["kind"] == "activity"]
        self.assertTrue(all(row.metadata["space_id"] == "interior:" + workshop.uid for row in rows))
        self.assertTrue(all(row.target_uid in {f.uid for f in sim.state.interiors[row.metadata["space_id"]].furniture} for row in rows))
        # A frontage coordinate alone may never start an indoor station.
        self.assertEqual(activities.progress(rows[0].uid, npc.uid, 601), "not_at_target")
        self.assertEqual(rows[0].started_minute, -1)
        seen_inside = seen_active_inside = seen_completed_inside = False
        positions = set()
        for minute in range(605, 2001, 5):
            sim.clock.minute = minute
            sim.interiors.tick_update(minute)
            actor = sim.state.interior_actors.get(npc.uid)
            if actor:
                seen_inside = True
                positions.add((actor.x, actor.y))
                seen_active_inside |= any(row.status == "active" for row in rows)
                seen_completed_inside |= any(row.status == "completed" for row in rows)
            else:
                sim.npcs.execute_tick(npc, town, minute, WorldPos(workshop.entrance[0], workshop.entrance[1], 0))
            if not npc.tasks and npc.uid not in sim.state.interior_actors:
                break
        self.assertTrue(seen_inside)
        self.assertTrue(seen_active_inside)
        self.assertTrue(seen_completed_inside)
        self.assertGreater(len(positions), 5)
        self.assertTrue(any(x % 1000 or y % 1000 for x, y in positions))
        self.assertIn(npc.facing_dx, (-1, 0, 1))
        self.assertIn(npc.facing_dy, (-1, 0, 1))
        self.assertFalse(npc.tasks, npc.tasks)
        self.assertNotIn(npc.uid, sim.state.interior_actors)
        self.assertEqual(self.total(sim, "core:iron_ore"), before["core:iron_ore"] - 2)
        self.assertEqual(self.total(sim, "core:coal"), before["core:coal"] - 1)
        self.assertEqual(self.total(sim, "core:iron_bloom"), before["core:iron_bloom"] + 1)
        self.assertGreater(storage.items["core:iron_bloom"], 0)
        restored = LivingWorldState.from_dict(sim.state.to_dict())
        self.assertEqual(restored.activity_reservations[rows[0].uid].metadata, rows[0].metadata)

    def test_same_space_and_continuous_station_proximity_are_required(self):
        sim, town, npc, workshop, activities, professions, _ = self.fixture()
        tasks = professions.plan_work(npc, town, 600)
        row = sim.state.activity_reservations[next(t["reservation_uid"] for t in tasks if t["kind"] == "activity")]
        door_uid = row.metadata["door_uid"]
        self.assertTrue(sim.interiors.enter_work_npc(npc, door_uid))
        actor = sim.state.interior_actors[npc.uid]
        actor.x, actor.y = 500, 500
        self.assertEqual(activities.progress(row.uid, npc.uid, 610), "not_at_target")
        actor.x, actor.y = row.metadata["interior_use_x"], row.metadata["interior_use_y"]
        self.assertEqual(activities.progress(row.uid, npc.uid, 610), "active")
        actor.space_id = "interior:another-building"
        self.assertEqual(activities.progress(row.uid, npc.uid, 999), "not_at_target")
        self.assertEqual(row.status, "active")

    def test_overflow_stays_at_continuous_station_and_cannot_repeat(self):
        sim, town, npc, workshop, activities, professions, storage = self.fixture()
        plan = sim.interiors.prepare_workplace(workshop.uid)
        self.assertTrue(sim.interiors.enter_work_npc(npc, plan.door_uid))
        actor = sim.state.interior_actors[npc.uid]
        actor.x, actor.y = 2345, 6789
        npc.inventory = {"core:iron_ore": 2, "core:coal": 1}
        before = dict(storage.items)
        professions.goods.add_to_actor = lambda worker, iid, qty: 0
        task = {"inputs": {"core:iron_ore": 2, "core:coal": 1}, "outputs": {"core:iron_bloom": 1}}
        self.assertTrue(professions.complete_process(npc, town, task, 650))
        self.assertEqual(storage.items, before)
        self.assertEqual([(p.x, p.y, p.items) for p in plan.piles], [(2345, 6789, {"core:iron_bloom": 1})])
        self.assertFalse(professions.complete_process(npc, town, task, 655))
        self.assertEqual(plan.piles[0].items["core:iron_bloom"], 1)

    def test_reserved_fixture_cannot_move_out_from_under_worker(self):
        sim, town, npc, workshop, activities, professions, _ = self.fixture()
        tasks = professions.plan_work(npc, town, 600)
        row = sim.state.activity_reservations[next(t["reservation_uid"] for t in tasks if t["kind"] == "activity")]
        sim.state.properties[workshop.uid].owner_uid = "player"
        door = sim.property_security.door_by_id(row.metadata["door_uid"])
        door.locked = False
        sim.entities.get(sim.player_id, interior_fixtures.Position).value = WorldPos(door.x, door.y, door.z)
        self.assertIn("You enter", sim.interiors.enter(door.uid))
        furnishing = next(f for f in sim.interiors.current_plan().furniture if f.uid == row.target_uid)
        self.assertIn("reserved", sim.interiors.rearrange(furnishing.uid, furnishing.x + 13, furnishing.y))

    def test_saved_station_walk_rebinds_same_reservation_to_portal(self):
        sim, town, npc, workshop, activities, professions, _ = self.fixture()
        tasks = professions.plan_work(npc, town, 600)
        task = next(t for t in tasks if t["kind"] == "move" and t.get("reservation_uid"))
        row = sim.state.activity_reservations[task["reservation_uid"]]
        original_uid, original_target = row.uid, row.target_uid
        row.metadata = {"work_bonus": row.metadata["work_bonus"]}
        row.use_x, row.use_y = row.x, row.y
        for key in ("interior_work_door_uid", "space_id"):
            task.pop(key, None)
        task["x"], task["y"] = row.x, row.y
        npc.tasks = [task]
        sim.npcs.execute_tick(npc, town, 610, WorldPos(npc.x, npc.y, npc.z))
        self.assertEqual(row.uid, original_uid)
        self.assertEqual(row.target_uid, original_target)
        self.assertEqual(row.metadata["space_id"], "interior:" + workshop.uid)
        self.assertIn(npc.uid, sim.state.interior_actors)
        self.assertFalse(npc.tasks)

    def test_player_station_query_uses_current_space_reach_and_partitions(self):
        sim, town, npc, workshop, activities, professions, _ = self.fixture()
        plan = sim.interiors.prepare_workplace(workshop.uid)
        self.assertEqual(sim.interiors.station_ids_near_player(), set())
        door = sim.property_security.door_by_id(plan.door_uid)
        door.locked = False
        sim.entities.get(sim.player_id, interior_fixtures.Position).value = WorldPos(door.x, door.y, door.z)
        self.assertIn("You enter", sim.interiors.enter(door.uid))
        fixture = next(f for f in plan.furniture if f.piece_id == "core:forge_piece")
        actor = sim.interiors.player_presence()
        actor.x, actor.y = sim.interiors.fixture_use_position(plan, fixture)
        before = sim.state.to_dict()
        self.assertIn("core:forge", sim.interiors.station_ids_near_player())
        self.assertEqual(sim.state.to_dict(), before)
        closest_x = max(fixture.x, min(actor.x, fixture.x + fixture.w))
        closest_y = max(fixture.y, min(actor.y, fixture.y + fixture.h))
        if abs(actor.x - closest_x) >= abs(actor.y - closest_y):
            plan.walls.append(InteriorRect((actor.x + closest_x) // 2, 0, 25, plan.height))
        else:
            plan.walls.append(InteriorRect(0, (actor.y + closest_y) // 2, plan.width, 25))
        before = sim.state.to_dict()
        self.assertNotIn("core:forge", sim.interiors.station_ids_near_player())
        self.assertEqual(sim.state.to_dict(), before)
        plan.walls.pop()
        actor.x, actor.y = 500, 500
        self.assertNotIn("core:forge", sim.interiors.station_ids_near_player())


if __name__ == "__main__":
    unittest.main()
