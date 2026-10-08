"""Daily timetables remain personal, deterministic and observational."""
import copy
from dataclasses import FrozenInstanceError
import json
import unittest

from worldseed.systems.npc_schedule import (
    daily_schedule, preferred_goal, schedule_at, schedule_rows,
)
from worldseed.systems.state import LivingWorldState, NPCState


class NPCScheduleTests(unittest.TestCase):
    seed = b"npc-schedule-tests"

    def npc(self, uid="npc:scheduled", occupation="farmer", age=30, **fields):
        return NPCState(uid, "Ada", age, occupation, [], 0, 0, 0,
                        "town:schedule", "faction:schedule", **fields)

    def assert_day_covered(self, blocks):
        self.assertEqual(blocks[0].start_minute, 0)
        self.assertEqual(blocks[-1].end_minute, 1440)
        for block in blocks:
            self.assertLess(block.start_minute, block.end_minute)
            self.assertGreaterEqual(block.start_minute, 0)
            self.assertLessEqual(block.end_minute, 1440)
        for first, second in zip(blocks, blocks[1:]):
            self.assertEqual(first.end_minute, second.start_minute)

    def minutes_for(self, blocks, activity):
        return sum(block.end_minute - block.start_minute for block in blocks
                   if block.activity == activity)

    def leisure_minute(self, npc):
        return next(block.start_minute for block in daily_schedule(npc, self.seed)
                    if block.activity == "leisure")

    def test_every_role_has_a_bounded_gap_free_day(self):
        for occupation in ("farmer", "lumberjack", "smith", "merchant", "cook",
                           "healer", "scholar", "priest", "guard", "unemployed"):
            for index in range(12):
                npc = self.npc(f"npc:{index}", occupation)
                with self.subTest(occupation=occupation, uid=npc.uid):
                    blocks = daily_schedule(npc, self.seed)
                    self.assert_day_covered(blocks)
                    self.assertLessEqual(len(blocks), 13)
                    self.assertEqual(self.minutes_for(blocks, "sleep"), 480)
                    self.assertEqual(self.minutes_for(blocks, "meal"), 90)

    def test_workers_have_eight_work_hours_with_a_lunch_break(self):
        for occupation in ("farmer", "merchant", "smith"):
            npc = self.npc(occupation=occupation)
            blocks = daily_schedule(npc, self.seed)
            self.assertEqual(self.minutes_for(blocks, "work"), 480)
            work = [block for block in blocks if block.is_work]
            self.assertEqual(len(work), 2)
            lunch = schedule_at(npc, self.seed, work[0].end_minute)
            self.assertEqual((lunch.activity, lunch.label), ("meal", "Lunch"))
            self.assertEqual(work[1].start_minute, lunch.end_minute)
            self.assertEqual(schedule_at(npc, self.seed, 18 * 60).label, "Dinner")

    def test_each_person_has_a_stable_offset_and_outdoor_workers_start_earlier(self):
        starts = set()
        for index in range(30):
            npc = self.npc(f"npc:{index}")
            first = daily_schedule(npc, self.seed)
            self.assertEqual(first, daily_schedule(copy.deepcopy(npc), self.seed))
            starts.add(next(block.start_minute for block in first if block.is_work))
        self.assertEqual(len(starts), 3)
        self.assertTrue(all(6 * 60 <= minute <= 6 * 60 + 30 for minute in starts))
        smith = self.npc(occupation="smith")
        self.assertGreater(next(block.start_minute for block in daily_schedule(smith, self.seed)
                                if block.is_work), max(starts))

    def test_guard_rota_covers_night_and_sleep_never_overlaps_duty(self):
        shifts = {}
        for index in range(40):
            npc = self.npc(f"npc:guard:{index}", "guard")
            blocks = daily_schedule(npc, self.seed)
            duty = next(block for block in blocks if block.activity == "guard")
            shifts[duty.start_minute] = npc
            self.assertEqual(self.minutes_for(blocks, "guard"), 480)
            self.assertEqual(self.minutes_for(blocks, "sleep"), 480)
            for minute in (duty.start_minute, duty.end_minute - 1):
                self.assertEqual(preferred_goal(npc, self.seed, minute), "guard")
            self.assert_day_covered(blocks)
        self.assertEqual(set(shifts), {0, 480, 960})
        night_guard = shifts[0]
        self.assertEqual(schedule_at(night_guard, self.seed, 3 * 60).activity, "guard")
        self.assertEqual(schedule_at(night_guard, self.seed, 15 * 60).activity, "sleep")
        day_guard = shifts[480]
        self.assertEqual(schedule_at(day_guard, self.seed, 23 * 60).activity, "sleep")
        self.assertEqual(schedule_at(day_guard, self.seed, 2 * 60).activity, "sleep")

    def test_children_attend_school_without_adult_profession_duty(self):
        child = self.npc(occupation="guard", age=12)
        blocks = daily_schedule(child, self.seed)
        self.assert_day_covered(blocks)
        self.assertEqual(self.minutes_for(blocks, "school"), 360)
        self.assertFalse(any(block.is_work for block in blocks))
        school = next(block for block in blocks if block.activity == "school")
        self.assertEqual(preferred_goal(child, self.seed, school.start_minute), "learn")
        self.assertEqual(self.minutes_for(blocks, "sleep"), 480)

    def test_unemployed_and_retired_people_have_free_time_instead_of_work(self):
        for occupation in ("", "unemployed", "retired", "none"):
            npc = self.npc(occupation=occupation, workplace_id="legacy:workplace")
            blocks = daily_schedule(npc, self.seed)
            self.assertFalse(any(block.is_work for block in blocks))
            self.assertGreater(self.minutes_for(blocks, "leisure"), 480)
            self.assert_day_covered(blocks)

    def test_block_boundaries_and_absolute_days_are_half_open(self):
        npc = self.npc()
        blocks = daily_schedule(npc, self.seed)
        for block in blocks:
            self.assertEqual(schedule_at(npc, self.seed, block.start_minute), block)
            self.assertEqual(schedule_at(npc, self.seed, block.end_minute - 1), block)
            for days in (-2, -1, 1, 100):
                self.assertEqual(schedule_at(npc, self.seed, block.start_minute + days * 1440), block)
        self.assertEqual(schedule_at(npc, self.seed, 1440), blocks[0])

    def test_leisure_responds_to_needs_without_moving_the_timetable(self):
        npc = self.npc()
        minute = self.leisure_minute(npc)
        original_times = [(block.start_minute, block.end_minute, block.activity)
                          for block in daily_schedule(npc, self.seed)]
        for needs, expected in (({"social": 90}, "socialize"),
                                ({"learning": 90}, "learn"),
                                ({"faith": 90}, "worship"),
                                ({"health": 90}, "heal")):
            npc.needs = needs
            self.assertEqual(preferred_goal(npc, self.seed, minute), expected)
            self.assertEqual(original_times, [(block.start_minute, block.end_minute, block.activity)
                                             for block in daily_schedule(npc, self.seed)])
        npc.needs = {}
        npc.rest = 75
        self.assertEqual(preferred_goal(npc, self.seed, minute), "rest")

    def test_skills_traits_and_occupation_shape_free_time(self):
        novice = self.npc(skills={"carpentry": 1})
        expert = self.npc(skills={"carpentry": 10})
        self.assertEqual(preferred_goal(novice, self.seed, self.leisure_minute(novice)), "socialize")
        self.assertEqual(preferred_goal(expert, self.seed, self.leisure_minute(expert)), "learn")
        curious = self.npc()
        curious.traits = ["curious"]
        priest = self.npc(occupation="priest")
        self.assertEqual(preferred_goal(curious, self.seed, self.leisure_minute(curious)), "learn")
        self.assertEqual(preferred_goal(priest, self.seed, self.leisure_minute(priest)), "worship")

    def test_inspection_is_immutable_and_does_not_change_saved_state(self):
        npc = self.npc(skills={"farming": 3}, needs={"social": 30})
        state = LivingWorldState()
        state.npcs[npc.uid] = npc
        before = state.to_dict()
        blocks = daily_schedule(npc, self.seed)
        rows = schedule_rows(npc, self.seed)
        schedule_at(npc, self.seed, 600)
        preferred_goal(npc, self.seed, 1100)
        self.assertEqual(state.to_dict(), before)
        self.assertEqual(len(rows), len(blocks))
        self.assertTrue(rows[-1][0].endswith("–24:00"))
        with self.assertRaises(FrozenInstanceError):
            blocks[0].activity = "work"

    def test_save_roundtrip_derives_the_same_schedule_and_preserves_pending_tasks(self):
        npc = self.npc(occupation="carpenter", skills={"carpentry": 8},
                       needs={"learning": 35, "social": 15})
        npc.traits = ["curious", "patient"]
        npc.tasks = [{"kind": "perform", "action": "work", "schedule_goal": "work",
                      "started_minute": 600, "complete_minute": 660,
                      "legacy_planner_marker": "opaque-route-metadata"}]
        state = LivingWorldState()
        state.clock_minute = 615
        state.npcs[npc.uid] = npc
        timetable = daily_schedule(npc, self.seed)
        current = preferred_goal(npc, self.seed, state.clock_minute)
        payload = json.loads(json.dumps(state.to_dict()))
        # Timetables are derived from existing fields rather than saved as a
        # separate schedule authority; task dictionaries remain extensible.
        self.assertNotIn("schedule", payload)
        self.assertFalse(any(key.startswith("schedule") for key in payload["npcs"][npc.uid]))
        for marker in ("work", None, "legacy:unknown-goal"):
            with self.subTest(schedule_goal=marker):
                saved = copy.deepcopy(payload)
                task = saved["npcs"][npc.uid]["tasks"][0]
                if marker is None:
                    task.pop("schedule_goal")
                    # Older NPC records can omit these optional fields.
                    saved["npcs"][npc.uid].pop("routine_phase")
                    saved["npcs"][npc.uid].pop("skill_xp")
                else:
                    task["schedule_goal"] = marker
                restored = LivingWorldState.from_dict(saved)
                loaded = restored.npcs[npc.uid]
                self.assertEqual(daily_schedule(loaded, self.seed), timetable)
                self.assertEqual(preferred_goal(loaded, self.seed, restored.clock_minute), current)
                self.assertEqual(loaded.tasks, [task])
                self.assertEqual(loaded.skills, npc.skills)
                self.assertEqual(loaded.needs, npc.needs)
                self.assertEqual(loaded.traits, npc.traits)


if __name__ == "__main__":
    unittest.main()
