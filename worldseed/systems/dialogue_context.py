"""Bounded, observational facts for declarative conversation predicates.

This module projects existing ledgers and read queries into scalar dot keys. It
never prepares geography, updates prices, creates currency, or saves state. A
missing authority is marked unavailable; empty inventories mean no carried
goods, not an invented purse. Collection keys extend automatically for mods.
"""
from __future__ import annotations

from collections.abc import Mapping
from itertools import islice
from typing import Any

from worldseed.core.coords import WorldPos
from worldseed.entities.components import Identity, Inventory, Position, Vitals
from worldseed.systems.economy import BASE_PRICE, TARGET
from worldseed.systems.generation import TRAITS

Scalar = str | int | float | bool | None
MAX_COLLECTION_FACTS = 256
MAX_MEMORY_FACTS = 40


def _mapping(value: Any) -> Mapping:
    return value if isinstance(value, Mapping) else {}


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _read_component(ctx: Any, sim: Any, typ: type) -> Any:
    entities = getattr(ctx, "entities", None) or getattr(sim, "entities", None)
    player_id = getattr(ctx, "player_id", None)
    if player_id is None:
        player_id = getattr(sim, "player_id", None)
    if entities is None or player_id is None:
        return None
    # EntityStore.get uses defaultdict indexing. try_get preserves even the
    # runtime component tables when a component is absent.
    getter = getattr(entities, "try_get", None) or getattr(entities, "get", None)
    if not callable(getter):
        return None
    try:
        return getter(player_id, typ)
    except (KeyError, AttributeError):
        return None


def _map_facts(facts: dict[str, Scalar], prefix: str, value: Any) -> None:
    rows = _mapping(value)
    facts[prefix + ".count"] = len(rows)
    # Only actor/town-local collections reach here. Bound modded collections
    # too; preserve stored order at the cap, then sort the selected keys.
    selected = list(islice(rows.items(), MAX_COLLECTION_FACTS))
    for key, item in sorted(selected, key=lambda pair: str(pair[0])):
        if isinstance(item, (str, int, float, bool)) or item is None:
            facts[prefix + "." + str(key)] = item


def _members(facts: dict[str, Scalar], prefix: str, value: Any) -> None:
    if not isinstance(value, (list, tuple, set, frozenset)):
        value = ()
    facts[prefix + ".count"] = len(value)
    selected = sorted(value, key=str)[:MAX_COLLECTION_FACTS] if isinstance(value, (set, frozenset)) else list(islice(value, MAX_COLLECTION_FACTS))
    for item in sorted(selected, key=str):
        if isinstance(item, (str, int)):
            facts[prefix + "." + str(item)] = True


def _fields(facts: dict[str, Scalar], prefix: str, owner: Any,
            defaults: Mapping[str, Scalar]) -> None:
    for key, default in defaults.items():
        value = getattr(owner, key, default)
        facts[prefix + "." + key] = value if isinstance(value, (str, int, float, bool)) else default


