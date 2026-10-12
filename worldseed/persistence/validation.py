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


def _validate_interiors(raw: dict[str, Any]) -> list[str]:
    """Validate optional fixed-point indoor records without preparing geography."""
    issues: list[str] = []
    plans, actors = _table(raw, "interiors"), _table(raw, "interior_actors")
    for key in ("interiors", "interior_actors"):
        if key in raw and not isinstance(raw[key], dict):
            issues.append(f"invalid interior table: {key}")
    furniture_ids: set[str] = set()
    for space_id, plan in plans.items():
        if not isinstance(plan, dict):
            issues.append(f"invalid interior record: {space_id}")
            continue
        building_id = plan.get("building_id", "")
        floor_index, floor_count = plan.get("floor_index", 0), plan.get("floor_count", 1)
        valid_floor = (type(floor_index) is int and type(floor_count) is int
                       and 1 <= floor_count <= 3 and 0 <= floor_index < floor_count)
        expected_space = "interior:" + str(building_id)
        if type(floor_index) is int and floor_index:
            expected_space += ":floor:" + str(floor_index)
        if plan.get("uid") != space_id or not building_id or space_id != expected_space:
            issues.append(f"invalid interior identity: {space_id}")
        if not valid_floor:
            issues.append(f"invalid interior floor metadata: {space_id}")
        if type(plan.get("furnishing_version", 0)) is not int or plan.get("furnishing_version", 0) not in (0, 1, 2):
            issues.append(f"unsupported interior furnishing version: {space_id}")
        width, height = plan.get("width"), plan.get("height")
        if type(plan.get("version", 1)) is not int or plan.get("version", 1) not in (1, 2, 3, 4):
            issues.append(f"unsupported interior plan version: {space_id}")
        layout_id = plan.get("layout_id", "")
        if not isinstance(layout_id, str) or (layout_id and (":" not in layout_id or any(c.isspace() for c in layout_id))):
            issues.append(f"invalid interior layout identity: {space_id}")
        for field in ("variant_id", "floor_material", "wall_material"):
            value = plan.get(field, "")
            if not isinstance(value, str) or (value and (":" not in value or any(c.isspace() for c in value))):
                issues.append(f"invalid interior {field}: {space_id}")
        if not all(type(v) is int and 1 <= v <= 100_000 for v in (width, height)):
            issues.append(f"invalid interior dimensions: {space_id}")
            continue
        def point_valid(row: dict, x_key="x", y_key="y") -> bool:
            x, y = row.get(x_key), row.get(y_key)
            return type(x) is int and type(y) is int and 0 <= x <= width and 0 <= y <= height
        def rect_valid(row) -> bool:
            return (isinstance(row, dict) and point_valid(row)
                    and all(type(row.get(k)) is int and row[k] > 0 for k in ("w", "h"))
                    and row["x"] + row["w"] <= width and row["y"] + row["h"] <= height)
        if not point_valid(plan, "entry_x", "entry_y"):
            issues.append(f"invalid interior portal position: {space_id}")
        if any(type(plan.get(k)) is not int for k in ("exterior_x", "exterior_y", "exterior_z")):
            issues.append(f"invalid interior exterior anchor: {space_id}")
        door_uid = plan.get("door_uid", "")
        door = _table(raw, "door_security").get(door_uid)
        if not door_uid or (door and door.get("property_id") != building_id):
            issues.append(f"invalid interior door binding: {space_id}")
        for collection in ("rooms", "walls", "furniture", "piles", "stairs"):
            rows = plan.get(collection, [])
            if not isinstance(rows, list):
                issues.append(f"invalid interior {collection}: {space_id}")
                continue
            identifiers: set[str] = set()
            for row in rows:
                if not isinstance(row, dict):
                    issues.append(f"invalid interior {collection} record: {space_id}")
                    continue
                if collection != "walls":
                    uid = row.get("uid", "")
                    if not isinstance(uid, str) or not uid or uid in identifiers:
                        issues.append(f"duplicate or invalid interior {collection} identity: {space_id}")
                    identifiers.add(str(uid))
                if collection == "rooms" and not rect_valid(row.get("rect")):
                    issues.append(f"invalid interior room rectangle: {space_id}")
                elif collection in {"walls", "furniture", "stairs"} and not rect_valid(row):
                    issues.append(f"invalid interior {collection} rectangle: {space_id}")
                if collection == "stairs":
                    target = plans.get(row.get("target_space_id", ""))
                    valid_target = isinstance(target, dict) and type(target.get("floor_index", 0)) is int
                    expected_direction = "up" if valid_target and valid_floor and target.get("floor_index", 0) > floor_index else "down"
                    if (not valid_target or target.get("building_id") != building_id
                            or not valid_floor or abs(target.get("floor_index", 0) - floor_index) != 1
                            or row.get("direction") != expected_direction):
                        issues.append(f"invalid interior stair binding: {space_id}")
                    elif (type(row.get("target_x")) is not int or type(row.get("target_y")) is not int
                          or not (0 <= row["target_x"] <= target.get("width", 0)
                                  and 0 <= row["target_y"] <= target.get("height", 0))):
                        issues.append(f"invalid interior stair landing: {space_id}")
                    else:
                        returns = target.get("stairs", [])
                        reverse_direction = "down" if row.get("direction") == "up" else "up"
                        if not (isinstance(returns, list) and any(
                                isinstance(back, dict) and back.get("target_space_id") == space_id
                                and back.get("direction") == reverse_direction for back in returns)):
                            issues.append(f"missing reciprocal interior stair binding: {space_id}")
                elif collection == "piles":
                    if not point_valid(row):
                        issues.append(f"invalid interior pile position: {space_id}")
                    items = row.get("items", {})
                    if not isinstance(items, dict) or any(not isinstance(k, str) or type(v) is not int or v < 0 for k, v in items.items()):
                        issues.append(f"negative or invalid interior pile goods: {space_id}")
                if collection == "furniture":
                    uid = str(row.get("uid", ""))
                    if uid in furniture_ids:
                        issues.append(f"duplicate interior furniture identity: {uid}")
                    furniture_ids.add(uid)
    for uid, actor in actors.items():
        if not isinstance(actor, dict):
            issues.append(f"invalid interior actor record: {uid}")
            continue
        plan = plans.get(actor.get("space_id", ""))
        if not isinstance(plan, dict):
            issues.append(f"orphan interior actor space: {uid}")
            continue
        if uid != "player" and uid not in _table(raw, "npcs"):
            issues.append(f"orphan interior NPC actor: {uid}")
        width, height = plan.get("width"), plan.get("height")
        waypoints = actor.get("waypoints", [])
        if not isinstance(waypoints, list) or any(not isinstance(p, (list, tuple)) or len(p) != 2 for p in waypoints):
            issues.append(f"invalid interior actor waypoints: {uid}")
            waypoints = []
        points = [(actor.get("x"), actor.get("y"))] + [tuple(p) for p in waypoints]
        if actor.get("target_x") is not None or actor.get("target_y") is not None:
            points.append((actor.get("target_x"), actor.get("target_y")))
        for x, y in points:
            if (type(x) is not int or type(y) is not int or type(width) is not int or type(height) is not int
                    or not (0 <= x <= width and 0 <= y <= height)):
                issues.append(f"interior actor position out of bounds: {uid}")
    for uid,reservation in _table(raw,'activity_reservations').items():
        metadata=reservation.get('metadata',{}) if isinstance(reservation,dict) else {}
        if not isinstance(metadata,dict) or not metadata.get('space_id'):continue
        plan=plans.get(metadata['space_id']) if isinstance(metadata['space_id'],str) else None
        if not isinstance(plan,dict):
            issues.append(f'orphan interior activity space: {uid}')
            continue
        if metadata.get('door_uid')!=plan.get('door_uid'):
            issues.append(f'invalid interior activity door binding: {uid}')
        x,y=metadata.get('interior_use_x'),metadata.get('interior_use_y')
        width,height=plan.get('width'),plan.get('height')
        if (any(type(v) is not int for v in (x,y,width,height)) or not (0<=x<width and 0<=y<height)):
            issues.append(f'invalid interior activity position: {uid}')
        fixture_ids={f.get('uid') for f in plan.get('furniture',[]) if isinstance(f,dict)}
        if reservation.get('target_uid') not in fixture_ids:
            issues.append(f'orphan interior activity fixture: {uid}')
    storage_bindings: set[tuple[str,str]] = set()
    for key,container in _table(raw,'containers').items():
        if not isinstance(container,dict):continue
        space_id=container.get('interior_space_id','')
        if not space_id:continue
        uid=container.get('uid','')
        furnishing_uid=container.get('interior_furniture_uid','')
        if not isinstance(space_id,str) or not isinstance(furnishing_uid,str):
            issues.append(f'invalid interior storage binding type: {uid}')
            continue
        linked_plan = plans.get(space_id)
        if furnishing_uid:
            binding=(space_id,furnishing_uid)
            if binding in storage_bindings:
                issues.append(f'duplicate interior storage furnishing: {uid}')
            storage_bindings.add(binding)
        if (space_id!='interior:'+str(container.get('property_id',''))
                and not (isinstance(linked_plan,dict)
                         and linked_plan.get('building_id')==container.get('property_id'))):
            issues.append(f'invalid interior storage space binding: {uid}')
        if key!='indoor-storage:'+str(uid):
            issues.append(f'invalid interior storage index: {uid}')
        profile=container.get('profile_id','')
        if not isinstance(profile,str) or not profile.startswith('core:'):
            issues.append(f'invalid interior storage profile: {uid}')
        plan=plans.get(space_id)
        # A storage point may be reserved before anyone prepares its interior.
        # A nonempty binding must reference its real furnishing. Empty means
        # migration safely deferred placement while that prepared room is full.
        if plan is not None:
            ids={f.get('uid') for f in plan.get('furniture',[]) if isinstance(f,dict)}
            if furnishing_uid and furnishing_uid not in ids:
                issues.append(f'orphan interior storage furnishing: {uid}')
        elif not furnishing_uid:
            issues.append(f'pending interior storage has no prepared space: {uid}')
        goods=container.get('items',{})
        if not isinstance(goods,dict) or any(type(v) is not int or v<0 for v in goods.values()):
            issues.append(f'negative or invalid interior storage goods: {uid}')
    return issues


