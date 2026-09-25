from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.persistence.database import WorldDatabase
from worldseed.systems.generation import ProceduralSocietyGenerator
from worldseed.systems.regional_civilization import RegionalCivilizationPlanner
from worldseed.systems.route_planner import RegionalRoutePlanner
from worldseed.world.generator import WorldGenerator
from worldseed.world.region_blocks import RegionBlockPlanner
from worldseed.world.world import World


class RegionalCivilizationTests(unittest.TestCase):
    def make_world(self, seed=b"regional-civilization-wu22"):
        td = tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup)
        registry = ContentRegistry.load(DATA_DIR)
        db = WorldDatabase.create(Path(td.name) / "world.db", "test", seed.hex())
        self.addCleanup(db.close)
        world = World(WorldGenerator(seed, registry), registry, db)
        world.settlement_plan_version = 4
        world.routegen_version = 2
        return world, db

    def test_settlement_presence_is_terrain_ranked_and_spaced(self):
        world, _ = self.make_world()
        civ = RegionalCivilizationPlanner(world, version=4)
        present = [
            civ.potential(x, y)
            for y in range(-6, 7)
            for x in range(-6, 7)
            if civ.potential(x, y).settlement_present
        ]
        self.assertGreater(len(present), 2)
        for row in present:
            self.assertGreaterEqual(row.capacity, civ.MIN_CAPACITY)
            self.assertGreaterEqual(row.land_ratio, 45)
            for other in present:
                if other is row:
                    continue
                self.assertGreater(max(abs(row.region_x - other.region_x), abs(row.region_y - other.region_y)), 1)

    def test_faction_domains_have_stable_seats_and_flavor(self):
        world, _ = self.make_world()
        civ = RegionalCivilizationPlanner(world, version=4)
        node = next(
            civ.potential(x, y)
            for y in range(-8, 9)
            for x in range(-8, 9)
            if civ.potential(x, y).settlement_present
        )
        seed = civ.faction_seed_for_region(node.region_x, node.region_y)
        again = civ.faction_seed_for_region(node.region_x, node.region_y)
        self.assertEqual(seed, again)
        self.assertTrue(seed.name.startswith("The "))
        self.assertTrue(seed.motto)
        self.assertTrue(seed.tradition)
        self.assertTrue(civ.potential(seed.seat_region_x, seed.seat_region_y).settlement_present)

    def test_route_planner_builds_sparse_persistent_backbone(self):
        world, db = self.make_world()
        civ = RegionalCivilizationPlanner(world, version=4)
        planner = RegionalRoutePlanner(world, civ, version=2)
        chosen = None
        for dy in range(-3, 4):
            for dx in range(-3, 4):
                nodes = civ.settlements_in_domain(dx, dy)
                if len(nodes) < 2:
                    continue
                routes = planner.domain_routes(dx, dy, persist=False)
                internal = [r for r in routes if r.rationale != "inter_faction_trunk"]
                if len(internal) >= len(nodes) - 1:
                    chosen = (dx, dy, nodes)
                    break
            if chosen:
                break
        self.assertIsNotNone(chosen)
        dx, dy, nodes = chosen
        routes = planner.domain_routes(dx, dy, persist=True)
        internal = [r for r in routes if r.rationale != "inter_faction_trunk"]
        self.assertGreaterEqual(len(internal), len(nodes) - 1)
        self.assertLessEqual(len(internal), len(nodes) - 1 + max(1, len(nodes) // 3))
        for route in routes:
            self.assertTrue(route.region_path)
            self.assertGreater(route.cost, 0)
            self.assertEqual(db.load_generated_route_plan(route.uid, 2), route.to_dict())

        graph = {(n.region_x, n.region_y): set() for n in nodes}
        for route in internal:
            a, b = route.origin_region, route.destination_region
            if a in graph and b in graph:
                graph[a].add(b); graph[b].add(a)
        seen = set()
        stack = [next(iter(graph))]
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node); stack.extend(graph[node] - seen)
        self.assertEqual(seen, set(graph))

    def test_society_uses_derived_building_authority_and_prominent_faction(self):
        world, _ = self.make_world()
        regions = RegionBlockPlanner(world)
        society = ProceduralSocietyGenerator(world.generator.world_seed, world.registry, regions)
        coords = next(
            (x, y)
            for y in range(-6, 7)
            for x in range(-6, 7)
            if regions._presence(x, y)
        )
        generated = society.settlement_for_cell(*coords)
        self.assertIsNotNone(generated)
        town, _, culture, _, faction = generated
        self.assertEqual(town.building_authority, "derived")
        self.assertEqual(town.buildings, {})
        self.assertTrue(town.culture_style)
        self.assertTrue(town.regional_role)
        self.assertTrue(town.founding_trait)
        self.assertTrue(faction.tradition)
        self.assertTrue(faction.motto)
        seed=regions.civilization.faction_seed_for_region(*coords)
        self.assertEqual(faction.uid, seed.uid)
        self.assertEqual(town.culture_id, culture.uid)
        self.assertEqual(faction.culture_id, culture.uid)
        self.assertTrue(set(seed.values[:2]).issubset(set(culture.values)))


if __name__ == "__main__":
    unittest.main()
