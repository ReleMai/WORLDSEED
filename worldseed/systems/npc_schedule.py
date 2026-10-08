"""Derived daily routines for named NPCs, shared by the game and the job lab.

Timetables are a read model of existing NPC identity, never a second clock or
saved state. Needs can change the chosen leisure activity without moving the
NPC's work and sleep hours. Urgent needs and unfinished physical transfers are
handled by the AI that consumes these preferences.
"""
from __future__ import annotations

from dataclasses import dataclass

from worldseed.core.rng import hash_u64
from worldseed.systems.state import NPCState


DAY_MINUTES = 1440


@dataclass(frozen=True, slots=True)
class ScheduleBlock:
    """One half-open interval within a day, with midnight crossings split."""

    start_minute: int
    end_minute: int
    activity: str
    label: str

    @property
    def is_work(self) -> bool:
        return self.activity in {"work", "guard"}


def _identity_hash(npc: NPCState, seed: bytes, purpose: str) -> int:
    return hash_u64(
        seed, "npc-schedule", purpose, npc.uid, npc.occupation,
        "child" if npc.age < 16 else "adult",
        ",".join(sorted(set(npc.traits))),
    )


def _leisure_goal(npc: NPCState, seed: bytes) -> str:
    """Use existing needs and skills to choose an executable free-time goal."""
    needs = npc.needs
    if npc.hp < 70 or needs.get("health", 0) >= 40:
        return "heal"
    expertise = min(10, max((int(level) for level in npc.skills.values()), default=0))
    traits = set(npc.traits)
    scores = {
        "socialize": 35 + 2 * needs.get("social", 0)
        + (30 if "kind" in traits else 0) + (20 if npc.age < 16 else 0),
        "learn": 20 + 2 * needs.get("learning", 0) + max(0, expertise) * 4
        + (45 if "curious" in traits else 0)
        + (70 if npc.occupation == "scholar" else 0),
        "worship": 10 + 2 * needs.get("faith", 0)
        + (35 if "traditional" in traits else 0)
        + (80 if npc.occupation == "priest" else 0),
        "rest": 20 + npc.rest * 2 + (25 if npc.age >= 60 else 0)
        + (15 if "stoic" in traits else 0),
    }
    # Hash only actual ties, keeping this small query cheap at local cadence.
    best_score = max(scores.values())
    tied = [goal for goal, score in scores.items() if score == best_score]
    if len(tied) == 1:
        return tied[0]
    return max(tied, key=lambda goal: _identity_hash(npc, seed, "leisure:" + goal))


def _cycle_blocks(anchor: int, phases: list[tuple[int, str, str]]) -> tuple[ScheduleBlock, ...]:
    if sum(duration for duration, _, _ in phases) != DAY_MINUTES:
        raise ValueError("A daily routine must cover exactly 1440 minutes")
    blocks = []
    cursor = anchor
    for duration, activity, label in phases:
        if duration < 0:
            raise ValueError("A routine interval cannot have negative duration")
        if duration == 0:
            continue
        start = cursor % DAY_MINUTES
        end = start + duration
        blocks.append(ScheduleBlock(start, min(end, DAY_MINUTES), activity, label))
        if end > DAY_MINUTES:
            blocks.append(ScheduleBlock(0, end - DAY_MINUTES, activity, label))
        cursor += duration
    blocks.sort(key=lambda block: block.start_minute)
    merged = []
    for block in blocks:
        if (merged and merged[-1].end_minute == block.start_minute
                and (merged[-1].activity, merged[-1].label) == (block.activity, block.label)):
            previous = merged.pop()
            block = ScheduleBlock(previous.start_minute, block.end_minute, block.activity, block.label)
        merged.append(block)
    return tuple(merged)


