import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.world.generator import WorldGenerator, WorldFields
from worldseed.world.hydrology import HydrologyGenerator, HydrologyDomain
from worldseed.world.coastal_mouths import contains
from worldseed.world.landforms import SEA_LEVEL_REFERENCE as SEA


class CoastalMouthTests(unittest.TestCase):
    def setUp(self):
        self.gen=WorldGenerator(b'mouth-regression',ContentRegistry.load(DATA_DIR),version=8)
        self.gen.landforms_v8.sample=lambda x,y:SimpleNamespace(elevation=SEA+80-x*10)
        self.gen.sample_fields=lambda p:WorldFields(SEA+80-p.x*10,40000,33000,35000)
        self.gen.climate_at=lambda p:SimpleNamespace(prevailing_wind_dx=0,prevailing_wind_dy=1024)
        self.gen.topography_at=lambda p:SimpleNamespace(slope=1000,ruggedness=0)
        self.gen.coast_v8.sample=lambda *a,**k:SimpleNamespace(shelter=70,sediment_potential=90)
        self.hydro=HydrologyGenerator(self.gen,version=2,morphology_version=2)
        self.gen.attach_hydrology(self.hydro)
        width=9;n=width*width;origin=-4
        elevation=tuple(SEA+80-(origin+x)*160 for y in range(width) for x in range(width))
        flow=[-1]*n;classes=[0]*n;acc=[0]*n;idx=4*width+4
        flow[idx]=idx+1;classes[idx]=3;acc[idx]=2400
        self.domain=HydrologyDomain(0,0,2,16,1,4,origin,origin,width,width,elevation,elevation,
                                   tuple(flow),tuple(acc),(7,)*n,tuple(classes),(60,)*n,(), 'fixture',
                                   channel_gradient=(100,)*n)
        self.hydro._domain_cache[(0,0)]=self.domain
        self.hydro._domain_cache[(0,-1)]=self.domain
        self.hydro._domain_cache[(-1,0)]=self.domain
        self.hydro._domain_cache[(-1,-1)]=self.domain

    def test_connected_distributaries_conserve_discharge_and_rebuild(self):
        plans,_=self.gen.coastal_mouths.plans(self.domain)
        self.assertEqual(len(plans),1);plan=plans[0]
        self.assertEqual(len(plan.branches),2)
        self.assertEqual(sum(plan.branch_discharge),plan.discharge)
        for path in plan.branches:
            self.assertIn(path[0],plan.primary)
            self.assertLess(self.gen.landforms_v8.sample(*path[-1]).elevation,SEA)
        self.gen.coastal_mouths._indexes.clear()
        self.assertEqual(self.gen.coastal_mouths.plans(self.domain)[0],plans)

    def test_projection_has_connected_water_estuary_width_and_lobes(self):
        plans,_=self.gen.coastal_mouths.plans(self.domain);plan=plans[0]
        water=set();deposits=set()
        x0,y0,x1,y1=plan.bounds
        for y in range(y0,y1+1):
            for x in range(x0,x1+1):
                hit=self.gen.coastal_mouths.at(WorldPos(x,y,0),self.domain)
                if hit:
                    
                    if hit[2]>=0:water.add((x,y))
                    elif hit[0]=='core:tidal_flat':deposits.add((x,y))
        self.assertTrue(deposits)
        self.assertTrue(any(not contains(plan.primary,x,y,plan.width) for x,y in water))
        pending=[plan.primary[0]];seen=set(pending)
        while pending:
            x,y=pending.pop()
            for p in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                if p in water and p not in seen:seen.add(p);pending.append(p)
        self.assertEqual(seen,water)
        for path in plan.branches:self.assertIn(path[-1],water)

    def test_old_contract_and_no_preparation_are_unchanged(self):
        p=WorldPos(24,12,0)
        self.gen.set_coast_morphology_version(1)
        self.assertEqual(self.hydro.surface_at(p),self.hydro.drainage_surface_at(p))
        self.gen.set_coast_morphology_version(2)
        self.hydro._domain_cache.clear()
        with patch.object(self.hydro,'generate',side_effect=AssertionError('unprepared generation')):
            self.assertIsNone(self.hydro.surface_at(p,prepared_only=True))

    def test_seam_copies_and_negative_coordinates_agree(self):
        a=self.gen.coastal_mouths.plans(self.domain)[0]
        b=self.gen.coastal_mouths.plans(replace(self.domain,domain_x=-1,fingerprint='neighbor'))[0]
        self.assertEqual(a,b)
        for x,y in ((-1,-1),(0,0),(16,-12),(32,12)):
            p=WorldPos(x,y,0)
            self.assertEqual(self.gen.coastal_mouths.at(p,self.domain),
                             self.gen.coastal_mouths.at(p,replace(self.domain,domain_x=-1,fingerprint='neighbor')))

    def test_steep_or_exposed_mouth_does_not_invent_a_delta(self):
        steep=replace(self.domain,channel_gradient=(900,)*81,fingerprint='steep')
        self.assertFalse(self.gen.coastal_mouths.plans(steep)[0][0].branches)
        self.gen.coast_v8.sample=lambda *a,**k:SimpleNamespace(shelter=10,sediment_potential=90)
        exposed=replace(self.domain,fingerprint='exposed')
        self.assertFalse(self.gen.coastal_mouths.plans(exposed)[0][0].branches)

    def test_new_water_agrees_with_hydrology_and_current(self):
        plan=self.gen.coastal_mouths.plans(self.domain)[0][0]
        p=WorldPos(*plan.branches[0][-1],0)
        surface=self.hydro.surface_at(p,prepared_only=True)
        self.assertTrue(surface.delta)
        self.assertIn(surface.terrain_override,('core:estuary_shallow','core:estuary_deep'))
        self.assertGreater(surface.crossing_cost,0)
        self.assertEqual(self.gen.current_at(p,prepared_only=True).kind,'estuary')

    def test_barrier_and_lagoon_require_shallow_sediment_supply(self):
        self.gen.coast_v8.sample=lambda *a,**k:SimpleNamespace(shelter=65,sediment_potential=90)
        plan=self.gen.coastal_mouths.plans(self.domain)[0][0]
        self.assertTrue(plan.barrier);self.assertTrue(plan.lagoon)
        p=WorldPos(*plan.barrier[-1],0)
        self.assertEqual(self.gen.coastal_mouths.at(p,self.domain)[0],'core:shore')
        lagoon=WorldPos(*plan.lagoon[-1],0)
        self.assertEqual(self.gen.coastal_mouths.at(lagoon,self.domain)[2],-1)
        self.gen.coastal_mouths._indexes.clear()
        self.gen.coast_v8.sample=lambda *a,**k:SimpleNamespace(shelter=65,sediment_potential=10)
        self.assertFalse(self.gen.coastal_mouths.plans(self.domain)[0][0].barrier)

    def test_current_inspection_never_builds_mouth_plans(self):
        self.gen.coastal_mouths._indexes.clear()
        with patch.object(self.gen.coastal_mouths,'plans',side_effect=AssertionError('render planned mouths')), patch.object(self.gen,'_surface_terrain_base',return_value='core:ocean_shallow'):
            self.gen.current_at(WorldPos(8,0,0),prepared_only=True)


