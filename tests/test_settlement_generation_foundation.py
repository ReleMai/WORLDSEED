import unittest

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.systems.settlement_planner import (
    SettlementSkeletonPlanner,
    analyze_building,
    settlement_piece_groups,
)
from worldseed.world.regional_plan import (
    LandUseParcel,
    RoadSegmentPlan,
    SettlementPlanState,
    StructurePlanState,
)
from worldseed.world.settlement_atlas import build_settlement_atlas
from worldseed.world.region_blocks import RegionBlockPlan, RegionRoadExit
from types import SimpleNamespace


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


    def test_terrain_aware_skeleton_generates_roads_common_and_land_use(self):
        class Cache:
            def __init__(self): self.rows={}
            def load_generated_settlement_plan(self,uid,version): return self.rows.get((uid,version))
            def store_generated_settlement_plan(self,uid,version,payload): self.rows[(uid,version)]=payload
            def commit_generated(self): pass

        class Env:
            def __init__(self,x,y):
                # A steep/wet vertical barrier has one usable pass at y=100.
                blocked = 96 <= x <= 99 and not 97 <= y <= 103
                self.open_water = False
                self.slope = 92 if blocked else 8 + abs((y % 11)-5)
                self.flood_risk = 90 if blocked else 8
                self.wetness = 45
                self.soil_fertility = 82 if x < 100 else 45
                self.farmland = 88 if x < 100 else 38
                self.resources = SimpleNamespace(stone=86 if x > 105 else 30, timber=50, freshwater=55)
                self.resource_opportunity = (self.resources.stone+self.resources.timber+self.resources.freshwater)//3

        cache=Cache()
        world=SimpleNamespace(
            generator=SimpleNamespace(world_seed=b'skeleton-test'),
            delta_source=cache,
            environment_at=lambda pos: Env(pos.x,pos.y),
        )
        region=RegionBlockPlan(
            uid='region:0:0',region_x=0,region_y=0,version=1,
            dominant_biome='grassland',biome_mix={'grassland':25},
            mean_elevation=30000,mean_moisture=30000,mean_temperature=32000,relief=1000,
            settlement_present=True,settlement_anchor=(100,100),settlement_score=80,
            settlement_archetype='mining',control_potential='settled',
            roads=(RegionRoadExit('east',100,'road'),),
        )
        planner=SettlementSkeletonPlanner(world)
        skeleton=planner.plan(region,'settlement:0:0',95,persist=True)
        self.assertEqual(skeleton.plan.rank,'town')
        self.assertTrue(skeleton.plan.common_cells)
        self.assertTrue(skeleton.plan.gateway_cells)
        self.assertGreaterEqual(len(skeleton.roads),3)
        self.assertIn('civic',skeleton.plan.land_use_summary)
        self.assertIn('residential',skeleton.plan.land_use_summary)
        self.assertIn('farm',skeleton.plan.land_use_summary)
        industrial=[p for p in skeleton.parcels if p.kind=='industrial']
        self.assertTrue(industrial)
        self.assertEqual(industrial[0].purpose,'mine_approach')
        # Generated roads must use the pass through the synthetic barrier rather
        # than cutting across the steep/flooded cells.
        for road in skeleton.roads:
            for x,y in road.polyline:
                self.assertFalse(96 <= x <= 99 and not 97 <= y <= 103)
        # Every non-common parcel has a stable access road binding.
        for parcel in skeleton.parcels:
            if parcel.kind!='civic':
                self.assertTrue(parcel.access_road_id)
                self.assertIn(parcel.access_road_id,{r.uid for r in skeleton.roads})
        rebuilt=SettlementSkeletonPlanner(world).plan(region,'settlement:0:0',95,persist=True)
        self.assertEqual(rebuilt.fingerprint,skeleton.fingerprint)
        self.assertEqual(rebuilt.to_dict(),skeleton.to_dict())

    def test_skeleton_is_independent_of_unrelated_registry_or_rng_state(self):
        class Cache:
            def load_generated_settlement_plan(self,*_): return None
            def store_generated_settlement_plan(self,*_): pass
            def commit_generated(self): pass
        env=SimpleNamespace(
            open_water=False,slope=10,flood_risk=5,wetness=40,soil_fertility=65,farmland=70,
            resources=SimpleNamespace(stone=40,timber=60,freshwater=50),resource_opportunity=50,
        )
        world=SimpleNamespace(generator=SimpleNamespace(world_seed=b'order-test'),delta_source=Cache(),environment_at=lambda pos: env)
        region=RegionBlockPlan(
            uid='r',region_x=0,region_y=0,version=1,dominant_biome='grassland',biome_mix={'grassland':25},
            mean_elevation=1,mean_moisture=1,mean_temperature=1,relief=1,
            settlement_present=True,settlement_anchor=(120,120),settlement_score=70,
            settlement_archetype='agrarian',control_potential='settled',
            roads=(RegionRoadExit('north',120,'road'),RegionRoadExit('south',120,'road')),
        )
        a=SettlementSkeletonPlanner(world).plan(region,'settlement:r',55,persist=False)
        # An unrelated attribute/order mutation must not enter the planner's deterministic inputs.
        world.unrelated={'z':3,'a':1}
        b=SettlementSkeletonPlanner(world).plan(region,'settlement:r',55,persist=False)
        self.assertEqual(a.fingerprint,b.fingerprint)



if __name__ == "__main__":
    unittest.main()
