import unittest
from types import SimpleNamespace

from worldseed.config import DATA_DIR, SETTLEMENT_PLAN_VERSION
from worldseed.content.registry import ContentRegistry
from worldseed.systems.physicalization import SettlementPhysicalizationSystem
from worldseed.systems.settlement_planner import SettlementSkeletonPlanner
from worldseed.world.region_blocks import RegionBlockPlan, RegionRoadExit


class Cache:
    def load_generated_settlement_plan(self, *_):
        return None
    def store_generated_settlement_plan(self, *_):
        pass
    def commit_generated(self):
        pass


class Env:
    open_water=False
    slope=5
    flood_risk=4
    wetness=38
    soil_fertility=78
    farmland=82
    resources=SimpleNamespace(stone=78,timber=74,freshwater=62)
    resource_opportunity=71


class ProfessionYardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=ContentRegistry.load(DATA_DIR)

    def skeleton(self, archetype: str, uid: str):
        world=SimpleNamespace(
            generator=SimpleNamespace(world_seed=f"yard-{archetype}".encode()),
            delta_source=Cache(),
            registry=self.registry,
            settlement_plan_version=SETTLEMENT_PLAN_VERSION,
            environment_at=lambda pos: Env(),
        )
        region=RegionBlockPlan(
            uid=f"region:{archetype}",region_x=0,region_y=0,version=1,
            dominant_biome="grassland",biome_mix={"grassland":25},
            mean_elevation=1,mean_moisture=1,mean_temperature=1,relief=1,
            settlement_present=True,settlement_anchor=(180,180),settlement_score=88,
            settlement_archetype=archetype,control_potential="settled",
            roads=(RegionRoadExit("north",180,"road"),RegionRoadExit("east",180,"road")),
        )
        return world,region,SettlementSkeletonPlanner(world).plan(
            region,uid,110,persist=False
        )

    def test_profession_workshops_have_authored_yard_identity(self):
        _,_,mining=self.skeleton("mining","settlement:yard:mining")
        smithy=next(s for s in mining.structures if s.function=="smithy")
        smith_pieces=[p for p in mining.pieces if p.structure_plan_id==smithy.uid]
        smith_ids={p.piece_id for p in smith_pieces}
        self.assertIn("core:profession_sign_piece",smith_ids)
        self.assertIn("core:ore_pile_piece",smith_ids)
        self.assertIn("core:coal_bin_piece",smith_ids)
        self.assertTrue(any(p.role=="yard_fence" for p in smith_pieces))
        self.assertTrue(any(p.role=="yard_gate" for p in smith_pieces))

        _,_,forest=self.skeleton("forest","settlement:yard:forest")
        logging=next(s for s in forest.structures if s.function=="logging_camp")
        wood_ids={p.piece_id for p in forest.pieces if p.structure_plan_id==logging.uid}
        self.assertIn("core:logging_hut_piece",wood_ids)
        self.assertIn("core:logging_tool_rack_piece",wood_ids)
        self.assertIn("core:dev43_timber_stack_piece",wood_ids)
        self.assertIn("core:logging_sapling_piece",wood_ids)
        self.assertIn("core:logging_managed_tree_piece",wood_ids)

        _,_,agrarian=self.skeleton("agrarian","settlement:yard:agrarian")
        field=next(s for s in agrarian.structures if s.function=="farm_field")
        field_ids={p.piece_id for p in agrarian.pieces if p.structure_plan_id==field.uid}
        self.assertIn("core:dev43_plowed_soil_piece",field_ids)
        self.assertIn("core:dev43_field_fence_piece",field_ids)
        if agrarian.plan.version >= 10:
            barn=next(s for s in agrarian.structures if s.function=="barn")
            shed=next(p for p in agrarian.pieces if p.structure_plan_id==barn.uid and p.piece_id=="core:farm_shed_piece")
            self.assertNotIn((shed.x,shed.y),set(field.footprint))
            self.assertNotIn("core:farm_shed_piece",field_ids)
        else:
            self.assertIn("core:farm_shed_piece",field_ids)

    def test_every_generated_building_has_authoritative_service_path(self):
        _,_,skeleton=self.skeleton("mining","settlement:yard:roads")
        service=[r for r in skeleton.roads if r.road_class=="service_path"]
        self.assertTrue(service)
        all_road_cells={cell for road in skeleton.roads for cell in road.polyline}
        road_ids={r.uid for r in skeleton.roads}
        for structure in skeleton.structures:
            ex,ey=structure.entrance
            # A door may already open directly onto an existing street. Only
            # buildings set back from that street need a separate service-path
            # segment; both cases must join the same authoritative road graph.
            self.assertTrue(
                any(abs(ex-x)+abs(ey-y)<=1 for x,y in all_road_cells),
                structure.uid,
            )
        for parcel in skeleton.parcels:
            if parcel.structure_ids:
                self.assertTrue(parcel.access_road_id)
                self.assertIn(parcel.access_road_id,road_ids)

    def test_yard_fences_block_but_gates_and_service_paths_are_passable(self):
        world,region,skeleton=self.skeleton("mining","settlement:yard:physical")
        region_planner=SimpleNamespace(plan=lambda rx,ry,persist=True:region)
        planner=SettlementSkeletonPlanner(world)
        # Seed the exact generated skeleton so physicalization reads the same plan.
        planner._cache["settlement:yard:physical"]=skeleton
        physical=SettlementPhysicalizationSystem(world,self.registry,region_planner,planner)
        settlement=SimpleNamespace(
            uid="settlement:yard:physical",region_x=0,region_y=0,population=110,
            culture_id="",faction_id="",
        )
        physical.sync([settlement],(0,0),radius=0)
        fence=next(c for c in physical.cells() if c.structure_piece_role=="yard_fence")
        gate=next(c for c in physical.cells() if c.structure_piece_role=="yard_gate")
        self.assertFalse(physical.passable(SimpleNamespace(x=fence.x,y=fence.y,z=0),True))
        self.assertTrue(physical.passable(SimpleNamespace(x=gate.x,y=gate.y,z=0),True))
        road=next(c for c in physical.cells() if c.road_ids and any(
            rid in {r.uid for r in skeleton.roads if r.road_class=="service_path"}
            for rid in c.road_ids
        ))
        self.assertTrue(physical.passable(SimpleNamespace(x=road.x,y=road.y,z=0),True))


if __name__=="__main__":
    unittest.main()
