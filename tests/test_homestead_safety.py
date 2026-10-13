"""Construction safety uses prepared physical state, before any stage effect."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import ChunkKey, WorldPos, split_world
from worldseed.entities.components import Inventory, Position, Vitals
from worldseed.entities.store import EntityStore
from worldseed.persistence.database import WorldDatabase
from worldseed.sim.commands import AdvanceBlueprintCommand
from worldseed.sim.engine import Simulation
from worldseed.systems.building import BuildingSystem
from worldseed.systems.homestead_blueprints import HomesteadBlueprintService, catalog, doorway, footprint
from worldseed.systems.interior_state import InteriorActor
from worldseed.systems.resources import ResourceSystem
from worldseed.systems.state import CreatureState, LivingWorldState, NPCState, pos_key
from worldseed.world.chunk import Chunk
from worldseed.world.generator import WorldGenerator
from worldseed.world.world import World


def npc_at(uid, cell, **kwargs):
    return NPCState(uid, "Cabin visitor", 25, "gatherer", [], *cell, "", "", **kwargs)


class PreparedGround:
    """Tiny prepared-world query fixture; accessing an absent chunk fails."""
    def __init__(self, registry):
        self.registry = registry
        self.missing_chunks = set()
        self.terrain = {}
        self.reads = []
        self.cache = SimpleNamespace(peek=self.peek)

    def peek(self, key):
        if key in self.missing_chunks:
            return None
        return SimpleNamespace(get=lambda x, y: self.registry.terrain_index(
            self.terrain.get((key.x * 32 + x, key.y * 32 + y, key.z), "core:grass")))

    def tile_at(self, pos):
        self.reads.append(pos)
        if self.peek(split_world(pos)[0]) is None:
            raise AssertionError("Construction attempted to generate an unprepared tile")
        terrain_id = self.terrain.get((pos.x, pos.y, pos.z), "core:grass")
        return SimpleNamespace(terrain=self.registry.terrain(terrain_id), terrain_id=terrain_id)


def service_fixture(registry, style_id="log_cabin_01", orientation=0, x=10, y=10):
    state = LivingWorldState()
    world = PreparedGround(registry)
    natural, flooded, secured = set(), set(), set()
    building = BuildingSystem(state, registry)
    sim = SimpleNamespace(
        registry=registry, state=state, world=world,
        player_pos=WorldPos(x - 1, y - 1, 0), building=building,
        resources=SimpleNamespace(blocks_movement=lambda p: (p.x, p.y, p.z) in natural),
        environment=SimpleNamespace(fluid_passable=lambda p: (p.x, p.y, p.z) not in flooded),
        property_security=SimpleNamespace(
            blocks_actor=lambda p, actor, *a: (p.x, p.y, p.z) in secured,
            blocks_player=lambda p: (p.x, p.y, p.z) in secured),
        settlement_physicalization=SimpleNamespace(
            cell_at=lambda p: None, clears_natural_feature=lambda p: False,
            shell_blocks=lambda p: False, passable=lambda p, w: w),
    )
    service = HomesteadBlueprintService(sim)
    sim.homestead = service
    building.homestead = service
    ok, message = service.place(style_id, x, y, orientation)
    if not ok:
        raise AssertionError(message)
    site = next(iter(state.homesteads.values()))
    site["stored"] = dict(catalog()[0]["log_cabin"]["materials"])
    return sim, service, site, natural, flooded, secured


def prepared_engine(test_case, state=None, position=WorldPos(9, 9, 0), path=None):
    """Real command systems with one dry chunk and no regional startup work."""
    registry = ContentRegistry.load(DATA_DIR)
    if path is None:
        folder = tempfile.TemporaryDirectory(prefix="worldseed-cabin-engine-")
        test_case.addCleanup(folder.cleanup)
        path = Path(folder.name) / "cabin.db"
    database = WorldDatabase.create(path, "Cabin safety fixture", b"cabin-safety".hex())
    test_case.addCleanup(database.close)
    world = World(WorldGenerator(b"cabin-safety", registry), registry, database)
    key = ChunkKey(0, 0, 0)
    chunk = Chunk.empty(key)
    ground = registry.terrain_index("core:grass")
    for index in range(len(chunk.terrain)):
        chunk.terrain[index] = ground
    world.cache.put(key, chunk)
    entities = EntityStore()
    player_id = entities.spawn(preferred_id=1)
    entities.add(player_id, Position(position))
    entities.add(player_id, Inventory({"core:wood": 3, "core:stone": 2}))
    entities.add(player_id, Vitals())
    if state is None:
        state = LivingWorldState(discovered_tiles=[pos_key(x, y, 0) for y in range(32) for x in range(32)])
        # This prepared construction clearing was already harvested. Keep the
        # real resource system and its collision rules, without random trees.
        state.resource_depletion = {pos_key(x, y, 0): state.clock_minute
                                    for y in range(7, 19) for x in range(7, 19)}
    with patch.object(Simulation, "_ensure_nearby_world") as prepare:
        sim = Simulation(world, entities, registry, 0, state, b"cabin-safety")
    prepare.assert_called_once_with(position, force=True)
    return sim, database


class HomesteadSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)

    def assert_rejected_without_mutation(self, sim, service, site):
        before = deepcopy(site)
        ok, message = service.advance(site["uid"])
        self.assertFalse(ok, message)
        self.assertTrue(message)
        self.assertEqual(site, before)
        self.assertIs(service.sites[site["uid"]], site)

    def test_all_styles_and_rotations_keep_foundation_open_and_frame_solid(self):
        styles = [uid for uid, style in catalog()[1].items() if style["home_id"] == "log_cabin"]
        self.assertEqual(len(styles), 10)
        for style_id in styles:
            for rotation in range(4):
                with self.subTest(style=style_id, rotation=rotation):
                    sim, service, site, *_ = service_fixture(self.registry, style_id, rotation)
                    self.assertTrue(service.advance(site["uid"])[0])
                    self.assertEqual(site["stage"], 1)
                    self.assertTrue(all(sim.building.passable(WorldPos(*c), True) for c in footprint(site)))
                    sim.player_pos = WorldPos(*doorway(site)[1])
                    self.assertTrue(service.advance(site["uid"])[0])
                    self.assertEqual(site["stage"], 2)
                    self.assertTrue(all(not sim.building.passable(WorldPos(*c), True) for c in footprint(site)))
                    self.assertTrue(sim.building.passable(WorldPos(*doorway(site)[1]), True))

    def test_frame_rejects_player_on_every_footprint_cell_in_every_rotation(self):
        for rotation in range(4):
            for index in range(9):
                with self.subTest(rotation=rotation, cell=index):
                    sim, service, site, *_ = service_fixture(self.registry, orientation=rotation)
                    site["stage"] = 1
                    sim.player_pos = WorldPos(*footprint(site)[index])
                    self.assert_rejected_without_mutation(sim, service, site)
                    self.assertTrue(sim.building.passable(sim.player_pos, True))

    def test_frame_rejects_live_outdoor_npc_and_creature_in_every_rotation(self):
        for rotation in range(4):
            for kind in ("npc", "creature"):
                with self.subTest(rotation=rotation, actor=kind):
                    sim, service, site, *_ = service_fixture(self.registry, orientation=rotation)
                    site["stage"] = 1
                    cell = footprint(site)[4]
                    if kind == "npc":
                        sim.state.npcs["npc:visitor"] = npc_at("npc:visitor", cell)
                    else:
                        sim.state.creatures["animal:visitor"] = CreatureState("animal:visitor", "core:deer", *cell, 100)
                    self.assert_rejected_without_mutation(sim, service, site)

    def test_dead_and_indoor_actors_do_not_occupy_outdoor_shell(self):
        sim, service, site, *_ = service_fixture(self.registry)
        site["stage"] = 1
        cell = footprint(site)[4]
        sim.state.npcs["npc:indoor"] = npc_at("npc:indoor", cell)
        sim.state.interior_actors["npc:indoor"] = InteriorActor("interior:other", 2000, 2000)
        sim.state.npcs["npc:dead"] = npc_at("npc:dead", cell, alive=False, hp=0)
        sim.state.creatures["animal:dead"] = CreatureState("animal:dead", "core:deer", *cell, 0)
        self.assertTrue(service.advance(site["uid"])[0])

    def test_player_in_another_interior_is_not_an_outdoor_occupant(self):
        sim, service, site, *_ = service_fixture(self.registry)
        site["stage"] = 1
        sim.player_pos = WorldPos(*footprint(site)[4])
        sim.state.interior_actors["player"] = InteriorActor("interior:other", 2000, 2000)
        ok, message = service.construction_safety(site, 2)
        self.assertTrue(ok, message)

    def test_each_rotated_landing_rejects_natural_flood_and_security_obstructions(self):
        for style_id in ("log_cabin_01", "log_cabin_02"):
            for rotation in range(4):
                for blocker in ("natural", "flood", "security", "terrain"):
                    with self.subTest(style=style_id, rotation=rotation, blocker=blocker):
                        sim, service, site, natural, flooded, secured = service_fixture(self.registry, style_id, rotation)
                        site["stage"] = 1
                        landing = doorway(site)[1]
                        if blocker == "terrain":
                            sim.world.terrain[landing] = "core:water"
                        else:
                            {"natural": natural, "flood": flooded, "security": secured}[blocker].add(landing)
                        self.assert_rejected_without_mutation(sim, service, site)

    def test_unprepared_rotated_landing_is_rejected_without_generation(self):
        sim, service, site, *_ = service_fixture(self.registry, x=31, y=29)
        site["stage"] = 1
        # South-facing left door lands across the southern chunk boundary.
        landing = doorway(site)[1]
        self.assertEqual(landing, (31, 32, 0))
        sim.world.missing_chunks.add(split_world(WorldPos(*landing))[0])
        self.assert_rejected_without_mutation(sim, service, site)

    def test_real_resource_queries_do_not_read_an_unprepared_cardinal_neighbor(self):
        sim, service, site, *_ = service_fixture(self.registry, x=0, y=10)
        sim.player_pos = WorldPos(3, 11, 0)
        sim.world.generator = WorldGenerator(b"cabin-resource-halo", self.registry)
        sim.world.delta_source = SimpleNamespace()
        sim.resources = ResourceSystem(sim.state, self.registry, b"cabin-resource-halo", sim.world)
        sim.resources.attach_settlement_physicalization(sim.settlement_physicalization)
        sim.world.missing_chunks.add(ChunkKey(-1, 0, 0))
        sim.world.reads.clear()
        before = sim.state.to_dict()
        # Every footprint/landing tile is prepared, but a resource query at
        # x=0 could inspect x=-1 while choosing shoreline/structural features.
        ok, message, _ = service.preview("log_cabin_01", 0, 10, 0)
        self.assertFalse(ok, message)
        self.assertEqual(sim.state.to_dict(), before)
        site["stage"] = 1
        self.assert_rejected_without_mutation(sim, service, site)
        self.assertTrue(all(pos.x >= 0 for pos in sim.world.reads))

    def test_frame_cannot_close_the_only_escape_of_player_or_npc_outside(self):
        for kind in ("player", "npc"):
            with self.subTest(actor=kind):
                sim, service, site, natural, *_ = service_fixture(self.registry)
                site["stage"] = 1
                trapped = (9, 11, 0)
                natural.update({(8, 11, 0), (9, 10, 0), (9, 12, 0)})
                if kind == "player":
                    sim.player_pos = WorldPos(*trapped)
                else:
                    sim.state.npcs["npc:visitor"] = npc_at("npc:visitor", trapped)
                    sim.player_pos = WorldPos(*doorway(site)[1])
                self.assert_rejected_without_mutation(sim, service, site)
                natural.remove((8, 11, 0))
                self.assertTrue(service.advance(site["uid"])[0])

    def test_clear_landing_must_connect_to_an_exterior_escape(self):
        sim, service, site, natural, *_ = service_fixture(self.registry)
        site["stage"] = 1
        natural.update({(9, 13, 0), (11, 13, 0), (10, 14, 0)})
        self.assert_rejected_without_mutation(sim, service, site)

    def test_diagonally_adjacent_npc_cannot_be_trapped_by_frame_corner(self):
        sim, service, site, natural, *_ = service_fixture(self.registry)
        site["stage"] = 1
        sim.player_pos = WorldPos(*doorway(site)[1])
        sim.state.npcs["npc:corner"] = npc_at("npc:corner", (9, 9, 0))
        natural.update({(8, 9, 0), (9, 8, 0), (9, 10, 0), (10, 8, 0), (11, 9, 0)})
        self.assert_rejected_without_mutation(sim, service, site)

    def test_legacy_recovery_skips_an_open_apron_tile_with_no_escape(self):
        sim, service, site, natural, *_ = service_fixture(self.registry)
        site["stage"] = 4
        sim.player_pos = WorldPos(11, 11, 0)
        sim.state.npcs["npc:door"] = npc_at("npc:door", doorway(site)[1])
        # The closest northern tile is open, but walls and the solid cabin
        # enclose it. Another open apron tile has access to surrounding ground.
        natural.update({(11, 8, 0), (10, 9, 0), (12, 9, 0)})
        before = sim.state.to_dict()
        landing = service.recovery_landing(site, sim.player_pos)
        self.assertIsNotNone(landing)
        self.assertNotEqual(landing, WorldPos(11, 9, 0))
        self.assertNotEqual(landing, WorldPos(*doorway(site)[1]))
        self.assertNotIn((landing.x, landing.y, landing.z), footprint(site))
        self.assertTrue(sim.building.passable(landing, True))
        self.assertFalse(sim.resources.blocks_movement(landing))
        self.assertEqual(sim.state.to_dict(), before)

    def test_cancellation_after_rejection_refunds_original_materials_and_clears_shell(self):
        sim, service, site, *_ = service_fixture(self.registry)
        site["stage"] = 1
        site["stored"].pop("core:reed_bundle")
        site["stored"].update({"core:pine_bough": 5, "core:beachgrass": 7})
        sim.player_pos = WorldPos(*footprint(site)[4])
        self.assert_rejected_without_mutation(sim, service, site)
        goods = dict(site["stored"])
        inv = Inventory({"core:wood": 2})
        self.assertTrue(service.cancel(site["uid"], inv)[0])
        self.assertEqual(inv.items, dict(goods, **{"core:wood": goods["core:wood"] + 2}))
        self.assertFalse(sim.state.homesteads)
        self.assertTrue(sim.building.passable(sim.player_pos, True))

    def test_framed_cancellation_and_reload_preserve_collision_and_refunds(self):
        sim, service, site, *_ = service_fixture(self.registry)
        self.assertTrue(service.advance(site["uid"])[0])
        self.assertTrue(service.advance(site["uid"])[0])
        restored = LivingWorldState.from_dict(sim.state.to_dict())
        sim.state = restored
        sim.building = BuildingSystem(restored, self.registry)
        sim.homestead = HomesteadBlueprintService(sim)
        sim.building.homestead = sim.homestead
        self.assertFalse(sim.building.passable(WorldPos(*footprint(site)[4]), True))
        inv = Inventory()
        self.assertTrue(sim.homestead.cancel(site["uid"], inv)[0])
        self.assertEqual(inv.items, site["stored"])
        self.assertTrue(sim.building.passable(WorldPos(*footprint(site)[4]), True))

    def test_preview_and_safety_reads_are_bounded_and_do_not_realize_regions(self):
        sim, service, site, *_ = service_fixture(self.registry)
        before = sim.state.to_dict()
        sim.world.reads.clear()
        sim.player_pos = WorldPos(14, 10, 0)
        ok, message, _ = service.preview("log_cabin_01", 15, 11, 0)
        self.assertTrue(ok, message)
        self.assertEqual(sim.state.to_dict(), before)
        self.assertLess(len(sim.world.reads), 64)
        sim.world.reads.clear()
        ok, message = service.construction_safety(site, 2)
        self.assertTrue(ok, message)
        self.assertEqual(sim.state.to_dict(), before)
        self.assertLess(len(sim.world.reads), 1024)


class HomesteadCommandSafetyTests(unittest.TestCase):
    def test_rejected_stage_command_has_no_time_turn_or_post_action_cost(self):
        sim, _ = prepared_engine(self)
        ok, message = sim.homestead.place("log_cabin_01", 10, 10, 0)
        self.assertTrue(ok, message)
        site = next(iter(sim.state.homesteads.values()))
        site["stored"] = dict(catalog()[0]["log_cabin"]["materials"])
        site["stage"] = 1
        sim.entities.get(sim.player_id, Position).value = WorldPos(11, 11, 0)
        before = (sim.clock.minute, sim.turn, deepcopy(site),
                  dict(sim.entities.get(sim.player_id, Inventory).items),
                  deepcopy(sim.entities.get(sim.player_id, Vitals)))
        with patch.object(sim, "_advance_time", side_effect=AssertionError("Rejected command advanced time")), \
             patch.object(sim, "_post_action", side_effect=AssertionError("Rejected command ran consequences")):
            sim.execute(AdvanceBlueprintCommand(sim.player_id, site["uid"]))
        after = (sim.clock.minute, sim.turn, deepcopy(site),
                 dict(sim.entities.get(sim.player_id, Inventory).items),
                 deepcopy(sim.entities.get(sim.player_id, Vitals)))
        self.assertEqual(after, before)
        self.assertTrue(sim.log[-1].message)


if __name__ == "__main__":
    unittest.main()
