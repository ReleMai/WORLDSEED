"""Three deterministic, interactive salvage tabletop puzzles.

A project is a serialized record of components and their changing condition.
Mouse/keyboard selections are commands, not client-owned gameplay state.
No RNG is consumed when opening a panel or inspecting a saved puzzle.
"""
from __future__ import annotations

from worldseed.core.rng import hash_u64
from worldseed.systems.salvage_perks import has

GAME_NAMES = {
    "disassembly": "THE DISASSEMBLY BENCH",
    "fracture": "FRACTURE & EXTRACTION",
    "recovery": "THE MATERIAL RECOVERY TABLE",
}
GAME_DESCRIPTIONS = {
    "disassembly": "Release supporting joints before their dependents. Match each fastening to a careful tool.",
    "fracture": "Read faults and hardness. Choose impact force for each section without crushing valuable pieces.",
    "recovery": "Separate textile layers in order. Clean or unpick each material without destroying its useful form.",
}
OPERATIONS = {
    "disassembly": (
        ("unfasten", "Unfasten", "Ease a joined fitting loose."),
        ("wedge", "Wedge", "Spread a tight wooden or metal seam."),
        ("cut", "Cut binding", "Cut a strap or stubborn lashing."),
    ),
    "fracture": (
        ("tap", "Light tap", "Preserve brittle edges and fine inclusions."),
        ("wedge", "Place wedge", "Follow an existing fracture seam."),
        ("strike", "Firm strike", "Break a particularly dense section."),
    ),
    "recovery": (
        ("unpick", "Unpick stitches", "Recover intact thread and seams."),
        ("wash", "Wash gently", "Clear packed dirt and deposits."),
        ("dry", "Dry and brush", "Stabilize a damp organic layer."),
        ("cut", "Cut free", "Separate a torn, hopelessly tangled area."),
    ),
}
# (label, public visual clue, correct tool, hidden condition, value)
TEMPLATES = {
    "disassembly": (
        ("Loose peg joint", "A wooden pin holds this joint together.", "unfasten", "free pin", False),
        ("Wedge-tight mortise", "The grain separates along a thin fitted seam.", "wedge", "tight join", True),
        ("Wrapped binding", "A dark cord lies beneath the outer frame.", "cut", "concealed knot", False),
        ("Bolted support", "Fastener heads hold a load-bearing support.", "unfasten", "heavy fitting", True),
        ("Splintered bracket", "The bracket is already cracked along one edge.", "wedge", "fragile support", True),
        ("Fiber-lashed handle", "Fibers bind the fitted handle to the shaft.", "cut", "lashings", False),
    ),
    "fracture": (
        ("Fine glass-like edge", "Hairline faults spider across a thin surface.", "tap", "brittle", True),
        ("Natural fault line", "A continuous seam crosses the section.", "wedge", "seamed", True),
        ("Dense mineral core", "This region is compact and resists light pressure.", "strike", "hard", True),
        ("Porous inclusion", "The inclusion looks chalky and easily pulverized.", "tap", "porous", True),
        ("Split stone plate", "Two layers are already separated at the edge.", "wedge", "laminated", False),
        ("Hard ceramic heel", "A thick uncracked area resists the chisel.", "strike", "dense", False),
    ),
    "recovery": (
        ("Worn stitches", "Tiny stitches cross an otherwise intact seam.", "unpick", "fine thread", True),
        ("Dirty outer panel", "Caked debris obscures the useful surface.", "wash", "soiled", True),
        ("Damp fiber coil", "The wound fibers are damp but not broken.", "dry", "damp", True),
        ("Tangled scrap edge", "The edge is too tangled to release by hand.", "cut", "knotted", False),
        ("Buckled stitching", "The material puckers at a long sewn seam.", "unpick", "sewn", True),
        ("Dusty inner fabric", "Fine grit coats a salvageable textile layer.", "wash", "gritty", True),
    ),
}

def profile_for(method: str) -> str:
    if method in ("crush",):
        return "fracture"
    if method in ("strip", "clean"):
        return "recovery"
    return "disassembly"

