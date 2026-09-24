import unittest

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.systems.settlement_planner import analyze_building, settlement_piece_groups
from worldseed.world.regional_plan import (
    LandUseParcel,
    RoadSegmentPlan,
    SettlementPlanState,
    StructurePlanState,
)
from worldseed.world.settlement_atlas import build_settlement_atlas


class SettlementGenerationFoundationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)

    def test_settlement_piece_catalog_has_required_breadth(self):
        pieces = self.registry.settlement_pieces
        self.assertGreaterEqual(len(pieces), 100)
        groups = settlement_piece_groups(self.registry)
        required = {
            "wall", "floor", "opening", "furniture", "workshop",
            "road", "agriculture", "mine", "decoration", "civic",
        }
        self.assertTrue(required.issubset(groups))
        self.assertGreaterEqual(len(groups["wall"]), 10)
        self.assertGreaterEqual(len(groups["workshop"]), 10)
        self.assertGreaterEqual(len(groups["road"]), 8)
        self.assertEqual(len(pieces), len(set(pieces)))

    def test_large_building_detects_separate_interior_rooms(self):
        walls = set()
        for x in range(10):
            walls.add((x, 0)); walls.add((x, 7))
        for y in range(8):
            walls.add((0, y)); walls.add((9, y))
        for y in range(1, 7):
            walls.add((5, y))
        walls.remove((5, 3))
        doors = {(0, 3), (5, 3)}
        walls.discard((0, 3))
        floors = {(x, y) for x in range(1, 9) for y in range(1, 7) if x != 5 or y == 3}
        roofs = set(floors)
        fixtures = {
            (2, 2): {"bed", "sleep"},
            (7, 2): {"forge", "smithy", "station"},
            (7, 4): {"anvil", "smithy", "station"},
        }
        result = analyze_building(
            "structure:test", wall_cells=walls, door_cells=doors,
            floor_cells=floors, roof_cells=roofs, fixture_tags=fixtures,
        )
        self.assertTrue(result.enclosed)
        self.assertEqual(len(result.rooms), 2)
        self.assertEqual({room.kind for room in result.rooms}, {"bedroom", "smithy"})
        self.assertEqual(result.building_type, "smithy")
        self.assertGreater(result.interior_area, 30)
        self.assertEqual(result.roof_percent, 100)
        self.assertIn((0, 3), result.exterior_doorways)
        self.assertTrue(all(room.sheltered for room in result.rooms))
        self.assertTrue(all((5, 3) in room.doorway_cells for room in result.rooms))

    def test_room_detection_is_generation_order_independent(self):
        walls = {(0,0),(1,0),(2,0),(0,1),(2,1),(0,2),(1,2),(2,2)}
        a = analyze_building("s", wall_cells=walls, door_cells={(1,2)}, roof_cells={(1,1)})
        b = analyze_building("s", wall_cells=reversed(sorted(walls)), door_cells=[(1,2)], roof_cells=[(1,1)])
        self.assertEqual(a, b)

    def test_settlement_atlas_maps_plan_layers_and_rooms(self):
        plan = SettlementPlanState("settlement-plan:1", "settlement:1", 1, 10, 10, "agrarian")
        road = RoadSegmentPlan("road:1", settlement_plan_id=plan.uid, polyline=[(8,10),(9,10),(10,10),(11,10)])
        parcel = LandUseParcel("parcel:1", plan.uid, cells=[(10,9),(11,9),(10,10),(11,10)], kind="residential")
        structure = StructurePlanState(
            "structure:1", plan.uid, "core:house", "home",
            footprint=[(10,9),(11,9)], building_type="residence", enclosed=True, interior_area=2,
        )
        analysis = analyze_building(
            structure.uid,
            wall_cells={(9,8),(10,8),(11,8),(12,8),(9,9),(12,9),(9,10),(11,10),(12,10)},
            door_cells={(10,10)}, floor_cells={(10,9),(11,9)},
            roof_cells={(10,9),(11,9)}, fixture_tags={(10,9):{"bed"}},
        )
        room = analysis.rooms[0]
        atlas = build_settlement_atlas(
            plan, roads=[road], parcels=[parcel], structures=[structure], rooms=[room], margin=2
        )
        cell = atlas.cell_at(10, 9)
        self.assertIsNotNone(cell)
        self.assertEqual(cell.parcel_id, parcel.uid)
        self.assertEqual(cell.land_use, "residential")
        self.assertEqual(cell.structure_id, structure.uid)
        self.assertEqual(cell.room_id, room.uid)
        self.assertEqual(cell.room_kind, "bedroom")
        rebuilt = build_settlement_atlas(
            plan, roads=[road], parcels=[parcel], structures=[structure], rooms=[room], margin=2
        )
        self.assertEqual(rebuilt.fingerprint, atlas.fingerprint)


if __name__ == "__main__":
    unittest.main()