def validate_salvage_session(session: Any, attempts: int) -> list[str]:
    """Check the already-consumed project without looking up world content."""
    if not isinstance(session, dict):
        return ['invalid salvage session']
    if not session:
        return []
    issues = []
    def identity(value):
        return isinstance(value, str) and ':' in value and not any(c.isspace() for c in value)
    if type(session.get('version')) is not int or session.get('version') != 1:
        issues.append('unsupported salvage session version')
    if not identity(session.get('item_id')) or not identity(session.get('definition_id')):
        issues.append('invalid salvage session item identity')
    attempt = session.get('attempt')
    if type(attempt) is not int or type(attempts) is not int or not 0 <= attempt < attempts:
        issues.append('salvage session attempt is not reserved')
    if type(session.get('started_minute')) is not int or session['started_minute'] < 0:
        issues.append('invalid salvage session start time')
    step, score = session.get('step'), session.get('score')
    valid_progress = type(step) is int and 0 <= step <= 2 and type(score) is int and 0 <= score <= 2 * step and score % 2 == 0
    choices = session.get('choices')
    if (not valid_progress or not isinstance(choices, list)
            or any(not isinstance(choice, str) or not choice for choice in choices)
            or (type(step) is int and len(choices) != step)):
        issues.append('invalid salvage decision progress')
    if isinstance(choices, list):
        legal_choices = ({'brace', 'pad', 'brush'}, {'unfasten', 'strip', 'sort', 'crush', 'carve', 'clean'})
        if any(index >= len(legal_choices) or not isinstance(choice, str) or choice not in legal_choices[index]
               for index, choice in enumerate(choices)):
            issues.append('invalid persisted salvage action')
    phase = session.get('phase')
    if phase not in ('inspection', 'disassembly') or (phase == 'inspection' and (step != 0 or score != 0)):
        issues.append('invalid salvage session phase')
    challenges = session.get('challenges')
    if not isinstance(challenges, list) or len(challenges) != 3 or any(type(v) is not int or not 0 <= v <= 2 for v in challenges):
        issues.append('invalid salvage inspection challenges')
    for key, maximum in (('skill_level', 10), ('tool_bonus', 12)):
        if type(session.get(key)) is not int or not 0 <= session[key] <= maximum:
            issues.append(f'invalid salvage session {key}')
    return issues


