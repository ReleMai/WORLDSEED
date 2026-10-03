"""Continuous station reach, exclusive use, discovery and real recipe commands."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from worldseed.app import _interior_context_menu
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.entities.components import Inventory
from worldseed.entities.store import EntityStore
from worldseed.sim.commands import CraftCommand
from worldseed.sim.engine import Simulation
from worldseed.systems.crafting import CraftingSystem
from worldseed.systems.interior_state import InteriorActor, InteriorFurniture, InteriorPlan, InteriorRect
from worldseed.systems.interiors import InteriorSystem
from worldseed.systems.state import ActivityReservationState, LivingWorldState, NPCState
from worldseed.systems.workshops import STATION_PIECE_ALIASES, WORKSHOP_PROFILES
from worldseed.ui.interior_workstation import workstation_details


class InteriorWorkstationUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)

    def fixture(self, piece_id="core:loom_piece", inputs=None):
        state = LivingWorldState(player_crafting_discovery_enabled=True)
        furniture = InteriorFurniture("fixture:original", piece_id, 1000, 1000, 1200, 1000)
        plan = InteriorPlan("interior:work", "work", "door:work", 1, 2, 0, 10000, 10000,
                            furniture=[furniture], entry_x=5000, entry_y=9000)
        state.interiors[plan.uid] = plan
        state.interior_actors["player"] = InteriorActor(plan.uid, 1600, 2500)
        entities = EntityStore()
        player = entities.spawn()
        inventory = Inventory(dict(inputs or {}))
        entities.add(player, inventory)
        messages = []
        sim = SimpleNamespace(state=state, registry=self.registry, entities=entities, player_id=player,
                              clock=SimpleNamespace(minute=600), player_skill=lambda skill: 5,
                              _message=messages.append, known_npc_ids=lambda: set(), introduced_npc_ids=lambda: set(), log=[])
        sim.interiors = InteriorSystem(sim)
        sim.crafting = CraftingSystem(state, self.registry)
        sim._player_station_ids = lambda: Simulation._player_station_ids(sim)
        return sim, plan, furniture, inventory, messages

    def reserve(self, sim, plan, furniture):
        worker = NPCState(uid="npc:worker", name="Hidden Worker", settlement_id="town",
                          age=30, traits=[], x=1, y=2, z=0, faction_id="", occupation="weaver")
        row = ActivityReservationState("reservation:original", worker.uid, "town", "work", "weave",
                                       "affordance:original", furniture.uid, "fixture", 1, 2, 0,
                                       1, 2, 0, 600, 90, expires_minute=1000,
                                       metadata={"space_id": plan.uid})
        worker.tasks = [{"kind": "activity", "reservation_uid": row.uid}]
        sim.state.npcs[worker.uid] = worker
        sim.state.activity_reservations[row.uid] = row
        sim.interiors._put_actor(worker.uid, InteriorActor(plan.uid, 2500, 2400))
        return row

    def test_inspect_filters_unknown_recipes_and_reports_real_missing_materials(self):
        sim, plan, furniture, inv, messages = self.fixture(inputs={"core:fiber": 2})
        before = sim.state.to_dict()
        self.assertNotIn("Weave Cloth", workstation_details(sim, furniture))
        self.assertEqual(sim.state.to_dict(), before)
        sim.state.player_discovered_recipes = ["core:weave_cloth"]
        before = sim.state.to_dict()
        text = workstation_details(sim, furniture)
        self.assertIn(WORKSHOP_PROFILES["core:loom"].purpose, text)
        self.assertIn("Weave Cloth", text)
        self.assertIn("2/4", text)
        self.assertIn("Timed process jobs", text)
        self.assertEqual(sim.state.to_dict(), before)

    def test_busy_worker_blocks_station_and_command_without_disclosing_identity(self):
        sim, plan, furniture, inv, messages = self.fixture(inputs={"core:fiber": 4})
        sim.state.player_discovered_recipes = ["core:weave_cloth"]
        row = self.reserve(sim, plan, furniture)
        before = sim.state.to_dict()
        self.assertEqual(sim.interiors.furniture_use_status(furniture.uid), "busy")
        self.assertNotIn("core:loom", sim.interiors.station_ids_near_player())
        text = workstation_details(sim, furniture)
        self.assertIn("Busy", text)
        self.assertNotIn("Hidden Worker", text)
        self.assertEqual(sim.state.to_dict(), before)
        Simulation._craft(sim, CraftCommand(sim.player_id, "core:weave_cloth"))
        self.assertEqual(inv.count("core:fiber"), 4)
        self.assertEqual(inv.count("core:woven_cloth"), 0)
        row.status = "completed"
        self.assertIn("core:loom", sim.interiors.station_ids_near_player())

    def test_expired_reservation_is_read_only_and_does_not_block_player(self):
        sim, plan, furniture, inv, messages = self.fixture()
        row = self.reserve(sim, plan, furniture)
        sim.clock.minute = row.expires_minute + 1
        before = sim.state.to_dict()
        self.assertEqual(sim.interiors.furniture_use_status(furniture.uid), "available")
        self.assertIn("core:loom", sim.interiors.station_ids_near_player())
        self.assertEqual(row.status, "reserved")
        self.assertEqual(sim.state.to_dict(), before)

    def test_real_forge_and_loom_recipe_commands_consume_carried_inputs_once(self):
        cases = [("core:forge_piece", "core:iron_bloom", {"core:iron_ore": 2, "core:coal": 2}, "core:iron_bloom"),
                 ("core:loom_piece", "core:weave_cloth", {"core:fiber": 4}, "core:woven_cloth")]
        for piece, recipe_id, inputs, output in cases:
            with self.subTest(recipe=recipe_id):
                sim, plan, furniture, inv, messages = self.fixture(piece, inputs)
                sim.state.player_discovered_recipes = [recipe_id]
                sim.state.player_knowledge = ["tech:smelting"]
                Simulation._craft(sim, CraftCommand(sim.player_id, recipe_id))
                self.assertEqual(inv.count(output), 1, messages)
                for item in inputs:
                    self.assertEqual(inv.count(item), 0)
                Simulation._craft(sim, CraftCommand(sim.player_id, recipe_id))
                self.assertEqual(inv.count(output), 1)

    def test_partition_rejects_recipe_command_even_when_fixture_is_close(self):
        sim, plan, furniture, inv, messages = self.fixture(inputs={"core:fiber": 4})
        sim.state.player_discovered_recipes = ["core:weave_cloth"]
        plan.walls.append(InteriorRect(0, 2250, plan.width, 40))
        self.assertEqual(sim.interiors.furniture_use_status(furniture.uid), "out_of_reach")
        Simulation._craft(sim, CraftCommand(sim.player_id, "core:weave_cloth"))
        self.assertEqual(inv.count("core:fiber"), 4)
        self.assertEqual(inv.count("core:woven_cloth"), 0)

    def test_context_use_routes_every_existing_workshop_profile_to_shared_ui(self):
        primary = {}
        for piece, station in STATION_PIECE_ALIASES.items():
            primary.setdefault(station, piece)
        for station in WORKSHOP_PROFILES:
            with self.subTest(station=station):
                sim, plan, furniture, inv, messages = self.fixture(primary[station])
                ctx = SimpleNamespace(sim=sim, entities=sim.entities, player_id=sim.player_id)
                before = sim.state.to_dict()
                with patch("worldseed.app._select", return_value="use"), patch("worldseed.app._crafting_menu", return_value="opened") as menu:
                    self.assertEqual(_interior_context_menu(ctx, object(), 1500, 1500), "opened")
                    menu.assert_called_once_with(ctx, unittest.mock.ANY, "workshops", station)
                self.assertEqual(sim.state.to_dict(), before)

    def test_busy_context_does_not_open_another_station_menu(self):
        sim, plan, furniture, inv, messages = self.fixture()
        self.reserve(sim, plan, furniture)
        ctx = SimpleNamespace(sim=sim, entities=sim.entities, player_id=sim.player_id)
        with patch("worldseed.app._select", return_value="use"), patch("worldseed.app._crafting_menu") as menu:
            self.assertIn("busy", _interior_context_menu(ctx, object(), 1500, 1500))
            menu.assert_not_called()

    def test_station_inspect_returns_to_context_without_mutating_state(self):
        sim, plan, furniture, inv, messages = self.fixture()
        ctx = SimpleNamespace(sim=sim, entities=sim.entities, player_id=sim.player_id)
        before = sim.state.to_dict()
        with patch("worldseed.app._select", return_value="inspect"), patch("worldseed.app._view_text") as view:
            _interior_context_menu(ctx, object(), 1500, 1500)
            self.assertEqual(view.call_args.kwargs["title"], "INTERIOR WORKSTATION")
            self.assertIn("WEAVER'S LOOM", view.call_args.args[1])
        self.assertEqual(sim.state.to_dict(), before)

    def test_station_refresh_never_scans_worldwide_npc_or_reservation_collections(self):
        class NoGlobalIteration(dict):
            def __iter__(self):
                raise AssertionError("Global iteration is forbidden for indoor station refresh")
            def values(self):
                raise AssertionError("Global value scan is forbidden for indoor station refresh")
        sim, plan, furniture, inv, messages = self.fixture()
        self.reserve(sim, plan, furniture)
        sim.state.npcs = NoGlobalIteration(sim.state.npcs)
        sim.state.activity_reservations = NoGlobalIteration(sim.state.activity_reservations)
        self.assertNotIn("core:loom", sim.interiors.station_ids_near_player())
        self.assertEqual(sim.interiors.furniture_use_status(furniture.uid), "busy")


if __name__ == "__main__":
    unittest.main()
