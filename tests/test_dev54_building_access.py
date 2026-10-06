"""Building occupancy remains exact and shared by player/NPC traversal.

The matrix prepares finite synthetic plans once. Traversal then queries only
the prepared physical projection; it must not request terrain or planning.
"""
from collections import deque
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.audit_settlement_layouts import ARCHETYPES, POPULATIONS, synthetic_fixture
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.systems.building import BuildingSystem
from worldseed.systems.pathfinding import local_path
from worldseed.systems.physicalization import SettlementPhysicalizationSystem
from worldseed.systems.settlement_planner import SettlementSkeletonPlanner
from worldseed.systems.state import LivingWorldState
from worldseed.world.regional_plan import RoadSegmentPlan, StructurePiecePlan, StructurePlanState


CARDINALS = ((1, 0), (-1, 0), (0, 1), (0, -1))


class BuildingAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)

    def projection(self, skeleton, world=None):
        physical = SettlementPhysicalizationSystem(world, self.registry, None, None)
        physical._index_skeleton("settlement:access-test", skeleton)
        state = LivingWorldState()
        building = BuildingSystem(state, self.registry)
        building.attach_settlement_physicalization(physical)
        return physical, building, state

    def assert_path(self, path, start, goal, passable):
        self.assertTrue(path, f"NPC local path failed: {start} -> {goal}")
        self.assertEqual(path[0], start)
        self.assertEqual(path[-1], goal)
        self.assertTrue(all(passable(cell) for cell in path))
        for a, b in zip(path, path[1:]):
            self.assertEqual(abs(a.x - b.x) + abs(a.y - b.y), 1)

    @staticmethod
    def local_road_goal(start, road_cells):
        """Select a small connected road trip, not an unbounded town search."""
        queue = deque([(start, 0)])
        reached = {start}
        furthest = start
        while queue:
            cell, distance = queue.popleft()
            furthest = cell
            if distance == 6:
                continue
            for dx, dy in CARDINALS:
                nxt = (cell[0] + dx, cell[1] + dy)
                if nxt in road_cells and nxt not in reached:
                    reached.add(nxt)
                    queue.append((nxt, distance + 1))
        return furthest

    def test_all_25_layout_cases_share_passable_roads_and_npc_frontage_paths(self):
        cases = 0
        trips = 0
        for archetype in ARCHETYPES:
            for population in POPULATIONS:
                with self.subTest(archetype=archetype, population=population):
                    world, region, uid = synthetic_fixture(
                        self.registry, archetype, population, version=12)
                    planner = SettlementSkeletonPlanner(world)
                    skeleton = planner.plan(region, uid, population, persist=False)
                    before = deepcopy(skeleton.to_dict())
                    with patch.object(world, "environment_at", side_effect=AssertionError(
                            "prepared traversal requested terrain")), \
                         patch.object(planner, "plan", side_effect=AssertionError(
                            "prepared traversal regenerated settlement")):
                        physical, building, state = self.projection(skeleton, world)
                        state_before = state.to_dict()
                        closed = [row for row in skeleton.structures
                                  if row.enclosed and not row.destroyed and row.condition > 0]
                        blocked = {tuple(cell) for row in closed for cell in row.footprint}
                        road_cells = {tuple(cell) for road in skeleton.roads
                                      for cell in road.polyline}
                        entrances = {tuple(row.entrance) for row in closed
                                     if row.entrance is not None}
                        self.assertLessEqual(road_cells & blocked, entrances,
                                             "a real road crosses a solid building body")
                        traversable_roads = road_cells - blocked
                        self.assertTrue(closed)
                        self.assertTrue(traversable_roads)
                        for cell in sorted(traversable_roads):
                            pos = WorldPos(*cell, 0)
                            self.assertFalse(physical.shell_blocks(pos))
                            self.assertTrue(building.passable(pos, True), cell)
                        for row in closed:
                            frontage = physical.frontage_for(row.uid)
                            self.assertIsNotNone(frontage, row.uid)
                            start_cell = (frontage.x, frontage.y)
                            self.assertIn(start_cell, traversable_roads)
                            self.assertTrue(building.passable(frontage, True))
                            # Exterior entrance cells remain solid portals, not
                            # ordinary walk-through tiles, even unlocked.
                            self.assertFalse(building.passable(WorldPos(*row.entrance, 0), True))
                            goal_cell = self.local_road_goal(start_cell, traversable_roads)
                            self.assertNotEqual(start_cell, goal_cell, row.uid)
                            goal = WorldPos(*goal_cell, 0)
                            def passable(pos):
                                return (pos.z == 0 and (pos.x, pos.y) in traversable_roads
                                        and building.passable(pos, True))
                            self.assert_path(local_path(frontage, goal, passable, 1000),
                                             frontage, goal, passable)
                            trips += 1
                        self.assertEqual(before, skeleton.to_dict())
                        self.assertEqual(state_before, state.to_dict())
                    cases += 1
        self.assertEqual(cases, 25)
        self.assertGreater(trips, 100)

    def fixture(self, shape="rectangle", *, destroyed=False, condition=100):
        footprint = {(x, y) for y in range(3, 9) for x in range(3, 9)}
        if shape == "l_house":
            footprint -= {(7, 3), (8, 3), (7, 4), (8, 4)}
        elif shape == "chamfered_cottage":
            footprint -= {(3, 3), (8, 3), (3, 8), (8, 8)}
        structure = StructurePlanState(
            "structure:access-test", "plan:access-test", "core:house", "residence",
            footprint=sorted(footprint), entrance=(5, 8), enclosed=True,
            building_form=shape, destroyed=destroyed, condition=condition)
        door = self.registry.settlement_pieces["core:wood_door_piece"]
        pieces = [StructurePiecePlan("door:access-test", structure.uid,
                                     door.id, 5, 8, role="entrance")]
        road = RoadSegmentPlan("road:access-test", road_class="service_path",
                               polyline=[(x, 9) for x in range(2, 10)])
        skeleton = SimpleNamespace(structures=[structure], pieces=pieces,
                                   rooms=[], roads=[road], parcels=[])
        return skeleton, structure, footprint

    def test_irregular_footprint_holes_and_exterior_apron_remain_walkable(self):
        for shape in ("rectangle", "l_house", "chamfered_cottage"):
            with self.subTest(shape=shape):
                skeleton, structure, footprint = self.fixture(shape)
                physical, building, _ = self.projection(skeleton)
                for y in range(2, 10):
                    for x in range(2, 10):
                        pos = WorldPos(x, y, 0)
                        occupied = (x, y) in footprint
                        self.assertEqual(physical.shell_blocks(pos), occupied, pos)
                        self.assertEqual(building.passable(pos, True), not occupied, pos)
                        self.assertEqual(building.blocks_sight(pos), occupied, pos)
                        if not occupied:
                            self.assertIsNone(physical.shell_at(pos))
                self.assertEqual(physical.frontage_for(structure.uid), WorldPos(5, 9, 0))
                self.assertEqual(physical.destination_for(structure.uid), WorldPos(5, 9, 0))
                self.assertEqual(physical.door_at(WorldPos(5, 8)).structure_piece_uid,
                                 "door:access-test")

    def test_npc_local_path_routes_around_solid_body_not_through_it(self):
        skeleton, _, footprint = self.fixture()
        physical, building, state = self.projection(skeleton)
        before = state.to_dict()
        start, goal = WorldPos(2, 6), WorldPos(9, 6)
        def passable(pos):
            return (pos.z == 0 and 1 <= pos.x <= 10 and 1 <= pos.y <= 10
                    and building.passable(pos, True))
        path = local_path(start, goal, passable, 1000)
        self.assert_path(path, start, goal, passable)
        self.assertGreater(len(path), goal.x - start.x + 1)
        self.assertFalse(any((cell.x, cell.y) in footprint for cell in path))
        self.assertTrue(all(not physical.shell_blocks(cell) for cell in path))
        self.assertEqual(before, state.to_dict())

    def test_destroyed_and_zero_condition_buildings_do_not_keep_shell_collision(self):
        for destroyed, condition in ((True, 100), (False, 0)):
            with self.subTest(destroyed=destroyed, condition=condition):
                skeleton, _, footprint = self.fixture(destroyed=destroyed, condition=condition)
                physical, building, _ = self.projection(skeleton)
                for x, y in footprint:
                    pos = WorldPos(x, y, 0)
                    self.assertIsNone(physical.shell_at(pos))
                    self.assertFalse(physical.shell_blocks(pos))
                    self.assertTrue(building.passable(pos, True))
                    self.assertFalse(building.blocks_sight(pos))

    def test_surface_shell_never_blocks_same_coordinates_underground(self):
        skeleton, _, footprint = self.fixture()
        physical, building, _ = self.projection(skeleton)
        for x, y in footprint:
            pos = WorldPos(x, y, -1)
            self.assertIsNone(physical.shell_at(pos))
            self.assertTrue(building.passable(pos, True))
            self.assertFalse(building.blocks_sight(pos))
        # The supplied terrain authority still wins: no collision fix turns
        # ocean, underground rock, or other impassable terrain into a road.
        self.assertFalse(building.passable(WorldPos(5, 9, 0), False))
        self.assertFalse(building.passable(WorldPos(5, 5, -1), False))


if __name__ == "__main__":
    unittest.main()