def _validate_salvaging(raw: dict[str, Any]) -> list[str]:
    issues = []
    skills = raw.get('player_skills', {})
    level = skills.get('salvaging', 0) if isinstance(skills, dict) else 0
    if type(level) is not int or not 0 <= level <= 10:
        issues.append('salvaging skill out of bounds')
        level = 0
    xp = raw.get('player_salvaging_xp', 0)
    if type(xp) is not int or not 0 <= xp < 24 + level * 14:
        issues.append('salvaging practice out of bounds')
    attempts = raw.get('salvaging_attempts', 0)
    if type(attempts) is not int or not 0 <= attempts <= 1_000_000_000:
        issues.append('salvaging attempt count out of bounds')
    issues.extend(validate_salvage_session(raw.get('player_salvage_session', {}), attempts))
    rows = raw.get('player_salvage_log', [])
    if not isinstance(rows, list) or len(rows) > 80:
        issues.append('invalid salvage result log')
        return issues
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            issues.append('invalid salvage result record')
            continue
        attempt = row.get('attempt')
        if type(attempt) is not int or type(attempts) is not int or not 0 <= attempt < attempts or attempt in seen:
            issues.append('invalid or duplicate completed salvage attempt')
        if type(attempt) is int:
            seen.add(attempt)
        score = row.get('score')
        if type(score) is not int or not 0 <= score <= 6 or score % 2 or row.get('max_score') != 6:
            issues.append('invalid salvage result score')
        for key in ('outputs', 'rare_outputs'):
            drops = row.get(key)
            if (not isinstance(drops, dict) or (key == 'outputs' and not drops)
                    or any(not isinstance(iid, str) or ':' not in iid or type(amount) is not int or not 1 <= amount <= 1000
                           for iid, amount in (drops.items() if isinstance(drops, dict) else []))):
                issues.append(f'invalid salvage result {key}')
        if isinstance(row.get('outputs'), dict) and isinstance(row.get('rare_outputs'), dict):
            if any(row['outputs'].get(iid) != amount for iid, amount in row['rare_outputs'].items()):
                issues.append('rare salvage drops disagree with total outputs')
        if type(row.get('completed_minute')) is not int or row['completed_minute'] < 0:
            issues.append('invalid salvage completion time')
    session = raw.get('player_salvage_session', {})
    if isinstance(session, dict) and session and type(session.get('attempt')) is int and session['attempt'] in seen:
        issues.append('salvage attempt is both active and completed')
    return issues


