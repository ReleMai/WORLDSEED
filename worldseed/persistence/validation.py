from __future__ import annotations

"""Cross-record validation for long-lived WORLDSEED simulation state.

This module deliberately validates serialized dictionaries rather than live
objects so the same checks can be used by save tools without booting a world.
Checks are conservative: only references whose ownership contract is explicit
are treated as hard errors.
"""

from collections import Counter
from typing import Any


def _table(raw: dict[str, Any], name: str) -> dict[str, dict[str, Any]]:
    value = raw.get(name, {})
    return value if isinstance(value, dict) else {}


def validate_sim_state(raw: dict[str, Any] | None) -> list[str]:
    if not raw:
        return []
    issues: list[str] = []
    xp=raw.get('player_swimming_xp',0)
    skill=(raw.get('player_skills',{}) or {}).get('swimming',0)
    if not isinstance(xp,int) or not 0<=xp<120:issues.append('swimming practice out of bounds')
    if not isinstance(skill,int) or not 0<=skill<=10:issues.append('swimming skill out of bounds')
    experiments=raw.get('player_crafting_experiments',0)
    if not isinstance(experiments,int) or not 0<=experiments<=1_000_000:
        issues.append('crafting experiment count out of bounds')
    for key in ('player_discovered_items','player_discovered_recipes'):
        rows=raw.get(key,[]) or []
        if not isinstance(rows,list) or any(not isinstance(v,str) for v in rows):
            issues.append(f'invalid crafting discovery list: {key}')
        elif len(rows)!=len(set(rows)):
            issues.append(f'duplicate crafting discovery entries: {key}')
    settlements = _table(raw, "settlements")
    npcs = _table(raw, "npcs")
    factions = _table(raw, "factions")
    routes = _table(raw, "trade_routes")
    caravans = _table(raw, "caravans")
    properties = _table(raw, "properties")
    migrations = _table(raw, "migration_cohorts")
    cohorts = _table(raw, "cohorts")
    offices = _table(raw, "offices")
    dynasties = _table(raw, "dynasties")
    claims = _table(raw, "claims")
    libraries = _table(raw, "libraries")
    schools = _table(raw, "knowledge_schools")
    institutions = _table(raw, "religious_institutions")
    religions = _table(raw, "religions")
    books = _table(raw, "books")
    diseases = _table(raw, "diseases")
    infections = _table(raw, "infections")

    for uid, row in settlements.items():
        if int(row.get("population", 0)) < 0:
            issues.append(f"negative settlement population: {uid}")
        if int(row.get("wealth", 0)) < 0:
            issues.append(f"negative settlement wealth: {uid}")
        if int(row.get("food_stress", 0)) not in range(0, 101):
            issues.append(f"settlement food stress out of bounds: {uid}")
        stocks = row.get("stocks", {}) or {}
        if any(int(v) < 0 for v in stocks.values()):
            issues.append(f"negative settlement stock: {uid}")
        fid = str(row.get("faction_id", ""))
        if fid and fid not in factions:
            issues.append(f"orphan settlement faction: {uid}->{fid}")

    for uid, row in npcs.items():
        sid = str(row.get("settlement_id", ""))
        if sid and sid not in settlements:
            issues.append(f"orphan NPC settlement: {uid}->{sid}")
        spouse = str(row.get("spouse_uid", ""))
        if spouse and spouse not in npcs:
            issues.append(f"orphan NPC spouse: {uid}->{spouse}")
        for child in row.get("children", []) or []:
            if child not in npcs:
                issues.append(f"orphan NPC child: {uid}->{child}")
        for parent in row.get("parents", []) or []:
            if parent not in npcs:
                issues.append(f"orphan NPC parent: {uid}->{parent}")
        if int(row.get("wealth", 0)) < 0:
            issues.append(f"negative NPC wealth: {uid}")
        if int(row.get("hp", 0)) < 0:
            issues.append(f"negative NPC hp: {uid}")

    outbound = Counter()
    for uid, row in routes.items():
        origin = str(row.get("origin", "")); dest = str(row.get("destination", ""))
        if origin not in settlements:
            issues.append(f"orphan route origin: {uid}->{origin}")
        if dest not in settlements:
            issues.append(f"orphan route destination: {uid}->{dest}")
        danger = int(row.get("danger", 0))
        if not 0 <= danger <= 100:
            issues.append(f"route danger out of bounds: {uid}")
        if int(row.get("capacity", 0)) < 0:
            issues.append(f"negative route capacity: {uid}")
        outbound[origin] += 1
    for origin, count in outbound.items():
        if count > 6:
            issues.append(f"trade graph exceeds partner budget: {origin} has {count}")

    for uid, row in caravans.items():
        if str(row.get("origin", "")) not in settlements:
            issues.append(f"orphan caravan origin: {uid}")
        if str(row.get("destination", "")) not in settlements:
            issues.append(f"orphan caravan destination: {uid}")
        route = str(row.get("route_id", ""))
        if route and route not in routes:
            # Completed historical logistics may outlive a route until pruning;
            # only traveling caravans require a live route contract.
            if row.get("status") == "traveling":
                issues.append(f"traveling caravan missing route: {uid}->{route}")
        if any(int(v) < 0 for v in (row.get("goods", {}) or {}).values()):
            issues.append(f"negative caravan cargo: {uid}")

    for uid, row in migrations.items():
        if str(row.get("origin", "")) not in settlements:
            issues.append(f"orphan migration origin: {uid}")
        if str(row.get("destination", "")) not in settlements:
            issues.append(f"orphan migration destination: {uid}")
        if int(row.get("count", 0)) < 0:
            issues.append(f"negative migration count: {uid}")

    for uid, row in properties.items():
        sid = str(row.get("settlement_id", ""))
        if sid and sid not in settlements:
            issues.append(f"orphan property settlement: {uid}->{sid}")
        condition = int(row.get("condition", 0))
        if not 0 <= condition <= 100:
            issues.append(f"property condition out of bounds: {uid}")
        for occupant in row.get("occupants", []) or []:
            if occupant not in npcs:
                issues.append(f"orphan property occupant: {uid}->{occupant}")

    for uid, row in cohorts.items():
        if int(row.get("count", 0)) < 0:
            issues.append(f"negative cohort: {uid}")
        for key in ("mean_health", "stored_energy", "disease"):
            value = int(row.get(key, 0))
            if value < 0:
                issues.append(f"negative cohort {key}: {uid}")

    for uid, row in offices.items():
        faction = str(row.get("faction_id", "")); holder = str(row.get("holder_uid", ""))
        if faction not in factions:
            issues.append(f"orphan office faction: {uid}->{faction}")
        if holder and holder not in npcs:
            issues.append(f"orphan office holder: {uid}->{holder}")

    for uid, row in dynasties.items():
        faction = str(row.get("faction_id", "")); founder = str(row.get("founder_uid", ""))
        if faction and faction not in factions:
            issues.append(f"orphan dynasty faction: {uid}->{faction}")
        if founder and founder not in npcs:
            issues.append(f"orphan dynasty founder: {uid}->{founder}")

    for uid, row in claims.items():
        claimant = str(row.get("claimant_id", ""))
        if claimant and claimant not in factions:
            issues.append(f"orphan claim claimant: {uid}->{claimant}")
        if row.get("target_type") == "settlement" and str(row.get("target_id", "")) not in settlements:
            issues.append(f"orphan settlement claim target: {uid}")

    for uid, row in libraries.items():
        sid = str(row.get("settlement_id", ""))
        if sid not in settlements:
            issues.append(f"orphan library settlement: {uid}->{sid}")
        for book_uid in row.get("book_uids", []) or []:
            if book_uid not in books:
                issues.append(f"orphan library book: {uid}->{book_uid}")

    for uid, row in schools.items():
        if str(row.get("settlement_id", "")) not in settlements:
            issues.append(f"orphan school settlement: {uid}")
        for member in row.get("member_uids", []) or []:
            if member not in npcs:
                issues.append(f"orphan school member: {uid}->{member}")

    for uid, row in institutions.items():
        if str(row.get("settlement_id", "")) not in settlements:
            issues.append(f"orphan religious institution settlement: {uid}")
        rel = str(row.get("religion_id", ""))
        if rel and rel not in religions:
            issues.append(f"orphan religious institution religion: {uid}->{rel}")
        for priest in row.get("priest_uids", []) or []:
            if priest not in npcs:
                issues.append(f"orphan priest: {uid}->{priest}")


    for uid, row in diseases.items():
        sid=str(row.get("settlement_id", ""))
        if sid and sid not in settlements:
            issues.append(f"orphan disease settlement: {uid}->{sid}")
        infected=int(row.get("infected",0));recovered=int(row.get("recovered",0));deaths=int(row.get("deaths",0));immune=int(row.get("immune",0))
        if min(infected,recovered,deaths,immune)<0:
            issues.append(f"negative disease count: {uid}")
        if not 0<=int(row.get("severity",0))<=100:
            issues.append(f"disease severity out of bounds: {uid}")
        if not 0<=int(row.get("contagiousness",0))<=100:
            issues.append(f"disease contagiousness out of bounds: {uid}")

    player_infections=set(raw.get("player_infections",[]) or [])
    for uid,row in infections.items():
        host_type=str(row.get("host_type",""));host_id=str(row.get("host_id",""))
        if host_type=="npc" and host_id not in npcs:
            issues.append(f"orphan infection NPC host: {uid}->{host_id}")
        if host_type=="player" and uid not in player_infections and str(row.get("stage",""))!="recovered":
            issues.append(f"active player infection not referenced by player: {uid}")
        if int(row.get("severity",0))<0 or int(row.get("viral_load",0))<0:
            issues.append(f"negative infection metric: {uid}")

    for uid,row in npcs.items():
        for inf in row.get("infections",[]) or []:
            if inf not in infections:
                issues.append(f"orphan NPC infection: {uid}->{inf}")

    for uid,row in caravans.items():
        if any(int(v)<0 for v in (row.get("pathogen_load",{}) or {}).values()):
            issues.append(f"negative caravan pathogen load: {uid}")
    for uid,row in migrations.items():
        if any(int(v)<0 for v in (row.get("pathogen_load",{}) or {}).values()):
            issues.append(f"negative migration pathogen load: {uid}")

    history = raw.get("history", []) or []
    event_ids = [str(e.get("uid", "")) for e in history if isinstance(e, dict)]
    if len(event_ids) != len(set(event_ids)):
        issues.append("duplicate live history event id")
    archive = raw.get("history_archive", {}) or {}
    for key, row in archive.items():
        if int((row or {}).get("count", 0)) < 0:
            issues.append(f"negative history archive count: {key}")

    for token in raw.get("realized_regions", []) or []:
        try:
            x, y = str(token).split(",", 1); int(x); int(y)
        except Exception:
            issues.append(f"invalid realized region key: {token!r}")

    return sorted(set(issues))
