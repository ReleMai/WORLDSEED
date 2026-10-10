from __future__ import annotations

import argparse
from collections import Counter
import gc
import tempfile
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worldseed.app import _load_context
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory, Position
from worldseed.sim.commands import BuildCommand, CookMealCommand, CraftCommand, DiscoveryPotCommand, EatMealCommand
from worldseed.systems.state import CarcassState, pos_key
from worldseed.ui.startup import StartSelection


def _build_profile() -> dict:
    return {
        "attributes": {"strength": 5, "agility": 5, "endurance": 5, "intellect": 5, "perception": 5, "will": 5},
        "skills": {
            "athletics": 0, "survival": 3, "foraging": 4, "woodcutting": 3,
            "mining": 0, "hunting": 5, "melee": 0, "crafting": 4,
            "medicine": 0, "scholarship": 0, "persuasion": 0, "trading": 0,
            "naturalism": 0, "arcana": 0,
        },
        "talents": [],
    }


def _resource_positions(sim, item_id: str, radius: int = 20) -> list[WorldPos]:
    p = sim.player_pos
    rows = []
    for y in range(p.y - radius, p.y + radius + 1):
        for x in range(p.x - radius, p.x + radius + 1):
            q = WorldPos(x, y, p.z)
            fv = sim.resources.feature_at(q)
            if not fv or fv.stage != "mature":
                continue
            rdef = sim.registry.resources.get(fv.feature_id)
            if not rdef or rdef.required_tool_tag or item_id not in rdef.yields:
                continue
            rows.append((abs(x - p.x) + abs(y - p.y), x, y, q))
    return [r[-1] for r in sorted(rows)]


def _collect(sim, inv: Inventory, item_id: str, quantity: int, radius: int = 20) -> None:
    for q in _resource_positions(sim, item_id, radius):
        if inv.count(item_id) >= quantity:
            return
        sim.resources.harvest(q, inv, sim.clock.minute)
        sim.crafting.sync_discoveries(inv)
    if inv.count(item_id) < quantity:
        raise AssertionError(f"bootstrap landscape could not supply {quantity} {item_id}; got {inv.count(item_id)}")


_PRIMITIVE_PRODUCERS = {
    "core:stone_flake": "core:stone_flake",
    "core:plant_cordage": "core:plant_cordage",
}


def _supply(sim, actor: int, costs: dict[str, int]) -> None:
    """Replace consumed experiments through harvest and primitive production.

    Discovery spends its experiment ingredients. The bootstrap must pay that
    cost from the same landscape as the final equipment, without granting
    supplies or silently unlocking the desired recipe.
    """
    inv = sim.entities.get(actor, Inventory)
    for item_id, quantity in sorted(costs.items()):
        if inv.count(item_id) >= quantity:
            continue
        producer_id = _PRIMITIVE_PRODUCERS.get(item_id)
        if producer_id:
            producer = sim.registry.recipes[producer_id]
            batch_size = producer.outputs[item_id]
            batches = (quantity - inv.count(item_id) + batch_size - 1) // batch_size
            _craft(sim, actor, producer_id, batches)
        else:
            _collect(sim, inv, item_id, quantity)


def _learn(sim, actor: int, recipe_id: str) -> None:
    if sim.crafting.recipe_is_discovered(recipe_id):
        return
    recipe = sim.registry.recipes[recipe_id]
    signature = tuple(sim.crafting.discovery_signature(recipe))
    costs = dict(Counter(signature))
    inv = sim.entities.get(actor, Inventory)
    _supply(sim, actor, costs)
    candidates = sim.crafting.pot_candidates(signature, inv)
    if recipe_id not in {row.id for row in candidates}:
        raise AssertionError(f"bootstrap recipe {recipe_id} has no legal experiment")
    # Every successful mix learns exactly one previously unknown candidate.
    # Therefore the original candidate count bounds the work, even when the
    # named target is not the first deterministic discovery.
    for _ in range(len(candidates)):
        _supply(sim, actor, costs)
        before = set(sim.state.player_discovered_recipes)
        sim.execute(DiscoveryPotCommand(actor, signature))
        if not set(sim.state.player_discovered_recipes) - before:
            raise AssertionError(f"bootstrap experiment for {recipe_id} failed: {sim.log[-1].message if sim.log else 'no message'}")
        if sim.crafting.recipe_is_discovered(recipe_id):
            return
    raise AssertionError(f"bootstrap recipe {recipe_id} was not learned within its candidate bound")


def _craft(sim, actor: int, recipe_id: str, times: int = 1) -> None:
    _learn(sim, actor, recipe_id)
    for _ in range(times):
        _supply(sim, actor, sim.registry.recipes[recipe_id].inputs)
        before = len(sim.log)
        sim.execute(CraftCommand(actor, recipe_id))
        if len(sim.log) == before or "complete" not in sim.log[-1].message.lower():
            raise AssertionError(f"failed to craft {recipe_id}: {sim.log[-1].message if sim.log else 'no message'}")


