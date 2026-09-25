import unittest

from worldseed.config import DATA_DIR
from worldseed.core.coords import WorldPos
from worldseed.content.registry import ContentRegistry
from worldseed.systems.physicalization import SettlementPhysicalizationSystem
from worldseed.systems.building import BuildingSystem
from worldseed.systems.state import LivingWorldState
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
            registry=self.registry,
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
        world=SimpleNamespace(generator=SimpleNamespace(world_seed=b'order-test'),delta_source=Cache(),registry=self.registry,environment_at=lambda pos: env)
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



    def test_generated_buildings_use_catalog_and_pass_enclosure_detector(self):
        class Cache:
            def load_generated_settlement_plan(self,*_): return None
            def store_generated_settlement_plan(self,*_): pass
            def commit_generated(self): pass
        env=SimpleNamespace(
            open_water=False,slope=6,flood_risk=4,wetness=42,soil_fertility=70,farmland=76,
            resources=SimpleNamespace(stone=72,timber=60,freshwater=55),resource_opportunity=62,
        )
        world=SimpleNamespace(
            generator=SimpleNamespace(world_seed=b'building-plan-test'),delta_source=Cache(),
            registry=self.registry,environment_at=lambda pos: env,
        )
        region=RegionBlockPlan(
            uid='rb',region_x=0,region_y=0,version=1,dominant_biome='grassland',biome_mix={'grassland':25},
            mean_elevation=1,mean_moisture=1,mean_temperature=1,relief=1,
            settlement_present=True,settlement_anchor=(160,160),settlement_score=80,
            settlement_archetype='mining',control_potential='settled',
            roads=(RegionRoadExit('north',160,'road'),RegionRoadExit('east',160,'road')),
        )
        skeleton=SettlementSkeletonPlanner(world).plan(region,'settlement:buildings',110,persist=False)
        self.assertTrue(skeleton.structures)
        self.assertTrue(skeleton.rooms)
        self.assertTrue(skeleton.pieces)
        self.assertEqual(set(skeleton.plan.structure_site_ids),{s.uid for s in skeleton.structures})
        catalog=set(self.registry.settlement_pieces)
        self.assertTrue(all(piece.piece_id in catalog for piece in skeleton.pieces))
        for structure in skeleton.structures:
            self.assertTrue(structure.enclosed)
            self.assertGreaterEqual(structure.roof_percent,60)
            self.assertTrue(structure.entrance)
            self.assertTrue(structure.room_ids)
            self.assertTrue(structure.piece_ids)
            self.assertTrue(set(structure.room_ids).issubset({r.uid for r in skeleton.rooms}))
            self.assertTrue(set(structure.piece_ids).issubset({p.uid for p in skeleton.pieces}))
        self.assertTrue(any(len(s.room_ids)>=2 for s in skeleton.structures))
        self.assertTrue(any(s.building_type=='smithy' for s in skeleton.structures))
        smithy=next(s for s in skeleton.structures if s.building_type=='smithy')
        self.assertIn('smithy',{r.kind for r in skeleton.rooms if r.structure_plan_id==smithy.uid})

    def test_roofs_are_first_class_settlement_pieces(self):
        roofs=[p for p in self.registry.settlement_pieces.values() if p.category=='roof']
        self.assertGreaterEqual(len(roofs),8)
        self.assertTrue(all(p.layer=='overlay' for p in roofs))


    def test_local_physicalization_exposes_collision_rooms_and_road_glyphs(self):
        class Cache:
            def load_generated_settlement_plan(self,*_): return None
            def store_generated_settlement_plan(self,*_): pass
            def commit_generated(self): pass
        env=SimpleNamespace(
            open_water=False,slope=5,flood_risk=4,wetness=40,soil_fertility=72,farmland=80,
            resources=SimpleNamespace(stone=75,timber=60,freshwater=55),resource_opportunity=64,
        )
        region=RegionBlockPlan(
            uid='physical-region',region_x=0,region_y=0,version=1,
            dominant_biome='grassland',biome_mix={'grassland':25},
            mean_elevation=1,mean_moisture=1,mean_temperature=1,relief=1,
            settlement_present=True,settlement_anchor=(180,180),settlement_score=82,
            settlement_archetype='mining',control_potential='settled',
            roads=(RegionRoadExit('north',180,'road'),RegionRoadExit('east',180,'road')),
        )
        world=SimpleNamespace(
            generator=SimpleNamespace(world_seed=b'physicalization-test'),
            delta_source=Cache(),registry=self.registry,environment_at=lambda pos:env,
        )
        region_planner=SimpleNamespace(plan=lambda rx,ry,persist=True:region)
        skeleton_planner=SettlementSkeletonPlanner(world)
        physical=SettlementPhysicalizationSystem(world,self.registry,region_planner,skeleton_planner)
        settlement=SimpleNamespace(uid='settlement:physical',region_x=0,region_y=0,population=105)
        self.assertEqual(physical.sync([settlement],(0,0)),1)
        cells=physical.cells()
        self.assertTrue(cells)
        road_cell=next(c for c in cells if c.road_ids and c.ground_piece_id)
        self.assertEqual(physical.glyph_at(WorldPos(road_cell.x,road_cell.y,0)),'=')
        wall_cell=next(c for c in cells if c.structure_piece_id and
                       not self.registry.settlement_pieces[c.structure_piece_id].passable)
        wall_pos=WorldPos(wall_cell.x,wall_cell.y,0)
        self.assertFalse(physical.passable(wall_pos,True))
        self.assertTrue(physical.blocks_sight(wall_pos))
        door_cell=next(c for c in cells if c.structure_piece_id and
                       'door' in self.registry.settlement_pieces[c.structure_piece_id].tags)
        self.assertTrue(physical.passable(WorldPos(door_cell.x,door_cell.y,0),True))
        room_cell=next(c for c in cells if c.room_id)
        room=physical.room_at(WorldPos(room_cell.x,room_cell.y,0))
        self.assertTrue(room['enclosed'])
        self.assertTrue(room['sheltered'])
        self.assertGreaterEqual(room['roof_percent'],60)
        self.assertIn(room['classification'],{'room','bedroom','smithy','storage','workshop'})
        # Generated civilization is reconstruction-only and does not duplicate
        # its walls into player construction state.
        state=LivingWorldState()
        building=BuildingSystem(state,self.registry)
        building.attach_settlement_physicalization(physical)
        self.assertFalse(state.structures)
        self.assertFalse(building.passable(wall_pos,True))
        self.assertTrue(building.blocks_sight(wall_pos))
        self.assertEqual(building.room_at(WorldPos(room_cell.x,room_cell.y,0))['room_id'],room['room_id'])

    def test_physicalization_is_bounded_to_active_region(self):
        class Cache:
            def load_generated_settlement_plan(self,*_): return None
            def store_generated_settlement_plan(self,*_): pass
            def commit_generated(self): pass
        env=SimpleNamespace(
            open_water=False,slope=5,flood_risk=4,wetness=40,soil_fertility=70,farmland=75,
            resources=SimpleNamespace(stone=50,timber=55,freshwater=50),resource_opportunity=52,
        )
        world=SimpleNamespace(
            generator=SimpleNamespace(world_seed=b'bounded-physical'),delta_source=Cache(),
            registry=self.registry,environment_at=lambda pos:env,
        )
        regions={
            (0,0):RegionBlockPlan('r0',0,0,1,'grassland',{'grassland':25},1,1,1,1,True,(120,120),70,'agrarian','settled'),
            (1,0):RegionBlockPlan('r1',1,0,1,'grassland',{'grassland':25},1,1,1,1,True,(640,120),70,'forest','settled'),
        }
        region_planner=SimpleNamespace(plan=lambda rx,ry,persist=True:regions[(rx,ry)])
        physical=SettlementPhysicalizationSystem(
            world,self.registry,region_planner,SettlementSkeletonPlanner(world)
        )
        settlements=[
            SimpleNamespace(uid='settlement:a',region_x=0,region_y=0,population=45),
            SimpleNamespace(uid='settlement:b',region_x=1,region_y=0,population=45),
        ]
        physical.sync(settlements,(0,0),radius=0)
        self.assertEqual(physical.active_settlement_ids,('settlement:a',))
        self.assertTrue(all(c.settlement_id=='settlement:a' for c in physical.cells()))
        physical.sync(settlements,(1,0),radius=0)
        self.assertEqual(physical.active_settlement_ids,('settlement:b',))
        self.assertTrue(all(c.settlement_id=='settlement:b' for c in physical.cells()))


    def test_village_start_selects_target_before_environment_then_finalizes_gateway(self):
        from unittest.mock import patch
        from worldseed.app import _find_village_target, _village_gateway_spawn

        town=SimpleNamespace(uid="settlement:0:0",x=100,y=100,region_x=0,region_y=0,population=35)
        region=SimpleNamespace(region_x=0,region_y=0)
        skeleton=SimpleNamespace(plan=SimpleNamespace(common_cells=[(100,100)],gateway_cells=[(120,100)]))
        class FakeRegionPlanner:
            def __init__(self,world): pass
            def plan(self,rx,ry,persist=True): return region
        class FakeSkeletonPlanner:
            calls=0
            def __init__(self,world): pass
            def plan(self,plan,uid,population,persist=True):
                FakeSkeletonPlanner.calls+=1;return skeleton
        class FakeSociety:
            def __init__(self,seed,registry,planner): pass
            def settlement_for_cell(self,rx,ry):
                if (rx,ry)==(0,0): return (town,[],None,None,None)
                return None
        fields=SimpleNamespace(elevation=32000)
        terrain=SimpleNamespace(passable=True,tags=())
        environment=SimpleNamespace(open_water=False)
        world=SimpleNamespace(
            registry=SimpleNamespace(terrains={"land":terrain}),
            generator=SimpleNamespace(sample_fields=lambda pos:fields,terrain_at=lambda pos:"land"),
            environment_at=lambda pos:environment,
        )
        with patch("worldseed.app.RegionBlockPlanner",FakeRegionPlanner), \
             patch("worldseed.app.SettlementSkeletonPlanner",FakeSkeletonPlanner), \
             patch("worldseed.app.ProceduralSocietyGenerator",FakeSociety):
            target=_find_village_target(world,b"seed",self.registry)
            self.assertIs(target,town)
            self.assertEqual(FakeSkeletonPlanner.calls,0,"target selection must not require prepared hydrology")
            pos=_village_gateway_spawn(world,target)
        self.assertEqual(FakeSkeletonPlanner.calls,1)
        self.assertEqual((pos.x,pos.y,pos.z),(122,100,0))

    def test_village_target_rejects_base_ocean_anchor(self):
        from unittest.mock import patch
        from worldseed.app import _find_village_target
        wet=SimpleNamespace(uid="settlement:0:0",x=100,y=100,region_x=0,region_y=0,population=35)
        dry=SimpleNamespace(uid="settlement:1:0",x=620,y=100,region_x=1,region_y=0,population=35)
        class FakeRegionPlanner:
            def __init__(self,world): pass
        class FakeSociety:
            def __init__(self,seed,registry,planner): pass
            def settlement_for_cell(self,rx,ry):
                return (wet,[],None,None,None) if (rx,ry)==(0,0) else ((dry,[],None,None,None) if (rx,ry)==(1,0) else None)
        world=SimpleNamespace(generator=SimpleNamespace(sample_fields=lambda pos:SimpleNamespace(elevation=20000 if pos.x<512 else 32000)))
        with patch("worldseed.app.RegionBlockPlanner",FakeRegionPlanner),patch("worldseed.app.ProceduralSocietyGenerator",FakeSociety):
            self.assertIs(_find_village_target(world,b"seed",self.registry),dry)


if __name__ == "__main__":
    unittest.main()