def daily_schedule(npc: NPCState, seed: bytes) -> tuple[ScheduleBlock, ...]:
    """Return a bounded, deterministic, gap-free timetable without mutating NPCs.

    Adults work eight hours with a lunch break; guards have three continuous
    eight-hour shifts with sleep outside duty. Children attend six hours of
    school. Every routine reserves eight hours for sleep and three meals.
    Unemployed adults have personal/free time instead of fictional work.
    """
    leisure_goal = _leisure_goal(npc, seed)
    leisure_label = "Leisure: " + {
        "socialize": "Socializing", "learn": "Study", "worship": "Worship",
        "rest": "Rest", "heal": "Recovery",
    }[leisure_goal]
    if npc.age >= 16 and npc.occupation == "guard":
        anchor = int(_identity_hash(npc, seed, "guard-shift") % 3) * 480
        return _cycle_blocks(anchor, [
            (480, "guard", "Guard duty"),
            (30, "meal", "Meal after duty"),
            (180, "leisure", leisure_label),
            (30, "personal", "Personal time"),
            (480, "sleep", "Sleep"),
            (30, "meal", "Breakfast"),
            (120, "leisure", leisure_label),
            (30, "meal", "Meal before duty"),
            (60, "personal", "Personal time"),
        ])

    offset = int(_identity_hash(npc, seed, "start-offset") % 3) * 15
    child = npc.age < 16
    if child:
        anchor = 8 * 60 + offset
        duty_duration, sleep_start = 180, 780
        duty_activity, duty_label = "school", "School"
    else:
        if npc.occupation in {"farmer", "herder", "hunter", "lumberjack", "fisher", "baker", "cook"}:
            start_hour = 6
        elif npc.occupation in {"miner", "healer", "priest", "miller", "butcher"}:
            start_hour = 7
        else:
            start_hour = 8
        anchor = start_hour * 60 + offset
        duty_duration, sleep_start = 240, 900
        duty_activity, duty_label = "work", "Work"
        if npc.occupation in {"", "none", "unemployed", "retired", "child"}:
            duty_activity, duty_label = "leisure", leisure_label

    duty_end = duty_duration * 2 + 30
    dinner_start = 18 * 60 - anchor
    # Personal time after duty gives workers time to return home. Children
    # have a shorter school day and more free time before the common dinner.
    phases = [
        (duty_duration, duty_activity, duty_label),
        (30, "meal", "Lunch"),
        (duty_duration, duty_activity, duty_label),
        (60, "personal", "Personal time"),
        (dinner_start - duty_end - 60, "leisure", leisure_label),
        (30, "meal", "Dinner"),
        (sleep_start - dinner_start - 60, "leisure", leisure_label),
        (30, "personal", "Personal time"),
        (480, "sleep", "Sleep"),
    ]
    if child:
        phases.append((120, "leisure", leisure_label))
    phases.extend([(30, "meal", "Breakfast"), (30, "personal", "Personal time")])
    return _cycle_blocks(anchor, phases)


def schedule_at(npc: NPCState, seed: bytes, minute: int) -> ScheduleBlock:
    """Find the half-open block at any absolute game minute, including past days."""
    day_minute = int(minute) % DAY_MINUTES
    return next(block for block in daily_schedule(npc, seed)
                if block.start_minute <= day_minute < block.end_minute)


def preferred_goal(npc: NPCState, seed: bytes, minute: int,
                   block: ScheduleBlock | None = None) -> str:
    """Translate the current schedule into a goal the existing AI can execute.

    Consumers already holding the current block may pass it to avoid building
    the timetable again. The supplied block must match the requested minute.
    """
    activity = (block if block is not None else schedule_at(npc, seed, minute)).activity
    if activity in {"personal", "leisure"}:
        return _leisure_goal(npc, seed)
    return {"work": "work", "guard": "guard", "school": "learn",
            "meal": "eat", "sleep": "rest"}[activity]


def schedule_rows(npc: NPCState, seed: bytes) -> list[tuple[str, str]]:
    """Observational rows for the World Console and the standalone job lab."""
    def hhmm(value: int) -> str:
        return f"{value // 60:02d}:{value % 60:02d}"

    return [(f"{hhmm(block.start_minute)}–{hhmm(block.end_minute)}", block.label)
            for block in daily_schedule(npc, seed)]