def run_bootstrap(seed_text: str = "rc7-bootstrap") -> dict:
    seed = seed_text.encode("utf-8")
    with tempfile.TemporaryDirectory() as td:
        selection = StartSelection(Path(td) / "bootstrap.db", True, "Bootstrap", seed.hex(), "Tester", "custom", _build_profile())
        ctx = _load_context(selection,prepare_world=False)
        try:
            sim = ctx.sim
            inv = ctx.entities.get(ctx.player_id, Inventory)
            if inv.items:
                raise AssertionError(f"new character did not start empty: {inv.items}")

            # The start scorer should make a true primitive bootstrap possible without granting supplies.
            _collect(sim, inv, "core:stone", 10)
            _collect(sim, inv, "core:stout_branch", 10)
            _collect(sim, inv, "core:brush", 14)

            _craft(sim, ctx.player_id, "core:stone_flake", 2)
            _craft(sim, ctx.player_id, "core:plant_cordage", 4)
            _craft(sim, ctx.player_id, "core:stone_knife")
            _craft(sim, ctx.player_id, "core:stone_axe")
            _craft(sim, ctx.player_id, "core:sling")
            _craft(sim, ctx.player_id, "core:sling_stone", 2)

            # Establish fire from the same natural resource pool.
            p = sim.player_pos
            camp = next((p.moved(dx, dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                         if sim.world.is_passable(p.moved(dx, dy)) and not sim.resources.blocks_movement(p.moved(dx, dy))
                         and sim.building.structure_at(p.moved(dx, dy)) is None), None)
            if camp is None:
                raise AssertionError("no adjacent tile available for primitive campfire")
            dx, dy = camp.x - p.x, camp.y - p.y
            _supply(sim, ctx.player_id, sim.registry.structures["core:campfire"].cost)
            sim.execute(BuildCommand(ctx.player_id, "core:campfire", dx, dy))
            if sim.building.structure_at(camp) is None:
                raise AssertionError(f"campfire construction failed: {sim.log[-1].message if sim.log else 'no message'}")

            # An axe must make the next tier (timber/bark) available from the landscape.
            tree = None
            for y in range(p.y - 30, p.y + 31):
                for x in range(p.x - 30, p.x + 31):
                    q = WorldPos(x, y, 0)
                    fv = sim.resources.feature_at(q)
                    if fv and fv.stage == "mature" and "tree" in sim.registry.resources[fv.feature_id].tags:
                        tree = q
                        break
                if tree:
                    break
            if tree is None:
                raise AssertionError("no tree found within bootstrap search radius")
            ok, msg, _, _ = sim.resources.harvest(tree, inv, sim.clock.minute)
            if not ok or inv.count("core:wood") <= 0:
                raise AssertionError(f"stone axe did not unlock timber: {msg}")

            # Validate the hunt -> carcass -> field processing chain using a real species profile.
            rabbit = sim.registry.species["core:rabbit"]
            carcass = CarcassState("bootstrap-carcass", rabbit.id, p.x, p.y, p.z, sim.clock.minute, 90)
            sim.state.carcasses[carcass.uid] = carcass
            for action in ("skin", "butcher", "debone"):
                ok, msg, _ = sim.processing.process_carcass(carcass.uid, action, inv, sim.player_skill("hunting"), sim.clock.minute)
                if not ok:
                    raise AssertionError(f"carcass {action} failed: {msg}")

            meat_id = "core:raw_small_game" if inv.count("core:raw_small_game") else "core:raw_game_meat"
            if inv.count(meat_id) <= 0:
                raise AssertionError("butchery produced no cookable meat")
            sim.execute(CookMealCommand(ctx.player_id, "core:roast", (meat_id,)))
            if not sim.state.prepared_meals:
                raise AssertionError("dynamic cooking created no prepared meal")
            meal_uid = next(iter(sim.state.prepared_meals))
            from worldseed.sim.commands import EatMealCommand
            sim.execute(EatMealCommand(ctx.player_id, meal_uid))
            if not sim.state.player_diet_history:
                raise AssertionError("eating prepared meal did not update diet history")

            return {
                "spawn": (p.x, p.y, p.z),
                "inventory_items": sum(inv.items.values()),
                "wood": inv.count("core:wood"),
                "hide": inv.count("core:fresh_hide"),
                "bone": inv.count("core:bone"),
                "diet_events": len(sim.state.player_diet_history),
                "campfire": True,
                "empty_start": True,
            }
        finally:
            ctx.db.close();del ctx;gc.collect()


def main() -> int:
    parser = argparse.ArgumentParser(description="WORLDSEED zero-item early-game bootstrap smoke test")
    parser.add_argument("--seeds", type=int, default=5)
    args = parser.parse_args()
    for i in range(args.seeds):
        result = run_bootstrap(f"rc7-bootstrap-{i}")
        print(f"seed {i}: PASS {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
