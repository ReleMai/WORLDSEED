"""Read-only workstation information for a selected continuous furnishing."""
from __future__ import annotations

from worldseed.entities.components import Inventory
from worldseed.systems.workshops import STATION_PIECE_ALIASES, WORKSHOP_PROFILES, recipes_for_station


def workstation_details(sim, furniture) -> str:
    """Describe actual availability and learned recipes, never hidden content."""
    station = STATION_PIECE_ALIASES.get(furniture.piece_id)
    profile = WORKSHOP_PROFILES.get(station)
    if profile is None:
        return ""
    status = sim.interiors.furniture_use_status(furniture.uid)
    availability = {
        "available": "Available — open the workstation to choose a learned recipe.",
        "busy": "Busy — a worker has reserved this fixture; wait for them to finish.",
        "out_of_reach": "Out of reach — move closer; interior walls block use.",
        "unavailable": "Unavailable in this interior.",
    }[status]
    lines = [profile.title, profile.purpose, "", availability,
             "Recipes use your carried materials and the original fixture.",
             "Timed process jobs and the separate meal-cooking menu remain outdoor actions.",
             "", "Learned recipes:"]
    inv = sim.entities.get(sim.player_id, Inventory)
    stations = sim.interiors.station_ids_near_player()
    learned = [recipe for recipe in recipes_for_station(sim.registry, station)
               if sim.crafting.recipe_is_discovered(recipe.id)]
    for recipe in learned:
        missing = sim.crafting.missing_requirements(recipe.id, inv, stations)
        lines.append(f"{recipe.name} — {recipe.minutes} minutes")
        lines.append("  Needs: " + "; ".join(missing) if missing else "  Ready to craft")
    if not learned:
        lines.append("No learned recipes for this station yet. Learn techniques or experiment with materials.")
    return "\n".join(lines)
