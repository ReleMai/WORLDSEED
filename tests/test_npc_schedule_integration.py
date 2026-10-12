"""Personal routines change decisions without bypassing physical work authority."""
from collections import Counter
from types import SimpleNamespace
import unittest

from tests import test_interiors as interior_fixtures
from tests import test_phase4_professions as profession_fixtures
from worldseed.core.coords import WorldPos
from worldseed.systems.ai import NPCSystem
from worldseed.systems.npc_schedule import daily_schedule, schedule_at
from worldseed.systems.state import LivingWorldState, NPCState, SettlementState


class NullHistory:
    def record(self, *args, **kwargs):
        pass


class NPCScheduleIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        profession_fixtures.Phase4ProfessionTests.setUpClass()
        interior_fixtures.InteriorPortalTests.setUpClass()

    def fixture(self):
        state = LivingWorldState()
        town = SettlementState("town:schedule", "Town", 0, 0, 0, 0, 50,
                               "culture", "religion", "faction")
        npc = NPCState("npc:schedule", "Alex", 30, "merchant", [], 0, 0, 0,
                       town.uid, town.faction_id, home_id="home", workplace_id="work",
                       hunger=0, thirst=0, rest=0)
        state.settlements[town.uid], state.npcs[npc.uid] = town, npc
        ai = NPCSystem(state, b"schedule-integration", NullHistory(),
                       world=SimpleNamespace(is_passable=lambda pos: True))
        return state, town, npc, ai

    def test_personal_sleep_and_leisure_gate_work_with_urgent_needs_overriding(self):
        _, town, npc, ai = self.fixture()
        blocks = daily_schedule(npc, ai.seed)
        for activity, allowed in (("work", {"work"}), ("sleep", {"rest"}),
                                  ("leisure", {"socialize", "learn", "rest", "worship", "heal"})):
            block = next(block for block in blocks if block.activity == activity)
            npc.goal = "work"
            self.assertIn(ai.select_utility_goal(npc, town, block.start_minute)[0], allowed)
        sleep = next(block for block in blocks if block.activity == "sleep")
        npc.thirst = 90
        self.assertEqual(ai.select_utility_goal(npc, town, sleep.start_minute)[0], "drink")
        npc.thirst, npc.hunger = 0, 90
        self.assertEqual(ai.select_utility_goal(npc, town, sleep.start_minute)[0], "eat")
        npc.hunger, npc.hp = 0, 35
        self.assertEqual(ai.select_utility_goal(npc, town, sleep.start_minute)[0], "heal")

    def test_shift_boundary_redirects_a_safe_work_walk(self):
        _, town, npc, ai = self.fixture()
        final_shift = [block for block in daily_schedule(npc, ai.seed) if block.activity == "work"][-1]
        ai.settlement_physicalization = SimpleNamespace(
            destination_for=lambda *args: WorldPos(50, 0),
            destination_for_function=lambda *args: WorldPos(0, 0))
        ai._choose_goal_and_plan(npc, town, final_shift.end_minute - 1)
        ai.refresh_schedule(npc, town, final_shift.end_minute - 1)
        self.assertEqual(npc.tasks[0]["schedule_goal"], "work")
        ai.tick_update(final_shift.end_minute, WorldPos(0, 0))
        self.assertNotEqual(npc.goal, "work")
        self.assertFalse(any(task.get("action") == "work" for task in npc.tasks))

    def test_inflight_reserved_batch_finishes_and_deposits_after_shift_end(self):
        made = profession_fixtures.Phase4ProfessionTests().make(
            "carpenter", "core:woodcraft", piece_id="core:carpenter_bench_piece")
        state, town, npc, world, physical, activities, _, _, professions, storage = made
        npc.hunger = npc.thirst = npc.rest = 0
        storage.items["core:wood"] = 1
        ai = NPCSystem(state, b"profession-tests", NullHistory(), world=world)
        physical.destination_for_function = lambda *args: WorldPos(0, 0)
        ai.attach_settlement_population(physical, None)
        ai.attach_activity_system(activities)
        ai.attach_profession_system(professions)
        end = [block.end_minute for block in daily_schedule(npc, ai.seed) if block.activity == "work"][-1]
        start = end - 3
        ai._choose_goal_and_plan(npc, town, start)
        self.assertTrue(any(task.get("reservation_uid") for task in npc.tasks))
        before = Counter(storage.items) + Counter(npc.inventory) + Counter(town.stocks)
        initial_chain = list(npc.tasks)
        for minute in range(start, end + 90):
            ai.tick_update(minute, WorldPos(0, 0))
            if storage.items.get("core:wooden_bowl", 0) == 1:
                break
        else:
            self.fail("Reserved batch did not reach real storage after its shift ended")
        self.assertGreaterEqual(minute, end)
        self.assertEqual(storage.items.get("core:wood", 0), 0)
        self.assertEqual(npc.inventory, {})
        expected = before.copy()
        expected.subtract({"core:wood": 1})
        expected.update({"core:wooden_bowl": 1})
        self.assertEqual(+expected, +(Counter(storage.items) + Counter(npc.inventory) + Counter(town.stocks)))
        self.assertTrue(any(row.status == "completed" for row in state.activity_reservations.values()))
        self.assertTrue(all(task.get("schedule_goal") == "work" for task in initial_chain))
        ai.tick_update(minute + 1, WorldPos(0, 0))
        self.assertNotEqual(npc.goal, "work")

    def test_faster_ticks_do_not_multiply_work_or_need_growth(self):
        for tick in (1, 5):
            with self.subTest(tick=tick):
                _, town, npc, ai = self.fixture()
                completions = []
                ai.economy = SimpleNamespace(representative_work=lambda who, where, minute: completions.append(minute))
                npc.tasks = [{"kind": "perform", "action": "work"}]
                for minute in range(600, 661, tick):
                    ai.tick_update(minute, WorldPos(0, 0))
                self.assertEqual(completions, [660])
                self.assertEqual((npc.hunger, npc.thirst, npc.rest), (0, 0, 0))

    def test_home_resident_recovers_from_voluntary_rest_during_work_then_releases(self):
        sim, house, door = interior_fixtures.InteriorPortalTests().fixture()
        npc = sim.state.npcs["npc:owner"]
        npc.occupation, npc.goal = "merchant", "rest"
        npc.home_id, npc.workplace_id = house.uid, "work:elsewhere"
        npc.hunger, npc.thirst, npc.rest = 0, 0, 60
        npc.tasks = []
        work = next(block for block in daily_schedule(npc, sim.seed) if block.activity == "work")
        sim.clock.minute = work.start_minute + 30
        npc.x, npc.y, npc.z = door.x, door.y, door.z
        self.assertTrue(sim.interiors.enter_npc(npc, door.uid))
        initial = npc.rest
        sim.interiors.tick_update(sim.clock.minute + 1)
        self.assertIn(npc.uid, sim.state.interior_actors)
        self.assertNotEqual(sim.state.interior_actors[npc.uid].action, "leaving")
        for minute in range(sim.clock.minute + 2, sim.clock.minute + 240):
            sim.interiors.tick_update(minute)
            if npc.uid not in sim.state.interior_actors or sim.state.interior_actors[npc.uid].action == "leaving":
                break
        self.assertLess(npc.rest, initial)
        if npc.uid in sim.state.interior_actors:
            self.assertEqual(sim.state.interior_actors[npc.uid].action, "leaving")

    def test_multiple_residents_enter_home_without_stacking(self):
        from copy import deepcopy
        sim,house,door=interior_fixtures.InteriorPortalTests().fixture()
        npc=sim.state.npcs["npc:owner"]
        npc.home_id=house.uid
        npc.x,npc.y,npc.z=door.x,door.y,door.z
        other=deepcopy(npc);other.uid="npc:second-resident"
        sim.state.npcs[other.uid]=other
        self.assertTrue(sim.interiors.enter_npc(npc,door.uid))
        self.assertTrue(sim.interiors.enter_npc(other,door.uid))
        first=sim.state.interior_actors[npc.uid]
        second=sim.state.interior_actors[other.uid]
        self.assertEqual(first.space_id,second.space_id)
        self.assertNotEqual((first.x,first.y),(second.x,second.y))

    def test_home_meal_uses_seating_and_reduces_hunger(self):
        sim,house,door=interior_fixtures.InteriorPortalTests().fixture()
        npc=sim.state.npcs["npc:owner"]
        npc.occupation="merchant"
        npc.goal="eat"
        npc.home_id, npc.workplace_id=house.uid,"other:workplace"
        npc.hunger,npc.thirst,npc.rest=85,30,0
        npc.tasks=[]
        meal=next(block for block in daily_schedule(npc,sim.seed)
                  if block.activity=="meal")
        sim.clock.minute=meal.start_minute
        npc.x,npc.y,npc.z=door.x,door.y,door.z
        self.assertTrue(sim.interiors.enter_npc(npc,door.uid))
        actions=set()
        for minute in range(meal.start_minute+1,meal.end_minute):
            sim.interiors.tick_update(minute)
            actor=sim.state.interior_actors.get(npc.uid)
            if actor is None:break
            actions.add(actor.action)
            if npc.hunger<60:break
        self.assertIn("eating",actions)
        self.assertLess(npc.hunger,85)

    def test_night_guard_sleeps_in_day_and_wakes_for_own_duty(self):
        sim, house, door = interior_fixtures.InteriorPortalTests().fixture()
        npc = sim.state.npcs["npc:owner"]
        npc.occupation, npc.goal = "guard", "rest"
        # Pick a deterministic night guard; the actual schedule remains derived
        # from identity and is the same authority used by the game and UI.
        for index in range(30):
            uid = "npc:night-guard:" + str(index)
            npc.uid = uid
            if schedule_at(npc, sim.seed, 60).activity == "guard":
                break
        else:
            self.fail("No night-shift fixture identity found")
        sim.state.npcs = {npc.uid: npc}
        npc.home_id, npc.workplace_id = house.uid, "watchhouse:elsewhere"
        npc.hunger = npc.thirst = npc.rest = 0
        npc.tasks = []
        sleep = next(block for block in daily_schedule(npc, sim.seed)
                     if block.activity == "sleep" and block.start_minute >= 6 * 60)
        sim.clock.minute = sleep.start_minute
        npc.x, npc.y, npc.z = door.x, door.y, door.z
        self.assertTrue(sim.interiors.enter_npc(npc, door.uid))
        sim.interiors.tick_update(sleep.start_minute + 1)
        self.assertIn(npc.uid, sim.state.interior_actors)
        self.assertNotEqual(sim.state.interior_actors[npc.uid].action, "leaving")
        actor = sim.state.interior_actors[npc.uid]
        plan = sim.state.interiors[actor.space_id]
        actor.x, actor.y = plan.entry_x, plan.entry_y
        actor.waypoints.clear()
        actor.last_need_minute = 1440
        sim.npcs = NPCSystem(sim.state, sim.seed, NullHistory())
        sim.npcs.attach_interior_system(sim.interiors)
        sim.npcs.tick_update(1440, sim.player_pos)
        self.assertNotIn(npc.uid, sim.state.interior_actors)
        self.assertFalse(npc.tasks)  # The exit is this tick's physical action.
        sim.npcs.tick_update(1441, sim.player_pos)
        self.assertEqual(npc.goal, "guard")


if __name__ == "__main__":
    unittest.main()
