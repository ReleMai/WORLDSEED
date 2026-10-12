"""Salvaging mastery: three specializations and save-safe perk purchases."""
from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class SalvagePerk:
    id: str
    name: str
    path: str
    tier: int
    level: int
    description: str

_NAMES = {
    "precision": (
        ("seam_sense", "Seam Sense", "Reveal the safest approach to one concealed connection."),
        ("steady_hands", "Steady Hands", "Stabilize a project once, reducing strain by 20."),
        ("intact_recovery", "Intact Recovery", "Clean work protects an additional common component."),
        ("gentle_undo", "Gentle Undo", "Correct one damaging operation at a small time cost."),
        ("conservator", "Conservator", "Pristine work recovers one eligible rare part without a chance roll."),
    ),
    "scavenging": (
        ("fast_hands", "Fast Hands", "Quick salvage takes twenty percent less time."),
        ("sorted_scrap", "Sorted Scrap", "Quick salvage improves from 65% to 75% common recovery."),
        ("sweep_job", "Sweep Job", "Process four identical objects in one quick salvage operation."),
        ("makeshift_rig", "Makeshift Rig", "Quick jobs tolerate tools one grade below the requirement."),
        ("wreckbreaker", "Wreckbreaker", "Quick salvage reaches 85%, handles six items and can recover rare parts."),
    ),
    "ingenuity": (
        ("tell_tale_marks", "Tell-Tale Marks", "Show learned crafting uses in salvage component previews."),
        ("workshop_whisper", "Workshop Whisper", "Record a workshop hint when reclaiming relevant material."),
        ("notes_from_ruins", "Notes From Ruins", "First-time salvages can reveal an extra material combination clue."),
        ("targeted_search", "Targeted Search", "Favor one salvage output for a better recovery chance."),
        ("lost_arts", "Lost Arts", "Pristine work on three distinct sources forms a workshop research dossier."),
    ),
}
LEVEL_GATES = (1, 3, 5, 7, 10)
PERKS = {
    row[0]: SalvagePerk(row[0], row[1], path, tier, LEVEL_GATES[tier-1], row[2])
    for path, rows in _NAMES.items() for tier, row in enumerate(rows, 1)
}
PATHS = tuple(_NAMES)

def owned(state) -> set[str]:
    return set(getattr(state, "player_salvage_perks", []))

def available_points(state) -> int:
    return max(0, min(10, int(state.player_skills.get("salvaging", 0))) - len(owned(state)))

def has(state, perk_id: str) -> bool:
    return perk_id in owned(state)

def purchase(state, perk_id: str) -> tuple[bool, str]:
    perk = PERKS.get(perk_id)
    if perk is None:
        return False, "Unknown salvaging perk."
    current = owned(state)
    if perk_id in current:
        return False, "You already know that perk."
    if available_points(state) <= 0:
        return False, "No unspent salvaging skill points."
    if int(state.player_skills.get("salvaging", 0)) < perk.level:
        return False, f"Requires Salvaging level {perk.level}."
    if perk.tier > 1:
        previous = _NAMES[perk.path][perk.tier-2][0]
        if previous not in current:
            return False, "Unlock the previous perk on this path first."
    state.player_salvage_perks = sorted(current | {perk_id})
    return True, f"Unlocked {perk.name}."

def respec(state) -> tuple[bool, str]:
    if not owned(state):
        return False, "No salvaging perks to refund."
    remaining = int(getattr(state, "player_salvage_respecs", 0))
    if remaining <= 0:
        return False, "No salvaging respec tokens remain."
    state.player_salvage_respecs = remaining - 1
    state.player_salvage_perks = []
    return True, "Salvaging perks refunded. All earned skill points are available again."

def view(state) -> dict:
    skills = owned(state)
    level = min(10, max(0, int(state.player_skills.get("salvaging", 0))))
    return {
        "level": level, "points": available_points(state),
        "respecs": int(getattr(state, "player_salvage_respecs", 1)),
        "paths": [
            {"id": path, "label": path.title(), "perks": [
                {"id": p.id, "name": p.name, "tier": p.tier,
                 "level": p.level, "description": p.description,
                 "owned": p.id in skills,
                 "available": p.id not in skills and level >= p.level
                    and available_points(state) > 0
                    and (p.tier == 1 or _NAMES[path][p.tier-2][0] in skills)}
                for p in (PERKS[row[0]] for row in rows)]}
            for path, rows in _NAMES.items()
        ],
    }
