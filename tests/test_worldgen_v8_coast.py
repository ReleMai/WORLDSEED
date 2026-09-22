from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from worldseed.config import DATA_DIR, COAST_MORPHOLOGY_VERSION
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.persistence.database import WorldDatabase
from worldseed.world.generator import WorldGenerator
from worldseed.world.world import World
from worldseed.world.coast_v8 import (
    COAST_MORPHOLOGY_ALGORITHM, COAST_MORPHOLOGY_VERSION,
)
from worldseed.world.landforms import SEA_LEVEL_REFERENCE


class WorldgenV8CoastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=ContentRegistry.load(DATA_DIR)
        cls.seed=b'worldgen-v8-phase5-coast'
        cls.gen=WorldGenerator(cls.seed,cls.registry,version=8)

    def _find_coast(self):
        # Search only geological elevation first; coast sampling itself is more
        # expensive and should be tested on a physically plausible candidate.
        for y in range(-3072,3073,96):
            for x in range(-3072,3073,96):
                center=self.gen.landforms_v8.sample(x,y).elevation
                ocean=center<SEA_LEVEL_REFERENCE
                around=[
                    self.gen.landforms_v8.sample(x+dx,y+dy).elevation<SEA_LEVEL_REFERENCE
                    for dx,dy in ((64,0),(-64,0),(0,64),(0,-64))
                ]
                if any(v!=ocean for v in around):
                    return WorldPos(x,y,0)
        self.fail('fixture seed did not expose a coast in audit window')

    def test_phase5_coast_read_model_is_deterministic(self):
        pos=self._find_coast()
        a=self.gen.coast_at(pos)
        b=WorldGenerator(self.seed,self.registry,version=8).coast_at(pos)
        self.assertEqual(a,b)
        self.assertEqual(a.version,COAST_MORPHOLOGY_VERSION)
        self.assertEqual(a.algorithm,COAST_MORPHOLOGY_ALGORITHM)

    def test_legacy_worlds_do_not_adopt_v8_coast_model(self):
        old=WorldGenerator(self.seed,self.registry,version=7)
        self.assertIsNone(old.coast_at(WorldPos(0,0,0)))

    def test_coast_fields_are_bounded_and_physically_typed(self):
        pos=self._find_coast()
        coast=self.gen.coast_at(pos)
        self.assertTrue(coast.near_coast)
        for value in (
            coast.shelf_depth,coast.land_fraction,coast.open_sea,
            coast.wave_exposure,coast.shelter,coast.bay_score,
            coast.headland_score,coast.tidal_flat_potential,
            coast.marsh_potential,coast.sediment_potential,
            coast.estuary_strength,coast.delta_potential,
            coast.lagoon_potential,
        ):
            self.assertGreaterEqual(value,0)
            self.assertLessEqual(value,100)
        if coast.ocean:
            self.assertIn(coast.shelf_class,{'intertidal','shallow','shelf','deep'})
            self.assertIn(coast.coast_kind,{'nearshore','protected_bay','tidal_flat'})
        else:
            self.assertEqual(coast.shelf_class,'land')
            self.assertIn(coast.coast_kind,{'beach','rocky','cliff','headland','marsh','tidal_flat'})
        self.assertIn(coast.shore_material,{'sand','gravel','rock','mud'})

    def test_bathymetry_uses_horizontal_continental_geometry(self):
        # Two ocean cells with similar raw depth need not share shelf class:
        # distance to opposite land is explicitly part of the read model.
        found=[]
        for y in range(-2048,2049,128):
            for x in range(-2048,2049,128):
                if self.gen.landforms_v8.sample(x,y).elevation>=SEA_LEVEL_REFERENCE:
                    continue
                c=self.gen.coast_at(WorldPos(x,y,0))
                if c is not None:
                    found.append(c)
        self.assertTrue(found)
        self.assertTrue(any(c.shelf_depth>0 for c in found))
        self.assertGreaterEqual(len({c.shelf_class for c in found}),2)

    def test_coast_sampling_does_not_change_authoritative_terrain(self):
        pos=self._find_coast()
        before=self.gen.terrain_at(pos)
        self.gen.coast_at(pos)
        after=self.gen.terrain_at(pos)
        self.assertEqual(before,after)

    def test_negative_coordinates_use_same_absolute_contract(self):
        a=self.gen.coast_at(WorldPos(-513,-769,0))
        b=self.gen.coast_at(WorldPos(-513,-769,0))
        self.assertEqual(a,b)

    def test_new_save_enables_coast_materialization_but_legacy_missing_meta_stays_zero(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'new.db'
            db=WorldDatabase.create(path,'new',self.seed.hex())
            self.assertEqual(db.get_meta('coast_morphology_version'),COAST_MORPHOLOGY_VERSION)
            world=World(WorldGenerator(self.seed,self.registry,version=8),self.registry,db)
            self.assertEqual(world.generator.coast_morphology_version,COAST_MORPHOLOGY_VERSION)
            db.connection.execute("DELETE FROM world_meta WHERE key='coast_morphology_version'")
            db.connection.commit();db.close()

            old=WorldDatabase.open(path)
            self.assertEqual(old.get_meta('coast_morphology_version'),0)
            old_world=World(WorldGenerator(self.seed,self.registry,version=8),self.registry,old)
            self.assertEqual(old_world.generator.coast_morphology_version,0)
            old.close()

    def test_materializer_maps_physical_coast_classes_to_gameplay_terrain(self):
        from types import SimpleNamespace
        gen=WorldGenerator(self.seed,self.registry,version=8)
        fields=gen.sample_fields(WorldPos(0,0,0))
        cases=[
            (SimpleNamespace(ocean=True,shelf_class='intertidal'), 'core:ocean_wade'),
            (SimpleNamespace(ocean=True,shelf_class='shallow'), 'core:ocean_shallow'),
            (SimpleNamespace(ocean=True,shelf_class='shelf'), 'core:ocean_shelf'),
            (SimpleNamespace(ocean=True,shelf_class='deep'), 'core:ocean_deep'),
            (SimpleNamespace(ocean=False,coast_distance=4,marsh_potential=0,tidal_flat_potential=0,coast_kind='cliff',shore_material='rock'), 'core:coastal_cliff'),
            (SimpleNamespace(ocean=False,coast_distance=4,marsh_potential=0,tidal_flat_potential=0,coast_kind='rocky',shore_material='rock'), 'core:rocky_shore'),
            (SimpleNamespace(ocean=False,coast_distance=4,marsh_potential=0,tidal_flat_potential=0,coast_kind='beach',shore_material='gravel'), 'core:coastal_gravel'),
            (SimpleNamespace(ocean=False,coast_distance=10,marsh_potential=20,tidal_flat_potential=85,coast_kind='tidal_flat',shore_material='mud'), 'core:tidal_flat'),
            (SimpleNamespace(ocean=False,coast_distance=18,marsh_potential=90,tidal_flat_potential=55,coast_kind='marsh',shore_material='mud'), 'core:salt_marsh'),
        ]
        original=gen.coast_at
        try:
            for coast,expected in cases:
                gen.coast_at=lambda *_args, _coast=coast, **_kwargs:_coast
                self.assertEqual(gen._phase5_coast_terrain(WorldPos(0,0,0),fields),expected)
        finally:
            gen.coast_at=original

    def test_coast_version_zero_preserves_pre_phase5_surface_projection(self):
        gen=WorldGenerator(self.seed,self.registry,version=8)
        # Find a v1 materialized coastal terrain distinct from the old generic
        # sand/shore/ocean depth projection, then verify version 0 does not use it.
        candidate=None
        new_ids={'core:rocky_shore','core:coastal_cliff','core:coastal_gravel','core:tidal_flat','core:salt_marsh'}
        coast=self._find_coast()
        for y in range(coast.y-160,coast.y+161,8):
            for x in range(coast.x-160,coast.x+161,8):
                tid=gen._surface_terrain_base(WorldPos(x,y,0))
                if tid in new_ids:
                    candidate=WorldPos(x,y,0);break
            if candidate:break
        self.assertIsNotNone(candidate)
        new_tid=gen._surface_terrain_base(candidate)
        gen.set_coast_morphology_version(0)
        old_tid=gen._surface_terrain_base(candidate)
        self.assertIn(new_tid,new_ids)
        self.assertNotIn(old_tid,new_ids)


if __name__=='__main__':
    unittest.main()
