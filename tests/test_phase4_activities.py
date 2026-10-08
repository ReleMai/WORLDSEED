import unittest
from types import SimpleNamespace

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.systems.activities import ActivitySystem
from worldseed.systems.ai import NPCSystem
from worldseed.systems.state import LivingWorldState, NPCState, SettlementState
from worldseed.world.regional_plan import StructurePiecePlan


class NullHistory:
    def record(self, *args, **kwargs):
        pass


class FakePhysicalization:
    def __init__(self, skeleton, structure_id):
        self._skeleton = skeleton
        self.structure_id = structure_id
        self.world = SimpleNamespace(is_passable=lambda pos: True)

    def skeleton_for(self, settlement_id):
        return self._skeleton

    def cell_at(self, pos):
        return SimpleNamespace(structure_id=self.structure_id)

    def passable(self, pos, world_passable=True):
        return bool(world_passable)

    def destination_for(self, structure_id, room_id=""):
        return WorldPos(10, 9, 0)


class Phase4ActivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)

    def fixture(self):
        state = LivingWorldState()
        town = SettlementState(
            uid="settlement:activity",
            name="Activity Town",
            region_x=0,
            region_y=0,
            x=10,
            y=10,
            population=40,
            culture_id="culture:test",
            religion_id="religion:test",
            faction_id="faction:test",
        )
        state.settlements[town.uid] = town
        workplace = "structure:smithy"
        forge = StructurePiecePlan(
            uid="piece:forge",
            structure_plan_id=workplace,
            piece_id="core:forge_piece",
            x=10,
            y=10,
            layer="fixture",
            role="fixture",
        )
        anvil = StructurePiecePlan(
            uid="piece:anvil",
            structure_plan_id=workplace,
            piece_id="core:anvil_piece",
            x=12,
            y=10,
            layer="fixture",
            role="fixture",
        )
        skeleton = SimpleNamespace(pieces=[forge, anvil])
        physical = FakePhysicalization(skeleton, workplace)
        npc = NPCState(
            uid="npc:smith",
            name="Smith",
            age=31,
            occupation="smith",
            traits=["patient"],
            x=8,
            y=9,
            z=0,
            settlement_id=town.uid,
            faction_id=town.faction_id,
            workplace_id=workplace,
            work_room_id="room:smithy",
            home_id="home:smith",
        )
        state.npcs[npc.uid] = npc
        activities = ActivitySystem(state, self.registry, physical, physical.world)
        return state, town, npc, physical, activities

    def test_affordances_come_from_real_workplace_fixtures(self):
        state, town, npc, physical, activities = self.fixture()
        rows = activities.work_affordances(npc, town)
        self.assertEqual({row.target_uid for row in rows}, {"piece:forge", "piece:anvil"})
        forge = next(row for row in rows if "forge" in row.tags)
        self.assertEqual(forge.workplace_role, "smith")
        self.assertNotEqual((forge.use_x, forge.use_y), (forge.x, forge.y))

    def test_reservations_are_exclusive_and_persist(self):
        state, town, npc, physical, activities = self.fixture()
        forge = next(row for row in activities.work_affordances(npc, town) if "forge" in row.tags)
        first = activities.reserve(npc, forge, 600, duration_minutes=15, phase="heat")
        self.assertIsNotNone(first)

        other = NPCState(
            uid="npc:smith:other",
            name="Other Smith",
            age=28,
            occupation="smith",
            traits=[],
            x=8,
            y=9,
            z=0,
            settlement_id=town.uid,
            faction_id=town.faction_id,
            workplace_id=npc.workplace_id,
        )
        state.npcs[other.uid] = other
        self.assertIsNone(activities.reserve(other, forge, 600, duration_minutes=15, phase="heat"))

        restored = LivingWorldState.from_dict(state.to_dict())
        self.assertIn(first.uid, restored.activity_reservations)
        self.assertEqual(restored.activity_reservations[first.uid].target_uid, "piece:forge")

    def test_smith_plan_is_physical_heat_then_shape_chain(self):
        state, town, npc, physical, activities = self.fixture()
        tasks = activities.plan_work(npc, town, 600)
        self.assertEqual([row["kind"] for row in tasks], ["move", "activity", "move", "activity"])
        self.assertEqual(tasks[1]["action"], "smith_heat")
        self.assertEqual(tasks[3]["action"], "smith_shape")
        self.assertEqual(tasks[3]["on_complete"], "work")
        reservations = [state.activity_reservations[t["reservation_uid"]] for t in tasks if t["kind"] == "activity"]
        self.assertEqual([row.phase for row in reservations], ["heat", "shape"])
        self.assertEqual(len({row.target_uid for row in reservations}), 2)

    def test_busy_physical_smithy_never_falls_back_to_ghost_work(self):
        state, town, npc, physical, activities = self.fixture()
        first_tasks = activities.plan_work(npc, town, 600)
        self.assertTrue(first_tasks)

        other = NPCState(
            uid="npc:smith:waiting",
            name="Waiting Smith",
            age=29,
            occupation="smith",
            traits=[],
            x=8,
            y=9,
            z=0,
            settlement_id=town.uid,
            faction_id=town.faction_id,
            workplace_id=npc.workplace_id,
            home_id="home:waiting",
        )
        state.npcs[other.uid] = other
        calls = []
        ai = NPCSystem(state, b"phase4-busy-test", NullHistory())
        ai.attach_settlement_population(physical, SimpleNamespace(bind_settlement=lambda town: None))
        ai.attach_activity_system(activities)
        ai.attach_economy(SimpleNamespace(
            representative_work=lambda actor, settlement, minute: calls.append(actor.uid)
        ))
        reservations_before=state.to_dict()["activity_reservations"]
        stocks_before=dict(town.stocks)
        ai.generate_plan(other, town, 600, "work")
        # A busy station now sends the actor to the real workplace to wait;
        # it still cannot bypass the reservation with abstract ghost work.
        self.assertEqual(other.tasks[0], {"kind":"move", "x":10, "y":9, "schedule_goal":"work"})
        self.assertEqual(other.tasks[1]["kind"], "wait")
        self.assertFalse(any(t.get("action")=="work" for t in other.tasks))
        for minute in range(605, 630, 5):
            ai.execute_tick(other, town, minute, WorldPos(8, 9))
        self.assertEqual(calls, [])
        self.assertEqual(town.stocks,stocks_before)
        self.assertEqual(state.to_dict()["activity_reservations"],reservations_before)

    def test_ai_completes_smith_work_only_after_both_physical_activities(self):
        state, town, npc, physical, activities = self.fixture()
        calls = []
        economy = SimpleNamespace(
            representative_work=lambda actor, settlement, minute: calls.append((actor.uid, minute))
        )
        ai = NPCSystem(state, b"phase4-activity-test", NullHistory())
        ai.attach_settlement_population(physical, SimpleNamespace(bind_settlement=lambda town: None))
        ai.attach_activity_system(activities)
        ai.attach_economy(economy)

        npc.needs = {"purpose": 60}
        ai.generate_plan(npc, town, 600, "work")
        self.assertEqual(len(npc.tasks), 4)

        # Arrive at the forge standing cell.
        npc.x, npc.y = npc.tasks[0]["x"], npc.tasks[0]["y"]
        ai._execute_task(npc, town, 605, WorldPos(10, 10, 0))
        self.assertEqual(npc.tasks[0]["action"], "smith_heat")
        ai._execute_task(npc, town, 610, WorldPos(10, 10, 0))
        self.assertEqual(calls, [])
        ai._execute_task(npc, town, 625, WorldPos(10, 10, 0))
        self.assertEqual(calls, [])

        # Move to the anvil standing cell, then spend the second duration there.
        self.assertEqual(npc.tasks[0]["kind"], "move")
        npc.x, npc.y = npc.tasks[0]["x"], npc.tasks[0]["y"]
        ai._execute_task(npc, town, 630, WorldPos(10, 10, 0))
        self.assertEqual(npc.tasks[0]["action"], "smith_shape")
        ai._execute_task(npc, town, 635, WorldPos(10, 10, 0))
        self.assertEqual(calls, [])
        ai._execute_task(npc, town, 655, WorldPos(10, 10, 0))
        self.assertEqual(calls, [(npc.uid, 655)])
        self.assertEqual(npc.needs["purpose"], 40)
        self.assertFalse(npc.tasks)


if __name__ == "__main__":
    unittest.main()