def create_project(definition, item_id: str, attempt: int, seed: bytes, minute: int,
                   level: int, tool_bonus: int, state) -> dict:
    game = profile_for(definition.method)
    options = TEMPLATES[game]
    start = hash_u64(seed, "salvage.tabletop.v2", attempt, item_id, game) % len(options)
    count = 4 if definition.difficulty <= 5 else 5
    nodes = []
    for index in range(count):
        label, clue, ideal, condition, valuable = options[(start + index) % len(options)]
        # A support graph: the second and last elements need preceding work.
        depends = index - 1 if index in (1, count - 1) else -1
        nodes.append({
            "label": label, "clue": clue, "ideal": ideal,
            "condition": condition, "valuable": valuable, "depends": depends,
            "done": False, "grade": 0, "surveyed": False, "operation": "",
            "damage": 0, "splash": 0,
        })
    return {
        "version": 2, "item_id": item_id, "definition_id": definition.id,
        "attempt": attempt, "started_minute": max(0, minute),
        "phase": "inspection", "step": 0, "game": game,
        "nodes": nodes, "selected": 0, "score": 0, "stress": 0,
        "mistakes": 0, "skill_level": level, "tool_bonus": tool_bonus,
        "stabilized": False, "undone": False, "history": [],
        "priority": "", "minutes_spent": 0,
        "reveal_first": has(state, "seam_sense"),
    }

def _selectable(project: dict, index: int) -> bool:
    nodes = project["nodes"]
    if not 0 <= index < len(nodes) or nodes[index]["done"]:
        return False
    parent = nodes[index]["depends"]
    return parent < 0 or nodes[parent]["done"]

