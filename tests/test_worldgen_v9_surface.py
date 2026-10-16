from __future__ import annotations

from collections import Counter
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import ChunkKey, WorldPos
from worldseed.world.generator import WorldFields, WorldGenerator
from worldseed.world.surface_v9 import Q, SurfaceV9Sampler


class WorldgenV9SurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)

    @staticmethod
    def _flat_topography(slope=0, ridge=0, valley=0):
        return SimpleNamespace(sample_xy=lambda x, y: SimpleNamespace(
            slope=slope, ridge_exposure=ridge, valley_depth=valley))

    def test_twelve_seeds_keep_exact_v8_physical_fields_and_cave_authority(self):
        for seed_index in range(12):
            seed = f"v9-physical-source-{seed_index}".encode()
            old = WorldGenerator(seed, self.registry, version=8)
            new = WorldGenerator(seed, self.registry, version=9)
            for x, y in ((-2049,-1025),(-17,16),(-1,-1),(0,0),(16,15),(913,-1441),(2048,8192)):
                pos = WorldPos(x,y,0)
                self.assertEqual(new.sample_fields(pos), old.sample_fields(pos), (seed_index,pos))
                self.assertEqual(new.climate_at(pos), old.climate_at(pos))
                self.assertEqual(new.topography_at(pos), old.topography_at(pos))
            self.assertIs(type(new.caves), type(old.caves))
            self.assertEqual(new.caves.connector_span(0,0),old.caves.connector_span(0,0))

    def test_twelve_seeds_global_cell_queries_are_order_and_cache_independent(self):
        # Include both sides of positive/negative chunk and lattice boundaries.
        coordinates = [(x,y) for y in (-33,-32,-17,-16,-1,0,15,16,31,32)
                       for x in (-33,-32,-17,-16,-1,0,15,16,31,32)]
        for seed_index in range(12):
            seed = f"v9-seam-source-{seed_index}".encode()
            forward = WorldGenerator(seed,self.registry,version=9)
            reverse = WorldGenerator(seed,self.registry,version=9)
            a = {xy:forward.landcover_at(WorldPos(*xy,0)) for xy in coordinates}
            b = {xy:reverse.landcover_at(WorldPos(*xy,0)) for xy in reversed(coordinates)}
            self.assertEqual(a,b,seed_index)
            forward._lattice_cache.clear()
            forward.surface_v9._topographic_node.cache_clear()
            for xy in coordinates[::11]:
                self.assertEqual(forward.landcover_at(WorldPos(*xy,0)),a[xy])

    def test_ecotones_form_connected_patches_instead_of_per_cell_confetti(self):
        generator = WorldGenerator(b"v9-grove-continuity",self.registry,version=9)
        sampler = SurfaceV9Sampler(generator._value_noise,self._flat_topography())
        marginal = WorldFields(36000,39000,33000,39000)
        cells = {(x,y):sampler.sample(x,y,marginal) for y in range(-64,65) for x in range(-64,65)}
        counts = Counter(c.terrain_id for c in cells.values())
        self.assertGreater(counts["core:forest"],500)
        self.assertGreater(counts["core:grass"],500)
        boundaries = edges = isolated = max_patch_step = 0
        for (x,y),cell in cells.items():
            neighbors = [cells[(x+dx,y+dy)] for dx,dy in ((1,0),(-1,0),(0,1),(0,-1))
                         if (x+dx,y+dy) in cells]
            boundaries += sum(n.terrain_id != cell.terrain_id for n in neighbors)
            edges += len(neighbors)
            isolated += len(neighbors)==4 and all(n.terrain_id != cell.terrain_id for n in neighbors)
            max_patch_step = max(max_patch_step,max(abs(n.cover_patch-cell.cover_patch) for n in neighbors))
        self.assertLess(boundaries / edges,0.035)
        self.assertLess(isolated / len(cells),0.001)
        self.assertLess(max_patch_step,700)

    def test_actual_adjacent_chunk_materialization_is_order_independent(self):
        seed = b"v9-adjacent-materialization"
        a = WorldGenerator(seed,self.registry,version=9)
        b = WorldGenerator(seed,self.registry,version=9)
        keys = (ChunkKey(-1,0,0),ChunkKey(0,0,0))
        forward = {key:tuple(a.generate_chunk(key).terrain) for key in keys}
        reverse = {key:tuple(b.generate_chunk(key).terrain) for key in reversed(keys)}
        self.assertEqual(forward,reverse)

    def test_habitat_remains_causal_and_slope_aware(self):
        noise = lambda *args: Q // 2
        sheltered = SurfaceV9Sampler(noise,self._flat_topography(valley=8000))
        exposed = SurfaceV9Sampler(noise,self._flat_topography(slope=45000,ridge=9000))
        marginal = WorldFields(36000,40500,33000,39000)
        self.assertEqual(sheltered.sample(0,0,marginal).terrain_id,"core:forest")
        self.assertEqual(exposed.sample(0,0,marginal).terrain_id,"core:grass")
        self.assertEqual(exposed.sample(0,0,WorldFields(48000,50000,33000,45000)).terrain_id,"core:rock")
        for sampler in (sheltered,exposed):
            self.assertEqual(sampler.sample(0,0,WorldFields(35000,10000,45000,28000)).terrain_id,"core:scrub")
            self.assertEqual(sampler.sample(0,0,WorldFields(35000,50000,10000,40000)).terrain_id,"core:tundra")
            self.assertEqual(sampler.sample(0,0,WorldFields(53000,50000,33000,45000)).terrain_id,"core:rock")

    def test_cave_coast_ocean_and_prepared_hydrology_keep_priority(self):
        generator = WorldGenerator(b"v9-priority",self.registry,version=9)
        pos = WorldPos(0,0,0)
        fields = WorldFields(35000,45000,33000,43000)
        with patch.object(generator,"sample_fields",return_value=fields), \
             patch.object(generator,"_connector_span",return_value=1), \
             patch.object(generator.surface_v9,"sample",side_effect=AssertionError("protected mouth reached landcover")):
            self.assertEqual(generator.terrain_at(pos),"core:cave_mouth")
        with patch.object(generator,"sample_fields",return_value=fields), \
             patch.object(generator,"_connector_span",return_value=0), \
             patch.object(generator,"_phase5_coast_terrain",return_value="core:rocky_shore"), \
             patch.object(generator.surface_v9,"sample",side_effect=AssertionError("protected coast reached landcover")):
            self.assertEqual(generator.terrain_at(pos),"core:rocky_shore")
        with patch.object(generator,"sample_fields",return_value=WorldFields(10000,45000,33000,43000)), \
             patch.object(generator,"_connector_span",return_value=0), \
             patch.object(generator,"_phase5_coast_terrain",return_value=None), \
             patch.object(generator.surface_v9,"sample",side_effect=AssertionError("ocean reached landcover")):
            self.assertEqual(generator.terrain_at(pos),"core:ocean_deep")
        hydro = SimpleNamespace(surface_at=lambda _:SimpleNamespace(
            terrain_override="core:river_shallow",river_class=2,river_depth_class=1))
        generator.attach_hydrology(hydro)
        with patch.object(generator,"sample_fields",return_value=fields), \
             patch.object(generator,"_connector_span",return_value=0), \
             patch.object(generator,"_phase5_coast_terrain",return_value=None):
            self.assertEqual(generator.terrain_at(pos),"core:river_shallow")

    def test_dry_land_ids_preserve_traversability_and_existing_resource_habitats(self):
        # No new solid tile/barrier or parallel harvest identity is introduced.
        for terrain_id in ("core:grass","core:forest","core:scrub","core:tundra","core:rock"):
            self.assertTrue(self.registry.terrains[terrain_id].passable,terrain_id)
            self.assertTrue(any(terrain_id in row.terrains for row in self.registry.resources.values()),terrain_id)
        self.assertEqual(WorldGenerator(b"cache-bound", self.registry, version=9).surface_v9._topographic_node.cache_info().maxsize,8192)
        old = WorldGenerator(b"legacy-no-v9-readmodel",self.registry,version=8)
        self.assertIsNone(old.landcover_at(WorldPos(0,0,0)))
        new = WorldGenerator(b"v9-no-underground-readmodel",self.registry,version=9)
        self.assertIsNone(new.landcover_at(WorldPos(0,0,-1)))


    def test_topography_cache_does_not_retain_an_unloaded_world(self):
        import gc
        import weakref
        sampler=SurfaceV9Sampler(lambda *args:32767,self._flat_topography())
        sampler._topographic_node(0,0)
        reference=weakref.ref(sampler)
        del sampler
        gc.collect()
        self.assertIsNone(reference())


if __name__ == "__main__":
    unittest.main()