class CoastSaveTests(unittest.TestCase):
    def test_v1_save_and_v2_surface_caches_remain_separate(self):
        import tempfile
        from pathlib import Path
        from worldseed.persistence.database import WorldDatabase
        from worldseed.world.world import World
        from worldseed.core.coords import ChunkKey
        registry=ContentRegistry.load(DATA_DIR);seed=b'coast-pinned'
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'world.db';db=WorldDatabase.create(path,'test',seed.hex())
            key=ChunkKey(0,0,0)
            db.set_meta('coast_morphology_version',1)
            db.store_generated_surface_chunk(key,8,2,2,1,['core:rocky_shore']*1024)
            db.store_generated_surface_chunk(key,8,2,2,2,['core:estuary_deep']*1024)
            db.commit_generated();db.close()
            db=WorldDatabase.open(path)
            try:
                world=World(WorldGenerator(seed,registry,version=8),registry,db)
                self.assertEqual(world.generator.coast_morphology_version,1)
                with patch.object(world.generator,'generate_chunk',side_effect=AssertionError('cache rerolled')):
                    self.assertEqual(world.tile_at(WorldPos(0,0,0)).terrain_id,'core:rocky_shore')
                self.assertEqual(db.load_generated_surface_chunk(key,8,2,2,2)[0],'core:estuary_deep')
            finally:db.close()