def quality(project: dict) -> int:
    nodes = project["nodes"]
    if not nodes:
        return 0
    average = sum(node["grade"] for node in nodes) // len(nodes)
    return max(0, min(100, average - project["stress"] // 5))

def view(project: dict, name: str, state, definition=None) -> dict:
    game = project["game"]
    nodes = project["nodes"]
    active = project["selected"]
    count_done = sum(int(n["done"]) for n in nodes)
    row = nodes[active]
    revealed = row["surveyed"] or (active == 0 and project.get("reveal_first"))
    available = _selectable(project, active)
    displayed = [
        {"id": index, "label": n["label"], "clue": n["clue"],
         "done": n["done"], "locked": not _selectable(project, index) and not n["done"],
         "selected": index == active, "valuable": n["valuable"],
         "grade": n["grade"] if n["done"] else None,
         "damage": n["damage"],
         "ideal": n["ideal"] if (n["surveyed"] or index == 0 and project.get("reveal_first")) else ""}
        for index, n in enumerate(nodes)
    ]
    actions = [
        {"id": "work:" + key, "label": label, "description": description}
        for key, label, description in OPERATIONS[game]
    ] if project["phase"] == "work" and available else []
    return {
        "version": 2, "item_id": project["item_id"], "name": name,
        "game": game, "game_title": GAME_NAMES[game], "game_description": GAME_DESCRIPTIONS[game],
        "phase": project["phase"], "step": count_done, "stage_count": len(nodes),
        "score": quality(project), "max_score": 100, "stress": project["stress"],
        "nodes": displayed, "selected_node": active,
        "prompt": "Inspect the source" if project["phase"] == "inspection" else row["label"],
        "cue": GAME_DESCRIPTIONS[game] if project["phase"] == "inspection" else row["clue"] + ("  Best tool: " + row["ideal"] + "." if revealed else ""),
        "choices": ([{"id": "inspect", "label": "Begin inspection", "description": "Expose material layers and work surfaces."}]
                    if project["phase"] == "inspection" else actions),
        "can_survey": project["phase"] == "work" and available and not row["surveyed"],
        "can_stabilize": project["phase"] == "work" and has(state, "steady_hands") and not project["stabilized"] and project["stress"] > 0,
        "can_undo": project["phase"] == "work" and has(state, "gentle_undo") and not project["undone"] and bool(project["history"]),
        "priority": project["priority"],
        "can_prioritize": has(state, "targeted_search") and project["phase"] == "work",
        "possible_outputs": list(sorted(definition.yields)) + [drop.item_id for drop in definition.rare_yields] if definition else [],
    }

def play(project: dict, choice: str, state) -> tuple[bool, str, int, bool]:
    """Apply one authorized tabletop action; caller owns item transfer on completion."""
    if project["phase"] == "inspection":
        if choice != "inspect":
            return False, "Inspect the object before beginning work.", 0, False
        project["phase"] = "work"
        return True, GAME_DESCRIPTIONS[project["game"]], 1, False
    if project["phase"] != "work":
        return False, "This project is no longer active.", 0, False
    nodes = project["nodes"]
    if choice.startswith("select:"):
        try:
            index = int(choice.split(":", 1)[1])
        except (TypeError, ValueError):
            return False, "Invalid salvage component.", 0, False
        if not 0 <= index < len(nodes):
            return False, "That component is not part of the object.", 0, False
        project["selected"] = index
        return True, nodes[index]["clue"], 0, False
    if choice == "stabilize":
        if not has(state, "steady_hands") or project["stabilized"] or project["stress"] <= 0:
            return False, "Stabilization is unavailable.", 0, False
        project["stress"] = max(0, project["stress"] - 20)
        project["stabilized"] = True
        return True, "You brace the work and ease accumulated strain.", 2, False
    if choice == "undo":
        if not has(state, "gentle_undo") or project["undone"] or not project["history"]:
            return False, "No damaged operation can be corrected.", 0, False
        index = project["history"].pop()
        node = nodes[index]
        if not node["done"] or node["grade"] >= 100:
            return False, "Only the last imperfect operation can be corrected.", 0, False
        node["done"], node["grade"], node["operation"] = False, 0, ""
        if node["splash"] and index + 1 < len(nodes):
            nodes[index + 1]["damage"] = max(0, nodes[index + 1]["damage"] - node["splash"])
        node["splash"] = 0
        project["step"] -= 1
        project["stress"] = max(0, project["stress"] - 8)
        project["undone"] = True
        project["selected"] = index
        return True, "You reopen the damaged join, though some strain remains.", 3, False
    if choice.startswith("prioritize:"):
        if not has(state, "targeted_search"):
            return False, "Targeted Search is not unlocked.", 0, False
        # Caller verifies this target against the authored loot table before play().
        iid = choice.split(":", 1)[1]
        if not iid:
            return False, "Choose an actual recoverable component.", 0, False
        project["priority"] = iid
        return True, "You mark that material as your recovery priority.", 0, False
    selected = project["selected"]
    if not _selectable(project, selected):
        return False, "Release the supporting component first.", 0, False
    node = nodes[selected]
    if choice == "survey":
        if node["surveyed"]:
            return False, "This component is already surveyed.", 0, False
        node["surveyed"] = True
        return True, "Inspection reveals a " + node["condition"] + "; use " + node["ideal"] + ".", 1, False
    if not choice.startswith("work:"):
        return False, "Choose a recovery technique for the selected component.", 0, False
    operation = choice.split(":", 1)[1]
    allowed = {entry[0] for entry in OPERATIONS[project["game"]]}
    if operation not in allowed:
        return False, "That tool cannot be used at this table.", 0, False
    ideal = operation == node["ideal"]
    # The wrong tool may still work, but damaging brittle or valuable material
    # is deliberately much less productive than reading its visible cues.
    grade = max(15, (100 if ideal else 55 if node["surveyed"] else 35) - node["damage"])
    damage = 0 if ideal else 12 if node["valuable"] else 8
    # Fracture shocks can spoil nearby mineral sections, while tearing
    # a recovery layer frays the fibers directly underneath it.
    # Mechanical disassembly concentrates stress in connections instead.
    if not ideal and selected + 1 < len(nodes):
        adjacent = nodes[selected+1]
        if not adjacent["done"] and project["game"] in ("fracture", "recovery"):
            spread = 18 if project["game"] == "fracture" and operation == "strike" else (
                12 if project["game"] == "recovery" and operation == "cut" else 6)
            adjacent["damage"] = min(50, adjacent["damage"] + spread)
            node["splash"] = spread
    if project["game"] == "disassembly" and not ideal and node["valuable"]:
        damage += 6
    node["done"], node["grade"], node["operation"] = True, grade, operation
    project["stress"] = min(100, project["stress"] + damage)
    project["mistakes"] += int(not ideal)
    project["step"] += 1
    if not ideal:
        project["history"].append(selected)
    completed = project["step"] == len(nodes)
    project["score"] = quality(project)
    duration = 2 + (1 if project["game"] == "disassembly" else 0)
    project["minutes_spent"] = min(40, project["minutes_spent"] + duration)
    detail = ("A clean separation preserves this component." if ideal
              else "The tool damages a recoverable surface; some fragments remain useful.")
    return True, detail, duration, completed
