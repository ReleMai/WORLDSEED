"""Conversation facts observe existing state and never activate the world."""
from __future__ import annotations

import copy
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.clock import GameClock
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Identity, Inventory, Position, Vitals
from worldseed.entities.store import EntityStore
from worldseed.systems.dialogue_context import MAX_COLLECTION_FACTS, MAX_MEMORY_FACTS, build_dialogue_facts
from worldseed.systems.economy import EconomySystem
from worldseed.systems.environment import EnvironmentSystem
from worldseed.systems.generation import ProceduralSocietyGenerator
from worldseed.systems.history import HistorySystem
from worldseed.systems.state import FactionState, HouseholdState, LivingWorldState, NPCState, SettlementState


class LookupOnlyDict(dict):
    """Global ledgers may be looked up, but cannot be enumerated by chat."""
    def __iter__(self):
        raise AssertionError("global ledger scan")

    def items(self):
        raise AssertionError("global ledger scan")

    def values(self):
        raise AssertionError("global ledger scan")


class DialogueContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)

    def fixture(self):
        state = LivingWorldState(clock_minute=601, player_name="Mara")
        town = SettlementState("settlement:test", "Ash Vale", 0, 0, 10, 20, 80, "", "", "faction:test",
                               wealth=9000, housing_capacity=70, food_stress=55, sanitation=20)
        town.stocks = {"core:bread": 4, "core:wood": 32}
        state.settlements[town.uid] = town
        state.factions[town.faction_id] = FactionState(town.faction_id, "The Vale", "", at_war=["faction:enemy"])
        npc = NPCState("npc:test", "Tomas", 38, "merchant", ["patient", "suspicious"], 10, 20, 0,
                       town.uid, town.faction_id, wealth=700, skills={"trading": 7},
                       needs={"social": 48, "security": 62}, children=["npc:child"])
        npc.relationships["player"] = {"trust": 12, "affection": 8, "familiarity": 20}
        npc.memories = [{"type": "gift", "subject": "player", "minute": 570, "valence": 8}]
        state.npcs[npc.uid] = npc
        state.introduced_npcs.append(npc.uid)
        state.player_crime_heat[town.uid] = 51
        state.player_bounties[town.uid] = 22
        entities = EntityStore()
        entities.spawn(preferred_id=1)
        entities.add(1, Position(WorldPos(10, 20, 0)))
        entities.add(1, Inventory({"core:copper_coin": 17, "core:bread": 2}))
        entities.add(1, Vitals(hp=28, hunger=80, stamina=12))
        history = HistorySystem(state)
        sim = SimpleNamespace(
            state=state, clock=GameClock(state.clock_minute), entities=entities, player_id=1,
            economy=EconomySystem(state, self.registry, b"chat-facts", history),
            environment=EnvironmentSystem(state, self.registry, b"chat-facts", history),
        )
        ctx = SimpleNamespace(sim=sim, entities=entities, player_id=1)
        return ctx, npc, town

    def test_currency_source_is_carried_copper_not_npc_town_or_item_value(self):
        ctx, npc, town = self.fixture()
        before = ctx.sim.state.to_dict()
        inv = ctx.entities.get(1, Inventory)
        inventory_before = copy.deepcopy(inv.items)
        facts = build_dialogue_facts(ctx, npc)
        self.assertEqual(facts["player.wealth"], 17)
        self.assertEqual(facts["npc.wealth"], 700)
        self.assertEqual(facts["town.wealth"], 9000)
        self.assertEqual(facts["town.currency_id"], "")
        self.assertEqual(facts["player.inventory.core:bread"], 2)
        self.assertEqual(facts["town.buy_prices.core:bread"], ctx.sim.economy.trade_price(town.uid, "core:bread", True))
        self.assertFalse(facts["player.afford.core:bread"])
        self.assertEqual(ctx.sim.state.to_dict(), before)
        self.assertEqual(inv.items, inventory_before)
        inv.items.pop("core:copper_coin")
        self.assertEqual(build_dialogue_facts(ctx, npc)["player.wealth"], 0)

    def test_player_npc_town_and_faction_conditions_are_independent(self):
        ctx, npc, town = self.fixture()
        facts = build_dialogue_facts(ctx, npc)
        self.assertTrue(facts["player.hurt"])
        self.assertTrue(facts["player.hungry"])
        self.assertTrue(facts["player.exhausted"])
        self.assertTrue(facts["player.wanted"])
        self.assertEqual(facts["player.notoriety"], 51)
        self.assertEqual(facts["player.bounty"], 22)
        self.assertEqual(facts["npc.skills.trading"], 7)
        self.assertEqual(facts["comparison.skills.trading"], -7)
        self.assertEqual(facts["relationship.trust"], 12)
        self.assertEqual(facts["npc.family_count"], 1)
        self.assertEqual(facts["npc.memories.player_valence"], 8)
        self.assertTrue(facts["npc.traits.suspicious"])
        self.assertFalse(facts["npc.traits.greedy"])
        self.assertTrue(facts["town.stressed"])
        self.assertTrue(facts["town.housing_shortage"])
        self.assertTrue(facts["town.unsanitary"])
        self.assertTrue(facts["faction.at_war"])
        self.assertEqual(facts["faction.war_count"], 1)

    def test_environment_uses_current_authoritative_weather_time_and_presence(self):
        ctx, npc, _ = self.fixture()
        ctx.sim.environment.weather = SimpleNamespace(at=Mock(return_value={"kind": "storm", "rain": 8, "wetness": 90, "fog": 35}))
        ctx.entities.get(1, Position).value = WorldPos(10, 20, -2)
        ctx.sim.clock.minute = 90 * 1440 + 23 * 60
        ctx.sim.state.interior_actors["player"] = SimpleNamespace(space_id="interior:home")
        ctx.sim.state.interiors["interior:home"] = SimpleNamespace(function="residence", floor_index=1)
        facts = build_dialogue_facts(ctx, npc)
        ctx.sim.environment.weather.at.assert_called_once_with(ctx.sim.clock.minute, 10, 20)
        self.assertEqual(facts["environment.weather"], "storm")
        self.assertEqual(facts["environment.season"], "winter")
        self.assertEqual(facts["environment.phase"], "night")
        self.assertTrue(facts["environment.indoors"])
        self.assertTrue(facts["environment.underground"])
        self.assertFalse(facts["environment.exposed"])
        self.assertEqual(facts["environment.interior_function"], "residence")
        self.assertEqual(facts["environment.interior_floor"], 1)

    def test_current_task_household_and_shared_culture_are_existing_bindings(self):
        ctx, npc, _ = self.fixture()
        npc.family_uid = "household:test"
        npc.culture_id = "culture:test"
        npc.tasks = [{"kind": "perform", "action": "drink"}]
        ctx.entities.add(1, Identity("Mara", culture_id=npc.culture_id))
        ctx.sim.state.households[npc.family_uid] = HouseholdState(
            npc.family_uid, npc.settlement_id, member_uids=[npc.uid], hardship_score=67,
            days_short=3, unmet_needs={"core:soap": 2})
        facts = build_dialogue_facts(ctx, npc)
        self.assertTrue(facts["comparison.same_culture"])
        self.assertEqual(facts["npc.urgent_need"], "security")
        self.assertEqual(facts["npc.task_action"], "drink")
        self.assertEqual(facts["household.hardship_score"], 67)
        self.assertEqual(facts["household.unmet_needs.core:soap"], 2)
        self.assertEqual(facts["household.member_count"], 1)

    def test_minimal_context_defaults_are_safe_and_explicitly_unavailable(self):
        npc = SimpleNamespace(uid="npc:minimal")
        ctx = SimpleNamespace(sim=SimpleNamespace(state=SimpleNamespace(player_wealth=999999)))
        facts = build_dialogue_facts(ctx, npc)
        self.assertFalse(facts["player.vitals_available"])
        self.assertFalse(facts["player.inventory_available"])
        self.assertFalse(facts["environment.weather_available"])
        self.assertFalse(facts["town.quotes_available"])
        self.assertFalse(facts["player.hurt"])
        self.assertEqual(facts["player.wealth"], 0)
        self.assertEqual(facts["npc.occupation"], "villager")
        self.assertTrue(all(isinstance(value, (str, int, float, bool)) or value is None for value in facts.values()))

    def test_stranger_does_not_read_any_private_npc_attributes(self):
        class Stranger:
            uid = "npc:stranger"

            def __getattr__(self, name):
                raise AssertionError("private stranger field read: " + name)

        ctx, _, _ = self.fixture()
        ctx.sim.state.introduced_npcs.clear()
        facts = build_dialogue_facts(ctx, Stranger())
        self.assertFalse(facts["npc.introduced"])
        self.assertEqual([key for key in facts if key.startswith("npc.")], ["npc.introduced"])
        self.assertFalse(any(key.startswith(("relationship.", "town.", "faction.")) for key in facts))

    def test_no_world_generation_global_npc_route_or_settlement_scans(self):
        ctx, npc, _ = self.fixture()
        state = ctx.sim.state
        state.npcs = LookupOnlyDict({npc.uid: npc})
        state.settlements = LookupOnlyDict(state.settlements)
        state.factions = LookupOnlyDict(state.factions)
        state.trade_routes = LookupOnlyDict({"route:1": object()})
        ctx.sim.world = Mock()
        ctx.sim.world.get_tile.side_effect = AssertionError("chunk load")
        ctx.sim.world.generator.generate_chunk.side_effect = AssertionError("generation")
        ctx.sim.realize_regions = Mock(side_effect=AssertionError("realization"))
        ctx.sim.economy.ensure_currency = Mock(side_effect=AssertionError("currency mutation"))
        ctx.sim.economy.update_prices = Mock(side_effect=AssertionError("price mutation"))
        ctx.sim.npcs = SimpleNamespace(nearby_npcs=Mock(return_value=(npc,)))
        start = time.perf_counter()
        for _ in range(20):
            facts = build_dialogue_facts(ctx, npc)
        self.assertLess(time.perf_counter() - start, 2.0)
        self.assertEqual(facts["relationship.community"], 10)
        self.assertEqual(facts["relationship.community_sample_size"], 1)
        ctx.sim.npcs.nearby_npcs.assert_called_with(WorldPos(10, 20, 0), radius=24)
        ctx.sim.world.get_tile.assert_not_called()
        ctx.sim.world.generator.generate_chunk.assert_not_called()
        ctx.sim.realize_regions.assert_not_called()

    def test_modded_maps_extend_vocabulary_and_memory_queries_are_bounded(self):
        ctx, npc, _ = self.fixture()
        ctx.sim.state.player_skills["mod:falconry"] = 6
        npc.needs["mod:solitude"] = 91
        npc.memories = [{"type": "promise", "subject": "player", "valence": 1}] * 1000
        npc.backstory = {f"entry:{i}": "detail" for i in range(1000)}
        facts = build_dialogue_facts(ctx, npc)
        self.assertEqual(facts["player.skills.mod:falconry"], 6)
        self.assertEqual(facts["npc.needs.mod:solitude"], 91)
        self.assertEqual(facts["npc.memories.count"], 1000)
        self.assertEqual(facts["npc.memories.player_count"], MAX_MEMORY_FACTS)
        self.assertEqual(facts["npc.memories.player_valence"], MAX_MEMORY_FACTS)
        self.assertEqual(sum(key.startswith("npc.backstory.entry:") for key in facts), MAX_COLLECTION_FACTS)

    def test_real_generated_representative_has_hundreds_of_measured_facts(self):
        ctx, _, town = self.fixture()
        generator = ProceduralSocietyGenerator(b"chat-facts", self.registry)
        npc = generator.representatives_for_settlement(town, count=1)[0]
        ctx.sim.state.introduced_npcs = [npc.uid]
        first = build_dialogue_facts(ctx, npc)
        second = build_dialogue_facts(ctx, npc)
        self.assertEqual(first, second)
        self.assertGreaterEqual(len(first), 350, f"actual supported facts: {len(first)}")


if __name__ == "__main__":
    unittest.main()
