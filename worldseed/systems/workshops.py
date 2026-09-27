from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WorkshopProfile:
    station_id: str
    title: str
    purpose: str
    action_label: str
    occupation: str
    function: str
    icon: str
    accent: tuple[int, int, int]


WORKSHOP_PROFILES = {
    "core:forge": WorkshopProfile(
        "core:forge","BLACKSMITH'S FORGE",
        "Smelt ore, heat metal, and forge durable tools, weapons, armor, and hardware.",
        "FORGE","smith","smithy","hammer",(188,112,70),
    ),
    "core:workbench": WorkshopProfile(
        "core:workbench","CARPENTER'S WORKBENCH",
        "Shape timber into containers, implements, furnishings, shields, and other woodcraft.",
        "BUILD","carpenter","workshop","saw",(165,126,78),
    ),
    "core:millstone": WorkshopProfile(
        "core:millstone","MILLER'S MILL",
        "Grind harvested grain into flour and prepare bulk grain for settlement food production.",
        "MILL","miller","mill","mill",(182,157,91),
    ),
    "core:bakery_oven": WorkshopProfile(
        "core:bakery_oven","BAKERY OVEN",
        "Turn milled flour into durable prepared food for households, markets, and travel.",
        "BAKE","baker","bakery","bread",(196,139,76),
    ),
    "core:butcher_table": WorkshopProfile(
        "core:butcher_table","BUTCHER'S BLOCK",
        "Break down game and livestock into usable meat, fat, hides, and cooking ingredients.",
        "BUTCHER","butcher","butcher","knife",(166,91,76),
    ),
    "core:tanning_frame": WorkshopProfile(
        "core:tanning_frame","TANNERY",
        "Cure scraped hides with bark and time to make leather for clothing, armor, and equipment.",
        "TAN","tanner","tannery","hide",(151,105,69),
    ),
    "core:loom": WorkshopProfile(
        "core:loom","WEAVER'S LOOM",
        "Turn loose fiber into woven cloth used for clothing, household goods, trade, and future tailoring.",
        "WEAVE","weaver","weavery","loom",(138,121,159),
    ),
    "core:pottery_wheel": WorkshopProfile(
        "core:pottery_wheel","POTTER'S WORKSHOP",
        "Shape clay into useful vessels before firing, supporting storage, cooking, and trade.",
        "THROW CLAY","potter","pottery","pot",(173,105,74),
    ),
    "core:brewery_vat": WorkshopProfile(
        "core:brewery_vat","BREWERY",
        "Ferment grain and fruit into small ale, converting farm surplus into a valuable settlement good.",
        "BREW","brewer","brewery","vat",(151,117,67),
    ),
    "core:herbalist_table": WorkshopProfile(
        "core:herbalist_table","HERBALIST & APOTHECARY",
        "Prepare medicinal herbs, tonics, and sanitation supplies for household and clinical use.",
        "PREPARE","healer","clinic","herb",(103,145,91),
    ),
    "core:masonry_bench": WorkshopProfile(
        "core:masonry_bench","MASON'S YARD",
        "Dress raw stone into construction material for durable civic works, roads, and fortifications.",
        "CUT STONE","mason","mason_yard","stone",(128,132,131),
    ),
    "core:smoke_rack": WorkshopProfile(
        "core:smoke_rack","FISH SMOKEHOUSE",
        "Clean and smoke fish so waterfront harvests become portable food instead of spoiling quickly.",
        "SMOKE","fisher","fishery","fish",(91,136,151),
    ),
}


# Generated settlement fixtures are not player-built StructureInstance objects,
# but player crafting must still recognize them as the same usable station.
STATION_PIECE_ALIASES = {
    "core:forge_piece": "core:forge",
    "core:anvil_piece": "core:forge",
    "core:carpenter_bench_piece": "core:workbench",
    "core:sawbench_piece": "core:workbench",
    "core:millstone_piece": "core:millstone",
    "core:bakery_oven_piece": "core:bakery_oven",
    "core:butcher_table_piece": "core:butcher_table",
    "core:tanning_rack_piece": "core:tanning_frame",
    "core:loom_piece": "core:loom",
    "core:spinning_wheel_piece": "core:loom",
    "core:pottery_wheel_piece": "core:pottery_wheel",
    "core:kiln_piece": "core:pottery_wheel",
    "core:brewery_vat_piece": "core:brewery_vat",
    "core:herbalist_table_piece": "core:herbalist_table",
    "core:apothecary_shelf_piece": "core:herbalist_table",
    "core:masonry_bench_piece": "core:masonry_bench",
    "core:stone_cutting_yard_piece": "core:masonry_bench",
    "core:smoke_rack_piece": "core:smoke_rack",
    "core:fish_cleaning_table_piece": "core:smoke_rack",
    "core:net_mending_bench_piece": "core:smoke_rack",
}


def recipes_for_station(registry, station_id: str):
    """Return stable station-specific player recipes."""
    sid=str(station_id)
    return sorted(
        (recipe for recipe in registry.recipes.values() if recipe.station==sid),
        key=lambda recipe:(recipe.category,recipe.name,recipe.id),
    )


def profile_dict(profile: WorkshopProfile) -> dict:
    return {
        "station_id": profile.station_id,
        "title": profile.title,
        "purpose": profile.purpose,
        "action_label": profile.action_label,
        "occupation": profile.occupation,
        "function": profile.function,
        "icon": profile.icon,
        "accent": list(profile.accent),
    }
