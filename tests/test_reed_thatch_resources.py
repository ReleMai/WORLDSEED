"""Regression coverage for accessible reeds and timber-derived roof thatch."""
import unittest
from types import SimpleNamespace

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.systems.resources import ResourceSystem


class ShorelineAndThatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=ContentRegistry.load(DATA_DIR)

    def make_resources(self,version=5):
        fields=SimpleNamespace(temperature=30000,moisture=9000)
        world=SimpleNamespace(
            generator=SimpleNamespace(sample_fields=lambda pos:fields),
            delta_source=None,
            tile_at=lambda pos:SimpleNamespace(terrain_id=(
                "core:river_shallow" if pos.x<0 else "core:riverbank")))
        state=SimpleNamespace(clock_minute=0,structures={},containers={},crops={},
                              soils={},resource_depletion={})
        return ResourceSystem(state,self.registry,b"shore-reed-test",world,version=version)

    def test_accessible_bank_reeds_ignore_broad_climate_moisture(self):
        system=self.make_resources()
        positions=[WorldPos(x,y,0) for x in range(2,62) for y in range(-10,10)]
        result={pos:system._shoreline_reed(pos,"core:riverbank") for pos in positions}
        reeds=sum(fid=="core:reed_bed" for fid in result.values())
        self.assertGreater(reeds,100)
        self.assertEqual(result,{pos:system._shoreline_reed(pos,"core:riverbank")
                                  for pos in reversed(positions)})

    def test_prepared_empty_bank_cells_still_materialize_reeds(self):
        system=self.make_resources()
        blank=tuple([None]*1024)
        system._load_prepared_feature_chunk=lambda cx,cy,season:blank
        candidate=next(WorldPos(x,y,0) for x in range(2,60)
                       for y in range(-20,20)
                       if system._shoreline_reed(WorldPos(x,y,0),"core:riverbank"))
        self.assertEqual(system._base_feature(candidate),"core:reed_bed")
        self.assertEqual(system.feature_at(candidate).stage,"mature")

    def test_actual_pine_harvest_yields_boughs(self):
        from worldseed.systems.resources import FeatureView
        class Inventory:
            def __init__(self):self.items={};self.added={}
            def add(self,iid,amount):
                self.items[iid]=self.items.get(iid,0)+amount
                self.added[iid]=self.added.get(iid,0)+amount
        system=self.make_resources()
        system.feature_at=lambda pos,minute=None:FeatureView("core:pine_tree","mature")
        system._best_tool=lambda *args:1
        system.state.player_skills={"woodcutting":0}
        system.state.player_talents=set()
        inv=Inventory()
        ok,message,minutes,outputs=system.harvest(WorldPos(11,22,0),inv,30)
        self.assertTrue(ok,message)
        self.assertGreaterEqual(outputs["core:pine_bough"],2)
        self.assertLessEqual(outputs["core:pine_bough"],4)
        self.assertEqual(inv.added["core:pine_bough"],outputs["core:pine_bough"])

    def test_older_resource_versions_are_unchanged(self):
        system=self.make_resources(version=4)
        self.assertIsNone(system._shoreline_reed(WorldPos(2,3,0),"core:riverbank"))

    def test_inland_grass_cannot_generate_reeds(self):
        system=self.make_resources()
        system.world.tile_at=lambda pos:SimpleNamespace(terrain_id="core:grass")
        for x in range(-12,12):
            for y in range(-12,12):
                self.assertIsNone(system._shoreline_reed(WorldPos(x,y,0),"core:grass"))

    def test_pine_chopping_produces_roof_material(self):
        pine=self.registry.resources["core:pine_tree"]
        self.assertIn("core:pine_bough",pine.yields)
        self.assertEqual(pine.yields["core:pine_bough"],(2,4))
        self.assertIn("thatch_material",self.registry.items["core:pine_bough"].tags)


if __name__=="__main__":
    unittest.main()
