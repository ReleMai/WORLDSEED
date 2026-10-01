"""Dev43 settlement diversity, specialization, and authored-art contracts."""

import json
import unittest
from types import SimpleNamespace

from PIL import Image

from worldseed.config import DATA_DIR, PACKAGE_ROOT, SETTLEMENT_PLAN_VERSION
from worldseed.content.registry import ContentRegistry
from worldseed.systems.settlement_planner import SettlementSkeleton, SettlementSkeletonPlanner
from worldseed.systems.settlement_population import SettlementPopulationBinder
from worldseed.systems.state import LivingWorldState
from worldseed.world.region_blocks import RegionBlockPlan, RegionRoadExit


class Cache:
    def load_generated_settlement_plan(self, *_):
        return None

    def store_generated_settlement_plan(self, *_):
        pass

    def commit_generated(self):
        pass


class Env:
    open_water = False
    slope = 9
    flood_risk = 6
    wetness = 42
    soil_fertility = 81
    farmland = 84
    resources = SimpleNamespace(stone=76, timber=73, freshwater=61)
    resource_opportunity = 78


class Dev43SettlementDiversityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)

    def skeleton(self, archetype="mining", uid="settlement:dev43"):
        world = SimpleNamespace(
            generator=SimpleNamespace(world_seed=f"dev43-{archetype}".encode()),
            delta_source=Cache(),
            registry=self.registry,
            settlement_plan_version=SETTLEMENT_PLAN_VERSION,
            environment_at=lambda pos: Env(),
        )
        region = RegionBlockPlan(
            uid=f"region:{archetype}", region_x=0, region_y=0, version=1,
            dominant_biome="grassland", biome_mix={"grassland": 25},
            mean_elevation=1, mean_moisture=1, mean_temperature=1, relief=1,
            settlement_present=True, settlement_anchor=(180, 180), settlement_score=88,
            settlement_archetype=archetype, control_potential="settled",
            roads=(RegionRoadExit("north", 180, "road"), RegionRoadExit("east", 180, "road")),
        )
        return SettlementSkeletonPlanner(world).plan(region, uid, 110, persist=False)

    def test_specializations_are_bounded_and_terrain_content_is_derived(self):
        allowed_resources={"mining", "logging", "farming", "livestock", "fishing"}
        allowed_crops={
            "core:wheat", "core:turnip", "core:barley", "core:beans", "core:cabbage",
            "core:carrot", "core:onion", "core:flax", "core:corn", "core:pumpkin",
        }
        allowed_animals={"core:pig", "core:cow", "core:chicken", "core:sheep"}
        saw_crops=saw_livestock=False
        for archetype in ("mining", "forest", "agrarian", "frontier", "fishing"):
            plan=self.skeleton(archetype,f"settlement:dev43:{archetype}").plan
            self.assertEqual(2,len(plan.resource_specializations))
            self.assertEqual(2,len(set(plan.resource_specializations)))
            self.assertTrue(set(plan.resource_specializations)<=allowed_resources)
            if "farming" in plan.resource_specializations:
                saw_crops=True
                self.assertTrue(plan.crop_ids)
                self.assertLessEqual(len(plan.crop_ids),4)
                self.assertTrue(set(plan.crop_ids)<=allowed_crops)
            else:
                self.assertFalse(plan.crop_ids)
            if "livestock" in plan.resource_specializations:
                saw_livestock=True
                self.assertEqual(2,len(plan.livestock_species_ids))
                self.assertTrue(set(plan.livestock_species_ids)<=allowed_animals)
            else:
                self.assertFalse(plan.livestock_species_ids)
        self.assertTrue(saw_crops)
        self.assertTrue(saw_livestock)

    def test_layout_has_varied_building_forms_and_natural_road_turns(self):
        skeleton=self.skeleton()
        residence_forms={
            row.building_form for row in skeleton.structures
            if row.function in {"residence", "inn", "barracks", "outskirt_camp"}
        }
        self.assertGreaterEqual(len(residence_forms),3)
        turns=[]
        for road in skeleton.roads:
            directions=[(b[0]-a[0],b[1]-a[1]) for a,b in zip(road.polyline,road.polyline[1:])]
            turns.append(sum(a!=b for a,b in zip(directions,directions[1:])))
        self.assertGreaterEqual(max(turns),3)

    def test_plan_cache_round_trip_preserves_dev43_authority(self):
        skeleton=self.skeleton("frontier","settlement:dev43:roundtrip")
        restored=SettlementSkeleton.from_dict(skeleton.to_dict())
        self.assertEqual(skeleton.fingerprint,restored.fingerprint)
        self.assertEqual(skeleton.plan.resource_specializations,restored.plan.resource_specializations)
        self.assertEqual(skeleton.plan.crop_ids,restored.plan.crop_ids)
        self.assertEqual(skeleton.plan.livestock_species_ids,restored.plan.livestock_species_ids)
        self.assertEqual(
            [(p.resource_deposit,p.crop_id,p.livestock_species_ids) for p in skeleton.parcels],
            [(p.resource_deposit,p.crop_id,p.livestock_species_ids) for p in restored.parcels],
        )
        self.assertEqual(
            [s.building_form for s in skeleton.structures],
            [s.building_form for s in restored.structures],
        )

    def test_livestock_materializes_idempotently_inside_plan_owned_pen(self):
        skeleton=self.skeleton("frontier","settlement:dev43:livestock")
        pen=next(p for p in skeleton.parcels if p.purpose=="animal_pen")
        state=LivingWorldState()
        binder=SettlementPopulationBinder(state,self.registry,b"dev43-livestock",SimpleNamespace())
        settlement=SimpleNamespace(uid=skeleton.plan.settlement_id)
        binder._sync_livestock(settlement,skeleton)
        self.assertEqual(4,len(state.creatures))
        self.assertEqual(set(pen.livestock_species_ids),{row.species_id for row in state.creatures.values()})
        self.assertTrue(all(row.domestic and row.pen_id==pen.uid for row in state.creatures.values()))
        self.assertTrue(all((row.x,row.y) in set(pen.cells) for row in state.creatures.values()))
        binder._sync_livestock(settlement,skeleton)
        self.assertEqual(4,len(state.creatures))

    def test_authored_workshop_and_crop_assets_are_distinct_rgba(self):
        manifest=json.loads((PACKAGE_ROOT/"assets"/"visuals.json").read_text(encoding="utf-8"))
        paths=list(manifest["settlement_pieces"].values())
        paths.extend(manifest["crops"]["core:corn"])
        paths.extend(manifest["crops"]["core:pumpkin"])
        files=[PACKAGE_ROOT/path for path in paths]
        self.assertEqual(len(files),len(set(paths)))
        self.assertEqual(len(files),len({path.read_bytes() for path in files}))
        for path in files:
            with self.subTest(asset=path.name), Image.open(path) as image:
                self.assertEqual("RGBA",image.mode)
                self.assertIsNotNone(image.getchannel("A").getbbox())


if __name__ == "__main__":
    unittest.main()
