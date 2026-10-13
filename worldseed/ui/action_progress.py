"""Presentation-only schedules for world-advancing, visibly timed actions.

The simulation remains authoritative for duration and state. This module only
translates committed game minutes into bounded animation progress; it never
changes the simulation, recipe outputs, or save format.
"""
from __future__ import annotations

import re


_ACTION_NAMES = {
    "CraftCommand": "Crafting",
    "ComponentCraftCommand": "Assembling",
    "DiscoveryPotCommand": "Experimenting",
    "ExperimentRecipeCommand": "Experimenting",
    "CookMealCommand": "Cooking",
    "StartSalvageCommand": "Starting salvage",
    "StartSalvageGameCommand": "Preparing salvage",
    "SalvageActionCommand": "Salvaging",
    "QuickSalvageCommand": "Salvaging",
    "ProcessCarcassCommand": "Butchering",
    "StartProcessingCommand": "Processing materials",
    "BuildCommand": "Building",
    "AdvanceBlueprintCommand": "Building",
    "RepairCrossingCommand": "Repairing crossing",
    "WaitCommand": "Waiting",
    "RestCommand": "Resting",
    "GatherCommand": "Gathering",
    "FishingCommand": "Fishing",
    "ExcavateShaftCommand": "Excavating",
    "CollectWaterCommand": "Collecting water",
    "RitualCommand": "Performing ritual",
    "ReadBookCommand": "Reading",
}


def action_title(command: object) -> str:
    name = type(command).__name__
    if name in _ACTION_NAMES:
        return _ACTION_NAMES[name]
    name = name.removesuffix("Command")
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name).strip() or "Working"


def visual_duration(game_minutes: int) -> float:
    """Seconds of presentation, not a gameplay mechanic or extra time charge."""
    minutes = max(0, int(game_minutes))
    return min(5.0, max(0.35, 0.35 + minutes * 0.085))


def elapsed_minutes(total_minutes: int, fraction: float, already_advanced: int = 0) -> int:
    """Monotone authoritative target, clamped so time can never be double-billed."""
    total = max(0, int(total_minutes))
    current = max(0, min(total, int(already_advanced)))
    fraction = max(0.0, min(1.0, float(fraction)))
    return max(current, min(total, int(total * fraction + 1e-9)))