def validate_sim_state(raw: dict[str, Any] | None) -> list[str]:
    if not raw:
        return []
    issues: list[str] = []
    issues.extend(_validate_interiors(raw))
    issues.extend(_validate_salvaging(raw))
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
    journal = raw.get('player_crafting_log', [])
    if not isinstance(journal, list) or len(journal) > 80:
        issues.append('invalid crafting discovery history')
    else:
        learned = raw.get('player_discovered_recipes', [])
        if not isinstance(learned, list):learned=[]
        for entry in journal:
            if not isinstance(entry, dict):
                issues.append('invalid crafting discovery history entry')
                continue
            rid = entry.get('recipe_id')
            samples = entry.get('ingredients')
            minute = entry.get('minute')
            if (not isinstance(rid, str) or rid not in learned
                    or not isinstance(minute, int) or minute < 0
                    or not isinstance(samples, list) or not 1 <= len(samples) <= 5
                    or any(not isinstance(iid, str) for iid in samples)):
                issues.append('invalid crafting discovery history entry')
    settlements = _table(raw, "settlements")
    introduced=raw.get('introduced_npcs',[]) or []
    if not isinstance(introduced,list) or any(not isinstance(uid,str) for uid in introduced):
        issues.append('invalid NPC introduction list')
    else:
        if len(introduced)!=len(set(introduced)):issues.append('duplicate NPC introductions')
        known=raw.get('discovered_npcs',[]) or []
        if isinstance(known,list) and any(uid not in known for uid in introduced):
            issues.append('introduced NPC identity is not discovered')
    npcs = _table(raw, "npcs")
    factions = _table(raw, "factions")
    monuments = _table(raw, "claim_monuments")
    territory = _table(raw, "territory_control")
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
        portrait_version = row.get("portrait_version", 1)
        if type(portrait_version) is not int or portrait_version not in (1, 2):
            issues.append(f"invalid NPC portrait version: {uid}")
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
        inventory = row.get("inventory", {})
        valid_inventory = isinstance(inventory, dict) and all(
            isinstance(iid, str) and ":" in iid and not any(c.isspace() for c in iid)
            and type(qty) is int and qty >= 0
            for iid, qty in inventory.items()
        )
        if not valid_inventory:
            issues.append(f"invalid NPC inventory: {uid}")
        equipment = row.get("equipment", {})
        if not isinstance(equipment, dict) or any(
            slot not in {"hand", "head", "body", "hands", "legs", "offhand"}
            or not isinstance(iid, str)
            for slot, iid in (equipment.items() if isinstance(equipment, dict) else ())
        ):
            issues.append(f"invalid NPC equipment: {uid}")
        elif valid_inventory and any(
            int(inventory.get(iid, 0)) < count for iid, count in Counter(equipment.values()).items()
        ):
            issues.append(f"NPC equipment exceeds carried inventory: {uid}")

    carried_deliveries = Counter()
    for uid, row in _table(raw, 'household_deliveries').items():
        physical = row.get('physical_cargo', False)
        if type(physical) is not bool:
            issues.append(f'invalid household cargo mode: {uid}')
        if physical and row.get('status') == 'carried':
            quantity = row.get('quantity', 0)
            if type(quantity) is not int or quantity < 0:
                issues.append(f'invalid household cargo quantity: {uid}')
            else:
                carried_deliveries[(row.get('carrier_uid', ''), row.get('item_id', ''))] += quantity
    for (carrier, item), quantity in carried_deliveries.items():
        inventory = npcs.get(carrier, {}).get('inventory', {})
        if not isinstance(inventory, dict) or not isinstance(inventory.get(item, 0), int) or inventory.get(item, 0) < quantity:
            issues.append(f'household delivery exceeds carried inventory: {carrier}:{item}')

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

    for uid, row in monuments.items():
        for key in ("integrity", "garrison_strength", "supply_level", "capture_progress"):
            if not 0 <= int(row.get(key, 0)) <= 100:
                issues.append(f"claim monument {key} out of bounds: {uid}")
        controller = str(row.get("controller_faction_id", ""))
        claimant = str(row.get("claimant_faction_id", ""))
        if controller and controller not in factions:
            issues.append(f"orphan claim monument controller: {uid}->{controller}")
        if claimant and claimant not in factions:
            issues.append(f"orphan claim monument claimant: {uid}->{claimant}")
        if int(row.get("max_reach", 0)) not in range(1, 9):
            issues.append(f"claim monument reach out of bounds: {uid}")

    for token, row in territory.items():
        try:
            rx, ry = str(token).split(",", 1); int(rx); int(ry)
        except Exception:
            issues.append(f"invalid territory region key: {token!r}")
        for key in ("control_strength", "rival_strength"):
            if not 0 <= int(row.get(key, 0)) <= 100:
                issues.append(f"territory {key} out of bounds: {token}")
        for key in ("controller_faction_id", "rival_faction_id"):
            faction = str(row.get(key, ""))
            if faction and faction not in factions:
                issues.append(f"orphan territory faction: {token}->{faction}")

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