def _environment_facts(ctx: Any, sim: Any, state: Any,
                       facts: dict[str, Scalar]) -> WorldPos:
    clock = getattr(sim, "clock", None)
    minute = _integer(getattr(clock, "minute", getattr(state, "clock_minute", 480)), 480)
    day = minute // 1440
    hour = minute // 60 % 24
    phase = "morning" if 5 <= hour < 11 else "day" if 11 <= hour < 17 else "evening" if 17 <= hour < 22 else "night"
    facts.update({
        "environment.minute": minute, "environment.hour": hour,
        "environment.minute_of_hour": minute % 60, "environment.day": day,
        "environment.year": day // 120 + 1, "environment.day_of_season": day % 30 + 1,
        "environment.season": ("spring", "summer", "autumn", "winter")[day // 30 % 4],
        "environment.phase": phase, "environment.night": phase == "night",
    })
    component = _read_component(ctx, sim, Position)
    pos = getattr(component, "value", None)
    if pos is None:
        pos = getattr(sim, "player_pos", None)
    if pos is None:
        pos = WorldPos(0, 0, 0)
        facts["environment.position_available"] = False
    else:
        facts["environment.position_available"] = True
    pos = WorldPos(_integer(getattr(pos, "x", 0)), _integer(getattr(pos, "y", 0)), _integer(getattr(pos, "z", 0)))
    presence = _mapping(getattr(state, "interior_actors", {})).get("player")
    space_id = str(getattr(presence, "space_id", "") or "")
    plan = _mapping(getattr(state, "interiors", {})).get(space_id)
    facts.update({
        "environment.x": pos.x, "environment.y": pos.y, "environment.z": pos.z,
        "environment.underground": pos.z < 0, "environment.indoors": presence is not None,
        "environment.interior_id": space_id,
        "environment.interior_function": str(getattr(plan, "function", "") or ""),
        "environment.interior_floor": _integer(getattr(plan, "floor_index", 0)),
    })
    weather = getattr(getattr(sim, "environment", None), "weather", None)
    at = getattr(weather, "at", None)
    sample = _mapping(at(minute, pos.x, pos.y)) if callable(at) and facts["environment.position_available"] else {}
    facts["environment.weather_available"] = bool(sample)
    for key in ("kind", "temp_delta", "wind", "rain", "visibility", "cloud_cover", "storm_intensity", "humidity", "wetness", "fog", "wind_dx", "wind_dy", "wind_speed"):
        facts["environment." + key] = sample.get(key, "unknown" if key == "kind" else 0)
    facts["environment.weather"] = facts["environment.kind"]
    facts["environment.wet"] = bool(_integer(sample.get("rain")) > 0 or _integer(sample.get("wetness")) > 0)
    facts["environment.storm"] = sample.get("kind") == "storm" or _integer(sample.get("storm_intensity")) > 0
    facts["environment.exposed"] = presence is None and pos.z >= 0
    return pos


def _player_facts(ctx: Any, sim: Any, state: Any, facts: dict[str, Scalar]) -> None:
    vitals = _read_component(ctx, sim, Vitals)
    if vitals is None:
        vitals = getattr(sim, "player_vitals", None)
    facts["player.vitals_available"] = vitals is not None
    _fields(facts, "player", vitals, {
        "hp": 100, "max_hp": 100, "hunger": 0, "thirst": 0,
        "stamina": 100, "body_temp": 50, "pain": 0, "blood": 100,
    })
    _fields(facts, "player", state, {
        "player_name": "Wanderer", "player_sex": "", "player_literacy": 0,
        "player_swimming_xp": 0, "player_fishing_xp": 0, "player_hunting_xp": 0,
        "player_readied_weapon": "", "player_guarding": False,
        "player_defense_mode": "", "player_hunting_stance": "normal",
        "player_aim_quality": 0, "player_stealth_mode": False,
        "player_crafting_discovery_enabled": False, "player_crafting_experiments": 0,
    })
    # Strip the authoritative state's player_ prefix for the public vocabulary.
    for key in tuple(facts):
        if key.startswith("player.player_"):
            facts["player." + key.removeprefix("player.player_")] = facts.pop(key)
    identity = _read_component(ctx, sim, Identity)
    facts["player.identity_available"] = identity is not None
    _fields(facts, "player", identity, {"culture_id": "", "occupation": "wanderer", "age": 18})
    for source, target in (
        ("player_attributes", "attributes"), ("player_skills", "skills"),
        ("player_languages", "languages"), ("player_equipment", "equipment"),
        ("player_equipped_artifacts", "artifacts"), ("player_body_parts", "body_parts"),
        ("player_nutrition", "nutrition"), ("player_food_effects", "food_effects"),
        ("player_immunities", "immunities"),
    ):
        _map_facts(facts, "player." + target, getattr(state, source, {}))
    for source, target in (
        ("player_talents", "talents"), ("player_knowledge", "knowledge"),
        ("player_infections", "infections"), ("player_discovered_items", "discovered_items"),
        ("player_discovered_recipes", "discovered_recipes"), ("player_unseen_recipes", "unseen_recipes"),
    ):
        _members(facts, "player." + target, getattr(state, source, ()))
    inventory = _read_component(ctx, sim, Inventory)
    items = _mapping(getattr(inventory, "items", {}))
    facts["player.inventory_available"] = inventory is not None
    _map_facts(facts, "player.inventory", items)
    # Market purchase/sale/toll commands all spend this exact carried item.
    count = getattr(inventory, "count", None)
    facts["player.wealth"] = max(0, _integer(count("core:copper_coin") if callable(count) else items.get("core:copper_coin", 0)))
    facts["player.inventory_units"] = sum(max(0, _integer(qty)) for _, qty in islice(items.items(), MAX_COLLECTION_FACTS))
    facts["player.wound_count"] = len(getattr(state, "player_wounds", ()) or ())
    facts["player.infected"] = bool(getattr(state, "player_infections", ()))
    facts["player.hurt"] = bool(facts["player.vitals_available"] and (facts["player.hp"] < max(25, facts["player.max_hp"] // 2) or facts["player.pain"] >= 45 or facts["player.blood"] < 65))
    facts["player.hungry"] = bool(facts["player.vitals_available"] and facts["player.hunger"] >= 70)
    facts["player.thirsty"] = bool(facts["player.vitals_available"] and facts["player.thirst"] >= 70)
    facts["player.exhausted"] = bool(facts["player.vitals_available"] and facts["player.stamina"] <= 20)
    facts["player.cold"] = bool(facts["player.vitals_available"] and facts["player.body_temp"] <= 25)
    facts["player.hot"] = bool(facts["player.vitals_available"] and facts["player.body_temp"] >= 75)
    facts["player.armed"] = bool(facts["player.readied_weapon"] or _mapping(getattr(state, "player_equipment", {})).get("weapon"))
    facts["player.trespassing"] = bool(getattr(state, "player_trespass_property_id", ""))


def _npc_facts(npc: Any, state: Any, facts: dict[str, Scalar]) -> None:
    _fields(facts, "npc", npc, {
        "uid": "", "name": "", "age": 18, "sex": "", "occupation": "villager",
        "hp": 100, "hunger": 0, "thirst": 0, "rest": 0, "wealth": 0,
        "goal": "", "goal_score": 0, "routine_phase": "", "literacy": 0,
        "home_id": "", "workplace_id": "", "property_id": "", "employer_id": "",
        "culture_id": "", "religion_id": "", "settlement_id": "", "faction_id": "",
        "assigned_process_id": "", "work_assignment_day": -1, "work_hours_today": 0,
        "alive": True, "spouse_uid": "", "family_uid": "", "lineage_uid": "",
    })
    for key in ("needs", "skills", "skill_xp", "language_fluency", "inventory", "equipment", "immunities", "backstory"):
        _map_facts(facts, "npc." + key, getattr(npc, key, {}))
    for key in ("traits", "wants", "knowledge", "infections", "disease_history"):
        _members(facts, "npc." + key, getattr(npc, key, ()))
    traits = getattr(npc, "traits", ()) or ()
    for trait in TRAITS:
        facts["npc.traits." + trait] = trait in traits
    parents = getattr(npc, "parents", ()) or ()
    children = getattr(npc, "children", ()) or ()
    facts.update({
        "npc.spouse": bool(facts["npc.spouse_uid"]),
        "npc.parent_count": len(parents), "npc.child_count": len(children),
        "npc.family_count": len(parents) + len(children) + int(bool(facts["npc.spouse_uid"])),
        "npc.has_home": bool(facts["npc.home_id"]),
        "npc.has_workplace": bool(facts["npc.workplace_id"]),
        "npc.child": facts["npc.age"] < 16, "npc.elder": facts["npc.age"] >= 60,
        "npc.hurt": facts["npc.hp"] < 70, "npc.hungry": facts["npc.hunger"] >= 70,
        "npc.thirsty": facts["npc.thirst"] >= 70, "npc.tired": facts["npc.rest"] >= 70,
        "npc.infected": bool(getattr(npc, "infections", ())),
        "npc.indoors": facts["npc.uid"] in _mapping(getattr(state, "interior_actors", {})),
    })
    rel = _mapping(_mapping(getattr(npc, "relationships", {})).get("player", {}))
    for key in ("trust", "affection", "familiarity"):
        facts["relationship." + key] = _integer(rel.get(key, 0))
    _map_facts(facts, "relationship.values", rel)
    memories = getattr(npc, "memories", ()) or ()
    facts["npc.memories.count"] = len(memories)
    facts["npc.memories.player_count"] = 0
    facts["npc.memories.player_valence"] = 0
    for row in memories[-MAX_MEMORY_FACTS:]:
        row = _mapping(row)
        kind = str(row.get("type", "") or "")
        if kind:
            key = "npc.memories." + kind
            facts[key] = _integer(facts.get(key)) + 1
        if row.get("subject") == "player":
            facts["npc.memories.player_count"] += 1
            facts["npc.memories.player_valence"] += _integer(row.get("valence", 0))
    facts["npc.memories.sample_count"] = min(len(memories), MAX_MEMORY_FACTS)
    facts["npc.memories.last_type"] = str(_mapping(memories[-1]).get("type", "")) if memories else ""
    facts["npc.memories.last_minute"] = _integer(_mapping(memories[-1]).get("minute", -1), -1) if memories else -1
    tasks = getattr(npc, "tasks", ()) or ()
    facts["npc.task_count"] = len(tasks)
    task = _mapping(tasks[0]) if tasks else {}
    facts["npc.task_kind"] = str(task.get("kind", ""))
    facts["npc.task_action"] = str(task.get("action", ""))
    needs = list(islice(_mapping(getattr(npc, "needs", {})).items(), MAX_COLLECTION_FACTS))
    urgent = max(needs, key=lambda row: (_integer(row[1]), str(row[0]))) if needs else ("", 0)
    facts["npc.urgent_need"] = str(urgent[0])
    facts["npc.urgent_need_score"] = _integer(urgent[1])
    household = _mapping(getattr(state, "households", {})).get(facts["npc.family_uid"])
    facts["household.present"] = household is not None
    _fields(facts, "household", household, {
        "food_shortage": 0, "days_short": 0, "logistics_mode": "unknown", "reserve_days": 0,
        "total_spent": 0, "total_income": 0, "nutrition_quality": 0, "fuel_shortage": 0,
        "hygiene_shortage": 0, "medical_shortage": 0, "hardship_score": 0, "stable_days": 0,
    })
    for key in ("target_stock", "unmet_needs", "diet_mix"):
        _map_facts(facts, "household." + key, getattr(household, key, {}))
    facts["household.member_count"] = len(getattr(household, "member_uids", ()) or ())


def _town_facts(sim: Any, state: Any, npc: Any, facts: dict[str, Scalar]) -> None:
    settlement_id = str(getattr(npc, "settlement_id", "") or "")
    town = _mapping(getattr(state, "settlements", {})).get(settlement_id)
    facts["town.present"] = town is not None
    _fields(facts, "town", town, {
        "uid": "", "name": "", "population": 0, "wealth": 0,
        "food_stress": 0, "unemployment": 0, "housing_capacity": 0, "homeless": 0,
        "religious_tension": 0, "sanitation": 50, "healer_capacity": 0,
        "quarantine_level": 0, "health_policy": "unknown", "currency_id": "",
        "currency_name": "", "currency_value": 100, "barter_enabled": False,
        "route_centrality": 0, "frontier_status": "unknown", "border_pressure": 0,
        "patrol_pressure": 0, "faction_id": "", "culture_id": "", "religion_id": "",
    })
    for key in ("stocks", "prices", "labor_pool", "law", "budget"):
        _map_facts(facts, "town." + key, getattr(town, key, {}))
    for key in ("knowledge", "resource_specializations", "crop_ids", "livestock_species_ids"):
        _members(facts, "town." + key, getattr(town, key, ()))
    facts.update({
        "town.stressed": bool(town and (facts["town.food_stress"] >= 45 or facts["town.unemployment"] >= 35)),
        "town.food_shortage": bool(town and facts["town.food_stress"] >= 45),
        "town.housing_shortage": bool(town and (facts["town.homeless"] > 0 or facts["town.population"] > facts["town.housing_capacity"])),
        "town.unsanitary": bool(town and facts["town.sanitation"] < 35),
        "town.quarantined": bool(town and facts["town.quarantine_level"] > 0),
        "town.housing_spare": max(0, facts["town.housing_capacity"] - facts["town.population"]),
    })
    heat = _integer(_mapping(getattr(state, "player_crime_heat", {})).get(settlement_id, 0))
    bounty = _integer(_mapping(getattr(state, "player_bounties", {})).get(settlement_id, 0))
    facts.update({"player.crime_heat": heat, "player.bounty": bounty,
                  "player.notoriety": heat, "player.wanted": heat >= 35 or bounty > 0})
    price = getattr(getattr(sim, "economy", None), "trade_price", None)
    facts["town.quotes_available"] = bool(town is not None and callable(price))
    if town is not None:
        stocks = _mapping(getattr(town, "stocks", {}))
        # The economy's supported standard goods, plus existing modded market
        # entries. Quote through the same read API used by transactions.
        goods = set(BASE_PRICE)
        goods.update(key for key, _ in islice(stocks.items(), MAX_COLLECTION_FACTS))
        goods.update(key for key, _ in islice(_mapping(getattr(town, "prices", {})).items(), MAX_COLLECTION_FACTS))
        for item in sorted(goods, key=str)[:MAX_COLLECTION_FACTS]:
            facts["town.stocks." + str(item)] = _integer(stocks.get(item, 0))
            if item in TARGET:
                facts["town.shortages." + item] = _integer(stocks.get(item, 0)) < TARGET[item]
            if callable(price):
                buy = max(1, _integer(price(settlement_id, item, True), 1))
                facts["town.buy_prices." + str(item)] = buy
                facts["town.sell_prices." + str(item)] = max(1, _integer(price(settlement_id, item, False), 1))
                facts["player.afford." + str(item)] = facts["player.wealth"] >= buy


def _faction_facts(state: Any, npc: Any, facts: dict[str, Scalar]) -> None:
    faction_id = str(getattr(npc, "faction_id", "") or facts["town.faction_id"] or "")
    faction = _mapping(getattr(state, "factions", {})).get(faction_id)
    facts["faction.present"] = faction is not None
    _fields(facts, "faction", faction, {
        "uid": "", "name": "", "treasury": 0, "power": 0, "manpower": 0,
        "military_supply": 0, "war_exhaustion": 0, "archetype": "unknown",
        "doctrine": "", "prominence": 0, "road_investment": 0, "toll_policy": 0,
    })
    wars = getattr(faction, "at_war", ()) or ()
    facts["faction.at_war"] = bool(wars)
    facts["faction.war_count"] = len(wars)
    _members(facts, "faction.enemies", wars)
    _map_facts(facts, "faction.laws", getattr(faction, "laws", {}))
    _map_facts(facts, "faction.relations", getattr(faction, "relations", {}))
    for category, id_key, maps, members, scalars in (
        ("culture", "culture_id", ("lexicon",), ("values", "taboos"), ("name", "craft_bias", "architecture_style", "public_space_tradition")),
        ("religion", "religion_id", (), ("domains",), ("name", "deity", "taboo", "ritual", "sacred_animal")),
    ):
        identity = str(getattr(npc, id_key, "") or facts["town." + id_key] or "")
        owner = _mapping(getattr(state, category + "s", {})).get(identity)
        facts[category + ".present"] = owner is not None
        _fields(facts, category, owner, dict.fromkeys(scalars, ""))
        for key in maps:
            _map_facts(facts, category + "." + key, getattr(owner, key, {}))
        for key in members:
            _members(facts, category + "." + key, getattr(owner, key, ()))


def build_dialogue_facts(ctx: Any, npc: Any) -> dict[str, Scalar]:
    """Snapshot real conversation inputs without world or ledger mutation.

    Known maps expose namespaced keys, e.g. ``player.skills.persuasion`` and
    ``town.stocks.core:bread``. Wealth is copper purchasing power carried by
    the player; NPC/town treasuries are separate. Unknown NPCs expose only
    player/environment facts and the introduction gate. Missing minimal-test
    authorities have safe defaults and explicit availability flags.
    """
    sim = getattr(ctx, "sim", ctx)
    state = getattr(sim, "state", None)
    facts: dict[str, Scalar] = {}
    pos = _environment_facts(ctx, sim, state, facts)
    _player_facts(ctx, sim, state, facts)
    uid = str(getattr(npc, "uid", "") or "")
    introduced = getattr(state, "introduced_npcs", None)
    facts["npc.introduced"] = uid in introduced if introduced is not None else True
    if not facts["npc.introduced"]:
        return facts
    _npc_facts(npc, state, facts)
    _town_facts(sim, state, npc, facts)
    _faction_facts(state, npc, facts)
    player_skills = _mapping(getattr(state, "player_skills", {}))
    for skill, level in islice(_mapping(getattr(npc, "skills", {})).items(), MAX_COLLECTION_FACTS):
        facts["comparison.skills." + str(skill)] = _integer(player_skills.get(skill, 0)) - _integer(level)
    facts["comparison.wealth"] = facts["player.wealth"] - _integer(facts["npc.wealth"])
    facts["comparison.same_culture"] = bool(facts["npc.culture_id"] and facts["npc.culture_id"] == facts["player.culture_id"])
    facts["relationship.community"] = 0
    facts["relationship.community_sample_size"] = 0
    nearby = getattr(getattr(sim, "npcs", None), "nearby_npcs", None)
    facts["relationship.community_available"] = bool(callable(nearby) and facts["environment.position_available"])
    if facts["relationship.community_available"]:
        values = []
        for person in islice(nearby(pos, radius=24), MAX_COLLECTION_FACTS):
            if getattr(person, "settlement_id", "") != facts["npc.settlement_id"]:
                continue
            rel = _mapping(_mapping(getattr(person, "relationships", {})).get("player", {}))
            if _integer(rel.get("familiarity", 0)) > 0:
                values.append((_integer(rel.get("trust")) + _integer(rel.get("affection"))) // 2)
        facts["relationship.community"] = sum(values) // len(values) if values else 0
        facts["relationship.community_sample_size"] = len(values)
    return facts
