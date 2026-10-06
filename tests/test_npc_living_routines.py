"""Local residents move and complete routines without a second economy."""
from types import SimpleNamespace
import unittest

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.systems.ai import NPCSystem
from worldseed.systems.economy import EconomySystem
from worldseed.systems.pathfinding import local_path
from worldseed.systems.state import LivingWorldState, NPCState, SettlementState


class NullHistory:
    def record(self, *args, **kwargs):
        pass


class NPCLivingRoutineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)

    def fixture(self, occupation="merchant"):
        state = LivingWorldState()
        town = SettlementState("settlement:living", "Millford", 0, 0, 0, 0, 100,
                               "culture:test", "religion:test", "faction:test",
                               stocks={"core:wheat":160, "core:turnip":100,
                                       "core:wood":100, "core:stone":80,
                                       "core:iron_ore":40, "core:coal":40},
                               knowledge=["tech:smelting"])
        npc = NPCState("npc:living", "Ada", 30, occupation, [], 0, 0, 0,
                       town.uid, town.faction_id, home_id="home:living",
                       workplace_id="work:living")
        state.settlements[town.uid] = town
        state.npcs[npc.uid] = npc
        ai = NPCSystem(state, b"living-test", NullHistory(),
                       world=SimpleNamespace(is_passable=lambda pos: True))
        return state, town, npc, ai

    def test_local_path_reaches_cardinal_and_diagonal_trips_deterministically(self):
        for goal in (WorldPos(28, 0), WorldPos(24, 24), WorldPos(-24, 24)):
            with self.subTest(goal=goal):
                first = local_path(WorldPos(0, 0), goal, lambda pos: True, 1000)
                self.assertTrue(first)
                self.assertEqual(first[-1], goal)
                self.assertEqual(len(first), abs(goal.x) + abs(goal.y) + 1)
                self.assertEqual(first, local_path(WorldPos(0, 0), goal, lambda pos: True, 1000))

    def test_local_path_detours_around_building_and_bounds_failed_search(self):
        blocked = {(x, y) for x in range(3, 10) for y in range(-2, 3)}
        path = local_path(WorldPos(0, 0), WorldPos(15, 0),
                          lambda pos: (pos.x, pos.y) not in blocked, 1000)
        self.assertTrue(path)
        self.assertGreater(len(path), 16)
        self.assertTrue(all((pos.x, pos.y) not in blocked for pos in path))
        probes = []
        def closed_wall(pos):
            probes.append(pos)
            return pos.x != 1
        self.assertEqual(local_path(WorldPos(0, 0), WorldPos(2, 0), closed_wall, 80), [])
        self.assertLessEqual(len(probes), 80 * 4)
        self.assertTrue(all(max(abs(pos.x), abs(pos.y)) <= 40 for pos in probes))
        self.assertEqual(local_path(WorldPos(0, 0), WorldPos(41, 0), lambda pos: True, 200), [])

    def test_npc_advances_over_multiple_ticks_on_long_diagonal_trip(self):
        _, town, npc, ai = self.fixture()
        npc.tasks = [{"kind":"move", "x":60, "y":60, "exact":True}]
        positions = []
        for minute in range(605, 855, 5):
            if not npc.tasks:
                break
            ai.tick_update(minute, WorldPos(32, 32))
            positions.append((npc.x, npc.y))
        self.assertEqual((npc.x, npc.y), (60, 60))
        self.assertGreater(len(set(positions)), 25)
        self.assertFalse(npc.tasks)
        self.assertEqual(ai.nearby_npcs(WorldPos(60, 60), 1), (npc,))

    def test_nonexact_move_arrives_beside_impassable_target(self):
        _, town, npc, ai = self.fixture()
        ai.world.is_passable = lambda pos: (pos.x, pos.y) != (20, 0)
        npc.tasks = [{"kind":"move", "x":20, "y":0}]
        for minute in range(605, 665, 5):
            if not npc.tasks:
                break
            ai.tick_update(minute, WorldPos(0, 0))
        self.assertEqual(abs(npc.x - 20) + abs(npc.y), 1)
        self.assertFalse(npc.tasks)

    def test_locked_physical_corridor_cannot_be_teleported_through(self):
        _, town, npc, ai = self.fixture()
        locked = [True]
        ai.world.is_passable = lambda pos: 0 <= pos.x <= 6 and pos.y == 0
        ai.property_security = SimpleNamespace(
            blocks_actor=lambda pos, uid, minute: locked[0] and pos.x == 2)
        npc.tasks = [{"kind":"move", "x":6, "y":0, "exact":True}]
        ai.tick_update(605, WorldPos(0, 0))
        self.assertEqual((npc.x, npc.y), (0, 0))
        locked[0] = False
        ai.tick_update(610, WorldPos(0, 0))
        self.assertEqual((npc.x, npc.y), (3, 0))

    def test_satisfied_need_releases_historical_peak_goal(self):
        _, town, npc, ai = self.fixture()
        npc.goal = "drink"
        npc.goal_score = 500
        npc.thirst = 0
        goal, score = ai.select_utility_goal(npc, town, 600)
        self.assertEqual(goal, "work")
        self.assertLess(score, 500)
        npc.goal, npc.goal_score, npc.rest = "rest", 1000, 0
        self.assertEqual(ai.select_utility_goal(npc, town, 600)[0], "work")

    def test_drinking_completes_before_hour_and_next_goal_walks(self):
        _, town, npc, ai = self.fixture()
        npc.goal, npc.goal_score, npc.thirst = "drink", 360, 90
        npc.tasks = [{"kind":"perform", "action":"drink"}]
        ai.settlement_physicalization = SimpleNamespace(
            destination_for=lambda uid, room="": WorldPos(15, 0))
        ai.tick_update(605, WorldPos(0, 0))
        self.assertEqual(npc.thirst, 90)
        ai.tick_update(610, WorldPos(0, 0))
        self.assertEqual(npc.thirst, 35)
        self.assertFalse(npc.tasks)
        ai.tick_update(615, WorldPos(0, 0))
        self.assertEqual(npc.goal, "drink")
        # A second short drink satisfies remaining thirst, then work wins.
        for minute in range(620, 640, 5):
            ai.tick_update(minute, WorldPos(0, 0))
        self.assertEqual(npc.goal, "work")
        self.assertGreater(npc.x, 0)

    def test_local_work_and_purchases_do_not_multiply_with_tick_frequency(self):
        _, town, npc, ai = self.fixture()
        completions = []
        ai.economy = SimpleNamespace(
            representative_work=lambda who, where, minute: completions.append(minute),
            trade_price=lambda *args, **kwargs: 3,
            record_transaction=lambda *args, **kwargs: None)
        npc.tasks = [{"kind":"perform", "action":"work"}]
        before = dict(town.stocks)
        for minute in range(600, 660, 5):
            ai.tick_update(minute, WorldPos(0, 0))
        self.assertEqual(completions, [])
        ai.tick_update(660, WorldPos(0, 0))
        self.assertEqual(completions, [660])
        self.assertEqual(town.stocks, before)
        npc.hunger = 90
        npc.tasks = [{"kind":"perform", "action":"eat"}]
        wealth = npc.wealth
        for minute in range(665, 725, 5):
            ai.tick_update(minute, WorldPos(0, 0))
        self.assertEqual(town.stocks, before)
        ai.tick_update(725, WorldPos(0, 0))
        self.assertEqual(town.stocks["core:wheat"], before["core:wheat"] - 1)
        self.assertEqual(npc.wealth, wealth - 3)

    def test_routine_deadline_roundtrips_without_restarting_on_load(self):
        state, town, npc, ai = self.fixture()
        npc.rest = 90
        npc.tasks = [{"kind":"perform", "action":"rest"}]
        ai.tick_update(605, WorldPos(0, 0))
        restored = LivingWorldState.from_dict(state.to_dict())
        loaded_npc = restored.npcs[npc.uid]
        loaded_ai = NPCSystem(restored, b"living-test", NullHistory())
        loaded_ai.tick_update(630, WorldPos(0, 0))
        self.assertEqual(loaded_npc.rest, 90)
        loaded_ai.tick_update(635, WorldPos(0, 0))
        self.assertEqual(loaded_npc.rest, 35)
        self.assertFalse(loaded_npc.tasks)

    def test_first_work_plan_prepares_jobs_without_production(self):
        state, town, npc, ai = self.fixture("farmer")
        economy = EconomySystem(state, self.registry, b"living-test", NullHistory())
        ai.attach_economy(economy)
        assignments = []
        def plan(who, where, minute):
            assignments.append((who.work_assignment_day, who.assigned_process_id))
            return [{"kind":"move", "x":12, "y":0, "profession_task":True}]
        ai.professions = SimpleNamespace(supports_physical_work=lambda *args: True, plan_work=plan)
        stocks, wealth = dict(town.stocks), town.wealth
        ai.generate_plan(npc, town, 600, "work")
        self.assertEqual(assignments[0][0], 0)
        self.assertTrue(assignments[0][1])
        self.assertEqual(npc.work_hours_today, 0)
        self.assertEqual(town.stocks, stocks)
        self.assertEqual(town.wealth, wealth)
        npc.work_hours_today = 2
        newcomer = NPCState("npc:new-worker", "Bo", 28, "farmer", [], 1, 0, 0,
                            town.uid, town.faction_id)
        state.npcs[newcomer.uid] = newcomer
        economy.ensure_work_assignments(town, 610)
        self.assertEqual(npc.work_hours_today, 2)
        self.assertEqual(newcomer.work_assignment_day, 0)
        self.assertTrue(newcomer.assigned_process_id)
        self.assertEqual(town.stocks, stocks)

    def test_unavailable_exact_job_waits_at_own_workplace_without_output(self):
        _, town, npc, ai = self.fixture("farmer")
        ai.settlement_physicalization = SimpleNamespace(
            destination_for=lambda uid, room="": WorldPos(12, 0))
        ai.professions = SimpleNamespace(
            supports_physical_work=lambda *args: True,
            plan_work=lambda *args: [], has_active_work=lambda who: False,
            is_physical_task=lambda task: False)
        before = dict(town.stocks)
        ai.generate_plan(npc, town, 600, "work")
        phases = []
        for minute in range(605, 650, 5):
            ai.tick_update(minute, WorldPos(0, 0))
            phases.append(npc.routine_phase)
        self.assertGreaterEqual(npc.x, 11)
        self.assertEqual(town.stocks, before)
        self.assertEqual(npc.work_hours_today, 0)
        self.assertIn("waiting_for_work", phases)

    def test_hourly_supply_retry_occurs_once_per_active_settlement(self):
        state, town, npc, ai = self.fixture()
        other = NPCState("npc:other", "Bo", 30, "merchant", [], 1, 0, 0,
                         town.uid, town.faction_id, home_id="home:other")
        state.npcs[other.uid] = other
        npc.tasks = [{"kind":"perform", "action":"work"}]
        other.tasks = [{"kind":"perform", "action":"work"}]
        calls = []
        ai.settlement_population = SimpleNamespace(equipment=SimpleNamespace(
            provision_settlement=lambda where: calls.append(where.uid)))
        ai.decision_update(600, WorldPos(0, 0))
        self.assertEqual(calls, [town.uid])


if __name__ == "__main__":
    unittest.main()
